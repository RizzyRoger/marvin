"""Shared helpers for cloud LLM providers."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend.credentials import redact_secrets
from backend.providers.types import ProviderError, ProviderErrorCode, StreamEvent, StreamEventType

logger = logging.getLogger(__name__)


def openai_style_messages(
    system_prompt: str,
    runtime_context: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if runtime_context:
        out.append({"role": "system", "content": runtime_context})
    for msg in messages:
        role = msg.get("role")
        if role not in {"user", "assistant", "tool", "system"}:
            continue
        entry: dict[str, Any] = {"role": role}
        if "content" in msg:
            entry["content"] = msg.get("content") or ""
        if role == "assistant" and msg.get("tool_calls"):
            entry["tool_calls"] = msg["tool_calls"]
        if role == "tool":
            entry["tool_call_id"] = msg.get("tool_call_id") or msg.get("name") or "tool"
            if "name" in msg:
                entry["name"] = msg["name"]
        out.append(entry)
    return out


def anthropic_messages(
    messages: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Split system content and convert OpenAI-style history to Anthropic."""
    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    pending_tool_results: list[dict[str, Any]] = []

    def flush_tool_results() -> None:
        nonlocal pending_tool_results
        if pending_tool_results:
            converted.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_parts.append(str(msg.get("content") or ""))
            continue
        if role == "tool":
            pending_tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": msg.get("tool_call_id") or "tool",
                    "content": str(msg.get("content") or ""),
                }
            )
            continue
        flush_tool_results()
        if role == "user":
            converted.append({"role": "user", "content": str(msg.get("content") or "")})
        elif role == "assistant":
            content_blocks: list[dict[str, Any]] = []
            text = msg.get("content") or ""
            if text:
                content_blocks.append({"type": "text", "text": text})
            for call in msg.get("tool_calls") or []:
                fn = call.get("function") or {}
                raw_args = fn.get("arguments") or "{}"
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
                except json.JSONDecodeError:
                    args = {}
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": call.get("id") or f"tool-{len(content_blocks)}",
                        "name": fn.get("name") or "",
                        "input": args,
                    }
                )
            if content_blocks:
                converted.append({"role": "assistant", "content": content_blocks})
    flush_tool_results()
    return "\n\n".join(p for p in system_parts if p), converted


def openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return list(tools or [])


def anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for tool in tools or []:
        fn = tool.get("function") or tool
        out.append(
            {
                "name": fn.get("name"),
                "description": fn.get("description") or "",
                "input_schema": fn.get("parameters")
                or {"type": "object", "properties": {}},
            }
        )
    return out


def map_http_error(
    status: int | None,
    message: str,
    *,
    provider_id: str,
) -> ProviderError:
    text = redact_secrets(message or "")
    lower = text.lower()
    if status in {401, 403} or "invalid api key" in lower or "incorrect api key" in lower:
        code = ProviderErrorCode.INVALID_API_KEY
        user = "The API key was rejected. Open Settings → AI Providers to update it."
    elif "revoked" in lower:
        code = ProviderErrorCode.KEY_REVOKED
        user = "This API key has been revoked. Replace it in Settings → AI Providers."
    elif status == 404 or "model" in lower and "not found" in lower:
        code = ProviderErrorCode.MODEL_UNAVAILABLE
        user = "That model is unavailable. Choose another model in the composer menu."
    elif status == 429 or "rate" in lower:
        code = ProviderErrorCode.RATE_LIMITED
        user = "The provider rate-limited this request. Try again shortly."
    elif "quota" in lower or "billing" in lower or "insufficient" in lower:
        code = ProviderErrorCode.QUOTA_EXHAUSTED
        user = "Provider quota or billing is exhausted."
    elif status is not None and status >= 500:
        code = ProviderErrorCode.OUTAGE
        user = "The provider appears to be unavailable right now."
    elif "timeout" in lower:
        code = ProviderErrorCode.TIMEOUT
        user = "The provider request timed out."
    elif "network" in lower or "connection" in lower:
        code = ProviderErrorCode.NETWORK
        user = "Could not reach the provider. Check your network connection."
    else:
        code = ProviderErrorCode.UNKNOWN
        user = "The AI provider returned an error."
    return ProviderError(code, user, provider_id=provider_id, status_code=status)


def error_event(exc: Exception, provider_id: str, model_id: str = "") -> StreamEvent:
    if isinstance(exc, ProviderError):
        return StreamEvent(
            type=StreamEventType.PROVIDER_ERROR,
            error_code=exc.code,
            error_message=exc.user_message(),
            provider_id=provider_id,
            model_id=model_id,
        )
    mapped = map_http_error(None, str(exc), provider_id=provider_id)
    return StreamEvent(
        type=StreamEventType.PROVIDER_ERROR,
        error_code=mapped.code,
        error_message=mapped.user_message(),
        provider_id=provider_id,
        model_id=model_id,
    )


def check_canceled(cancel_event) -> bool:
    return bool(cancel_event is not None and cancel_event.is_set())
