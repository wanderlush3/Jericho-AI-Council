"""
Jericho — Stories Routes
"""

from __future__ import annotations

import logging
import json as json_module
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from starlette.responses import StreamingResponse

from core.manager_cache import (
    get_api_client,
    get_character_manager,
    get_location_manager,
    get_registry,
    get_story_manager,
)
from core.routes._helpers import (
    _get_pipeline,
    _build_participant_context,
)
from core.injection_profiles import InjectionProfile



log = logging.getLogger(__name__)

router = APIRouter()

_PARTICIPANT_MAX = 10
_STORY_CHAT_MAX_ROUNDS = 5

@router.get("/api/stories")
def api_stories_list(
    status: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List all stories, optionally filtered by status."""
    from core.story import StoryManager

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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

    smgr = get_story_manager()
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
    from core.api_client import ChatMessage

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

    smgr = get_story_manager()

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
        character_manager=get_character_manager(),
        location_manager=get_location_manager(),
    )

    # F-043: Enrich prompt with participant context
    # F-061: Use NARRATION profile for story narration
    if participants:
        participant_context = _build_participant_context(
            participants, profile=InjectionProfile.NARRATION,
        )
        if participant_context:
            prompt = prompt + "\n\n" + participant_context

    # Call LLM
    client = get_api_client()
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

    smgr = get_story_manager()

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
    # F-061: Use IMAGE_GEN profile for story illustration
    if participants:
        participant_context = _build_participant_context(
            participants, profile=InjectionProfile.IMAGE_GEN,
        )
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
            log.debug("core.routes.stories: non-critical error", exc_info=True)
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


# ── Story Chat ───────────────────────────────────────────


def _make_story_chat() -> "HumanChat":
    """Instantiate HumanChat for story chat sessions."""
    from core.routes.chat import _make_human_chat
    return _make_human_chat()


def _next_story_chat_id() -> str:
    """Generate the next sequential STC-XXXX chat ID."""
    from config.settings import CONVERSATIONS_DIR
    existing = sorted(CONVERSATIONS_DIR.glob("H-STC-*.json"))
    if not existing:
        return "STC-0001"
    last = existing[-1].stem  # e.g. "H-STC-0042"
    num = int(last.split("-")[-1]) + 1
    return f"STC-{num:04d}"


def _get_story_round(chat_record) -> int:
    """Get the current round number from chat metadata."""
    return (chat_record.metadata or {}).get("story_round", 0)


def _increment_story_round(hc, chat_id: str) -> int:
    """Increment and return the new round number."""
    rec = hc.get(chat_id)
    meta = dict(rec.metadata or {})
    current = meta.get("story_round", 0)
    meta["story_round"] = current + 1
    # Update metadata by replacing the record
    from core.human_chat import HumanChatRecord
    d = rec.to_dict()
    d["metadata"] = meta
    updated = HumanChatRecord.from_dict(d)
    hc._save(updated)
    return current + 1


def _is_story_chat_at_limit(chat_record) -> bool:
    """Check if the story chat has reached its round limit."""
    meta = chat_record.metadata or {}
    current = meta.get("story_round", 0)
    max_rounds = meta.get("story_max_rounds", _STORY_CHAT_MAX_ROUNDS)
    return current >= max_rounds


@router.get("/api/stories/{story_id}/chat/active")
def api_story_chat_active(story_id: str) -> dict[str, Any]:
    """Find the active (non-closed) story chat for a story.

    Returns: {"chat_id": "STC-XXXX", "chat": {...}, "round": N, "max_rounds": 5}
             or {"chat_id": null}
    """
    hc = _make_story_chat()
    chats = hc.list_chats(closed=False)
    for c in chats:
        meta = c.metadata or {}
        if (
            meta.get("story_chat") is True
            and meta.get("story_id") == story_id
            and not c.closed_at
        ):
            return {
                "chat_id": c.chat_id,
                "chat": c.to_dict(),
                "round": meta.get("story_round", 0),
                "max_rounds": meta.get("story_max_rounds", _STORY_CHAT_MAX_ROUNDS),
            }
    return {"chat_id": None}


@router.post("/api/stories/{story_id}/chat")
def api_story_chat_create(
    story_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a story chat session.

    Body: {
        "participants": [
            {"id": "sage", "type": "council"},
            {"id": "CH-0001", "type": "character"}
        ],
        "chapter_id": "CHP-0001",
        "scene_id": "SCE-0001"
    }

    Returns: the created chat record with round info.
    """
    from core.story import StoryManager, StoryNotFoundError
    from core.human_chat import HumanChatValidationError

    body = body or {}
    participants = body.get("participants", [])
    chapter_id = body.get("chapter_id", "")
    scene_id = body.get("scene_id", "")

    smgr = get_story_manager()
    try:
        story = smgr.get(story_id)
    except StoryNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Story '{story_id}' not found.",
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

    first_member = ""
    first_character = ""
    if council_ids:
        first_member = council_ids[0]
    if character_ids:
        first_character = character_ids[0]

    hc = _make_story_chat()
    chat_id = _next_story_chat_id()

    # Build scene context for topic
    scene_label = ""
    if chapter_id and scene_id:
        for ch in story.chapters:
            if ch.chapter_id == chapter_id:
                for sc in ch.scenes:
                    if sc.scene_id == scene_id:
                        scene_label = f" - Ch.{ch.chapter_number} Sc.{sc.scene_number}"
                        break
                break

    try:
        rec = hc.create_chat(
            chat_id,
            title=f"Story Chat: {story.title}{scene_label}",
            member_name=first_member,
            character_id=first_character,
            topic=f"Discussing story: {story.title}",
            metadata={
                "story_chat": True,
                "story_id": story_id,
                "story_title": story.title,
                "chapter_id": chapter_id,
                "scene_id": scene_id,
                "story_round": 0,
                "story_max_rounds": _STORY_CHAT_MAX_ROUNDS,
            },
        )
    except HumanChatValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Add remaining council members beyond the first
    for cid in council_ids[1:]:
        try:
            rec = hc.add_council_member(chat_id, cid)
        except Exception:
            log.debug("core.routes.stories: non-critical error", exc_info=True)

    # Add remaining characters beyond the first
    for chid in character_ids[1 if not first_member else 0:]:
        if chid == first_character:
            continue
        try:
            rec = hc.add_character(chat_id, chid)
        except Exception:
            log.debug("core.routes.stories: non-critical error", exc_info=True)

    result = rec.to_dict()
    result["round"] = 0
    result["max_rounds"] = _STORY_CHAT_MAX_ROUNDS
    return result


@router.post("/api/stories/{story_id}/chat/{chat_id}/inject-narration")
async def api_story_chat_inject_narration(
    story_id: str,
    chat_id: str,
    body: dict[str, Any] | None = None,
):
    """Inject a narration into the story chat and trigger participant discussion.

    Body: {
        "narration_text": "...",   // the narration text to inject
        "chapter_id": "CHP-0001",
        "scene_id": "SCE-0001"
    }

    Returns: SSE stream of participant responses.
    """
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    body = body or {}
    narration_text = (body.get("narration_text") or "").strip()

    if not narration_text:
        raise HTTPException(
            status_code=400,
            detail="'narration_text' is required.",
        )

    async def event_generator():
        try:
            hc = _make_story_chat()

            # Inject the narration as a narrator message
            narrator_content = f"📖 **Narration:**\n\n{narration_text}"

            hc.send_human_message(
                chat_id,
                narrator_content,
                metadata={
                    "type": "narration_inject",
                    "story_id": story_id,
                    "chapter_id": body.get("chapter_id", ""),
                    "scene_id": body.get("scene_id", ""),
                },
            )

            # Auto-resume if paused
            rec = hc.get(chat_id)
            if rec.paused:
                hc.resume_chat(chat_id)

            # Increment round
            new_round = _increment_story_round(hc, chat_id)
            max_rounds = (rec.metadata or {}).get(
                "story_max_rounds", _STORY_CHAT_MAX_ROUNDS,
            )

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

            # Check if at limit and auto-close
            final_record = hc.get(chat_id)
            at_limit = new_round >= max_rounds
            if at_limit:
                try:
                    hc.close_chat(chat_id, summary="Story chat reached round limit.")
                    final_record = hc.get(chat_id)
                except Exception:
                    log.debug("core.routes.stories: non-critical error", exc_info=True)
            done_data = json_module.dumps({
                "chat": final_record.to_dict(),
                "round": new_round,
                "max_rounds": max_rounds,
                "at_limit": at_limit,
            })
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


@router.post("/api/stories/{story_id}/chat/{chat_id}/send-stream")
async def api_story_chat_send_stream(
    story_id: str,
    chat_id: str,
    body: dict[str, Any] | None = None,
):
    """Send a human message in the story chat.

    Body: {"content": "..."}

    Returns: SSE stream of participant responses.
    """
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    body = body or {}
    content = (body.get("content") or "").strip()
    if not content:
        raise HTTPException(
            status_code=400,
            detail="'content' is required.",
        )

    async def event_generator():
        try:
            hc = _make_story_chat()

            # Check round limit before proceeding
            rec = hc.get(chat_id)
            if _is_story_chat_at_limit(rec):
                err = json_module.dumps({
                    "detail": "Story chat has reached the maximum number of rounds.",
                })
                yield f"event: error\ndata: {err}\n\n"
                return

            # Auto-resume if paused
            if rec.paused:
                hc.resume_chat(chat_id)

            hc.send_human_message(chat_id, content)

            # Increment round
            new_round = _increment_story_round(hc, chat_id)
            max_rounds = (rec.metadata or {}).get(
                "story_max_rounds", _STORY_CHAT_MAX_ROUNDS,
            )

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
            at_limit = new_round >= max_rounds
            if at_limit:
                try:
                    hc.close_chat(chat_id, summary="Story chat reached round limit.")
                    final_record = hc.get(chat_id)
                except Exception:
                    log.debug("core.routes.stories: non-critical error", exc_info=True)
            done_data = json_module.dumps({
                "chat": final_record.to_dict(),
                "round": new_round,
                "max_rounds": max_rounds,
                "at_limit": at_limit,
            })
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


@router.post("/api/stories/{story_id}/chat/{chat_id}/continue-stream")
async def api_story_chat_continue_stream(
    story_id: str,
    chat_id: str,
):
    """Trigger one round of AI-to-AI discussion in story chat.

    Returns: SSE stream of participant responses.
    """
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    async def event_generator():
        try:
            hc = _make_story_chat()

            # Check round limit
            rec = hc.get(chat_id)
            if _is_story_chat_at_limit(rec):
                err = json_module.dumps({
                    "detail": "Story chat has reached the maximum number of rounds.",
                })
                yield f"event: error\ndata: {err}\n\n"
                return

            # Increment round
            new_round = _increment_story_round(hc, chat_id)
            max_rounds = (rec.metadata or {}).get(
                "story_max_rounds", _STORY_CHAT_MAX_ROUNDS,
            )

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
            at_limit = new_round >= max_rounds
            if at_limit:
                try:
                    hc.close_chat(chat_id, summary="Story chat reached round limit.")
                    final_record = hc.get(chat_id)
                except Exception:
                    log.debug("core.routes.stories: non-critical error", exc_info=True)
            done_data = json_module.dumps({
                "chat": final_record.to_dict(),
                "round": new_round,
                "max_rounds": max_rounds,
                "at_limit": at_limit,
            })
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


@router.post("/api/stories/{story_id}/chat/{chat_id}/narrate-round")
async def api_story_chat_narrate_round(
    story_id: str,
    chat_id: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a mid-conversation narration that incorporates chat context.

    Calls the LLM narrator with story context + recent chat messages,
    saves the narration to the scene, and injects it into the chat log.

    Optional body: {
        "provider": "openrouter",
        "model": "..."
    }

    Returns: {"narrative_text": "...", "model": "...", "round": N, "max_rounds": 5}
    """
    from core.story import (
        StoryManager, StoryNotFoundError,
        ChapterNotFoundError, SceneNotFoundError,
    )
    from core.api_client import APIClient, ChatMessage
    from core.characters import CharacterManager
    from core.locations import LocationManager
    from core.human_chat import HumanChatNotFoundError, HumanChatError

    body = body or {}

    hc = _make_story_chat()

    # Get chat record to find story/chapter/scene context
    try:
        rec = hc.get(chat_id)
    except HumanChatNotFoundError:
        raise HTTPException(status_code=404, detail=f"Chat '{chat_id}' not found.")

    meta = rec.metadata or {}
    if meta.get("story_id") != story_id:
        raise HTTPException(
            status_code=400,
            detail="Chat does not belong to this story.",
        )

    chapter_id = meta.get("chapter_id", "")
    scene_id = meta.get("scene_id", "")

    smgr = get_story_manager()
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

    if chapter is None or scene is None:
        raise HTTPException(
            status_code=404,
            detail="Chapter or scene not found for this chat.",
        )

    # Build prompt with story context + recent chat messages
    prompt = StoryManager.build_scene_narration_prompt(
        story, chapter, scene,
        character_manager=CharacterManager(),
        location_manager=LocationManager(),
    )

    # Add recent chat conversation as context
    recent_messages = (rec.messages or [])[-10:]
    if recent_messages:
        prompt += "\n\n### Recent Discussion:\n"
        prompt += "The following conversation has taken place about this scene:\n\n"
        for msg in recent_messages:
            if msg.metadata and msg.metadata.get("type") == "narration_inject":
                continue  # skip previous narration injects to avoid recursion
            label = "Human" if msg.role == "human" else msg.speaker
            prompt += f"**{label}:** {msg.content}\n\n"
        prompt += (
            "\n### Task:\n"
            "Based on the discussion above, write the next narrative "
            "continuation of this scene. Incorporate any insights, "
            "reactions, or ideas raised in the discussion. Write in "
            "third person, present tense. Be vivid and atmospheric. "
            "Aim for 2-4 paragraphs. Do not include any meta-commentary."
        )

    # Enrich prompt with participant context
    # F-061: Use NARRATION profile for story chat narration
    participants = meta.get("participants", [])
    if participants:
        participant_context = _build_participant_context(
            participants, profile=InjectionProfile.NARRATION,
        )
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
            "narrative text \u2014 no commentary or meta-text."
        ),
    )
    messages = [ChatMessage(role="user", content=prompt)]
    response = await client.chat(narrator, messages)

    narrative_text = response.content or ""

    # Append narration to scene's existing narrative
    existing_text = scene.narrative_text or ""
    if existing_text:
        updated_text = existing_text + "\n\n---\n\n" + narrative_text
    else:
        updated_text = narrative_text

    smgr.update_scene(
        story_id, chapter_id, scene_id,
        narrative_text=updated_text,
    )

    # Inject the narration into the chat log
    narrator_content = f"\U0001f4d6 **Narration:**\n\n{narrative_text}"
    try:
        # Auto-resume if paused
        rec = hc.get(chat_id)
        if rec.paused:
            hc.resume_chat(chat_id)

        hc.send_human_message(
            chat_id,
            narrator_content,
            metadata={
                "type": "narration_inject",
                "story_id": story_id,
                "chapter_id": chapter_id,
                "scene_id": scene_id,
            },
        )
    except Exception:
        log.debug("core.routes.stories: non-critical error", exc_info=True)

    rec = hc.get(chat_id)
    current_round = _get_story_round(rec)
    max_rounds = meta.get("story_max_rounds", _STORY_CHAT_MAX_ROUNDS)

    return {
        "narrative_text": narrative_text,
        "model": response.model,
        "provider": response.provider,
        "round": current_round,
        "max_rounds": max_rounds,
    }
