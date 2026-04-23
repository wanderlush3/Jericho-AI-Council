"""
Jericho — Explore Routes
"""

from __future__ import annotations

import logging

import json as json_module
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from core.manager_cache import get_location_manager
from core.routes._helpers import (
    _get_pipeline,
    _explore_primary_image,
)
from core.injection_profiles import InjectionProfile
# F-064: _build_participant_context extracted to core/context_builder.py
# Re-exported here for backward compatibility with existing imports.
from core.context_builder import (  # noqa: F401
    build_participant_context as _build_participant_context,
    PARTICIPANT_MAX as _PARTICIPANT_MAX,
)


log = logging.getLogger(__name__)

router = APIRouter()

# ── Exploration (F-040) ───────────────────────────────────

@router.get("/api/explore")
def api_explore_list() -> list[dict[str, Any]]:
    """List all active locations with exploration data.

    Returns location info, scene counts, and primary image URLs.
    """
    from core.exploration import ExplorationManager
    from core.image_manager import ImageManager

    lmgr = get_location_manager()
    emgr = ExplorationManager()
    imgr = ImageManager()

    locations = lmgr.list_locations(status="active")
    result = []
    for loc in locations:
        # Get primary image
        primary_url = ""
        try:
            images = imgr.list_images("location", loc.id)
            primary = next(
                (img for img in images if img.is_primary), None,
            )
            if primary:
                primary_url = f"/api/images/file/{primary.id}"
            elif images:
                primary_url = f"/api/images/file/{images[0].id}"
        except Exception:
            log.debug("Failed to load location details for explore enrichment", exc_info=True)
        result.append({
            "id": loc.id,
            "name": loc.name,
            "description": loc.description,
            "tags": loc.tags,
            "status": loc.status,
            "parent_location_id": loc.parent_location_id,
            "primary_image_url": primary_url,
            "scene_count": emgr.count_scenes(loc.id),
        })
    return result

@router.get("/api/explore/{location_id}")
def api_explore_detail(location_id: str) -> dict[str, Any]:
    """Get full exploration data for a location.

    Returns location info, all scenes, navigation targets, and images.
    """
    from core.locations import LocationNotFoundError
    from core.exploration import ExplorationManager
    from core.image_manager import ImageManager

    lmgr = get_location_manager()
    emgr = ExplorationManager()
    imgr = ImageManager()

    try:
        loc = lmgr.get(location_id)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )

    # Scenes
    scenes = emgr.list_scenes(location_id)
    scene_dicts = []
    for s in scenes:
        sd = s.to_dict()
        sd["image_url"] = f"/api/images/file/{s.image_id}"
        scene_dicts.append(sd)

    # Navigation targets
    nav = ExplorationManager.get_navigation_targets(
        location_id, lmgr,
    )
    nav_data: dict[str, Any] = {"parent": None, "children": [], "siblings": []}
    if nav["parent"]:
        p = nav["parent"]
        p_img = _explore_primary_image(imgr, "location", p.id)
        nav_data["parent"] = {
            "id": p.id, "name": p.name,
            "description": p.description,
            "primary_image_url": p_img,
        }
    for child in nav["children"]:
        c_img = _explore_primary_image(imgr, "location", child.id)
        nav_data["children"].append({
            "id": child.id, "name": child.name,
            "description": child.description,
            "primary_image_url": c_img,
        })
    for sib in nav["siblings"]:
        s_img = _explore_primary_image(imgr, "location", sib.id)
        nav_data["siblings"].append({
            "id": sib.id, "name": sib.name,
            "description": sib.description,
            "primary_image_url": s_img,
        })

    # Primary image
    primary_url = _explore_primary_image(imgr, "location", location_id)

    # Location features
    features = []
    for f in (loc.features or []):
        features.append({
            "name": f.name,
            "description": f.description,
            "feature_type": getattr(f, "feature_type", "custom"),
        })

    # Exploration state (F-079)
    from core.exploration_state import ExplorationStateManager
    state_mgr = ExplorationStateManager()
    state = state_mgr.get(location_id)
    feature_names = [f["name"] for f in features]
    state_data = None
    if state is not None:
        state_data = state.to_dict()
        state_data["available_moves"] = state.get_available_moves(
            feature_names,
        )
        state_data["progress"] = state.get_exploration_progress(
            len(feature_names),
        )

    return {
        "id": loc.id,
        "name": loc.name,
        "description": loc.description,
        "lore": loc.lore,
        "tags": loc.tags,
        "status": loc.status,
        "coordinates": loc.coordinates,
        "parent_location_id": loc.parent_location_id,
        "features": features,
        "primary_image_url": primary_url,
        "scenes": scene_dicts,
        "navigation": nav_data,
        "exploration_state": state_data,
    }

