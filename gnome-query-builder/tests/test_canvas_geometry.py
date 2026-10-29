# SPDX-License-Identifier: Apache-2.0
"""Geometry helpers for join-canvas edge anchors (no GTK display needed)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(ROOT))

# Import geometry helpers without realizing widgets — canvas imports gi but
# does not open a display at import time.
from gnome_query_builder.databricks.base import TableRef
from gnome_query_builder.model.join_graph import GraphTable, JoinEdge
from gnome_query_builder.ui import canvas as C


class CanvasGeometryTests(unittest.TestCase):
    def _table(self, name: str, cols: list[str], x: float, y: float) -> GraphTable:
        return GraphTable(
            ref=TableRef("main", "default", name),
            alias=name,
            columns=cols,
            x=x,
            y=y,
            placed=True,
        )

    def test_port_y_follows_join_column_not_node_mid(self) -> None:
        t = self._table(
            "orders",
            ["order_id", "customer_id", "amount"],
            40,
            36,
        )
        y_cust = C._column_port_y(t, "customer_id")
        y_mid = t.y + C._node_height(t) / 2.0
        y_expected = t.y + C.COL_FIRST_BASELINE + 1 * C.NODE_COL_H - 4.0
        self.assertAlmostEqual(y_cust, y_expected)
        self.assertNotAlmostEqual(y_cust, y_mid)

    def test_edge_attaches_to_facing_sides_and_columns(self) -> None:
        left = self._table("customers", ["customer_id", "name"], 40, 36)
        right = self._table(
            "orders", ["order_id", "customer_id", "amount"], 320, 80
        )
        edge = JoinEdge("customers", "customer_id", "orders", "customer_id")
        (x1, y1), (x2, y2), start_side, end_side = C._edge_endpoints(left, right, edge)
        self.assertEqual(start_side, "right")
        self.assertEqual(end_side, "left")
        self.assertAlmostEqual(x1, left.x + C.NODE_W)
        self.assertAlmostEqual(x2, right.x)
        self.assertAlmostEqual(y1, C._column_port_y(left, "customer_id"))
        self.assertAlmostEqual(y2, C._column_port_y(right, "customer_id"))

    def test_bezier_midpoint_on_curve(self) -> None:
        c1, c2 = C._bezier_controls(0, 0, 100, 40)
        mid = C._bezier_point(0.5, (0, 0), c1, c2, (100, 40))
        self.assertGreater(mid[0], 20)
        self.assertLess(mid[0], 80)


if __name__ == "__main__":
    unittest.main()
