# SPDX-License-Identifier: Apache-2.0
"""Spike-quality join canvas: table nodes + join edges via GtkDrawingArea/Cairo."""

from __future__ import annotations

import math

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from gnome_query_builder.model.join_graph import GraphTable, JoinEdge, JoinGraph  # noqa: E402

NODE_W = 200.0
HEADER_H = 28.0
FQN_BASELINE = 42.0
COL_FIRST_BASELINE = 58.0
NODE_COL_H = 16.0
NODE_MAX_COLS = 6
NODE_PAD = 10.0
PORT_R = 4.5
HIT_EDGE_PX = 16.0

JOIN_TYPES = ("INNER", "LEFT", "RIGHT", "FULL")


def _node_height(table: GraphTable) -> float:
    n = min(len(table.columns), NODE_MAX_COLS)
    extra = 14.0 if len(table.columns) > NODE_MAX_COLS else 0.0
    # Space through last visible column baseline + padding
    body = COL_FIRST_BASELINE + max(n, 1) * NODE_COL_H + extra - HEADER_H
    return HEADER_H + max(body, 40.0)


def _column_index(table: GraphTable, column: str) -> int | None:
    name = (column or "").strip()
    if not name:
        return None
    for i, col in enumerate(table.columns[:NODE_MAX_COLS]):
        if col == name:
            return i
    # Join key exists but scrolled off visible list — pin to last visible row.
    if name in table.columns and table.columns:
        return min(len(table.columns), NODE_MAX_COLS) - 1
    return None


def _column_port_y(table: GraphTable, column: str) -> float:
    """Vertical center of the join-key column row (or node mid as fallback)."""
    idx = _column_index(table, column)
    if idx is None:
        return table.y + _node_height(table) / 2.0
    # Text baseline is at COL_FIRST_BASELINE + i*H; center the port on the glyph box.
    baseline = table.y + COL_FIRST_BASELINE + idx * NODE_COL_H
    return baseline - 4.0


def _port(
    table: GraphTable, column: str, *, side: str
) -> tuple[float, float]:
    y = _column_port_y(table, column)
    if side == "left":
        return (table.x, y)
    return (table.x + NODE_W, y)


def _edge_endpoints(
    left: GraphTable, right: GraphTable, edge: JoinEdge
) -> tuple[tuple[float, float], tuple[float, float], str, str]:
    """Return (start, end, start_side, end_side) for drawing left→right join."""
    # Attach to the side facing the other node; Y follows join key columns.
    if left.x + NODE_W / 2.0 <= right.x + NODE_W / 2.0:
        start = _port(left, edge.left_column, side="right")
        end = _port(right, edge.right_column, side="left")
        return start, end, "right", "left"
    start = _port(left, edge.left_column, side="left")
    end = _port(right, edge.right_column, side="right")
    return start, end, "left", "right"


def _bezier_point(
    t: float,
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    p3: tuple[float, float],
) -> tuple[float, float]:
    u = 1.0 - t
    x = (
        u * u * u * p0[0]
        + 3 * u * u * t * p1[0]
        + 3 * u * t * t * p2[0]
        + t * t * t * p3[0]
    )
    y = (
        u * u * u * p0[1]
        + 3 * u * u * t * p1[1]
        + 3 * u * t * t * p2[1]
        + t * t * t * p3[1]
    )
    return (x, y)


