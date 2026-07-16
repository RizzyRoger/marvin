#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON=""
for candidate in \
  /opt/homebrew/bin/python3.12 \
  /opt/homebrew/bin/python3.11 \
  /usr/local/bin/python3.12 \
  /usr/local/bin/python3.11 \
  /usr/bin/python3
do
  if [ -x "$candidate" ]; then
    PYTHON="$candidate"
    break
  fi
done

SITE_PACKAGES=""
for dir in "$ROOT/.venv"/lib/python*/site-packages; do
  if [ -d "$dir" ]; then
    SITE_PACKAGES="$dir"
    break
  fi
done

if [ -z "$PYTHON" ] || [ -z "$SITE_PACKAGES" ]; then
  echo "Run ./scripts/setup.sh first." >&2
  exit 1
fi

# Clear zombie server left behind after a crash.
if lsof -ti:8765 >/dev/null 2>&1; then
  if ! curl -sf --max-time 2 http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
    lsof -ti:8765 | xargs kill -9 2>/dev/null || true
    sleep 0.5
  fi
fi

export PYTHONUNBUFFERED=1
export PYTHONPATH="$ROOT:$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
export VIRTUAL_ENV="$ROOT/.venv"
exec "$PYTHON" -m backend.app
