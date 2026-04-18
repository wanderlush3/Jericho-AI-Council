"""
Jericho — Tests for Item System

Tests for core/items.py: ItemProperty, Item, ItemManager,
lifecycle, property management, updates, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.items import (
    Item,
    ItemError,
    ItemLifecycleError,
    ItemManager,
    ItemNotFoundError,
    ItemProperty,
    ItemValidationError,
    OWNER_TYPES,
    validate_owned_by,
)


# ─── Helpers ──────────────────────────────────────────────────


def _make_property(**overrides) -> ItemProperty:
    """Create a default ItemProperty for testing."""
    defaults = {
        "name": "Fire Enchantment",
        "description": "Imbues the item with fire damage",
        "property_type": "magical",
    }
    defaults.update(overrides)
    return ItemProperty.create(**defaults)


def _make_manager(tmp_path: Path) -> ItemManager:
    """Create an ItemManager with a temp directory."""
    return ItemManager(items_dir=tmp_path / "items")


def _create_sample(mgr: ItemManager, **overrides) -> Item:
    """Create a minimal item via the manager."""
    defaults = {
        "name": "Starfall Blade",
        "description": "A legendary sword forged from a fallen star",
        "author": "Council",
        "tier": "permanent",
    }
    defaults.update(overrides)
    name = defaults.pop("name")
    desc = defaults.pop("description")
    return mgr.create(name, desc, **defaults)


# ═══════════════════════════════════════════════════════════════
# ItemProperty
# ═══════════════════════════════════════════════════════════════


class TestItemProperty:
    def test_fields(self):
        p = ItemProperty(name="Shield", description="Blocks attacks", property_type="equipment")
        assert p.name == "Shield"
        assert p.description == "Blocks attacks"
        assert p.property_type == "equipment"

    def test_frozen(self):
        p = _make_property()
        with pytest.raises(AttributeError):
            p.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        p = _make_property()
        d = p.to_dict()
        p2 = ItemProperty.from_dict(d)
        assert p == p2

    def test_create_factory(self):
        p = ItemProperty.create("Health Potion", "Restores health", "consumable")
        assert p.name == "Health Potion"
        assert p.property_type == "consumable"

    def test_invalid_property_type(self):
        with pytest.raises(ItemValidationError, match="Property type"):
            ItemProperty.create("X", "Y", property_type="imaginary")

    def test_default_property_type(self):
        p = ItemProperty(name="X", description="Y")
        assert p.property_type == "custom"

    def test_all_valid_types(self):
        for pt in ("magical", "physical", "consumable", "equipment", "material", "custom"):
            p = ItemProperty.create("Test", "Desc", property_type=pt)
            assert p.property_type == pt


# ═══════════════════════════════════════════════════════════════
# Item
# ═══════════════════════════════════════════════════════════════


class TestItem:
    def test_fields(self):
        p = _make_property()
        item = Item(
            id="ITEM-0001",
            name="Starfall Blade",
            description="A legendary sword",
            author="Council",
            properties=[p],
        )
        assert item.id == "ITEM-0001"
        assert item.name == "Starfall Blade"
        assert item.status == "draft"
        assert item.version == 1
        assert len(item.properties) == 1

    def test_frozen(self):
        item = Item(id="ITEM-0001", name="A", description="D", author="C")
        with pytest.raises(AttributeError):
            item.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        p = _make_property()
        item = Item.create(
            id="ITEM-0001",
            name="Starfall Blade",
            description="A legendary sword",
            author="Council",
            lore="Forged in the heart of a dying star",
            properties=[p],
            tags=["weapon", "legendary"],
            rarity="legendary",
            metadata={"origin": "session-1"},
        )
        d = item.to_dict()
        item2 = Item.from_dict(d)
        assert item == item2

    def test_create_factory(self):
        item = Item.create(
            id="ITEM-0001",
            name="Starfall Blade",
            description="A legendary sword",
            author="Council",
        )
        assert item.status == "draft"
        assert item.version == 1
        assert item.created_at != ""
        assert item.updated_at != ""

    def test_defaults(self):
        item = Item(id="ITEM-0001", name="A", description="D", author="C")
        assert item.lore == ""
        assert item.properties == []
        assert item.tags == []
        assert item.rarity == ""
        assert item.owned_by == []
        assert item.version == 1
        assert item.metadata == {}

    def test_from_dict_missing_optionals(self):
        data = {"id": "ITEM-0001", "name": "A", "description": "D", "author": "C"}
        item = Item.from_dict(data)
        assert item.status == "draft"
        assert item.version == 1
        assert item.properties == []

    def test_create_with_metadata(self):
        item = Item.create(
            id="ITEM-0001",
            name="A",
            description="D",
            author="C",
            metadata={"key": "value"},
        )
        assert item.metadata == {"key": "value"}


# ═══════════════════════════════════════════════════════════════
# ItemManager Init
# ═══════════════════════════════════════════════════════════════


class TestItemManagerInit:
    def test_creates_directory(self, tmp_path):
        mgr = ItemManager(items_dir=tmp_path / "new_items")
        assert mgr.directory.exists()

    def test_existing_directory(self, tmp_path):
        d = tmp_path / "items"
        d.mkdir()
        mgr = ItemManager(items_dir=d)
        assert mgr.directory == d

    def test_repr(self, tmp_path):
        mgr = _make_manager(tmp_path)
        r = repr(mgr)
        assert "ItemManager" in r
        assert "items=0" in r


# ═══════════════════════════════════════════════════════════════
# Item Creation
# ═══════════════════════════════════════════════════════════════


class TestItemCreation:
    def test_basic(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        assert item.id == "ITEM-0001"
        assert item.name == "Starfall Blade"
        assert item.status == "draft"

    def test_sequential_ids(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item1 = _create_sample(mgr, name="Alpha")
        item2 = _create_sample(mgr, name="Beta")
        assert item1.id == "ITEM-0001"
        assert item2.id == "ITEM-0002"

    def test_persistence(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        loaded = mgr.get(item.id)
        assert loaded.name == item.name
        assert loaded.author == item.author

    def test_with_all_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        prop = _make_property()
        item = mgr.create(
            "Starfall Blade",
            "A legendary sword",
            author="Council",
            lore="Forged in a dying star",
            properties=[prop],
            tags=["weapon", "legendary"],
            rarity="legendary",
            metadata={"origin": "test"},
        )
        assert item.lore == "Forged in a dying star"
        assert len(item.properties) == 1
        assert item.tags == ["weapon", "legendary"]
        assert item.rarity == "legendary"
        assert item.metadata == {"origin": "test"}

    def test_empty_name_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemValidationError, match="Name"):
            mgr.create("", "Desc", author="Council")

    def test_empty_description_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemValidationError, match="Description"):
            mgr.create("Starfall Blade", "", author="Council")

    def test_empty_author_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemValidationError, match="Author"):
            mgr.create("Starfall Blade", "Desc", author="")

    def test_whitespace_stripping(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create("  Starfall Blade  ", "  A sword  ", author="  Council  ")
        assert item.name == "Starfall Blade"
        assert item.description == "A sword"
        assert item.author == "Council"


# ═══════════════════════════════════════════════════════════════
# Item Retrieval
# ═══════════════════════════════════════════════════════════════


class TestItemRetrieval:
    def test_get_by_id(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        loaded = mgr.get(item.id)
        assert loaded.id == item.id

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemNotFoundError, match="ITEM-9999"):
            mgr.get("ITEM-9999")

    def test_list_all(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        items = mgr.list_items()
        assert len(items) == 2

    def test_filter_by_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item1 = _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        mgr.update_status(item1.id, "active")
        drafts = mgr.list_items(status="draft")
        assert len(drafts) == 1
        assert drafts[0].name == "Beta"

    def test_filter_by_author(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", author="Council")
        _create_sample(mgr, name="Beta", author="Sage")
        council_items = mgr.list_items(author="council")  # case-insensitive
        assert len(council_items) == 1
        assert council_items[0].name == "Alpha"

    def test_filter_by_tag(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", tags=["weapon", "legendary"])
        _create_sample(mgr, name="Beta", tags=["armor"])
        weapons = mgr.list_items(tag="weapon")
        assert len(weapons) == 1
        assert weapons[0].name == "Alpha"

    def test_combined_filters(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", author="Council", tags=["weapon"])
        _create_sample(mgr, name="Beta", author="Council", tags=["armor"])
        _create_sample(mgr, name="Gamma", author="Sage", tags=["weapon"])
        results = mgr.list_items(author="council", tag="weapon")
        assert len(results) == 1
        assert results[0].name == "Alpha"

    def test_empty_list(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.list_items() == []


# ═══════════════════════════════════════════════════════════════
# Status Lifecycle
# ═══════════════════════════════════════════════════════════════


class TestStatusLifecycle:
    def test_draft_to_active(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update_status(item.id, "active")
        assert updated.status == "active"

    def test_active_to_archived(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        mgr.update_status(item.id, "active")
        updated = mgr.update_status(item.id, "archived")
        assert updated.status == "archived"

    def test_skip_phase_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        with pytest.raises(ItemLifecycleError):
            mgr.update_status(item.id, "archived")  # draft → archived not allowed

    def test_archived_terminal(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        mgr.update_status(item.id, "active")
        mgr.update_status(item.id, "archived")
        with pytest.raises(ItemLifecycleError):
            mgr.update_status(item.id, "active")

    def test_unknown_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        with pytest.raises(ItemValidationError, match="Unknown status"):
            mgr.update_status(item.id, "imaginary")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemNotFoundError):
            mgr.update_status("ITEM-9999", "active")

    def test_status_update_bumps_updated_at(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update_status(item.id, "active")
        assert updated.updated_at >= item.updated_at


# ═══════════════════════════════════════════════════════════════
# Property Management
# ═══════════════════════════════════════════════════════════════


class TestPropertyManagement:
    def test_add_property(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        prop = _make_property()
        updated = mgr.add_property(item.id, prop)
        assert len(updated.properties) == 1

    def test_duplicate_property_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr, properties=[_make_property()])
        dup = _make_property(name="fire enchantment")  # case-insensitive
        with pytest.raises(ItemValidationError, match="already exists"):
            mgr.add_property(item.id, dup)

    def test_remove_property(self, tmp_path):
        mgr = _make_manager(tmp_path)
        p1 = _make_property(name="Fire")
        p2 = _make_property(name="Ice")
        item = _create_sample(mgr, properties=[p1, p2])
        updated = mgr.remove_property(item.id, "Fire")
        assert len(updated.properties) == 1
        assert updated.properties[0].name == "Ice"

    def test_remove_nonexistent_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        with pytest.raises(ItemValidationError, match="not found"):
            mgr.remove_property(item.id, "Nonexistent")

    def test_add_property_persists(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        prop = _make_property()
        mgr.add_property(item.id, prop)
        reloaded = mgr.get(item.id)
        assert len(reloaded.properties) == 1

    def test_remove_property_case_insensitive(self, tmp_path):
        mgr = _make_manager(tmp_path)
        p1 = _make_property(name="Fire")
        p2 = _make_property(name="Ice")
        item = _create_sample(mgr, properties=[p1, p2])
        updated = mgr.remove_property(item.id, "  FIRE  ")
        assert len(updated.properties) == 1

    def test_multiple_properties(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        for i in range(10):
            prop = ItemProperty.create(f"Property-{i}", f"Desc-{i}", "magical")
            item = mgr.add_property(item.id, prop)
        assert len(item.properties) == 10


# ═══════════════════════════════════════════════════════════════
# Item Update
# ═══════════════════════════════════════════════════════════════


class TestItemUpdate:
    def test_update_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update(item.id, name="Starfall Blade v2")
        assert updated.name == "Starfall Blade v2"

    def test_update_description(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update(item.id, description="An even more legendary sword")
        assert updated.description == "An even more legendary sword"

    def test_update_lore(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update(item.id, lore="Crafted by ancient smiths")
        assert updated.lore == "Crafted by ancient smiths"

    def test_immutable_field_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        with pytest.raises(ItemValidationError, match="immutable"):
            mgr.update(item.id, id="ITEM-9999")

    def test_author_immutable(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        with pytest.raises(ItemValidationError, match="immutable"):
            mgr.update(item.id, author="Sage")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemNotFoundError):
            mgr.update("ITEM-9999", name="Ghost")

    def test_multiple_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update(
            item.id, name="New Name", description="New Desc", tags=["new-tag"],
        )
        assert updated.name == "New Name"
        assert updated.description == "New Desc"
        assert updated.tags == ["new-tag"]

    def test_bumps_updated_at(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update(item.id, name="Changed")
        assert updated.updated_at >= item.updated_at

    def test_update_rarity(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        updated = mgr.update(item.id, rarity="legendary")
        assert updated.rarity == "legendary"

    def test_update_owned_by(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        assert item.owned_by == []
        updated = mgr.update(item.id, owned_by=[
            {"name": "Araushnee", "type": "character"},
        ])
        assert len(updated.owned_by) == 1
        assert updated.owned_by[0]["name"] == "Araushnee"
        assert updated.owned_by[0]["type"] == "character"
        # Persist through reload
        reloaded = mgr.get(item.id)
        assert len(reloaded.owned_by) == 1
        assert reloaded.owned_by[0]["name"] == "Araushnee"

    def test_owned_by_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Whip", "A coiled leather whip",
            author="Council",
            owned_by=[{"name": "Araushnee", "type": "character"}],
        )
        loaded = mgr.get(item.id)
        d = loaded.to_dict()
        assert d["owned_by"] == [{"name": "Araushnee", "type": "character"}]
        restored = Item.from_dict(d)
        assert restored.owned_by == [{"name": "Araushnee", "type": "character"}]


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_unicode(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Ätlántis 日本刀",
            "描述 — description with émojis ⚔️",
            author="Fõrge",
        )
        loaded = mgr.get(item.id)
        assert loaded.name == "Ätlántis 日本刀"

    def test_long_lore(self, tmp_path):
        mgr = _make_manager(tmp_path)
        long_text = "A" * 100_000
        item = mgr.create("Blade", "Sword", author="Council", lore=long_text)
        loaded = mgr.get(item.id)
        assert len(loaded.lore) == 100_000

    def test_many_properties(self, tmp_path):
        mgr = _make_manager(tmp_path)
        properties = [ItemProperty.create(f"P-{i}", f"D-{i}", "magical") for i in range(50)]
        item = mgr.create("Blade", "Sword", author="Council", properties=properties)
        loaded = mgr.get(item.id)
        assert len(loaded.properties) == 50

    def test_corrupt_json_skipped(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr)
        # Write a corrupt file
        corrupt = mgr.directory / "ITEM-0099.json"
        corrupt.write_text("{bad json", encoding="utf-8")
        items = mgr.list_items()
        assert len(items) == 1  # corrupt file skipped

    def test_persistence_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        prop = _make_property()
        item = mgr.create(
            "Starfall Blade",
            "A legendary sword",
            author="Council",
            lore="Forged in a dying star",
            properties=[prop],
            tags=["weapon", "legendary"],
            rarity="legendary",
            tier="permanent",
            metadata={"origin": "test"},
        )
        mgr.update_status(item.id, "active")
        mgr.add_property(item.id, ItemProperty.create("Ice Shard", "Freezes on impact", "magical"))

        # Reload from a fresh manager
        mgr2 = ItemManager(items_dir=mgr.directory)
        loaded = mgr2.get(item.id)
        assert loaded.name == "Starfall Blade"
        assert loaded.status == "active"
        assert loaded.tier == "permanent"
        assert len(loaded.properties) == 2
        assert loaded.lore == "Forged in a dying star"
        assert loaded.tags == ["weapon", "legendary"]


# ═══════════════════════════════════════════════════════════════
# Item Tiers
# ═══════════════════════════════════════════════════════════════


class TestItemTier:
    def test_tier_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Potion", "A healing elixir",
            author="Council", tier="consumable",
        )
        d = item.to_dict()
        assert d["tier"] == "consumable"
        restored = Item.from_dict(d)
        assert restored.tier == "consumable"

    def test_tier_in_create(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Shield", "A sturdy shield",
            author="Council", tier="permanent",
        )
        assert item.tier == "permanent"

    def test_activation_blocked_without_tier(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Blade", "Desc", author="Council", tier="",
        )
        with pytest.raises(ItemValidationError, match="tier must be set"):
            mgr.update_status(item.id, "active")

    def test_activation_allowed_with_tier(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Blade", "Desc", author="Council", tier="degradable",
        )
        updated = mgr.update_status(item.id, "active")
        assert updated.status == "active"

    def test_invalid_tier_rejected_on_create(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemValidationError, match="Invalid tier"):
            mgr.create("Blade", "Desc", author="Council", tier="mythical")

    def test_invalid_tier_rejected_on_update(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        with pytest.raises(ItemValidationError, match="Invalid tier"):
            mgr.update(item.id, tier="mythical")

    def test_tier_update(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Blade", "Desc", author="Council", tier="permanent",
        )
        updated = mgr.update(item.id, tier="consumable")
        assert updated.tier == "consumable"

    def test_all_valid_tiers(self, tmp_path):
        for tier in ("permanent", "consumable", "degradable"):
            mgr = _make_manager(tmp_path / tier)
            item = mgr.create(
                "Test", "Desc", author="Council", tier=tier,
            )
            assert item.tier == tier

    def test_default_tier_is_empty(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = mgr.create("Blade", "Desc", author="Council")
        assert item.tier == ""


# ═══════════════════════════════════════════════════════════════
# Owned By
# ═══════════════════════════════════════════════════════════════


class TestOwnedBy:
    def test_multiple_owners(self, tmp_path):
        mgr = _make_manager(tmp_path)
        owners = [
            {"name": "King Oberon", "type": "council_member"},
            {"name": "Araushnee", "type": "character"},
            {"name": "Player One", "type": "user"},
        ]
        item = mgr.create("Crown", "Royal crown", author="Council", owned_by=owners)
        assert len(item.owned_by) == 3
        loaded = mgr.get(item.id)
        assert len(loaded.owned_by) == 3
        assert loaded.owned_by[0]["name"] == "King Oberon"
        assert loaded.owned_by[1]["type"] == "character"
        assert loaded.owned_by[2]["type"] == "user"

    def test_validation_invalid_type(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemValidationError, match="invalid"):
            mgr.create("Crown", "Royal crown", author="Council", owned_by=[
                {"name": "Bob", "type": "monster"},
            ])

    def test_validation_empty_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemValidationError, match="name must not be empty"):
            mgr.create("Crown", "Royal crown", author="Council", owned_by=[
                {"name": "", "type": "user"},
            ])

    def test_duplicate_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemValidationError, match="Duplicate"):
            mgr.create("Crown", "Royal crown", author="Council", owned_by=[
                {"name": "Bob", "type": "user"},
                {"name": "bob", "type": "user"},  # case-insensitive duplicate
            ])

    def test_backward_compat_legacy_owner(self, tmp_path):
        """Legacy items with 'owner' string should auto-migrate to owned_by."""
        import json
        mgr = _make_manager(tmp_path)
        # Simulate a legacy item JSON with 'owner' string
        legacy_data = {
            "id": "ITEM-0001",
            "name": "Whip",
            "description": "A whip",
            "author": "Council",
            "owner": "Araushnee",
        }
        item = Item.from_dict(legacy_data)
        assert item.owned_by == [{"name": "Araushnee", "type": "user"}]

    def test_backward_compat_no_owner(self):
        """Legacy items without any owner field get empty owned_by."""
        data = {"id": "ITEM-0001", "name": "A", "description": "D", "author": "C"}
        item = Item.from_dict(data)
        assert item.owned_by == []

    def test_update_validation_invalid_type(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = _create_sample(mgr)
        with pytest.raises(ItemValidationError, match="invalid"):
            mgr.update(item.id, owned_by=[
                {"name": "Bob", "type": "alien"},
            ])

    def test_update_clear_owners(self, tmp_path):
        """Setting owned_by to empty list clears all owners."""
        mgr = _make_manager(tmp_path)
        item = mgr.create(
            "Crown", "Royal crown", author="Council",
            owned_by=[{"name": "Bob", "type": "user"}],
        )
        assert len(item.owned_by) == 1
        updated = mgr.update(item.id, owned_by=[])
        assert updated.owned_by == []

    def test_validate_owned_by_function(self):
        """Test the public validate_owned_by helper directly."""
        # Valid entries
        assert validate_owned_by([
            {"name": "A", "type": "user"},
            {"name": "B", "type": "character"},
        ]) == []

        # Non-list
        errors = validate_owned_by("bad")
        assert len(errors) == 1
        assert "must be a list" in errors[0]

        # Non-dict entry
        errors = validate_owned_by(["bad"])
        assert len(errors) == 1
        assert "must be a dict" in errors[0]

    def test_owner_types_constant(self):
        assert "user" in OWNER_TYPES
        assert "character" in OWNER_TYPES
        assert "council_member" in OWNER_TYPES


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(ItemNotFoundError, ItemError)
        assert issubclass(ItemValidationError, ItemError)
        assert issubclass(ItemLifecycleError, ItemError)
        assert issubclass(ItemError, Exception)

    def test_not_found_fields(self):
        e = ItemNotFoundError("ITEM-0001")
        assert e.item_id == "ITEM-0001"
        assert "ITEM-0001" in str(e)

    def test_validation_fields(self):
        e = ItemValidationError(["err1", "err2"])
        assert e.errors == ["err1", "err2"]
        assert "err1" in str(e)

    def test_lifecycle_fields(self):
        e = ItemLifecycleError("ITEM-0001", "draft", "archived")
        assert e.item_id == "ITEM-0001"
        assert e.current_status == "draft"
        assert e.requested_status == "archived"


# ═══════════════════════════════════════════════════════════════
# Gift Giving (F-068)
# ═══════════════════════════════════════════════════════════════


class TestGiftGiving:
    """Tests for ItemManager.gift_item() — F-068."""

    def _make_active_item(self, mgr, *, owners=None, name="Crown"):
        """Create an active item with owners."""
        if owners is None:
            owners = [{"name": "Alice", "type": "user"}]
        item = mgr.create(
            name, "A royal crown", author="Council",
            tier="permanent", owned_by=owners,
        )
        return mgr.update_status(item.id, "active")

    def test_basic_gift(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        gift = mgr.gift_item(
            item.id,
            from_owner={"name": "Alice", "type": "user"},
            to_owner={"name": "Bob", "type": "character"},
        )
        assert gift.item_id == item.id
        assert gift.item_name == "Crown"
        assert gift.from_owner["name"] == "Alice"
        assert gift.to_owner["name"] == "Bob"
        assert gift.timestamp != ""

    def test_ownership_transferred(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        mgr.gift_item(
            item.id,
            from_owner={"name": "Alice", "type": "user"},
            to_owner={"name": "Bob", "type": "character"},
        )
        reloaded = mgr.get(item.id)
        names = [o["name"] for o in reloaded.owned_by]
        assert "Alice" not in names
        assert "Bob" in names

    def test_from_owner_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        with pytest.raises(ItemValidationError, match="not a current owner"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "Nonexistent", "type": "user"},
                to_owner={"name": "Bob", "type": "character"},
            )

    def test_to_owner_already_owns(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr, owners=[
            {"name": "Alice", "type": "user"},
            {"name": "Bob", "type": "character"},
        ])

        with pytest.raises(ItemValidationError, match="already owns"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "Alice", "type": "user"},
                to_owner={"name": "Bob", "type": "character"},
            )

    def test_self_gift_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        with pytest.raises(ItemValidationError, match="same owner"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "Alice", "type": "user"},
                to_owner={"name": "Alice", "type": "user"},
            )

    def test_case_insensitive_self_gift(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        with pytest.raises(ItemValidationError, match="same owner"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "ALICE", "type": "user"},
                to_owner={"name": "alice", "type": "user"},
            )

    def test_inactive_item_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        # Create but don't activate
        item = mgr.create(
            "Crown", "Royal crown", author="Council",
            tier="permanent", owned_by=[{"name": "Alice", "type": "user"}],
        )
        with pytest.raises(ItemValidationError, match="must be active"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "Alice", "type": "user"},
                to_owner={"name": "Bob", "type": "character"},
            )

    def test_archived_item_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)
        mgr.update_status(item.id, "archived")

        with pytest.raises(ItemValidationError, match="must be active"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "Alice", "type": "user"},
                to_owner={"name": "Bob", "type": "character"},
            )

    def test_invalid_to_owner_type(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        with pytest.raises(ItemValidationError, match="invalid"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "Alice", "type": "user"},
                to_owner={"name": "Bob", "type": "monster"},
            )

    def test_empty_to_owner_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        with pytest.raises(ItemValidationError, match="name must not be empty"):
            mgr.gift_item(
                item.id,
                from_owner={"name": "Alice", "type": "user"},
                to_owner={"name": "", "type": "user"},
            )

    def test_gift_record_serialization(self, tmp_path):
        from core.items import GiftRecord
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        gift = mgr.gift_item(
            item.id,
            from_owner={"name": "Alice", "type": "user"},
            to_owner={"name": "Bob", "type": "character"},
            message="A token of appreciation",
        )
        d = gift.to_dict()
        assert d["item_id"] == item.id
        assert d["item_name"] == "Crown"
        assert d["from_owner"]["name"] == "Alice"
        assert d["to_owner"]["name"] == "Bob"
        assert d["message"] == "A token of appreciation"
        assert d["timestamp"] != ""

    def test_gift_with_custom_message(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        gift = mgr.gift_item(
            item.id,
            from_owner={"name": "Alice", "type": "user"},
            to_owner={"name": "Bob", "type": "character"},
            message="For your bravery!",
        )
        assert gift.message == "For your bravery!"

    def test_sequential_gifts(self, tmp_path):
        """Gift item from A→B, then B→C."""
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr)

        # A→B
        mgr.gift_item(
            item.id,
            from_owner={"name": "Alice", "type": "user"},
            to_owner={"name": "Bob", "type": "character"},
        )
        reloaded = mgr.get(item.id)
        assert [o["name"] for o in reloaded.owned_by] == ["Bob"]

        # B→C
        mgr.gift_item(
            item.id,
            from_owner={"name": "Bob", "type": "character"},
            to_owner={"name": "Carol", "type": "council_member"},
        )
        reloaded = mgr.get(item.id)
        assert [o["name"] for o in reloaded.owned_by] == ["Carol"]

    def test_gift_preserves_other_owners(self, tmp_path):
        mgr = _make_manager(tmp_path)
        item = self._make_active_item(mgr, owners=[
            {"name": "Alice", "type": "user"},
            {"name": "Dave", "type": "council_member"},
        ])

        mgr.gift_item(
            item.id,
            from_owner={"name": "Alice", "type": "user"},
            to_owner={"name": "Bob", "type": "character"},
        )
        reloaded = mgr.get(item.id)
        names = sorted(o["name"] for o in reloaded.owned_by)
        assert "Alice" not in names
        assert "Bob" in names
        assert "Dave" in names

    def test_item_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(ItemNotFoundError):
            mgr.gift_item(
                "ITEM-9999",
                from_owner={"name": "Alice", "type": "user"},
                to_owner={"name": "Bob", "type": "character"},
            )
