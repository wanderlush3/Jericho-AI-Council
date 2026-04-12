"""
Jericho — Settings Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

@router.get("/api/analytics")
def api_analytics() -> dict[str, Any]:
    """Full analytics report."""
    from core.analytics import SessionAnalytics
    from core.manager_cache import (
        get_character_manager,
        get_item_manager,
        get_law_manager,
        get_location_manager,
        get_proposal_manager,
        get_registry,
        get_store_manager,
        get_story_manager,
        get_treasury_manager,
        get_voting_engine,
    )

    # Optional managers — gracefully degrade if unavailable
    image_manager = None
    template_manager = None
    taxation_manager = None
    try:
        from core.image_manager import ImageManager
        image_manager = ImageManager()
    except Exception:
        pass
    try:
        from core.comfyui_client import WorkflowTemplateManager
        template_manager = WorkflowTemplateManager()
    except Exception:
        pass
    try:
        from core.taxation import TaxationManager
        taxation_manager = TaxationManager()
    except Exception:
        pass

    sa = SessionAnalytics(
        proposal_manager=get_proposal_manager(),
        voting_engine=get_voting_engine(),
        character_manager=get_character_manager(),
        location_manager=get_location_manager(),
        item_manager=get_item_manager(),
        store_manager=get_store_manager(),
        treasury_manager=get_treasury_manager(),
        taxation_manager=taxation_manager,
        story_manager=get_story_manager(),
        image_manager=image_manager,
        template_manager=template_manager,
        law_manager=get_law_manager(),
        registry=get_registry(),
    )
    report = sa.full_report()
    return report.to_dict()

# ── Settings / API Keys ───────────────────────────────────

@router.get("/api/settings/keys")
def api_keys_status() -> list[dict[str, Any]]:
    """Return configuration status for each API provider (never raw keys)."""
    from core.api_keys import APIKeyManager
    mgr = APIKeyManager()
    return mgr.all_status()

@router.post("/api/settings/keys")
def api_keys_save(body: dict[str, Any]) -> dict[str, Any]:
    """Encrypt and save an API key.  Body: {"provider": "openrouter", "api_key": "sk-..."}."""
    from core.api_keys import APIKeyManager
    provider = body.get("provider", "").strip().lower()
    raw_key = body.get("api_key", "").strip()

    if not provider or not raw_key:
        raise HTTPException(status_code=400, detail="Both 'provider' and 'api_key' are required.")

    mgr = APIKeyManager()
    try:
        result = mgr.save_key(provider, raw_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result

@router.delete("/api/settings/keys/{provider}")
def api_keys_delete(provider: str) -> dict[str, Any]:
    """Remove a configured API key."""
    from core.api_keys import APIKeyManager
    mgr = APIKeyManager()
    try:
        result = mgr.delete_key(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result

# ── Settings / Models ─────────────────────────────────────
# NOTE: Settings models are the *fallback default*. A council member's
# own model takes priority unless set to "Default".

@router.get("/api/settings/models")
def api_models_status() -> list[dict[str, Any]]:
    """Return configured default model for each API provider."""
    from core.api_keys import APIKeyManager
    mgr = APIKeyManager()
    return mgr.all_model_status()

@router.post("/api/settings/models")
def api_models_save(body: dict[str, Any]) -> dict[str, Any]:
    """Save a default model name.  Body: {"provider": "openrouter", "model": "anthropic/claude-3.5-sonnet"}."""
    from core.api_keys import APIKeyManager
    provider = body.get("provider", "").strip().lower()
    model = body.get("model", "").strip()

    if not provider or not model:
        raise HTTPException(status_code=400, detail="Both 'provider' and 'model' are required.")

    mgr = APIKeyManager()
    try:
        result = mgr.save_model(provider, model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result

@router.get("/api/settings/mancer-models")
def api_mancer_models() -> list[str]:
    """Return the list of valid Mancer model options for dropdown menus."""
    from config.settings import MANCER_MODEL_OPTIONS
    return list(MANCER_MODEL_OPTIONS)

@router.get("/api/settings/openrouter-models")
def api_openrouter_models() -> list[str]:
    """Return the list of valid OpenRouter model options for dropdown menus."""
    from config.settings import OPENROUTER_MODEL_OPTIONS
    return list(OPENROUTER_MODEL_OPTIONS)

@router.get("/api/settings/lmstudio-models")
def api_lmstudio_models() -> list[str]:
    """Return the list of valid LM Studio model options for dropdown menus."""
    from config.settings import LMSTUDIO_MODEL_OPTIONS
    return list(LMSTUDIO_MODEL_OPTIONS)

@router.get("/api/settings/summarization")
def api_summarization_config() -> dict[str, Any]:
    """Return the current summarization LLM configuration."""
    from config.settings import (
        DEFAULT_SUMMARIZATION_PROVIDER,
        DEFAULT_SUMMARIZATION_MODEL,
        SUMMARIZATION_PROVIDER_ENV,
        SUMMARIZATION_MODEL_ENV,
    )
    import os
    provider = (
        os.environ.get(SUMMARIZATION_PROVIDER_ENV, "").strip()
        or DEFAULT_SUMMARIZATION_PROVIDER
    )
    model = (
        os.environ.get(SUMMARIZATION_MODEL_ENV, "").strip()
        or DEFAULT_SUMMARIZATION_MODEL
    )
    return {"provider": provider, "model": model}

@router.post("/api/settings/summarization")
def api_summarization_save(body: dict[str, Any]) -> dict[str, Any]:
    """Save summarization provider and model.

    Body: {"provider": "openrouter", "model": "mistralai/mistral-small-2603"}
    """
    from core.api_keys import APIKeyManager
    provider = body.get("provider", "").strip().lower()
    model = body.get("model", "").strip()

    if not provider or not model:
        raise HTTPException(
            status_code=400,
            detail="Both 'provider' and 'model' are required.",
        )
    if provider not in ("openrouter", "mancer", "lmstudio"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider '{provider}'. Must be 'openrouter', 'mancer', or 'lmstudio'.",
        )

    from config.settings import (
        SUMMARIZATION_PROVIDER_ENV,
        SUMMARIZATION_MODEL_ENV,
    )
    import os
    os.environ[SUMMARIZATION_PROVIDER_ENV] = provider
    os.environ[SUMMARIZATION_MODEL_ENV] = model

    # Also persist to .env via APIKeyManager
    mgr = APIKeyManager()
    mgr.save_env_value(SUMMARIZATION_PROVIDER_ENV, provider)
    mgr.save_env_value(SUMMARIZATION_MODEL_ENV, model)

    return {"provider": provider, "model": model, "saved": True}

@router.get("/api/settings/summarization-models")
def api_summarization_models(
    provider: str = Query("openrouter"),
) -> list[str]:
    """Return the list of summarization model options for a provider."""
    from config.settings import (
        SUMMARIZATION_OPENROUTER_MODELS,
        SUMMARIZATION_MANCER_MODELS,
    )
    if provider == "mancer":
        return list(SUMMARIZATION_MANCER_MODELS)
    if provider == "lmstudio":
        from config.settings import SUMMARIZATION_LMSTUDIO_MODELS
        return list(SUMMARIZATION_LMSTUDIO_MODELS)
    return list(SUMMARIZATION_OPENROUTER_MODELS)

# ── Settings / User Description ───────────────────────────

@router.get("/api/settings/user-description")
def api_user_description_get() -> dict[str, Any]:
    """Return the user's self-description."""
    from core.api_keys import APIKeyManager
    mgr = APIKeyManager()
    return {"description": mgr.get_user_description()}

