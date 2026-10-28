#!/usr/bin/env bash
# Start the ROMKA dev server, refusing to run on a port owned by something else.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
PORT="${PORT:-8000}"
SKIP_CHECKS="${SKIP_CHECKS:-0}"

echo "== ROMKA =="
echo "http://127.0.0.1:${PORT}/auth  (demo: demo@romka.local / RomkaDemo2026!)"

if [ "$SKIP_CHECKS" != "1" ]; then
  set +e
  "$PY" scripts/doctor.py --only port --port "$PORT"
  code=$?
  set -e
  if [ "$code" = "15" ]; then
    echo "ROMKA is already running on port ${PORT} — open http://127.0.0.1:${PORT}/auth"
    exit 0
  fi
  if [ "$code" != "0" ]; then
    echo "Port ${PORT} is not usable (exit ${code}). Nothing was started." >&2
    echo "Try:  PORT=8010 ./scripts/run_dev.sh" >&2
    echo "Full diagnosis: ${PY} scripts/doctor.py" >&2
    exit 1
  fi
fi

"$PY" -m alembic upgrade head
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
