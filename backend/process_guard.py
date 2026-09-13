"""Pid-file helpers so Marvin only reclaims its own listener on PORT."""

from __future__ import annotations

import logging
import os
import signal
import time
from pathlib import Path

from backend.config import DATA_DIR, HOST, PORT

logger = logging.getLogger(__name__)

PID_PATH = DATA_DIR / "marvin.pid"


def pid_path() -> Path:
    return PID_PATH


def write_pid_file(pid: int | None = None) -> None:
    value = pid if pid is not None else os.getpid()
    try:
        PID_PATH.parent.mkdir(parents=True, exist_ok=True)
        PID_PATH.write_text(str(value), encoding="utf-8")
        try:
            PID_PATH.chmod(0o600)
        except OSError:
            pass
    except OSError:
        logger.debug("Could not write pid file", exc_info=True)


def read_pid_file() -> int | None:
    try:
        raw = PID_PATH.read_text(encoding="utf-8").strip()
        return int(raw) if raw else None
    except (OSError, ValueError):
        return None


def clear_pid_file() -> None:
    try:
        if PID_PATH.is_file():
            PID_PATH.unlink()
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _pid_listens_on_port(pid: int, port: int = PORT) -> bool:
    """Best-effort check via lsof (macOS/Linux)."""
    import subprocess

    try:
        completed = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in (completed.stdout or "").splitlines():
        try:
            if int(line.strip()) == pid:
                return True
        except ValueError:
            continue
    return False


def reclaim_stale_listener(*, health_ok: bool) -> None:
    """
    If PORT is occupied but health checks fail, kill only the pid recorded in
    marvin.pid (when it still owns the port). Never mass-kill every listener.
    """
    import socket

    try:
        with socket.create_connection((HOST, PORT), timeout=0.4):
            occupied = True
    except OSError:
        occupied = False

    if not occupied or health_ok:
        return

    old = read_pid_file()
    if old is None:
        logger.warning(
            "Port %s busy without a Marvin pid file — not killing foreign processes",
            PORT,
        )
        return
    if not _pid_alive(old):
        clear_pid_file()
        return
    if not _pid_listens_on_port(old, PORT):
        logger.warning(
            "Pid %s from marvin.pid is alive but not listening on %s — leaving alone",
            old,
            PORT,
        )
        return

    logger.warning("Reclaiming stale Marvin pid=%s on port %s", old, PORT)
    try:
        os.kill(old, signal.SIGTERM)
        time.sleep(0.4)
        if _pid_alive(old):
            os.kill(old, signal.SIGKILL)
            time.sleep(0.2)
    except OSError:
        logger.debug("Failed to signal stale pid %s", old, exc_info=True)
    clear_pid_file()
