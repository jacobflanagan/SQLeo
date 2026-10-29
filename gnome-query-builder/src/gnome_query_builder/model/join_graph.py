# SPDX-License-Identifier: Apache-2.0
"""Minimal join graph: ordered tables + pairwise join keys (not a full canvas)."""

from __future__ import annotations

from dataclasses import dataclass, field

from gnome_query_builder.databricks.base import TableRef


@dataclass
class GraphTable:
    ref: TableRef
    alias: str
    columns: list[str] = field(default_factory=list)


@dataclass
class JoinEdge:
    left_alias: str
    left_column: str
    right_alias: str
    right_column: str
    join_type: str = "INNER"  # INNER | LEFT | RIGHT | FULL


@dataclass
class JoinGraph:
    tables: list[GraphTable] = field(default_factory=list)
    edges: list[JoinEdge] = field(default_factory=list)

    def aliases(self) -> set[str]:
        return {t.alias for t in self.tables}

    def next_alias(self, table_name: str) -> str:
        base = "".join(ch for ch in table_name if ch.isalnum() or ch == "_") or "t"
        base = base[:12].lower()
        if base not in self.aliases():
            return base
        i = 2
        while f"{base}{i}" in self.aliases():
            i += 1
        return f"{base}{i}"

    def add_table(self, ref: TableRef, columns: list[str] | None = None) -> GraphTable:
        gt = GraphTable(ref=ref, alias=self.next_alias(ref.name), columns=list(columns or []))
        self.tables.append(gt)
        return gt

    def remove_alias(self, alias: str) -> None:
        self.tables = [t for t in self.tables if t.alias != alias]
        self.edges = [
            e
            for e in self.edges
            if e.left_alias != alias and e.right_alias != alias
        ]

    def suggest_join(self, left: GraphTable, right: GraphTable) -> JoinEdge | None:
        """Prefer columns with the same name on both sides (e.g. customer_id)."""
        left_set = set(left.columns)
        for col in right.columns:
            if col in left_set and (col.endswith("_id") or col == "id"):
                return JoinEdge(left.alias, col, right.alias, col)
        shared = left_set.intersection(right.columns)
        if shared:
            col = sorted(shared)[0]
            return JoinEdge(left.alias, col, right.alias, col)
        return None

    def ensure_edge_for_new_table(self, new: GraphTable) -> None:
        if len(self.tables) < 2:
            return
        # Join new table to the previous one when a key can be guessed.
        prev = self.tables[-2]
        edge = self.suggest_join(prev, new)
        if edge is None:
            # Placeholder keys so SQL still emits; user can edit in the join list.
            left_col = prev.columns[0] if prev.columns else "id"
            right_col = new.columns[0] if new.columns else "id"
            edge = JoinEdge(prev.alias, left_col, new.alias, right_col)
        self.edges.append(edge)
