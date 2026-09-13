"""Provider-neutral LLM types for Marvin."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class StreamEventType(str, Enum):
    TEXT_DELTA = "text_delta"
    TOOL_CALL_STARTED = "tool_call_started"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_COMPLETED = "tool_call_completed"
    USAGE = "usage"
    RESPONSE_COMPLETED = "response_completed"
    RESPONSE_CANCELED = "response_canceled"
    PROVIDER_ERROR = "provider_error"


@dataclass(frozen=True)
class ModelDefinition:
    provider_id: str
    model_id: str
    display_name: str
    supports_streaming: bool = True
    supports_tool_calls: bool = True
    enabled: bool = True
    recommended: bool = False
    deprecated: bool = False


@dataclass
class AgentRequest:
    system_prompt: str
    runtime_context: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    provider_id: str
    model_id: str
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 256
    session_id: str = ""
    turn_id: str = ""
    generation_id: str = ""
    force_tool_use: bool = False
    cancellation_event: Any = None


@dataclass
class StreamEvent:
    type: StreamEventType
    text: str = ""
    tool_name: str = ""
    tool_call_id: str = ""
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    error_code: str = ""
    error_message: str = ""
    provider_id: str = ""
    model_id: str = ""


class ProviderErrorCode(str, Enum):
    NOT_CONFIGURED = "provider_not_configured"
    INVALID_API_KEY = "invalid_api_key"
    KEY_REVOKED = "key_revoked"
    MODEL_UNAVAILABLE = "model_unavailable"
    RATE_LIMITED = "rate_limited"
    QUOTA_EXHAUSTED = "quota_exhausted"
    TIMEOUT = "request_timeout"
    NETWORK = "network_unavailable"
    OUTAGE = "provider_outage"
    MALFORMED = "malformed_response"
    TOOL_INCOMPATIBLE = "tool_call_incompatibility"
    CANCELED = "user_cancellation"
    UNKNOWN = "unknown"


class ProviderError(Exception):
    def __init__(
        self,
        code: ProviderErrorCode | str,
        message: str,
        *,
        provider_id: str = "",
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.code = code.value if isinstance(code, ProviderErrorCode) else str(code)
        self.message = message
        self.provider_id = provider_id
        self.status_code = status_code

    def user_message(self) -> str:
        return self.message
