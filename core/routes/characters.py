"""
Jericho — Characters Routes
"""

from __future__ import annotations

import logging

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse

from core.manager_cache import get_character_manager



log = logging.getLogger(__name__)

router = APIRouter()

@router.get("/api/characters")
def api_characters_list(
    status: str | None = Query(None),
    author: str | None = Query(None),
    tag: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List characters with optional filters."""
    from core.characters import CharacterManager
    from config.settings import CHARACTER_AVATARS_DIR
    mgr = get_character_manager()
    items = mgr.list_characters(status=status, author=author, tag=tag)
    result = []
    for c in items:
        d = c.to_dict()
        avatar_file = CHARACTER_AVATARS_DIR / f"{c.id}.png"
        if avatar_file.exists():
            d["avatar_url"] = f"/api/characters/{c.id}/avatar"
        result.append(d)
    return result

@router.get("/api/characters/{character_id}")
def api_character_detail(character_id: str) -> dict[str, Any]:
    """Get a single character template."""
    from core.characters import CharacterManager, CharacterNotFoundError
    from config.settings import CHARACTER_AVATARS_DIR
    mgr = get_character_manager()
    try:
        c = mgr.get(character_id)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )
    d = c.to_dict()
    avatar_file = CHARACTER_AVATARS_DIR / f"{c.id}.png"
    if avatar_file.exists():
        d["avatar_url"] = f"/api/characters/{c.id}/avatar"
    return d

@router.post("/api/characters")
def api_character_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a new character.

    Body: {"name": "...", "description": "...", "author": "...",
           "backstory": "...", "physical_description": "...",
           "system_prompt": "...", "greeting": "...",
           "example_messages": [...], "tags": [...],
           "traits": [{"trait_type": "...", "name": "...",
                        "description": "...", "intensity": 0.8}]}
    """
    from core.characters import (
        CharacterManager, CharacterValidationError, Trait,
    )

    name = body.get("name", "").strip()
    description = body.get("description", "").strip()
    author = body.get("author", "").strip()
    backstory = body.get("backstory", "").strip()
    physical_description = body.get("physical_description", "").strip()
    system_prompt = body.get("system_prompt", "").strip()
    greeting = body.get("greeting", "").strip()
    example_messages = body.get("example_messages", [])
    tags = body.get("tags", [])
    raw_traits = body.get("traits", [])
    api_provider = body.get("api_provider", "openrouter").strip() or "openrouter"
    model = body.get("model", "Default").strip() or "Default"

    if not name or not description or not author:
        raise HTTPException(
            status_code=400,
            detail="Fields 'name', 'description', and 'author' are required.",
        )

    # Parse traits
    traits: list[Trait] = []
    for t in raw_traits:
        try:
            traits.append(Trait.create(
                trait_type=t.get("trait_type", "personality"),
                name=t.get("name", ""),
                description=t.get("description", ""),
                intensity=float(t.get("intensity", 0.5)),
            ))
        except CharacterValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    mgr = get_character_manager()
    try:
        char = mgr.create(
            name, description, author=author, backstory=backstory,
            physical_description=physical_description,
            traits=traits or None, system_prompt=system_prompt,
            greeting=greeting, example_messages=example_messages or None,
            tags=tags or None,
            api_provider=api_provider, model=model,
        )
    except CharacterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return char.to_dict()

@router.put("/api/characters/{character_id}")
def api_character_update(
    character_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Update mutable fields on a character.

    Body may contain: name, description, backstory, system_prompt,
    greeting, example_messages, tags, metadata.
    """
    from core.characters import (
        CharacterManager, CharacterNotFoundError, CharacterValidationError,
    )
    mgr = get_character_manager()
    try:
        char = mgr.update(character_id, **body)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )
    except CharacterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return char.to_dict()

@router.put("/api/characters/{character_id}/status")
def api_character_status(
    character_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Transition a character's lifecycle status.

    Body: {"status": "active"}
    """
    from core.characters import (
        CharacterManager, CharacterNotFoundError,
        CharacterValidationError, CharacterLifecycleError,
    )

    new_status = body.get("status", "").strip()
    if not new_status:
        raise HTTPException(status_code=400, detail="'status' is required.")

    mgr = get_character_manager()
    try:
        char = mgr.update_status(character_id, new_status)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )
    except (CharacterValidationError, CharacterLifecycleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return char.to_dict()

@router.post("/api/characters/{character_id}/avatar-upload")
def api_character_avatar_upload(
    character_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Upload avatar as base64 JSON.

    Body: {"image_data": "data:image/png;base64,..."}
    """
    import base64
    from config.settings import CHARACTER_AVATARS_DIR
    from core.characters import CharacterManager, CharacterNotFoundError

    mgr = get_character_manager()
    try:
        mgr.get(character_id)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )

    image_data = body.get("image_data", "")
    if not image_data:
        raise HTTPException(status_code=400, detail="'image_data' is required.")

    try:
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        raw_bytes = base64.b64decode(image_data)
    except Exception:
        log.debug("characters: failed if "," in image_data:", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid base64 image data.")

    CHARACTER_AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    avatar_path = CHARACTER_AVATARS_DIR / f"{character_id}.png"
    with open(avatar_path, "wb") as f:
        f.write(raw_bytes)

    return {
        "status": "ok",
        "avatar_url": f"/api/characters/{character_id}/avatar",
    }

@router.get("/api/characters/{character_id}/avatar")
def api_character_avatar_get(character_id: str):
    """Serve a character's avatar PNG."""
    from config.settings import CHARACTER_AVATARS_DIR
    from core.characters import CharacterManager, CharacterNotFoundError

    mgr = get_character_manager()
    try:
        mgr.get(character_id)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )

    avatar_path = CHARACTER_AVATARS_DIR / f"{character_id}.png"
    if not avatar_path.exists():
        raise HTTPException(
            status_code=404, detail="No avatar uploaded for this character.",
        )

    return FileResponse(str(avatar_path), media_type="image/png")

@router.get("/api/characters/{character_id}/export-png")
def api_character_export_png(character_id: str):
    """Export a character as a PNG with embedded TavernCard v2 metadata.

    If the character has an avatar, that image is used as the base PNG.
    Otherwise a minimal placeholder PNG is generated.
    """
    from config.settings import CHARACTER_AVATARS_DIR
    from core.characters import CharacterManager, CharacterNotFoundError
    from core.png_embed import (
        embed_character_in_png, create_minimal_png,
    )

    mgr = get_character_manager()
    try:
        char = mgr.get(character_id)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )

    # Use avatar if exists, otherwise minimal placeholder
    avatar_path = CHARACTER_AVATARS_DIR / f"{character_id}.png"
    if avatar_path.exists():
        png_bytes = avatar_path.read_bytes()
    else:
        png_bytes = create_minimal_png()

    result_bytes = embed_character_in_png(png_bytes, char)

    from starlette.responses import Response
    safe_name = char.name.replace(" ", "_").replace("/", "_")
    return Response(
        content=result_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.png"',
        },
    )

