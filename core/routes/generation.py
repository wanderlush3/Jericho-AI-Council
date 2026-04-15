"""
Jericho — Generation Routes
"""

from __future__ import annotations

import logging


import json as json_module
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from core.manager_cache import (
    get_api_client,
    get_character_manager,
    get_item_manager,
    get_location_manager,
    get_registry,
    get_store_manager,
)


log = logging.getLogger(__name__)

router = APIRouter()



# ── Generation Pipeline (F-037f) ─────────────────────────

# Module-level pipeline singleton — created once, persists across requests
_generation_pipeline = None

def _get_pipeline():
    """Lazily create the GenerationPipeline singleton."""
    global _generation_pipeline
    if _generation_pipeline is None:
        import os
        from core.generation_pipeline import GenerationPipeline
        from core.comfyui_client import (
            ComfyUIClient, ComfyUIConfig, WorkflowTemplateManager,
        )
        from core.image_manager import ImageManager
        from core.prompt_builder import PromptBuilder
        from core.registry import CouncilRegistry
        from core.api_client import APIClient
        from core.characters import CharacterManager
        from core.locations import LocationManager
        from config.settings import (
            COMFYUI_DEFAULT_HOST, COMFYUI_DEFAULT_PORT,
            COMFYUI_HOST_ENV, COMFYUI_PORT_ENV,
        )

        # Read user-configured ComfyUI address from env vars
        host = os.environ.get(COMFYUI_HOST_ENV, "").strip() or COMFYUI_DEFAULT_HOST
        port_str = os.environ.get(COMFYUI_PORT_ENV, "").strip()
        try:
            port = int(port_str) if port_str else COMFYUI_DEFAULT_PORT
        except ValueError:
            port = COMFYUI_DEFAULT_PORT
        comfyui_config = ComfyUIConfig(host=host, port=port)

        # Build a fully-wired PromptBuilder so all prompt modes work
        try:
            registry = get_registry()
        except Exception:
            registry = None
        try:
            api_client = get_api_client()
        except Exception:
            api_client = None

        _generation_pipeline = GenerationPipeline(
            comfyui_client=ComfyUIClient(comfyui_config),
            template_manager=WorkflowTemplateManager(),
            image_manager=ImageManager(),
            prompt_builder=PromptBuilder(
                api_client=api_client,
                registry=registry,
                character_manager=CharacterManager(),
                location_manager=LocationManager(),
                item_manager=get_item_manager(),
                store_manager=get_store_manager(),
            ),
        )
    return _generation_pipeline

def _explore_primary_image(imgr: Any, entity_type: str, entity_id: str) -> str:
    """Get primary image URL for an entity, or empty string."""
    try:
        images = imgr.list_images(entity_type, entity_id)
        primary = next(
            (img for img in images if img.is_primary), None,
        )
        if primary:
            return f"/api/images/file/{primary.id}"
        elif images:
            return f"/api/images/file/{images[0].id}"
    except Exception:
        log.debug("core.routes.generation: non-critical error", exc_info=True)
    return ""

@router.post("/api/generate/prompts")
async def api_generate_prompts(body: dict[str, Any]) -> dict[str, Any]:
    """Preview prompts for council_vote mode (or any mode).

    This generates prompts WITHOUT queueing to ComfyUI —
    used by the frontend to show prompt options before generating.

    Body: same as /api/generate/{entity_type}/{entity_id}

    Returns: {"prompts": [{"positive": "...", "negative": "...", "member_name": "..."}, ...]}
    """
    from core.prompt_builder import (
        PromptBuilder, PromptRequest, PromptResult,
        get_style_preset, PromptValidationError,
    )
    from core.registry import CouncilRegistry
    from core.api_client import APIClient

    prompt_mode = body.get("prompt_mode", "system")
    member_name = body.get("member_name", "")
    user_prompt = body.get("user_prompt", "")
    style_preset_key = body.get("style_preset_key", "")
    participants = body.get("participants", [])
    entity_type = body.get("entity_type", "")
    entity_id = body.get("entity_id", "")

    style_preset = None
    if style_preset_key:
        style_preset = get_style_preset(style_preset_key)

    try:
        prompt_request = PromptRequest.create(
            prompt_mode,
            entity_type=entity_type,
            entity_id=entity_id,
            member_name=member_name,
            user_prompt=user_prompt,
            style_preset=style_preset,
            participants=participants if participants else None,
        )
    except PromptValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Build prompt builder with live connections (cached)
    try:
        builder = PromptBuilder(
            api_client=get_api_client(),
            registry=get_registry(),
            character_manager=get_character_manager(),
            location_manager=get_location_manager(),
            item_manager=get_item_manager(),
            store_manager=get_store_manager(),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to initialize prompt builder: {exc}",
        )

    try:
        result = await builder.generate(prompt_request)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Prompt generation failed: {exc}",
        )

    if isinstance(result, list):
        prompts = [
            {
                "positive": r.positive,
                "negative": r.negative,
                "member_name": r.member_name,
                "mode": r.mode,
            }
            for r in result
        ]
    else:
        prompts = [{
            "positive": result.positive,
            "negative": result.negative,
            "member_name": result.member_name,
            "mode": result.mode,
        }]

    return {"prompts": prompts}

