"""
Jericho — Per-Entity-Type Workflow Template Assignments (F-039)

Manages default ComfyUI workflow template assignments per entity type.
Each entity type (character, location, item, store) can be assigned a
preferred workflow template that is automatically pre-selected in the
Generate Image modal.

Storage: single JSON file at ``data/comfyui/template_assignments.json``.

Template recommendation uses a smart fallback chain:

1. Explicit assignment (user-configured)
2. First template whose ``entity_type`` field matches
3. First template overall

Usage::

    mgr = TemplateAssignmentManager()
    mgr.set_assignment("character", "TPL-0001")
    recommended = mgr.get_recommended_template("character")
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config.settings import (
    COMFYUI_TEMPLATE_ASSIGNMENTS_FILE,
    COMFYUI_ASSIGNABLE_ENTITY_TYPES,
)
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class TemplateAssignmentError(Exception):
    """Base exception for template assignment errors."""


class TemplateAssignmentValidationError(TemplateAssignmentError):
    """Raised when assignment data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


# ─── Template Assignment Manager ─────────────────────────────


class TemplateAssignmentManager:
    """Manages per-entity-type workflow template assignments.

    Assignments are stored as a flat JSON object mapping entity type
    strings to template IDs::

        {
            "character": "TPL-0001",
            "location": "TPL-0002",
            "item": "",
            "store": ""
        }

    An empty string means no explicit assignment (use fallback).

    Usage::

        mgr = TemplateAssignmentManager()
        mgr.set_assignment("character", "TPL-0001")
        template_id = mgr.get_recommended_template("character")
    """

    def __init__(
        self,
        assignments_file: Path | None = None,
        template_manager: Any = None,
    ) -> None:
        self._file = assignments_file or COMFYUI_TEMPLATE_ASSIGNMENTS_FILE
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._template_manager = template_manager

    # ── Properties ───────────────────────────────────────────

    @property
    def file_path(self) -> Path:
        return self._file

    # ── Read ─────────────────────────────────────────────────

    def get_all_assignments(self) -> dict[str, str]:
        """Return all current assignments as {entity_type: template_id}.

        Missing entity types are filled with empty strings.
        """
        data = self._load()
        # Ensure all valid entity types are present
        result: dict[str, str] = {}
        for et in COMFYUI_ASSIGNABLE_ENTITY_TYPES:
            result[et] = data.get(et, "")
        return result

    def get_assignment(self, entity_type: str) -> str:
        """Return the assigned template ID for an entity type.

        Returns empty string if no assignment exists.

        Raises:
            TemplateAssignmentValidationError: If entity_type is invalid.
        """
        self._validate_entity_type(entity_type)
        data = self._load()
        return data.get(entity_type, "")

    # ── Write ────────────────────────────────────────────────

    def set_assignment(
        self,
        entity_type: str,
        template_id: str,
    ) -> dict[str, str]:
        """Assign a template to an entity type.

        Args:
            entity_type: One of the valid entity types.
            template_id: The template ID (e.g. ``TPL-0001``).
                Use empty string to clear the assignment.

        Returns:
            Updated assignments dict.

        Raises:
            TemplateAssignmentValidationError: If entity_type is invalid
                or template_id does not exist.
        """
        self._validate_entity_type(entity_type)

        template_id = template_id.strip()

        # Validate template exists (if non-empty and we have a manager)
        if template_id and self._template_manager is not None:
            from core.comfyui_client import TemplateNotFoundError
            try:
                self._template_manager.get(template_id)
            except TemplateNotFoundError:
                raise TemplateAssignmentValidationError(
                    f"Template '{template_id}' not found."
                )

        data = self._load()
        data[entity_type] = template_id
        self._save(data)
        return self.get_all_assignments()

    def clear_assignment(self, entity_type: str) -> dict[str, str]:
        """Clear the assignment for an entity type.

        Returns:
            Updated assignments dict.

        Raises:
            TemplateAssignmentValidationError: If entity_type is invalid.
        """
        return self.set_assignment(entity_type, "")

    def set_all_assignments(
        self,
        assignments: dict[str, str],
    ) -> dict[str, str]:
        """Bulk update assignments.

        Only valid entity types are accepted; others are silently ignored.

        Args:
            assignments: Dict of {entity_type: template_id}.

        Returns:
            Updated assignments dict.

        Raises:
            TemplateAssignmentValidationError: If a template_id is
                non-empty and does not exist.
        """
        data = self._load()

        for et, tpl_id in assignments.items():
            if et not in COMFYUI_ASSIGNABLE_ENTITY_TYPES:
                continue
            tpl_id = tpl_id.strip() if tpl_id else ""

            # Validate template exists
            if tpl_id and self._template_manager is not None:
                from core.comfyui_client import TemplateNotFoundError
                try:
                    self._template_manager.get(tpl_id)
                except TemplateNotFoundError:
                    raise TemplateAssignmentValidationError(
                        f"Template '{tpl_id}' not found."
                    )

            data[et] = tpl_id

        self._save(data)
        return self.get_all_assignments()

    # ── Recommend ────────────────────────────────────────────

    def get_recommended_template(
        self,
        entity_type: str,
    ) -> str:
        """Get the best template for an entity type using fallback chain.

        Fallback order:
        1. Explicit assignment
        2. First template whose ``entity_type`` field matches
        3. First template overall

        Returns:
            Template ID string, or empty string if no templates exist.
        """
        # Normalise entity type
        entity_type = entity_type.strip().lower()

        # 1. Explicit assignment
        try:
            assigned = self.get_assignment(entity_type)
            if assigned:
                # Verify it still exists
                if self._template_manager is not None:
                    from core.comfyui_client import TemplateNotFoundError
                    try:
                        self._template_manager.get(assigned)
                        return assigned
                    except TemplateNotFoundError:
                        pass  # Assignment stale, fall through
                else:
                    return assigned
        except TemplateAssignmentValidationError:
            pass  # Unknown entity type, fall through

        # 2. First template whose entity_type field matches
        if self._template_manager is not None:
            matching = self._template_manager.list_templates(
                entity_type=entity_type,
            )
            if matching:
                return matching[0].id

        # 3. First template overall
        if self._template_manager is not None:
            all_templates = self._template_manager.list_templates()
            if all_templates:
                return all_templates[0].id

        return ""

    # ── Test Template ────────────────────────────────────────

    def test_template(self, template_id: str) -> dict[str, Any]:
        """Validate that a template can be used for generation.

        Checks:
        - Template exists
        - Has workflow_json
        - Reports which placeholder tokens it requires

        Returns:
            Dict with ``valid``, ``template_id``, ``name``,
            ``placeholders``, ``missing_critical``, ``entity_type``.

        Raises:
            TemplateAssignmentValidationError: If template_id is empty.
        """
        if not template_id.strip():
            raise TemplateAssignmentValidationError(
                "template_id is required."
            )

        if self._template_manager is None:
            raise TemplateAssignmentValidationError(
                "No template manager available."
            )

        from core.comfyui_client import TemplateNotFoundError

        try:
            tpl = self._template_manager.get(template_id)
        except TemplateNotFoundError:
            return {
                "valid": False,
                "template_id": template_id,
                "name": "",
                "error": f"Template '{template_id}' not found.",
                "placeholders": [],
                "missing_critical": [],
                "entity_type": "",
            }

        # Critical placeholders that the pipeline always fills
        critical = {"prompt", "negative", "seed", "width", "height"}
        has_placeholders = set(tpl.placeholders)
        missing_critical = sorted(critical - has_placeholders)

        return {
            "valid": True,
            "template_id": tpl.id,
            "name": tpl.name,
            "description": tpl.description,
            "entity_type": tpl.entity_type,
            "placeholders": tpl.placeholders,
            "missing_critical": missing_critical,
            "has_prompt": "prompt" in has_placeholders,
            "has_negative": "negative" in has_placeholders,
            "has_dimensions": (
                "width" in has_placeholders
                and "height" in has_placeholders
            ),
        }

    # ── Internal ─────────────────────────────────────────────

    def _validate_entity_type(self, entity_type: str) -> None:
        """Raise if entity_type is not valid."""
        if not entity_type or not entity_type.strip():
            raise TemplateAssignmentValidationError(
                "entity_type is required."
            )
        if entity_type.strip().lower() not in COMFYUI_ASSIGNABLE_ENTITY_TYPES:
            raise TemplateAssignmentValidationError(
                f"Invalid entity type '{entity_type}'. "
                f"Must be one of: {', '.join(COMFYUI_ASSIGNABLE_ENTITY_TYPES)}"
            )

    def _load(self) -> dict[str, str]:
        """Load assignments from disk."""
        if not self._file.exists():
            return {}
        try:
            text = self._file.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, dict):
                return {}
            return data
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self, data: dict[str, str]) -> None:
        """Save assignments to disk."""
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        atomic_write(self._file, payload)

    def __repr__(self) -> str:
        assignments = self.get_all_assignments()
        active = sum(1 for v in assignments.values() if v)
        return (
            f"TemplateAssignmentManager("
            f"assignments={active}/{len(assignments)}, "
            f"file={self._file})"
        )
