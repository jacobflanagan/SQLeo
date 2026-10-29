# SPDX-License-Identifier: Apache-2.0
"""Real Databricks SDK backend (CLI profile / OAuth / env credentials)."""

from __future__ import annotations

import logging
from typing import Any

from gnome_query_builder.databricks.base import ColumnInfo, QueryResult, TableRef

log = logging.getLogger(__name__)


class SdkBackend:
    """Uses databricks-sdk WorkspaceClient with the same auth as the CLI.

    Preferred auth: OAuth via ``~/.databrickscfg`` profile (host + auth_type=databricks-cli
    or oauth-m2m / PAT). See Databricks CLI profile docs.
    """

    def __init__(self, client: Any, profile: str | None = None) -> None:
        self._client = client
        self._profile = profile or "DEFAULT"

    @property
    def mode(self) -> str:
        return "sdk"

    @property
    def status_label(self) -> str:
        host = getattr(getattr(self._client, "config", None), "host", None) or "?"
        return f"SDK profile={self._profile} host={host}"

    def list_catalogs(self) -> list[str]:
        return sorted(c.name for c in self._client.catalogs.list() if c.name)

    def list_schemas(self, catalog: str) -> list[str]:
        return sorted(
            s.name for s in self._client.schemas.list(catalog_name=catalog) if s.name
        )

    def list_tables(self, catalog: str, schema: str) -> list[TableRef]:
        out: list[TableRef] = []
        for t in self._client.tables.list(catalog_name=catalog, schema_name=schema):
            if not t.name:
                continue
            out.append(TableRef(catalog=catalog, schema=schema, name=t.name))
        return sorted(out, key=lambda r: r.name)

    def list_columns(self, table: TableRef) -> list[ColumnInfo]:
        info = self._client.tables.get(full_name=table.fqn)
        cols: list[ColumnInfo] = []
        for c in info.columns or []:
            cols.append(
                ColumnInfo(
                    name=c.name or "?",
                    data_type=str(c.type_text or c.type_name or "STRING"),
                    comment=c.comment or "",
                )
            )
        return cols

    def list_warehouses(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for wh in self._client.warehouses.list():
            wid = wh.id or ""
            name = wh.name or wid
            if wid:
                out.append((wid, name))
        return out

    def execute_sql(
        self,
        sql: str,
        *,
        warehouse_id: str | None,
        limit: int,
    ) -> QueryResult:
        if not warehouse_id:
            raise RuntimeError("No SQL warehouse selected")

        guarded = _ensure_limit(sql, limit)
        response = self._client.statement_execution.execute_statement(
            statement=guarded,
            warehouse_id=warehouse_id,
            wait_timeout="50s",
        )

        columns: list[str] = []
        manifest = getattr(response, "manifest", None)
        schema = getattr(manifest, "schema", None) if manifest else None
        for col in getattr(schema, "columns", None) or []:
            columns.append(col.name or f"col_{len(columns)}")

        rows: list[list[object]] = []
        result = getattr(response, "result", None)
        data_array = getattr(result, "data_array", None) if result else None
        for raw in data_array or []:
            rows.append(list(raw))

        status = getattr(response, "status", None)
        state = str(getattr(status, "state", "") or "")
        message = f"warehouse={warehouse_id} state={state} limit={limit}"
        return QueryResult(columns=columns, rows=rows, message=message)


def _ensure_limit(sql: str, limit: int) -> str:
    """Append LIMIT if the statement does not already contain one (naive)."""
    stripped = sql.strip().rstrip(";")
    if " limit " in f" {stripped.lower()} ":
        return stripped
    return f"{stripped}\nLIMIT {int(limit)}"


def try_connect(profile: str | None = None) -> SdkBackend | None:
    """Return an SdkBackend if credentials resolve; else None."""
    try:
        from databricks.sdk import WorkspaceClient
    except ImportError:
        log.info("databricks-sdk not installed")
        return None

    try:
        kwargs: dict[str, Any] = {}
        if profile:
            kwargs["profile"] = profile
        client = WorkspaceClient(**kwargs)
        # Cheap probe: config must have a host; listing catalogs may need network.
        host = getattr(client.config, "host", None)
        if not host:
            return None
        # Touch auth without failing the whole UI if network is down later.
        return SdkBackend(client, profile=profile)
    except Exception as exc:  # noqa: BLE001 — spike: any auth failure → mock
        log.info("Databricks SDK auth failed: %s", exc)
        return None