@router.post("/api/generate/cancel/{job_id}")
def api_generate_cancel(job_id: str) -> dict[str, Any]:
    """Cancel a running generation job."""
    from core.generation_pipeline import GenerationNotFoundError

    pipeline = _get_pipeline()
    try:
        progress = pipeline.cancel_job(job_id)
    except GenerationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    return progress.to_dict()

@router.get("/api/generate/stream/{job_id}")
async def api_generate_stream(job_id: str) -> StreamingResponse:
    """SSE stream of generation progress for a job.

    Events:
        - event: progress — {job_id, stage, progress_pct, message, prompt_positive, prompt_negative}
        - event: done     — {job_id, stage: "completed", image_id, ...}
        - event: error    — {job_id, stage: "failed", error, ...}
    """
    from core.generation_pipeline import GenerationNotFoundError

    pipeline = _get_pipeline()

    async def event_generator():
        try:
            async for progress in pipeline.run_job(job_id):
                data = json_module.dumps(progress.to_dict())
                if progress.stage == "completed":
                    yield f"event: done\ndata: {data}\n\n"
                elif progress.stage in ("failed", "cancelled"):
                    yield f"event: error\ndata: {data}\n\n"
                else:
                    yield f"event: progress\ndata: {data}\n\n"
        except GenerationNotFoundError:
            err = json_module.dumps({"detail": f"Job '{job_id}' not found."})
            yield f"event: error\ndata: {err}\n\n"
        except Exception as exc:
            err = json_module.dumps({"detail": str(exc)})
            yield f"event: error\ndata: {err}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/api/generate/jobs")
def api_generate_jobs(
    active_only: bool = Query(False),
) -> list[dict[str, Any]]:
    """List all generation jobs."""
    pipeline = _get_pipeline()
    return pipeline.list_jobs(active_only=active_only)

@router.get("/api/generate/jobs/{job_id}")
def api_generate_job_detail(job_id: str) -> dict[str, Any]:
    """Get details for a single generation job."""
    from core.generation_pipeline import GenerationNotFoundError

    pipeline = _get_pipeline()
    try:
        return pipeline.get_job(job_id)
    except GenerationNotFoundError:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

@router.post("/api/generate/batch")
async def api_generate_batch(body: dict[str, Any]) -> dict[str, Any]:
    """Batch generate images for multiple entities of the same type.

    Body: {
        "entity_type": "character",
        "entity_ids": ["CH-0001", "CH-0002", ...],
        "template_id": "TPL-0001",
        "prompt_mode": "system",
        "member_name": "",
        "user_prompt": "",
        "style_preset_key": "",
        "participants": [],
        "selected_prompt_index": 0,
        "width": 512,
        "height": 512,
        "seed": 0
    }

    Returns: {"job_ids": ["GEN-0001", ...], "count": N}
    """
    from core.generation_pipeline import (
        GenerationRequest, GenerationValidationError,
        GenerationQueueFullError,
    )
    from core.image_manager import VALID_ENTITY_TYPES

    entity_type = (body.get("entity_type") or "").strip()
    entity_ids = body.get("entity_ids", [])
    template_id = (body.get("template_id") or "").strip()

    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type '{entity_type}'. "
                   f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    if not entity_ids or not isinstance(entity_ids, list):
        raise HTTPException(
            status_code=400,
            detail="'entity_ids' must be a non-empty list.",
        )

    if len(entity_ids) > 10:
        raise HTTPException(
            status_code=400,
            detail=f"Batch size {len(entity_ids)} exceeds maximum of 10.",
        )

    if not template_id:
        raise HTTPException(
            status_code=400,
            detail="'template_id' is required.",
        )

    # Build a GenerationRequest for each entity
    requests = []
    for eid in entity_ids:
        try:
            req = GenerationRequest.create(
                entity_type=entity_type,
                entity_id=str(eid).strip(),
                template_id=template_id,
                prompt_mode=body.get("prompt_mode", "system"),
                member_name=body.get("member_name", ""),
                user_prompt=body.get("user_prompt", ""),
                style_preset_key=body.get("style_preset_key", ""),
                participants=body.get("participants", []),
                selected_prompt_index=body.get("selected_prompt_index", 0),
                width=body.get("width", 512),
                height=body.get("height", 512),
                seed=body.get("seed", 0),
            )
            requests.append(req)
        except GenerationValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Validation error for entity '{eid}': {exc}",
            )

    pipeline = _get_pipeline()
    try:
        job_ids = pipeline.start_batch_generation(requests)
    except GenerationQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except GenerationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"job_ids": job_ids, "count": len(job_ids)}

