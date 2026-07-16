#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME="Marvin"
APP_DIR="$ROOT/${APP_NAME}.app"
CONTENTS="$APP_DIR/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
BRAND_LOGO="$ROOT/../../media/b28c1df3-7823-4e4b-8f18-8a8a9c6af0da-removebg-preview.png"

echo "=== Building ${APP_NAME}.app ==="

mkdir -p "$MACOS" "$RESOURCES"

# Resolve paths at build time — Finder-launched bash apps cannot read Documents/Obsidian paths.
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
  echo "Run ./scripts/setup.sh first (need Homebrew Python + project venv)." >&2
  exit 1
fi

# Launcher lives inside the .app bundle (Finder blocks scripts in Documents/Obsidian).
cat >"$RESOURCES/launch.sh" <<LAUNCHER
#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$ROOT"
PYTHON="$PYTHON"
SITE_PACKAGES="$SITE_PACKAGES"
LOG_FILE="\$PROJECT_ROOT/data/marvin.log"
mkdir -p "\$PROJECT_ROOT/data"
cd "\$PROJECT_ROOT"
export PYTHONUNBUFFERED=1
export PYTHONPATH="\$PROJECT_ROOT:\$SITE_PACKAGES"
export VIRTUAL_ENV="\$PROJECT_ROOT/.venv"

# Clear zombie server left behind after a crash.
if lsof -ti:8765 >/dev/null 2>&1; then
  if ! curl -sf --max-time 2 http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
    lsof -ti:8765 | xargs kill -9 2>/dev/null || true
    sleep 0.5
  fi
fi

exec "\$PYTHON" -m backend.app >>"\$LOG_FILE" 2>&1
LAUNCHER
chmod +x "$RESOURCES/launch.sh"

LAUNCH_SCRIPT="$RESOURCES/launch.sh"

# AppleScript runs the bundled launcher with user permissions.
cat >"$MACOS/${APP_NAME}" <<APPLESCRIPT
#!/usr/bin/osascript
set launchScript to "$LAUNCH_SCRIPT"
try
  do shell script quoted form of launchScript
on error errMsg number errNum
  display alert "Marvin failed to start (" & errNum & ")" message errMsg
end try
APPLESCRIPT

chmod +x "$MACOS/${APP_NAME}"

cat >"$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>en</string>
  <key>CFBundleExecutable</key>
  <string>${APP_NAME}</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>com.marvin.voice-agent</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>${APP_NAME}</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>Marvin needs microphone access for voice conversations.</string>
  <key>NSDocumentsFolderUsageDescription</key>
  <string>Marvin needs access to its project folder for models and chat history.</string>
  <key>NSSupportsAutomaticGraphicsSwitching</key>
  <true/>
</dict>
</plist>
PLIST

# Build the macOS icon from Marvin's brand artwork.
if [ -f "$BRAND_LOGO" ]; then
  cp "$BRAND_LOGO" "$RESOURCES/brand-logo.png"
  rm -rf "$RESOURCES/AppIcon.iconset"
  "$ROOT/.venv/bin/python" - "$BRAND_LOGO" "$RESOURCES/AppIcon.icns" <<'PY'
import sys
from PIL import Image

source, destination = sys.argv[1:3]
image = Image.open(source).convert("RGBA")
image = image.resize((1024, 1024), Image.Resampling.LANCZOS)
image.save(destination, format="ICNS")
PY
else
  echo "Warning: brand logo not found at $BRAND_LOGO" >&2
fi

echo ""
echo "Built: $APP_DIR"
echo "Double-click ${APP_NAME}.app in Finder, or run: open \"$APP_DIR\""
