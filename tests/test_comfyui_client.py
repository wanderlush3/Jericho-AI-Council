"""
Tests for core.comfyui_client (F-037a)

Coverage:
- Data classes (ComfyUIConfig, WorkflowTemplate, GenerationJob)
- Placeholder detection and filling
- WorkflowTemplateManager CRUD
- ComfyUIClient (mocked HTTP)
- Exception hierarchy
- Edge cases
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.comfyui_client import (
    KNOWN_PLACEHOLDERS,
    PLACEHOLDER_PATTERN,
    ComfyUIClient,
    ComfyUIConfig,
    ComfyUIConnectionError,
    ComfyUIError,
    ComfyUIWorkflowError,
    GenerationJob,
    TemplateError,
    TemplateNotFoundError,
    TemplateValidationError,
    WorkflowTemplate,
    WorkflowTemplateManager,
    detect_placeholders,
    ensure_preview_output,
    fill_placeholders,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════


def _sample_workflow(**overrides: Any) -> dict[str, Any]:
    """Return a minimal ComfyUI-style workflow JSON with placeholders."""
    wf: dict[str, Any] = {
        "3": {
            "class_type": "KSampler",
            "inputs": {
                "seed": "%seed%",
                "steps": 20,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "6": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "%prompt%",
            },
        },
        "7": {
            "class_type": "CLIPTextEncode",
            "inputs": {
                "text": "%negative%",
            },
        },
        "5": {
            "class_type": "EmptyLatentImage",
            "inputs": {
                "width": "%width%",
                "height": "%height%",
                "batch_size": 1,
            },
        },
    }
    wf.update(overrides)
    return wf


def _workflow_no_placeholders() -> dict[str, Any]:
    """Workflow with no placeholder tokens."""
    return {
        "1": {
            "class_type": "KSampler",
            "inputs": {"seed": 42, "steps": 20},
        },
    }


@pytest.fixture
def tmp_templates_dir(tmp_path: Path) -> Path:
    d = tmp_path / "templates"
    d.mkdir()
    return d


@pytest.fixture
def mgr(tmp_templates_dir: Path) -> WorkflowTemplateManager:
    return WorkflowTemplateManager(templates_dir=tmp_templates_dir)


# ═══════════════════════════════════════════════════════════════
# ComfyUIConfig
# ═══════════════════════════════════════════════════════════════


class TestComfyUIConfig:

    def test_fields(self) -> None:
        cfg = ComfyUIConfig(host="1.2.3.4", port=9999)
        assert cfg.host == "1.2.3.4"
        assert cfg.port == 9999

    def test_defaults(self) -> None:
        cfg = ComfyUIConfig()
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8007

    def test_base_url(self) -> None:
        cfg = ComfyUIConfig(host="10.0.0.1", port=8200)
        assert cfg.base_url == "http://10.0.0.1:8200"

    def test_frozen(self) -> None:
        cfg = ComfyUIConfig()
        with pytest.raises(AttributeError):
            cfg.host = "other"  # type: ignore[misc]

    def test_to_dict_roundtrip(self) -> None:
        cfg = ComfyUIConfig(host="myhost", port=1234)
        d = cfg.to_dict()
        restored = ComfyUIConfig.from_dict(d)
        assert restored.host == cfg.host
        assert restored.port == cfg.port

    def test_create_factory(self) -> None:
        cfg = ComfyUIConfig.create(host="  192.168.1.1  ", port=8188)
        assert cfg.host == "192.168.1.1"
        assert cfg.port == 8188

    def test_create_empty_host_raises(self) -> None:
        with pytest.raises(TemplateValidationError) as exc_info:
            ComfyUIConfig.create(host="   ", port=8188)
        assert "Host is required" in exc_info.value.errors[0]

    def test_create_invalid_port_raises(self) -> None:
        with pytest.raises(TemplateValidationError) as exc_info:
            ComfyUIConfig.create(host="localhost", port=0)
        assert "Port" in exc_info.value.errors[0]

    def test_create_port_too_high_raises(self) -> None:
        with pytest.raises(TemplateValidationError) as exc_info:
            ComfyUIConfig.create(host="localhost", port=70000)
        assert "Port" in exc_info.value.errors[0]

    def test_from_dict_defaults(self) -> None:
        cfg = ComfyUIConfig.from_dict({})
        assert cfg.host == "127.0.0.1"
        assert cfg.port == 8007


# ═══════════════════════════════════════════════════════════════
# WorkflowTemplate
# ═══════════════════════════════════════════════════════════════


class TestWorkflowTemplate:

    def test_fields(self) -> None:
        tpl = WorkflowTemplate(
            id="TPL-0001",
            name="My Template",
            description="A test",
            workflow_json={"1": {}},
        )
        assert tpl.id == "TPL-0001"
        assert tpl.name == "My Template"

    def test_frozen(self) -> None:
        tpl = WorkflowTemplate(
            id="TPL-0001", name="x", description="", workflow_json={},
        )
        with pytest.raises(AttributeError):
            tpl.name = "other"  # type: ignore[misc]

    def test_to_dict_roundtrip(self) -> None:
        tpl = WorkflowTemplate(
            id="TPL-0001",
            name="Test",
            description="Desc",
            workflow_json=_sample_workflow(),
            placeholders=["prompt", "seed"],
            entity_type="character",
            author="User",
        )
        d = tpl.to_dict()
        restored = WorkflowTemplate.from_dict(d)
        assert restored.id == tpl.id
        assert restored.placeholders == tpl.placeholders
        assert restored.workflow_json == tpl.workflow_json

    def test_create_factory(self) -> None:
        wf = _sample_workflow()
        tpl = WorkflowTemplate.create(
            id="TPL-0001",
            name="Factory Test",
            workflow_json=wf,
            author="User",
        )
        assert tpl.id == "TPL-0001"
        assert tpl.name == "Factory Test"
        assert tpl.created_at != ""
        assert tpl.updated_at != ""
        # Should auto-detect placeholders
        assert "prompt" in tpl.placeholders
        assert "seed" in tpl.placeholders
        assert "negative" in tpl.placeholders

    def test_create_factory_no_placeholders(self) -> None:
        wf = _workflow_no_placeholders()
        tpl = WorkflowTemplate.create(
            id="TPL-0001",
            name="No Placeholders",
            workflow_json=wf,
        )
        assert tpl.placeholders == []

    def test_defaults(self) -> None:
        tpl = WorkflowTemplate(
            id="TPL-0001", name="x", description="", workflow_json={},
        )
        assert tpl.entity_type == ""
        assert tpl.author == ""
        assert tpl.placeholders == []
        assert tpl.metadata == {}

    def test_from_dict_missing_optionals(self) -> None:
        data = {"id": "TPL-0001", "name": "x", "workflow_json": {}}
        tpl = WorkflowTemplate.from_dict(data)
        assert tpl.description == ""
        assert tpl.entity_type == ""
        assert tpl.metadata == {}


# ═══════════════════════════════════════════════════════════════
# GenerationJob
# ═══════════════════════════════════════════════════════════════


class TestGenerationJob:

    def test_fields(self) -> None:
        job = GenerationJob(
            job_id="GEN-0001",
            prompt_id="abc-123",
            template_id="TPL-0001",
        )
        assert job.job_id == "GEN-0001"
        assert job.prompt_id == "abc-123"
        assert job.status == "queued"

    def test_frozen(self) -> None:
        job = GenerationJob(
            job_id="GEN-0001", prompt_id="x", template_id="TPL-0001",
        )
        with pytest.raises(AttributeError):
            job.status = "done"  # type: ignore[misc]

    def test_to_dict_roundtrip(self) -> None:
        job = GenerationJob(
            job_id="GEN-0001",
            prompt_id="abc-123",
            template_id="TPL-0001",
            entity_type="character",
            entity_id="CH-0001",
            status="completed",
            output_filename="output_00001_.png",
        )
        d = job.to_dict()
        restored = GenerationJob.from_dict(d)
        assert restored.job_id == job.job_id
        assert restored.prompt_id == job.prompt_id
        assert restored.output_filename == job.output_filename

    def test_create_factory(self) -> None:
        job = GenerationJob.create(
            job_id="GEN-0001",
            prompt_id="abc",
            template_id="TPL-0001",
            entity_type="location",
            entity_id="LOC-0001",
        )
        assert job.status == "queued"
        assert job.created_at != ""
        assert job.completed_at == ""

    def test_defaults(self) -> None:
        job = GenerationJob(
            job_id="GEN-0001", prompt_id="x", template_id="TPL-0001",
        )
        assert job.entity_type == ""
        assert job.entity_id == ""
        assert job.output_filename == ""
        assert job.error == ""
        assert job.metadata == {}


# ═══════════════════════════════════════════════════════════════
# Placeholder Detection
# ═══════════════════════════════════════════════════════════════


class TestDetectPlaceholders:

    def test_finds_basic_placeholders(self) -> None:
        wf = _sample_workflow()
        found = detect_placeholders(wf)
        assert "prompt" in found
        assert "negative" in found
        assert "seed" in found
        assert "width" in found
        assert "height" in found

    def test_no_placeholders(self) -> None:
        wf = _workflow_no_placeholders()
        assert detect_placeholders(wf) == []

    def test_deduplicates(self) -> None:
        wf = {
            "1": {"inputs": {"text": "%prompt%"}},
            "2": {"inputs": {"text": "%prompt%"}},
        }
        found = detect_placeholders(wf)
        assert found.count("prompt") == 1

    def test_sorted(self) -> None:
        wf = {
            "1": {"inputs": {"a": "%seed%", "b": "%prompt%", "c": "%cfg%"}},
        }
        found = detect_placeholders(wf)
        assert found == sorted(found)

    def test_nested_lists(self) -> None:
        wf = {
            "1": {"inputs": {"items": ["%prompt%", ["%seed%"]]}},
        }
        found = detect_placeholders(wf)
        assert "prompt" in found
        assert "seed" in found

    def test_empty_workflow(self) -> None:
        assert detect_placeholders({}) == []

    def test_non_string_values_ignored(self) -> None:
        wf = {"1": {"inputs": {"count": 42, "flag": True, "ratio": 0.5}}}
        assert detect_placeholders(wf) == []


# ═══════════════════════════════════════════════════════════════
# Placeholder Filling
# ═══════════════════════════════════════════════════════════════


class TestFillPlaceholders:

    def test_basic_fill(self) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%"}}}
        filled = fill_placeholders(wf, {"prompt": "a cat sitting"})
        assert filled["1"]["inputs"]["text"] == "a cat sitting"

    def test_multiple_placeholders(self) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%, style: %negative%"}}}
        filled = fill_placeholders(wf, {
            "prompt": "a dog",
            "negative": "blurry",
        })
        assert filled["1"]["inputs"]["text"] == "a dog, style: blurry"

    def test_unfilled_left_alone(self) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%", "seed": "%seed%"}}}
        filled = fill_placeholders(wf, {"prompt": "hello"})
        assert filled["1"]["inputs"]["text"] == "hello"
        assert filled["1"]["inputs"]["seed"] == "%seed%"

    def test_does_not_modify_original(self) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%"}}}
        filled = fill_placeholders(wf, {"prompt": "replaced"})
        assert wf["1"]["inputs"]["text"] == "%prompt%"
        assert filled["1"]["inputs"]["text"] == "replaced"

    def test_non_string_values_preserved(self) -> None:
        wf = {"1": {"inputs": {"count": 42, "flag": True}}}
        filled = fill_placeholders(wf, {"count": "99"})
        assert filled["1"]["inputs"]["count"] == 42  # Not changed
        assert filled["1"]["inputs"]["flag"] is True

    def test_nested_lists(self) -> None:
        wf = {"1": {"inputs": {"items": ["%prompt%", "%seed%"]}}}
        filled = fill_placeholders(wf, {"prompt": "cat", "seed": "123"})
        assert filled["1"]["inputs"]["items"] == ["cat", "123"]

    def test_empty_values(self) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%"}}}
        filled = fill_placeholders(wf, {})
        assert filled["1"]["inputs"]["text"] == "%prompt%"

    def test_numeric_replacement_as_string(self) -> None:
        """Values are always strings; numeric tokens get string replacement."""
        wf = {"1": {"inputs": {"seed": "%seed%"}}}
        filled = fill_placeholders(wf, {"seed": "42"})
        assert filled["1"]["inputs"]["seed"] == "42"


# ═══════════════════════════════════════════════════════════════
# Placeholder Pattern
# ═══════════════════════════════════════════════════════════════


class TestPlaceholderPattern:

    def test_matches_known_tokens(self) -> None:
        for token in ["prompt", "negative", "seed", "width", "height"]:
            text = f"%{token}%"
            match = PLACEHOLDER_PATTERN.search(text)
            assert match is not None
            assert match.group(1) == token

    def test_no_match_without_percent(self) -> None:
        assert PLACEHOLDER_PATTERN.search("prompt") is None

    def test_uppercase_not_matched(self) -> None:
        # Pattern only matches lowercase
        assert PLACEHOLDER_PATTERN.search("%PROMPT%") is None

    def test_known_placeholders_is_frozenset(self) -> None:
        assert isinstance(KNOWN_PLACEHOLDERS, frozenset)
        assert "prompt" in KNOWN_PLACEHOLDERS
        assert "seed" in KNOWN_PLACEHOLDERS


# ═══════════════════════════════════════════════════════════════
# WorkflowTemplateManager — Init
# ═══════════════════════════════════════════════════════════════


class TestTemplateManagerInit:

    def test_creates_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "new_dir"
        assert not d.exists()
        WorkflowTemplateManager(templates_dir=d)
        assert d.exists()

    def test_properties(self, tmp_templates_dir: Path) -> None:
        mgr = WorkflowTemplateManager(templates_dir=tmp_templates_dir)
        assert mgr.directory == tmp_templates_dir

    def test_repr(self, mgr: WorkflowTemplateManager) -> None:
        r = repr(mgr)
        assert "WorkflowTemplateManager" in r
        assert "templates=0" in r


# ═══════════════════════════════════════════════════════════════
# WorkflowTemplateManager — Create
# ═══════════════════════════════════════════════════════════════


class TestTemplateCreate:

    def test_basic(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Test Workflow", workflow_json=wf)
        assert tpl.id == "TPL-0001"
        assert tpl.name == "Test Workflow"
        assert "prompt" in tpl.placeholders

    def test_sequential_ids(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        t1 = mgr.create("First", workflow_json=wf)
        t2 = mgr.create("Second", workflow_json=wf)
        assert t1.id == "TPL-0001"
        assert t2.id == "TPL-0002"

    def test_persistence(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Persistent", workflow_json=wf)
        loaded = mgr.get(tpl.id)
        assert loaded.name == "Persistent"
        assert loaded.workflow_json == wf

    def test_with_all_fields(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create(
            "Full Template",
            description="A full test",
            workflow_json=wf,
            entity_type="character",
            author="TestUser",
            metadata={"source": "export"},
        )
        assert tpl.description == "A full test"
        assert tpl.entity_type == "character"
        assert tpl.author == "TestUser"
        assert tpl.metadata == {"source": "export"}

    def test_empty_name_raises(self, mgr: WorkflowTemplateManager) -> None:
        with pytest.raises(TemplateValidationError) as exc_info:
            mgr.create("   ", workflow_json=_sample_workflow())
        assert "name is required" in exc_info.value.errors[0].lower()

    def test_empty_workflow_raises(self, mgr: WorkflowTemplateManager) -> None:
        with pytest.raises(TemplateValidationError) as exc_info:
            mgr.create("Test", workflow_json={})
        assert "Workflow JSON is required" in exc_info.value.errors[0]

    def test_whitespace_stripping(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create(
            "  Spaced  ",
            description="  desc  ",
            workflow_json=wf,
            author="  Author  ",
            entity_type="  character  ",
        )
        assert tpl.name == "Spaced"
        assert tpl.description == "desc"
        assert tpl.author == "Author"
        assert tpl.entity_type == "character"

    def test_auto_detects_placeholders(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Auto Detect", workflow_json=wf)
        expected = sorted(["prompt", "negative", "seed", "width", "height"])
        assert tpl.placeholders == expected


# ═══════════════════════════════════════════════════════════════
# WorkflowTemplateManager — Read
# ═══════════════════════════════════════════════════════════════


class TestTemplateRead:

    def test_get_by_id(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        created = mgr.create("Readable", workflow_json=wf)
        loaded = mgr.get(created.id)
        assert loaded.name == "Readable"

    def test_get_not_found(self, mgr: WorkflowTemplateManager) -> None:
        with pytest.raises(TemplateNotFoundError) as exc_info:
            mgr.get("TPL-9999")
        assert exc_info.value.template_id == "TPL-9999"

    def test_list_all(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        mgr.create("A", workflow_json=wf)
        mgr.create("B", workflow_json=wf)
        mgr.create("C", workflow_json=wf)
        assert len(mgr.list_templates()) == 3

    def test_list_filter_entity_type(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        mgr.create("Char", workflow_json=wf, entity_type="character")
        mgr.create("Loc", workflow_json=wf, entity_type="location")
        mgr.create("Gen", workflow_json=wf, entity_type="")
        chars = mgr.list_templates(entity_type="character")
        assert len(chars) == 1
        assert chars[0].name == "Char"

    def test_list_filter_author(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        mgr.create("A1", workflow_json=wf, author="Alice")
        mgr.create("B1", workflow_json=wf, author="Bob")
        alice = mgr.list_templates(author="alice")  # case-insensitive
        assert len(alice) == 1
        assert alice[0].name == "A1"

    def test_has_template(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Exists", workflow_json=wf)
        assert mgr.has_template(tpl.id)
        assert not mgr.has_template("TPL-9999")

    def test_list_empty(self, mgr: WorkflowTemplateManager) -> None:
        assert mgr.list_templates() == []

    def test_corrupt_file_skipped(
        self, tmp_templates_dir: Path,
    ) -> None:
        # Write a corrupt JSON file
        corrupt = tmp_templates_dir / "TPL-0001.json"
        corrupt.write_text("not valid json {{{", encoding="utf-8")
        mgr = WorkflowTemplateManager(templates_dir=tmp_templates_dir)
        assert mgr.list_templates() == []


# ═══════════════════════════════════════════════════════════════
# WorkflowTemplateManager — Update
# ═══════════════════════════════════════════════════════════════


class TestTemplateUpdate:

    def test_update_name(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Original", workflow_json=wf)
        updated = mgr.update(tpl.id, name="Renamed")
        assert updated.name == "Renamed"

    def test_update_description(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("D", workflow_json=wf)
        updated = mgr.update(tpl.id, description="New desc")
        assert updated.description == "New desc"

    def test_update_workflow_redetects_placeholders(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Detect", workflow_json=wf)
        assert "prompt" in tpl.placeholders

        new_wf = {"1": {"inputs": {"text": "%entity_name%"}}}
        updated = mgr.update(tpl.id, workflow_json=new_wf)
        assert "entity_name" in updated.placeholders
        assert "prompt" not in updated.placeholders

    def test_update_immutable_raises(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Immutable", workflow_json=wf)
        with pytest.raises(TemplateValidationError) as exc_info:
            mgr.update(tpl.id, id="TPL-9999")
        assert "immutable" in str(exc_info.value).lower()

    def test_update_unknown_field_raises(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Unknown", workflow_json=wf)
        with pytest.raises(TemplateValidationError) as exc_info:
            mgr.update(tpl.id, nonexistent_field="value")
        assert "Unknown" in str(exc_info.value)

    def test_update_not_found(self, mgr: WorkflowTemplateManager) -> None:
        with pytest.raises(TemplateNotFoundError):
            mgr.update("TPL-9999", name="x")

    def test_update_bumps_updated_at(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Bump", workflow_json=wf)
        original_updated = tpl.updated_at
        updated = mgr.update(tpl.id, name="Bumped")
        assert updated.updated_at >= original_updated

    def test_update_multiple_fields(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Multi", workflow_json=wf)
        updated = mgr.update(
            tpl.id, name="New Name", description="New desc",
            entity_type="item",
        )
        assert updated.name == "New Name"
        assert updated.description == "New desc"
        assert updated.entity_type == "item"


# ═══════════════════════════════════════════════════════════════
# WorkflowTemplateManager — Delete
# ═══════════════════════════════════════════════════════════════


class TestTemplateDelete:

    def test_delete(self, mgr: WorkflowTemplateManager) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Deletable", workflow_json=wf)
        assert mgr.has_template(tpl.id)
        mgr.delete(tpl.id)
        assert not mgr.has_template(tpl.id)

    def test_delete_not_found(self, mgr: WorkflowTemplateManager) -> None:
        with pytest.raises(TemplateNotFoundError):
            mgr.delete("TPL-9999")

    def test_delete_preserves_others(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        t1 = mgr.create("Keep", workflow_json=wf)
        t2 = mgr.create("Delete", workflow_json=wf)
        mgr.delete(t2.id)
        assert mgr.has_template(t1.id)
        assert not mgr.has_template(t2.id)


# ═══════════════════════════════════════════════════════════════
# WorkflowTemplateManager — Fill Template
# ═══════════════════════════════════════════════════════════════


class TestFillTemplate:

    def test_fill_template(self, mgr: WorkflowTemplateManager) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%", "neg": "%negative%"}}}
        tpl = mgr.create("Fillable", workflow_json=wf)
        filled = mgr.fill_template(tpl.id, {
            "prompt": "a cat",
            "negative": "blurry",
        })
        assert filled["1"]["inputs"]["text"] == "a cat"
        assert filled["1"]["inputs"]["neg"] == "blurry"

    def test_fill_template_not_found(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        with pytest.raises(TemplateNotFoundError):
            mgr.fill_template("TPL-9999", {"prompt": "x"})

    def test_get_unfilled_placeholders(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create("Unfilled", workflow_json=wf)
        unfilled = mgr.get_unfilled_placeholders(tpl.id, {"prompt": "x"})
        assert "prompt" not in unfilled
        assert "seed" in unfilled
        assert "negative" in unfilled

    def test_get_unfilled_all_satisfied(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%"}}}
        tpl = mgr.create("AllFilled", workflow_json=wf)
        unfilled = mgr.get_unfilled_placeholders(tpl.id, {"prompt": "x"})
        assert unfilled == []


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Init & Context Manager
# ═══════════════════════════════════════════════════════════════


class TestComfyUIClientInit:

    def test_defaults(self) -> None:
        client = ComfyUIClient()
        assert client.config.host == "127.0.0.1"
        assert client.config.port == 8007
        assert client.base_url == "http://127.0.0.1:8007"

    def test_custom_config(self) -> None:
        cfg = ComfyUIConfig(host="10.0.0.1", port=9000)
        client = ComfyUIClient(cfg)
        assert client.config.host == "10.0.0.1"
        assert client.base_url == "http://10.0.0.1:9000"

    def test_repr(self) -> None:
        client = ComfyUIClient()
        r = repr(client)
        assert "ComfyUIClient" in r
        assert "127.0.0.1:8007" in r

    def test_not_entered_raises(self) -> None:
        client = ComfyUIClient()
        with pytest.raises(ComfyUIError, match="context manager"):
            client._ensure_client()


class TestComfyUIClientContextManager:

    @pytest.mark.asyncio
    async def test_enter_exit(self) -> None:
        with patch("core.comfyui_client.ComfyUIClient.__aenter__") as mock_enter:
            mock_client = AsyncMock()
            mock_enter.return_value = mock_client
            # Just verify the class has the right structure
            client = ComfyUIClient()
            assert client._client is None

    @pytest.mark.asyncio
    async def test_close_idempotent(self) -> None:
        client = ComfyUIClient()
        # Should not raise even if never entered
        await client.close()
        await client.close()


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Test Connection (mocked)
# ═══════════════════════════════════════════════════════════════


class TestComfyUIClientTestConnection:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "system": {"os": "linux", "comfyui_version": "0.3.0"},
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        result = await client.test_connection()
        assert "system" in result
        mock_client.get.assert_called_once_with("/system_stats")

    @pytest.mark.asyncio
    async def test_connection_refused(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        client = ComfyUIClient()
        client._client = mock_client

        with pytest.raises(ComfyUIConnectionError) as exc_info:
            await client.test_connection()
        assert "Cannot connect" in str(exc_info.value)
        assert exc_info.value.host == "127.0.0.1"
        assert exc_info.value.port == 8007


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Queue Workflow (mocked)
# ═══════════════════════════════════════════════════════════════


class TestComfyUIClientQueueWorkflow:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"prompt_id": "abc-123-def"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        prompt_id = await client.queue_workflow({"3": {"inputs": {}}})
        assert prompt_id == "abc-123-def"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_with_client_id(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"prompt_id": "xyz"}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        await client.queue_workflow({"3": {}}, client_id="my-client")
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json", call_kwargs[1].get("json", {}))
        assert payload.get("client_id") == "my-client"

    @pytest.mark.asyncio
    async def test_server_reject(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid workflow format"

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        with pytest.raises(ComfyUIWorkflowError) as exc_info:
            await client.queue_workflow({"bad": True})
        assert "rejected" in str(exc_info.value).lower()
        assert "400" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_missing_prompt_id(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        with pytest.raises(ComfyUIWorkflowError, match="prompt_id"):
            await client.queue_workflow({"3": {}})

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            side_effect=ConnectionRefusedError("refused"),
        )

        client = ComfyUIClient()
        client._client = mock_client

        with pytest.raises(ComfyUIConnectionError):
            await client.queue_workflow({"3": {}})


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Get History (mocked)
# ═══════════════════════════════════════════════════════════════


class TestComfyUIClientGetHistory:

    @pytest.mark.asyncio
    async def test_completed(self) -> None:
        history_data = {
            "abc-123": {
                "status": {"completed": True, "status_str": "success"},
                "outputs": {
                    "9": {"images": [{"filename": "out_00001_.png",
                                      "subfolder": "", "type": "output"}]},
                },
            },
        }
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = history_data
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        result = await client.get_history("abc-123")
        assert result["status"]["completed"] is True

    @pytest.mark.asyncio
    async def test_not_found_returns_empty(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        result = await client.get_history("nonexistent")
        assert result == {}

    @pytest.mark.asyncio
    async def test_connection_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        client = ComfyUIClient()
        client._client = mock_client

        with pytest.raises(ComfyUIConnectionError):
            await client.get_history("abc")


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Poll Until Complete (mocked)
# ═══════════════════════════════════════════════════════════════


class TestComfyUIClientPollUntilComplete:

    @pytest.mark.asyncio
    async def test_immediate_complete(self) -> None:
        history = {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {"9": {"images": []}},
        }
        client = ComfyUIClient(poll_interval=0.01, max_poll_attempts=5)
        client._client = MagicMock()  # not None so _ensure_client passes
        with patch.object(client, "get_history", new_callable=AsyncMock) as mock:
            mock.return_value = history
            result = await client.poll_until_complete("abc")
        assert result["status"]["completed"] is True

    @pytest.mark.asyncio
    async def test_delayed_complete(self) -> None:
        empty = {}
        history = {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {},
        }
        client = ComfyUIClient(poll_interval=0.01, max_poll_attempts=10)
        client._client = MagicMock()
        with patch.object(client, "get_history", new_callable=AsyncMock) as mock:
            mock.side_effect = [empty, empty, history]
            result = await client.poll_until_complete("abc")
        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_workflow_error(self) -> None:
        history = {
            "status": {
                "completed": False,
                "status_str": "error",
                "messages": [["execution_error", {"message": "bad node"}]],
            },
        }
        client = ComfyUIClient(poll_interval=0.01, max_poll_attempts=5)
        client._client = MagicMock()
        with patch.object(client, "get_history", new_callable=AsyncMock) as mock:
            mock.return_value = history
            with pytest.raises(ComfyUIWorkflowError) as exc_info:
                await client.poll_until_complete("abc")
        assert exc_info.value.prompt_id == "abc"

    @pytest.mark.asyncio
    async def test_timeout(self) -> None:
        client = ComfyUIClient(poll_interval=0.01, max_poll_attempts=3)
        client._client = MagicMock()
        with patch.object(client, "get_history", new_callable=AsyncMock) as mock:
            mock.return_value = {}  # Never completes
            with pytest.raises(ComfyUIWorkflowError, match="timed out"):
                await client.poll_until_complete("abc")
        assert mock.call_count == 3


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Extract Output Images
# ═══════════════════════════════════════════════════════════════


class TestExtractOutputImages:

    def test_single_image(self) -> None:
        history = {
            "outputs": {
                "9": {
                    "images": [{
                        "filename": "out_00001_.png",
                        "subfolder": "",
                        "type": "output",
                    }],
                },
            },
        }
        images = ComfyUIClient.extract_output_images(history)
        assert len(images) == 1
        assert images[0]["filename"] == "out_00001_.png"
        assert images[0]["type"] == "output"

    def test_multiple_images(self) -> None:
        history = {
            "outputs": {
                "9": {
                    "images": [
                        {"filename": "a.png", "subfolder": "", "type": "output"},
                        {"filename": "b.png", "subfolder": "", "type": "output"},
                    ],
                },
            },
        }
        images = ComfyUIClient.extract_output_images(history)
        assert len(images) == 2

    def test_multiple_nodes(self) -> None:
        history = {
            "outputs": {
                "9": {"images": [{"filename": "a.png", "subfolder": "", "type": "output"}]},
                "12": {"images": [{"filename": "b.png", "subfolder": "", "type": "output"}]},
            },
        }
        images = ComfyUIClient.extract_output_images(history)
        assert len(images) == 2

    def test_no_outputs(self) -> None:
        assert ComfyUIClient.extract_output_images({}) == []
        assert ComfyUIClient.extract_output_images({"outputs": {}}) == []

    def test_no_images_key(self) -> None:
        history = {"outputs": {"9": {"text": "hello"}}}
        assert ComfyUIClient.extract_output_images(history) == []


# ═══════════════════════════════════════════════════════════════
# ensure_preview_output
# ═══════════════════════════════════════════════════════════════


class TestEnsurePreviewOutput:
    """Tests for the automatic PreviewImage node injection."""

    def test_standard_save_node_unchanged(self) -> None:
        """Workflow with a standard SaveImage should not be modified."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {}},
            "2": {"class_type": "VAEDecode", "inputs": {"samples": ["1", 0]}},
            "3": {
                "class_type": "SaveImage",
                "inputs": {"images": ["2", 0], "filename_prefix": "test"},
            },
        }
        result = ensure_preview_output(wf)
        assert len(result) == 3  # No new nodes
        assert "SaveImage" in [n.get("class_type") for n in result.values()]

    def test_preview_image_node_unchanged(self) -> None:
        """Workflow with PreviewImage should not be modified."""
        wf = {
            "1": {"class_type": "VAEDecode", "inputs": {}},
            "2": {
                "class_type": "PreviewImage",
                "inputs": {"images": ["1", 0]},
            },
        }
        result = ensure_preview_output(wf)
        assert len(result) == 2

    def test_custom_save_node_gets_preview_injected(self) -> None:
        """Workflow with only a custom save node should get PreviewImage."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {}},
            "2": {"class_type": "VAEDecode", "inputs": {"samples": ["1", 0]}},
            "3": {
                "class_type": "Save Image (LoraManager)",
                "inputs": {"images": ["2", 0], "filename_prefix": "test"},
            },
        }
        original_keys = set(wf.keys())
        result = ensure_preview_output(wf)
        assert len(result) == 4  # One new node
        new_nodes = {k: v for k, v in result.items() if k not in original_keys}
        assert len(new_nodes) == 1
        preview = list(new_nodes.values())[0]
        assert preview["class_type"] == "PreviewImage"
        assert preview["inputs"]["images"] == ["2", 0]  # Same source

    def test_injected_node_has_high_id(self) -> None:
        """Injected node ID should be far above existing IDs."""
        wf = {
            "20": {"class_type": "VAEDecode", "inputs": {}},
            "30": {
                "class_type": "Save Image (Custom)",
                "inputs": {"images": ["20", 0]},
            },
        }
        original_keys = set(wf.keys())
        result = ensure_preview_output(wf)
        new_ids = [k for k in result if k not in original_keys]
        assert len(new_ids) == 1
        assert int(new_ids[0]) >= 9000  # High offset

    def test_namespaced_ids_handled(self) -> None:
        """Subgraph-namespaced IDs like '13:59' should be parsed."""
        wf = {
            "11": {"class_type": "UltimateSDUpscale", "inputs": {}},
            "13:59": {
                "class_type": "Save Image (LoraManager)",
                "inputs": {"images": ["11", 0]},
            },
        }
        original_keys = set(wf.keys())
        result = ensure_preview_output(wf)
        new_ids = [k for k in result if k not in original_keys]
        assert len(new_ids) == 1
        # Should be >= max(11, 13, 59) + 9000
        assert int(new_ids[0]) >= 9059

    def test_no_save_node_unchanged(self) -> None:
        """Workflow with no save/preview node at all returns unchanged."""
        wf = {
            "1": {"class_type": "KSampler", "inputs": {}},
            "2": {"class_type": "VAEDecode", "inputs": {}},
        }
        result = ensure_preview_output(wf)
        assert len(result) == 2  # No injection

    def test_non_dict_values_skipped(self) -> None:
        """Non-dict values (malformed workflow) shouldn't crash."""
        wf: dict[str, Any] = {"bad": True, "also_bad": "string"}
        result = ensure_preview_output(wf)
        assert result == wf  # Unchanged

    def test_empty_workflow(self) -> None:
        result = ensure_preview_output({})
        assert result == {}


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Download Image (mocked)
# ═══════════════════════════════════════════════════════════════


