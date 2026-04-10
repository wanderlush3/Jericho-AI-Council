"""
Jericho — Stories Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query

from core.routes._helpers import (
    _get_pipeline,
    _build_participant_context,
)


router = APIRouter()

_PARTICIPANT_MAX = 10

@router.get("/api/stories")
def api_stories_list(
    status: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List all stories, optionally filtered by status."""
    from core.story import StoryManager

    smgr = StoryManager()
    stories = smgr.list_stories(status=status)
    result = []
    for s in stories:
        result.append({
            "story_id": s.story_id,
            "title": s.title,
            "synopsis": s.synopsis,
            "author": s.author,
            "status": s.status,
            "style_preset_key": s.style_preset_key,
            "template_id": s.template_id,
            "chapter_count": len(s.chapters),
            "scene_count": sum(
                len(ch.scenes) for ch in s.chapters
            ),
            "illustration_count": sum(
                1 for ch in s.chapters
                for sc in ch.scenes if sc.image_id
            ),
            "entity_refs": s.entity_refs,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })
    return result

@router.post("/api/stories")
def api_stories_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new story.

    Body: {"title": "...", "synopsis": "...", "author": "...",
           "style_preset_key": "", "template_id": ""}
    """
    from core.story import StoryManager, StoryValidationError

    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(
            status_code=400, detail="'title' is required.",
        )

    smgr = StoryManager()
    try:
        story = smgr.create(
            title,
            body.get("synopsis", ""),
            author=body.get("author", ""),
            style_preset_key=body.get("style_preset_key", ""),
            template_id=body.get("template_id", ""),
            metadata=body.get("metadata"),
        )
    except StoryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return story.to_dict()

@router.get("/api/stories/{story_id}")
def api_stories_detail(story_id: str) -> dict[str, Any]:
    """Get a full story with chapters and scenes."""
    from core.story import StoryManager, StoryNotFoundError

    smgr = StoryManager()
    try:
        story = smgr.get(story_id)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )

    d = story.to_dict()
    # Enrich scenes with image URLs
    for ch in d.get("chapters", []):
        for sc in ch.get("scenes", []):
            if sc.get("image_id"):
                sc["image_url"] = f"/api/images/file/{sc['image_id']}"
            else:
                sc["image_url"] = ""
    return d

@router.put("/api/stories/{story_id}")
def api_stories_update(
    story_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Update story fields.

    Body: {"title": "...", "synopsis": "...",
           "style_preset_key": "...", "template_id": "..."}
    """
    from core.story import (
        StoryManager, StoryNotFoundError, StoryValidationError,
    )

    smgr = StoryManager()
    try:
        updated = smgr.update(
            story_id,
            title=body.get("title"),
            synopsis=body.get("synopsis"),
            style_preset_key=body.get("style_preset_key"),
            template_id=body.get("template_id"),
            metadata=body.get("metadata"),
        )
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except StoryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return updated.to_dict()

