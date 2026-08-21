# Marvin

Personal voice AI agent — runs entirely on your machine.

**Pipeline:** Microphone → Silero VAD → Whisper large-v3-turbo → Qwen3 4B (local default) or cloud LLM → Piper ONNX → Speakers

Only transcribed text is saved; raw audio recordings are never persisted.

## Requirements

- macOS (Apple Silicon recommended) or Linux
- Python 3.10+
- [Homebrew](https://brew.sh)
- ~4.5 GB disk space for local models (including Qwen)
- Optional API keys for OpenAI, Anthropic, and/or xAI (Settings → AI Providers)
- Optional `SPOTIFY_CLIENT_ID` for Spotify Connect control
- Optional `TAVILY_API_KEY` for web search

## Quick Start

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Then launch Marvin as a **local desktop app** (dev):

```bash
./scripts/run.sh
```

### Install to /Applications

```bash
./scripts/install_to_applications.sh
open -a Marvin
```

That builds a self-contained `Marvin.app`, copies it to `/Applications`, and places models/data under `~/Library/Application Support/Marvin/`. Double-clicking the Applications icon no longer needs the Documents project folder. Set the Obsidian vault under Settings → General if it is not `~/Documents/Obsidian Vault`.

Or run the API server only:

```bash
source .venv/bin/activate
python -m backend.main
```

Then open **http://127.0.0.1:8765** in your browser.

## Settings

Open **Settings** for:

| Category | What it controls |
|----------|------------------|
| General | Theme, UI scale, Obsidian vault path, privacy summary, clear chat |
| AI Providers | OpenAI / Anthropic / xAI keys (Keychain) + model picker |
| Voice Lock | Enroll voice, strictness, addressing rules |
| Spotify | Connect / disconnect Spotify (PKCE; tokens in Keychain) |
| Skills | Status and folder for `skill.md` standing instructions |

## Privacy — what leaves the machine

| Data | Stays local | May leave (only if enabled) |
|------|-------------|------------------------------|
| Mic audio / Voice Lock embeddings | Yes | No |
| Chat history JSON | Yes | Cloud LLM prompts/replies when a cloud model is selected |
| Obsidian vault on disk | Yes | **Note fragments can leave** if a cloud model + Obsidian tools run in the same turn |
| Web search queries | — | Yes, to Tavily |
| Spotify OAuth + playback commands | Tokens in Keychain | Auth/API traffic to Spotify |

See [SECURITY.md](SECURITY.md) for the distribution threat model and wipe paths.

Third-party license texts are collected in [`licenses/`](licenses/) and indexed in [Licenses.md](Licenses.md).

## Website (marvin.sarl)

Static landing page lives in [`docs/`](docs/). Host with GitHub Pages (`main` → `/docs`). DNS and publish steps: [docs/README.md](docs/README.md) and [docs/DNS.md](docs/DNS.md).

## Packaging / DMG distribution

**Local install (this Mac):**

```bash
./scripts/install_to_applications.sh   # Dev build + /Applications + models (clears quarantine locally)
./scripts/build_app.sh                 # Rebuild Marvin.app only
```

**Release artifact for another Mac (Apple Silicon):**

```bash
./scripts/lock_requirements.sh         # Prefer hashed lock (uv / pip-tools)
./scripts/release_build.sh             # Embedded Python — no Homebrew on the recipient Mac
./scripts/sign_and_notarize.sh         # Developer ID + notarize + staple (Apple cert required)
./scripts/create_dmg.sh                # dist/Marvin-VERSION-arm64.dmg + ZIP + SHA256SUMS
```

- Models are **not** inside the DMG; first launch downloads and verifies them into Application Support.
- Never ship your `.env`. Recipients use their own Spotify client id and API keys.
- Do **not** publish `xattr -cr` / Gatekeeper-disable instructions for downloaders.

Details: [SECURITY.md](SECURITY.md).

Writable state:

| Path | Contents |
|------|----------|
| `~/Library/Application Support/Marvin/data` | chat, voice lock, prefs, reminders |
| `~/Library/Application Support/Marvin/models` | Whisper / Piper / related models |
| `~/Library/Logs/Marvin/marvin.log` | Launch logs |

If Obsidian notes fail after install, open **Settings → General**, confirm the vault path, and grant Marvin access to Documents (or Full Disk Access) when macOS prompts.

## Python runner

Ask explicitly to run/execute Python. In **distributed / bundled** builds the runner is **off** unless `MARVIN_ALLOW_PYTHON=1` (then macOS `sandbox-exec` deny-network is applied). Dev builds keep the scripts-dir runner enabled.

## Spotify setup

1. Create an app in the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).
2. Add redirect URI: `http://127.0.0.1:8765/api/spotify/callback`
3. Put `SPOTIFY_CLIENT_ID=...` in `.env` (see `.env.example`).
4. Restart Marvin → Settings → Spotify → Connect Spotify.
5. Keep Spotify open on a device; Premium is required for playback control.

