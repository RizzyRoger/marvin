"""Reply scrubber removes leaked tool-call fragments."""

from __future__ import annotations

import unittest

from backend.pipeline.reply_scrub import scrub_tool_call_leakage
from backend.tools import obsidian as obsidian_tools


class ReplyScrubTests(unittest.TestCase):
    def test_strips_moncall_and_tool_name(self):
        self.assertEqual(
            scrub_tool_call_leakage(
                "I'll find today's tutoring task and mark it complete. moncall"
            ),
            "I'll find today's tutoring task and mark it complete.",
        )
        self.assertEqual(
            scrub_tool_call_leakage(
                "I'll mark tutoring complete in your vault. "
                "mon0 rounda find_incomplete_tasks"
            ),
            "I'll mark tutoring complete in your vault.",
        )

    def test_strips_xml_tool_call_markers(self):
        text = 'Done. <tool_call>{"name":"edit_note"}</tool_call>'
        self.assertEqual(scrub_tool_call_leakage(text), "Done.")

    def test_strips_monadsoblivious_mid_string(self):
        raw = (
            "I'll find today's daily note and check off the arms workout. "
            "monadsobliviousChecking off workout arms on today's note. "
            "monadsobliviousChecked off workout arms on today’s note."
        )
        cleaned = scrub_tool_call_leakage(raw)
        self.assertNotIn("monadsoblivious", cleaned.lower())
        self.assertIn("Checked off workout arms", cleaned)
        self.assertNotIn("I'll find today's daily note", cleaned)


class TaskWriteIntentTests(unittest.TestCase):
    def setUp(self):
        obsidian_tools.clear_pending_write()

    def tearDown(self):
        obsidian_tools.clear_pending_write()

    def test_check_off_grants_write_without_obsidian_word(self):
        self.assertTrue(obsidian_tools.user_grants_write("check off tutoring"))
        self.assertTrue(obsidian_tools.user_grants_write("check it off"))
        self.assertTrue(
            obsidian_tools.user_grants_write("mark tutoring as complete")
        )
        self.assertTrue(obsidian_tools.explicit_vault_intent("check off tutoring"))

    def test_prompt_912_check_off_and_authorise_grant_write(self):
        phrase = "Use obsidian to check off precalc hw and bio hw"
        self.assertTrue(obsidian_tools.user_grants_write(phrase))
        self.assertTrue(obsidian_tools.user_grants_write("I authorise"))
        self.assertTrue(obsidian_tools.user_grants_write("I authorize"))
        self.assertTrue(obsidian_tools.user_grants_write("use the write tool"))
        self.assertIsNone(obsidian_tools.prefetch_read_request(phrase))

    def test_review_and_summarize_stay_read_only(self):
        self.assertFalse(obsidian_tools.user_grants_write("review my daily note"))
        self.assertFalse(obsidian_tools.user_grants_write("summarize my daily note"))
        self.assertFalse(obsidian_tools.user_grants_write("what's on my list"))
        self.assertFalse(obsidian_tools.user_grants_write("check my note"))
        self.assertIsNotNone(obsidian_tools.prefetch_read_request("review my daily note"))

    def test_follow_up_authorise_uses_pending_check_off(self):
        obsidian_tools.remember_write_turn(
            "Use obsidian to check off precalc hw and bio hw"
        )
        self.assertTrue(obsidian_tools.user_grants_write("I authorise"))
        self.assertTrue(obsidian_tools.user_grants_write("yes"))
        self.assertEqual(
            obsidian_tools._extract_task_query(
                obsidian_tools.effective_write_message("I authorise")
            ),
            "precalc hw and bio hw",
        )
        names = {
            t["function"]["name"]
            for t in obsidian_tools.tools_for_request("I authorise")
        }
        self.assertIn("complete_task", names)

    def test_unrelated_follow_up_clears_pending_write(self):
        obsidian_tools.remember_write_turn("check off tutoring")
        obsidian_tools.remember_write_turn("what's the weather")
        self.assertFalse(obsidian_tools.user_grants_write("yes"))

    def test_deferred_write_catches_mark_complete_promises(self):
        self.assertTrue(
            obsidian_tools.looks_like_deferred_write(
                "I'll find today's tutoring task and mark it complete."
            )
        )
        self.assertTrue(
            obsidian_tools.looks_like_deferred_write(
                "I'll mark tutoring complete in your vault."
            )
        )
        self.assertTrue(
            obsidian_tools.looks_like_invented_write_claim(
                "Checked off workout arms on today’s note."
            )
        )


class CompleteTaskTests(unittest.TestCase):
    def test_complete_task_toggles_checkbox(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            daily = vault / "daily notes"
            daily.mkdir()
            note = daily / "2026-08-19.md"
            note.write_text(
                "# Today\n\n- [ ] cancel subscription\n- [ ] workout arms\n- [x] done already\n",
                encoding="utf-8",
            )
            with (
                patch.object(obsidian_tools, "VAULT_ROOT", vault),
                patch.object(
                    obsidian_tools,
                    "resolve_daily_note",
                    return_value={
                        "status": "found",
                        "path": "daily notes/2026-08-19.md",
                        "date": "2026-08-19",
                    },
                ),
            ):
                result = obsidian_tools.complete_task(
                    "arms workout",
                    authorized=True,
                    user_authorized=True,
                )
            self.assertTrue(result.startswith("OK:"), result)
            body = note.read_text(encoding="utf-8")
            self.assertIn("- [x] workout arms", body)
            self.assertIn("- [ ] cancel subscription", body)
            self.assertNotIn("- [ ] workout arms", body)

    def test_tools_for_check_off_include_complete_task(self):
        names = {
            t["function"]["name"]
            for t in obsidian_tools.tools_for_request("check off workout arms")
        }
        self.assertIn("complete_task", names)
        self.assertIn("find_incomplete_tasks", names)

    def test_complete_task_checks_off_two_homework_items(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            daily = vault / "daily notes"
            daily.mkdir()
            note = daily / "2026-08-19.md"
            note.write_text(
                "# Today\n\n- [ ] precalc hw\n- [ ] bio hw\n- [ ] unrelated\n",
                encoding="utf-8",
            )
            with (
                patch.object(obsidian_tools, "VAULT_ROOT", vault),
                patch.object(
                    obsidian_tools,
                    "resolve_daily_note",
                    return_value={
                        "status": "found",
                        "path": "daily notes/2026-08-19.md",
                        "date": "2026-08-19",
                    },
                ),
            ):
                result = obsidian_tools.complete_task(
                    "precalc hw and bio hw",
                    authorized=True,
                    user_authorized=True,
                )
            self.assertTrue(result.startswith("OK:"), result)
            body = note.read_text(encoding="utf-8")
            self.assertIn("- [x] precalc hw", body)
            self.assertIn("- [x] bio hw", body)
            self.assertIn("- [ ] unrelated", body)


if __name__ == "__main__":
    unittest.main()
