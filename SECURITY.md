# Marvin security & distribution notes

This document is for people who build or receive a Marvin DMG/ZIP.

## Threat model (honest)

Marvin is a **trusted personal agent** on a single-user Mac. It is not a multi-tenant
service and is not hardened against malware running as the same macOS user.

| Trust assumption | Reality |
|------------------|---------|
| Only you use this Mac account | Same-user processes can still read App Support files |
| Loopback API is for the Marvin UI | Bundled builds require a Keychain-backed session cookie/token |
| Python “sandbox” | Disabled in distributed builds by default; when enabled uses `sandbox-exec` + deny-network |

## What a release image must never contain

- Your `.env` (Tavily / Spotify client id)
- `data/` chat history, Voice Lock profiles, reminders
- `models/` (downloaded on first launch into Application Support)
- Keychain exports or API keys

Release builds fail if `.env`, chat history, or voice profiles appear under the staged `.app`.

## Signed distribution path

```bash
./scripts/lock_requirements.sh          # hashed lock when uv/pip-tools available
./scripts/release_build.sh              # embedded Python, clean venv, VERSION stamp
./scripts/sign_and_notarize.sh          # Developer ID + notarytool + staple
./scripts/create_dmg.sh                 # Marvin-VERSION-arm64.dmg + ZIP + SHA256SUMS
```

Recipients should verify:

```bash
shasum -a 256 -c SHA256SUMS-*-arm64.txt
```

**Do not** tell recipients to run `xattr -cr` or to disable Gatekeeper. That is only for
the developer’s own local `install_to_applications.sh` copy.

## Permissions recipients will see

1. Gatekeeper / notarization prompt (signed builds)
2. Microphone (Info.plist usage string)
3. Files access when choosing an Obsidian vault under Documents

## Data locations

| Path | Contents |
|------|----------|
| `/Applications/Marvin.app` | Code + embedded Python + venv |
| `~/Library/Application Support/Marvin/data` | chat, prefs, reminders, scripts |
| `~/Library/Application Support/Marvin/models` | Whisper / Piper / Silero / WeSpeaker |
| `~/Library/Application Support/Marvin/.env` | Optional local secrets (recipient-owned) |
| `~/Library/Logs/Marvin/marvin.log` | Launch / runtime logs |
| Keychain | `Marvin AI Providers`, `Marvin Spotify`, `Marvin Local API`, `Marvin Voice Lock` |

## Uninstall / wipe

1. Delete `/Applications/Marvin.app`
2. Delete `~/Library/Application Support/Marvin`
3. Delete `~/Library/Logs/Marvin`
4. Remove Keychain items listed above

## Privacy matrix

| Data | Local | Leaves machine |
|------|-------|----------------|
| Mic audio / Voice Lock embeddings | Yes | No |
| Chat history JSON | Yes | Cloud LLM prompts if a cloud model is selected |
| Obsidian vault on disk | Yes | **Yes, fragments can leave** when a cloud model + Obsidian tools run in the same turn |
| Web search | — | Tavily queries when enabled |
| Spotify | Tokens in Keychain | Spotify API traffic |

## Local API auth (bundled mode)

When `MARVIN_BUNDLE=1`, FastAPI requires the session cookie (set on `/`) or
`X-Marvin-Token` / `Authorization: Bearer`. OpenAPI docs are disabled.
`/api/health` and Spotify OAuth callback remain reachable without the token.

Override: `MARVIN_REQUIRE_AUTH=0` (dev only) or `=1` to force auth outside the bundle.

## Python runner

Distributed builds set `PYTHON_RUNNER_ENABLED=False` unless `MARVIN_ALLOW_PYTHON=1`.
When enabled on macOS, Marvin wraps execution with `sandbox-exec` (deny network, scripts dir only).

## Cold-machine smoke checklist

- [ ] Fresh user account or second Mac, Apple Silicon
- [ ] Open DMG → drag to Applications (no Homebrew required)
- [ ] Gatekeeper allows notarized app
- [ ] Mic prompt appears; first-run model download verifies
- [ ] Vault setup dialog; no silent Documents vault attach
- [ ] Unauthenticated `curl http://127.0.0.1:8765/api/chat/history` → 401
- [ ] Settings → AI Providers stores keys in Keychain
- [ ] `/docs` returns 404 in bundled mode
- [ ] SHA256 matches published sums
