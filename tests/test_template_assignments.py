"""
Tests for the Per-Entity-Type Workflow Template Assignments (F-039).

Tests cover:
- TemplateAssignmentManager CRUD operations
- Smart fallback chain (assigned → entity_type match → first available)
- Validation (invalid entity types, nonexistent templates)
- Persistence and reload consistency
- Edge cases
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock

import pytest

from core.template_assignments import (
    TemplateAssignmentManager,
    TemplateAssignmentError,
    TemplateAssignmentValidationError,
)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_dir(tmp_path):
    """Temporary directory for test files."""
    return tmp_path


@pytest.fixture
def assignments_file(tmp_dir):
    """Path to a temporary assignments file."""
    return tmp_dir / "template_assignments.json"


@pytest.fixture
def mock_template_manager():
    """Mock WorkflowTemplateManager with some templates."""
    mgr = MagicMock()

    class FakeTemplate:
        def __init__(self, id, name="", entity_type="", desc=""):
            self.id = id
            self.name = name
            self.entity_type = entity_type
            self.description = desc
            self.placeholders = ["prompt", "negative", "seed", "width", "height"]
            self.workflow_json = {"test": True}

    templates = {
        "TPL-0001": FakeTemplate("TPL-0001", "Portrait", "character"),
        "TPL-0002": FakeTemplate("TPL-0002", "Landscape", "location"),
        "TPL-0003": FakeTemplate("TPL-0003", "General"),
    }

    def fake_get(tpl_id):
        if tpl_id in templates:
            return templates[tpl_id]
        from core.comfyui_client import TemplateNotFoundError
        raise TemplateNotFoundError(tpl_id)

    def fake_list(entity_type=None, author=None):
        result = list(templates.values())
        if entity_type is not None:
            result = [t for t in result if t.entity_type == entity_type]
        return result

    mgr.get = fake_get
    mgr.list_templates = fake_list
    return mgr


@pytest.fixture
def manager(assignments_file, mock_template_manager):
    """TemplateAssignmentManager with mock template manager."""
    return TemplateAssignmentManager(
        assignments_file=assignments_file,
        template_manager=mock_template_manager,
    )


@pytest.fixture
def bare_manager(assignments_file):
    """TemplateAssignmentManager without template manager."""
    return TemplateAssignmentManager(
        assignments_file=assignments_file,
        template_manager=None,
    )


# ─── TestGetAllAssignments ─────────────────────────────────────


class TestGetAllAssignments:
    """Tests for get_all_assignments()."""

    def test_empty_when_no_file(self, manager):
        result = manager.get_all_assignments()
        assert "character" in result
        assert "location" in result
        assert "item" in result
        assert "store" in result
        assert all(v == "" for v in result.values())

    def test_returns_all_entity_types(self, manager):
        result = manager.get_all_assignments()
        assert len(result) == 4

    def test_preserves_set_values(self, manager):
        manager.set_assignment("character", "TPL-0001")
        result = manager.get_all_assignments()
        assert result["character"] == "TPL-0001"
        assert result["location"] == ""

    def test_fills_missing_entity_types(self, manager, assignments_file):
        # Write partial data
        assignments_file.write_text('{"character": "TPL-0001"}', encoding="utf-8")
        result = manager.get_all_assignments()
        assert result["character"] == "TPL-0001"
        assert result["location"] == ""
        assert result["item"] == ""
        assert result["store"] == ""


# ─── TestGetAssignment ─────────────────────────────────────────


class TestGetAssignment:
    """Tests for get_assignment()."""

    def test_empty_when_not_set(self, manager):
        assert manager.get_assignment("character") == ""

    def test_returns_set_value(self, manager):
        manager.set_assignment("character", "TPL-0001")
        assert manager.get_assignment("character") == "TPL-0001"

    def test_invalid_entity_type(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.get_assignment("invalid_type")

    def test_empty_entity_type(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.get_assignment("")

    def test_whitespace_entity_type(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.get_assignment("   ")


# ─── TestSetAssignment ─────────────────────────────────────────


class TestSetAssignment:
    """Tests for set_assignment()."""

    def test_basic(self, manager):
        result = manager.set_assignment("character", "TPL-0001")
        assert result["character"] == "TPL-0001"

    def test_overwrite(self, manager):
        manager.set_assignment("character", "TPL-0001")
        result = manager.set_assignment("character", "TPL-0002")
        assert result["character"] == "TPL-0002"

    def test_clear_with_empty_string(self, manager):
        manager.set_assignment("character", "TPL-0001")
        result = manager.set_assignment("character", "")
        assert result["character"] == ""

    def test_persists_to_disk(self, manager, assignments_file):
        manager.set_assignment("location", "TPL-0002")
        assert assignments_file.exists()
        data = json.loads(assignments_file.read_text(encoding="utf-8"))
        assert data["location"] == "TPL-0002"

    def test_invalid_entity_type(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.set_assignment("invalid", "TPL-0001")

    def test_nonexistent_template(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.set_assignment("character", "TPL-9999")

    def test_strips_whitespace(self, manager):
        result = manager.set_assignment("character", "  TPL-0001  ")
        assert result["character"] == "TPL-0001"

    def test_multiple_entity_types(self, manager):
        manager.set_assignment("character", "TPL-0001")
        manager.set_assignment("location", "TPL-0002")
        result = manager.get_all_assignments()
        assert result["character"] == "TPL-0001"
        assert result["location"] == "TPL-0002"

    def test_without_template_manager(self, bare_manager):
        """Without a template manager, any ID is accepted."""
        result = bare_manager.set_assignment("character", "TPL-ANYTHING")
        assert result["character"] == "TPL-ANYTHING"


# ─── TestClearAssignment ───────────────────────────────────────


class TestClearAssignment:
    """Tests for clear_assignment()."""

    def test_basic(self, manager):
        manager.set_assignment("character", "TPL-0001")
        result = manager.clear_assignment("character")
        assert result["character"] == ""

    def test_clear_already_empty(self, manager):
        result = manager.clear_assignment("character")
        assert result["character"] == ""

    def test_invalid_entity_type(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.clear_assignment("invalid")


# ─── TestSetAllAssignments ─────────────────────────────────────


class TestSetAllAssignments:
    """Tests for set_all_assignments()."""

    def test_bulk_update(self, manager):
        result = manager.set_all_assignments({
            "character": "TPL-0001",
            "location": "TPL-0002",
        })
        assert result["character"] == "TPL-0001"
        assert result["location"] == "TPL-0002"
        assert result["item"] == ""

    def test_ignores_invalid_entity_types(self, manager):
        result = manager.set_all_assignments({
            "character": "TPL-0001",
            "invalid_type": "TPL-0002",
        })
        assert result["character"] == "TPL-0001"
        assert "invalid_type" not in result

    def test_validates_template_exists(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.set_all_assignments({
                "character": "TPL-9999",
            })

    def test_empty_string_clears(self, manager):
        manager.set_assignment("character", "TPL-0001")
        result = manager.set_all_assignments({"character": ""})
        assert result["character"] == ""


# ─── TestGetRecommendedTemplate ────────────────────────────────


class TestGetRecommendedTemplate:
    """Tests for get_recommended_template() smart fallback chain."""

    def test_explicit_assignment_takes_priority(self, manager):
        manager.set_assignment("character", "TPL-0003")  # General template
        # TPL-0001 has entity_type="character" but assignment overrides
        result = manager.get_recommended_template("character")
        assert result == "TPL-0003"

    def test_entity_type_match_fallback(self, manager):
        """No assignment → falls back to template with matching entity_type."""
        result = manager.get_recommended_template("character")
        assert result == "TPL-0001"  # has entity_type="character"

    def test_location_entity_type_match(self, manager):
        result = manager.get_recommended_template("location")
        assert result == "TPL-0002"  # has entity_type="location"

    def test_first_template_fallback(self, manager):
        """No assignment, no entity_type match → first template."""
        result = manager.get_recommended_template("item")
        # item has no entity_type match, so gets first template overall
        assert result in ("TPL-0001", "TPL-0002", "TPL-0003")

    def test_empty_when_no_templates(self, bare_manager):
        result = bare_manager.get_recommended_template("character")
        assert result == ""

    def test_stale_assignment_falls_through(self, manager, assignments_file):
        """If assigned template no longer exists, skip to next fallback."""
        # Manually write a stale assignment
        assignments_file.write_text(
            '{"character": "TPL-DELETED"}', encoding="utf-8"
        )
        result = manager.get_recommended_template("character")
        # Falls through to entity_type match
        assert result == "TPL-0001"

    def test_unknown_entity_type_uses_first(self, manager):
        """Unknown entity types use first-template fallback."""
        result = manager.get_recommended_template("unknown_thing")
        assert result in ("TPL-0001", "TPL-0002", "TPL-0003")


# ─── TestTestTemplate ─────────────────────────────────────────


class TestTestTemplate:
    """Tests for test_template() validation."""

    def test_valid_template(self, manager):
        result = manager.test_template("TPL-0001")
        assert result["valid"] is True
        assert result["template_id"] == "TPL-0001"
        assert result["name"] == "Portrait"
        assert result["has_prompt"] is True
        assert result["has_negative"] is True
        assert result["has_dimensions"] is True
        assert result["missing_critical"] == []

    def test_nonexistent_template(self, manager):
        result = manager.test_template("TPL-9999")
        assert result["valid"] is False
        assert "not found" in result["error"]

    def test_empty_template_id(self, manager):
        with pytest.raises(TemplateAssignmentValidationError):
            manager.test_template("")

    def test_no_template_manager(self, bare_manager):
        with pytest.raises(TemplateAssignmentValidationError):
            bare_manager.test_template("TPL-0001")

    def test_missing_placeholders(self, manager, mock_template_manager):
        """Template missing critical placeholders."""
        # Create a template with limited placeholders
        class LimitedTemplate:
            id = "TPL-0003"
            name = "General"
            description = ""
            entity_type = ""
            placeholders = ["prompt"]  # Missing negative, seed, width, height
            workflow_json = {"test": True}

        mock_template_manager.get = lambda tpl_id: LimitedTemplate() if tpl_id == "TPL-0003" else mock_template_manager.get(tpl_id)

        result = manager.test_template("TPL-0003")
        assert result["valid"] is True
        assert "negative" in result["missing_critical"]
        assert "seed" in result["missing_critical"]
        assert result["has_prompt"] is True
        assert result["has_negative"] is False


# ─── TestPersistence ───────────────────────────────────────────


class TestPersistence:
    """Tests for file persistence."""

    def test_creates_parent_dirs(self, tmp_dir):
        deep_file = tmp_dir / "nested" / "deep" / "assignments.json"
        mgr = TemplateAssignmentManager(assignments_file=deep_file)
        assert deep_file.parent.exists()

    def test_survives_reload(self, assignments_file, mock_template_manager):
        mgr1 = TemplateAssignmentManager(
            assignments_file=assignments_file,
            template_manager=mock_template_manager,
        )
        mgr1.set_assignment("character", "TPL-0001")
        mgr1.set_assignment("location", "TPL-0002")

        mgr2 = TemplateAssignmentManager(
            assignments_file=assignments_file,
            template_manager=mock_template_manager,
        )
        result = mgr2.get_all_assignments()
        assert result["character"] == "TPL-0001"
        assert result["location"] == "TPL-0002"

    def test_handles_corrupt_file(self, assignments_file):
        assignments_file.write_text("NOT JSON!!!", encoding="utf-8")
        mgr = TemplateAssignmentManager(assignments_file=assignments_file)
        result = mgr.get_all_assignments()
        assert all(v == "" for v in result.values())

    def test_handles_wrong_type_in_file(self, assignments_file):
        assignments_file.write_text("[1, 2, 3]", encoding="utf-8")
        mgr = TemplateAssignmentManager(assignments_file=assignments_file)
        result = mgr.get_all_assignments()
        assert all(v == "" for v in result.values())


# ─── TestEdgeCases ─────────────────────────────────────────────


class TestEdgeCases:
    """Edge case testing."""

    def test_unicode_template_ids(self, bare_manager):
        bare_manager.set_assignment("character", "TPL-µ∂∆")
        assert bare_manager.get_assignment("character") == "TPL-µ∂∆"

    def test_repr(self, manager):
        r = repr(manager)
        assert "TemplateAssignmentManager" in r
        assert "0/4" in r

    def test_repr_after_set(self, manager):
        manager.set_assignment("character", "TPL-0001")
        r = repr(manager)
        assert "1/4" in r

    def test_concurrent_entity_types(self, manager):
        """Set all four entity types."""
        manager.set_assignment("character", "TPL-0001")
        manager.set_assignment("location", "TPL-0002")
        manager.set_assignment("item", "TPL-0003")
        manager.set_assignment("store", "TPL-0001")
        result = manager.get_all_assignments()
        assert result["character"] == "TPL-0001"
        assert result["location"] == "TPL-0002"
        assert result["item"] == "TPL-0003"
        assert result["store"] == "TPL-0001"

    def test_file_path_property(self, manager, assignments_file):
        assert manager.file_path == assignments_file


# ─── TestExceptions ────────────────────────────────────────────


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_base_exception(self):
        assert issubclass(TemplateAssignmentError, Exception)

    def test_validation_inherits_base(self):
        assert issubclass(
            TemplateAssignmentValidationError,
            TemplateAssignmentError,
        )

    def test_validation_has_errors_list(self):
        exc = TemplateAssignmentValidationError(["err1", "err2"])
        assert exc.errors == ["err1", "err2"]
        assert "err1" in str(exc)
        assert "err2" in str(exc)

    def test_validation_string_input(self):
        exc = TemplateAssignmentValidationError("single error")
        assert exc.errors == ["single error"]
