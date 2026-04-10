"""
Jericho — Council Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse


router = APIRouter()

# ── Council ───────────────────────────────────────────────

@router.get("/api/council")
def api_council_list() -> list[dict[str, Any]]:
    """List all council members."""
    from core.registry import CouncilRegistry
    from config.settings import COUNCIL_AVATARS_DIR
    registry = CouncilRegistry().load()
    members = registry.list_members()
    result = []
    for m in members:
        d = {
            "name": m.name,
            "role": m.role,
            "description": m.description,
            "personality": m.personality,
            "api_provider": m.api_provider,
            "model": m.model,
            "vote_weight": m.vote_weight,
            "specialties": m.specialties,
            "system_prompt": m.system_prompt,
        }
        avatar_file = COUNCIL_AVATARS_DIR / f"{m.name.lower()}.png"
        if avatar_file.exists():
            d["avatar_url"] = f"/api/council/{m.name}/avatar"
        result.append(d)
    return result

@router.get("/api/council/candidates")
def api_council_candidates() -> list[dict[str, Any]]:
    """List active characters that are not already council members.

    Returns characters eligible for promotion to council membership.
    Only active characters whose names don't match an existing
    council member (case-insensitive) are included.
    """
    from core.registry import CouncilRegistry
    from core.characters import CharacterManager
    from config.settings import CHARACTER_AVATARS_DIR

    registry = CouncilRegistry().load()
    cmgr = CharacterManager()
    active_chars = cmgr.list_characters(status="active")

    # Build set of existing council member names (lowercase)
    council_names = {m.name.lower() for m in registry.list_members()}

    candidates = []
    for c in active_chars:
        if c.name.lower() not in council_names:
            d = {
                "id": c.id,
                "name": c.name,
                "description": c.description,
                "status": c.status,
                "api_provider": c.api_provider,
                "model": c.model,
                "system_prompt": c.system_prompt,
            }
            avatar_file = CHARACTER_AVATARS_DIR / f"{c.id}.png"
            if avatar_file.exists():
                d["avatar_url"] = f"/api/characters/{c.id}/avatar"
            candidates.append(d)
    return candidates

@router.post("/api/council/promote")
def api_council_promote(body: dict[str, Any]) -> dict[str, Any]:
    """Promote a character to council member.

    Body: {
        "character_id": "CH-0001",
        "role": "Innovation Advisor",
        "role_description": "Explores new ideas and advises on creative solutions",
        "api_provider": "openrouter",   // optional, defaults to character's
        "model": "anthropic/claude-3.5-sonnet"  // optional, defaults to character's
    }

    Creates a new YAML profile in council/members/ and returns
    the new council member data.
    """
    import yaml as yaml_mod
    from core.registry import CouncilRegistry
    from core.characters import CharacterManager, CharacterNotFoundError

    character_id = body.get("character_id", "").strip()
    role = body.get("role", "").strip()
    role_description = body.get("role_description", "").strip()

    errors = []
    if not character_id:
        errors.append("'character_id' is required")
    if not role:
        errors.append("'role' is required")
    if not role_description:
        errors.append("'role_description' is required")
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    # Load character
    cmgr = CharacterManager()
    try:
        character = cmgr.get(character_id)
    except CharacterNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Character '{character_id}' not found.",
        )

    if character.status != "active":
        raise HTTPException(
            status_code=400,
            detail=f"Character '{character.name}' is not active (status: {character.status}).",
        )

    # Check not already on council
    registry = CouncilRegistry().load()
    if character.name.lower() in {m.name.lower() for m in registry.list_members()}:
        raise HTTPException(
            status_code=400,
            detail=f"'{character.name}' is already a council member.",
        )

    # Determine provider & model
    api_provider = body.get("api_provider", "").strip() or character.api_provider
    model = body.get("model", "").strip() or character.model
    if model == "Default":
        model = "anthropic/claude-3.5-sonnet"

    # Build YAML data
    member_data = {
        "name": character.name,
        "role": role,
        "description": role_description,
        "api_provider": api_provider,
        "model": model,
        "vote_weight": 1.0,
        "system_prompt": character.system_prompt or f"You are {character.name}, the {role} on the Jericho Council.",
    }

    # Write YAML to council/members/
    # Import from core.web_api so test patches (mock.patch("core.web_api.COUNCIL_MEMBERS_DIR"))
    # propagate correctly.
    from core.web_api import COUNCIL_MEMBERS_DIR
    filename = f"{character.name.lower().replace(' ', '_')}.yaml"
    member_filepath = COUNCIL_MEMBERS_DIR / filename
    comment = f"# Council Member: {character.name} — {role}\n"
    yaml_body = yaml_mod.dump(
        member_data, default_flow_style=False,
        allow_unicode=True, sort_keys=False,
    )
    with open(member_filepath, "w", encoding="utf-8") as f:
        f.write(comment)
        f.write(yaml_body)

    return {
        "status": "ok",
        "name": character.name,
        "role": role,
        "description": role_description,
        "api_provider": api_provider,
        "model": model,
        "vote_weight": 1.0,
        "system_prompt": member_data["system_prompt"],
        "member_file": filename,
    }

@router.get("/api/council/{name}")
def api_council_detail(name: str) -> dict[str, Any]:
    """Get a single council member by name."""
    from core.registry import CouncilRegistry, MemberNotFoundError
    from config.settings import COUNCIL_AVATARS_DIR
    registry = CouncilRegistry().load()
    try:
        m = registry.get(name)
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")
    d = {
        "name": m.name,
        "role": m.role,
        "description": m.description,
        "personality": m.personality,
        "api_provider": m.api_provider,
        "model": m.model,
        "vote_weight": m.vote_weight,
        "specialties": m.specialties,
        "system_prompt": m.system_prompt,
    }
    avatar_file = COUNCIL_AVATARS_DIR / f"{m.name.lower()}.png"
    if avatar_file.exists():
        d["avatar_url"] = f"/api/council/{m.name}/avatar"
    return d

@router.put("/api/council/{name}")
def api_council_update(name: str, body: dict[str, Any]) -> dict[str, Any]:
    """Update editable fields of a council member.

    Body may contain: name, api_provider, model, vote_weight,
    system_prompt, traits, communication_style, decision_approach.
    Read-only fields (role, description, specialties) are rejected.
    """
    from core.registry import CouncilRegistry, MemberNotFoundError
    registry = CouncilRegistry().load()
    try:
        updated = registry.update_member(name, body)
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "name": updated.name,
        "role": updated.role,
        "description": updated.description,
        "personality": updated.personality,
        "api_provider": updated.api_provider,
        "model": updated.model,
        "vote_weight": updated.vote_weight,
        "specialties": updated.specialties,
        "system_prompt": updated.system_prompt,
    }

@router.post("/api/council/{name}/avatar")
async def api_council_avatar_upload(name: str) -> dict[str, Any]:
    """Upload an avatar PNG for a council member.

    Accepts multipart form data with fields:
      - file: the PNG image
      - zoom: zoom level (float, default 1.0)
      - offsetX: horizontal offset (float, default 0)
      - offsetY: vertical offset (float, default 0)
    """
    from fastapi import Request
    from config.settings import COUNCIL_AVATARS_DIR
    from core.registry import CouncilRegistry, MemberNotFoundError
    import base64

    # Verify the member exists
    registry = CouncilRegistry().load()
    try:
        member = registry.get(name)
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

    # This endpoint is called via JS fetch with JSON body containing base64 data
    # since we need zoom metadata alongside the image.
    return {"detail": "Use the JSON endpoint instead."}

@router.post("/api/council/{name}/avatar-upload")
def api_council_avatar_upload_json(name: str, body: dict[str, Any]) -> dict[str, Any]:
    """Upload avatar as base64 JSON.

    Body: {"image_data": "data:image/png;base64,...", "zoom": 1.0, "offsetX": 0, "offsetY": 0}
    """
    import base64
    from config.settings import COUNCIL_AVATARS_DIR
    from core.registry import CouncilRegistry, MemberNotFoundError

    registry = CouncilRegistry().load()
    try:
        member = registry.get(name)
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

    image_data = body.get("image_data", "")
    zoom = body.get("zoom", 1.0)
    offset_x = body.get("offsetX", 0)
    offset_y = body.get("offsetY", 0)

    if not image_data:
        raise HTTPException(status_code=400, detail="'image_data' is required.")

    # Parse base64 data URL
    try:
        if "," in image_data:
            image_data = image_data.split(",", 1)[1]
        raw_bytes = base64.b64decode(image_data)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid base64 image data.")

    # Ensure avatars directory exists
    COUNCIL_AVATARS_DIR.mkdir(parents=True, exist_ok=True)

    # Save the PNG
    avatar_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.png"
    with open(avatar_path, "wb") as f:
        f.write(raw_bytes)

    # Save zoom metadata
    meta_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.json"
    import json as json_mod
    with open(meta_path, "w", encoding="utf-8") as f:
        json_mod.dump({"zoom": zoom, "offsetX": offset_x, "offsetY": offset_y}, f)

    return {
        "status": "ok",
        "avatar_url": f"/api/council/{member.name}/avatar",
    }

@router.get("/api/council/{name}/avatar")
def api_council_avatar_get(name: str):
    """Serve a council member's avatar PNG."""
    from config.settings import COUNCIL_AVATARS_DIR
    from core.registry import CouncilRegistry, MemberNotFoundError

    registry = CouncilRegistry().load()
    try:
        member = registry.get(name)
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

    avatar_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.png"
    if not avatar_path.exists():
        raise HTTPException(status_code=404, detail="No avatar uploaded for this member.")

    return FileResponse(str(avatar_path), media_type="image/png")

@router.get("/api/council/{name}/avatar-meta")
def api_council_avatar_meta(name: str) -> dict[str, Any]:
    """Get avatar zoom metadata for a council member."""
    from config.settings import COUNCIL_AVATARS_DIR
    from core.registry import CouncilRegistry, MemberNotFoundError

    registry = CouncilRegistry().load()
    try:
        member = registry.get(name)
    except MemberNotFoundError:
        raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")

    meta_path = COUNCIL_AVATARS_DIR / f"{member.name.lower()}.json"
    if not meta_path.exists():
        return {"zoom": 1.0, "offsetX": 0, "offsetY": 0}

    import json as json_mod
    with open(meta_path, "r", encoding="utf-8") as f:
        return json_mod.load(f)