@router.put("/api/stories/{story_id}/status")
def api_stories_update_status(
    story_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Transition a story's lifecycle status.

    Body: {"status": "active"}
    """
    from core.story import (
        StoryManager, StoryNotFoundError,
        StoryValidationError, StoryLifecycleError,
    )

    new_status = (body.get("status") or "").strip()
    if not new_status:
        raise HTTPException(
            status_code=400, detail="'status' is required.",
        )

    smgr = StoryManager()
    try:
        updated = smgr.update_status(story_id, new_status)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except StoryLifecycleError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except StoryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return updated.to_dict()

@router.delete("/api/stories/{story_id}")
def api_stories_delete(story_id: str) -> dict[str, Any]:
    """Delete a story."""
    from core.story import StoryManager, StoryNotFoundError

    smgr = StoryManager()
    try:
        smgr.delete(story_id)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    return {"status": "ok", "deleted": story_id}

# ── Stories: Chapters ────────────────────────────────────

@router.post("/api/stories/{story_id}/chapters")
def api_stories_add_chapter(
    story_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Add a chapter to a story.

    Body: {"title": "Chapter 1", "synopsis": "..."}
    """
    from core.story import (
        StoryManager, StoryNotFoundError, StoryValidationError,
    )

    smgr = StoryManager()
    try:
        chapter = smgr.add_chapter(
            story_id,
            title=body.get("title", ""),
            synopsis=body.get("synopsis", ""),
            metadata=body.get("metadata"),
        )
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except StoryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return chapter.to_dict()

@router.put("/api/stories/{story_id}/chapters/{chapter_id}")
def api_stories_update_chapter(
    story_id: str,
    chapter_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Update a chapter's title or synopsis.

    Body: {"title": "...", "synopsis": "..."}
    """
    from core.story import (
        StoryManager, StoryNotFoundError, ChapterNotFoundError,
    )

    smgr = StoryManager()
    try:
        chapter = smgr.update_chapter(
            story_id, chapter_id,
            title=body.get("title"),
            synopsis=body.get("synopsis"),
        )
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except ChapterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter '{chapter_id}' not found.",
        )

    return chapter.to_dict()

@router.delete("/api/stories/{story_id}/chapters/{chapter_id}")
def api_stories_delete_chapter(
    story_id: str,
    chapter_id: str,
) -> dict[str, Any]:
    """Delete a chapter and all its scenes."""
    from core.story import (
        StoryManager, StoryNotFoundError, ChapterNotFoundError,
    )

    smgr = StoryManager()
    try:
        smgr.delete_chapter(story_id, chapter_id)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except ChapterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter '{chapter_id}' not found.",
        )
    return {"status": "ok", "deleted": chapter_id}

# ── Stories: Scenes ──────────────────────────────────────

@router.post(
    "/api/stories/{story_id}/chapters/{chapter_id}/scenes",
)
def api_stories_add_scene(
    story_id: str,
    chapter_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Add a scene to a chapter.

    Body: {"narrative_text": "...", "characters": ["CH-0001"],
           "location_id": "LOC-0001", "mood": "tense"}
    """
    from core.story import (
        StoryManager, StoryNotFoundError,
        ChapterNotFoundError, StoryValidationError,
    )

    smgr = StoryManager()
    try:
        scene = smgr.add_scene(
            story_id, chapter_id,
            narrative_text=body.get("narrative_text", ""),
            characters=body.get("characters"),
            location_id=body.get("location_id", ""),
            mood=body.get("mood", ""),
            metadata=body.get("metadata"),
        )
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except ChapterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter '{chapter_id}' not found.",
        )
    except StoryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return scene.to_dict()

@router.put(
    "/api/stories/{story_id}/chapters/{chapter_id}/scenes/{scene_id}",
)
def api_stories_update_scene(
    story_id: str,
    chapter_id: str,
    scene_id: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    """Update a scene's fields.

    Body: {"narrative_text": "...", "characters": [...],
           "location_id": "...", "mood": "..."}
    """
    from core.story import (
        StoryManager, StoryNotFoundError,
        ChapterNotFoundError, SceneNotFoundError,
    )

    smgr = StoryManager()
    try:
        scene = smgr.update_scene(
            story_id, chapter_id, scene_id,
            narrative_text=body.get("narrative_text"),
            characters=body.get("characters"),
            location_id=body.get("location_id"),
            mood=body.get("mood"),
            image_id=body.get("image_id"),
            prompt_used=body.get("prompt_used"),
        )
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except ChapterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter '{chapter_id}' not found.",
        )
    except SceneNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Scene '{scene_id}' not found.",
        )

    d = scene.to_dict()
    if scene.image_id:
        d["image_url"] = f"/api/images/file/{scene.image_id}"
    return d

