#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Headless Cairo render of a sample join canvas → PNG."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(ROOT))

import cairo

from gnome_query_builder.databricks.base import TableRef
from gnome_query_builder.model.join_graph import JoinGraph
from gnome_query_builder.ui.canvas import JoinCanvas


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
    orders.y = 120.0

    canvas = JoinCanvas()
    canvas.set_graph(g)
    canvas._selected_alias = customers.alias
    canvas._selected_edge_idx = 0

    width, height = 760, 420
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    cr = cairo.Context(surface)
    canvas._on_draw(canvas, cr, width, height)
    surface.write_to_png(str(out))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
