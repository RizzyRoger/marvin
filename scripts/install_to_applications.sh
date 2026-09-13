#!/usr/bin/env bash
# Build Marvin.app, install to /Applications, and bootstrap models into
# ~/Library/Application Support/Marvin.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_SRC="$ROOT/Marvin.app"
APP_DST="/Applications/Marvin.app"
SUPPORT="${HOME}/Library/Application Support/Marvin"
MODELS_DIR="$SUPPORT/models"
DATA_DIR="$SUPPORT/data"

cd "$ROOT"

echo "=== Install Marvin to /Applications ==="
"$ROOT/scripts/build_app.sh"

if [ ! -d "$APP_SRC" ]; then
  echo "Build failed: $APP_SRC missing." >&2
  exit 1
fi

mkdir -p "$DATA_DIR" "$MODELS_DIR"

# Prefer copying existing project models (fast); otherwise download.
if [ -d "$ROOT/models/whisper-large-v3-turbo" ] && [ ! -d "$MODELS_DIR/whisper-large-v3-turbo" ]; then
  echo "Copying models from project → Application Support…"
  rsync -a "$ROOT/models/" "$MODELS_DIR/"
elif [ ! -d "$MODELS_DIR/whisper-large-v3-turbo" ]; then
  echo "Downloading models into Application Support…"
  export MARVIN_BUNDLE=1
  export MARVIN_ROOT="$ROOT"
  export MARVIN_DATA_DIR="$DATA_DIR"
  export MARVIN_MODELS_DIR="$MODELS_DIR"
  if [ -x "$ROOT/.venv/bin/python" ]; then
    "$ROOT/.venv/bin/python" "$ROOT/scripts/download_models.py"
  else
    python3 "$ROOT/scripts/download_models.py"
  fi
else
  echo "Models already present in Application Support."
fi

if [ -d "$ROOT/models/llm-mlx" ] && [ ! -d "$MODELS_DIR/llm-mlx" ]; then
  echo "Copying MLX Qwen weights → Application Support…"
  mkdir -p "$MODELS_DIR/llm-mlx"
  rsync -a "$ROOT/models/llm-mlx/" "$MODELS_DIR/llm-mlx/"
fi

# Seed vault path preference when Documents Obsidian Vault exists.
DEFAULT_VAULT="${HOME}/Documents/Obsidian Vault"
PREFS="$DATA_DIR/user_prefs.json"
if [ -d "$DEFAULT_VAULT" ] && [ ! -f "$PREFS" ]; then
  python3 - "$PREFS" "$DEFAULT_VAULT" <<'PY'
import json
import sys
from pathlib import Path

prefs = Path(sys.argv[1])
vault = sys.argv[2]
prefs.parent.mkdir(parents=True, exist_ok=True)
data = {}
if prefs.is_file():
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
    except Exception:
        data = {}
if not isinstance(data, dict):
    data = {}
data.setdefault("vault_root", vault)
prefs.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(f"Seeded vault_root → {data['vault_root']}")
PY
fi

# Copy optional project .env secrets into Application Support (do not overwrite).
if [ -f "$ROOT/.env" ] && [ ! -f "$SUPPORT/.env" ]; then
  cp "$ROOT/.env" "$SUPPORT/.env"
  echo "Copied .env → $SUPPORT/.env"
fi

echo "Installing app → $APP_DST"
rm -rf "$APP_DST"
cp -R "$APP_SRC" "$APP_DST"

# Clear quarantine so double-click works for *local developer* installs only.
# Never publish xattr -cr instructions for downloaded DMGs — use notarization instead.
if command -v xattr >/dev/null 2>&1; then
  xattr -cr "$APP_DST" 2>/dev/null || true
fi

echo ""
echo "Installed: $APP_DST"
echo "Data:      $DATA_DIR"
echo "Models:    $MODELS_DIR"
echo "Open with: open -a Marvin"
echo "Or:        open /Applications/Marvin.app"