@router.post("/api/explore/{location_id}/look-around")
async def api_explore_look_around(
    location_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trigger 'Look Around' scene generation for a location.

    Uses the generation pipeline to create a scene image based on
    the location's description, lore, and features.

    Optional body: {
        "target": "Great Hall",         // F-079: movement target
        "scene_type": "overview",       // scene type to record
        "template_id": "TPL-XXXX",     // override template
        "style_preset_key": "",        // style preset
        "width": 512, "height": 512,
        "participants": [              // F-042: optional participants
            {"id": "sage", "type": "council"},
            {"id": "CH-0001", "type": "character"}
        ]
    }

    When ``target`` is provided (F-079), the exploration state is
    updated and the prompt focuses on the specified area.  Valid
    targets: ``"exterior"``, a feature name, or ``"explore_further"``
    (for imaginative mode).

    Returns: {"job_id": "GEN-XXXX", "status": "queued",
              "location_id": "LOC-XXXX", "target": "...",
              "exploration_state": {...}}
    """
    from core.locations import LocationNotFoundError
    from core.exploration import ExplorationManager
    from core.exploration_state import (
        ExplorationStateManager,
        InvalidMoveError,
        FOCUS_EXTERIOR,
        FOCUS_INITIAL,
    )
    from core.generation_pipeline import (
        GenerationRequest, GenerationValidationError,
        GenerationQueueFullError,
    )

    body = body or {}

    # F-042: Validate participants
    participants = body.get("participants", [])
    if participants:
        if not isinstance(participants, list):
            raise HTTPException(
                status_code=400,
                detail="'participants' must be a list.",
            )
        if len(participants) > _PARTICIPANT_MAX:
            raise HTTPException(
                status_code=400,
                detail=f"Too many participants ({len(participants)}). "
                       f"Maximum is {_PARTICIPANT_MAX}.",
            )

    lmgr = get_location_manager()
    try:
        loc = lmgr.get(location_id)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )

    # F-079: Exploration state — get or create, then apply movement
    state_mgr = ExplorationStateManager()
    state = state_mgr.get_or_create(location_id)
    target = (body.get("target") or "").strip()

    if target:
        # Validate feature targets exist
        feature_names = [f.name for f in (loc.features or [])]
        if (
            target not in (FOCUS_EXTERIOR, "explore_further")
            and target not in feature_names
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Unknown target '{target}'. Valid targets: "
                       f"exterior, explore_further, or one of: "
                       f"{', '.join(feature_names)}",
            )
        try:
            state.move_to(target)
        except InvalidMoveError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    else:
        # No target = first look-around (exterior overview)
        if state.current_focus == FOCUS_INITIAL:
            state.move_to(FOCUS_EXTERIOR)

    # Persist updated state
    state_mgr.save(state)

    # F-079: Use focused prompt when state is active
    previous_scenes = ExplorationManager().list_scenes(location_id)
    context = ExplorationManager.build_focused_prompt(
        loc, state, previous_scenes,
    )

    # F-042: Enrich context with participant identities + world state
    # F-061: Use IMAGE_GEN profile for image generation (skip heavy layers)
    if participants:
        participant_context = _build_participant_context(
            participants, profile=InjectionProfile.IMAGE_GEN,
        )
        if participant_context:
            context = context + "\n\n" + participant_context

    # Get template — prefer body override, then "explore" assignment,
    # then fall back to "location" assignment, then error
    template_id = (body.get("template_id") or "").strip()
    if not template_id:
        try:
            from core.template_assignments import TemplateAssignmentManager
            from core.comfyui_client import WorkflowTemplateManager
            tam = TemplateAssignmentManager(
                template_manager=WorkflowTemplateManager(),
            )
            template_id = tam.get_recommended_template("explore")
            if not template_id:
                template_id = tam.get_recommended_template("location")
        except Exception:
            log.debug("Failed to load template for explore generation", exc_info=True)
    if not template_id:
        raise HTTPException(
            status_code=400,
            detail="No template specified and no default template "
                   "assigned for locations. Set one in Settings → "
                   "ComfyUI → Template Assignments.",
        )

    # Auto-set scene_type based on exploration state
    scene_type = body.get("scene_type", "")
    if not scene_type:
        if state.current_focus in (FOCUS_INITIAL, FOCUS_EXTERIOR):
            scene_type = "overview"
        elif state.mode == "imaginative":
            scene_type = "feature"  # imaginative discoveries are features
        else:
            scene_type = "feature"

    width = body.get("width", 512)
    height = body.get("height", 512)

    try:
        request = GenerationRequest.create(
            entity_type="location",
            entity_id=location_id,
            template_id=template_id,
            prompt_mode="system",
            user_prompt=context,
            style_preset_key=body.get("style_preset_key", ""),
            width=width,
            height=height,
            seed=body.get("seed", 0),
            metadata={
                "exploration": True,
                "scene_type": scene_type,
                "focus_area": state.current_focus,
                "exploration_depth": state.exploration_depth,
                "exploration_mode": state.mode,
                "participants": [
                    {"id": p.get("id"), "type": p.get("type")}
                    for p in participants
                ] if participants else [],
            },
        )
    except GenerationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    pipeline = _get_pipeline()
    try:
        job_id = pipeline.start_generation(request)
    except GenerationQueueFullError as exc:
        raise HTTPException(status_code=429, detail=str(exc))

    # Launch the pipeline execution as a background task.
    # start_generation() only creates the job entry; run_job() is
    # the async generator that actually drives the pipeline stages.
    # Without this, the job stays at "queued / 0%" forever because
    # nothing consumes the generator.
    import asyncio

    async def _run_in_background(jid: str) -> None:
        try:
            async for _progress in pipeline.run_job(jid):
                pass  # progress is recorded inside _JobState
        except Exception:
            log.exception(
                "Background generation failed for %s", jid,
            )

    asyncio.create_task(_run_in_background(job_id))

    # Build state data for response
    feature_names = [f.name for f in (loc.features or [])]
    state_resp = state.to_dict()
    state_resp["available_moves"] = state.get_available_moves(
        feature_names,
    )
    state_resp["progress"] = state.get_exploration_progress(
        len(feature_names),
    )

    return {
        "job_id": job_id,
        "status": "queued",
        "location_id": location_id,
        "target": state.current_focus,
        "exploration_state": state_resp,
    }


@router.get("/api/explore/{location_id}/state")
def api_explore_state(location_id: str) -> dict[str, Any]:
    """Get the current exploration state for a location (F-079).

    Returns the state data with available moves and progress, or
    null state if exploration hasn't started.
    """
    from core.locations import LocationNotFoundError
    from core.exploration_state import ExplorationStateManager

    lmgr = get_location_manager()
    try:
        loc = lmgr.get(location_id)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )

    state_mgr = ExplorationStateManager()
    state = state_mgr.get(location_id)
    feature_names = [f.name for f in (loc.features or [])]

    if state is None:
        return {
            "location_id": location_id,
            "started": False,
            "state": None,
        }

    state_data = state.to_dict()
    state_data["available_moves"] = state.get_available_moves(
        feature_names,
    )
    state_data["progress"] = state.get_exploration_progress(
        len(feature_names),
    )
    return {
        "location_id": location_id,
        "started": True,
        "state": state_data,
    }


@router.post("/api/explore/{location_id}/state/reset")
def api_explore_state_reset(location_id: str) -> dict[str, Any]:
    """Reset exploration state for a location (F-079).

    Clears all movement history and returns the fresh state.
    """
    from core.locations import LocationNotFoundError
    from core.exploration_state import ExplorationStateManager

    lmgr = get_location_manager()
    try:
        lmgr.get(location_id)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )

    state_mgr = ExplorationStateManager()
    state = state_mgr.reset(location_id)
    return {
        "location_id": location_id,
        "state": state.to_dict(),
        "message": "Exploration state reset successfully.",
    }

@router.get("/api/explore/{location_id}/scenes")
def api_explore_scenes(
    location_id: str,
    scene_type: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List exploration scenes for a location."""
    from core.exploration import ExplorationManager

    emgr = ExplorationManager()
    scenes = emgr.list_scenes(location_id, scene_type=scene_type)
    result = []
    for s in scenes:
        sd = s.to_dict()
        sd["image_url"] = f"/api/images/file/{s.image_id}"
        result.append(sd)
    return result

@router.delete("/api/explore/{location_id}/scenes/{scene_id}")
def api_explore_delete_scene(
    location_id: str,
    scene_id: str,
) -> dict[str, Any]:
    """Delete an exploration scene."""
    from core.exploration import ExplorationManager, SceneNotFoundError

    emgr = ExplorationManager()
    try:
        scene = emgr.get_scene(scene_id)
    except SceneNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Scene '{scene_id}' not found.",
        )
    if scene.location_id != location_id:
        raise HTTPException(
            status_code=400,
            detail=f"Scene '{scene_id}' does not belong to "
                   f"location '{location_id}'.",
        )
    emgr.delete_scene(scene_id)
    return {"status": "ok", "deleted": scene_id}

