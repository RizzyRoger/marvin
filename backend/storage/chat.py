"""Persist chat history as JSON (text only — no raw audio)."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import CHAT_HISTORY_PATH, DATA_DIR

_history_lock = threading.RLock()
_history_cache: list[dict[str, Any]] | None = None


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_history() -> list[dict[str, Any]]:
    global _history_cache
    with _history_lock:
        if _history_cache is None:
            _ensure_data_dir()
            if not CHAT_HISTORY_PATH.exists():
                _history_cache = []
            else:
                with CHAT_HISTORY_PATH.open("r", encoding="utf-8") as f:
                    _history_cache = json.load(f)
        return list(_history_cache)


def save_history(messages: list[dict[str, Any]]) -> None:
    global _history_cache
    with _history_lock:
        _ensure_data_dir()
        fd, temp_name = tempfile.mkstemp(
            dir=DATA_DIR,
            prefix=".chat-history-",
            suffix=".tmp",
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(messages, f, ensure_ascii=False, separators=(",", ":"))
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_name, CHAT_HISTORY_PATH)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        _history_cache = list(messages)


def append_message(
    role: str,
    content: str,
    function_id: str = "chat",
) -> dict[str, Any]:
    with _history_lock:
        messages = load_history()
        entry = {
            "id": str(uuid.uuid4()),
            "role": role,
            "content": content,
            "function_id": function_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        messages.append(entry)
        save_history(messages)
        return entry


def clear_history() -> None:
    save_history([])
