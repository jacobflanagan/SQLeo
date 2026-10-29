# SPDX-License-Identifier: Apache-2.0
"""Backend interface for Unity Catalog browse + SQL warehouse execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass(frozen=True)
class TableRef:
    catalog: str
    schema: str
    name: str

    @property
    def fqn(self) -> str:
        return f"{self.catalog}.{self.schema}.{self.name}"

    def spark_ident(self) -> str:
        """Three-level Spark SQL identifier with backticks."""
        return f"`{self.catalog}`.`{self.schema}`.`{self.name}`"


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str = "STRING"
    comment: str = ""


@dataclass
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[list[object]] = field(default_factory=list)
    truncated: bool = False
    message: str = ""


class DatabricksBackend(Protocol):
    """Clear seam: real SDK/CLI or mock for offline UI."""

    @property
    def mode(self) -> str:
        """Human-readable mode: 'sdk', 'mock', etc."""
        ...

    @property
    def status_label(self) -> str:
        """Short status for the header/subtitle."""
        ...

    def list_catalogs(self) -> Sequence[str]:
        ...

    def list_schemas(self, catalog: str) -> Sequence[str]:
        ...

    def list_tables(self, catalog: str, schema: str) -> Sequence[TableRef]:
        ...

    def list_columns(self, table: TableRef) -> Sequence[ColumnInfo]:
        ...

    def list_warehouses(self) -> Sequence[tuple[str, str]]:
        """Return (warehouse_id, display_name) pairs."""
        ...

    def execute_sql(
        self,
        sql: str,
        *,
        warehouse_id: str | None,
        limit: int,
    ) -> QueryResult:
        ...
