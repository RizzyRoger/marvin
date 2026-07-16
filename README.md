# Marvin

Personal voice AI agent — runs entirely on your machine.

**Pipeline:** Microphone → Silero VAD → Whisper large-v3-turbo → Qwen3 4B Instruct → Kokoro-82M → Speakers

Only transcribed text is saved; raw audio recordings are never persisted.

## Requirements

- macOS (Apple Silicon recommended) or Linux
- Python 3.10+
- [Homebrew](https://brew.sh)
- ~6 GB disk space for models
- Microphone and speakers

## Quick Start

```bash
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Then launch Marvin as a **local desktop app**:

```bash
./scripts/run.sh
```

Or double-click **`Marvin.app`** in Finder.

The app opens a native window (no browser tab needed). To run the API server only:

```bash
source .venv/bin/activate
python -m backend.main
```

Then open **http://127.0.0.1:8765** in your browser.

## Usage

1. Wait for models to load (status pill turns green).
2. Click **Start Voice** and speak, or type in the text box.
3. Select functions from the sidebar (Voice Lock, Obsidian, etc.).
4. Say *"switch to Obsidian"* or ask *"Review my daily note"* to use vault tools.

### Obsidian safeguards

- Marvin can **list, search, and read** notes outside `Projects/`.
- Approximate descriptions such as **"my cognitive science introduction"** are
  matched against note names and folder structure; exact filenames are optional.
- The entire **`Projects/`** folder is hard-blocked (including this app).
- **Edit / create / delete** only run when you explicitly ask (e.g. "edit my note…") and the model sets `authorized=true`; the server double-checks your wording.
- Edits use atomic file replacement to avoid partially written or corrupted notes.
- Large dumps are capped (~4k characters per write).
- Marvin will not ask follow-up questions — it answers in one turn.

## Models

| Stage | Model | Size |
|-------|-------|------|
| VAD | Silero VAD | ~2 MB |
| Speaker | SpeechBrain ECAPA-TDNN | ~20 MB |
| STT | Whisper large-v3-turbo (int8) | ~1.5 GB |
| LLM | Qwen3-4B-Instruct-2507 Q4_K_M | ~2.5 GB |
| TTS | Kokoro-82M (`bm_george` British male) | ~350 MB |

Re-download models anytime:

```bash
python scripts/download_models.py
```

## Project Structure

```
Marvin/
├── backend/
│   ├── main.py          # FastAPI server
│   ├── agent.py         # Voice pipeline orchestrator
│   ├── config.py        # Settings and function registry
│   ├── api.py           # REST + WebSocket routes
│   └── pipeline/        # VAD, STT, LLM, TTS modules
├── frontend/            # Web UI (sidebar + chat)
├── Marvin.app           # Native macOS app (built by setup)
├── scripts/
│   ├── setup.sh         # One-command setup
│   ├── run.sh           # Launch desktop app
│   ├── build_app.sh     # Rebuild Marvin.app
│   └── download_models.py
├── models/              # Downloaded model weights
└── data/                # Chat history (JSON, text only)
```

## Adding Functions

Edit `backend/config.py`:

1. Set `"enabled": True` on a function in `FUNCTIONS`.
2. Add a system prompt in `SYSTEM_PROMPTS`.
3. Add voice aliases in `FUNCTION_VOICE_ALIASES`.

## Troubleshooting

**App opens then immediately closes (dock bounce)**  
1. Quit any existing Marvin instance:
   ```bash
   lsof -ti:8765 | xargs kill
   ```
2. Rebuild the app:
   ```bash
   ./scripts/build_app.sh
   ```
3. Launch (run this on its own line — don't paste the comment after it):
   ```bash
   open Marvin.app
   ```
   Or double-click `Marvin.app` in Finder.
4. Check `data/marvin.log` for errors.

**From Terminal instead:**
```bash
./scripts/run.sh
```

**Slow LLM responses on Apple Silicon**  
Metal GPU offload is disabled by default to avoid crashes. To try GPU acceleration:
```bash
MARVIN_LLM_GPU_LAYERS=-1 ./scripts/run.sh
```

## Roadmap

- [x] Voice lock / authentication
- [x] Obsidian vault access (read + authorized edit)
- [ ] Daily planning
- [ ] Web search
- [ ] Python script execution
- [ ] Optional pyannote diarization for multi-speaker sessions
