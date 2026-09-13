"""FastAPI routes and WebSocket handlers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.agent import MarvinAgent
from backend.config import FUNCTIONS
from backend.storage.chat import clear_history, delete_exchange, load_history

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared agent instance (initialized on startup)
agent: MarvinAgent | None = None
_ws_clients: set[WebSocket] = set()


class TextMessage(BaseModel):
    text: str
    timezone: str | None = None


class FunctionSelect(BaseModel):
    function_id: str


class TimezoneMessage(BaseModel):
    timezone: str


class VoiceSettingsUpdate(BaseModel):
    voice_lock_enabled: bool | None = None
    strictness_mode: str | None = None
    require_addressing: bool | None = None
    contextual_continuation_enabled: bool | None = None
    continuation_window_seconds: int | None = None
    profile_name: str | None = None


async def broadcast(event: str, data: dict[str, Any]) -> None:
    global _ws_clients
    dead: set[WebSocket] = set()
    payload = json.dumps({"event": event, "data": data})
    for ws in _ws_clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.add(ws)
    _ws_clients -= dead


def init_agent(marvin: MarvinAgent) -> None:
    global agent
    agent = marvin
    loop = asyncio.get_running_loop()

    def on_status(status: str, data: dict) -> None:
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast("status", {"status": status, **data}),
                loop,
            )

    def on_message(message: dict) -> None:
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast("message", message),
                loop,
            )

    def on_reminder(event: str, data: dict) -> None:
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(broadcast(event, data), loop)
        if agent is not None:
            kind = str((data or {}).get("kind") or "reminder")
            label = str(
                (data or {}).get("name")
                or (data or {}).get("message")
                or ("Timer" if kind == "timer" else "Reminder")
            ).strip()
            spoken = (
                f"Timer done: {label}."
                if kind == "timer"
                else f"Reminder: {label}."
            )

            def _speak_due() -> None:
                try:
                    agent.speak(spoken)
                except Exception:
                    logger.exception("Failed to speak due reminder/timer")

            threading.Thread(
                target=_speak_due, name="marvin-reminder-tts", daemon=True
            ).start()

    marvin.on_status = on_status
    marvin.on_message = on_message
    marvin.on_broadcast = on_reminder

    from backend.reminders import start_reminder_scheduler

    start_reminder_scheduler(on_reminder)


def _tool_activity(marvin: MarvinAgent | None) -> dict:
    if not marvin:
        return {"functions_used": [], "sticky_tools": [], "active_tools": []}
    return marvin._tool_activity_payload()


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "models_ready": agent.is_ready if agent else False,
        "listening": agent._listening if agent else False,
        "active_function": agent.active_function if agent else "chat",
        "voice_enrolled": agent.voice_enrolled if agent else False,
        **_tool_activity(agent),
    }


@router.get("/api/functions")
async def get_functions():
    return {"functions": FUNCTIONS, "active": agent.active_function if agent else "chat"}


@router.post("/api/functions/select")
async def select_function(body: FunctionSelect):
    if not agent:
        raise HTTPException(503, "Agent not initialized")
    if not agent.set_function(body.function_id):
        raise HTTPException(400, f"Function '{body.function_id}' is not available")
    await broadcast("function_changed", {"function_id": body.function_id})
    return {"active": body.function_id}


@router.get("/api/chat/history")
async def get_chat_history():
    return {"messages": load_history()}


@router.delete("/api/chat/history/{message_id}")
async def delete_chat_exchange(message_id: str):
    try:
        result = delete_exchange(message_id)
    except KeyError as exc:
        raise HTTPException(404, "Message not found") from exc
    if agent and agent._llm:
        agent._llm.reset_history()
        pairs: list[dict[str, str]] = []
        for item in result["messages"]:
            role = item.get("role")
            content = item.get("content") or ""
            if role in {"user", "assistant"} and content:
                pairs.append({"role": role, "content": content})
        agent._llm.set_history(pairs)
    await broadcast("history_updated", {"messages": result["messages"]})
    return result


@router.delete("/api/chat/history")
async def delete_chat_history():
    clear_history()
    if agent:
        agent.clear_used_tools()
        if agent._llm:
            agent._llm.reset_history()
    await broadcast("history_cleared", {"functions_used": [], "sticky_tools": [], "active_tools": []})
    return {"ok": True}


@router.post("/api/chat/send")
async def send_message(body: TextMessage):
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Empty message")

    loop = asyncio.get_running_loop()
    reply = await loop.run_in_executor(
        None,
        lambda: agent.process_and_speak(text, client_timezone=body.timezone),
    )
    return {"reply": reply}


@router.post("/api/session/timezone")
async def set_session_timezone(body: TimezoneMessage):
    if not agent:
        raise HTTPException(503, "Agent not initialized")
    agent.set_client_timezone(body.timezone)
    return {"timezone": agent._clock.session_timezone}


@router.post("/api/voice/start")
async def start_voice():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    listening = agent.start_listening()
    if not listening:
        raise HTTPException(503, "Microphone could not be opened")
    return {"listening": listening, "voice_enrolled": agent.voice_enrolled}


@router.post("/api/voice/stop")
async def stop_voice():
    if agent:
        agent.stop_listening()
    return {"listening": False}


@router.get("/api/voice/profile")
async def voice_profile():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    return agent.voice_profile_status()


@router.get("/api/voice/settings")
async def get_voice_settings():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    return agent.voice_listening_status()


@router.patch("/api/voice/settings")
@router.put("/api/voice/settings")
async def patch_voice_settings(body: VoiceSettingsUpdate):
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    changes = body.model_dump(exclude_none=True)
    if "strictness_mode" in changes and changes["strictness_mode"] not in {
        "balanced",
        "strict",
        "very_strict",
    }:
        raise HTTPException(400, "strictness_mode must be balanced, strict, or very_strict")
    if changes.get("voice_lock_enabled") and not agent.voice_enrolled:
        raise HTTPException(
            400,
            "Enroll a voice profile before enabling Voice Lock",
        )
    status = agent.update_voice_listening_settings(**changes)
    await broadcast("voice_settings", status)
    return status


class EnrollSampleBody(BaseModel):
    sample_id: str | None = None


@router.post("/api/voice/enroll/sample")
async def enroll_sample(body: EnrollSampleBody | None = None):
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    if agent._listening:
        raise HTTPException(400, "Stop Voice before recording enrollment samples")
    payload = body or EnrollSampleBody()
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: agent.record_enrollment_sample(sample_id=payload.sample_id),
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    await broadcast("voice_enroll", result)
    return result


@router.post("/api/voice/enroll/finish")
async def enroll_finish():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    try:
        result = agent.finalize_voice_enrollment()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await broadcast("voice_enroll", {"enrolled": True, **result})
    await broadcast("voice_settings", agent.voice_listening_status())
    return result


@router.post("/api/voice/enroll/reset")
async def enroll_reset():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    status = agent.reset_enrollment()
    await broadcast("voice_enroll", status)
    await broadcast("voice_settings", status)
    return status


@router.delete("/api/voice/enroll/sample/{sample_id}")
async def enroll_reset_sample(sample_id: str):
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    try:
        status = agent.reset_enrollment_sample(sample_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    await broadcast("voice_enroll", status)
    await broadcast("voice_settings", status)
    return status


@router.post("/api/voice/test")
async def test_voice_sample():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    if agent._listening:
        raise HTTPException(400, "Stop Voice before testing")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, agent.test_voice_sample)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result


@router.delete("/api/voice/profile")
async def delete_voice_profile():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    agent.clear_voice_profile()
    status = agent.voice_listening_status()
    await broadcast("voice_enroll", {"enrolled": False})
    await broadcast("voice_settings", status)
    return status


@router.get("/api/skills/status")
async def skills_status():
    from backend.skills import (
        PHASE2_SKILL_IDS,
        discover_bundled_skills,
        get_skill_file_service,
        load_format_skill_settings,
    )

    service = get_skill_file_service()
    service.ensure_exists()
    status = service.get_status()
    enabled = load_format_skill_settings()
    format_skills = [
        {
            "id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "enabled": bool(enabled.get(skill.skill_id, skill.group == "custom")),
            "phase": skill.phase,
            "group": skill.group,
            "custom": skill.group == "custom",
        }
        for skill in discover_bundled_skills()
    ]
    status["format_skills"] = format_skills
    status["bundled_skills"] = format_skills
    status["phase2_skills"] = list(PHASE2_SKILL_IDS)
    return status


@router.post("/api/skills/reveal")
async def skills_reveal():
    """Open the skill.md folder in the system file browser."""
    import subprocess
    import sys

    from backend.skills import get_skill_file_service

    path = get_skill_file_service().ensure_exists()
    folder = str(path.parent)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", folder])
        else:
            subprocess.Popen(["explorer", folder])
    except Exception as exc:
        raise HTTPException(500, f"Could not open skills folder: {exc}") from exc
    return {"path": str(path), "opened": True}


class FormatSkillsUpdate(BaseModel):
    enabled: dict[str, bool]


@router.put("/api/skills/format")
async def skills_format_update(body: FormatSkillsUpdate):
    from backend.skills import (
        discover_bundled_skills,
        save_format_skill_settings,
    )

    saved = save_format_skill_settings(body.enabled or {})
    skills = [
        {
            "id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "enabled": bool(saved.get(skill.skill_id, skill.group == "custom")),
            "phase": skill.phase,
            "group": skill.group,
            "custom": skill.group == "custom",
        }
        for skill in discover_bundled_skills()
    ]
    return {
        "enabled": saved,
        "format_skills": skills,
        "bundled_skills": skills,
    }


@router.delete("/api/skills/custom/{slug}")
async def skills_custom_delete(slug: str):
    from backend.skills.custom import delete_custom_skill

    result = delete_custom_skill(slug)
    if result.startswith("REFUSED:"):
        raise HTTPException(404, result)
    from backend.skills import discover_bundled_skills, load_format_skill_settings

    enabled = load_format_skill_settings()
    skills = [
        {
            "id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "enabled": bool(enabled.get(skill.skill_id, skill.group == "custom")),
            "phase": skill.phase,
            "group": skill.group,
            "custom": skill.group == "custom",
        }
        for skill in discover_bundled_skills()
    ]
    return {"ok": True, "result": result, "format_skills": skills, "bundled_skills": skills}


class ProviderKeyBody(BaseModel):
    api_key: str


class ProviderTestBody(BaseModel):
    api_key: str | None = None


class ModelSelectBody(BaseModel):
    provider_id: str
    model_id: str


@router.get("/api/providers")
async def get_providers():
    from backend.provider_service import providers_status

    return providers_status()


@router.put("/api/providers/{provider_id}/key")
async def put_provider_key(provider_id: str, body: ProviderKeyBody):
    from backend.provider_service import save_provider_key

    try:
        return save_provider_key(provider_id, body.api_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc


@router.delete("/api/providers/{provider_id}/key")
async def remove_provider_key(provider_id: str):
    from backend.provider_service import delete_provider_key

    try:
        return delete_provider_key(provider_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/providers/{provider_id}/test")
async def test_provider(provider_id: str, body: ProviderTestBody | None = None):
    from backend.provider_service import test_provider_key

    payload = body or ProviderTestBody()
    try:
        return test_provider_key(provider_id, payload.api_key)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/providers/select")
async def select_provider_model(body: ModelSelectBody):
    from backend.provider_service import select_model

    try:
        result = select_model(body.provider_id, body.model_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await broadcast("model_changed", result)
    return result


@router.get("/api/spotify/status")
async def spotify_status():
    from backend.tools.spotify import spotify_status as status_fn

    status = status_fn()
    return {
        "enabled": status.enabled,
        "client_configured": status.client_configured,
        "connected": status.connected,
        "display_name": status.display_name,
        "hint": status.hint,
    }


@router.post("/api/spotify/authorize")
async def spotify_authorize():
    import webbrowser

    from backend.tools.spotify import begin_authorize
    from backend.tools.spotify.types import SpotifyError

    try:
        payload = begin_authorize()
    except SpotifyError as exc:
        raise HTTPException(400, exc.user_message()) from exc

    url = payload.get("authorize_url") or ""
    opened = False
    if url:
        try:
            opened = bool(webbrowser.open(url))
        except Exception:
            logger.exception("SPOTIFY: failed to open authorize URL in browser")
            opened = False
    return {**payload, "opened_browser": opened}


@router.get("/api/spotify/callback")
async def spotify_callback(code: str = "", state: str = "", error: str = ""):
    from backend.tools.spotify.auth import exchange_code
    from backend.tools.spotify.types import SpotifyError

    if error:
        return HTMLResponse(
            _spotify_callback_html(
                False,
                "Spotify login was canceled or denied. You can close this window.",
            ),
            status_code=400,
        )
    if not code or not state:
        return HTMLResponse(
            _spotify_callback_html(False, "Missing Spotify login parameters."),
            status_code=400,
        )
    try:
        exchange_code(code, state)
    except SpotifyError as exc:
        return HTMLResponse(
            _spotify_callback_html(False, exc.user_message()),
            status_code=400,
        )
    from backend.tools.spotify import register_spotify_capability

    register_spotify_capability()
    return HTMLResponse(
        _spotify_callback_html(
            True,
            "Spotify connected. You can close this window and return to Marvin.",
        )
    )


@router.delete("/api/spotify/connection")
async def spotify_disconnect():
    from backend.tools.spotify import disconnect

    status = disconnect()
    return {
        "enabled": status.enabled,
        "client_configured": status.client_configured,
        "connected": status.connected,
        "display_name": status.display_name,
        "hint": status.hint,
    }


@router.get("/api/scrambler/status")
async def scrambler_status():
    from backend.tools.voice_scrambler import scrambler_status_payload

    return scrambler_status_payload()


@router.post("/api/scrambler/start")
async def scrambler_start(body: dict | None = None):
    from backend.tools.voice_scrambler import scrambler_status_payload, start_scrambler

    device = str((body or {}).get("output_device") or "").strip() or None
    message = start_scrambler(device)
    status = scrambler_status_payload()
    status["message"] = message
    return status


@router.post("/api/scrambler/stop")
async def scrambler_stop():
    from backend.tools.voice_scrambler import scrambler_status_payload, stop_scrambler

    message = stop_scrambler()
    status = scrambler_status_payload()
    status["message"] = message
    return status


@router.put("/api/scrambler/settings")
async def scrambler_settings_put(body: dict | None = None):
    from backend.tools.voice_scrambler import (
        reset_scrambler_settings,
        save_scrambler_settings,
        scrambler_status_payload,
    )

    payload = body or {}
    if payload.get("reset"):
        reset_scrambler_settings()
    else:
        allowed = {
            "enabled_strength",
            "clarity_disguise",
            "wet_dry",
            "master_gain",
            "mod_strength",
            "pitch",
            "formant",
            "gain",
            "delay_ms",
        }
        patch = {k: payload[k] for k in allowed if k in payload}
        if patch:
            save_scrambler_settings(patch)
    return scrambler_status_payload()


@router.get("/api/vault/status")
async def vault_status():
    from backend import config
    from backend.clock import load_saved_vault_root
    from backend.tools.obsidian import vault_access_state, vault_is_connected

    configured = bool(load_saved_vault_root() or os.environ.get("MARVIN_VAULT_ROOT"))
    root = Path(config.VAULT_ROOT) if configured and str(config.VAULT_ROOT) else Path()
    access = vault_access_state()
    return {
        "path": str(root) if configured else "",
        "configured": configured,
        "needs_setup": not configured,
        "connected": vault_is_connected() if configured else False,
        "exists": root.is_dir() if configured else False,
        "needs_permission": bool(access.get("needs_permission")),
        "hint": access.get("hint") or "",
        "bundle": (os.environ.get("MARVIN_BUNDLE") or "").strip().lower()
        in {"1", "true", "yes"},
    }


@router.post("/api/vault/request-access")
async def vault_request_access():
    import subprocess
    import sys

    from backend import config
    from backend.tools.obsidian import vault_access_state

    path = Path(config.VAULT_ROOT) if str(config.VAULT_ROOT) else Path()
    if not path or not str(path):
        raise HTTPException(400, "Configure a vault path first.")
    folder = str(path)
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", folder])
            subprocess.Popen(
                [
                    "osascript",
                    "-e",
                    f'try\nset p to POSIX file "{folder}" as alias\nend try',
                ]
            )
        elif sys.platform.startswith("linux"):
            subprocess.Popen(["xdg-open", folder])
        else:
            subprocess.Popen(["explorer", folder])
    except Exception as exc:
        raise HTTPException(500, f"Could not open vault folder: {exc}") from exc
    return vault_access_state()


@router.get("/api/speech/settings")
async def speech_settings_get():
    from backend.speech_settings import speech_settings_payload

    return speech_settings_payload()


@router.put("/api/speech/settings")
async def speech_settings_put(body: dict):
    from backend.speech_settings import save_speech_settings, speech_settings_payload

    try:
        save_speech_settings(
            nationality=(body or {}).get("nationality"),
            gender=(body or {}).get("gender"),
            mode=(body or {}).get("mode"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if agent is not None:
        try:
            agent.reload_tts()
        except Exception:
            logger.debug("TTS reload after speech settings failed", exc_info=True)
    return speech_settings_payload()


@router.put("/api/vault/path")
async def vault_set_path(body: dict):
    from backend import config
    from backend.clock import save_vault_root
    from backend.tools import obsidian as obsidian_tools

    raw = str((body or {}).get("path") or "").strip()
    if not raw:
        raise HTTPException(400, "path is required")
    try:
        saved = save_vault_root(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    path = Path(saved)
    config.VAULT_ROOT = path
    obsidian_tools.VAULT_ROOT = path
    try:
        obsidian_tools._invalidate_note_cache()
    except Exception:
        pass
    access = obsidian_tools.vault_access_state()
    return {
        "path": saved,
        "connected": bool(access.get("connected")),
        "needs_permission": bool(access.get("needs_permission")),
        "hint": access.get("hint") or "",
    }


@router.get("/api/reminders")
async def reminders_list():
    from backend.reminders import list_pending

    return {"reminders": list_pending()}


def _spotify_callback_html(ok: bool, message: str) -> str:
    title = "Spotify connected" if ok else "Spotify connection failed"
    safe = (
        message.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>{title}</title>
  <style>
    body {{
      font-family: Georgia, "Times New Roman", serif;
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: #f3efe6;
      color: #1f1a14;
    }}
    main {{
      max-width: 28rem;
      padding: 2rem;
      text-align: center;
    }}
    h1 {{ font-size: 1.4rem; margin: 0 0 0.75rem; }}
    p {{ margin: 0; line-height: 1.5; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p>{safe}</p>
  </main>
</body>
</html>"""


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _ws_clients.add(ws)
    try:
        await ws.send_text(json.dumps({
            "event": "connected",
            "data": {
                "models_ready": agent.is_ready if agent else False,
                "active_function": agent.active_function if agent else "chat",
                "functions": FUNCTIONS,
                "voice_enrolled": agent.voice_enrolled if agent else False,
                **_tool_activity(agent),
            },
        }))
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "ping":
                await ws.send_text(json.dumps({"event": "pong", "data": {}}))
            elif event == "send_message" and agent:
                data = msg.get("data", {}) or {}
                text = (data.get("text") or "").strip()
                timezone = data.get("timezone")
                if text:
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: agent.process_and_speak(
                            text, client_timezone=timezone
                        ),
                    )
            elif event == "set_timezone" and agent:
                timezone = (msg.get("data", {}) or {}).get("timezone")
                if timezone:
                    agent.set_client_timezone(timezone)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
