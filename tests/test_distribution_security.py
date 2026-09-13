"""Distribution security: auth, vault setup, model manifest, python gate."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


class LocalAuthTests(unittest.TestCase):
    def test_auth_enabled_in_bundle(self):
        from backend.local_auth import auth_enabled

        with patch.dict(os.environ, {"MARVIN_BUNDLE": "1"}, clear=False):
            os.environ.pop("MARVIN_REQUIRE_AUTH", None)
            self.assertTrue(auth_enabled())

    def test_auth_disabled_in_dev(self):
        from backend.local_auth import auth_enabled

        with patch.dict(
            os.environ,
            {"MARVIN_BUNDLE": "0", "MARVIN_REQUIRE_AUTH": "0"},
            clear=False,
        ):
            self.assertFalse(auth_enabled())

    def test_token_roundtrip_memory(self):
        from backend import local_auth

        local_auth._memory_token = None
        with patch.dict(os.environ, {"MARVIN_API_TOKEN": "test-token-value"}, clear=False):
            self.assertEqual(local_auth.get_or_create_token(), "test-token-value")
            self.assertTrue(local_auth.token_matches("test-token-value"))
            self.assertFalse(local_auth.token_matches("nope"))
        local_auth._memory_token = None

    def test_bundle_rejects_unauthenticated_api(self):
        with patch.dict(
            os.environ,
            {
                "MARVIN_BUNDLE": "1",
                "MARVIN_REQUIRE_AUTH": "1",
                "MARVIN_API_TOKEN": "unit-test-token",
            },
            clear=False,
        ):
            # Re-import app with auth on
            import importlib

            import backend.local_auth as la
            import backend.main as main_mod

            la._memory_token = None
            importlib.reload(main_mod)
            client = TestClient(main_mod.app)
            denied = client.get("/api/chat/history")
            self.assertEqual(denied.status_code, 401)
            ok = client.get(
                "/api/chat/history",
                headers={"X-Marvin-Token": "unit-test-token"},
            )
            self.assertEqual(ok.status_code, 200)
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertIsNone(main_mod.app.docs_url)
            la._memory_token = None


class VaultBundleTests(unittest.TestCase):
    def test_bundle_no_autodetect(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / "data"
            data.mkdir()
            with patch.dict(
                os.environ,
                {
                    "MARVIN_BUNDLE": "1",
                    "MARVIN_DATA_DIR": str(data),
                    "MARVIN_ROOT": tmp,
                },
                clear=False,
            ):
                os.environ.pop("MARVIN_VAULT_ROOT", None)
                from backend import config

                # Call resolver with explicit root; prefs empty → empty Path in bundle.
                resolved = config.resolve_vault_root(Path(tmp))
                self.assertEqual(resolved, Path())


class ModelManifestTests(unittest.TestCase):
    def test_verify_missing(self):
        from backend.model_manifest import verify_models

        with tempfile.TemporaryDirectory() as tmp:
            problems = verify_models(Path(tmp))
            self.assertTrue(any("missing" in p for p in problems))

    def test_verify_size_ok(self):
        from backend.model_manifest import MODEL_MIN_SIZES, verify_models

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rel = "silero-vad/hubconf.py"
            path = root / rel
            path.parent.mkdir(parents=True)
            path.write_text("# hub\n" + ("x" * MODEL_MIN_SIZES[rel]), encoding="utf-8")
            problems = verify_models(root, required=[rel])
            self.assertEqual(problems, [])


class PythonRunnerGateTests(unittest.TestCase):
    def test_disabled_in_bundle(self):
        with patch.dict(os.environ, {"MARVIN_BUNDLE": "1"}, clear=False):
            os.environ.pop("MARVIN_ALLOW_PYTHON", None)
            import importlib

            import backend.config as cfg
            import backend.tools.python_runner as pr

            importlib.reload(cfg)
            importlib.reload(pr)
            self.assertFalse(pr.register_python_capability())
            msg = pr.dispatch_python_tool(
                "run_python",
                {"code": "print(1)", "authorized": True},
                "run this python",
            )
            self.assertIn("disabled", msg.lower())


class ProcessGuardTests(unittest.TestCase):
    def test_pid_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("backend.process_guard.PID_PATH", Path(tmp) / "marvin.pid"):
                from backend.process_guard import (
                    clear_pid_file,
                    read_pid_file,
                    write_pid_file,
                )

                write_pid_file(12345)
                self.assertEqual(read_pid_file(), 12345)
                clear_pid_file()
                self.assertIsNone(read_pid_file())


class PackagingScriptsTests(unittest.TestCase):
    def test_scripts_exist(self):
        root = Path(__file__).resolve().parents[1]
        for name in (
            "scripts/release_build.sh",
            "scripts/sign_and_notarize.sh",
            "scripts/create_dmg.sh",
            "scripts/lock_requirements.sh",
            "scripts/entitlements.plist",
            "SECURITY.md",
            "VERSION",
            "resources/brand-logo.png",
        ):
            self.assertTrue((root / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
