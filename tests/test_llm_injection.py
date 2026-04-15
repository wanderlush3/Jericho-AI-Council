"""
Tests for F-053: LLM Injection System

Covers:
- Item llm_injection field persistence (create, update, to_dict, from_dict)
- is_injection_active() logic for permanent vs consumable items + expiry
- Location llm_injection field persistence
- Store llm_injection field persistence
- Backward compatibility (existing data without llm_injection)
"""

from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from config.settings import CONSUMABLE_INJECTION_TTL_HOURS
from core.items import Item, ItemManager, is_injection_active
from core.locations import Location, LocationManager
from core.stores import Store, StoreManager


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def tmp_items(tmp_path: Path):
    d = tmp_path / "items"
    d.mkdir()
    return ItemManager(items_dir=d)


@pytest.fixture()
def tmp_locs(tmp_path: Path):
    d = tmp_path / "locations"
    d.mkdir()
    return LocationManager(locations_dir=d)


@pytest.fixture()
def tmp_stores(tmp_path: Path):
    d = tmp_path / "stores"
    d.mkdir()
    return StoreManager(stores_dir=d)


# ════════════════════════════════════════════════════════════════
# Item LLM Injection
# ════════════════════════════════════════════════════════════════


class TestItemInjection:
    """Item.llm_injection field and is_injection_active() helper."""

    def test_create_with_injection(self, tmp_items: ItemManager):
        item = tmp_items.create(
            "Test Sword", "A glowing blade", author="Council",
            llm_injection="Glows faintly near undead",
        )
        assert item.llm_injection == "Glows faintly near undead"

    def test_create_without_injection(self, tmp_items: ItemManager):
        item = tmp_items.create("Plain Shield", "Basic", author="Council")
        assert item.llm_injection == ""

    def test_update_injection(self, tmp_items: ItemManager):
        item = tmp_items.create("Shield", "Sturdy", author="Council")
        updated = tmp_items.update(item.id, llm_injection="Reflects magic damage")
        assert updated.llm_injection == "Reflects magic damage"

    def test_roundtrip_to_dict_from_dict(self, tmp_items: ItemManager):
        item = tmp_items.create(
            "Ring", "Shiny", author="Council",
            llm_injection="Grants invisibility at night",
        )
        d = item.to_dict()
        assert d["llm_injection"] == "Grants invisibility at night"
        restored = Item.from_dict(d)
        assert restored.llm_injection == "Grants invisibility at night"

    def test_from_dict_missing_injection_defaults_empty(self):
        """Backward compatibility: existing JSON without llm_injection."""
        data = {
            "id": "ITEM-9999",
            "name": "Legacy Sword",
            "description": "Found in old data",
            "author": "Council",
        }
        item = Item.from_dict(data)
        assert item.llm_injection == ""


class TestIsInjectionActive:
    """is_injection_active() helper function logic."""

    def test_empty_injection_always_false(self):
        item = Item.create(
            id="ITEM-0001", name="X", description="Y", author="A",
            tier="permanent",
        )
        assert is_injection_active(item) is False

    def test_permanent_item_always_active(self):
        item = Item.create(
            id="ITEM-0002", name="X", description="Y", author="A",
            tier="permanent",
            llm_injection="Always on",
        )
        assert is_injection_active(item) is True

    def test_degradable_item_always_active(self):
        item = Item.create(
            id="ITEM-0003", name="X", description="Y", author="A",
            tier="degradable",
            llm_injection="Always on",
        )
        assert is_injection_active(item) is True

    def test_consumable_within_ttl_is_active(self):
        """Consumable item updated recently → injection should be active."""
        now = datetime.now(timezone.utc)
        item = Item(
            id="ITEM-0004", name="Potion", description="Y", author="A",
            tier="consumable",
            llm_injection="Heals slowly over time",
            updated_at=now.isoformat(),
        )
        assert is_injection_active(item) is True

    def test_consumable_past_ttl_is_expired(self):
        """Consumable item updated >24h ago → injection should be expired."""
        old = datetime.now(timezone.utc) - timedelta(hours=CONSUMABLE_INJECTION_TTL_HOURS + 1)
        item = Item(
            id="ITEM-0005", name="Old Potion", description="Y", author="A",
            tier="consumable",
            llm_injection="Was once magical",
            updated_at=old.isoformat(),
        )
        assert is_injection_active(item) is False

    def test_consumable_exactly_at_ttl_boundary(self):
        """Consumable item exactly at 24h boundary → should be active (<=)."""
        exactly = datetime.now(timezone.utc) - timedelta(hours=CONSUMABLE_INJECTION_TTL_HOURS)
        item = Item(
            id="ITEM-0006", name="Potion", description="Y", author="A",
            tier="consumable",
            llm_injection="Boundary test",
            updated_at=exactly.isoformat(),
        )
        assert is_injection_active(item) is True

    def test_consumable_no_updated_at(self):
        """Consumable with no updated_at → injection not active."""
        item = Item(
            id="ITEM-0007", name="X", description="Y", author="A",
            tier="consumable",
            llm_injection="Should be inactive",
            updated_at="",
        )
        assert is_injection_active(item) is False

    def test_default_tier_is_permanent(self):
        """Items with no tier set should behave as permanent."""
        item = Item.create(
            id="ITEM-0008", name="X", description="Y", author="A",
            llm_injection="Active",
        )
        # Default tier is "" which is not "consumable", so static
        assert is_injection_active(item) is True