@router.post("/api/explore/{location_id}/scenes")
def api_explore_add_scene(
    location_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Manually add a scene for a location.

    Body: {"image_id": "IMG-XXXX", "scene_type": "overview",
           "description": "...", "focus_area": "..."}
    """
    from core.exploration import (
        ExplorationManager, ExplorationValidationError,
    )

    emgr = ExplorationManager()
    image_id = (body.get("image_id") or "").strip()
    if not image_id:
        raise HTTPException(
            status_code=400, detail="'image_id' is required.",
        )

    try:
        scene = emgr.add_scene(
            location_id=location_id,
            image_id=image_id,
            scene_type=body.get("scene_type", "overview"),
            description=body.get("description", ""),
            focus_area=body.get("focus_area", ""),
            metadata=body.get("metadata", {}),
        )
    except ExplorationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = scene.to_dict()
    result["image_url"] = f"/api/images/file/{scene.image_id}"
    return result

# ── Explore Chat (Location Discussion) ────────────────────

def _make_explore_chat() -> "HumanChat":
    """Instantiate HumanChat for explore chat sessions."""
    from core.routes.chat import _make_human_chat
    return _make_human_chat()


def _next_explore_chat_id() -> str:
    """Generate the next sequential EC-XXXX chat ID."""
    from config.settings import CONVERSATIONS_DIR
    existing = sorted(CONVERSATIONS_DIR.glob("H-EC-*.json"))
    if not existing:
        return "EC-0001"
    last = existing[-1].stem  # e.g. "H-EC-0042"
    num = int(last.split("-")[-1]) + 1
    return f"EC-{num:04d}"


@router.get("/api/explore/{location_id}/chat/active")
def api_explore_chat_active(location_id: str) -> dict[str, Any]:
    """Find the active (non-closed) explore chat for a location.

    Returns: {"chat_id": "EC-XXXX", "chat": {...}} or {"chat_id": null}
    """
    hc = _make_explore_chat()
    chats = hc.list_chats(closed=False)
    for c in chats:
        meta = c.metadata or {}
        if (
            meta.get("explore_location_id") == location_id
            and not c.closed_at
        ):
            return {"chat_id": c.chat_id, "chat": c.to_dict()}
    return {"chat_id": None}


@router.post("/api/explore/{location_id}/chat")
def api_explore_chat_create(
    location_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create an explore chat session for a location.

    Body: {
        "participants": [
            {"id": "sage", "type": "council"},
            {"id": "CH-0001", "type": "character"}
        ]
    }

    Returns: the created chat record.
    """
    from core.locations import LocationNotFoundError
    from core.human_chat import HumanChatValidationError

    body = body or {}
    participants = body.get("participants", [])

    lmgr = get_location_manager()
    try:
        loc = lmgr.get(location_id)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )

    if not participants:
        raise HTTPException(
            status_code=400,
            detail="At least one participant is required.",
        )

    # Separate council members and characters
    council_ids = [
        p["id"] for p in participants if p.get("type") == "council"
    ]
    character_ids = [
        p["id"] for p in participants if p.get("type") == "character"
    ]

    # Need at least one council member or character
    first_member = ""
    first_character = ""
    if council_ids:
        first_member = council_ids[0]
    if character_ids:
        first_character = character_ids[0]

    hc = _make_explore_chat()
    chat_id = _next_explore_chat_id()

    try:
        rec = hc.create_chat(
            chat_id,
            title=f"Exploring {loc.name}",
            member_name=first_member,
            character_id=first_character,
            topic=f"Exploring location: {loc.name}",
            metadata={
                "explore_location_id": location_id,
                "location_name": loc.name,
                "location_description": loc.description or "",
                "location_lore": loc.lore or "",
            },
        )
    except HumanChatValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Add remaining council members beyond the first
    for cid in council_ids[1:]:
        try:
            rec = hc.add_council_member(chat_id, cid)
        except Exception:
            log.debug("Failed to add council member %s to explore chat", cid, exc_info=True)

    # Add remaining characters beyond the first
    for chid in character_ids[1 if not first_member else 0:]:
        if chid == first_character:
            continue
        try:
            rec = hc.add_character(chat_id, chid)
        except Exception:
            log.debug("Failed to add character %s to explore chat", chid, exc_info=True)

    return rec.to_dict()


