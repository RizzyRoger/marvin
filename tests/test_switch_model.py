"""switch_model tool routing and dispatch tests."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from backend import ai_settings
from backend.agent import MarvinAgent
from backend.model_catalog import LOCAL_MODEL_ID, LOCAL_PROVIDER_ID
from backend.tools.ai_model import (
    decide_switch_model,
    dispatch_switch_model,
    tools_for_switch_model,
)


class SwitchModelRoutingTests(unittest.TestCase):
    def test_switch_phrases_required(self):
        for text in (
            "switch to Claude",
            "change to Grok",
            "use ChatGPT",
            "set the model to local Qwen",
            "go back to local",
            "use the openai model",
        ):
            with self.subTest(text=text):
                self.assertTrue(decide_switch_model(text, available=True))

    def test_non_switch_phrases(self):
        for text in (
            "what's the weather",
            "set a timer for 5 minutes",
            "play some music",
            "what is Claude Anthropic",
        ):
            with self.subTest(text=text):
                self.assertFalse(decide_switch_model(text, available=True))

    def test_unavailable(self):
        self.assertFalse(decide_switch_model("switch to Claude", available=False))

    def test_tools_exported(self):
        names = {t["function"]["name"] for t in tools_for_switch_model()}
        self.assertEqual(names, {"switch_model"})


class SwitchModelDispatchTests(unittest.TestCase):
    def test_dispatch_local_defaults_flagship(self):
        with patch(
            "backend.tools.ai_model.select_model",
            return_value={"needs_key": False},
        ) as select, patch(
            "backend.tools.ai_model.network_available",
            return_value=True,
        ):
            msg = dispatch_switch_model(
                "switch_model",
                {"provider_id": "local"},
                "switch to local",
            )
        select.assert_called_once_with(LOCAL_PROVIDER_ID, LOCAL_MODEL_ID)
        self.assertIn("next reply", msg.lower())
        self.assertIn("qwen", msg.lower())

    def test_dispatch_needs_key(self):
        with patch(
            "backend.tools.ai_model.select_model",
            return_value={
                "needs_key": True,
                "focus_provider": "anthropic",
            },
        ), patch(
            "backend.tools.ai_model.network_available",
            return_value=True,
        ):
            msg = dispatch_switch_model(
                "switch_model",
                {"provider_id": "anthropic"},
                "switch to Claude",
            )
        self.assertIn("API key", msg)
        self.assertIn("Settings", msg)

    def test_dispatch_cloud_success(self):
        with patch(
            "backend.tools.ai_model.select_model",
            return_value={"needs_key": False},
        ) as select, patch(
            "backend.tools.ai_model.network_available",
            return_value=True,
        ):
            msg = dispatch_switch_model(
                "switch_model",
                {"provider_id": "xai"},
                "switch to Grok",
            )
        select.assert_called_once_with("xai", "grok-4.5")
        self.assertIn("next reply", msg.lower())
        self.assertIn("Grok", msg)

    def test_dispatch_offline_cloud_saves(self):
        with patch(
            "backend.tools.ai_model.select_model",
            return_value={"needs_key": False},
        ), patch(
            "backend.tools.ai_model.network_available",
            return_value=False,
        ):
            msg = dispatch_switch_model(
                "switch_model",
                {"provider_id": "openai"},
                "use ChatGPT",
            )
        self.assertIn("online", msg.lower())
        self.assertIn("Qwen", msg)

    def test_dispatch_unknown_provider(self):
        msg = dispatch_switch_model(
            "switch_model",
            {"provider_id": "nope"},
            "switch",
        )
        self.assertIn("provider", msg.lower())

    def test_cancel(self):
        ev = threading.Event()
        ev.set()
        msg = dispatch_switch_model(
            "switch_model",
            {"provider_id": "local"},
            "switch",
            cancellation_event=ev,
        )
        self.assertIn("canceled", msg.lower())


class SwitchModelAgentWiringTests(unittest.TestCase):
    def test_normalize_switch_activity(self):
        agent = object.__new__(MarvinAgent)
        self.assertEqual(
            agent._normalize_tool_activity_name("switch_model"),
            "ai_model",
        )

    def test_functions_includes_ai_model(self):
        from backend.config import FUNCTIONS

        ids = {f["id"] for f in FUNCTIONS}
        self.assertIn("ai_model", ids)

    def test_local_select_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_provider_settings.json"
            with patch.object(ai_settings, "_SETTINGS_PATH", path), patch(
                "backend.provider_service.get_credential_store"
            ) as mock_store, patch(
                "backend.provider_service.providers_status",
                return_value={"ok": True},
            ), patch(
                "backend.tools.ai_model.network_available",
                return_value=True,
            ):
                store = MagicMock()
                store.is_configured.return_value = True
                mock_store.return_value = store
                msg = dispatch_switch_model(
                    "switch_model",
                    {"provider_id": "qwen"},
                    "use qwen",
                )
                loaded = ai_settings.load_ai_provider_settings()
            self.assertEqual(loaded.selected_provider, LOCAL_PROVIDER_ID)
            self.assertEqual(loaded.selected_model, LOCAL_MODEL_ID)
            self.assertIn("next reply", msg.lower())


if __name__ == "__main__":
    unittest.main()