# NOTE: This catch-all route MUST come AFTER specific /api/generate/ routes
# to avoid route matching conflicts (e.g. "cancel" matching as entity_type).
@router.post("/api/generate/{entity_type}/{entity_id}")
async def api_generate_start(
    entity_type: str, entity_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Start an image generation job for an entity.

    Body: {
        "template_id": "TPL-0001",
        "prompt_mode": "system",       // system|character|raw_user|user_refined|council_vote
        "member_name": "",             // required for character/user_refined
        "user_prompt": "",             // required for raw_user/user_refined
        "style_preset_key": "",        // optional, e.g. "fantasy_art"
        "participants": [],            // required for council_vote (2+ names)
        "selected_prompt_index": 0,    // for council_vote: which prompt to use
        "width": 512,
        "height": 512,
        "seed": 0                      // 0 = random
    }

    Returns: {"job_id": "GEN-0001", "status": "queued"}
    """
    from core.generation_pipeline import (
        GenerationRequest, GenerationValidationError,
        GenerationQueueFullError,
    )
    from core.image_manager import VALID_ENTITY_TYPES

    if entity_type not in VALID_ENTITY_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid entity type '{entity_type}'. "
                   f"Must be one of: {', '.join(sorted(VALID_ENTITY_TYPES))}",
        )

    template_id = (body.get("template_id") or "").strip()
    if not template_id:
        raise HTTPException(status_code=400, detail="'template_id' is required.")

    try:
        request = GenerationRequest.create(
            entity_type=entity_type,
            entity_id=entity_id,
            template_id=template_id,
            prompt_mode=body.get("prompt_mode", "system"),
            member_name=body.get("member_name", ""),
            user_prompt=body.get("user_prompt", ""),
            style_preset_key=body.get("style_preset_key", ""),
            participants=body.get("participants", []),
            selected_prompt_index=body.get("selected_prompt_index", 0),
            width=body.get("width", 512),
            height=body.get("height", 512),
            seed=body.get("seed", 0),
        )
    except GenerationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    pipeline = _get_pipeline()
    try:
        job_id = pipeline.start_generation(request)
    except GenerationQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except GenerationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"job_id": job_id, "status": "queued"}

# ── Participants (F-042) ─────────────────────────────────

_PARTICIPANT_MAX = 10

@router.get("/api/participants/available")
def api_participants_available() -> list[dict[str, Any]]:
    """Return a merged list of council members and active characters.

    Each entry has: id, name, type ('council'|'character'),
    description, avatar_url.  Used by Explore and Story UIs
    to populate the participant selector.
    """
    from config.settings import COUNCIL_AVATARS_DIR, CHARACTER_AVATARS_DIR

    result: list[dict[str, Any]] = []

    # Council members
    try:
        registry = get_registry()
        # Single directory scan for avatar existence (Category 5)
        existing_council_avatars = {
            f.stem.lower() for f in COUNCIL_AVATARS_DIR.glob("*.png")
        } if COUNCIL_AVATARS_DIR.exists() else set()
        for m in registry.list_members():
            avatar_url = ""
            if m.name.lower() in existing_council_avatars:
                avatar_url = f"/api/council/{m.name}/avatar"
            result.append({
                "id": m.name.lower(),
                "name": m.name,
                "type": "council",
                "description": m.description or m.role,
                "role": m.role,
                "avatar_url": avatar_url,
            })
    except Exception:
        log.debug("core.routes.generation: non-critical error", exc_info=True)
    try:
        cmgr = get_character_manager()
        # Single directory scan for avatar existence (Category 5)
        existing_char_avatars = {
            f.stem for f in CHARACTER_AVATARS_DIR.glob("*.png")
        } if CHARACTER_AVATARS_DIR.exists() else set()
        for c in cmgr.list_characters(status="active"):
            avatar_url = ""
            if c.id in existing_char_avatars:
                avatar_url = f"/api/characters/{c.id}/avatar"
            result.append({
                "id": c.id,
                "name": c.name,
                "type": "character",
                "description": c.description or "",
                "role": "",
                "avatar_url": avatar_url,
            })
    except Exception:
        log.debug("core.routes.generation: non-critical error", exc_info=True)
    return result