@router.post("/api/explore/{location_id}/chat/{chat_id}/inject-scene")
async def api_explore_chat_inject_scene(
    location_id: str,
    chat_id: str,
    body: dict[str, Any] | None = None,
):
    """Inject the Look Around prompt into the chat and trigger discussion.

    Body: {
        "prompt_text": "...",   // the prompt used for scene generation
        "image_url": "..."      // optional: URL of the generated image
    }

    Returns: SSE stream of participant responses, same format as chat.
    """
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    body = body or {}
    prompt_text = (body.get("prompt_text") or "").strip()
    image_url = (body.get("image_url") or "").strip()

    if not prompt_text:
        raise HTTPException(
            status_code=400,
            detail="'prompt_text' is required.",
        )

    async def event_generator():
        try:
            hc = _make_explore_chat()

            # Inject the scene description as a narrator message
            narrator_content = f"🌍 **Scene Description:**\n\n{prompt_text}"
            if image_url:
                narrator_content += f"\n\n![Scene]({image_url})"

            hc.send_human_message(
                chat_id,
                narrator_content,
                metadata={
                    "type": "scene_inject",
                    "location_id": location_id,
                    "image_url": image_url,
                },
            )

            # Auto-resume if paused
            rec = hc.get(chat_id)
            if rec.paused:
                hc.resume_chat(chat_id)

            # Stream participant responses
            t_start = time.monotonic()
            async for member_name, response, record in hc.get_agent_response_streaming(chat_id):
                t_end = time.monotonic()
                response_time_ms = round((t_end - t_start) * 1000)
                content_text = response.content or ""
                event_data = json_module.dumps({
                    "speaker": member_name,
                    "content": content_text,
                    "model": response.model,
                    "provider": response.provider,
                    "response_time_ms": response_time_ms,
                })
                yield f"event: message\ndata: {event_data}\n\n"
                t_start = time.monotonic()

            # Send final state
            final_record = hc.get(chat_id)
            done_data = json_module.dumps({"chat": final_record.to_dict()})
            yield f"event: done\ndata: {done_data}\n\n"

        except HumanChatNotFoundError:
            err = json_module.dumps({"detail": f"Chat '{chat_id}' not found."})
            yield f"event: error\ndata: {err}\n\n"
        except (HumanChatError, Exception) as exc:
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


