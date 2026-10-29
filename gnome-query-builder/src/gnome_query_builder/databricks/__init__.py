# SPDX-License-Identifier: Apache-2.0
"""Databricks access: profile/OAuth SDK client or offline mock."""

from gnome_query_builder.databricks.base import (
    ColumnInfo,
    DatabricksBackend,
    QueryResult,
    TableRef,
)
from gnome_query_builder.databricks.factory import create_backend

__all__ = [
    "ColumnInfo",
    "DatabricksBackend",
    "QueryResult",
    "TableRef",
    "create_backend",
]
