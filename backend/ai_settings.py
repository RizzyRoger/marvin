"""AI provider selection settings (non-secret)."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

from backend.config import DATA_DIR

logger = logging.getLogger(__name__)

_SETTINGS_PATH = DATA_DIR / "ai_provider_settings.json"


@dataclass
class AIProviderSettings:
    selected_provider: str | None = None
    selected_model: str | None = None
    pending_provider: str | None = None
    pending_model: str | None = None
    default_models: dict | None = None
    last_cloud_provider: str | None = None
    last_cloud_model: str | None = None

    def __post_init__(self) -> None:
        if self.default_models is None:
            self.default_models = {}


def _remap_stale_selection(
    provider: str | None, model: str | None
) -> tuple[str | None, str | None]:
    """Map removed catalog IDs onto the current flagship (or clear)."""
    from backend.model_catalog import (
        LOCAL_MODEL_ID,
        LOCAL_PROVIDER_ID,
        default_model_for_provider,
        find_model,
    )

    if not provider:
        return None, None
    if provider == "qwen":
        provider = LOCAL_PROVIDER_ID
        model = model or LOCAL_MODEL_ID
    if provider == LOCAL_PROVIDER_ID:
        return LOCAL_PROVIDER_ID, LOCAL_MODEL_ID
    if model and find_model(provider, model):
        return provider, model
    fallback = default_model_for_provider(provider)
    if fallback:
        logger.info(
            "AI settings: remapped stale model %s/%s → %s",
            provider,
            model,
            fallback.model_id,
        )
        return provider, fallback.model_id
    logger.info(
        "AI settings: cleared unknown selection %s/%s",
        provider,
        model,
    )
    return None, None


def load_ai_provider_settings() -> AIProviderSettings:
    if not _SETTINGS_PATH.is_file():
        return AIProviderSettings()
    try:
        raw = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read AI provider settings; using defaults")
        return AIProviderSettings()
    provider = raw.get("selected_provider") or None
    model = raw.get("selected_model") or None
    provider, model = _remap_stale_selection(provider, model)

    pending_provider = raw.get("pending_provider") or None
    pending_model = raw.get("pending_model") or None
    if pending_provider:
        pending_provider, pending_model = _remap_stale_selection(
            pending_provider, pending_model
        )

    last_cloud_provider = raw.get("last_cloud_provider") or None
    last_cloud_model = raw.get("last_cloud_model") or None
    if last_cloud_provider:
        last_cloud_provider, last_cloud_model = _remap_stale_selection(
            last_cloud_provider, last_cloud_model
        )
        # Never treat local as a "last cloud" choice.
        if last_cloud_provider in {None, "local", "qwen"}:
            last_cloud_provider = None
            last_cloud_model = None

    defaults = dict(raw.get("default_models") or {})
    cleaned_defaults: dict[str, str] = {}
    for pid, mid in defaults.items():
        remapped_p, remapped_m = _remap_stale_selection(
            str(pid), str(mid) if mid else None
        )
        if remapped_p and remapped_m:
            cleaned_defaults[remapped_p] = remapped_m

    # Seed last_cloud from a cloud selection when missing (upgrade path).
    if (
        not last_cloud_provider
        and provider
        and provider not in {"local", "qwen"}
        and model
    ):
        last_cloud_provider, last_cloud_model = provider, model

    settings = AIProviderSettings(
        selected_provider=provider,
        selected_model=model,
        pending_provider=pending_provider,
        pending_model=pending_model,
        default_models=cleaned_defaults,
        last_cloud_provider=last_cloud_provider,
        last_cloud_model=last_cloud_model,
    )
    # Persist remaps so the UI stays consistent with runtime.
    if (
        provider != (raw.get("selected_provider") or None)
        or model != (raw.get("selected_model") or None)
        or pending_provider != (raw.get("pending_provider") or None)
        or pending_model != (raw.get("pending_model") or None)
        or cleaned_defaults != defaults
        or last_cloud_provider != (raw.get("last_cloud_provider") or None)
        or last_cloud_model != (raw.get("last_cloud_model") or None)
    ):
        try:
            save_ai_provider_settings(settings)
        except OSError:
            logger.debug("Could not persist remapped AI settings", exc_info=True)
    return settings


def save_ai_provider_settings(settings: AIProviderSettings) -> AIProviderSettings:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = asdict(settings)
    tmp = _SETTINGS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(_SETTINGS_PATH)
    return settings


def update_ai_provider_settings(**changes) -> AIProviderSettings:
    current = load_ai_provider_settings()
    for key, value in changes.items():
        if hasattr(current, key):
            setattr(current, key, value)
    return save_ai_provider_settings(current)
