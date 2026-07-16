"""Marvin application entry point."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.agent import MarvinAgent
from backend.api import init_agent, router
from backend.config import BRAND_LOGO_PATH

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("marvin")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
agent = MarvinAgent()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_agent(agent)

    def load():
        try:
            agent.load_models()
            agent.sync_history_to_llm()
            logger.info("Marvin is ready.")
        except Exception:
            logger.exception("Failed to load models")

    threading.Thread(target=load, daemon=True).start()
    yield


app = FastAPI(title="Marvin", description="Personal voice AI agent", lifespan=lifespan)
app.include_router(router)

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def index():
    index_path = FRONTEND_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Marvin backend running. Frontend not found."}


@app.get("/brand-logo.png")
async def brand_logo():
    if BRAND_LOGO_PATH.exists():
        return FileResponse(BRAND_LOGO_PATH, media_type="image/png")
    return {"message": "Brand logo not found."}


def main():
    import uvicorn

    from backend.config import HOST, PORT

    uvicorn.run("backend.main:app", host=HOST, port=PORT, reload=False)


if __name__ == "__main__":
    main()
