#!/usr/bin/env bash
# Clean release build: embedded standalone Python, locked deps, secret leak checks.
# Output: Marvin.app in the project root (unsigned). Sign via scripts/sign_and_notarize.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Marvin"
# Build under /tmp — project paths with spaces break python -m venv / ensurepip.
BUILD_ROOT="${TMPDIR:-/tmp}/marvin-release-build-$$"
APP_DIR="$BUILD_ROOT/${APP_NAME}.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
FRAMEWORKS="$CONTENTS/Frameworks"
RUNTIME="$RESOURCES/runtime"
VENV="$RESOURCES/venv"
CACHE="$ROOT/dist/cache"
VERSION="$(tr -d '[:space:]' <"$ROOT/VERSION")"
ARCH="$(uname -m)"
if [ "$ARCH" != "arm64" ]; then
  echo "This release build targets Apple Silicon (arm64). Host is $ARCH." >&2
  exit 1
fi

cleanup_build() {
  rm -rf "$BUILD_ROOT"
}
trap cleanup_build EXIT

# python-build-standalone (install_only) — recipients need no Homebrew.
PY_VER="3.11.9"
PY_TAG="20240726"
PY_URL="https://github.com/indygreg/python-build-standalone/releases/download/${PY_TAG}/cpython-${PY_VER}+${PY_TAG}-aarch64-apple-darwin-install_only.tar.gz"
PY_TGZ="$CACHE/cpython-${PY_VER}+${PY_TAG}-aarch64-install_only.tar.gz"

echo "=== Release build ${APP_NAME} ${VERSION} (arm64) ==="
echo "Staging in $BUILD_ROOT (avoids spaces in project path)"
rm -rf "$BUILD_ROOT"
mkdir -p "$CACHE" "$MACOS" "$RESOURCES" "$FRAMEWORKS" "$RUNTIME"

fail_secrets() {
  echo "SECRET LEAK: $1" >&2
  exit 1
}

echo "Fetching standalone Python (cached if present)…"
if [ ! -f "$PY_TGZ" ]; then
  curl -fL --retry 3 -o "$PY_TGZ" "$PY_URL"
