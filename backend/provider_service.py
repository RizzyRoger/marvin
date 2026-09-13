"""AI provider settings API helpers."""

from __future__ import annotations

import logging

from backend.ai_settings import (
    load_ai_provider_settings,
    save_ai_provider_settings,
    update_ai_provider_settings,
)
from backend.credentials import ProviderId, get_credential_store
from backend.model_catalog import (
    LOCAL_MODEL_ID,
    LOCAL_PROVIDER_ID,
    PROVIDER_DISPLAY,
    catalog_payload,
    default_model_for_provider,
    invalidate_cache,
)
from backend.providers import get_provider
from backend.providers.session_llm import resolve_active_selection
from backend.providers.types import ProviderError

logger = logging.getLogger(__name__)

_PROVIDER_IDS: tuple[ProviderId, ...] = ("openai", "anthropic", "xai")


def providers_status() -> dict:
    from backend.network import network_available

    store = get_credential_store()
    settings = load_ai_provider_settings()
    configured = {pid: store.is_configured(pid) for pid in _PROVIDER_IDS}
    cards = []
    for pid in _PROVIDER_IDS:
        default = (settings.default_models or {}).get(pid)
        if not default:
            model = default_model_for_provider(pid)
            default = model.model_id if model else None
        cards.append(
            {
                "provider_id": pid,
                "display_name": PROVIDER_DISPLAY[pid],
                "configured": configured[pid],
                "default_model": default,
                "privacy_notice": (
                    "Prompts and conversation context are sent to this provider "
                    "when it is selected."
                ),
            }
        )
    online = network_available()
    effective_provider, effective_model = resolve_active_selection()
    return {
        "providers": cards,
        "selected_provider": effective_provider,
        "selected_model": effective_model,
        "saved_provider": settings.selected_provider,
        "saved_model": settings.selected_model,
        "last_cloud_provider": settings.last_cloud_provider,
        "last_cloud_model": settings.last_cloud_model,
        "pending_provider": settings.pending_provider,
        "pending_model": settings.pending_model,
        "network_available": online,
        "catalog": catalog_payload(configured),
        "local_default": {
            "provider_id": LOCAL_PROVIDER_ID,
            "model_id": LOCAL_MODEL_ID,
            "display_name": "Qwen3 4B Instruct",
        },
    }


def save_provider_key(provider_id: str, api_key: str) -> dict:
    if provider_id not in _PROVIDER_IDS:
        raise ValueError("Unknown provider")
    store = get_credential_store()
    # Persist first so the key is available; validation failure does not delete it.
    store.set(provider_id, api_key)  # type: ignore[arg-type]
    invalidate_cache(provider_id)
    validation = test_provider_key(provider_id)
    settings = load_ai_provider_settings()
    # Apply pending selection only after a successful validation.
    if validation.get("ok") and (
        settings.pending_provider == provider_id and settings.pending_model
    ):
        settings.selected_provider = provider_id
        settings.selected_model = settings.pending_model
        settings.pending_provider = None
        settings.pending_model = None
        settings.last_cloud_provider = provider_id
        settings.last_cloud_model = settings.selected_model
        defaults = dict(settings.default_models or {})
        defaults[provider_id] = settings.selected_model
        settings.default_models = defaults
        save_ai_provider_settings(settings)
    elif validation.get("ok") and not settings.selected_provider:
        model = default_model_for_provider(provider_id)
        if model:
            settings.selected_provider = provider_id
            settings.selected_model = model.model_id
            settings.last_cloud_provider = provider_id
            settings.last_cloud_model = model.model_id
            defaults = dict(settings.default_models or {})
            defaults[provider_id] = model.model_id
            settings.default_models = defaults
            save_ai_provider_settings(settings)
    status = providers_status()
    status["validation"] = validation
    return status


def delete_provider_key(provider_id: str) -> dict:
    if provider_id not in _PROVIDER_IDS:
        raise ValueError("Unknown provider")
    store = get_credential_store()
    store.delete(provider_id)  # type: ignore[arg-type]
    invalidate_cache(provider_id)
    settings = load_ai_provider_settings()
    if settings.selected_provider == provider_id:
        settings.selected_provider = LOCAL_PROVIDER_ID
        settings.selected_model = LOCAL_MODEL_ID
        save_ai_provider_settings(settings)
    return providers_status()


def test_provider_key(provider_id: str, api_key: str | None = None) -> dict:
    if provider_id not in _PROVIDER_IDS:
        raise ValueError("Unknown provider")
    provider = get_provider(provider_id, api_key=api_key or None)
    try:
        if api_key:
            # Validate the candidate without deleting the stored key on failure.
            get_provider(provider_id, api_key=api_key).validate_credentials()
        else:
            provider.validate_credentials()
        models = provider.list_models()
        return {
            "ok": True,
            "provider_id": provider_id,
            "models": [
                {
                    "model_id": m.model_id,
                    "display_name": m.display_name,
                    "recommended": m.recommended,
                }
                for m in models
            ],
        }
    except ProviderError as exc:
        return {
            "ok": False,
            "provider_id": provider_id,
            "error_code": exc.code,
            "error_message": exc.user_message(),
        }
    except Exception as exc:
        mapped = provider.normalize_error(exc)
        if isinstance(mapped, ProviderError):
            return {
                "ok": False,
                "provider_id": provider_id,
                "error_code": mapped.code,
                "error_message": mapped.user_message(),
            }
        return {
            "ok": False,
            "provider_id": provider_id,
            "error_code": "unknown",
            "error_message": "Could not validate the API key.",
        }


def select_model(provider_id: str, model_id: str) -> dict:
    if provider_id == LOCAL_PROVIDER_ID:
        defaults = dict(load_ai_provider_settings().default_models or {})
        defaults[LOCAL_PROVIDER_ID] = model_id or LOCAL_MODEL_ID
        update_ai_provider_settings(
            selected_provider=LOCAL_PROVIDER_ID,
            selected_model=model_id or LOCAL_MODEL_ID,
            pending_provider=None,
            pending_model=None,
            default_models=defaults,
        )
        return {**providers_status(), "needs_key": False}
    if provider_id not in _PROVIDER_IDS:
        raise ValueError("Unknown provider")
    store = get_credential_store()
    if not store.is_configured(provider_id):  # type: ignore[arg-type]
        update_ai_provider_settings(
            pending_provider=provider_id,
            pending_model=model_id,
        )
        return {
            **providers_status(),
            "needs_key": True,
            "focus_provider": provider_id,
        }
    defaults = dict(load_ai_provider_settings().default_models or {})
    defaults[provider_id] = model_id
    update_ai_provider_settings(
        selected_provider=provider_id,
        selected_model=model_id,
        pending_provider=None,
        pending_model=None,
        default_models=defaults,
        last_cloud_provider=provider_id,
        last_cloud_model=model_id,
    )
    return {**providers_status(), "needs_key": False}
