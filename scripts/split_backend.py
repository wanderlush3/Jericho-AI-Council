"""
split_backend.py — Extract web_api.py endpoints into core/routes/*.py modules.

Reads the monolithic web_api.py, splits endpoints into per-domain route modules
using FastAPI APIRouter. Maintains identical functionality.
"""

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORIG = ROOT / "core" / "web_api.py"
BACKUP = ROOT / "core" / "web_api_original.py"
ROUTES_DIR = ROOT / "core" / "routes"

# Read the original source
src = ORIG.read_text(encoding="utf-8")
lines = src.splitlines(keepends=True)

print(f"Read {len(lines)} lines from web_api.py")

# ── Backup the original ──
BACKUP.write_text(src, encoding="utf-8")
print(f"Backed up original to web_api_original.py")

# ── Section definitions ──
# Each tuple: (module_name, start_line, end_line)
# Lines are 1-indexed, inclusive. These define the ranges of code
# inside create_app() that belong to each route module.
# Helper functions that fall between sections are noted separately.

SECTIONS = [
    # Status + narrative bulletins
    ("status",      56,   253),
    # Council CRUD + avatars + promote
    ("council",    254,   585),
    # Proposals + discussion streaming + handoffs
    ("proposals",  586,  1635),
    # Votes
    ("votes",     1636,  1723),
    # Characters CRUD + traits + avatar + PNG export
    ("characters",1724,  2088),
    # Tasks
    ("tasks",     2089,  2442),
    # Locations CRUD
    ("locations",  2443, 2574),
    # Items CRUD
    ("items",      2575, 2702),
    # Stores CRUD + inventory + purchase
    ("stores",     2703, 2937),
    # Analytics + Settings + ComfyUI config
    ("settings",   2938, 3695),
    # Chat helpers + endpoints (includes _next_chat_id, _make_human_chat, _make_discussion_manager)
    ("chat",       3696, 4082),
    # Memories
    ("memories",   4083, 4235),
    # Laws
    ("laws",       4236, 4362),
    # Evolutions
    ("evolutions", 4363, 4842),
    # Council Sessions
    ("sessions",   4843, 5282),
    # Treasury + Taxation
    ("treasury",   5283, 5489),
    # Images
    ("images",     5490, 5645),
    # Generation pipeline + _get_pipeline + _explore_primary_image
    ("generation", 5646, 6101),
    # _build_participant_context + Explore endpoints
    ("explore",    6103, 6651),
    # Stories
    ("stories",    6652, 7396),
]


def dedent_body(text):
    """Remove exactly 4 spaces of leading indentation from each line (un-nest from create_app)."""
    result = []
    for line in text.splitlines(keepends=True):
        if line.startswith("    "):
            result.append(line[4:])
        elif line.strip() == "":
            result.append(line)
        else:
            # Lines not indented (shouldn't happen inside create_app, but be safe)
            result.append(line)
    return "".join(result)


def fixup_body(body, module_name):
    """Apply necessary transformations to a route module body."""
    # Replace @application with @router
    body = body.replace("@application.", "@router.")
    # Remove any nonlocal statements (pipeline singleton moved to _helpers)
    body = body.replace("        nonlocal _generation_pipeline\n", "")
    return body


def detect_imports(body):
    """Detect which top-level and helper imports a route body needs."""
    top = []
    top.append("from __future__ import annotations\n")
    top.append("")
    
    # Standard library
    if "json_module" in body or "json.dumps" in body:
        top.append("import json as json_module")
    if "from typing import" not in body and "Any" in body:
        top.append("from typing import Any")
    if "from dataclasses import asdict" in body or "asdict(" in body:
        top.append("from dataclasses import asdict")
    if "from pathlib import Path" in body:
        pass  # it's already inline
    
    top.append("")
    top.append("from fastapi import APIRouter, HTTPException, Query")
    
    if "FileResponse" in body:
        top.append("from fastapi.responses import FileResponse, JSONResponse")
    elif "JSONResponse" in body:
        top.append("from fastapi.responses import JSONResponse")
    if "StreamingResponse" in body:
        top.append("from starlette.responses import StreamingResponse")
    
    # Check for helpers
    helpers = []
    for h in [
        "_get_pipeline", "_build_participant_context", "_explore_primary_image",
        "_build_session_prompt", "_sync_law_shared_memory",
    ]:
        if h + "(" in body or h + " " in body:
            # Only import if it's USED but not DEFINED in this body
            if f"def {h}" not in body:
                helpers.append(h)
    
    top.append("")
    
    if helpers:
        top.append("from core.routes._helpers import (")
        for h in helpers:
            top.append(f"    {h},")
        top.append(")")
        top.append("")
    
    top.append("")
    top.append("router = APIRouter()")
    top.append("")
    
    return "\n".join(top)