@router.delete(
    "/api/stories/{story_id}/chapters/{chapter_id}/scenes/{scene_id}",
)
def api_stories_delete_scene(
    story_id: str,
    chapter_id: str,
    scene_id: str,
) -> dict[str, Any]:
    """Delete a scene."""
    from core.story import (
        StoryManager, StoryNotFoundError,
        ChapterNotFoundError, SceneNotFoundError,
    )

    smgr = StoryManager()
    try:
        smgr.delete_scene(story_id, chapter_id, scene_id)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )
    except ChapterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter '{chapter_id}' not found.",
        )
    except SceneNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Scene '{scene_id}' not found.",
        )
    return {"status": "ok", "deleted": scene_id}

# ── Stories: Narrate & Illustrate ────────────────────────

@router.post(
    "/api/stories/{story_id}/chapters/{chapter_id}"
    "/scenes/{scene_id}/narrate",
)
async def api_stories_narrate_scene(
    story_id: str,
    chapter_id: str,
    scene_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate LLM narration for a scene.

    Uses the story/chapter context and entity data to build a
    rich prompt, then calls the LLM to generate narrative prose.

    Optional body: {
        "provider": "openrouter",
        "model": "...",
        "participants": [
            {"id": "sage", "type": "council"},
            {"id": "CH-0001", "type": "character"}
        ]
    }

    Returns: {"narrative_text": "...", "model": "...", "provider": "..."}
    """
    from core.story import (
        StoryManager, StoryNotFoundError,
        ChapterNotFoundError, SceneNotFoundError,
    )
    from core.api_client import APIClient, ChatMessage
    from core.characters import CharacterManager
    from core.locations import LocationManager

    body = body or {}

    # F-043: Validate participants
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

    smgr = StoryManager()

    try:
        story = smgr.get(story_id)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )

    # Find chapter and scene
    chapter = None
    scene = None
    for ch in story.chapters:
        if ch.chapter_id == chapter_id:
            chapter = ch
            for sc in ch.scenes:
                if sc.scene_id == scene_id:
                    scene = sc
                    break
            break

    if chapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter '{chapter_id}' not found.",
        )
    if scene is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scene '{scene_id}' not found.",
        )

    # Build the narration prompt with entity context
    prompt = StoryManager.build_scene_narration_prompt(
        story, chapter, scene,
        character_manager=CharacterManager(),
        location_manager=LocationManager(),
    )

    # F-043: Enrich prompt with participant context
    if participants:
        participant_context = _build_participant_context(participants)
        if participant_context:
            prompt = prompt + "\n\n" + participant_context

    # Call LLM
    client = APIClient()
    from core.registry import CouncilMember

    provider = body.get("provider", "openrouter")
    model = body.get("model", "mistralai/mistral-small-2603")
    narrator = CouncilMember(
        name="Narrator",
        role="Story Narrator",
        description="An expert storyteller",
        api_provider=provider,
        model=model,
        system_prompt=(
            "You are a masterful storyteller. Write vivid, "
            "atmospheric prose fiction. Respond with only the "
            "narrative text — no commentary or meta-text."
        ),
    )
    messages = [ChatMessage(role="user", content=prompt)]
    response = await client.chat(narrator, messages)

    # Save narrative to scene
    smgr.update_scene(
        story_id, chapter_id, scene_id,
        narrative_text=response.content,
    )

    return {
        "narrative_text": response.content,
        "model": response.model,
        "provider": response.provider,
    }

@router.post(
    "/api/stories/{story_id}/chapters/{chapter_id}"
    "/scenes/{scene_id}/illustrate",
)
async def api_stories_illustrate_scene(
    story_id: str,
    chapter_id: str,
    scene_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Trigger illustration generation for a scene.

    Uses the scene's narrative and entity context to generate
    an image via the ComfyUI pipeline.

    Optional body: {
        "template_id": "TPL-XXXX",
        "style_preset_key": "fantasy_art",
        "width": 768, "height": 512,
        "participants": [
            {"id": "sage", "type": "council"},
            {"id": "CH-0001", "type": "character"}
        ]
    }

    Returns: {"job_id": "GEN-XXXX", "status": "queued"}
    """
    from core.story import (
        StoryManager, StoryNotFoundError,
        ChapterNotFoundError, SceneNotFoundError,
    )
    from core.generation_pipeline import (
        GenerationRequest, GenerationValidationError,
        GenerationQueueFullError,
    )

    body = body or {}

    # F-043: Validate participants
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

    smgr = StoryManager()

    try:
        story = smgr.get(story_id)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
        )

    # Find chapter and scene
    chapter = None
    scene = None
    for ch in story.chapters:
        if ch.chapter_id == chapter_id:
            chapter = ch
            for sc in ch.scenes:
                if sc.scene_id == scene_id:
                    scene = sc
                    break
            break

    if chapter is None:
        raise HTTPException(
            status_code=404,
            detail=f"Chapter '{chapter_id}' not found.",
        )
    if scene is None:
        raise HTTPException(
            status_code=404,
            detail=f"Scene '{scene_id}' not found.",
        )

    # Build prompt from narrative + context
    prompt_parts = []
    if scene.narrative_text:
        prompt_parts.append(
            f"Illustrate: {scene.narrative_text[:500]}"
        )
    if scene.mood:
        prompt_parts.append(f"Mood: {scene.mood}")
    if not prompt_parts:
        prompt_parts.append(
            f"Scene from story '{story.title}', "
            f"chapter '{chapter.title or 'Untitled'}'"
        )

    user_prompt = " | ".join(prompt_parts)

    # F-043: Enrich prompt with participant context
    if participants:
        participant_context = _build_participant_context(participants)
        if participant_context:
            user_prompt = user_prompt + "\n\n" + participant_context

    # Determine template
    template_id = (body.get("template_id") or "").strip()
    if not template_id and story.template_id:
        template_id = story.template_id
    if not template_id:
        try:
            from core.template_assignments import (
                TemplateAssignmentManager,
            )
            from core.comfyui_client import WorkflowTemplateManager
            tam = TemplateAssignmentManager(
                template_manager=WorkflowTemplateManager(),
            )
            # Use location template if scene has a location,
            # otherwise fall back to character
            entity_type = (
                "location" if scene.location_id else "character"
            )
            template_id = tam.get_recommended_template(entity_type)
        except Exception:
            pass
    if not template_id:
        raise HTTPException(
            status_code=400,
            detail="No template specified and no default template "
                   "could be determined. Specify 'template_id' in "
                   "the request body or set a default in Settings.",
        )

    # Build generation request
    entity_type = "location" if scene.location_id else "character"
    entity_id = scene.location_id or (
        scene.characters[0] if scene.characters else "story"
    )

    try:
        request = GenerationRequest.create(
            entity_type=entity_type,
            entity_id=entity_id,
            template_id=template_id,
            prompt_mode="raw_user",
            user_prompt=user_prompt,
            style_preset_key=(
                body.get("style_preset_key")
                or story.style_preset_key
                or ""
            ),
            width=body.get("width", 768),
            height=body.get("height", 512),
            seed=body.get("seed", 0),
            metadata={
                "story_illustration": True,
                "story_id": story_id,
                "chapter_id": chapter_id,
                "scene_id": scene_id,
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

    # Launch the pipeline execution in the background so the
    # job actually progresses (same pattern as look-around).
    import asyncio

    async def _run_in_background(jid: str) -> None:
        try:
            last_progress = None
            async for _progress in pipeline.run_job(jid):
                last_progress = _progress
            # Link the generated image back to the scene
            if last_progress and last_progress.image_id:
                try:
                    from core.story import StoryManager
                    _smgr = StoryManager()
                    _smgr.update_scene(
                        story_id, chapter_id, scene_id,
                        image_id=last_progress.image_id,
                    )
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Generated image %s but failed to link to "
                        "scene %s/%s/%s",
                        last_progress.image_id,
                        story_id, chapter_id, scene_id,
                    )
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Background illustration failed for %s", jid,
            )

    asyncio.create_task(_run_in_background(job_id))

    return {
        "job_id": job_id,
        "status": "queued",
        "story_id": story_id,
        "chapter_id": chapter_id,
        "scene_id": scene_id,
    }

