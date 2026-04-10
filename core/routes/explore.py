"""
Jericho — Explore Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.routes._helpers import (
    _get_pipeline,
    _explore_primary_image,
)


router = APIRouter()

_PARTICIPANT_MAX = 10

def _build_participant_context(
    participants: list[dict[str, Any]],
) -> str:
    """Build rich markdown context for selected participants.

    Injects:
    - Council members: persona, core beliefs, relevant memories
    - Characters: full description, backstory, traits, system prompt
    - Shared world context: active laws, locations, items

    Args:
        participants: List of {"id": "...", "type": "council"|"character"}

    Returns:
        Markdown text suitable for prompt injection.
    """
    if not participants:
        return ""

    parts: list[str] = []
    parts.append("\n## Present Participants\n")

    # Separate by type
    council_ids = [
        p["id"] for p in participants if p.get("type") == "council"
    ]
    character_ids = [
        p["id"] for p in participants if p.get("type") == "character"
    ]

    # ── Council Members ──
    if council_ids:
        try:
            from core.registry import CouncilRegistry
            registry = CouncilRegistry().load()
            members_map = {
                m.name.lower(): m for m in registry.list_members()
            }
        except Exception:
            members_map = {}

        # Memory influence engine (may not be available)
        mi = None
        try:
            from core.memory_influence import MemoryInfluence
            mi = MemoryInfluence(embedding_provider=None)
        except Exception:
            pass

        for cid in council_ids:
            member = members_map.get(cid.lower())
            if not member:
                parts.append(f"### 🏛️ Council Member: {cid}")
                parts.append("*(Member data unavailable)*\n")
                continue

            parts.append(f"### 🏛️ Council Member: {member.name}")
            parts.append(f"**Role:** {member.role}")
            if member.description:
                parts.append(f"**Description:** {member.description}")
            if member.system_prompt:
                prompt_preview = member.system_prompt[:500]
                parts.append(
                    f"**Persona:** {prompt_preview}"
                    + ("…" if len(member.system_prompt) > 500 else "")
                )
            if member.specialties:
                parts.append(
                    f"**Specialties:** {', '.join(member.specialties)}"
                )

            # Inject core beliefs and memories via MemoryInfluence
            if mi:
                try:
                    ctx = mi.build_context(
                        member.name,
                        ["exploration", "location", "scene"],
                    )
                    if ctx.beliefs:
                        parts.append("\n**Core Beliefs:**")
                        for sb in ctx.beliefs[:5]:
                            parts.append(
                                f"- **{sb.belief.topic}**: "
                                f"{sb.belief.content}"
                            )
                    if ctx.memories:
                        parts.append("\n**Relevant Memories:**")
                        for sm in ctx.memories[:5]:
                            parts.append(
                                f"- [{sm.entry.event_type}] "
                                f"{sm.entry.content}"
                            )
                except Exception:
                    pass

            parts.append("")  # blank separator

    # ── Characters ──
    if character_ids:
        try:
            from core.characters import CharacterManager
            cmgr = CharacterManager()
        except Exception:
            cmgr = None

        for char_id in character_ids:
            if cmgr is None:
                parts.append(f"### 🎭 Character: {char_id}")
                parts.append("*(Character data unavailable)*\n")
                continue

            try:
                char = cmgr.get(char_id)
            except Exception:
                parts.append(f"### 🎭 Character: {char_id}")
                parts.append("*(Character not found)*\n")
                continue

            parts.append(f"### 🎭 Character: {char.name}")
            if char.description:
                parts.append(f"**Description:** {char.description}")
            if char.backstory:
                backstory_preview = char.backstory[:500]
                parts.append(
                    f"**Backstory:** {backstory_preview}"
                    + ("…" if len(char.backstory) > 500 else "")
                )
            if char.traits:
                trait_strs = [
                    f"{t.name} ({t.trait_type}, "
                    f"{int(t.intensity * 100)}%)"
                    for t in char.traits[:8]
                ]
                parts.append(f"**Traits:** {', '.join(trait_strs)}")
            if char.system_prompt:
                prompt_preview = char.system_prompt[:500]
                parts.append(
                    f"**Persona:** {prompt_preview}"
                    + ("…" if len(char.system_prompt) > 500 else "")
                )
            parts.append("")

    # ── Shared World Context ──
    parts.append("\n## World Context\n")

    # Active Laws
    try:
        from core.laws import LawManager
        lmgr = LawManager()
        active_laws = lmgr.list_laws(status="active")
        if active_laws:
            parts.append("### Active Laws")
            for law in active_laws[:10]:
                parts.append(
                    f"- **{law.title}**: {law.description[:200]}"
                )
            parts.append("")
    except Exception:
        pass

    # Active Locations
    try:
        from core.locations import LocationManager
        loc_mgr = LocationManager()
        active_locs = loc_mgr.list_locations(status="active")
        if active_locs:
            parts.append("### Known Locations")
            for loc in active_locs[:10]:
                line = f"- **{loc.name}**: {loc.description[:150]}"
                if loc.lore:
                    line += f" — {loc.lore[:100]}"
                parts.append(line)
            parts.append("")
    except Exception:
        pass

    # Active Items
    try:
        from core.items import ItemManager
        imr = ItemManager()
        active_items = imr.list_items(status="active")
        if active_items:
            parts.append("### Known Items")
            for item in active_items[:10]:
                line = f"- **{item.name}**: {item.description[:150]}"
                if item.rarity:
                    line += f" [{item.rarity}]"
                parts.append(line)
            parts.append("")
    except Exception:
        pass

    return "\n".join(parts)

# ── Exploration (F-040) ───────────────────────────────────

@router.get("/api/explore")
def api_explore_list() -> list[dict[str, Any]]:
    """List all active locations with exploration data.

    Returns location info, scene counts, and primary image URLs.
    """
    from core.locations import LocationManager
    from core.exploration import ExplorationManager
    from core.image_manager import ImageManager

    lmgr = LocationManager()
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
            pass

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
    from core.locations import LocationManager, LocationNotFoundError
    from core.exploration import ExplorationManager
    from core.image_manager import ImageManager

    lmgr = LocationManager()
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
        "scene_type": "overview",      // scene type to record
        "template_id": "TPL-XXXX",     // override template
        "style_preset_key": "",        // style preset
        "width": 512, "height": 512,
        "participants": [              // F-042: optional participants
            {"id": "sage", "type": "council"},
            {"id": "CH-0001", "type": "character"}
        ]
    }

    Returns: {"job_id": "GEN-XXXX", "status": "queued",
              "location_id": "LOC-XXXX"}
    """
    from core.locations import LocationManager, LocationNotFoundError
    from core.exploration import ExplorationManager
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

    lmgr = LocationManager()
    try:
        loc = lmgr.get(location_id)
    except LocationNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Location '{location_id}' not found.",
        )

    # Build look-around description for the prompt
    context = ExplorationManager.build_look_around_description(loc)

    # F-042: Enrich context with participant identities + world state
    if participants:
        participant_context = _build_participant_context(participants)
        if participant_context:
            context = context + "\n\n" + participant_context

    # Get template — prefer body override, then recommended,
    # then fall back to error
    template_id = (body.get("template_id") or "").strip()
    if not template_id:
        try:
            from core.template_assignments import TemplateAssignmentManager
            from core.comfyui_client import WorkflowTemplateManager
            tam = TemplateAssignmentManager(
                template_manager=WorkflowTemplateManager(),
            )
            template_id = tam.get_recommended_template("location")
        except Exception:
            pass
    if not template_id:
        raise HTTPException(
            status_code=400,
            detail="No template specified and no default template "
                   "assigned for locations. Set one in Settings → "
                   "ComfyUI → Template Assignments.",
        )

    scene_type = body.get("scene_type", "overview")
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
            import logging
            logging.getLogger(__name__).exception(
                "Background generation failed for %s", jid,
            )

    asyncio.create_task(_run_in_background(job_id))

    return {
        "job_id": job_id,
        "status": "queued",
        "location_id": location_id,
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
           "description": "..."}
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
            metadata=body.get("metadata", {}),
        )
    except ExplorationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    result = scene.to_dict()
    result["image_url"] = f"/api/images/file/{scene.image_id}"
    return result

# ── Stories (F-041) ──────────────────────────────────────

