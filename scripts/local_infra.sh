#!/usr/bin/env bash
# Wrapper: creates ./.infra-venv with pgserver + redislite on first use, then runs local_infra.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$ROOT/.infra-venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q pgserver redislite redis
fi
exec "$VENV/bin/python" "$ROOT/scripts/local_infra.py" "$@"