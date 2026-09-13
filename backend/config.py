"""Marvin configuration — paths, model IDs, and UI defaults."""

import os
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
CHAT_HISTORY_PATH = DATA_DIR / "chat_history.json"
LOG_PATH = DATA_DIR / "marvin.log"

# --- Speech-to-text (Whisper large-v3-turbo, int8 ≈ Q4) ---
WHISPER_MODEL_ID = "deepdml/faster-whisper-large-v3-turbo-ct2"
WHISPER_COMPUTE_TYPE = "int8"
WHISPER_DEVICE = "auto"  # cuda if available, else cpu (works on Apple Silicon)
WHISPER_BEAM_SIZE = 1  # greedy decoding is substantially faster for live conversation

# --- LLM (Qwen3 4B Instruct, Q4) ---
LLM_REPO = "DhruvalLabs/Qwen3-4B-Instruct-2507-GGUF"
LLM_FILENAME = "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
LLM_MLX_REPO = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
LLM_MLX_DIR = MODELS_DIR / "llm-mlx"
LLM_N_CTX = 8192
LLM_HISTORY_MESSAGES = 6  # three recent turns preserve continuity with less prompt work
# Spoken replies stay short; keep generation bounded to reduce LLM+TTS latency.
LLM_CHAT_MAX_TOKENS = 256
# Metal + PyTorch together can crash llama.cpp on macOS; default to CPU there.
# Override with MARVIN_LLM_GPU_LAYERS=-1 for full Metal offload if stable on your machine.
_default_gpu_layers = 0 if platform.system() == "Darwin" else -1
LLM_N_GPU_LAYERS = int(os.getenv("MARVIN_LLM_GPU_LAYERS", str(_default_gpu_layers)))

# --- TTS (Kokoro-82M) ---
KOKORO_VOICE = "bm_george"  # British male
KOKORO_LANG = "b"  # British English
KOKORO_SAMPLE_RATE = 24000
KOKORO_VOICE_MAP = {
    ("british", "male"): ("bm_george", "b"),
    ("british", "female"): ("bf_emma", "b"),
    ("american", "male"): ("am_adam", "a"),
    ("american", "female"): ("af_bella", "a"),
}

# Piper path stubs so speech_settings can resolve optional downloaded voices.
PIPER_VOICE = "en_GB-alan-medium"
PIPER_MODEL_DIR = MODELS_DIR / "piper" / "en" / "en_GB" / "alan" / "medium"
PIPER_MODEL_PATH = PIPER_MODEL_DIR / f"{PIPER_VOICE}.onnx"
PIPER_CONFIG_PATH = PIPER_MODEL_DIR / f"{PIPER_VOICE}.onnx.json"

# --- VAD (Silero) ---
VAD_SAMPLE_RATE = 16000
VAD_THRESHOLD = 0.5
# Natural pauses and filler words often exceed 500 ms; keep the turn open longer.
VAD_MIN_SILENCE_MS = 1200
VAD_SPEECH_PAD_MS = 300

# --- Speaker verification (SpeechBrain ECAPA-TDNN) ---
SPEAKER_MODEL_ID = "speechbrain/spkrec-ecapa-voxceleb"
SPEAKER_PROFILE_PATH = DATA_DIR / "voice_profile.npz"
SPEAKER_SAMPLE_RATE = 16000
SPEAKER_THRESHOLD = 0.2  # cosine similarity; raise to be stricter
SPEAKER_ENROLL_COUNT = 6
SPEAKER_ENROLL_SECONDS = 4.0
SPEAKER_NATURAL_ENROLL_SECONDS = 10.0
SPEAKER_VERIFY_SECONDS = 2.5
SPEAKER_LOCK_ENABLED = True  # default; runtime Voice Lock toggle lives in voice_listening_settings.json

# --- UI tones ---
TONE_SAMPLE_RATE = 22050

