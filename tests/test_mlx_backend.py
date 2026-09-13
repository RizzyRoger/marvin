"""MLX/local Qwen routing and textual tool-call fallback."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from backend.pipeline.llm import QwenLLM, mlx_weights_ready, should_use_mlx


class FakeModel:
    def __init__(self, reply: str = "Hello from llama."):
        self.reply = reply
        self.calls: list[dict] = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "choices": [{"message": {"content": self.reply}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2},
        }


class MlxBackendTests(unittest.TestCase):
    def test_mlx_weights_ready_requires_config_or_safetensors(self):
        self.assertFalse(mlx_weights_ready(Path("/tmp/marvin-missing-mlx")))

    def test_should_use_mlx_false_on_non_apple_silicon(self):
        with patch("backend.pipeline.llm.platform.system", return_value="Linux"):
            self.assertFalse(should_use_mlx())

    def test_should_use_mlx_false_without_weights(self):
        with patch("backend.pipeline.llm.platform.system", return_value="Darwin"):
            with patch("backend.pipeline.llm.platform.machine", return_value="arm64"):
                with patch("backend.pipeline.llm.mlx_weights_ready", return_value=False):
                    self.assertFalse(should_use_mlx())

    def test_complete_uses_injected_fake_model(self):
        llm = object.__new__(QwenLLM)
        llm._model = FakeModel("ok")
        llm._backend = "none"
        llm._mlx_model = None
        response = llm._complete(messages=[{"role": "user", "content": "hi"}])
        self.assertEqual(response["choices"][0]["message"]["content"], "ok")
        self.assertEqual(len(llm._model.calls), 1)

    def test_textual_tool_calls_still_parse_for_vault_turns(self):
        llm = object.__new__(QwenLLM)
        calls = llm._extract_text_tool_calls(
            '<tool_call>{"name":"search_notes","arguments":{"query":"garden"}}'
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "search_notes")
        self.assertIn("garden", calls[0]["function"]["arguments"])

    def test_chat_with_tools_reads_textual_tool_calls(self):
        llm = object.__new__(QwenLLM)
        llm._history = []
        llm.last_metrics = {}

        class ToolThenText(FakeModel):
            def create_chat_completion(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": (
                                        '<tool_call>{"name":"search_notes",'
                                        '"arguments":{"query":"ledger"}}'
                                    )
                                }
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                    }
                return {
                    "choices": [{"message": {"content": "Found the ledger."}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1},
                }

        llm._model = ToolThenText()
        executed: list[str] = []

        def execute(name, args, _user):
            executed.append(name)
            return f"OK: {args.get('query')}"

        reply = llm.chat_with_tools(
            "find ledger",
            "System",
            [{"type": "function", "function": {"name": "search_notes"}}],
            execute,
        )
        self.assertEqual(executed, ["search_notes"])
        self.assertIn("ledger", reply.lower())
