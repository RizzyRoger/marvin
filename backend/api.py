"""FastAPI routes and WebSocket handlers."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from backend.agent import MarvinAgent
from backend.config import ENROLL_PHRASES, FUNCTIONS, SPEAKER_ENROLL_SECONDS
from backend.storage.chat import clear_history, load_history

logger = logging.getLogger(__name__)
router = APIRouter()

# Shared agent instance (initialized on startup)
agent: MarvinAgent | None = None
_ws_clients: set[WebSocket] = set()


class TextMessage(BaseModel):
    text: str


class FunctionSelect(BaseModel):
    function_id: str


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

    marvin.on_status = on_status
    marvin.on_message = on_message


@router.get("/api/health")
async def health():
    return {
        "status": "ok",
        "models_ready": agent.is_ready if agent else False,
        "listening": agent._listening if agent else False,
        "active_function": agent.active_function if agent else "chat",
        "voice_enrolled": agent.voice_enrolled if agent else False,
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


@router.delete("/api/chat/history")
async def delete_chat_history():
    clear_history()
    if agent and agent._llm:
        agent._llm.reset_history()
    await broadcast("history_cleared", {})
    return {"ok": True}


@router.post("/api/chat/send")
async def send_message(body: TextMessage):
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Empty message")

    loop = asyncio.get_running_loop()
    reply = await loop.run_in_executor(None, agent.process_text, text)
    loop.run_in_executor(None, agent.speak, reply)
    return {"reply": reply}


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
    status = agent.voice_profile_status()
    status["phrases"] = ENROLL_PHRASES
    status["sample_seconds"] = SPEAKER_ENROLL_SECONDS
    status["instructions"] = (
        "Stop Voice if it is on. Quiet room helps. Click Record sample, then read "
        "the phrase aloud in your normal voice until the tone ends. Repeat for each "
        "phrase, then click Save voice profile."
    )
    return status


@router.post("/api/voice/enroll/sample")
async def enroll_sample():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    if agent._listening:
        raise HTTPException(400, "Stop Voice before recording enrollment samples")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, agent.record_enrollment_sample)
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
    return result


@router.post("/api/voice/enroll/reset")
async def enroll_reset():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    agent.reset_enrollment()
    return agent.voice_profile_status()


@router.delete("/api/voice/profile")
async def delete_voice_profile():
    if not agent or not agent.is_ready:
        raise HTTPException(503, "Models not loaded yet")
    agent.clear_voice_profile()
    await broadcast("voice_enroll", {"enrolled": False})
    return {"enrolled": False}


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
            },
        }))
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            event = msg.get("event")
            if event == "ping":
                await ws.send_text(json.dumps({"event": "pong", "data": {}}))
            elif event == "send_message" and agent:
                text = msg.get("data", {}).get("text", "").strip()
                if text:
                    loop = asyncio.get_running_loop()
                    reply = await loop.run_in_executor(None, agent.process_text, text)
                    loop.run_in_executor(None, agent.speak, reply)
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(ws)
