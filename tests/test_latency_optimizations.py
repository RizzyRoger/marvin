"""Focused regression tests for latency-sensitive request paths."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from backend.pipeline.llm import QwenLLM
from backend.config import VAD_MIN_SILENCE_MS
from backend.tools import obsidian


class FakeModel:
    def __init__(self, reply: str = "Done."):
        self.reply = reply
        self.calls: list[dict] = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "choices": [{"message": {"content": self.reply}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 5},
        }


class LatencyOptimizationTests(unittest.TestCase):
    def test_vad_allows_natural_mid_sentence_pauses(self):
        self.assertGreaterEqual(VAD_MIN_SILENCE_MS, 1000)

    def test_prefetched_context_uses_one_model_call(self):
        llm = object.__new__(QwenLLM)
        llm._model = FakeModel()
        llm._history = []
        llm.last_metrics = {}

        reply = llm.chat_with_context(
            "Summarize my daily note.",
            "Use vault evidence.",
            "# daily notes/2026-07-15.md\n\nTask one.",
        )

        self.assertEqual(reply, "Done.")
        self.assertEqual(len(llm._model.calls), 1)
        self.assertEqual(llm.last_metrics["model_calls"], 1)
        self.assertEqual(llm.last_metrics["tool_calls"], 1)

    def test_history_is_bounded_to_three_recent_turns(self):
        llm = object.__new__(QwenLLM)
        llm._model = FakeModel()
        llm._history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": str(i)}
            for i in range(20)
        ]
        llm.last_metrics = {}

        llm.chat("Current request", "System")

        sent_messages = llm._model.calls[0]["messages"]
        self.assertEqual(len(sent_messages), 8)  # system + six history + user
        self.assertEqual(sent_messages[1]["content"], "14")

    def test_write_requests_receive_only_relevant_tool_schemas(self):
        names = {
            tool["function"]["name"]
            for tool in obsidian.tools_for_request("Add a task to my daily note")
        }
        self.assertEqual(names, {"read_best_note", "read_note", "edit_note"})

    def test_common_read_is_prefetched_and_content_is_cached(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            note = vault / "CogSci" / "1.1 - What is Cognitive Science About?.md"
            note.parent.mkdir()
            note.write_text("# Cognitive Science\nAn interdisciplinary field.")

            with patch.object(obsidian, "VAULT_ROOT", vault):
                obsidian._invalidate_note_cache()
                context = obsidian.prefetch_read_request(
                    "Summarize my cognitive science unit 1.1."
                )
                obsidian._invalidate_note_cache()
                first, first_hit = obsidian._read_cached_note(note)
                second, second_hit = obsidian._read_cached_note(note)

            self.assertIn("1.1 - What is Cognitive Science About?.md", context)
            self.assertEqual(first, second)
            self.assertFalse(first_hit)
            self.assertTrue(second_hit)

    def test_simple_tomorrow_note_uses_canonical_date_without_old_context(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            tomorrow = (date.today() + timedelta(days=1)).isoformat()
            with patch.object(obsidian, "VAULT_ROOT", vault):
                obsidian._invalidate_note_cache()
                reply = obsidian.handle_direct_daily_note_create(
                    "Marvin, create a note for tomorrow."
                )
                target = vault / "daily notes" / f"{tomorrow}.md"

            self.assertTrue(target.exists())
            self.assertIn(f"daily notes/{tomorrow}.md", reply)
            self.assertNotIn("behaviorism", target.read_text().lower())

    def test_standalone_create_excludes_unrelated_history(self):
        class CreateModel(FakeModel):
            def create_chat_completion(self, **kwargs):
                self.calls.append(kwargs)
                if len(self.calls) == 1:
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": (
                                        '<tool_call>{"name":"create_daily_note",'
                                        '"arguments":{"day":"tomorrow",'
                                        '"authorized":true}}</tool_call>'
                                    )
                                }
                            }
                        ],
                        "usage": {},
                    }
                return {
                    "choices": [{"message": {"content": "Created."}}],
                    "usage": {},
                }

        llm = object.__new__(QwenLLM)
        llm._model = CreateModel()
        llm._history = [
            {"role": "user", "content": "Tell me about behaviorism."},
            {"role": "assistant", "content": "Behaviorism focuses on behavior."},
        ]
        llm.last_metrics = {}
        llm.chat_with_tools(
            "Create a daily note for tomorrow.",
            "Use tools.",
            [],
            lambda *_args: "OK: created daily notes/tomorrow.md",
            requires_successful_write=True,
        )

        first_messages = llm._model.calls[0]["messages"]
        contents = [message["content"] for message in first_messages]
        self.assertEqual(contents[:2], ["Use tools.", "Create a daily note for tomorrow."])
        self.assertNotIn("behaviorism", " ".join(contents).lower())

    def test_explicit_edit_reaches_disk(self):
        with tempfile.TemporaryDirectory() as temp:
            vault = Path(temp)
            note = vault / "daily notes" / "test.md"
            note.parent.mkdir()
            note.write_text("# Test\n")
            with patch.object(obsidian, "VAULT_ROOT", vault):
                result = obsidian.dispatch_tool(
                    "edit_note",
                    {
                        "path": "daily notes/test.md",
                        "new_content": "- [ ] Work out",
                        "mode": "append",
                        "authorized": True,
                    },
                    "Add a workout task to my daily note.",
                )

            self.assertTrue(result.startswith("OK:"))
            self.assertIn("Work out", note.read_text())

    def test_failed_write_cannot_be_reported_as_complete(self):
        llm = object.__new__(QwenLLM)
        llm._model = FakeModel("Edit complete.")
        llm._history = []
        llm.last_metrics = {}

        reply = llm.chat_with_tools(
            "Edit my daily note.",
            "Use tools.",
            [],
            lambda *_args: "REFUSED: no write",
            requires_successful_write=True,
        )

        self.assertEqual(
            reply,
            "I did not change the note because no authorized write completed.",
        )


if __name__ == "__main__":
    unittest.main()