class TestComfyUIClientDownloadImage:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        fake_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = fake_bytes
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        result = await client.download_image("out_00001_.png")
        assert result == fake_bytes
        mock_client.get.assert_called_once_with(
            "/view",
            params={"filename": "out_00001_.png", "subfolder": "", "type": "output"},
        )

    @pytest.mark.asyncio
    async def test_with_subfolder(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"img"
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        await client.download_image(
            "x.png", subfolder="subdir", image_type="temp",
        )
        call_kwargs = mock_client.get.call_args
        params = call_kwargs.kwargs.get("params", call_kwargs[1].get("params", {}))
        assert params["subfolder"] == "subdir"
        assert params["type"] == "temp"

    @pytest.mark.asyncio
    async def test_download_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))

        client = ComfyUIClient()
        client._client = mock_client

        with pytest.raises(ComfyUIConnectionError, match="download"):
            await client.download_image("x.png")


# ═══════════════════════════════════════════════════════════════
# ComfyUIClient — Upload Image (mocked)
# ═══════════════════════════════════════════════════════════════


class TestComfyUIClientUploadImage:

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "name": "input.png", "subfolder": "", "type": "input",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        client = ComfyUIClient()
        client._client = mock_client

        result = await client.upload_image(b"imgdata", "input.png")
        assert result["name"] == "input.png"
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=ConnectionError("refused"))

        client = ComfyUIClient()
        client._client = mock_client

        with pytest.raises(ComfyUIConnectionError, match="upload"):
            await client.upload_image(b"data", "x.png")


