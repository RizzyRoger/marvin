"""LLM-callable model switching for Marvin."""

from __future__ import annotations

import logging
import re
import threading
from typing import Any

from backend.model_catalog import (
    LOCAL_PROVIDER_ID,
    PROVIDER_DISPLAY,
    default_model_for_provider,
    find_model,
)
from backend.network import network_available
from backend.provider_service import select_model

logger = logging.getLogger(__name__)

_VALID_PROVIDERS = frozenset({"local", "openai", "anthropic", "xai"})

_PROVIDER_ALIASES = {
    "local": "local",
    "qwen": "local",
    "qwen3": "local",
    "openai": "openai",
    "chatgpt": "openai",
    "gpt": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "opus": "anthropic",
    "xai": "xai",
    "grok": "xai",
}

_MODEL_OR_PROVIDER = (
    r"(?:claude|opus|anthropic|chatgpt|openai|gpt[\w.\-]*|grok|xai|"
    r"qwen3?|local(?:\s+qwen)?)"
)

_SWITCH_INTENT = re.compile(
    rf"(?:"
    rf"\b(?:switch|change|use|set)\b.{{0,48}}\b{_MODEL_OR_PROVIDER}\b"
    rf"|\b(?:go\s+)?(?:back\s+)?to\s+(?:the\s+)?{_MODEL_OR_PROVIDER}\b"
    rf"|\b{_MODEL_OR_PROVIDER}\b.{{0,24}}\b(?:model|instead)\b"
    rf")",
    re.I,
)

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "switch_model",
            "description": (
                "Switch Marvin’s active AI model for the next turn. "
                "Pass provider_id: local, openai, anthropic, or xai. "
                "Omit model_id to use that provider’s flagship. "
                "Do not claim a switch succeeded without calling this tool."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "provider_id": {
                        "type": "string",
                        "enum": ["local", "openai", "anthropic", "xai"],
                        "description": "Target provider.",
                    },
                    "model_id": {
                        "type": "string",
                        "description": (
                            "Optional catalog model id. Omit for the provider flagship."
                        ),
                    },
                },
                "required": ["provider_id"],
                "additionalProperties": False,
            },
        },
    },
]


def tools_for_switch_model() -> list[dict[str, Any]]:
    return list(TOOL_DEFINITIONS)


def decide_switch_model(user_message: str, *, available: bool = True) -> bool:
    text = (user_message or "").strip()
    if not text or not available:
        return False
    return bool(_SWITCH_INTENT.search(text))


def _normalize_provider(raw: str) -> str | None:
    key = (raw or "").strip().lower()
    if not key:
        return None
    if key in _VALID_PROVIDERS:
        return key
    return _PROVIDER_ALIASES.get(key)


def _display_name(provider_id: str, model_id: str) -> str:
    model = find_model(provider_id, model_id)
    if model and model.display_name:
        return model.display_name
    return PROVIDER_DISPLAY.get(provider_id, provider_id)


def dispatch_switch_model(
    name: str,
    args: dict,
    user_message: str,
    *,
    cancellation_event: threading.Event | None = None,
) -> str:
    del user_message
    if cancellation_event is not None and cancellation_event.is_set():
        return "Model switch canceled."
    if name != "switch_model":
        return f"Unknown model tool: {name}"

    provider_id = _normalize_provider(str(args.get("provider_id") or ""))
    if not provider_id:
        return (
            "I need a provider: local, openai, anthropic, or xai. "
            "Try again with one of those."
        )

    model_id = str(args.get("model_id") or "").strip()
    if not model_id:
        default = default_model_for_provider(provider_id)
        if not default:
            return f"No models are available for {provider_id}."
        model_id = default.model_id
    elif not find_model(provider_id, model_id):
        default = default_model_for_provider(provider_id)
        if not default:
            return f"I don’t recognize model {model_id} for {provider_id}."
        model_id = default.model_id

    try:
        result = select_model(provider_id, model_id)
    except ValueError:
        return "Unknown provider. Use local, openai, anthropic, or xai."
    except Exception:
        logger.exception("AI_MODEL: switch_model failed")
        return "Could not switch models right now."

    label = _display_name(provider_id, model_id)
    if result.get("needs_key"):
        provider_label = PROVIDER_DISPLAY.get(provider_id, provider_id)
        return (
            f"Saved {label}, but {provider_label} needs an API key. "
            "Open Settings to add it."
        )

    online = network_available()
    if not online and provider_id != LOCAL_PROVIDER_ID:
        return (
            f"Saved {label} — I’ll use it when you’re back online. "
            "This reply still uses local Qwen."
        )

    return f"Switched to {label} — next reply will use it."