@router.post("/api/characters/{character_id}/export-png")
def api_character_export_png_upload(
    character_id: str, body: dict[str, Any],
):
    """Export a character as a PNG with embedded TavernCard v2 metadata,
    using a user-supplied PNG as the base image.

    Body: {"image_data": "data:image/png;base64,..."}
    Returns the embedded PNG named jericho_<character_name>.png.
    """
    import base64
    from core.characters import CharacterManager, CharacterNotFoundError
    from core.png_embed import embed_character_in_png

    mgr = get_character_manager()
    try:
        char = mgr.get(character_id)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )

    image_data = body.get("image_data", "")
    if not image_data:
        raise HTTPException(status_code=400, detail="'image_data' is required.")

    try:
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        png_bytes = base64.b64decode(image_data)
    except Exception:
        log.debug("characters: failed if "," in image_data:", exc_info=True)
        raise HTTPException(status_code=400, detail="Invalid base64 image data.")

    if png_bytes[:8] != b"\x89PNG\r\n\x1a\n":
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid PNG.")

    result_bytes = embed_character_in_png(png_bytes, char)

    from starlette.responses import Response
    safe_name = char.name.replace(" ", "_").replace("/", "_")
    filename = f"jericho_{safe_name}.png"
    return Response(
        content=result_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )

# ── Character Traits ──────────────────────────────────────

@router.post("/api/characters/{character_id}/traits")
def api_character_add_trait(
    character_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Add a trait to a character.

    Body: {"trait_type": "personality", "name": "Curious",
           "description": "Always asking questions", "intensity": 0.8}
    """
    from core.characters import (
        CharacterManager, CharacterNotFoundError,
        CharacterValidationError, Trait,
    )

    mgr = get_character_manager()
    try:
        trait = Trait.create(
            trait_type=body.get("trait_type", "personality"),
            name=body.get("name", "").strip(),
            description=body.get("description", "").strip(),
            intensity=float(body.get("intensity", 0.5)),
        )
        char = mgr.add_trait(character_id, trait)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )
    except CharacterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return char.to_dict()

@router.delete("/api/characters/{character_id}/traits/{trait_name}")
def api_character_remove_trait(
    character_id: str, trait_name: str,
) -> dict[str, Any]:
    """Remove a trait from a character by name."""
    from core.characters import (
        CharacterManager, CharacterNotFoundError,
        CharacterValidationError,
    )

    mgr = get_character_manager()
    try:
        char = mgr.remove_trait(character_id, trait_name)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )
    except CharacterValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return char.to_dict()

# ── Tasks ─────────────────────────────────────────────────

