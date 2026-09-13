#!/usr/bin/env bash
# Build a friends-testing ZIP: clean release app, no secrets, SHA256, install notes.
# Unsigned (Gatekeeper: Right-click → Open). Do not publish publicly.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(tr -d '[:space:]' <"$ROOT/VERSION")"
ARCH="$(uname -m)"
OUT_DIR="$ROOT/dist"
STAGE="$OUT_DIR/friends-stage"
ZIP_NAME="Marvin-${VERSION}-${ARCH}-friends.zip"
SUMS_NAME="SHA256SUMS-${VERSION}-${ARCH}-friends.txt"

cd "$ROOT"

# Fail the script if release_build fails (don't hide behind pipes).
export PYTHONUNBUFFERED=1

if [ "$ARCH" != "arm64" ]; then
  echo "Friends ZIP is arm64-only for now (host=$ARCH)." >&2
  exit 1
fi

echo "=== Friends testing ZIP (${VERSION}, ${ARCH}) ==="

# Prefer a fresh release build so recipients need no Homebrew.
if [ "${MARVIN_SKIP_RELEASE_BUILD:-}" != "1" ]; then
  "$ROOT/scripts/release_build.sh"
else
  echo "MARVIN_SKIP_RELEASE_BUILD=1 — using existing Marvin.app"
fi

APP="$ROOT/Marvin.app"
if [ ! -d "$APP" ]; then
  echo "Marvin.app missing after build." >&2
  exit 1
fi

echo "Scanning for secrets…"
leaks="$(find "$APP" \( \
    -name '.env' -o \
    -name '.env.*' -o \
    -name 'chat_history.json' -o \
    -name 'voice_profile.npz' -o \
    -name 'voice_profile.npz.enc' -o \
    -name 'voice_profile.key' -o \
    -name 'reminders.json' \
  \) 2>/dev/null || true)"
if [ -n "$leaks" ]; then
  echo "REFUSING: personal/secret files found inside Marvin.app" >&2
  echo "$leaks" >&2
  exit 1
fi
# Best-effort scan of *our* runtime sources only (not site-packages).
if grep -RIlE 'sk-[A-Za-z0-9]{20,}|xai-[A-Za-z0-9]{20,}|sk-ant-[A-Za-z0-9]{20,}' \
    "$APP/Contents/Resources/runtime/backend" \
    "$APP/Contents/Resources/runtime/frontend" \
    2>/dev/null | head -5 | grep -q .; then
  echo "REFUSING: possible API key material in runtime tree" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -R "$APP" "$STAGE/Marvin.app"

# Install notes (also keep a copy in dist/)
NOTES_SRC="$OUT_DIR/FRIENDS_TESTING.md"
if [ ! -f "$NOTES_SRC" ]; then
  NOTES_SRC="$ROOT/SECURITY.md"
fi
cp "$NOTES_SRC" "$STAGE/README-FRIENDS.txt"

rm -f "$OUT_DIR/$ZIP_NAME"
ditto -c -k --keepParent "$STAGE/Marvin.app" "$OUT_DIR/$ZIP_NAME"
# Also put the readme beside the zip for the sender to forward
cp "$NOTES_SRC" "$OUT_DIR/README-FRIENDS.txt"

(
  cd "$OUT_DIR"
  shasum -a 256 "$ZIP_NAME" >"$SUMS_NAME"
)

# Size sanity: empty/stub zips are a failure
SIZE="$(stat -f%z "$OUT_DIR/$ZIP_NAME" 2>/dev/null || stat -c%s "$OUT_DIR/$ZIP_NAME")"
if [ "$SIZE" -lt 100000000 ]; then
  echo "REFUSING: ZIP is suspiciously small (${SIZE} bytes)" >&2
  exit 1
fi

rm -rf "$STAGE"

echo ""
echo "Created: $OUT_DIR/$ZIP_NAME"
echo "Sums:    $OUT_DIR/$SUMS_NAME"
echo "Notes:   $OUT_DIR/README-FRIENDS.txt"
echo ""
echo "Send ZIP + SHA256SUMS + README-FRIENDS to friends."
echo "Unsigned: they must Right-click → Open the first time."
echo "Do NOT include your .env or Application Support folder."