## Skills

`~/Library/Application Support/Marvin/skills/skill.md` is created on first launch.
Replace the placeholder with your instructions; Marvin appends it to the system prompt when configured.
Use Settings → Skills → Open skills folder.

## Local reminders

Say e.g. “Remind me to stretch in 20 minutes.” Reminders are stored under `data/reminders.json` and fire while Marvin is running (chat toast via WebSocket).

## Usage

1. Wait for models to load (status pill turns green).
2. Click **Start Voice** and speak, or type in the text box (local Qwen is the default).
3. Optionally open **Settings → AI Providers** to add a cloud API key, then use the gear beside **Send** to choose a model.
4. Marvin routes each request automatically; the sidebar shows which function is active.
5. Press **Shift+Enter** for a new line. Markdown is rendered in both prompts and replies.

### Obsidian safeguards

- Marvin can **list, search, and read** notes outside `Projects/`.
- The entire **`Projects/`** folder is hard-blocked.
- **Edit / create / delete** only run when you explicitly ask and the server double-checks wording.
- Marvin will not ask follow-up questions — it answers in one turn.

## Live-test checklist

See [LIVE_TEST.md](LIVE_TEST.md) before tagging a release.

## Models

| Stage | Model | Size |
|-------|-------|------|
| VAD | Silero VAD | ~2 MB |
| Speaker | WeSpeaker ResNet34 (VoxCeleb) | ~25 MB |
| STT | Whisper large-v3-turbo (int8) | ~1.5 GB |
| LLM | Qwen3 4B local (default) or OpenAI / Anthropic / xAI | ~2.5 GB local |
| TTS | Piper (`en_GB-alan-medium` British male, project-local) | ~60 MB |

```bash
python scripts/download_models.py
```

## Troubleshooting

**App opens then immediately closes / “Operation not permitted” on marvin.log**  
macOS often blocks Finder-launched apps from writing under **Documents** (where this Obsidian project lives). Logs now go to `~/Library/Logs/Marvin/marvin.log` (fallback `/tmp/marvin.log`).

```bash
lsof -ti:8765 | xargs kill
./scripts/build_app.sh
open Marvin.app
```

Check the log:

```bash
tail -n 50 ~/Library/Logs/Marvin/marvin.log
```

If the app still cannot read the project under Documents (models/venv), try one of:

1. Launch from Terminal (inherits Documents access): `./scripts/run.sh`
2. Move/copy `Marvin.app` to `/Applications`, then grant **System Settings → Privacy & Security → Files and Folders** (or Full Disk Access) access to Documents for Marvin
3. Set `MARVIN_HOME` to the project path if the app was moved

**Slow LLM on Apple Silicon**  
```bash
MARVIN_LLM_GPU_LAYERS=-1 ./scripts/run.sh
```

## Roadmap status

- [x] Voice Lock
- [x] Obsidian vault access
- [x] Web search (Tavily)
- [x] Spotify Connect control
- [x] Daily planning + local reminders
- [x] Skills file injection
- [x] Sandboxed Python runner
- [x] UI scale + privacy Settings
- [x] Release DMG pipeline (embedded Python, signing scripts, SECURITY.md)
- [ ] Notarized build on a Developer ID (requires Apple cert on the build Mac)
