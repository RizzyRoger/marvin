"""Shared PromptBuilder — identical Marvin instructions for every provider."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from backend.config import LLM_CHAT_MAX_TOKENS, SYSTEM_PROMPTS
from backend.providers.types import AgentRequest


@dataclass(frozen=True)
class BuiltPrompt:
    system_prompt: str
    runtime_context: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    system_prompt_hash: str


class PromptBuilder:
    """Build one canonical Marvin request shared by all provider adapters."""

    @staticmethod
    def canonical_system_prompt() -> str:
        return SYSTEM_PROMPTS["chat"]

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def build(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        runtime_context: str = "",
        system_prompt: str | None = None,
        provider_id: str,
        model_id: str,
        temperature: float = 0.7,
        top_p: float = 0.9,
        max_tokens: int = LLM_CHAT_MAX_TOKENS,
        session_id: str = "",
        turn_id: str = "",
        generation_id: str = "",
        force_tool_use: bool = False,
        cancellation_event: Any = None,
        prompt_suffix: str = "",
    ) -> tuple[AgentRequest, BuiltPrompt]:
        base = system_prompt if system_prompt is not None else self.canonical_system_prompt()
        if prompt_suffix:
            base = base + prompt_suffix
        built = BuiltPrompt(
            system_prompt=base,
            runtime_context=runtime_context or "",
            messages=list(messages),
            tools=list(tools or []),
            system_prompt_hash=self.hash_text(base),
        )
        request = AgentRequest(
            system_prompt=built.system_prompt,
            runtime_context=built.runtime_context,
            messages=built.messages,
            tools=built.tools,
            provider_id=provider_id,
            model_id=model_id,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
            session_id=session_id,
            turn_id=turn_id,
            generation_id=generation_id,
            force_tool_use=force_tool_use,
            cancellation_event=cancellation_event,
        )
        return request, built