fi
mkdir -p "$CACHE/python-extract"
rm -rf "$CACHE/python-extract"/*
tar -xzf "$PY_TGZ" -C "$CACHE/python-extract"
# install_only layout: python/bin/python3
if [ -d "$CACHE/python-extract/python" ]; then
  rsync -a "$CACHE/python-extract/python/" "$FRAMEWORKS/python/"
else
  echo "Unexpected python-build-standalone layout" >&2
  ls -la "$CACHE/python-extract" >&2
  exit 1
fi
PYTHON="$FRAMEWORKS/python/bin/python3"
if [ ! -x "$PYTHON" ]; then
  echo "Embedded python missing at $PYTHON" >&2
  exit 1
fi

echo "Copying runtime code…"
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.py[cod]' \
  --exclude '.DS_Store' \
  "$ROOT/backend/" "$RUNTIME/backend/"
rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '.DS_Store' \
  "$ROOT/frontend/" "$RUNTIME/frontend/"
mkdir -p "$RUNTIME/resources" "$RUNTIME/scripts/sandbox"
if [ -d "$ROOT/resources" ]; then
  rsync -a --delete --exclude '.DS_Store' "$ROOT/resources/" "$RUNTIME/resources/"
fi
if [ -f "$ROOT/scripts/sandbox/python_runner.sb" ]; then
  cp "$ROOT/scripts/sandbox/python_runner.sb" "$RUNTIME/scripts/sandbox/"
fi
cp "$ROOT/requirements.txt" "$RUNTIME/requirements.txt"
cp "$ROOT/VERSION" "$RUNTIME/VERSION"
if [ -f "$ROOT/requirements.lock" ]; then
  cp "$ROOT/requirements.lock" "$RUNTIME/requirements.lock"
fi

# Ensure brand logo is inside the bundle (never depend on a personal vault path).
if [ -f "$ROOT/resources/brand-logo.png" ]; then
  cp "$ROOT/resources/brand-logo.png" "$RUNTIME/resources/brand-logo.png"
else
  echo "WARNING: resources/brand-logo.png missing" >&2
fi

echo "Installing dependencies into embedded Python (relocatable, no venv)…"
# Ensure pip exists on the standalone interpreter.
if ! "$PYTHON" -m pip --version >/dev/null 2>&1; then
  curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$BUILD_ROOT/get-pip.py"
  "$PYTHON" "$BUILD_ROOT/get-pip.py"
fi
"$PYTHON" -m pip install --upgrade pip
if [ -f "$ROOT/requirements.lock" ] && grep -q 'sha256:' "$ROOT/requirements.lock"; then
  echo "Installing from hashed requirements.lock…"
  "$PYTHON" -m pip install --require-hashes -r "$ROOT/requirements.lock"
elif [ -f "$ROOT/requirements.lock" ]; then
  echo "Installing from requirements.lock (no hashes)…"
  "$PYTHON" -m pip install -r "$ROOT/requirements.lock"
else
  echo "No requirements.lock — installing requirements.txt (run ./scripts/lock_requirements.sh)" >&2
  "$PYTHON" -m pip install -r "$ROOT/requirements.txt"
fi
# Keep an empty venv dir marker unused; launcher uses Frameworks/python.
rm -rf "$VENV"
mkdir -p "$VENV"

echo "Scanning stage for secrets / personal data…"
STAGE_SCAN_PATHS=("$RUNTIME" "$FRAMEWORKS/python")
for stage in "${STAGE_SCAN_PATHS[@]}"; do
  # Only Marvin personal artifacts — not CA bundles (*.pem in certifi) or package metadata.
  leaks="$(find "$stage" \( \
      -name '.env' -o \
      -name '.env.*' -o \
      -name 'chat_history.json' -o \
      -name 'voice_profile.npz' -o \
      -name 'voice_profile.npz.enc' -o \
      -name 'voice_profile.key' -o \
      -name 'reminders.json' \
    \) 2>/dev/null || true)"
  if [ -n "$leaks" ]; then
    echo "$leaks" >&2
    fail_secrets "forbidden personal files under $stage"
  fi
done
# Models must not be inside the .app
if [ -d "$APP_DIR/Contents/Resources/models" ] || [ -d "$RUNTIME/models" ]; then
  fail_secrets "models directory must not be bundled inside the .app"
fi

# Remove old Documents pointer if present
rm -f "$RESOURCES/marvin-home"

cat >"$RESOURCES/launch.sh" <<'LAUNCHER'
#!/usr/bin/env bash
set -euo pipefail

BUNDLE_RESOURCES="$(cd "$(dirname "$0")" && pwd)"
RUNTIME="$BUNDLE_RESOURCES/runtime"
EMBEDDED_PY="$BUNDLE_RESOURCES/../Frameworks/python/bin/python3"
SUPPORT="${HOME}/Library/Application Support/Marvin"
DATA_DIR="$SUPPORT/data"
MODELS_DIR="$SUPPORT/models"

mkdir -p "$DATA_DIR" "$MODELS_DIR" 2>/dev/null || true

if [ ! -d "$RUNTIME/backend" ]; then
  osascript -e 'display alert "Marvin" message "This Marvin.app is incomplete (missing runtime). Reinstall from a signed release DMG."' || true
  exit 1
fi

export MARVIN_BUNDLE=1
export MARVIN_ROOT="$RUNTIME"
export MARVIN_DATA_DIR="$DATA_DIR"
export MARVIN_MODELS_DIR="$MODELS_DIR"

if [ ! -x "$EMBEDDED_PY" ]; then
  osascript -e 'display alert "Marvin" message "Bundled Python is missing. Reinstall Marvin from the official DMG."' || true
  exit 1
fi
PYTHON="$EMBEDDED_PY"

SITE_PACKAGES=""
for dir in "$BUNDLE_RESOURCES/../Frameworks/python"/lib/python*/site-packages; do
  if [ -d "$dir" ]; then
    SITE_PACKAGES="$dir"
    break
  fi
done

if [ -z "$SITE_PACKAGES" ]; then
  osascript -e 'display alert "Marvin" message "Bundled Python packages are missing. Reinstall Marvin."' || true
  exit 1
fi

export PYTHONPATH="$RUNTIME${SITE_PACKAGES:+:$SITE_PACKAGES}"

if [ ! -d "$MODELS_DIR/whisper-large-v3-turbo" ] || [ ! -f "$MODELS_DIR/piper/en/en_GB/alan/medium/en_GB-alan-medium.onnx" ]; then
  osascript -e 'display alert "Marvin" message "Speech models are not installed yet. Marvin will download and verify them now (several GB). Keep this Mac online."' || true
  DOWNLOAD_SCRIPT="$RUNTIME/scripts/download_models.py"
  if [ ! -f "$DOWNLOAD_SCRIPT" ]; then
    osascript -e 'display alert "Marvin" message "Model bootstrap script missing from this build."' || true
    exit 1
  fi
  cd "$RUNTIME"
  if ! "$PYTHON" "$DOWNLOAD_SCRIPT"; then
    osascript -e 'display alert "Marvin" message "Model download or verification failed. Check Console logs and retry."' || true
    exit 1
  fi
