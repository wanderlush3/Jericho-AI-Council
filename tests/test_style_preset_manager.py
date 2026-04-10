"""
Tests for F-037g — CustomStylePresetManager.

Exercises CRUD, import/export, merge with builtins, and edge cases.
"""

import json

import pytest


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture()
def presets_dir(tmp_path):
    """Provide a temporary presets directory."""
    d = tmp_path / "presets"
    d.mkdir()
    return d


@pytest.fixture()
def mgr(presets_dir, monkeypatch):
    """Create a CustomStylePresetManager with an isolated directory."""
    monkeypatch.setattr("config.settings.COMFYUI_PRESETS_DIR", presets_dir)
    from core.prompt_builder import CustomStylePresetManager
    return CustomStylePresetManager(presets_dir=presets_dir)


# ── Create ───────────────────────────────────────────────────────


class TestCreate:
    """Tests for CustomStylePresetManager.create()"""

    def test_create_basic(self, mgr):
        record = mgr.create(
            key="cyberpunk",
            name="Cyberpunk",
            description="Neon-lit cityscapes",
            positive_suffix="cyberpunk, neon lights, rain",
            negative_prefix="nature, medieval",
        )
        assert record["id"] == "PST-0001"
        assert record["key"] == "cyberpunk"
        assert record["name"] == "Cyberpunk"
        assert record["description"] == "Neon-lit cityscapes"
        assert record["positive_suffix"] == "cyberpunk, neon lights, rain"
        assert record["negative_prefix"] == "nature, medieval"
        assert "created_at" in record

    def test_create_sequential_ids(self, mgr):
        r1 = mgr.create(key="a", name="A")
        r2 = mgr.create(key="b", name="B")
        r3 = mgr.create(key="c", name="C")
        assert r1["id"] == "PST-0001"
        assert r2["id"] == "PST-0002"
        assert r3["id"] == "PST-0003"

    def test_create_normalizes_key(self, mgr):
        record = mgr.create(key="  My Cool Style  ", name="Cool")
        assert record["key"] == "my_cool_style"

    def test_create_empty_key_fails(self, mgr):
        from core.prompt_builder import PromptValidationError
        with pytest.raises(PromptValidationError):
            mgr.create(key="", name="Test")

    def test_create_empty_name_fails(self, mgr):
        from core.prompt_builder import PromptValidationError
        with pytest.raises(PromptValidationError):
            mgr.create(key="test", name="")

    def test_create_duplicate_key_fails(self, mgr):
        from core.prompt_builder import PromptValidationError
        mgr.create(key="dup", name="First")
        with pytest.raises(PromptValidationError, match="already exists"):
            mgr.create(key="dup", name="Second")


# ── Read ─────────────────────────────────────────────────────────


class TestRead:
    """Tests for get() and list_presets()."""

    def test_get_existing(self, mgr):
        created = mgr.create(key="test", name="Test")
        fetched = mgr.get(created["id"])
        assert fetched["key"] == "test"
        assert fetched["name"] == "Test"

    def test_get_not_found(self, mgr):
        from core.prompt_builder import PromptValidationError
        with pytest.raises(PromptValidationError, match="not found"):
            mgr.get("PST-9999")

    def test_list_empty(self, mgr):
        assert mgr.list_presets() == []

    def test_list_returns_sorted(self, mgr):
        mgr.create(key="zzz", name="Zzz Style")
        mgr.create(key="aaa", name="Aaa Style")
        presets = mgr.list_presets()
        assert len(presets) == 2
        assert presets[0]["name"] == "Aaa Style"
        assert presets[1]["name"] == "Zzz Style"

    def test_list_includes_style_preset_object(self, mgr):
        from core.prompt_builder import StylePreset
        mgr.create(key="test", name="Test", positive_suffix="pos", negative_prefix="neg")
        presets = mgr.list_presets()
        assert len(presets) == 1
        assert isinstance(presets[0]["preset"], StylePreset)
        assert presets[0]["preset"].positive_suffix == "pos"
        assert presets[0]["preset"].negative_prefix == "neg"


# ── Update ───────────────────────────────────────────────────────


class TestUpdate:
    """Tests for update()."""

    def test_update_name(self, mgr):
        created = mgr.create(key="test", name="Old Name")
        updated = mgr.update(created["id"], name="New Name")
        assert updated["name"] == "New Name"
        # Persisted
        fetched = mgr.get(created["id"])
        assert fetched["name"] == "New Name"

    def test_update_suffix_and_prefix(self, mgr):
        created = mgr.create(key="test", name="Test")
        updated = mgr.update(
            created["id"],
            positive_suffix="new pos",
            negative_prefix="new neg",
        )
        assert updated["positive_suffix"] == "new pos"
        assert updated["negative_prefix"] == "new neg"

    def test_update_empty_name_fails(self, mgr):
        from core.prompt_builder import PromptValidationError
        created = mgr.create(key="test", name="Test")
        with pytest.raises(PromptValidationError, match="empty"):
            mgr.update(created["id"], name="")

    def test_update_not_found(self, mgr):
        from core.prompt_builder import PromptValidationError
        with pytest.raises(PromptValidationError, match="not found"):
            mgr.update("PST-9999", name="Ghost")


