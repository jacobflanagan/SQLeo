# SPDX-License-Identifier: Apache-2.0
"""Entry point for the GNOME Query Builder spike."""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gnome-query-builder",
        description="GTK4 + libadwaita Databricks Unity Catalog query builder (MVP spike)",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Force mock Databricks backend (offline demo)",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("DATABRICKS_CONFIG_PROFILE"),
        help="Databricks CLI profile name (default: env DATABRICKS_CONFIG_PROFILE or DEFAULT)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Default LIMIT guardrail for warehouse runs (default: 100)",
    )
    args = parser.parse_args(argv)

    # Late import so --help works without a display.
    from gnome_query_builder.application import QueryBuilderApplication
    from gnome_query_builder.databricks.factory import create_backend

    backend = create_backend(force_mock=args.mock, profile=args.profile)
    app = QueryBuilderApplication(backend=backend, default_limit=args.limit)
    return app.run(sys.argv[:1])
