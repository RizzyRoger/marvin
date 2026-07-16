#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Marvin Setup ==="

# Prefer Python 3.11+ via Homebrew if system Python is too old
PYTHON=""
for candidate in python3.12 python3.11 python3; do
  if command -v "$candidate" &>/dev/null; then
    ver=$("$candidate" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=${ver%%.*}
    minor=${ver#*.}
    if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
      PYTHON="$candidate"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Python 3.10+ required. Install with: brew install python@3.11"
  exit 1
fi

echo "Using $PYTHON ($($PYTHON --version))"

# espeak-ng required for Kokoro TTS
if ! command -v espeak-ng &>/dev/null; then
  echo "Installing espeak-ng (required for Kokoro TTS)…"
  brew install espeak-ng
fi

# Create venv
if [ ! -d ".venv" ]; then
  "$PYTHON" -m venv .venv
fi
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

# llama-cpp-python with Metal support on Apple Silicon
if [ "$(uname -m)" = "arm64" ]; then
  echo "Installing llama-cpp-python with Metal (Apple Silicon)…"
  CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python --force-reinstall --no-cache-dir
fi

echo ""
echo "Downloading models (this may take a while)…"
python scripts/download_models.py

echo ""
echo "Building Marvin.app…"
chmod +x scripts/build_app.sh
./scripts/build_app.sh

echo ""
echo "=== Setup complete ==="
echo "Launch Marvin:"
echo "  ./scripts/run.sh"
echo "  open Marvin.app"
echo ""
echo "Or run the server only (browser): python -m backend.main"
