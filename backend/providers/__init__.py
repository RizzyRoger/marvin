"""Provider registry — lazy imports to avoid circular dependencies."""

from __future__ import annotations

from backend.providers.types import ProviderError, ProviderErrorCode

_PROVIDER_IDS = ("openai", "anthropic", "xai")


def get_provider(provider_id: str, api_key: str | None = None):
    if provider_id == "openai":
        from backend.providers.openai_provider import OpenAIProvider

        return OpenAIProvider(api_key=api_key)
    if provider_id == "anthropic":
        from backend.providers.anthropic_provider import AnthropicProvider

        return AnthropicProvider(api_key=api_key)
    if provider_id == "xai":
        from backend.providers.xai_provider import XAIProvider

        return XAIProvider(api_key=api_key)
    raise ProviderError(
        ProviderErrorCode.NOT_CONFIGURED,
        f"Unknown provider: {provider_id}",
        provider_id=provider_id or "",
    )


def all_provider_ids() -> list[str]:
    return list(_PROVIDER_IDS)


__all__ = [
    "all_provider_ids",
    "get_provider",
]
