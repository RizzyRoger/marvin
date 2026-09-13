"""Sandboxed Python script runner for Marvin."""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, PYTHON_RUNNER_ENABLED, ROOT

logger = logging.getLogger(__name__)

SCRIPTS_DIR = Path(os.environ.get("MARVIN_SCRIPTS_DIR", str(DATA_DIR / "scripts")))
MAX_CODE_CHARS = 8_000
MAX_OUTPUT_CHARS = 4_000
DEFAULT_TIMEOUT_SECONDS = 8.0

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Run a short Python script in Marvin’s sandbox (no network, timeout, "
                "cwd limited to the Marvin scripts directory). Only use when the user "
                "explicitly asked to run or execute Python/code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python source to execute.",
                    },
                    "authorized": {
                        "type": "boolean",
                        "description": "Must be true; user explicitly asked to run code.",
                    },
                },
                "required": ["code", "authorized"],
                "additionalProperties": False,
            },
        },
    }
]

_EXPLICIT_RUN = re.compile(
    r"\b("
    r"run (?:this |the )?(?:python |code|script)|"
    r"execute (?:this |the )?(?:python |code|script)|"
    r"python (?:code|script)|"
    r"sandbox"
    r")\b",
    re.I,
)


def register_python_capability() -> bool:
    if not PYTHON_RUNNER_ENABLED:
        return False
    try:
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
        return True
    except OSError:
        return False


def tools_for_python() -> list[dict[str, Any]]:
    if not register_python_capability():
        return []
    return list(TOOL_DEFINITIONS)


def user_grants_python_run(user_message: str) -> bool:
    return bool(_EXPLICIT_RUN.search(user_message or ""))


def wrap_python_result(text: str) -> str:
    return f'<python_data untrusted="true">\n{text}\n</python_data>'


def decide_python(user_message: str, *, available: bool) -> bool:
    if not available:
        return False
    return user_grants_python_run(user_message)


def _sandbox_profile_path(scripts_dir: Path) -> Path | None:
    template = ROOT / "scripts" / "sandbox" / "python_runner.sb"
    if not template.is_file():
        # Bundled layout: runtime/scripts may not exist; try alongside package.
        alt = Path(__file__).resolve().parents[2] / "scripts" / "sandbox" / "python_runner.sb"
        template = alt if alt.is_file() else template
    if not template.is_file():
        return None
    try:
        body = template.read_text(encoding="utf-8")
        scripts = str(scripts_dir.resolve())
        extra = (
            f'\n(allow file-read* (subpath "{scripts}"))\n'
            f'(allow file-write* (subpath "{scripts}"))\n'
            f'(allow file-read* (subpath "/private/tmp") (subpath "/tmp"))\n'
            f'(allow file-write* (subpath "/private/tmp") (subpath "/tmp"))\n'
        )
        out = SCRIPTS_DIR / ".marvin-python.sb"
        out.write_text(body + extra, encoding="utf-8")
        return out
    except OSError:
        logger.debug("Could not write sandbox profile", exc_info=True)
        return None


def dispatch_python_tool(
    name: str,
    args: dict,
    user_message: str,
    *,
    cancellation_event: threading.Event | None = None,
) -> str:
    if name != "run_python":
        return wrap_python_result(f"Unknown Python tool: {name}")
    if not PYTHON_RUNNER_ENABLED:
        return wrap_python_result(
            "Python runner is disabled in distributed builds. "
            "Set MARVIN_ALLOW_PYTHON=1 to enable (uses macOS sandbox-exec when available)."
        )
    if cancellation_event is not None and cancellation_event.is_set():
        return wrap_python_result("Canceled.")
    if not args.get("authorized") or not user_grants_python_run(user_message):
        return wrap_python_result(
            "REFUSED: Python runs require an explicit request to run or execute code."
        )
    code = str(args.get("code") or "")
    if not code.strip():
        return wrap_python_result("REFUSED: empty code.")
    if len(code) > MAX_CODE_CHARS:
        return wrap_python_result(
            f"REFUSED: code exceeds {MAX_CODE_CHARS} characters."
        )
    try:
        SCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return wrap_python_result(f"Error: scripts directory unavailable ({exc}).")

    env = {
        "PATH": os.environ.get("PATH", ""),
        "LANG": os.environ.get("LANG", "en_US.UTF-8"),
        "PYTHONPATH": "",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(SCRIPTS_DIR),
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".py",
        dir=str(SCRIPTS_DIR),
        delete=False,
    ) as handle:
        handle.write(code)
        script_path = handle.name

    cmd = ["python3", "-I", script_path]
    use_sandbox = (os.environ.get("MARVIN_ALLOW_PYTHON") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } or (os.environ.get("MARVIN_PYTHON_SANDBOX") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    profile = _sandbox_profile_path(SCRIPTS_DIR) if use_sandbox else None
    if profile is not None and os.path.exists("/usr/bin/sandbox-exec"):
        cmd = ["/usr/bin/sandbox-exec", "-f", str(profile), *cmd]

    try:
        completed = subprocess.run(
            cmd,
            cwd=str(SCRIPTS_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return wrap_python_result(
            f"Error: script timed out after {DEFAULT_TIMEOUT_SECONDS:.0f}s."
        )
    except Exception as exc:
        logger.exception("PYTHON_RUNNER: failed")
        return wrap_python_result(f"Error: could not run script ({exc}).")
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass

    if cancellation_event is not None and cancellation_event.is_set():
        return wrap_python_result("Canceled.")

    stdout = (completed.stdout or "")[:MAX_OUTPUT_CHARS]
    stderr = (completed.stderr or "")[:MAX_OUTPUT_CHARS]
    parts = [f"exit_code={completed.returncode}"]
    if stdout.strip():
        parts.append(f"stdout:\n{stdout}")
    if stderr.strip():
        parts.append(f"stderr:\n{stderr}")
    if len(parts) == 1:
        parts.append("(no output)")
    return wrap_python_result("\n".join(parts))
