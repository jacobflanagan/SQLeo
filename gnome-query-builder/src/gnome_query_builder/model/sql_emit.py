# SPDX-License-Identifier: Apache-2.0
"""Emit Spark SQL with explicit JOINs and three-level UC names."""

from __future__ import annotations

from gnome_query_builder.model.join_graph import JoinEdge, JoinGraph


def _qcol(alias: str, column: str) -> str:
    return f"`{alias}`.`{column}`"


def emit_spark_sql(graph: JoinGraph, *, limit: int | None = None) -> str:
    """Build a SELECT from the join graph.

    SQL is the product source of truth for complex edits; this emitter covers
    the spike path: one or more tables with explicit JOIN ... ON.
    """
    if not graph.tables:
        return "-- Add tables from the Unity Catalog browser\n"

    select_parts: list[str] = []
    for t in graph.tables:
        if t.columns:
            for c in t.columns:
                select_parts.append(f"  {_qcol(t.alias, c)}")
        else:
            select_parts.append(f"  `{t.alias}`.*")

    lines = ["SELECT"]
    lines.append(",\n".join(select_parts))

    first = graph.tables[0]
    lines.append(f"FROM {first.ref.spark_ident()} AS `{first.alias}`")

    # Map edges by right alias for chain order (table insertion order).
    edges_by_right: dict[str, JoinEdge] = {e.right_alias: e for e in graph.edges}

    for t in graph.tables[1:]:
        edge = edges_by_right.get(t.alias)
        join_type = (edge.join_type if edge else "INNER").upper()
        lines.append(f"{join_type} JOIN {t.ref.spark_ident()} AS `{t.alias}`")
        if edge:
            lines.append(
                "  ON "
                f"{_qcol(edge.left_alias, edge.left_column)}"
                " = "
                f"{_qcol(edge.right_alias, edge.right_column)}"
            )
        else:
            lines.append("  ON 1 = 1  -- TODO: set join keys")

    if limit is not None:
        lines.append(f"LIMIT {int(limit)}")

    return "\n".join(lines) + "\n"
