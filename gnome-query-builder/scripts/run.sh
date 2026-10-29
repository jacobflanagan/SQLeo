#!/usr/bin/env bash
# Dev launcher — no Meson install required.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m gnome_query_builder "$@"