@router.post("/api/explore/{location_id}/chat/{chat_id}/send-stream")
async def api_explore_chat_send_stream(
    location_id: str,
    chat_id: str,
    body: dict[str, Any],
):
    """Send a human message in the explore chat and stream responses.

    Body: {"content": "..."}

    Returns: SSE stream of participant responses.
    """
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(
            status_code=400,
            detail="'content' is required.",
        )

    async def event_generator():
        try:
            hc = _make_explore_chat()

            # Auto-resume if paused
            rec = hc.get(chat_id)
            if rec.paused:
                hc.resume_chat(chat_id)

            hc.send_human_message(chat_id, content)

            t_start = time.monotonic()
            async for member_name, response, record in hc.get_agent_response_streaming(chat_id):
                t_end = time.monotonic()
                response_time_ms = round((t_end - t_start) * 1000)
                content_text = response.content or ""
                event_data = json_module.dumps({
                    "speaker": member_name,
                    "content": content_text,
                    "model": response.model,
                    "provider": response.provider,
                    "response_time_ms": response_time_ms,
                })
                yield f"event: message\ndata: {event_data}\n\n"
                t_start = time.monotonic()

            final_record = hc.get(chat_id)
            done_data = json_module.dumps({"chat": final_record.to_dict()})
            yield f"event: done\ndata: {done_data}\n\n"

        except HumanChatNotFoundError:
            err = json_module.dumps({"detail": f"Chat '{chat_id}' not found."})
            yield f"event: error\ndata: {err}\n\n"
        except (HumanChatError, Exception) as exc:
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


