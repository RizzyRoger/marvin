"""LLM provider protocol."""

from __future__ import annotations

from typing import Iterator, Protocol

from backend.providers.types import AgentRequest, ModelDefinition, StreamEvent


class LLMProvider(Protocol):
    provider_id: str

    def is_configured(self) -> bool: ...

    def validate_credentials(self) -> None: ...

    def list_models(self) -> list[ModelDefinition]: ...

    def stream_response(self, request: AgentRequest) -> Iterator[StreamEvent]: ...

    def normalize_error(self, error: Exception) -> Exception: ...
