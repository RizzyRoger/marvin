#!/usr/bin/env bash
# Codesign (Developer ID) + notarize + staple Marvin.app.
# Requires: Apple Developer ID Application cert, notarytool credentials.
#
# Env:
#   MARVIN_SIGN_IDENTITY  e.g. "Developer ID Application: Your Name (TEAMID)"
#   MARVIN_NOTARY_PROFILE keychain profile from: xcrun notarytool store-credentials
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/Marvin.app"
ENTITLEMENTS="$ROOT/scripts/entitlements.plist"
IDENTITY="${MARVIN_SIGN_IDENTITY:-}"
PROFILE="${MARVIN_NOTARY_PROFILE:-MarvinNotary}"

if [ ! -d "$APP" ]; then
  echo "Marvin.app missing — run ./scripts/release_build.sh first." >&2
  exit 1
fi

if [ -z "$IDENTITY" ]; then
  # Try to pick a Developer ID Application identity automatically.
  IDENTITY="$(security find-identity -v -p codesigning 2>/dev/null | awk -F'"' '/Developer ID Application/ {print $2; exit}')"
fi

if [ -z "$IDENTITY" ]; then
  cat >&2 <<'EOF'
No Developer ID Application identity found.
Set MARVIN_SIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"
and configure notarytool:
  xcrun notarytool store-credentials MarvinNotary --apple-id ... --team-id ... --password ...
EOF
  exit 1
fi

echo "Signing with: $IDENTITY"
# Sign nested binaries deepest-first.
find "$APP" \( -name '*.so' -o -name '*.dylib' -o -name 'Python' -o -perm +111 -type f \) 2>/dev/null \
  | while read -r bin; do
      # Skip plain scripts without Mach-O
      if file "$bin" | grep -q 'Mach-O'; then
        codesign --force --options runtime --timestamp --entitlements "$ENTITLEMENTS" --sign "$IDENTITY" "$bin" 2>/dev/null || true
      fi
    done

codesign --force --deep --options runtime --timestamp \
  --entitlements "$ENTITLEMENTS" \
  --sign "$IDENTITY" \
  "$APP"

codesign --verify --deep --strict --verbose=2 "$APP"
spctl --assess --type execute --verbose=4 "$APP" 2>&1 || true

echo "Submitting to Apple notary service (profile=$PROFILE)…"
# Zip for upload (notarytool accepts .app via zip or dmg)
ZIP="$ROOT/dist/Marvin-notarize.zip"
mkdir -p "$ROOT/dist"
rm -f "$ZIP"
ditto -c -k --keepParent "$APP" "$ZIP"
xcrun notarytool submit "$ZIP" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"

echo "Signed + notarized: $APP"
echo "Next: ./scripts/create_dmg.sh"
