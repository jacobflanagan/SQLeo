# SPDX-License-Identifier: Apache-2.0
"""Offline mock Unity Catalog + fake warehouse runner for UI demos."""

from __future__ import annotations

from gnome_query_builder.databricks.base import ColumnInfo, QueryResult, TableRef

# Small synthetic lakehouse used when no CLI profile / host is available.
_MOCK_TREE: dict[str, dict[str, dict[str, list[ColumnInfo]]]] = {
    "samples": {
        "nyctaxi": {
            "trips": [
                ColumnInfo("tpep_pickup_datetime", "TIMESTAMP"),
                ColumnInfo("tpep_dropoff_datetime", "TIMESTAMP"),
                ColumnInfo("trip_distance", "DOUBLE"),
                ColumnInfo("fare_amount", "DOUBLE"),
                ColumnInfo("pickup_zip", "INT"),
                ColumnInfo("dropoff_zip", "INT"),
            ],
        },
        "bakehouse": {
            "sales_customers": [
                ColumnInfo("customer_id", "BIGINT"),
                ColumnInfo("customer_name", "STRING"),
                ColumnInfo("city", "STRING"),
                ColumnInfo("state", "STRING"),
            ],
            "sales_transactions": [
                ColumnInfo("transaction_id", "BIGINT"),
                ColumnInfo("customer_id", "BIGINT"),
                ColumnInfo("product_id", "BIGINT"),
                ColumnInfo("total_price", "DECIMAL(10,2)"),
                ColumnInfo("transaction_date", "DATE"),
            ],
            "sales_products": [
                ColumnInfo("product_id", "BIGINT"),
                ColumnInfo("product_name", "STRING"),
                ColumnInfo("category", "STRING"),
                ColumnInfo("price", "DECIMAL(10,2)"),
            ],
        },
    },
    "main": {
        "default": {
            "orders": [
                ColumnInfo("order_id", "BIGINT"),
                ColumnInfo("customer_id", "BIGINT"),
                ColumnInfo("order_date", "DATE"),
                ColumnInfo("amount", "DOUBLE"),
            ],
            "customers": [
                ColumnInfo("customer_id", "BIGINT"),
                ColumnInfo("name", "STRING"),
                ColumnInfo("email", "STRING"),
                ColumnInfo("region", "STRING"),
            ],
        },
    },
}


class MockBackend:
    def __init__(self, reason: str = "no Databricks credentials detected") -> None:
        self._reason = reason

    @property
    def mode(self) -> str:
        return "mock"

    @property
    def status_label(self) -> str:
        return f"Mock UC ({self._reason})"

    def list_catalogs(self) -> list[str]:
        return sorted(_MOCK_TREE.keys())

    def list_schemas(self, catalog: str) -> list[str]:
        return sorted(_MOCK_TREE.get(catalog, {}).keys())

    def list_tables(self, catalog: str, schema: str) -> list[TableRef]:
        tables = _MOCK_TREE.get(catalog, {}).get(schema, {})
        return [
            TableRef(catalog=catalog, schema=schema, name=name)
            for name in sorted(tables.keys())
        ]

    def list_columns(self, table: TableRef) -> list[ColumnInfo]:
        cols = (
            _MOCK_TREE.get(table.catalog, {})
            .get(table.schema, {})
            .get(table.name, [])
        )
        return list(cols)

    def list_warehouses(self) -> list[tuple[str, str]]:
        return [("mock-wh-1", "Mock SQL Warehouse")]

    def execute_sql(
        self,
        sql: str,
        *,
        warehouse_id: str | None,
        limit: int,
    ) -> QueryResult:
        # Produce a tiny deterministic grid so the results pane is exercisable.
        _ = warehouse_id
        preview = " ".join(sql.split())[:80]
        rows = [
            [i, f"mock_row_{i}", preview]
            for i in range(1, min(limit, 5) + 1)
        ]
        return QueryResult(
            columns=["row_id", "label", "sql_preview"],
            rows=rows,
            truncated=limit < 5,
            message=f"Mock runner (limit={limit})",
        )
