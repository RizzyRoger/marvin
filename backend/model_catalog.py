"""Centrally maintained model catalog for Marvin providers."""

from __future__ import annotations

import time
from typing import Iterable

from backend.providers.types import ModelDefinition

LOCAL_PROVIDER_ID = "local"
LOCAL_MODEL_ID = "qwen3-4b-instruct"

PROVIDER_DISPLAY = {
    LOCAL_PROVIDER_ID: "Local (Qwen)",
    "openai": "OpenAI (ChatGPT)",
    "anthropic": "Anthropic (Claude)",
    "xai": "xAI (Grok)",
}

# Fallback catalog — one flagship per provider (streaming + tool calling).
# Local Qwen is always available without an API key and is the offline default.
_FALLBACK: list[ModelDefinition] = [
    ModelDefinition(
        LOCAL_PROVIDER_ID,
        LOCAL_MODEL_ID,
        "Qwen3 4B Instruct",
        recommended=True,
    ),
    ModelDefinition("openai", "gpt-5.6-sol", "GPT-5.6 Sol", recommended=True),
    ModelDefinition(
        "anthropic", "claude-opus-5", "Claude Opus 5", recommended=True
    ),
    ModelDefinition("xai", "grok-4.5", "Grok 4.5", recommended=True),
]

_CACHE_TTL_SECONDS = 300.0
_cache: dict[str, tuple[float, list[ModelDefinition]]] = {}


def fallback_catalog() -> list[ModelDefinition]:
    return list(_FALLBACK)


def models_for_provider(provider_id: str) -> list[ModelDefinition]:
    cached = _cache.get(provider_id)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL_SECONDS:
        return list(cached[1])
    return [m for m in _FALLBACK if m.provider_id == provider_id and m.enabled]


def set_cached_models(provider_id: str, models: Iterable[ModelDefinition]) -> None:
    filtered = [
        m
        for m in models
        if m.supports_streaming and m.supports_tool_calls and m.enabled
    ]
    if not filtered:
        filtered = [m for m in _FALLBACK if m.provider_id == provider_id]
    _cache[provider_id] = (time.monotonic(), filtered)


def invalidate_cache(provider_id: str | None = None) -> None:
    if provider_id is None:
        _cache.clear()
    else:
        _cache.pop(provider_id, None)


def find_model(provider_id: str, model_id: str) -> ModelDefinition | None:
    for model in models_for_provider(provider_id) + fallback_catalog():
        if model.provider_id == provider_id and model.model_id == model_id:
            return model
    return None


def default_model_for_provider(provider_id: str) -> ModelDefinition | None:
    models = models_for_provider(provider_id)
    for model in models:
        if model.recommended:
            return model
    return models[0] if models else None


def catalog_payload(configured: dict[str, bool]) -> list[dict]:
    """UI-facing catalog grouped by provider."""
    groups: list[dict] = []
    for provider_id, display in PROVIDER_DISPLAY.items():
        models = models_for_provider(provider_id)
        is_configured = (
            True
            if provider_id == LOCAL_PROVIDER_ID
            else bool(configured.get(provider_id))
        )
        groups.append(
            {
                "provider_id": provider_id,
                "display_name": display,
                "configured": is_configured,
                "models": [
                    {
                        "provider_id": m.provider_id,
                        "model_id": m.model_id,
                        "display_name": m.display_name,
                        "supports_streaming": m.supports_streaming,
                        "supports_tool_calls": m.supports_tool_calls,
                        "recommended": m.recommended,
                        "deprecated": m.deprecated,
                        "configured": is_configured,
                    }
                    for m in models
                ],
            }
        )
    return groups