# ════════════════════════════════════════════════════════════════
# Location LLM Injection
# ════════════════════════════════════════════════════════════════


class TestLocationInjection:
    """Location.llm_injection field persistence."""

    def test_create_with_injection(self, tmp_locs: LocationManager):
        loc = tmp_locs.create(
            "Ironhaven", "A fortified port", author="Council",
            llm_injection="City gates sealed due to dragon sighting",
        )
        assert loc.llm_injection == "City gates sealed due to dragon sighting"

    def test_create_without_injection(self, tmp_locs: LocationManager):
        loc = tmp_locs.create("Plain", "Flat", author="Council")
        assert loc.llm_injection == ""

    def test_update_injection(self, tmp_locs: LocationManager):
        loc = tmp_locs.create("Tavern", "Cozy", author="Council")
        updated = tmp_locs.update(loc.id, llm_injection="A mysterious stranger appears")
        assert updated.llm_injection == "A mysterious stranger appears"

    def test_roundtrip(self, tmp_locs: LocationManager):
        loc = tmp_locs.create(
            "Forest", "Dark", author="Council",
            llm_injection="Wolves howl at night",
        )
        d = loc.to_dict()
        assert d["llm_injection"] == "Wolves howl at night"
        restored = Location.from_dict(d)
        assert restored.llm_injection == "Wolves howl at night"

    def test_from_dict_missing_injection(self):
        """Backward compatibility."""
        data = {
            "id": "LOC-9999",
            "name": "Old Place",
            "description": "Existed before F-053",
            "author": "Council",
        }
        loc = Location.from_dict(data)
        assert loc.llm_injection == ""

    def test_update_status_preserves_injection(self, tmp_locs: LocationManager):
        """update_status() must not lose llm_injection."""
        loc = tmp_locs.create(
            "Castle", "Grand", author="Council",
            llm_injection="The drawbridge is raised",
        )
        activated = tmp_locs.update_status(loc.id, "active")
        assert activated.llm_injection == "The drawbridge is raised"
        assert activated.status == "active"

    def test_add_feature_preserves_injection(self, tmp_locs: LocationManager):
        """add_feature() must not lose llm_injection."""
        from core.locations import LocationFeature
        loc = tmp_locs.create(
            "Harbor", "Busy", author="Council",
            llm_injection="Ships arrive daily",
        )
        loc = tmp_locs.update_status(loc.id, "active")
        feat = LocationFeature.create(name="Dock", description="A wooden dock")
        updated = tmp_locs.add_feature(loc.id, feat)
        assert updated.llm_injection == "Ships arrive daily"
        assert len(updated.features) == 1

    def test_remove_feature_preserves_injection(self, tmp_locs: LocationManager):
        """remove_feature() must not lose llm_injection."""
        from core.locations import LocationFeature
        loc = tmp_locs.create(
            "Temple", "Sacred", author="Council",
            llm_injection="Chanting echoes through halls",
        )
        feat = LocationFeature.create(name="Altar", description="Ancient altar")
        loc = tmp_locs.add_feature(loc.id, feat)
        updated = tmp_locs.remove_feature(loc.id, "Altar")
        assert updated.llm_injection == "Chanting echoes through halls"
        assert len(updated.features) == 0


# ════════════════════════════════════════════════════════════════
# Store LLM Injection
# ════════════════════════════════════════════════════════════════


class TestStoreInjection:
    """Store.llm_injection field persistence."""

    def test_create_with_injection(self, tmp_stores: StoreManager):
        store = tmp_stores.create(
            "Smithy", "A forge", author="Council",
            llm_injection="Half-price sale on enchanted weapons",
        )
        assert store.llm_injection == "Half-price sale on enchanted weapons"

    def test_create_without_injection(self, tmp_stores: StoreManager):
        store = tmp_stores.create("Shop", "Basic", author="Council")
        assert store.llm_injection == ""

    def test_update_injection(self, tmp_stores: StoreManager):
        store = tmp_stores.create("Alchemy", "Potions", author="Council")
        updated = tmp_stores.update(store.id, llm_injection="Buy 2 get 1 free today")
        assert updated.llm_injection == "Buy 2 get 1 free today"

    def test_roundtrip(self, tmp_stores: StoreManager):
        store = tmp_stores.create(
            "Enchanter", "Magic", author="Council",
            llm_injection="New enchantments available",
        )
        d = store.to_dict()
        assert d["llm_injection"] == "New enchantments available"
        restored = Store.from_dict(d)
        assert restored.llm_injection == "New enchantments available"

    def test_from_dict_missing_injection(self):
        """Backward compatibility."""
        data = {
            "id": "STORE-9999",
            "name": "Old Shop",
            "description": "Existed before F-053",
            "author": "Council",
        }
        store = Store.from_dict(data)
        assert store.llm_injection == ""

    def test_update_status_preserves_injection(self, tmp_stores: StoreManager):
        """update_status() must not lose llm_injection."""
        store = tmp_stores.create(
            "Tavern", "Drinks", author="Council",
            llm_injection="Happy hour from 6-8pm",
        )
        activated = tmp_stores.update_status(store.id, "active")
        assert activated.llm_injection == "Happy hour from 6-8pm"
        assert activated.status == "active"