@router.post("/api/explore/{location_id}/chat/{chat_id}/continue-stream")
async def api_explore_chat_continue_stream(
    location_id: str,
    chat_id: str,
):
    """Trigger one round of AI-to-AI discussion in explore chat.

    Returns: SSE stream of participant responses.
    """
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    async def event_generator():
        try:
            hc = _make_explore_chat()

            t_start = time.monotonic()
            async for member_name, response, record in hc.continue_conversation_streaming(chat_id):
                t_end = time.monotonic()
                response_time_ms = round((t_end - t_start) * 1000)
                content_text = response.content or ""
                event_data = json_module.dumps({
                    "speaker": member_name,
                    "content": content_text,
                    "model": response.model,
                    "provider": response.provider,
                    "response_time_ms": response_time_ms,
                })
                yield f"event: message\ndata: {event_data}\n\n"
                t_start = time.monotonic()

            final_record = hc.get(chat_id)
            done_data = json_module.dumps({"chat": final_record.to_dict()})
            yield f"event: done\ndata: {done_data}\n\n"

        except HumanChatNotFoundError:
            err = json_module.dumps({"detail": f"Chat '{chat_id}' not found."})
            yield f"event: error\ndata: {err}\n\n"
        except (HumanChatError, Exception) as exc:
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


# ── Stories (F-041) ──────────────────────────────────────
