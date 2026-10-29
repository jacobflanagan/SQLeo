# SPDX-License-Identifier: Apache-2.0
"""Choose SDK backend when credentials exist; otherwise mock UC metadata."""

from __future__ import annotations

import os
from pathlib import Path

from gnome_query_builder.databricks.base import DatabricksBackend
from gnome_query_builder.databricks.mock import MockBackend


def _has_config_hints(profile: str | None) -> bool:
    if os.environ.get("DATABRICKS_HOST") and (
        os.environ.get("DATABRICKS_TOKEN")
        or os.environ.get("DATABRICKS_CLIENT_ID")
        or os.environ.get("DATABRICKS_CONFIG_PROFILE")
    ):
        return True
    cfg = Path.home() / ".databrickscfg"
    if not cfg.is_file():
        return False
    text = cfg.read_text(encoding="utf-8", errors="ignore")
    if profile:
        return f"[{profile}]" in text or (profile == "DEFAULT" and "[DEFAULT]" in text)
    return "[DEFAULT]" in text or "host" in text.lower()


def create_backend(
    *,
    force_mock: bool = False,
    profile: str | None = None,
) -> DatabricksBackend:
    if force_mock:
        return MockBackend(reason="--mock")

    if not _has_config_hints(profile):
        return MockBackend(reason="no ~/.databrickscfg or DATABRICKS_* env")

    from gnome_query_builder.databricks.sdk_client import try_connect

    sdk = try_connect(profile=profile)
    if sdk is not None:
        return sdk
    return MockBackend(reason="SDK auth/connect failed; using mock")
