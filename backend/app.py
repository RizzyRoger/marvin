"""Marvin desktop app — native window around the local FastAPI UI."""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

import uvicorn
import webview

from backend.config import DATA_DIR, HOST, LOG_PATH, PORT

logger = logging.getLogger("marvin.app")

WINDOW_TITLE = "Marvin"
WINDOW_WIDTH = 1100
WINDOW_HEIGHT = 720
MIN_WIDTH = 800
MIN_HEIGHT = 500


def _configure_logging() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stderr)]
    try:
        handlers.append(
            RotatingFileHandler(LOG_PATH, maxBytes=2_000_000, backupCount=3)
        )
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _wait_for_server(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _port_open(host, port):
            return True
        time.sleep(0.15)
    return False


def _notify(title: str, message: str) -> None:
    if sys.platform != "darwin":
        return
    script = f'display alert "{title}" message "{message}"'
    try:
        subprocess.run(["osascript", "-e", script], check=False)
    except OSError:
        pass


def _already_running() -> bool:
    return _port_open(HOST, PORT)


def _health_ok() -> bool:
    try:
        import urllib.request

        with urllib.request.urlopen(f"http://{HOST}:{PORT}/api/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _kill_stale_server() -> None:
    if not _port_open(HOST, PORT) or _health_ok():
        return
    logger.warning("Killing stale Marvin process on port %s", PORT)
    subprocess.run(
        ["sh", "-c", f"lsof -ti:{PORT} | xargs kill -9 2>/dev/null || true"],
        check=False,
    )
    time.sleep(0.5)


def _run_server() -> None:
    uvicorn.run(
        "backend.main:app",
        host=HOST,
        port=PORT,
        log_level="info",
        access_log=False,
    )


def main() -> None:
    _configure_logging()
    _kill_stale_server()

    if _already_running() and _health_ok():
        logger.info("Marvin is already running on http://%s:%s — opening window", HOST, PORT)
    else:
        _kill_stale_server()
        server = threading.Thread(target=_run_server, daemon=True)
        server.start()
        if not _wait_for_server(HOST, PORT):
            logger.error("Server failed to start on http://%s:%s", HOST, PORT)
            _notify("Marvin Failed to Start", f"Check the log at {LOG_PATH}")
            sys.exit(1)

    try:
        window = webview.create_window(
            WINDOW_TITLE,
            f"http://{HOST}:{PORT}",
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(MIN_WIDTH, MIN_HEIGHT),
            background_color="#0f0f12",
        )
        webview.start(gui="cocoa" if sys.platform == "darwin" else None)
    except Exception:
        logger.exception("Desktop window failed")
        _notify("Marvin Crashed", f"See log: {LOG_PATH}")
        raise


if __name__ == "__main__":
    main()
