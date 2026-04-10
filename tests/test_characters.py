"""
Jericho — Tests for Character Template System (F-011)

Tests for core/characters.py: Trait, CharacterTemplate, CharacterManager,
lifecycle, trait management, YAML export, versioning, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from core.characters import (
    CharacterError,
    CharacterLifecycleError,
    CharacterManager,
    CharacterNotFoundError,
    CharacterTemplate,
    CharacterValidationError,
    Trait,
)


# ─── Helpers ──────────────────────────────────────────────────


def _make_trait(**overrides) -> Trait:
    """Create a default Trait for testing."""
    defaults = {
        "trait_type": "personality",
        "name": "Curious",
        "description": "Always asking questions",
        "intensity": 0.7,
    }
    defaults.update(overrides)
    return Trait.create(**defaults)


def _make_manager(tmp_path: Path) -> CharacterManager:
    """Create a CharacterManager with a temp directory."""
    return CharacterManager(characters_dir=tmp_path / "characters")


def _create_sample(mgr: CharacterManager, **overrides) -> CharacterTemplate:
    """Create a minimal character via the manager."""
    defaults = {
        "name": "Atlas",
        "description": "An explorer AI",
        "author": "Forge",
        "traits": [_make_trait()],
    }
    defaults.update(overrides)
    return mgr.create(**defaults)


# ═══════════════════════════════════════════════════════════════
# Trait
# ═══════════════════════════════════════════════════════════════


class TestTrait:
    def test_fields(self):
        t = Trait(trait_type="personality", name="Bold", description="Acts with conviction", intensity=0.8)
        assert t.trait_type == "personality"
        assert t.name == "Bold"
        assert t.description == "Acts with conviction"
        assert t.intensity == 0.8

    def test_frozen(self):
        t = _make_trait()
        with pytest.raises(AttributeError):
            t.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        t = _make_trait()
        d = t.to_dict()
        t2 = Trait.from_dict(d)
        assert t == t2

    def test_create_factory(self):
        t = Trait.create("values", "Honesty", "Always truthful", intensity=0.9)
        assert t.trait_type == "values"
        assert t.name == "Honesty"
        assert t.intensity == 0.9

    def test_invalid_intensity_too_high(self):
        with pytest.raises(CharacterValidationError, match="intensity"):
            Trait.create("personality", "Loud", "Very loud", intensity=1.5)

    def test_invalid_intensity_negative(self):
        with pytest.raises(CharacterValidationError, match="intensity"):
            Trait.create("personality", "Quiet", "Very quiet", intensity=-0.1)

    def test_default_intensity(self):
        t = Trait.create("flaws", "Stubborn", "Won't budge")
        assert t.intensity == 0.5


# ═══════════════════════════════════════════════════════════════
# CharacterTemplate
# ═══════════════════════════════════════════════════════════════


class TestCharacterTemplate:
    def test_fields(self):
        t = _make_trait()
        c = CharacterTemplate(
            id="CH-0001",
            name="Atlas",
            description="Explorer",
            author="Forge",
            traits=[t],
        )
        assert c.id == "CH-0001"
        assert c.name == "Atlas"
        assert c.status == "draft"
        assert c.version == 1
        assert len(c.traits) == 1

    def test_frozen(self):
        c = CharacterTemplate(id="CH-0001", name="A", description="D", author="F")
        with pytest.raises(AttributeError):
            c.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        t = _make_trait()
        c = CharacterTemplate.create(
            id="CH-0001",
            name="Atlas",
            description="Explorer",
            author="Forge",
            backstory="Born in the mountains",
            traits=[t],
            system_prompt="You are Atlas.",
            greeting="Hello, traveler!",
            example_messages=["I wonder what's over that hill."],
            tags=["explorer", "curious"],
            metadata={"origin": "design-session-1"},
        )
        d = c.to_dict()
        c2 = CharacterTemplate.from_dict(d)
        assert c == c2

    def test_create_factory(self):
        c = CharacterTemplate.create(
            id="CH-0001",
            name="Atlas",
            description="Explorer",
            author="Forge",
        )
        assert c.status == "draft"
        assert c.version == 1
        assert c.created_at != ""
        assert c.updated_at != ""

    def test_defaults(self):
        c = CharacterTemplate(id="CH-0001", name="A", description="D", author="F")
        assert c.backstory == ""
        assert c.traits == []
        assert c.system_prompt == ""
        assert c.greeting == ""
        assert c.example_messages == []
        assert c.tags == []
        assert c.version == 1
        assert c.metadata == {}

    def test_from_dict_missing_optionals(self):
        data = {"id": "CH-0001", "name": "A", "description": "D", "author": "F"}
        c = CharacterTemplate.from_dict(data)
        assert c.status == "draft"
        assert c.version == 1
        assert c.traits == []

    def test_create_with_metadata(self):
        c = CharacterTemplate.create(
            id="CH-0001",
            name="A",
            description="D",
            author="F",
            metadata={"key": "value"},
        )
        assert c.metadata == {"key": "value"}


# ═══════════════════════════════════════════════════════════════
# CharacterManager Init
# ═══════════════════════════════════════════════════════════════


class TestCharacterManagerInit:
    def test_creates_directory(self, tmp_path):
        mgr = CharacterManager(characters_dir=tmp_path / "new_chars")
        assert mgr.directory.exists()

    def test_existing_directory(self, tmp_path):
        d = tmp_path / "chars"
        d.mkdir()
        mgr = CharacterManager(characters_dir=d)
        assert mgr.directory == d

    def test_repr(self, tmp_path):
        mgr = _make_manager(tmp_path)
        r = repr(mgr)
        assert "CharacterManager" in r
        assert "characters=0" in r


# ═══════════════════════════════════════════════════════════════
# Character Creation
# ═══════════════════════════════════════════════════════════════


class TestCharacterCreation:
    def test_basic(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        assert c.id == "CH-0001"
        assert c.name == "Atlas"
        assert c.status == "draft"

    def test_sequential_ids(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c1 = _create_sample(mgr, name="Alpha")
        c2 = _create_sample(mgr, name="Beta")
        assert c1.id == "CH-0001"
        assert c2.id == "CH-0002"

    def test_persistence(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        loaded = mgr.get(c.id)
        assert loaded.name == c.name
        assert loaded.author == c.author

    def test_with_all_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = mgr.create(
            "Atlas",
            "Explorer",
            author="Forge",
            backstory="Born in the mountains",
            traits=[_make_trait()],
            system_prompt="You are Atlas.",
            greeting="Hello!",
            example_messages=["I wonder..."],
            tags=["explorer"],
            metadata={"origin": "test"},
        )
        assert c.backstory == "Born in the mountains"
        assert c.system_prompt == "You are Atlas."
        assert c.greeting == "Hello!"
        assert c.example_messages == ["I wonder..."]
        assert c.tags == ["explorer"]
        assert c.metadata == {"origin": "test"}

    def test_empty_name_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterValidationError, match="Name"):
            mgr.create("", "Desc", author="Forge", traits=[_make_trait()])

    def test_empty_author_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterValidationError, match="Author"):
            mgr.create("Atlas", "Desc", author="", traits=[_make_trait()])

    def test_no_traits_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterValidationError, match="trait"):
            mgr.create("Atlas", "Desc", author="Forge", traits=[])

    def test_whitespace_stripping(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = mgr.create("  Atlas  ", "  Explorer  ", author="  Forge  ", traits=[_make_trait()])
        assert c.name == "Atlas"
        assert c.description == "Explorer"
        assert c.author == "Forge"


# ═══════════════════════════════════════════════════════════════
# Character Retrieval
# ═══════════════════════════════════════════════════════════════


class TestCharacterRetrieval:
    def test_get_by_id(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        loaded = mgr.get(c.id)
        assert loaded.id == c.id

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterNotFoundError, match="CH-9999"):
            mgr.get("CH-9999")

    def test_list_all(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        chars = mgr.list_characters()
        assert len(chars) == 2

    def test_filter_by_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c1 = _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        mgr.update_status(c1.id, "active")
        drafts = mgr.list_characters(status="draft")
        assert len(drafts) == 1
        assert drafts[0].name == "Beta"

    def test_filter_by_author(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", author="Forge")
        _create_sample(mgr, name="Beta", author="Spark")
        forge_chars = mgr.list_characters(author="forge")  # case-insensitive
        assert len(forge_chars) == 1
        assert forge_chars[0].name == "Alpha"

    def test_filter_by_tag(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", tags=["explorer", "brave"])
        _create_sample(mgr, name="Beta", tags=["scholar"])
        explorers = mgr.list_characters(tag="explorer")
        assert len(explorers) == 1
        assert explorers[0].name == "Alpha"

    def test_combined_filters(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", author="Forge", tags=["explorer"])
        _create_sample(mgr, name="Beta", author="Forge", tags=["scholar"])
        _create_sample(mgr, name="Gamma", author="Spark", tags=["explorer"])
        results = mgr.list_characters(author="forge", tag="explorer")
        assert len(results) == 1
        assert results[0].name == "Alpha"

    def test_empty_list(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.list_characters() == []


# ═══════════════════════════════════════════════════════════════
# Status Lifecycle
# ═══════════════════════════════════════════════════════════════


class TestStatusLifecycle:
    def test_draft_to_active(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        updated = mgr.update_status(c.id, "active")
        assert updated.status == "active"

    def test_active_to_archived(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        updated = mgr.update_status(c.id, "archived")
        assert updated.status == "archived"

    def test_active_to_superseded(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        updated = mgr.update_status(c.id, "superseded")
        assert updated.status == "superseded"

    def test_skip_phase_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        with pytest.raises(CharacterLifecycleError):
            mgr.update_status(c.id, "archived")  # draft → archived not allowed

    def test_archived_to_active(self, tmp_path):
        """archived → active is allowed (bidirectional)."""
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        mgr.update_status(c.id, "archived")
        reactivated = mgr.update_status(c.id, "active")
        assert reactivated.status == "active"

    def test_archived_to_draft(self, tmp_path):
        """archived → draft is allowed."""
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        mgr.update_status(c.id, "archived")
        reverted = mgr.update_status(c.id, "draft")
        assert reverted.status == "draft"

    def test_superseded_terminal(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        mgr.update_status(c.id, "superseded")
        with pytest.raises(CharacterLifecycleError):
            mgr.update_status(c.id, "active")

    def test_unknown_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        with pytest.raises(CharacterValidationError, match="Unknown status"):
            mgr.update_status(c.id, "imaginary")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterNotFoundError):
            mgr.update_status("CH-9999", "active")


# ═══════════════════════════════════════════════════════════════
# Trait Management
# ═══════════════════════════════════════════════════════════════


class TestTraitManagement:
    def test_add_trait(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        new_trait = Trait.create("values", "Honesty", "Always truthful", intensity=0.9)
        updated = mgr.add_trait(c.id, new_trait)
        assert len(updated.traits) == 2

    def test_duplicate_name_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)  # has trait "Curious"
        dup_trait = Trait.create("flaws", "curious", "Same name different case")
        with pytest.raises(CharacterValidationError, match="already exists"):
            mgr.add_trait(c.id, dup_trait)

    def test_remove_trait(self, tmp_path):
        mgr = _make_manager(tmp_path)
        t1 = _make_trait(name="Curious")
        t2 = _make_trait(name="Bold", trait_type="values")
        c = mgr.create("Atlas", "Explorer", author="Forge", traits=[t1, t2])
        updated = mgr.remove_trait(c.id, "Curious")
        assert len(updated.traits) == 1
        assert updated.traits[0].name == "Bold"

    def test_remove_nonexistent_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        with pytest.raises(CharacterValidationError, match="not found"):
            mgr.remove_trait(c.id, "Nonexistent")

    def test_remove_last_trait_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)  # has exactly one trait
        with pytest.raises(CharacterValidationError, match="last trait"):
            mgr.remove_trait(c.id, "Curious")

    def test_add_trait_persists(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        new_trait = Trait.create("flaws", "Impatient", "Hates waiting")
        mgr.add_trait(c.id, new_trait)
        reloaded = mgr.get(c.id)
        assert len(reloaded.traits) == 2

    def test_remove_trait_case_insensitive(self, tmp_path):
        mgr = _make_manager(tmp_path)
        t1 = _make_trait(name="Curious")
        t2 = _make_trait(name="Bold", trait_type="values")
        c = mgr.create("Atlas", "Explorer", author="Forge", traits=[t1, t2])
        updated = mgr.remove_trait(c.id, "  CURIOUS  ")
        assert len(updated.traits) == 1


# ═══════════════════════════════════════════════════════════════
# Character Update
# ═══════════════════════════════════════════════════════════════


class TestCharacterUpdate:
    def test_update_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        updated = mgr.update(c.id, name="Atlas v2")
        assert updated.name == "Atlas v2"

    def test_update_description(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        updated = mgr.update(c.id, description="A seasoned explorer")
        assert updated.description == "A seasoned explorer"

    def test_update_backstory(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        updated = mgr.update(c.id, backstory="Born in the mountains")
        assert updated.backstory == "Born in the mountains"

    def test_immutable_field_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        with pytest.raises(CharacterValidationError, match="immutable"):
            mgr.update(c.id, id="CH-9999")

    def test_author_immutable(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        with pytest.raises(CharacterValidationError, match="immutable"):
            mgr.update(c.id, author="Spark")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterNotFoundError):
            mgr.update("CH-9999", name="Ghost")

    def test_multiple_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        updated = mgr.update(c.id, name="New Name", description="New Desc", tags=["new-tag"])
        assert updated.name == "New Name"
        assert updated.description == "New Desc"
        assert updated.tags == ["new-tag"]

    def test_bumps_updated_at(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        updated = mgr.update(c.id, name="Changed")
        assert updated.updated_at >= c.updated_at


# ═══════════════════════════════════════════════════════════════
# Export YAML
# ═══════════════════════════════════════════════════════════════


class TestExportYaml:
    def test_basic_export(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        yaml_str = mgr.export_yaml(c.id)
        data = yaml.safe_load(yaml_str)
        assert data["name"] == "Atlas"
        assert data["id"] == c.id

    def test_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = mgr.create(
            "Atlas",
            "Explorer",
            author="Forge",
            backstory="Born in the mountains",
            traits=[_make_trait()],
            system_prompt="You are Atlas.",
            greeting="Hello!",
            tags=["explorer"],
        )
        yaml_str = mgr.export_yaml(c.id)
        data = yaml.safe_load(yaml_str)
        assert data["name"] == "Atlas"
        assert data["backstory"] == "Born in the mountains"
        assert data["system_prompt"] == "You are Atlas."
        assert data["greeting"] == "Hello!"
        assert data["tags"] == ["explorer"]

    def test_includes_traits(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        yaml_str = mgr.export_yaml(c.id)
        data = yaml.safe_load(yaml_str)
        assert "traits" in data
        assert data["traits"][0]["name"] == "Curious"

    def test_to_custom_path(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        out = tmp_path / "exported" / "atlas.yaml"
        yaml_str = mgr.export_yaml(c.id, output_path=out)
        assert out.exists()
        assert yaml.safe_load(out.read_text(encoding="utf-8"))["name"] == "Atlas"
        assert yaml_str == out.read_text(encoding="utf-8")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterNotFoundError):
            mgr.export_yaml("CH-9999")

    def test_omits_empty_optional_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)  # no backstory, greeting, etc.
        yaml_str = mgr.export_yaml(c.id)
        data = yaml.safe_load(yaml_str)
        assert "backstory" not in data
        assert "greeting" not in data
        assert "example_messages" not in data


# ═══════════════════════════════════════════════════════════════
# Versioning
# ═══════════════════════════════════════════════════════════════


class TestVersioning:
    def test_create_version(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        new = mgr.create_version(c.id)
        assert new.version == 2
        assert new.status == "draft"

    def test_supersedes_original(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        mgr.create_version(c.id)
        original = mgr.get(c.id)
        assert original.status == "superseded"

    def test_links_via_metadata(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        mgr.update_status(c.id, "active")
        new = mgr.create_version(c.id)
        assert new.metadata["previous_version"] == c.id

    def test_copies_all_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = mgr.create(
            "Atlas",
            "Explorer",
            author="Forge",
            backstory="Mountains",
            traits=[_make_trait()],
            system_prompt="You are Atlas.",
            greeting="Hi!",
            example_messages=["I wonder..."],
            tags=["explorer"],
        )
        mgr.update_status(c.id, "active")
        new = mgr.create_version(c.id)
        assert new.name == c.name
        assert new.backstory == c.backstory
        assert new.system_prompt == c.system_prompt
        assert new.greeting == c.greeting
        assert new.tags == c.tags

    def test_not_active_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = _create_sample(mgr)
        with pytest.raises(CharacterLifecycleError):
            mgr.create_version(c.id)  # draft, not active

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(CharacterNotFoundError):
            mgr.create_version("CH-9999")


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_unicode(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = mgr.create(
            "Ätlàs 日本語",
            "描述 — description with émojis 🎭",
            author="Fõrge",
            traits=[Trait.create("personality", "créatif", "描述")],
        )
        loaded = mgr.get(c.id)
        assert loaded.name == "Ätlàs 日本語"

    def test_long_backstory(self, tmp_path):
        mgr = _make_manager(tmp_path)
        long_text = "A" * 100_000
        c = mgr.create(
            "Atlas",
            "Explorer",
            author="Forge",
            backstory=long_text,
            traits=[_make_trait()],
        )
        loaded = mgr.get(c.id)
        assert len(loaded.backstory) == 100_000

    def test_many_traits(self, tmp_path):
        mgr = _make_manager(tmp_path)
        traits = [Trait.create("personality", f"Trait-{i}", f"Desc-{i}") for i in range(50)]
        c = mgr.create("Atlas", "Explorer", author="Forge", traits=traits)
        loaded = mgr.get(c.id)
        assert len(loaded.traits) == 50

    def test_corrupt_json_skipped(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr)
        # Write a corrupt file
        corrupt = mgr.directory / "CH-0099.json"
        corrupt.write_text("{bad json", encoding="utf-8")
        chars = mgr.list_characters()
        assert len(chars) == 1  # corrupt file skipped

    def test_persistence_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        c = mgr.create(
            "Atlas",
            "Explorer",
            author="Forge",
            backstory="Mountains",
            traits=[_make_trait()],
            system_prompt="You are Atlas.",
            greeting="Hello!",
            example_messages=["I wonder..."],
            tags=["explorer", "curious"],
            metadata={"origin": "test"},
        )
        mgr.update_status(c.id, "active")
        mgr.add_trait(c.id, Trait.create("flaws", "Stubborn", "Won't budge"))

        # Reload from a fresh manager
        mgr2 = CharacterManager(characters_dir=mgr.directory)
        loaded = mgr2.get(c.id)
        assert loaded.name == "Atlas"
        assert loaded.status == "active"
        assert len(loaded.traits) == 2
        assert loaded.backstory == "Mountains"
        assert loaded.tags == ["explorer", "curious"]


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(CharacterNotFoundError, CharacterError)
        assert issubclass(CharacterValidationError, CharacterError)
        assert issubclass(CharacterLifecycleError, CharacterError)
        assert issubclass(CharacterError, Exception)

    def test_not_found_fields(self):
        e = CharacterNotFoundError("CH-0001")
        assert e.character_id == "CH-0001"
        assert "CH-0001" in str(e)

    def test_validation_fields(self):
        e = CharacterValidationError(["err1", "err2"])
        assert e.errors == ["err1", "err2"]
        assert "err1" in str(e)

    def test_lifecycle_fields(self):
        e = CharacterLifecycleError("CH-0001", "draft", "archived")
        assert e.character_id == "CH-0001"
        assert e.current_status == "draft"
        assert e.requested_status == "archived"
