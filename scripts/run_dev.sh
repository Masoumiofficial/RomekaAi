#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
"$PY" -m alembic upgrade head
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --reload
