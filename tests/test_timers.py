"""Countdown timer store, routing, and dispatch tests."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.agent import MarvinAgent
from backend.reminders import (
    TimerError,
    adjust_timer,
    cancel_timer,
    humanize_duration,
    list_pending_timers,
    pause_timer,
    resume_timer,
    start_timer,
)
from backend.tools.timers import (
    decide_timer,
    dispatch_timer_tool,
    tools_for_timers,
)


class TimerStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._path = Path(self._tmp.name) / "reminders.json"
        self._patcher = patch("backend.reminders._STORE_PATH", self._path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        # Avoid starting a long-lived scheduler thread in unit tests.
        self._sched = patch("backend.reminders._ensure_scheduler")
        self._sched.start()
        self.addCleanup(self._sched.stop)

    def test_humanize_and_default_name(self):
        self.assertEqual(humanize_duration(300), "5 minutes")
        self.assertEqual(humanize_duration(1), "1 second")
        self.assertEqual(humanize_duration(3600), "1 hour")

    def test_start_defaults_name_to_duration(self):
        item = start_timer(None, 120)
        self.assertEqual(item.kind, "timer")
        self.assertEqual(item.name, "2 minutes")
        pending = list_pending_timers()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["name"], "2 minutes")

    def test_pause_resume_and_adjust(self):
        item = start_timer("egg", 60)
        paused = pause_timer("egg")
        self.assertTrue(paused.paused)
        self.assertGreaterEqual(paused.remaining_seconds or 0, 1)
        before = float(paused.remaining_seconds or 0)
        adjusted = adjust_timer("egg", 30)
        self.assertTrue(adjusted.paused)
        self.assertAlmostEqual(
            float(adjusted.remaining_seconds or 0), before + 30, delta=1.5
        )
        resumed = resume_timer(item.id)
        self.assertFalse(resumed.paused)
        self.assertIsNone(resumed.remaining_seconds)
        self.assertGreater(resumed.fire_at, time.time())
        running = adjust_timer("egg", -15)
        self.assertFalse(running.paused)
        cancel_timer("egg")
        self.assertEqual(list_pending_timers(), [])

    def test_cancel_missing_raises(self):
        with self.assertRaises(TimerError):
            cancel_timer("missing")


class TimerRoutingTests(unittest.TestCase):
    def test_timer_phrases_required(self):
        for text in (
            "set a timer for 10 minutes",
            "start a timer for 30 seconds",
            "cancel the timer",
            "pause my timer",
            "resume the timer",
            "add 2 minutes to the timer",
        ):
            with self.subTest(text=text):
                self.assertTrue(decide_timer(text, available=True))

    def test_remind_me_not_timer(self):
        self.assertFalse(
            decide_timer("remind me to stretch in 10 minutes", available=True)
        )

    def test_tools_exported(self):
        names = {t["function"]["name"] for t in tools_for_timers()}
        self.assertEqual(
            names,
            {"timer_start", "timer_cancel", "timer_adjust", "timer_pause"},
        )


class TimerDispatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._path = Path(self._tmp.name) / "reminders.json"
        self._patcher = patch("backend.reminders._STORE_PATH", self._path)
        self._patcher.start()
        self.addCleanup(self._patcher.stop)
        self._sched = patch("backend.reminders._ensure_scheduler")
        self._sched.start()
        self.addCleanup(self._sched.stop)

    def test_dispatch_start_cancel(self):
        started = dispatch_timer_tool(
            "timer_start",
            {"duration_seconds": 90, "name": "tea"},
            "set a tea timer for 90 seconds",
        )
        self.assertIn("tea", started.lower())
        canceled = dispatch_timer_tool(
            "timer_cancel",
            {"name": "tea"},
            "cancel the tea timer",
        )
        self.assertIn("canceled", canceled.lower())


class TimerAgentWiringTests(unittest.TestCase):
    def test_normalize_timer_activity(self):
        agent = object.__new__(MarvinAgent)
        self.assertEqual(
            agent._normalize_tool_activity_name("timer_start"),
            "timers",
        )
        self.assertEqual(
            agent._normalize_tool_activity_name("timer_pause"),
            "timers",
        )

    def test_functions_includes_timers(self):
        from backend.config import FUNCTIONS

        ids = {f["id"] for f in FUNCTIONS}
        self.assertIn("timers", ids)


if __name__ == "__main__":
    unittest.main()
