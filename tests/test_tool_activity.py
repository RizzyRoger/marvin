"""Turn-scoped sidebar tool activity."""

from __future__ import annotations

import unittest

from unittest.mock import MagicMock, patch

from backend.agent import MarvinAgent


class ToolActivityTests(unittest.TestCase):
    def setUp(self):
        self.events: list[tuple[str, dict]] = []
        self.agent = MarvinAgent(on_status=lambda status, data: self.events.append((status, data)))

    def test_fresh_payload_is_empty(self):
        payload = self.agent._tool_activity_payload()
        self.assertEqual(payload["functions_used"], [])
        self.assertEqual(payload["sticky_tools"], [])
        self.assertEqual(payload["active_tools"], [])

    def test_set_function_does_not_light_sidebar(self):
        self.assertTrue(self.agent.set_function("obsidian"))
        payload = self.agent._tool_activity_payload()
        self.assertEqual(payload["functions_used"], [])
        self.assertEqual(payload["sticky_tools"], [])

    def test_begin_tool_lights_obsidian_and_drops_chat(self):
        call_id = self.agent.begin_tool(1, "read_best_note")
        payload = self.agent._tool_activity_payload()
        self.assertEqual(payload["functions_used"], ["obsidian"])
        self.assertEqual(payload["sticky_tools"], ["obsidian"])
        self.assertEqual(payload["active_tools"], ["obsidian"])
        self.assertTrue(call_id.startswith("obsidian-"))
        self.assertNotIn("chat", payload["functions_used"])

        self.agent.finish_tool(call_id, 1)
        done = self.agent._tool_activity_payload()
        self.assertEqual(done["active_tools"], [])
        self.assertEqual(done["sticky_tools"], ["obsidian"])

    def test_prefetch_marks_obsidian(self):
        self.agent._mark_tools_used("prefetch_read_request")
        self.assertEqual(self.agent._tool_activity_payload()["functions_used"], ["obsidian"])

    def test_next_turn_replaces_list(self):
        self.agent.begin_tool(1, "read_note")
        self.agent.clear_used_tools()
        self.assertEqual(self.agent._tool_activity_payload()["functions_used"], [])
        self.agent.begin_tool(2, "switch_model")
        self.assertEqual(self.agent._tool_activity_payload()["functions_used"], ["ai_model"])

    def test_tracked_executor_wraps_success_and_failure(self):
        def ok(name, arguments, user_message=""):
            return f"OK:{name}"

        def boom(name, arguments, user_message=""):
            raise RuntimeError("nope")

        wrapped = self.agent._tracked_tool_executor(ok)
        self.assertEqual(wrapped("search_notes", {}, "find it"), "OK:search_notes")
        self.assertEqual(self.agent._tool_activity_payload()["sticky_tools"], ["obsidian"])
        self.assertEqual(self.agent._tool_activity_payload()["active_tools"], [])

        self.agent.clear_used_tools()
        failing = self.agent._tracked_tool_executor(boom)
        with self.assertRaises(RuntimeError):
            failing("web_search", {}, "search")
        payload = self.agent._tool_activity_payload()
        self.assertEqual(payload["sticky_tools"], ["web_search"])
        self.assertEqual(payload["active_tools"], [])

    def test_emit_includes_activity_arrays(self):
        self.agent._emit("idle", {"ready": True})
        status, data = self.events[-1]
        self.assertEqual(status, "idle")
        self.assertIn("functions_used", data)
        self.assertIn("sticky_tools", data)
        self.assertIn("active_tools", data)

    def _mark_ready(self):
        self.agent._vad = object()
        self.agent._stt = object()
        self.agent._llm = MagicMock()
        self.agent._tts = object()
        self.agent._speaker = object()

    def test_process_text_clears_sidebar_on_new_prompt(self):
        self._mark_ready()
        self.agent.begin_tool(1, "read_note")
        self.assertEqual(self.agent.used_functions, ["obsidian"])
        with patch("backend.storage.chat.append_message", side_effect=lambda *a, **k: {"role": a[0], "content": a[1]}):
            reply = self.agent.process_text("switch to chat mode")
        self.assertIn("Chat", reply)
        self.assertEqual(self.agent._tool_activity_payload()["functions_used"], [])

    def test_prefetch_path_lights_obsidian(self):
        self._mark_ready()
        self.agent._llm.chat_with_context.return_value = "Here is the note."
        with (
            patch("backend.storage.chat.append_message", side_effect=lambda *a, **k: {"role": a[0], "content": a[1]}),
            patch("backend.tools.obsidian.remember_write_turn"),
            patch("backend.tools.obsidian.prefetch_read_request", return_value="note body"),
            patch("backend.tools.obsidian.handle_direct_daily_note_create", return_value=None),
            patch("backend.tools.obsidian.user_grants_write", return_value=False),
            patch("backend.tools.obsidian.is_write_consent_only", return_value=False),
            patch.object(self.agent, "_route_function", return_value=("obsidian", "fast")),
            patch("backend.skills.repeats.try_save_pending_skill", return_value=None),
            patch("backend.skills.repeats.maybe_propose_skill", return_value=None),
        ):
            reply = self.agent.process_text("read my daily note")
        self.assertEqual(reply, "Here is the note.")
        self.assertEqual(self.agent._tool_activity_payload()["functions_used"], ["obsidian"])


if __name__ == "__main__":
    unittest.main()