def _bezier_controls(
    x1: float, y1: float, x2: float, y2: float
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Horizontal-ish cubic controls so the curve leaves/enters ports orthogonally."""
    dx = abs(x2 - x1)
    pull = max(40.0, min(120.0, dx * 0.45))
    if x1 <= x2:
        c1 = (x1 + pull, y1)
        c2 = (x2 - pull, y2)
    else:
        c1 = (x1 - pull, y1)
        c2 = (x2 + pull, y2)
    return c1, c2


def _table_by_alias(graph: JoinGraph, alias: str) -> GraphTable | None:
    for t in graph.tables:
        if t.alias == alias:
            return t
    return None


def _dist_point_seg(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float
) -> float:
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    qx, qy = x1 + t * dx, y1 + t * dy
    return math.hypot(px - qx, py - qy)


def _dist_point_bezier(
    px: float,
    py: float,
    p0: tuple[float, float],
    c1: tuple[float, float],
    c2: tuple[float, float],
    p3: tuple[float, float],
    *,
    samples: int = 24,
) -> float:
    best = float("inf")
    prev = p0
    for i in range(1, samples + 1):
        pt = _bezier_point(i / samples, p0, c1, c2, p3)
        best = min(best, _dist_point_seg(px, py, prev[0], prev[1], pt[0], pt[1]))
        prev = pt
    return best


class JoinCanvas(Gtk.DrawingArea):
    """Interactive canvas: drag table nodes; click edges to select joins."""

    __gsignals__ = {
        "graph-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "selection-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self) -> None:
        super().__init__()
        self.set_draw_func(self._on_draw)
        self.set_content_width(720)
        self.set_content_height(360)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_focusable(True)

        self._graph = JoinGraph()
        self._selected_alias: str | None = None
        self._selected_edge_idx: int | None = None
        self._drag_alias: str | None = None
        self._drag_origin_x = 0.0
        self._drag_origin_y = 0.0
        self._hover_alias: str | None = None

        click = Gtk.GestureClick.new()
        click.set_button(1)
        click.connect("pressed", self._on_click_pressed)
        click.connect("released", self._on_click_released)
        self.add_controller(click)

        drag = Gtk.GestureDrag.new()
        drag.set_button(1)
        drag.connect("drag-begin", self._on_drag_begin)
        drag.connect("drag-update", self._on_drag_update)
        drag.connect("drag-end", self._on_drag_end)
        self.add_controller(drag)

        motion = Gtk.EventControllerMotion.new()
        motion.connect("motion", self._on_motion)
        self.add_controller(motion)

        self.add_css_class("join-canvas")

    # --- public API -------------------------------------------------------------

    def set_graph(self, graph: JoinGraph) -> None:
        self._graph = graph
        self._layout_if_needed()
        self._selected_alias = None
        self._selected_edge_idx = None
        self.queue_draw()
        self.emit("selection-changed")

    def get_graph(self) -> JoinGraph:
        return self._graph

    def refresh(self) -> None:
        self._layout_if_needed()
        self.queue_draw()

    @property
    def selected_edge_index(self) -> int | None:
        return self._selected_edge_idx

    @property
    def selected_edge(self) -> JoinEdge | None:
        if self._selected_edge_idx is None:
            return None
        if 0 <= self._selected_edge_idx < len(self._graph.edges):
            return self._graph.edges[self._selected_edge_idx]
        return None

    def select_edge(self, index: int | None) -> None:
        self._selected_edge_idx = index
        self._selected_alias = None
        self.queue_draw()
        self.emit("selection-changed")

    def cycle_selected_join_type(self) -> None:
        edge = self.selected_edge
        if edge is None:
            return
        cur = edge.join_type.upper()
        try:
            i = JOIN_TYPES.index(cur)
        except ValueError:
            i = 0
        edge.join_type = JOIN_TYPES[(i + 1) % len(JOIN_TYPES)]
        self.queue_draw()
        self.emit("graph-changed")
        self.emit("selection-changed")

    def remove_selected(self) -> None:
        if self._selected_alias is not None:
            self._graph.remove_alias(self._selected_alias)
            self._selected_alias = None
            self._selected_edge_idx = None
            self.queue_draw()
            self.emit("graph-changed")
            self.emit("selection-changed")
            return
        if self._selected_edge_idx is not None:
            idx = self._selected_edge_idx
            if 0 <= idx < len(self._graph.edges):
                del self._graph.edges[idx]
            self._selected_edge_idx = None
            self.queue_draw()
            self.emit("graph-changed")
            self.emit("selection-changed")

    # --- layout -----------------------------------------------------------------

    def _layout_if_needed(self) -> None:
        for i, t in enumerate(self._graph.tables):
            if not t.placed:
                t.x = 40.0 + (i % 3) * (NODE_W + 80.0)
                t.y = 36.0 + (i // 3) * 160.0
                t.placed = True
        self._update_content_size()

    def _update_content_size(self) -> None:
        if not self._graph.tables:
            self.set_content_width(720)
            self.set_content_height(360)
            return
        max_x = max(t.x + NODE_W + 40.0 for t in self._graph.tables)
        max_y = max(t.y + _node_height(t) + 40.0 for t in self._graph.tables)
        self.set_content_width(max(720, int(max_x)))
        self.set_content_height(max(360, int(max_y)))

    def _edge_geometry(self, edge: JoinEdge):
        left = _table_by_alias(self._graph, edge.left_alias)
        right = _table_by_alias(self._graph, edge.right_alias)
        if left is None or right is None:
            return None
        (x1, y1), (x2, y2), _, _ = _edge_endpoints(left, right, edge)
        c1, c2 = _bezier_controls(x1, y1, x2, y2)
        return (x1, y1), c1, c2, (x2, y2), left, right

    # --- hit testing ------------------------------------------------------------

    def _hit_node(self, x: float, y: float) -> GraphTable | None:
        for t in reversed(self._graph.tables):
            h = _node_height(t)
            if t.x <= x <= t.x + NODE_W and t.y <= y <= t.y + h:
                return t
        return None

    def _hit_edge(self, x: float, y: float) -> int | None:
        best_i: int | None = None
        best_d = HIT_EDGE_PX
        for i, edge in enumerate(self._graph.edges):
            geom = self._edge_geometry(edge)
            if geom is None:
                continue
            p0, c1, c2, p3, _left, _right = geom
            d = _dist_point_bezier(x, y, p0, c1, c2, p3)
            # Also accept hits on the join chip around the curve midpoint.
            mx, my = _bezier_point(0.5, p0, c1, c2, p3)
            d = min(d, math.hypot(x - mx, y - my) - 10.0)
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    # --- events -----------------------------------------------------------------

    def _on_click_pressed(self, _gesture, _n: int, x: float, y: float) -> None:
        # Prefer edges over nodes when clicking near a join chip/line so selection
        # of joins isn't swallowed by overlapping node bounds.
        edge_i = self._hit_edge(x, y)
        if edge_i is not None:
            self._selected_alias = None
            self._selected_edge_idx = edge_i
            self.queue_draw()
            self.emit("selection-changed")
            return
        node = self._hit_node(x, y)
        if node is not None:
            self._selected_alias = node.alias
            self._selected_edge_idx = None
            self.queue_draw()
            self.emit("selection-changed")
            return
        self._selected_alias = None
        self._selected_edge_idx = None
        self.queue_draw()
        self.emit("selection-changed")

    def _on_click_released(self, gesture, _n: int, x: float, y: float) -> None:
        if gesture.get_current_event() is None:
            return
        state = gesture.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            edge_i = self._hit_edge(x, y)
            if edge_i is not None:
                self._selected_edge_idx = edge_i
                self.cycle_selected_join_type()

    def _on_drag_begin(self, gesture, x: float, y: float) -> None:
        # Don't start a node drag when the pointer is on a join edge/chip.
        if self._hit_edge(x, y) is not None and self._hit_node(x, y) is None:
            self._drag_alias = None
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        node = self._hit_node(x, y)
        if node is None:
            self._drag_alias = None
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
        # If clicking a port/column row near an edge, still allow drag from node body.
        self._drag_alias = node.alias
        self._drag_origin_x = node.x
        self._drag_origin_y = node.y
        self._selected_alias = node.alias
        self._selected_edge_idx = None
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.emit("selection-changed")

    def _on_drag_update(self, _gesture, offset_x: float, offset_y: float) -> None:
        if self._drag_alias is None:
            return
        node = _table_by_alias(self._graph, self._drag_alias)
        if node is None:
            return
        node.x = max(8.0, self._drag_origin_x + offset_x)
        node.y = max(8.0, self._drag_origin_y + offset_y)
        node.placed = True
        self._update_content_size()
        # Edges recompute from live node positions on every draw.
        self.queue_draw()

    def _on_drag_end(self, *_args) -> None:
        if self._drag_alias is not None:
            self.emit("graph-changed")
        self._drag_alias = None

    def _on_motion(self, _ctrl, x: float, y: float) -> None:
        node = self._hit_node(x, y)
        alias = node.alias if node else None
        if alias != self._hover_alias:
            self._hover_alias = alias
            self.queue_draw()

    # --- drawing ----------------------------------------------------------------

    def _on_draw(self, _area, cr, width: int, height: int) -> None:
        cr.set_source_rgb(0.96, 0.96, 0.97)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        cr.set_source_rgba(0.75, 0.78, 0.82, 0.45)
        cr.set_line_width(1.0)
        step = 24
        for gx in range(0, width, step):
            cr.move_to(gx + 0.5, 0)
            cr.line_to(gx + 0.5, height)
        for gy in range(0, height, step):
            cr.move_to(0, gy + 0.5)
            cr.line_to(width, gy + 0.5)
        cr.stroke()

        if not self._graph.tables:
            cr.set_source_rgb(0.35, 0.38, 0.42)
            cr.select_font_face("Sans", 0, 0)
            cr.set_font_size(14)
            msg = "Double-click a UC table or use Add table to canvas"
            extents = cr.text_extents(msg)
            cr.move_to((width - extents.width) / 2, height / 2)
            cr.show_text(msg)
            return

        # Curves under nodes; chips/arrows after so labels stay readable.
        for i, edge in enumerate(self._graph.edges):
            self._draw_edge(
                cr, edge, selected=(i == self._selected_edge_idx), phase="curve"
            )

        active_ports = self._active_ports()
        for t in self._graph.tables:
            self._draw_node(
                cr,
                t,
                selected=(t.alias == self._selected_alias),
                hover=(t.alias == self._hover_alias),
                active_ports=active_ports.get(t.alias, set()),
            )

        for i, edge in enumerate(self._graph.edges):
            self._draw_edge(
                cr, edge, selected=(i == self._selected_edge_idx), phase="overlay"
            )

    def _active_ports(self) -> dict[str, set[tuple[str, str]]]:
        """Map alias → {(side, column)} for ports used by edges."""
        out: dict[str, set[tuple[str, str]]] = {}
        for edge in self._graph.edges:
            left = _table_by_alias(self._graph, edge.left_alias)
            right = _table_by_alias(self._graph, edge.right_alias)
            if left is None or right is None:
                continue
            _s, _e, start_side, end_side = _edge_endpoints(left, right, edge)
            out.setdefault(edge.left_alias, set()).add((start_side, edge.left_column))
            out.setdefault(edge.right_alias, set()).add((end_side, edge.right_column))
        return out

    def _draw_edge(
        self, cr, edge: JoinEdge, *, selected: bool, phase: str = "all"
    ) -> None:
        geom = self._edge_geometry(edge)
        if geom is None:
            return
        (x1, y1), c1, c2, (x2, y2), _left, _right = geom

        if phase in ("all", "curve"):
            if selected:
                cr.set_source_rgb(0.18, 0.45, 0.85)
                cr.set_line_width(3.0)
            else:
                cr.set_source_rgb(0.35, 0.45, 0.55)
                cr.set_line_width(2.0)
            cr.move_to(x1, y1)
            cr.curve_to(c1[0], c1[1], c2[0], c2[1], x2, y2)
            cr.stroke()

        if phase not in ("all", "overlay"):
            return

        # Arrow at end, oriented along the final tangent (c2 → end).
        # Stop just short of the port so the arrow doesn't swallow the dot.
        tx, ty = x2 - c2[0], y2 - c2[1]
        length = math.hypot(tx, ty) or 1.0
        ux, uy = tx / length, ty / length
        px, py = -uy, ux
        tip = (x2 - ux * (PORT_R + 1.0), y2 - uy * (PORT_R + 1.0))
        back = (tip[0] - ux * 9.0, tip[1] - uy * 9.0)
        if selected:
            cr.set_source_rgb(0.18, 0.45, 0.85)
        else:
            cr.set_source_rgb(0.35, 0.45, 0.55)
        cr.set_line_width(2.0)
        cr.move_to(tip[0], tip[1])
        cr.line_to(back[0] + px * 4.5, back[1] + py * 4.5)
        cr.move_to(tip[0], tip[1])
        cr.line_to(back[0] - px * 4.5, back[1] - py * 4.5)
        cr.stroke()

        # Join chip on the bezier midpoint (drawn above nodes).
        mx, my = _bezier_point(0.5, (x1, y1), c1, c2, (x2, y2))
        left_col = edge.left_column
        right_col = edge.right_column
        if len(left_col) > 16:
            left_col = left_col[:14] + "…"
        if len(right_col) > 16:
            right_col = right_col[:14] + "…"
        label = f"{edge.join_type}  {left_col} = {right_col}"
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(11)
        te = cr.text_extents(label)
        pad_x, pad_y = 7, 4
        w, h = te.width + pad_x * 2, te.height + pad_y * 2
        lx = mx - w / 2
        ly = my - h / 2 - 2
        # Soft shadow so chip reads over the curve/grid
        cr.set_source_rgba(0, 0, 0, 0.10)
        self._round_rect(cr, lx + 1, ly + 1, w, h, 4)
        cr.fill()
        self._round_rect(cr, lx, ly, w, h, 4)
        if selected:
            cr.set_source_rgb(0.18, 0.45, 0.85)
        else:
            cr.set_source_rgb(1, 1, 1)
        cr.fill_preserve()
        cr.set_source_rgb(0.55, 0.60, 0.68)
        cr.set_line_width(1.0)
        cr.stroke()
        if selected:
            cr.set_source_rgb(1, 1, 1)
        else:
            cr.set_source_rgb(0.15, 0.18, 0.22)
        cr.move_to(lx + pad_x, ly + pad_y - te.y_bearing)
        cr.show_text(label)

    def _draw_node(
        self,
        cr,
        table: GraphTable,
        *,
        selected: bool,
        hover: bool,
        active_ports: set[tuple[str, str]],
    ) -> None:
        h = _node_height(table)
        x, y = table.x, table.y

        cr.set_source_rgba(0, 0, 0, 0.08)
        self._round_rect(cr, x + 2, y + 3, NODE_W, h, 8)
        cr.fill()

        if selected:
            cr.set_source_rgb(0.93, 0.96, 1.0)
        elif hover:
            cr.set_source_rgb(0.98, 0.99, 1.0)
        else:
            cr.set_source_rgb(1, 1, 1)
        self._round_rect(cr, x, y, NODE_W, h, 8)
        cr.fill_preserve()
        if selected:
            cr.set_source_rgb(0.18, 0.45, 0.85)
            cr.set_line_width(2.2)
        else:
            cr.set_source_rgb(0.70, 0.74, 0.80)
            cr.set_line_width(1.2)
        cr.stroke()

        cr.save()
        self._round_rect(cr, x, y, NODE_W, HEADER_H, 8)
        cr.rectangle(x, y + HEADER_H / 2, NODE_W, HEADER_H / 2)
        cr.clip()
        if selected:
            cr.set_source_rgb(0.18, 0.45, 0.85)
        else:
            cr.set_source_rgb(0.22, 0.28, 0.36)
        cr.rectangle(x, y, NODE_W, HEADER_H)
        cr.fill()
        cr.restore()

        cr.set_source_rgb(1, 1, 1)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(12)
        cr.move_to(x + NODE_PAD, y + 18)
        cr.show_text(f"`{table.alias}`")

        cr.set_source_rgb(0.35, 0.38, 0.42)
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(10)
        fqn = table.ref.fqn
        if len(fqn) > 28:
            fqn = fqn[:25] + "…"
        cr.move_to(x + NODE_PAD, y + FQN_BASELINE)
        cr.show_text(fqn)

        # Highlight join-key column rows lightly.
        join_cols = {col for _side, col in active_ports}
        cols = table.columns[:NODE_MAX_COLS]
        for i, col in enumerate(cols):
            baseline = y + COL_FIRST_BASELINE + i * NODE_COL_H
            if col in join_cols:
                cr.set_source_rgba(0.18, 0.45, 0.85, 0.10)
                cr.rectangle(x + 4, baseline - 12, NODE_W - 8, NODE_COL_H)
                cr.fill()
            cr.set_source_rgb(0.25, 0.28, 0.32)
            cr.set_font_size(11)
            cr.move_to(x + NODE_PAD, baseline)
            cr.show_text(f"· {col}")
        if len(table.columns) > NODE_MAX_COLS:
            more = len(table.columns) - NODE_MAX_COLS
            cr.set_source_rgb(0.45, 0.48, 0.52)
            cr.move_to(x + NODE_PAD, y + COL_FIRST_BASELINE + len(cols) * NODE_COL_H)
            cr.show_text(f"… +{more} more")

        # Draw only ports that participate in joins (column-anchored).
        for side, column in active_ports:
            px, py = _port(table, column, side=side)
            cr.set_source_rgb(1, 1, 1)
            cr.arc(px, py, PORT_R, 0, 6.2832)
            cr.fill_preserve()
            cr.set_source_rgb(0.18, 0.45, 0.85)
            cr.set_line_width(1.5)
            cr.stroke()

    @staticmethod
    def _round_rect(cr, x: float, y: float, w: float, h: float, r: float) -> None:
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -1.5708, 0)
        cr.arc(x + w - r, y + h - r, r, 0, 1.5708)
        cr.arc(x + r, y + h - r, r, 1.5708, 3.1416)
        cr.arc(x + r, y + r, r, 3.1416, 4.7124)
        cr.close_path()
