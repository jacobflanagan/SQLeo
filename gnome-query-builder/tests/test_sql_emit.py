# SPDX-License-Identifier: Apache-2.0
"""Headless unit tests for join graph → Spark SQL emission."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(ROOT))

from gnome_query_builder.databricks.base import TableRef
from gnome_query_builder.model.join_graph import JoinGraph
from gnome_query_builder.model.sql_emit import emit_spark_sql


class SqlEmitTests(unittest.TestCase):
    def test_two_table_inner_join_three_level_names(self) -> None:
        g = JoinGraph()
        customers = g.add_table(
            TableRef("main", "default", "customers"),
            columns=["customer_id", "name"],
        )
        orders = g.add_table(
            TableRef("main", "default", "orders"),
            columns=["order_id", "customer_id", "amount"],
        )
        g.ensure_edge_for_new_table(orders)

        sql = emit_spark_sql(g)
        self.assertIn("`main`.`default`.`customers` AS `customers`", sql)
        self.assertIn("INNER JOIN `main`.`default`.`orders` AS `orders`", sql)
        self.assertIn("`customers`.`customer_id` = `orders`.`customer_id`", sql)
        self.assertIn("`customers`.`name`", sql)
        self.assertNotIn("SELECT *", sql)
        self.assertEqual(customers.alias, "customers")

    def test_empty_graph_comment(self) -> None:
        sql = emit_spark_sql(JoinGraph())
        self.assertTrue(sql.lstrip().startswith("--"))


if __name__ == "__main__":
    unittest.main()