fi

LOG_DIR="${HOME}/Library/Logs/Marvin"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG_FILE="$LOG_DIR/marvin.log"
if ! touch "$LOG_FILE" 2>/dev/null; then
  LOG_FILE="/tmp/marvin.log"
fi

cd "$RUNTIME"
export PYTHONUNBUFFERED=1
export MARVIN_LOG_FILE="$LOG_FILE"
if [ -f "$BUNDLE_RESOURCES/AppIcon.icns" ]; then
  export MARVIN_APP_ICON="$BUNDLE_RESOURCES/AppIcon.icns"
fi

PID_FILE="$DATA_DIR/marvin.pid"
if lsof -ti:8765 >/dev/null 2>&1; then
  if ! curl -sf --max-time 2 http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
    if [ -f "$PID_FILE" ]; then
      OLD_PID="$(tr -d '[:space:]' <"$PID_FILE" || true)"
      if [ -n "${OLD_PID:-}" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 0.4
        kill -9 "$OLD_PID" 2>/dev/null || true
      fi
    fi
  fi
fi

exec "$PYTHON" -m backend.app >>"$LOG_FILE" 2>&1
LAUNCHER
chmod +x "$RESOURCES/launch.sh"

mkdir -p "$RUNTIME/scripts"
cp "$ROOT/scripts/download_models.py" "$RUNTIME/scripts/download_models.py"

cat >"$MACOS/${APP_NAME}" <<'ENTRY'
#!/usr/bin/env bash
set -euo pipefail
MACOS_DIR="$(cd "$(dirname "$0")" && pwd)"
LAUNCH_SCRIPT="$MACOS_DIR/../Resources/launch.sh"
if [ ! -x "$LAUNCH_SCRIPT" ]; then
  osascript -e 'display alert "Marvin" message "Missing Contents/Resources/launch.sh. Reinstall from the release DMG."' || true
  exit 1
fi
exec "$LAUNCH_SCRIPT"
ENTRY
chmod +x "$MACOS/${APP_NAME}"

cat >"$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>${APP_NAME}</string>
  <key>CFBundleDisplayName</key><string>${APP_NAME}</string>
  <key>CFBundleIdentifier</key><string>local.marvin.voice</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleExecutable</key><string>${APP_NAME}</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Marvin needs the microphone for voice conversations and Voice Lock.</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
</dict>
</plist>
PLIST

BRAND_LOGO="$ROOT/resources/brand-logo.png"
if [ -f "$BRAND_LOGO" ] && command -v sips >/dev/null 2>&1; then
  ICONSET="$RESOURCES/AppIcon.iconset"
  mkdir -p "$ICONSET"
  sips -z 512 512 "$BRAND_LOGO" --out "$ICONSET/icon_512x512.png" >/dev/null
  sips -z 256 256 "$BRAND_LOGO" --out "$ICONSET/icon_256x256.png" >/dev/null
  sips -z 128 128 "$BRAND_LOGO" --out "$ICONSET/icon_128x128.png" >/dev/null
  if command -v iconutil >/dev/null 2>&1; then
    iconutil -c icns "$ICONSET" -o "$RESOURCES/AppIcon.icns" 2>/dev/null || true
  fi
  rm -rf "$ICONSET"
fi

# Final secret scan of the whole .app
if find "$APP_DIR" \( -name '.env' -o -name 'chat_history.json' -o -path '*/Application Support/*' \) 2>/dev/null | grep -q .; then
  fail_secrets "forbidden paths inside Marvin.app"
fi

# Install into the project tree (may contain spaces — copy only, no venv create here).
FINAL_APP="$ROOT/${APP_NAME}.app"
echo "Installing built app → $FINAL_APP"
rm -rf "$FINAL_APP"
mkdir -p "$ROOT"
cp -R "$APP_DIR" "$FINAL_APP"

echo "Built $FINAL_APP (unsigned)"
echo "Version: $VERSION"
echo "Next:    ./scripts/sign_and_notarize.sh && ./scripts/create_dmg.sh"
echo "Friends: ./scripts/package_friends_zip.sh"
