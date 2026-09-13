"""Anthropic Messages API provider adapter."""

from __future__ import annotations

import logging
from typing import Iterator

from backend.credentials import get_credential_store
from backend.model_catalog import fallback_catalog, set_cached_models
from backend.providers.common import (
    anthropic_messages,
    anthropic_tools,
    check_canceled,
    error_event,
    map_http_error,
)
from backend.providers.types import (
    AgentRequest,
    ModelDefinition,
    ProviderError,
    ProviderErrorCode,
    StreamEvent,
    StreamEventType,
)

logger = logging.getLogger(__name__)

_TIMEOUT = 45.0


class AnthropicProvider:
    provider_id = "anthropic"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def _key(self) -> str | None:
        return self._api_key or get_credential_store().get("anthropic")

    def is_configured(self) -> bool:
        return bool(self._key())

    def _client(self):
        from anthropic import Anthropic

        key = self._key()
        if not key:
            raise ProviderError(
                ProviderErrorCode.NOT_CONFIGURED,
                "Anthropic is not configured. Add an API key in Settings → AI Providers.",
                provider_id=self.provider_id,
            )
        return Anthropic(api_key=key, timeout=_TIMEOUT)

    def validate_credentials(self) -> None:
        client = self._client()
        try:
            # Lightweight auth check without a billable completion when possible.
            client.models.list(limit=1)
        except Exception as exc:
            raise self.normalize_error(exc) from None

    def list_models(self) -> list[ModelDefinition]:
        fallback = [m for m in fallback_catalog() if m.provider_id == "anthropic"]
        if not self.is_configured():
            return fallback
        try:
            client = self._client()
            remote = {m.id for m in client.models.list(limit=100).data}
            filtered = [m for m in fallback if m.model_id in remote] or fallback
            set_cached_models("anthropic", filtered)
            return filtered
        except Exception:
            logger.debug("Anthropic model list failed; using fallback", exc_info=True)
            return fallback

    def stream_response(self, request: AgentRequest) -> Iterator[StreamEvent]:
        if check_canceled(request.cancellation_event):
            yield StreamEvent(type=StreamEventType.RESPONSE_CANCELED)
            return
        try:
            client = self._client()
            prelude = [{"role": "system", "content": request.system_prompt}]
            if request.runtime_context:
                prelude.append({"role": "system", "content": request.runtime_context})
            system, messages = anthropic_messages(prelude + list(request.messages))
            kwargs: dict = {
                "model": request.model_id,
                "system": system,
                "messages": messages or [{"role": "user", "content": ""}],
                "temperature": request.temperature,
                "top_p": request.top_p,
                "max_tokens": request.max_tokens,
                "stream": True,
            }
            tools = anthropic_tools(request.tools)
            if tools:
                kwargs["tools"] = tools
                if request.force_tool_use:
                    kwargs["tool_choice"] = {"type": "any"}
            with client.messages.stream(**kwargs) as stream:
                active_tools: dict[int, dict] = {}
                for event in stream:
                    if check_canceled(request.cancellation_event):
                        yield StreamEvent(type=StreamEventType.RESPONSE_CANCELED)
                        return
                    etype = getattr(event, "type", "")
                    if etype == "content_block_start":
                        block = event.content_block
                        if getattr(block, "type", "") == "tool_use":
                            active_tools[event.index] = {
                                "id": block.id,
                                "name": block.name,
                                "arguments": "",
                            }
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_STARTED,
                                tool_call_id=block.id,
                                tool_name=block.name,
                                provider_id=self.provider_id,
                                model_id=request.model_id,
                            )
                    elif etype == "content_block_delta":
                        delta = event.delta
                        dtype = getattr(delta, "type", "")
                        if dtype == "text_delta":
                            yield StreamEvent(
                                type=StreamEventType.TEXT_DELTA,
                                text=delta.text,
                                provider_id=self.provider_id,
                                model_id=request.model_id,
                            )
                        elif dtype == "input_json_delta":
                            slot = active_tools.get(event.index)
                            if slot is not None:
                                slot["arguments"] += delta.partial_json
                                yield StreamEvent(
                                    type=StreamEventType.TOOL_CALL_DELTA,
                                    tool_call_id=slot["id"],
                                    tool_name=slot["name"],
                                    text=delta.partial_json,
                                )
                    elif etype == "content_block_stop":
                        slot = active_tools.pop(event.index, None)
                        if slot is not None:
                            import json

                            try:
                                args = json.loads(slot["arguments"] or "{}")
                            except json.JSONDecodeError:
                                args = {}
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_COMPLETED,
                                tool_call_id=slot["id"],
                                tool_name=slot["name"],
                                tool_arguments=args,
                            )
                final = stream.get_final_message()
                usage = {
                    "prompt_tokens": getattr(final.usage, "input_tokens", 0) or 0,
                    "completion_tokens": getattr(final.usage, "output_tokens", 0) or 0,
                }
                yield StreamEvent(type=StreamEventType.USAGE, usage=usage)
            yield StreamEvent(
                type=StreamEventType.RESPONSE_COMPLETED,
                provider_id=self.provider_id,
                model_id=request.model_id,
            )
        except Exception as exc:
            if check_canceled(request.cancellation_event):
                yield StreamEvent(type=StreamEventType.RESPONSE_CANCELED)
                return
            yield error_event(self.normalize_error(exc), self.provider_id, request.model_id)

    def normalize_error(self, error: Exception) -> Exception:
        if isinstance(error, ProviderError):
            return error
        status = getattr(error, "status_code", None) or getattr(
            getattr(error, "response", None), "status_code", None
        )
        return map_http_error(status, str(error), provider_id=self.provider_id)
