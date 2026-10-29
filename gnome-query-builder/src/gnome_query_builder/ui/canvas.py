# SPDX-License-Identifier: Apache-2.0
"""Spike-quality join canvas: table nodes + join edges via GtkDrawingArea/Cairo."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from gnome_query_builder.model.join_graph import GraphTable, JoinEdge, JoinGraph  # noqa: E402

NODE_W = 200.0
NODE_H_BASE = 56.0
NODE_COL_H = 16.0
NODE_MAX_COLS = 6
NODE_PAD = 10.0
PORT_R = 5.0
HIT_EDGE_PX = 14.0

JOIN_TYPES = ("INNER", "LEFT", "RIGHT", "FULL")


def _node_height(table: GraphTable) -> float:
    n = min(len(table.columns), NODE_MAX_COLS)
    extra = 14.0 if len(table.columns) > NODE_MAX_COLS else 0.0
    return NODE_H_BASE + n * NODE_COL_H + extra


def _port_left(table: GraphTable) -> tuple[float, float]:
    return (table.x, table.y + _node_height(table) / 2.0)


def _port_right(table: GraphTable) -> tuple[float, float]:
    return (table.x + NODE_W, table.y + _node_height(table) / 2.0)


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
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    qx, qy = x1 + t * dx, y1 + t * dy
    return ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5


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

        # CSS-ish cursor hint via CSS name
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
            if t.x == 0.0 and t.y == 0.0 and i > 0:
                # Only auto-place when still at origin and not the first table
                # that intentionally sits at (40,40) — check placed flag via
                # whether any non-default position exists.
                pass
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

    # --- hit testing ------------------------------------------------------------

    def _hit_node(self, x: float, y: float) -> GraphTable | None:
        # Top-most last
        for t in reversed(self._graph.tables):
            h = _node_height(t)
            if t.x <= x <= t.x + NODE_W and t.y <= y <= t.y + h:
                return t
        return None

    def _hit_edge(self, x: float, y: float) -> int | None:
        best_i: int | None = None
        best_d = HIT_EDGE_PX
        for i, edge in enumerate(self._graph.edges):
            left = _table_by_alias(self._graph, edge.left_alias)
            right = _table_by_alias(self._graph, edge.right_alias)
            if left is None or right is None:
                continue
            # Prefer connecting right port of left-side node → left port of right
            if left.x <= right.x:
                x1, y1 = _port_right(left)
                x2, y2 = _port_left(right)
            else:
                x1, y1 = _port_left(left)
                x2, y2 = _port_right(right)
            d = _dist_point_seg(x, y, x1, y1, x2, y2)
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    # --- events -----------------------------------------------------------------

    def _on_click_pressed(self, _gesture, _n: int, x: float, y: float) -> None:
        node = self._hit_node(x, y)
        if node is not None:
            self._selected_alias = node.alias
            self._selected_edge_idx = None
            self.queue_draw()
            self.emit("selection-changed")
            return
        edge_i = self._hit_edge(x, y)
        self._selected_alias = None
        self._selected_edge_idx = edge_i
        self.queue_draw()
        self.emit("selection-changed")

    def _on_click_released(self, gesture, _n: int, x: float, y: float) -> None:
        # Double-click edge cycles join type
        if gesture.get_current_event() is None:
            return
        # Gtk.GestureClick exposes n_presses via the pressed handler; use
        # a simple secondary: Ctrl+click cycles join type on edge.
        state = gesture.get_current_event_state()
        if state & Gdk.ModifierType.CONTROL_MASK:
            edge_i = self._hit_edge(x, y)
            if edge_i is not None:
                self._selected_edge_idx = edge_i
                self.cycle_selected_join_type()

    def _on_drag_begin(self, gesture, x: float, y: float) -> None:
        node = self._hit_node(x, y)
        if node is None:
            self._drag_alias = None
            gesture.set_state(Gtk.EventSequenceState.DENIED)
            return
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
        # Background
        cr.set_source_rgb(0.96, 0.96, 0.97)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Subtle grid
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

        # Edges under nodes
        for i, edge in enumerate(self._graph.edges):
            self._draw_edge(cr, edge, selected=(i == self._selected_edge_idx))

        for t in self._graph.tables:
            self._draw_node(
                cr,
                t,
                selected=(t.alias == self._selected_alias),
                hover=(t.alias == self._hover_alias),
            )

    def _draw_edge(self, cr, edge: JoinEdge, *, selected: bool) -> None:
        left = _table_by_alias(self._graph, edge.left_alias)
        right = _table_by_alias(self._graph, edge.right_alias)
        if left is None or right is None:
            return

        if left.x <= right.x:
            x1, y1 = _port_right(left)
            x2, y2 = _port_left(right)
        else:
            x1, y1 = _port_left(left)
            x2, y2 = _port_right(right)

        mx = (x1 + x2) / 2.0
        if selected:
            cr.set_source_rgb(0.18, 0.45, 0.85)
            cr.set_line_width(3.0)
        else:
            cr.set_source_rgb(0.35, 0.45, 0.55)
            cr.set_line_width(2.0)

        cr.move_to(x1, y1)
        cr.curve_to(mx, y1, mx, y2, x2, y2)
        cr.stroke()

        # Arrow tip at end
        cr.set_line_width(2.0)
        cr.move_to(x2, y2)
        cr.line_to(x2 - 8, y2 - 5)
        cr.move_to(x2, y2)
        cr.line_to(x2 - 8, y2 + 5)
        cr.stroke()

        # Label chip
        label = f"{edge.join_type}  {edge.left_column} = {edge.right_column}"
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(11)
        te = cr.text_extents(label)
        lx = mx - te.width / 2 - 6
        ly = (y1 + y2) / 2 - 10
        pad_x, pad_y = 6, 3
        w, h = te.width + pad_x * 2, te.height + pad_y * 2
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
        self, cr, table: GraphTable, *, selected: bool, hover: bool
    ) -> None:
        h = _node_height(table)
        x, y = table.x, table.y

        # Shadow
        cr.set_source_rgba(0, 0, 0, 0.08)
        self._round_rect(cr, x + 2, y + 3, NODE_W, h, 8)
        cr.fill()

        # Body
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

        # Header bar
        cr.save()
        self._round_rect(cr, x, y, NODE_W, 28, 8)
        cr.rectangle(x, y + 14, NODE_W, 14)
        cr.clip()
        if selected:
            cr.set_source_rgb(0.18, 0.45, 0.85)
        else:
            cr.set_source_rgb(0.22, 0.28, 0.36)
        cr.rectangle(x, y, NODE_W, 28)
        cr.fill()
        cr.restore()

        cr.set_source_rgb(1, 1, 1)
        cr.select_font_face("Sans", 0, 1)  # bold
        cr.set_font_size(12)
        title = f"`{table.alias}`"
        cr.move_to(x + NODE_PAD, y + 18)
        cr.show_text(title)

        # FQN
        cr.set_source_rgb(0.35, 0.38, 0.42)
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(10)
        fqn = table.ref.fqn
        if len(fqn) > 28:
            fqn = fqn[:25] + "…"
        cr.move_to(x + NODE_PAD, y + 42)
        cr.show_text(fqn)

        # Columns
        cr.set_source_rgb(0.25, 0.28, 0.32)
        cr.set_font_size(11)
        cols = table.columns[:NODE_MAX_COLS]
        for i, col in enumerate(cols):
            cr.move_to(x + NODE_PAD, y + 58 + i * NODE_COL_H)
            cr.show_text(f"· {col}")
        if len(table.columns) > NODE_MAX_COLS:
            more = len(table.columns) - NODE_MAX_COLS
            cr.set_source_rgb(0.45, 0.48, 0.52)
            cr.move_to(x + NODE_PAD, y + 58 + len(cols) * NODE_COL_H)
            cr.show_text(f"… +{more} more")

        # Ports
        for px, py in (_port_left(table), _port_right(table)):
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
