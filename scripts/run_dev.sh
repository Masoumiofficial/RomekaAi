#!/usr/bin/env bash
# Start the ROMKA dev server, refusing to run on a port owned by something else.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
[ -x "$PY" ] || PY=python3
PORT="${PORT:-8000}"
SKIP_CHECKS="${SKIP_CHECKS:-0}"
FREE_PORT="${FREE_PORT:-0}"     # FREE_PORT=1 ./scripts/run_dev.sh  -> stop the owner
ASSUME_YES="${YES:-0}"          # YES=1 skips the confirmation prompt

echo "== ROMKA =="
echo "http://127.0.0.1:${PORT}/auth  (demo: demo@romka.local / RomkaDemo2026!)"

HAVE_DOCTOR=0
[ -f scripts/doctor.py ] && HAVE_DOCTOR=1

if [ "$SKIP_CHECKS" != "1" ] && [ "$HAVE_DOCTOR" = "0" ]; then
  echo "core build: port pre-flight is not included; starting directly."
  echo "if the port is busy, close the other program or choose another: PORT=8010 ./scripts/run_dev.sh"
fi

if [ "$SKIP_CHECKS" != "1" ] && [ "$HAVE_DOCTOR" = "1" ]; then
  set +e
  "$PY" scripts/doctor.py --only port --port "$PORT"
  code=$?
  set -e
  if [ "$code" = "15" ]; then
    echo "ROMKA is already running on port ${PORT} — open http://127.0.0.1:${PORT}/auth"
    exit 0
  fi
  if [ "$code" = "13" ] && [ "$FREE_PORT" = "1" ]; then
    set +e
    "$PY" scripts/doctor.py --only port --port "$PORT" --stop-owner \
      $([ "$ASSUME_YES" = "1" ] && echo --yes)
    stopped=$?
    set -e
    if [ "$stopped" != "0" ]; then
      echo "Port ${PORT} could not be freed. Nothing was started." >&2
      exit 1
    fi
    set +e
    "$PY" scripts/doctor.py --only port --port "$PORT" --quiet
    code=$?
    set -e
  fi
  if [ "$code" != "0" ]; then
    echo "Port ${PORT} is not usable (exit ${code}). Nothing was started." >&2
    echo "Free it for me :  FREE_PORT=1 ./scripts/run_dev.sh" >&2
    echo "Other port     :  PORT=8010 ./scripts/run_dev.sh" >&2
    echo "Full diagnosis :  ${PY} scripts/doctor.py" >&2
    exit 1
  fi
fi

"$PY" -m alembic upgrade head
exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