# ── Delete ───────────────────────────────────────────────────────


class TestDelete:
    """Tests for delete()."""

    def test_delete_existing(self, mgr):
        created = mgr.create(key="test", name="Test")
        assert mgr.delete(created["id"]) is True
        # Should be gone
        from core.prompt_builder import PromptValidationError
        with pytest.raises(PromptValidationError, match="not found"):
            mgr.get(created["id"])

    def test_delete_not_found(self, mgr):
        from core.prompt_builder import PromptValidationError
        with pytest.raises(PromptValidationError, match="not found"):
            mgr.delete("PST-9999")


# ── Import / Export ──────────────────────────────────────────────


class TestImportExport:
    """Tests for import_json() and export_json()."""

    def test_export_empty(self, mgr):
        assert mgr.export_json() == []

    def test_export_returns_records(self, mgr):
        mgr.create(key="a", name="Alpha")
        mgr.create(key="b", name="Beta")
        exported = mgr.export_json()
        assert len(exported) == 2
        names = {r["name"] for r in exported}
        assert names == {"Alpha", "Beta"}
        # Should NOT contain StylePreset objects
        for r in exported:
            assert "preset" not in r

    def test_import_basic(self, mgr):
        data = [
            {"key": "imp1", "name": "Import One", "positive_suffix": "pos1"},
            {"key": "imp2", "name": "Import Two", "negative_prefix": "neg2"},
        ]
        created = mgr.import_json(data)
        assert len(created) == 2
        assert mgr.list_presets()[0]["key"] in ("imp1", "imp2")

    def test_import_skips_duplicates(self, mgr):
        mgr.create(key="existing", name="Existing")
        data = [
            {"key": "existing", "name": "Duplicate"},  # Should be skipped
            {"key": "new_one", "name": "New One"},
        ]
        created = mgr.import_json(data)
        assert len(created) == 1
        assert created[0]["key"] == "new_one"

    def test_import_skips_invalid(self, mgr):
        data = [
            {"key": "", "name": "No Key"},
            {"key": "no_name", "name": ""},
            {"key": "valid", "name": "Valid"},
        ]
        created = mgr.import_json(data)
        assert len(created) == 1

    def test_roundtrip(self, mgr, presets_dir):
        """Export from one manager, import into another."""
        mgr.create(key="round", name="Roundtrip", positive_suffix="test pos")
        exported = mgr.export_json()

        from core.prompt_builder import CustomStylePresetManager
        other_dir = presets_dir.parent / "other_presets"
        other_dir.mkdir()
        mgr2 = CustomStylePresetManager(presets_dir=other_dir)

        created = mgr2.import_json(exported)
        assert len(created) == 1
        assert created[0]["name"] == "Roundtrip"
        assert created[0]["positive_suffix"] == "test pos"


# ── Merge with Builtins ─────────────────────────────────────────


class TestBuiltinMerge:
    """Tests for get_style_preset() and list_style_presets() with custom presets."""

    def test_list_includes_builtins(self, monkeypatch, presets_dir):
        monkeypatch.setattr("config.settings.COMFYUI_PRESETS_DIR", presets_dir)
        from core.prompt_builder import list_style_presets
        presets = list_style_presets()
        names = {p.name for p in presets}
        # Builtins should always be present
        assert "Fantasy Art" in names
        assert "Realistic" in names

    def test_list_includes_custom(self, mgr, monkeypatch, presets_dir):
        monkeypatch.setattr("config.settings.COMFYUI_PRESETS_DIR", presets_dir)
        mgr.create(key="my_custom", name="My Custom Style", positive_suffix="custom pos")
        from core.prompt_builder import list_style_presets
        presets = list_style_presets()
        names = {p.name for p in presets}
        assert "My Custom Style" in names

    def test_get_custom_by_key(self, mgr, monkeypatch, presets_dir):
        monkeypatch.setattr("config.settings.COMFYUI_PRESETS_DIR", presets_dir)
        mgr.create(key="neo_baroque", name="Neo Baroque", positive_suffix="ornate, dramatic")
        from core.prompt_builder import get_style_preset
        preset = get_style_preset("neo_baroque")
        assert preset is not None
        assert preset.name == "Neo Baroque"
        assert preset.positive_suffix == "ornate, dramatic"

    def test_get_custom_by_name(self, mgr, monkeypatch, presets_dir):
        monkeypatch.setattr("config.settings.COMFYUI_PRESETS_DIR", presets_dir)
        mgr.create(key="industrial", name="Industrial", positive_suffix="gritty, metal")
        from core.prompt_builder import get_style_preset
        preset = get_style_preset("Industrial")
        assert preset is not None

    def test_get_builtin_still_works(self, monkeypatch, presets_dir):
        monkeypatch.setattr("config.settings.COMFYUI_PRESETS_DIR", presets_dir)
        from core.prompt_builder import get_style_preset
        preset = get_style_preset("Fantasy Art")
        assert preset is not None
        assert "fantasy" in preset.positive_suffix.lower() or "Fantasy" in preset.name