# --- Server ---
HOST = "127.0.0.1"
PORT = 8765
DEFAULT_USER_TIMEZONE = os.getenv("DEFAULT_USER_TIMEZONE", "America/Los_Angeles").strip() or "UTC"


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError:
        return


_load_dotenv(Path.home() / "Library" / "Application Support" / "Marvin" / ".env")
_load_dotenv(DATA_DIR / ".env")
_load_dotenv(ROOT / ".env")


def resolve_vault_root(root: Path | None = None) -> Path:
    """MARVIN_VAULT_ROOT env → user_prefs.json → two parents up (dev) → empty."""
    env = (os.environ.get("MARVIN_VAULT_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    prefs_path = DATA_DIR / "user_prefs.json"
    try:
        if prefs_path.is_file():
            import json

            data = json.loads(prefs_path.read_text(encoding="utf-8"))
            saved = str((data or {}).get("vault_root") or "").strip()
            if saved:
                return Path(saved).expanduser().resolve()
    except (OSError, ValueError, TypeError):
        pass
    if (os.environ.get("MARVIN_BUNDLE") or "").strip().lower() in {"1", "true", "yes"}:
        return Path()
    guessed = (root or ROOT).parent.parent
    if guessed.is_dir():
        return guessed.resolve()
    return Path()


def _bundle_mode() -> bool:
    return (os.environ.get("MARVIN_BUNDLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


# --- Obsidian vault ---
VAULT_ROOT = resolve_vault_root(ROOT)
BRAND_LOGO_PATH = (
    VAULT_ROOT
    / "media"
    / "b28c1df3-7823-4e4b-8f18-8a8a9c6af0da-removebg-preview.png"
)
# Distributed builds disable the Python runner unless explicitly re-enabled.
PYTHON_RUNNER_ENABLED = (
    (os.environ.get("MARVIN_ALLOW_PYTHON") or "").strip().lower()
    in {"1", "true", "yes", "on"}
    or not _bundle_mode()
)
OBSIDIAN_BLOCKED_DIR_NAMES = ("Projects",)  # hard-blocked for all tools
OBSIDIAN_MAX_READ_CHARS = 12_000
OBSIDIAN_MAX_WRITE_CHARS = 4_000  # even authorized edits cannot dump huge blobs
OBSIDIAN_MAX_APPEND_CHARS = 1_500
OBSIDIAN_CACHE_TTL_SECONDS = 30.0

# --- Web search (Tavily) ---
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "").strip()
WEB_SEARCH_TIMEOUT_MS = int(os.getenv("WEB_SEARCH_TIMEOUT_MS", "8000"))
WEB_SEARCH_DEFAULT_MAX_RESULTS = int(os.getenv("WEB_SEARCH_DEFAULT_MAX_RESULTS", "5"))
WEB_SEARCH_MAX_QUERIES_PER_TURN = int(os.getenv("WEB_SEARCH_MAX_QUERIES_PER_TURN", "3"))
WEB_SEARCH_MAX_CONCURRENCY = int(os.getenv("WEB_SEARCH_MAX_CONCURRENCY", "2"))
WEB_SEARCH_DEFAULT_DEPTH = os.getenv("WEB_SEARCH_DEFAULT_DEPTH", "balanced").strip().lower()
WEB_SEARCH_CACHE_ENABLED = os.getenv("WEB_SEARCH_CACHE_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
WEB_SEARCH_GENERAL_CACHE_TTL_MS = int(os.getenv("WEB_SEARCH_GENERAL_CACHE_TTL_MS", "300000"))
WEB_SEARCH_NEWS_CACHE_TTL_MS = int(os.getenv("WEB_SEARCH_NEWS_CACHE_TTL_MS", "60000"))

# --- Spotify (Web API + Connect control; Premium required for playback) ---
SPOTIFY_ENABLED = os.getenv("SPOTIFY_ENABLED", "1").strip().lower() not in {
    "0",
    "false",
    "no",
    "off",
}
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI",
    f"http://{HOST}:{PORT}/api/spotify/callback",
).strip()
SPOTIFY_SCOPES = (
    "user-read-playback-state "
    "user-modify-playback-state "
    "user-read-currently-playing "
    "playlist-read-private "
    "playlist-read-collaborative "
    "user-read-email "
    "user-top-read"
)
SPOTIFY_API_TIMEOUT_SECONDS = float(os.getenv("SPOTIFY_API_TIMEOUT_SECONDS", "10"))

# --- Agent functions (extensible sidebar) ---
FUNCTIONS = [
    {"id": "chat", "label": "Chat", "description": "General conversation with Marvin", "enabled": True},
    {"id": "voice_lock", "label": "Voice Lock", "description": "Enroll your voice so Marvin ignores others", "enabled": True},
    {"id": "obsidian", "label": "Obsidian", "description": "Read and (with permission) edit vault notes", "enabled": True},
    {"id": "daily_planning", "label": "Daily Planning", "description": "Plan your day and tasks", "enabled": True},
    {"id": "web_search", "label": "Web Search", "description": "Search the internet for current information", "enabled": True},
    {"id": "spotify", "label": "Spotify", "description": "Control Spotify playback on your devices", "enabled": True},
    {"id": "timers", "label": "Timers", "description": "Set and control countdown timers", "enabled": True},
    {"id": "voice_scrambler", "label": "Voice Scrambler", "description": "Anonymize mic audio for other apps", "enabled": True},
    {"id": "python_runner", "label": "Python Scripts", "description": "Run sandboxed Python scripts", "enabled": True},
    {"id": "ai_model", "label": "Model", "description": "Switch the active AI model", "enabled": True},
]

_SHARED_STYLE = (
    "Respond concisely and naturally, as if speaking aloud, and in short enough duration to be read aloud by a text-to-speech engine. "
    "Never use emoji or emoticons — plain text only. "
    "Never end with a question, offer, invitation, or request for more information. "
    "Never ask questions at the end of your response, or give a suggestion for what to do next. "
    "Do not write Unicode symbols that text-to-speech would read awkwardly. "
    "Treat each new request as independent by default. Use earlier conversation only "
    "when the new request explicitly refers back to it or is inherently about the same topic."
)

SYSTEM_PROMPTS = {
    "chat": (
        "You are Marvin, a helpful personal AI assistant. "
        f"{_SHARED_STYLE} "
        "Before responding, silently identify the requested function: chat, Obsidian, "
        "or Voice Lock. Follow that function's behavior without describing this step. "
        "If the user asks about Obsidian notes or the vault, use the available tools. "
        "Never access or mention anything under the Projects folder. "
        "Only edit/create/delete notes when the user explicitly asks you to change a file; "
        "then call the tool with authorized=true. Otherwise read-only. "
        "If they asked to check off / mark done or said I authorise / use the write tool, "
        "call complete_task with authorized=true."
    ),
    "obsidian": (
        "You are Marvin with Obsidian vault access. "
        f"{_SHARED_STYLE} "
        "Silently reflect: 'What file would the user mean by this?' Then identify the "
        "note operation, call the necessary tool, inspect its result, and answer from "
        "evidence without revealing your internal reasoning. "
        "When the path is approximate or implied, prefer read_best_note to infer and "
        "read it in one call; use find_note when you only need candidates. "
        "Use tools to list, search, and read notes when the user asks about their vault. "
        "Example: 'Review my daily note' means call read_best_note with that phrase, "
        "then summarize the returned note. "
        "If no note is found, find the closest matching note and use that instead. "
        "The Projects folder is permanently unavailable — refuse any request about it. "
        "You may edit, create, or delete notes ONLY when the user explicitly requests that change. "
        "If they asked to check off, mark done/complete, or authorized the write "
        "(I authorise / I authorize / use the write tool / use the edit tool), "
        "call complete_task with authorized=true and a query naming each item "
        "(join several with 'and'). Do not say you are not authorized after those phrases. "
        "For other writes, call the tool with authorized=true. Never invent file contents you did not read. "
        "Never copy topics or content from an earlier request into a new note unless the "
        "user explicitly connects them. Use create_daily_note for today or tomorrow so "
        "the application, not the model, determines the date and canonical folder. "
        "Keep edits small. Prefer append over replacing an entire note when possible."
    ),
    "daily_planning": (
        "You are Marvin in daily planning mode. Help the user organize their day, "
        f"prioritize tasks, and create actionable schedules. {_SHARED_STYLE}"
    ),
    "voice_lock": (
        "You are Marvin helping the user set up Voice Lock. "
        f"Explain enrollment steps clearly and briefly. {_SHARED_STYLE}"
    ),
}

ENROLL_PHRASE_POOL = [
    "The beige hue on the waters of the loch impressed all, including the French queen, before she heard that symphony again, just as young Arthur wanted.",
    "Are those shy Eurasian footwear, cowboy chaps, or jolly earthmoving headgear?",
    "With tenure, Suzie'd have all the more leisure for yachting, but her publications are no good.",
    "Shaw, those twelve beige hooks are joined if I patch a young, gooey mouth.",
    "The hungry purple dinosaur ate the other, softer one with sauce.",
    "A mad boxer shot a quick, gloved jab to the jaw of his dizzy opponent.",
    "The quick brown fox jumps over a lazy dog near the riverbank.",
    "How razorback-jumping frogs can level six piqued gymnasts!",
    "Pack my box with five dozen liquor jugs for the evening.",
    "We promptly judged antique ivory buckles for the next prize.",
]

ENROLL_NATURAL_PROMPT = (
    "Speak naturally for about ten seconds about your day. "
    "Do not read this instruction aloud; describe anything you did in your own words."
)
ENROLL_NATURAL_LABEL = "Natural speech sample"

# Backward-compatible alias used by older callers; prefer enrollment_phrases().
ENROLL_PHRASES = ENROLL_PHRASE_POOL[:5] + [ENROLL_NATURAL_PROMPT]


def enrollment_phrases() -> list[str]:
    """Return a shuffled set: five rich sentences + one natural-speech prompt."""
    import random

    rich = list(ENROLL_PHRASE_POOL)
    random.shuffle(rich)
    selected = rich[:5]
    insert_at = random.randrange(0, len(selected) + 1)
    selected.insert(insert_at, ENROLL_NATURAL_PROMPT)
    return selected


_TOOL_EVIDENCE_RULE = (
    "When tools are available this turn, never claim a tool action succeeded and never "
    "invent tool results (vault contents, search hits, Spotify playback, script output, "
    "timer state, model switch, scrambler state) without calling the tool and using its "
    "returned evidence."
)

# Voice commands to switch functions
FUNCTION_VOICE_ALIASES = {
    "chat": ["chat", "general", "conversation", "default"],
    "daily_planning": ["daily planning", "plan my day", "planning", "schedule"],
    "web_search": ["web search", "search the web", "internet search"],
    "obsidian": ["obsidian", "notes", "vault"],
    "python_runner": ["python", "run script", "execute code"],
    "voice_lock": ["voice lock", "voice key", "authentication"],
}


def response_max_tokens(user_message: str, *, default: int | None = None) -> int:
    """Heuristic token budget: bump only when the user asks for a long answer."""
    import re

    base = LLM_CHAT_MAX_TOKENS if default is None else default
    lower = (user_message or "").lower()
    if re.search(
        r"\b("
        r"in detail|explain in detail|long(?:er)?(?:\s+answer|\s+explanation)?|"
        r"walk me through|thorough(?:ly)?|elaborate|comprehensive|deep dive|"
        r"step by step|in depth|full(?:er)? explanation"
        r")\b",
        lower,
    ):
        return max(base, 550)
    return base
