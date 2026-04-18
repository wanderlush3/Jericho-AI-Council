"""
Jericho — Web Dashboard API

FastAPI application serving JSON endpoints that wrap existing managers,
plus static files for the single-page dashboard frontend.

Launch via CLI: ``jericho web``
Or directly:  ``uvicorn core.web_api:app --port 8080``

Route modules live in core/routes/:
    status, council, proposals, votes, characters, tasks,
    locations, items, stores, settings, chat, memories,
    laws, evolutions, sessions, treasury, images,
    generation, explore, stories, reputation
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

from config.settings import WEB_STATIC_DIR

# Re-export settings constants so existing test patches
# (e.g. patch("core.web_api.COUNCIL_MEMBERS_DIR", ...)) keep working.
from config.settings import COUNCIL_MEMBERS_DIR  # noqa: F401
from config.settings import EVOLUTION_DIR  # noqa: F401

# ── Import all route modules ──
from core.routes.status import router as status_router
from core.routes.council import router as council_router
from core.routes.proposals import router as proposals_router
from core.routes.votes import router as votes_router
from core.routes.characters import router as characters_router
from core.routes.tasks import router as tasks_router
from core.routes.locations import router as locations_router
from core.routes.items import router as items_router
from core.routes.stores import router as stores_router
from core.routes.settings import router as settings_router
from core.routes.chat import router as chat_router
from core.routes.memories import router as memories_router
from core.routes.laws import router as laws_router
from core.routes.evolutions import router as evolutions_router
from core.routes.sessions import router as sessions_router
from core.routes.treasury import router as treasury_router
from core.routes.images import router as images_router
from core.routes.generation import router as generation_router
from core.routes.explore import router as explore_router
from core.routes.stories import router as stories_router
from core.routes.reputation import router as reputation_router


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""

    application = FastAPI(
        title="Jericho AI Council",
        description="Web dashboard for the Jericho AI Council governance system.",
        version="0.9.0",
    )

    # Decrypt API keys at startup so APIClient reads the real keys
    # (load_dotenv only loads the encrypted Fernet tokens into os.environ)
    # Also load model overrides so APIClient can apply them.
    from core.api_keys import APIKeyManager
    mgr = APIKeyManager()
    mgr.load_all()
    for provider in mgr.PROVIDERS:
        mgr.load_model(provider)

    # Explicitly load ComfyUI settings from .env into os.environ.
    # This ensures persistence across server restarts even if
    # load_dotenv encounters edge-case parse issues (e.g. orphan
    # lines from earlier multiline value corruption).
    from config.settings import (
        COMFYUI_HOST_ENV, COMFYUI_PORT_ENV, COMFYUI_DEFAULT_STYLE_ENV,
    )
    import os as _os
    for _env_var in (COMFYUI_HOST_ENV, COMFYUI_PORT_ENV, COMFYUI_DEFAULT_STYLE_ENV):
        _val = mgr._read_env_value(_env_var)
        if _val is not None:
            _os.environ[_env_var] = _val

    # ── Include all route modules ──────────────────────────────
    application.include_router(status_router)
    application.include_router(council_router)
    application.include_router(proposals_router)
    application.include_router(votes_router)
    application.include_router(characters_router)
    application.include_router(tasks_router)
    application.include_router(locations_router)
    application.include_router(items_router)
    application.include_router(stores_router)
    application.include_router(settings_router)
    application.include_router(chat_router)
    application.include_router(memories_router)
    application.include_router(laws_router)
    application.include_router(evolutions_router)
    application.include_router(sessions_router)
    application.include_router(treasury_router)
    application.include_router(images_router)
    application.include_router(generation_router)
    application.include_router(explore_router)
    application.include_router(stories_router)
    application.include_router(reputation_router)

    # ── Static Files ──────────────────────────────────────────
    static_dir = WEB_STATIC_DIR
    if static_dir.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(static_dir)),
            name="static",
        )

    # Ensure text-based static assets have charset=utf-8 to prevent
    # browsers from misinterpreting emoji/Unicode in JS files on Windows.
    _TEXT_TYPES = {
        "text/html", "text/css", "text/javascript",
        "application/javascript", "application/json",
    }

    @application.middleware("http")
    async def _add_utf8_charset(request: Request, call_next):
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        base_type = ct.split(";")[0].strip()
        if base_type in _TEXT_TYPES and "charset" not in ct:
            response.headers["content-type"] = f"{base_type}; charset=utf-8"
        return response

    @application.get("/")
    def serve_index() -> FileResponse:
        """Serve the SPA index.html."""
        index = static_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found.")
        return FileResponse(str(index), media_type="text/html; charset=utf-8")

    return application


# Module-level app instance for ``uvicorn core.web_api:app``
app = create_app()