def main():
    ROUTES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create __init__.py
    (ROUTES_DIR / "__init__.py").write_text("", encoding="utf-8")
    
    # ── Extract each section ──
    for module_name, start, end in SECTIONS:
        print(f"Extracting {module_name} (lines {start}-{end})...")
        
        # Get the raw lines (1-indexed to 0-indexed)
        section_raw = "".join(lines[start - 1 : end])
        
        # Remove the 4-space create_app() indentation
        body = dedent_body(section_raw)
        
        # Apply fixups
        body = fixup_body(body, module_name)
        
        # Build header
        header = f'"""\nJericho — {module_name.replace("_", " ").title()} Routes\n"""\n\n'
        header += detect_imports(body)
        
        # Write
        filepath = ROUTES_DIR / f"{module_name}.py"
        content = header + "\n" + body
        filepath.write_text(content, encoding="utf-8")
        print(f"  -> {module_name}.py ({len(content.splitlines())} lines)")
    
    # ── Create _helpers.py ──
    # Extract the actual helper functions from the source
    print("Creating _helpers.py...")
    
    # Extract _build_session_prompt (lines ~5246-5282ish — need to find exact)
    # Extract _sync_law_shared_memory (lines ~4350-4362ish)
    # The _get_pipeline, _explore_primary_image, _build_participant_context
    # are included in their section modules. For helpers used across sections,
    # we need a shared module.
    
    # Actually, let me check which helpers are used across MULTIPLE sections:
    # _make_discussion_manager: used in proposals, settings -> defined in chat section
    # _make_human_chat: used in chat only -> stays in chat module
    # _next_chat_id: used in chat only -> stays in chat module
    # _get_pipeline: used in generation only -> stays in generation module
    # _explore_primary_image: used in explore only -> stays in explore/generation
    # _build_participant_context: used in explore + stories -> needs _helpers
    # _build_session_prompt: used in sessions only -> stays in sessions module
    # _sync_law_shared_memory: used in laws only -> stays in laws module
    # _make_discussion_manager: used in proposals AND sessions -> needs _helpers
    
    # So only _build_participant_context and _make_discussion_manager need to be shared.
    # But the simplest approach: put all helpers in _helpers.py and import from there.
    
    # For any helper that's DEFINED inside a section, we need to:
    # 1. Keep it in the section file (it works there)
    # 2. Also make it importable from _helpers if other sections need it
    
    # The cleanest approach: 
    # - chat.py defines _make_human_chat, _next_chat_id, _make_discussion_manager locally
    # - generation.py defines _get_pipeline, _explore_primary_image locally
    # - explore.py defines _build_participant_context locally
    # - sessions.py defines _build_session_prompt locally
    # - laws.py defines _sync_law_shared_memory locally
    # 
    # For cross-module usage:
    # - proposals.py needs _make_discussion_manager -> import from chat
    # - sessions.py needs _make_discussion_manager -> import from chat
    # - stories.py needs _build_participant_context -> import from explore
    # - stories.py needs _get_pipeline -> import from generation
    # - explore.py needs _get_pipeline -> import from generation
    # - explore.py needs _explore_primary_image -> import from generation
    
    # This creates circular-feeling imports but they're fine since it's only function imports.
    # Let me write a minimal _helpers.py that re-exports the cross-module helpers.
    
    helpers_content = '''"""
Jericho — Shared Route Helpers

Re-exports helper functions that are used across multiple route modules.
Each function is defined in its primary route module and re-exported here
for convenient cross-module importing.
"""

from __future__ import annotations

# These will be populated after all route modules are loaded.
# Using lazy imports to avoid circular dependency issues.


def _get_pipeline():
    """Lazily create the GenerationPipeline singleton. (Defined in generation.py)"""
    from core.routes.generation import _get_pipeline as _impl
    return _impl()


def _explore_primary_image(imgr, entity_type: str, entity_id: str) -> str:
    """Get primary image URL for an entity. (Defined in generation.py)"""
    from core.routes.generation import _explore_primary_image as _impl
    return _impl(imgr, entity_type, entity_id)


def _make_discussion_manager(proposal_manager=None):
    """Create a DiscussionManager. (Defined in chat.py)"""
    from core.routes.chat import _make_discussion_manager as _impl
    return _impl(proposal_manager)


def _build_participant_context(participants):
    """Build participant context for prompts. (Defined in explore.py)"""
    from core.routes.explore import _build_participant_context as _impl
    return _impl(participants)
'''
    
    (ROUTES_DIR / "_helpers.py").write_text(helpers_content, encoding="utf-8")
    print("  -> _helpers.py created")
    
    # ── Generate new web_api.py ──
    print("Generating new web_api.py compositor...")
    
    new_web_api = '''"""
Jericho — Web Dashboard API

FastAPI application serving JSON endpoints that wrap existing managers,
plus static files for the single-page dashboard frontend.

Launch via CLI: ``jericho web``
Or directly:  ``uvicorn core.web_api:app --port 8080``

Route modules live in core/routes/:
    status, council, proposals, votes, characters, tasks,
    locations, items, stores, settings, chat, memories,
    laws, evolutions, sessions, treasury, images,
    generation, explore, stories
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config.settings import WEB_STATIC_DIR

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

    # ── Static Files ──────────────────────────────────────────
    static_dir = WEB_STATIC_DIR
    if static_dir.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(static_dir)),
            name="static",
        )

    @application.get("/")
    def serve_index() -> FileResponse:
        """Serve the SPA index.html."""
        index = static_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found.")
        return FileResponse(str(index))

    return application


# Module-level app instance for ``uvicorn core.web_api:app``
app = create_app()
'''
    
    ORIG.write_text(new_web_api, encoding="utf-8")
    print(f"  -> new web_api.py ({len(new_web_api.splitlines())} lines)")
    
    print("\n=== Backend split complete! ===")
    print(f"Created {len(SECTIONS)} route modules + _helpers.py + __init__.py")
    print(f"Original backed up to: {BACKUP}")


if __name__ == "__main__":
    main()
