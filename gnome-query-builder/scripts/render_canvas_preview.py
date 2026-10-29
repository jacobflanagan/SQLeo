#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Headless Cairo render of a sample join canvas → PNG (no display required)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(ROOT))

import cairo

from gnome_query_builder.databricks.base import TableRef
from gnome_query_builder.model.join_graph import JoinGraph
from gnome_query_builder.ui import canvas as canvas_mod


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/join-canvas-preview.png")
    g = JoinGraph()
    customers = g.add_table(
        TableRef("main", "default", "customers"),
        columns=["customer_id", "name", "email", "created_at"],
    )
    orders = g.add_table(
        TableRef("main", "default", "orders"),
        columns=["order_id", "customer_id", "amount", "status"],
    )
    g.ensure_edge_for_new_table(orders)
    items = g.add_table(
        TableRef("main", "default", "order_items"),
        columns=["item_id", "order_id", "sku", "qty"],
    )
    g.ensure_edge_for_new_table(items)
    g.set_join_type(0, "INNER")
    g.set_join_type(1, "LEFT")

    # Build a fake DrawingArea-like draw by calling canvas draw helpers via instance
    # without realizing a GTK widget: reuse geometry helpers + a thin stand-in.
    width, height = 760, 400
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)

    class _Fake:
        _graph = g
        _selected_alias = customers.alias
        _selected_edge_idx = 0
        _hover_alias = None

        def _draw_edge(self, cr, edge, *, selected):
            JoinCanvas = canvas_mod.JoinCanvas
            # Bind unbound methods from a temporary approach: copy logic by
            # instantiating helper functions already module-level where possible.
            JoinCanvas._draw_edge(self, cr, edge, selected=selected)

        def _draw_node(self, cr, table, *, selected, hover):
            JoinCanvas = canvas_mod.JoinCanvas
            JoinCanvas._draw_node(self, cr, table, selected=selected, hover=hover)

        @staticmethod
        def _round_rect(cr, x, y, w, h, r):
            canvas_mod.JoinCanvas._round_rect(cr, x, y, w, h, r)

    fake = _Fake()
    # Background + grid (inline to avoid GTK DrawingArea)
    cr.set_source_rgb(0.96, 0.96, 0.97)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    cr.set_source_rgba(0.75, 0.78, 0.82, 0.45)
    cr.set_line_width(1.0)
    for gx in range(0, width, 24):
        cr.move_to(gx + 0.5, 0)
        cr.line_to(gx + 0.5, height)
    for gy in range(0, height, 24):
        cr.move_to(0, gy + 0.5)
        cr.line_to(width, gy + 0.5)
    cr.stroke()

    for i, edge in enumerate(g.edges):
        fake._draw_edge(cr, edge, selected=(i == 0))
    for t in g.tables:
        fake._draw_node(cr, t, selected=(t.alias == customers.alias), hover=False)

    surface.write_to_png(str(out))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
