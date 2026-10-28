#!/usr/bin/env bash
# ROMKA local setup (Linux / macOS).
#   ./scripts/setup.sh              # venv + deps + .env + migrate + tests
#   ./scripts/setup.sh --skip-tests # faster
#   ./scripts/setup.sh --test-only  # just run the suite
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SKIP_TESTS=0
TEST_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-tests) SKIP_TESTS=1 ;;
    --test-only) TEST_ONLY=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

if [ ! -x ".venv/bin/python" ]; then
  if [ "$TEST_ONLY" = "1" ]; then
    echo "no .venv yet; run ./scripts/setup.sh first" >&2
    exit 2
  fi
  PY="${PYTHON:-python3}"
  echo "== creating virtualenv with $PY =="
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip --quiet
  .venv/bin/python -m pip install -r requirements-dev.txt --quiet
fi

if [ "$TEST_ONLY" = "1" ]; then
  exec .venv/bin/python -m pytest -q
fi

[ -f .env ] || { cp .env.example .env; echo "created .env from .env.example (dev defaults)"; }
echo "== applying migrations =="
.venv/bin/python -m alembic upgrade head

if [ "$SKIP_TESTS" = "0" ]; then
  echo "== running tests (no network, no API key needed) =="
  .venv/bin/python -m pytest -q
fi

cat <<'EOF'

Setup complete.
  start:  ./scripts/run_dev.sh
  open :  http://127.0.0.1:8000/auth
  demo :  demo@romka.local / RomkaDemo2026!   (development only)

Optional hosted model (GapGPT):
EOF

if [ -f scripts/verify_provider.py ]; then
  cat <<'EOF'
  export GAPGPT_API_KEY="..."; .venv/bin/python scripts/verify_provider.py
EOF
else
  cat <<'EOF'
  set GAPGPT_API_KEY in .env and switch AI_PRIMARY_PROVIDER; this "core" build
  ships without scripts/verify_provider.py.
EOF
fi
