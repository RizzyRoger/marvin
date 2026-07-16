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
LLM_N_CTX = 8192
LLM_HISTORY_MESSAGES = 6  # three recent turns preserve continuity with less prompt work
# Metal + PyTorch together can crash llama.cpp on macOS; default to CPU there.
# Override with MARVIN_LLM_GPU_LAYERS=-1 for full Metal offload if stable on your machine.
_default_gpu_layers = 0 if platform.system() == "Darwin" else -1
LLM_N_GPU_LAYERS = int(os.getenv("MARVIN_LLM_GPU_LAYERS", str(_default_gpu_layers)))

# --- TTS (Kokoro-82M) ---
KOKORO_VOICE = "bm_george"  # British male
KOKORO_LANG = "b"  # British English
KOKORO_SAMPLE_RATE = 24000

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
SPEAKER_ENROLL_COUNT = 3
SPEAKER_ENROLL_SECONDS = 4.0
SPEAKER_VERIFY_SECONDS = 2.5
SPEAKER_LOCK_ENABLED = True  # when enrolled, only owner voice → Whisper

# --- UI tones ---
TONE_SAMPLE_RATE = 22050

# --- Server ---
HOST = "127.0.0.1"
PORT = 8765

# --- Obsidian vault ---
# Marvin lives at <vault>/Projects/Marvin → vault root is two parents up.
VAULT_ROOT = ROOT.parent.parent
BRAND_LOGO_PATH = (
    VAULT_ROOT
    / "media"
    / "b28c1df3-7823-4e4b-8f18-8a8a9c6af0da-removebg-preview.png"
)
OBSIDIAN_BLOCKED_DIR_NAMES = ("Projects",)  # hard-blocked for all tools
OBSIDIAN_MAX_READ_CHARS = 12_000
OBSIDIAN_MAX_WRITE_CHARS = 4_000  # even authorized edits cannot dump huge blobs
OBSIDIAN_MAX_APPEND_CHARS = 1_500
OBSIDIAN_CACHE_TTL_SECONDS = 30.0

# --- Agent functions (extensible sidebar) ---
FUNCTIONS = [
    {"id": "chat", "label": "Chat", "description": "General conversation with Marvin", "enabled": True},
    {"id": "voice_lock", "label": "Voice Lock", "description": "Enroll your voice so Marvin ignores others", "enabled": True},
    {"id": "obsidian", "label": "Obsidian", "description": "Read and (with permission) edit vault notes", "enabled": True},
    {"id": "daily_planning", "label": "Daily Planning", "description": "Plan your day and tasks", "enabled": False},
    {"id": "web_search", "label": "Web Search", "description": "Search the internet", "enabled": False},
    {"id": "python_runner", "label": "Python Scripts", "description": "Run Python scripts", "enabled": False},
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
        "then call the tool with authorized=true. Otherwise read-only."
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
        "For writes, call the tool with authorized=true. Never invent file contents you did not read. "
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

ENROLL_PHRASES = [
    "Marvin, this is my voice. Please remember how I sound.",
    "The weather is calm today and I am speaking clearly.",
    "My name is the owner of this machine and I talk like this.",
]

# Voice commands to switch functions
FUNCTION_VOICE_ALIASES = {
    "chat": ["chat", "general", "conversation", "default"],
    "daily_planning": ["daily planning", "plan my day", "planning", "schedule"],
    "web_search": ["web search", "search the web", "internet search"],
    "obsidian": ["obsidian", "notes", "vault"],
    "python_runner": ["python", "run script", "execute code"],
    "voice_lock": ["voice lock", "voice key", "authentication"],
}
