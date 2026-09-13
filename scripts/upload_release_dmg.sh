#!/usr/bin/env bash
# Resilient upload of Marvin DMG (or any file) to a GitHub Release.
# Uses HTTP/1.1 + retries — gh release upload often fails mid-stream on ~700MB
# assets with "broken pipe" / "tls: bad record MAC".
#
# Usage:
#   ./scripts/upload_release_dmg.sh [tag] [path-to-dmg]
#
# Defaults:
#   tag  = v1.0.0  (or VERSION file → v$VERSION)
#   path = dist/Marvin-${VERSION}-$(uname -m).dmg
#
# Requires: gh auth login, curl
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="$(tr -d '[:space:]' <"$ROOT/VERSION" 2>/dev/null || echo "1.0.0")"
ARCH="$(uname -m)"
TAG="${1:-v${VERSION}}"
FILE="${2:-$ROOT/dist/Marvin-${VERSION}-${ARCH}.dmg}"
REPO="${GITHUB_REPOSITORY:-RizzyRoger/marvin}"
MAX_ATTEMPTS="${UPLOAD_ATTEMPTS:-8}"
SLEEP_SECS="${UPLOAD_RETRY_SLEEP:-8}"

if [ ! -f "$FILE" ]; then
  echo "File not found: $FILE" >&2
  exit 1
fi

NAME="$(basename "$FILE")"
LOCAL_SIZE="$(stat -f%z "$FILE" 2>/dev/null || stat -c%s "$FILE")"
TOKEN="$(gh auth token)"
if [ -z "$TOKEN" ]; then
  echo "gh auth token empty — run: gh auth login" >&2
  exit 1
fi

echo "Repo:   $REPO"
echo "Tag:    $TAG"
echo "File:   $FILE ($LOCAL_SIZE bytes)"
echo "Name:   $NAME"

RELEASE_JSON="$(gh api "repos/${REPO}/releases/tags/${TAG}")"
RELEASE_ID="$(printf '%s' "$RELEASE_JSON" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')"
echo "Release id: $RELEASE_ID"

# Remove any prior asset with the same name (partial / failed uploads).
EXISTING_ID="$(printf '%s' "$RELEASE_JSON" | python3 -c '
import json,sys
name=sys.argv[1]
data=json.load(sys.stdin)
for a in data.get("assets") or []:
    if a.get("name")==name:
        print(a["id"])
        break
' "$NAME" || true)"
if [ -n "${EXISTING_ID:-}" ]; then
  echo "Deleting existing asset id=$EXISTING_ID …"
  gh api -X DELETE "repos/${REPO}/releases/assets/${EXISTING_ID}" >/dev/null
fi

URL="https://uploads.github.com/repos/${REPO}/releases/${RELEASE_ID}/assets?name=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))' "$NAME")"

attempt=1
while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
  echo "=== Upload attempt $attempt / $MAX_ATTEMPTS (HTTP/1.1) ==="
  TMP_JSON="$(mktemp)"
  HTTP_CODE=0
  set +e
  HTTP_CODE="$(
    curl -sS --http1.1 \
      --retry 0 \
      --connect-timeout 30 \
      --max-time 0 \
      -o "$TMP_JSON" -w "%{http_code}" \
      -X POST \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "X-GitHub-Api-Version: 2022-11-28" \
      -H "Content-Type: application/octet-stream" \
      --data-binary @"${FILE}" \
      "$URL"
  )"
  CURL_EC=$?
  set -e

  if [ "$CURL_EC" -eq 0 ] && [ "$HTTP_CODE" = "201" ]; then
    REMOTE_SIZE="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("size",0))' "$TMP_JSON")"
    rm -f "$TMP_JSON"
    if [ "$REMOTE_SIZE" = "$LOCAL_SIZE" ]; then
      echo "SUCCESS: uploaded $NAME ($REMOTE_SIZE bytes)"
      echo "URL: https://github.com/${REPO}/releases/download/${TAG}/${NAME}"
      exit 0
    fi
    echo "Size mismatch: local=$LOCAL_SIZE remote=$REMOTE_SIZE — will retry after delete"
    # Fall through: delete mismatched asset on next loop via re-fetch
    RELEASE_JSON="$(gh api "repos/${REPO}/releases/tags/${TAG}")"
    EXISTING_ID="$(printf '%s' "$RELEASE_JSON" | python3 -c '
import json,sys
name=sys.argv[1]
data=json.load(sys.stdin)
for a in data.get("assets") or []:
    if a.get("name")==name:
        print(a["id"])
        break
' "$NAME" || true)"
    if [ -n "${EXISTING_ID:-}" ]; then
      gh api -X DELETE "repos/${REPO}/releases/assets/${EXISTING_ID}" >/dev/null || true
    fi
  else
    echo "Attempt $attempt failed (curl_ec=$CURL_EC http=$HTTP_CODE)"
    if [ -s "$TMP_JSON" ]; then
      head -c 400 "$TMP_JSON" || true
      echo
    fi
    rm -f "$TMP_JSON"
  fi

  attempt=$((attempt + 1))
  if [ "$attempt" -le "$MAX_ATTEMPTS" ]; then
    echo "Sleeping ${SLEEP_SECS}s …"
    sleep "$SLEEP_SECS"
  fi
done

echo "FAILED: could not upload $NAME after $MAX_ATTEMPTS attempts." >&2
echo "Tips:" >&2
echo "  - For ~80MB chunks: split -b 80m FILE FILE.part && upload each part," >&2
echo "    then run workflow 'Assemble release DMG' on GitHub Actions." >&2
echo "  - Or open https://github.com/${REPO}/releases/tag/${TAG} → Edit → drag the file." >&2
exit 1