# ═══════════════════════════════════════════════════════════════
# Exception Hierarchy
# ═══════════════════════════════════════════════════════════════


class TestExceptions:

    def test_hierarchy(self) -> None:
        assert issubclass(ComfyUIConnectionError, ComfyUIError)
        assert issubclass(ComfyUIWorkflowError, ComfyUIError)
        assert issubclass(TemplateError, ComfyUIError)
        assert issubclass(TemplateNotFoundError, TemplateError)
        assert issubclass(TemplateValidationError, TemplateError)

    def test_connection_error_fields(self) -> None:
        err = ComfyUIConnectionError("msg", host="h", port=1234)
        assert err.host == "h"
        assert err.port == 1234

    def test_workflow_error_fields(self) -> None:
        err = ComfyUIWorkflowError("msg", prompt_id="abc")
        assert err.prompt_id == "abc"

    def test_not_found_fields(self) -> None:
        err = TemplateNotFoundError("TPL-0001")
        assert err.template_id == "TPL-0001"

    def test_validation_error_fields(self) -> None:
        err = TemplateValidationError(["error1", "error2"])
        assert len(err.errors) == 2
        assert "error1" in str(err)

    def test_validation_error_string(self) -> None:
        err = TemplateValidationError("single error")
        assert err.errors == ["single error"]


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:

    def test_unicode_template(self, mgr: WorkflowTemplateManager) -> None:
        wf = {"1": {"inputs": {"text": "%prompt%"}}}
        tpl = mgr.create(
            "模板名称 — Шаблон",
            description="描述 — описание",
            workflow_json=wf,
            author="作者",
        )
        loaded = mgr.get(tpl.id)
        assert loaded.name == "模板名称 — Шаблон"

    def test_large_workflow(self, mgr: WorkflowTemplateManager) -> None:
        # Simulate a large workflow with many nodes
        wf = {
            str(i): {
                "class_type": f"Node{i}",
                "inputs": {"text": f"%prompt%" if i % 3 == 0 else "static"},
            }
            for i in range(50)
        }
        tpl = mgr.create("Large", workflow_json=wf)
        assert "prompt" in tpl.placeholders

    def test_persistence_roundtrip(
        self, mgr: WorkflowTemplateManager,
    ) -> None:
        wf = _sample_workflow()
        tpl = mgr.create(
            "Roundtrip",
            workflow_json=wf,
            description="test desc",
            entity_type="character",
            author="User",
            metadata={"key": "value"},
        )
        # Create a new manager pointed at the same dir to force re-read
        mgr2 = WorkflowTemplateManager(templates_dir=mgr.directory)
        loaded = mgr2.get(tpl.id)
        assert loaded.name == tpl.name
        assert loaded.workflow_json == tpl.workflow_json
        assert loaded.placeholders == tpl.placeholders
        assert loaded.metadata == tpl.metadata

    def test_fill_deeply_nested(self) -> None:
        wf = {
            "1": {
                "inner": {
                    "deep": {
                        "deeper": [
                            {"nested": "%prompt%"},
                            ["%seed%"],
                        ],
                    },
                },
            },
        }
        filled = fill_placeholders(wf, {"prompt": "cat", "seed": "42"})
        assert filled["1"]["inner"]["deep"]["deeper"][0]["nested"] == "cat"
        assert filled["1"]["inner"]["deep"]["deeper"][1][0] == "42"

    def test_id_gap_sequencing(
        self, tmp_templates_dir: Path,
    ) -> None:
        """IDs are based on max existing, so gaps don't matter."""
        # Create TPL-0003 manually
        data = {
            "id": "TPL-0003",
            "name": "Gap",
            "workflow_json": {"1": {}},
        }
        filepath = tmp_templates_dir / "TPL-0003.json"
        filepath.write_text(json.dumps(data), encoding="utf-8")

        mgr = WorkflowTemplateManager(templates_dir=tmp_templates_dir)
        tpl = mgr.create("Next", workflow_json={"2": {}})
        assert tpl.id == "TPL-0004"

    def test_comfyui_config_equality(self) -> None:
        c1 = ComfyUIConfig(host="localhost", port=8188)
        c2 = ComfyUIConfig(host="localhost", port=8188)
        assert c1 == c2

    def test_generation_job_roundtrip(self) -> None:
        job = GenerationJob.create(
            job_id="GEN-0001",
            prompt_id="abc",
            template_id="TPL-0001",
            entity_type="character",
            entity_id="CH-0001",
            metadata={"style": "anime"},
        )
        d = job.to_dict()
        restored = GenerationJob.from_dict(d)
        assert restored.job_id == job.job_id
        assert restored.metadata == job.metadata
        assert restored.created_at == job.created_at