@router.post("/api/settings/user-description")
def api_user_description_save(body: dict[str, Any]) -> dict[str, Any]:
    """Save the user's self-description.  Body: {"description": "..."}."""
    from core.api_keys import APIKeyManager
    text = body.get("description", "")

    mgr = APIKeyManager()
    try:
        result = mgr.save_user_description(text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result

# ── Settings / User Name ─────────────────────────────────

@router.get("/api/settings/user-name")
def api_user_name_get() -> dict[str, Any]:
    """Return the user's display name."""
    from core.api_keys import APIKeyManager
    mgr = APIKeyManager()
    return {"name": mgr.get_user_name()}

@router.post("/api/settings/user-name")
def api_user_name_save(body: dict[str, Any]) -> dict[str, Any]:
    """Save the user's display name.  Body: {"name": "..."}."""
    from core.api_keys import APIKeyManager
    name = body.get("name", "")

    mgr = APIKeyManager()
    try:
        result = mgr.save_user_name(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result

# ── Settings / ComfyUI ────────────────────────────────────

@router.get("/api/settings/comfyui")
def api_comfyui_config_get() -> dict[str, Any]:
    """Return current ComfyUI connection configuration."""
    from config.settings import (
        COMFYUI_DEFAULT_HOST,
        COMFYUI_DEFAULT_PORT,
        COMFYUI_HOST_ENV,
        COMFYUI_PORT_ENV,
    )
    import os
    host = os.environ.get(COMFYUI_HOST_ENV, "").strip() or COMFYUI_DEFAULT_HOST
    port_str = os.environ.get(COMFYUI_PORT_ENV, "").strip()
    try:
        port = int(port_str) if port_str else COMFYUI_DEFAULT_PORT
    except ValueError:
        port = COMFYUI_DEFAULT_PORT
    return {"host": host, "port": port}

@router.post("/api/settings/comfyui")
def api_comfyui_config_save(body: dict[str, Any]) -> dict[str, Any]:
    """Save ComfyUI connection config.

    Body: {"host": "127.0.0.1", "port": 8188}
    """
    from config.settings import COMFYUI_HOST_ENV, COMFYUI_PORT_ENV
    from core.api_keys import APIKeyManager
    import os

    host = (body.get("host") or "").strip()
    port_raw = body.get("port", "")
    if not host:
        raise HTTPException(status_code=400, detail="'host' is required.")
    try:
        port = int(port_raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="'port' must be an integer.")
    if port < 1 or port > 65535:
        raise HTTPException(
            status_code=400,
            detail=f"Port must be between 1 and 65535, got {port}.",
        )

    os.environ[COMFYUI_HOST_ENV] = host
    os.environ[COMFYUI_PORT_ENV] = str(port)

    mgr = APIKeyManager()
    mgr.save_env_value(COMFYUI_HOST_ENV, host)
    mgr.save_env_value(COMFYUI_PORT_ENV, str(port))

    # Invalidate the pipeline singleton so it picks up the new address
    import core.routes.generation as _gen_mod
    _gen_mod._generation_pipeline = None

    return {"host": host, "port": port, "saved": True}

@router.post("/api/settings/comfyui/test")
def api_comfyui_test() -> dict[str, Any]:
    """Test connection to ComfyUI server.

    Uses the currently configured host/port.
    """
    import asyncio
    from config.settings import (
        COMFYUI_DEFAULT_HOST,
        COMFYUI_DEFAULT_PORT,
        COMFYUI_HOST_ENV,
        COMFYUI_PORT_ENV,
    )
    from core.comfyui_client import (
        ComfyUIClient,
        ComfyUIConfig,
        ComfyUIConnectionError,
    )
    import os

    host = os.environ.get(COMFYUI_HOST_ENV, "").strip() or COMFYUI_DEFAULT_HOST
    port_str = os.environ.get(COMFYUI_PORT_ENV, "").strip()
    try:
        port = int(port_str) if port_str else COMFYUI_DEFAULT_PORT
    except ValueError:
        port = COMFYUI_DEFAULT_PORT

    config = ComfyUIConfig(host=host, port=port)

    async def _test():
        async with ComfyUIClient(config, timeout=5.0) as client:
            return await client.test_connection()

    try:
        stats = asyncio.run(_test())
        return {
            "connected": True,
            "host": host,
            "port": port,
            "system_stats": stats,
        }
    except ComfyUIConnectionError as exc:
        return {
            "connected": False,
            "host": host,
            "port": port,
            "error": str(exc),
        }
    except Exception as exc:
        return {
            "connected": False,
            "host": host,
            "port": port,
            "error": f"Unexpected error: {exc}",
        }

@router.get("/api/settings/comfyui/templates")
def api_comfyui_templates_list(
    entity_type: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List all workflow templates."""
    from core.comfyui_client import WorkflowTemplateManager
    mgr = WorkflowTemplateManager()
    templates = mgr.list_templates(entity_type=entity_type)
    # Return summary (omit full workflow_json for list view)
    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "entity_type": t.entity_type,
            "author": t.author,
            "placeholders": t.placeholders,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
        }
        for t in templates
    ]

@router.post("/api/settings/comfyui/templates")
def api_comfyui_template_create(body: dict[str, Any]) -> dict[str, Any]:
    """Upload a new workflow template.

    Body: {"name": "...", "workflow_json": {...},
           "description": "", "entity_type": "", "author": ""}
    """
    from core.comfyui_client import (
        WorkflowTemplateManager,
        TemplateValidationError,
    )
    name = (body.get("name") or "").strip()
    workflow_json = body.get("workflow_json")
    description = (body.get("description") or "").strip()
    entity_type = (body.get("entity_type") or "").strip()
    author = (body.get("author") or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="'name' is required.")
    if not workflow_json or not isinstance(workflow_json, dict):
        raise HTTPException(
            status_code=400,
            detail="'workflow_json' must be a non-empty JSON object.",
        )

    mgr = WorkflowTemplateManager()
    try:
        tpl = mgr.create(
            name,
            description=description,
            workflow_json=workflow_json,
            entity_type=entity_type,
            author=author,
        )
    except TemplateValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return tpl.to_dict()

@router.get("/api/settings/comfyui/templates/{template_id}")
def api_comfyui_template_get(template_id: str) -> dict[str, Any]:
    """Get a single workflow template with full JSON."""
    from core.comfyui_client import (
        WorkflowTemplateManager,
        TemplateNotFoundError,
    )
    mgr = WorkflowTemplateManager()
    try:
        tpl = mgr.get(template_id)
    except TemplateNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_id}' not found.",
        )
    return tpl.to_dict()

@router.delete("/api/settings/comfyui/templates/{template_id}")
def api_comfyui_template_delete(template_id: str) -> dict[str, Any]:
    """Delete a workflow template."""
    from core.comfyui_client import (
        WorkflowTemplateManager,
        TemplateNotFoundError,
    )
    mgr = WorkflowTemplateManager()
    try:
        mgr.delete(template_id)
    except TemplateNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Template '{template_id}' not found.",
        )
    return {"deleted": True, "template_id": template_id}

@router.get("/api/settings/comfyui/style-presets")
def api_comfyui_style_presets() -> list[dict[str, Any]]:
    """List available prompt style presets (builtins + custom).

    Each entry includes: key, name, description, positive_suffix,
    negative_prefix, is_builtin flag.
    """
    from core.prompt_builder import (
        DEFAULT_STYLE_PRESETS, CustomStylePresetManager,
    )

    results = []

    # Built-in presets
    for key in sorted(DEFAULT_STYLE_PRESETS):
        p = DEFAULT_STYLE_PRESETS[key]
        results.append({
            "key": key,
            "name": p.name,
            "description": p.description,
            "positive_suffix": p.positive_suffix,
            "negative_prefix": p.negative_prefix,
            "is_builtin": True,
        })

    # Custom presets
    try:
        mgr = CustomStylePresetManager()
        for rec in mgr.list_presets():
            results.append({
                "id": rec["id"],
                "key": rec["key"],
                "name": rec["name"],
                "description": rec.get("description", ""),
                "positive_suffix": rec.get("positive_suffix", ""),
                "negative_prefix": rec.get("negative_prefix", ""),
                "is_builtin": False,
                "created_at": rec.get("created_at", ""),
            })
    except Exception:
        pass

    return results

@router.get("/api/settings/comfyui/default-style")
def api_comfyui_default_style_get() -> dict[str, Any]:
    """Return the current default style preset key."""
    from config.settings import COMFYUI_DEFAULT_STYLE_ENV
    import os
    key = os.environ.get(COMFYUI_DEFAULT_STYLE_ENV, "").strip()
    return {"style_key": key or ""}

@router.post("/api/settings/comfyui/default-style")
def api_comfyui_default_style_save(body: dict[str, Any]) -> dict[str, Any]:
    """Save the default style preset key.

    Body: {"style_key": "fantasy_art"}
    """
    from config.settings import COMFYUI_DEFAULT_STYLE_ENV
    from core.api_keys import APIKeyManager
    import os

    style_key = (body.get("style_key") or "").strip()

    # Validate if non-empty
    if style_key:
        from core.prompt_builder import get_style_preset
        if get_style_preset(style_key) is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown style preset '{style_key}'.",
            )

    os.environ[COMFYUI_DEFAULT_STYLE_ENV] = style_key
    mgr = APIKeyManager()
    mgr.save_env_value(COMFYUI_DEFAULT_STYLE_ENV, style_key)

    return {"style_key": style_key, "saved": True}

# ── Custom Style Presets CRUD (F-037g) ────────────────────

@router.get("/api/settings/comfyui/presets")
def api_custom_presets_list() -> list[dict[str, Any]]:
    """List all custom style presets (excludes builtins)."""
    from core.prompt_builder import CustomStylePresetManager
    mgr = CustomStylePresetManager()
    results = []
    for rec in mgr.list_presets():
        # Exclude the StylePreset object (not JSON-serializable)
        entry = {k: v for k, v in rec.items() if k != "preset"}
        results.append(entry)
    return results

@router.post("/api/settings/comfyui/presets")
def api_custom_presets_create(body: dict[str, Any]) -> dict[str, Any]:
    """Create a custom style preset.

    Body: {
        "key": "cyberpunk",
        "name": "Cyberpunk",
        "description": "Neon-lit dystopian cityscapes",
        "positive_suffix": "cyberpunk, neon, rain",
        "negative_prefix": "nature, medieval, fantasy"
    }
    """
    from core.prompt_builder import (
        CustomStylePresetManager, PromptValidationError,
    )
    mgr = CustomStylePresetManager()
    try:
        record = mgr.create(
            key=body.get("key", ""),
            name=body.get("name", ""),
            description=body.get("description", ""),
            positive_suffix=body.get("positive_suffix", ""),
            negative_prefix=body.get("negative_prefix", ""),
        )
    except PromptValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return record

@router.get("/api/settings/comfyui/presets/{preset_id}")
def api_custom_presets_get(preset_id: str) -> dict[str, Any]:
    """Get a custom style preset by ID."""
    from core.prompt_builder import (
        CustomStylePresetManager, PromptValidationError,
    )
    mgr = CustomStylePresetManager()
    try:
        return mgr.get(preset_id)
    except PromptValidationError:
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{preset_id}' not found.",
        )

@router.put("/api/settings/comfyui/presets/{preset_id}")
def api_custom_presets_update(
    preset_id: str, body: dict[str, Any],
) -> dict[str, Any]:
    """Update a custom style preset.

    Body: Any subset of {name, description, positive_suffix, negative_prefix}
    """
    from core.prompt_builder import (
        CustomStylePresetManager, PromptValidationError,
    )
    mgr = CustomStylePresetManager()
    kwargs: dict[str, Any] = {}
    if "name" in body:
        kwargs["name"] = body["name"]
    if "description" in body:
        kwargs["description"] = body["description"]
    if "positive_suffix" in body:
        kwargs["positive_suffix"] = body["positive_suffix"]
    if "negative_prefix" in body:
        kwargs["negative_prefix"] = body["negative_prefix"]

    try:
        return mgr.update(preset_id, **kwargs)
    except PromptValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@router.delete("/api/settings/comfyui/presets/{preset_id}")
def api_custom_presets_delete(preset_id: str) -> dict[str, Any]:
    """Delete a custom style preset."""
    from core.prompt_builder import (
        CustomStylePresetManager, PromptValidationError,
    )
    mgr = CustomStylePresetManager()
    try:
        mgr.delete(preset_id)
    except PromptValidationError:
        raise HTTPException(
            status_code=404,
            detail=f"Preset '{preset_id}' not found.",
        )
    return {"deleted": True, "preset_id": preset_id}

@router.get("/api/settings/comfyui/presets/export")
def api_custom_presets_export() -> list[dict[str, Any]]:
    """Export all custom presets as JSON."""
    from core.prompt_builder import CustomStylePresetManager
    mgr = CustomStylePresetManager()
    return mgr.export_json()

@router.post("/api/settings/comfyui/presets/import")
def api_custom_presets_import(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Import presets from JSON.

    Body: {"presets": [{key, name, description, positive_suffix, negative_prefix}, ...]}
    """
    from core.prompt_builder import CustomStylePresetManager
    mgr = CustomStylePresetManager()
    presets_data = body.get("presets", [])
    if not isinstance(presets_data, list):
        raise HTTPException(
            status_code=400,
            detail="'presets' must be a list.",
        )
    created = mgr.import_json(presets_data)
    return {
        "imported_count": len(created),
        "presets": created,
    }

# ── Per-Entity-Type Template Assignments (F-039) ──────────

@router.get("/api/settings/comfyui/template-assignments")
def api_template_assignments_get() -> dict[str, str]:
    """Get all per-entity-type template assignments.

    Returns: {"character": "TPL-0001", "location": "", ...}
    """
    from core.template_assignments import TemplateAssignmentManager
    from core.comfyui_client import WorkflowTemplateManager

    mgr = TemplateAssignmentManager(
        template_manager=WorkflowTemplateManager(),
    )
    return mgr.get_all_assignments()

@router.post("/api/settings/comfyui/template-assignments")
def api_template_assignments_save(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Save per-entity-type template assignments.

    Body: {"character": "TPL-0001", "location": "TPL-0002", ...}

    Only valid entity types are accepted; others are ignored.
    """
    from core.template_assignments import (
        TemplateAssignmentManager,
        TemplateAssignmentValidationError,
    )
    from core.comfyui_client import WorkflowTemplateManager

    mgr = TemplateAssignmentManager(
        template_manager=WorkflowTemplateManager(),
    )
    try:
        result = mgr.set_all_assignments(body)
    except TemplateAssignmentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"assignments": result, "saved": True}

@router.delete(
    "/api/settings/comfyui/template-assignments/{entity_type}"
)
def api_template_assignments_clear(
    entity_type: str,
) -> dict[str, Any]:
    """Clear the template assignment for an entity type."""
    from core.template_assignments import (
        TemplateAssignmentManager,
        TemplateAssignmentValidationError,
    )
    from core.comfyui_client import WorkflowTemplateManager

    mgr = TemplateAssignmentManager(
        template_manager=WorkflowTemplateManager(),
    )
    try:
        result = mgr.clear_assignment(entity_type)
    except TemplateAssignmentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {"assignments": result, "cleared": entity_type}

@router.get(
    "/api/settings/comfyui/recommended-template/{entity_type}"
)
def api_recommended_template(entity_type: str) -> dict[str, Any]:
    """Get the recommended template for an entity type.

    Uses the smart fallback chain:
    1. Explicit assignment
    2. First template with matching entity_type field
    3. First template overall

    Returns: {"entity_type": "...", "template_id": "...", "source": "..."}
    """
    from core.template_assignments import TemplateAssignmentManager
    from core.comfyui_client import WorkflowTemplateManager

    tmgr = WorkflowTemplateManager()
    mgr = TemplateAssignmentManager(template_manager=tmgr)

    # Determine which fallback was used
    assigned = mgr.get_all_assignments().get(entity_type, "")
    recommended = mgr.get_recommended_template(entity_type)

    if assigned and assigned == recommended:
        source = "assignment"
    elif recommended:
        # Check if it came from entity_type match
        matching = tmgr.list_templates(entity_type=entity_type)
        if matching and matching[0].id == recommended:
            source = "entity_type_match"
        else:
            source = "fallback"
    else:
        source = "none"

    return {
        "entity_type": entity_type,
        "template_id": recommended,
        "source": source,
    }

@router.post(
    "/api/settings/comfyui/template-assignments/test/{template_id}"
)
def api_template_test(template_id: str) -> dict[str, Any]:
    """Test a template's validity and placeholder coverage.

    Returns info about which placeholders the template has
    and whether critical ones (prompt, negative, seed, etc.) are present.
    """
    from core.template_assignments import (
        TemplateAssignmentManager,
        TemplateAssignmentValidationError,
    )
    from core.comfyui_client import WorkflowTemplateManager

    mgr = TemplateAssignmentManager(
        template_manager=WorkflowTemplateManager(),
    )
    try:
        return mgr.test_template(template_id)
    except TemplateAssignmentValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

