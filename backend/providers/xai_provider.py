"""xAI Grok provider — OpenAI-compatible endpoint."""

from __future__ import annotations

import json
import logging
from typing import Iterator

from backend.credentials import get_credential_store
from backend.model_catalog import fallback_catalog, set_cached_models
from backend.providers.common import (
    check_canceled,
    error_event,
    map_http_error,
    openai_style_messages,
    openai_tools,
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

_BASE_URL = "https://api.x.ai/v1"
_TIMEOUT = 45.0


class XAIProvider:
    provider_id = "xai"

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key

    def _key(self) -> str | None:
        return self._api_key or get_credential_store().get("xai")

    def is_configured(self) -> bool:
        return bool(self._key())

    def _client(self):
        from openai import OpenAI

        key = self._key()
        if not key:
            raise ProviderError(
                ProviderErrorCode.NOT_CONFIGURED,
                "xAI is not configured. Add an API key in Settings → AI Providers.",
                provider_id=self.provider_id,
            )
        return OpenAI(api_key=key, base_url=_BASE_URL, timeout=_TIMEOUT)

    def validate_credentials(self) -> None:
        client = self._client()
        try:
            client.models.list()
        except Exception as exc:
            raise self.normalize_error(exc) from None

    def list_models(self) -> list[ModelDefinition]:
        fallback = [m for m in fallback_catalog() if m.provider_id == "xai"]
        if not self.is_configured():
            return fallback
        try:
            client = self._client()
            remote = {m.id for m in client.models.list().data}
            filtered = [m for m in fallback if m.model_id in remote] or fallback
            set_cached_models("xai", filtered)
            return filtered
        except Exception:
            logger.debug("xAI model list failed; using fallback", exc_info=True)
            return fallback

    def stream_response(self, request: AgentRequest) -> Iterator[StreamEvent]:
        if check_canceled(request.cancellation_event):
            yield StreamEvent(type=StreamEventType.RESPONSE_CANCELED)
            return
        try:
            client = self._client()
            messages = openai_style_messages(
                request.system_prompt,
                request.runtime_context,
                request.messages,
            )
            kwargs: dict = {
                "model": request.model_id,
                "messages": messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "max_tokens": request.max_tokens,
                "stream": True,
            }
            tools = openai_tools(request.tools)
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "required" if request.force_tool_use else "auto"
            stream = client.chat.completions.create(**kwargs)
            tool_acc: dict[int, dict] = {}
            for chunk in stream:
                if check_canceled(request.cancellation_event):
                    yield StreamEvent(type=StreamEventType.RESPONSE_CANCELED)
                    return
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield StreamEvent(
                        type=StreamEventType.TEXT_DELTA,
                        text=delta.content,
                        provider_id=self.provider_id,
                        model_id=request.model_id,
                    )
                for tc in (delta.tool_calls if delta else None) or []:
                    idx = tc.index if tc.index is not None else 0
                    slot = tool_acc.setdefault(
                        idx, {"id": "", "name": "", "arguments": ""}
                    )
                    if tc.id:
                        if not slot["id"]:
                            slot["id"] = tc.id
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_STARTED,
                                tool_call_id=tc.id,
                                tool_name=(tc.function.name if tc.function else "") or "",
                            )
                        else:
                            slot["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            slot["name"] = tc.function.name
                        if tc.function.arguments:
                            slot["arguments"] += tc.function.arguments
                            yield StreamEvent(
                                type=StreamEventType.TOOL_CALL_DELTA,
                                tool_call_id=slot["id"],
                                tool_name=slot["name"],
                                text=tc.function.arguments,
                            )
            for slot in tool_acc.values():
                try:
                    args = json.loads(slot["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield StreamEvent(
                    type=StreamEventType.TOOL_CALL_COMPLETED,
                    tool_call_id=slot["id"] or slot["name"],
                    tool_name=slot["name"],
                    tool_arguments=args,
                )
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
