"""Network-aware model defaulting tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from backend.model_catalog import LOCAL_MODEL_ID, LOCAL_PROVIDER_ID
from backend.network import clear_network_cache, network_available
from backend.providers.session_llm import resolve_active_selection


class NetworkProbeTests(unittest.TestCase):
    def setUp(self):
        clear_network_cache()

    def tearDown(self):
        clear_network_cache()

    def test_env_override_offline(self):
        with patch.dict("os.environ", {"MARVIN_NETWORK_AVAILABLE": "0"}):
            self.assertFalse(network_available())

    def test_env_override_online(self):
        with patch.dict("os.environ", {"MARVIN_NETWORK_AVAILABLE": "1"}):
            self.assertTrue(network_available())

    def test_cache_skips_second_probe(self):
        calls = {"n": 0}

        def fake_connect(*_args, **_kwargs):
            calls["n"] += 1
            return MagicMock(
                __enter__=lambda s: s,
                __exit__=lambda *_a: False,
            )

        with patch.dict("os.environ", {}, clear=False):
            # Ensure override is unset for this test.
            import os

            os.environ.pop("MARVIN_NETWORK_AVAILABLE", None)
            clear_network_cache()
            with patch("backend.network.socket.create_connection", side_effect=fake_connect):
                self.assertTrue(network_available(force=True))
                self.assertTrue(network_available())
            self.assertEqual(calls["n"], 1)


class ResolveNetworkAwareTests(unittest.TestCase):
    def setUp(self):
        clear_network_cache()

    def tearDown(self):
        clear_network_cache()

    def _settings(self, **kwargs):
        base = dict(
            selected_provider=None,
            selected_model=None,
            pending_provider=None,
            pending_model=None,
            default_models={},
            last_cloud_provider=None,
            last_cloud_model=None,
        )
        base.update(kwargs)
        return SimpleNamespace(**base)

    def test_offline_forces_local_despite_last_cloud(self):
        with patch(
            "backend.providers.session_llm.load_ai_provider_settings",
            return_value=self._settings(
                selected_provider="openai",
                selected_model="gpt-5.6-sol",
                last_cloud_provider="openai",
                last_cloud_model="gpt-5.6-sol",
            ),
        ), patch(
            "backend.providers.session_llm.get_credential_store"
        ) as store, patch(
            "backend.network.network_available",
            return_value=False,
        ):
            store.return_value.is_configured.return_value = True
            provider, model = resolve_active_selection()
        self.assertEqual(provider, LOCAL_PROVIDER_ID)
        self.assertEqual(model, LOCAL_MODEL_ID)

    def test_online_prefers_last_cloud(self):
        with patch(
            "backend.providers.session_llm.load_ai_provider_settings",
            return_value=self._settings(
                selected_provider=None,
                selected_model=None,
                last_cloud_provider="xai",
                last_cloud_model="grok-4.5",
            ),
        ), patch(
            "backend.providers.session_llm.get_credential_store"
        ) as store, patch(
            "backend.network.network_available",
            return_value=True,
        ), patch(
            "backend.model_catalog.find_model",
            return_value=SimpleNamespace(model_id="grok-4.5"),
        ):
            store.return_value.is_configured.return_value = True
            provider, model = resolve_active_selection()
        self.assertEqual(provider, "xai")
        self.assertEqual(model, "grok-4.5")

    def test_online_explicit_local_stays_sticky(self):
        with patch(
            "backend.providers.session_llm.load_ai_provider_settings",
            return_value=self._settings(
                selected_provider="local",
                selected_model="qwen3-4b-instruct",
                last_cloud_provider="openai",
                last_cloud_model="gpt-5.6-sol",
            ),
        ), patch(
            "backend.providers.session_llm.get_credential_store"
        ) as store, patch(
            "backend.network.network_available",
            return_value=True,
        ):
            store.return_value.is_configured.return_value = True
            provider, model = resolve_active_selection()
        self.assertEqual(provider, LOCAL_PROVIDER_ID)
        self.assertEqual(model, "qwen3-4b-instruct")

    def test_select_cloud_persists_last_cloud(self):
        from backend import ai_settings
        from backend.provider_service import select_model

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ai_provider_settings.json"
            with patch.object(ai_settings, "_SETTINGS_PATH", path), patch(
                "backend.provider_service.get_credential_store"
            ) as store, patch(
                "backend.provider_service.providers_status",
                return_value={"ok": True},
            ):
                store.return_value.is_configured.return_value = True
                select_model("openai", "gpt-5.6-sol")
                loaded = ai_settings.load_ai_provider_settings()
            self.assertEqual(loaded.selected_provider, "openai")
            self.assertEqual(loaded.selected_model, "gpt-5.6-sol")
            self.assertEqual(loaded.last_cloud_provider, "openai")
            self.assertEqual(loaded.last_cloud_model, "gpt-5.6-sol")

    def test_providers_status_exposes_network(self):
        from backend.provider_service import providers_status

        with patch(
            "backend.provider_service.get_credential_store"
        ) as store, patch(
            "backend.provider_service.load_ai_provider_settings",
            return_value=self._settings(selected_provider="local"),
        ), patch(
            "backend.network.network_available",
            return_value=False,
        ), patch(
            "backend.provider_service.resolve_active_selection",
            return_value=(LOCAL_PROVIDER_ID, LOCAL_MODEL_ID),
        ):
            store.return_value.is_configured.return_value = False
            status = providers_status()
        self.assertFalse(status["network_available"])
        self.assertEqual(status["selected_provider"], "local")


if __name__ == "__main__":
    unittest.main()
