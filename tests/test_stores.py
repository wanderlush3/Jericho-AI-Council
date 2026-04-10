"""
Jericho — Tests for World Stores System

Tests for core/stores.py: StoreItem, Store, StoreManager,
lifecycle, inventory management, purchases, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core.stores import (
    Store,
    StoreError,
    StoreItem,
    StoreLifecycleError,
    StoreManager,
    StoreNotFoundError,
    StorePurchaseError,
    StoreValidationError,
)


# ─── Helpers ──────────────────────────────────────────────────


def _make_store_item(**overrides) -> StoreItem:
    """Create a default StoreItem for testing."""
    defaults = {
        "item_id": "ITEM-0001",
        "price_gold": 10,
        "price_silver": 0,
        "price_bronze": 0,
        "quantity": -1,
    }
    defaults.update(overrides)
    return StoreItem.create(**defaults)


def _make_manager(tmp_path: Path) -> StoreManager:
    """Create a StoreManager with a temp directory."""
    return StoreManager(stores_dir=tmp_path / "stores")


def _create_sample(mgr: StoreManager, **overrides) -> Store:
    """Create a minimal store via the manager."""
    defaults: dict[str, Any] = {
        "name": "Ironhaven Smithy",
        "description": "A master forge run by the finest artisans",
        "author": "Council",
        "store_type": "blacksmith",
    }
    defaults.update(overrides)
    name = defaults.pop("name")
    desc = defaults.pop("description")
    return mgr.create(name, desc, **defaults)


# ═══════════════════════════════════════════════════════════════
# StoreItem
# ═══════════════════════════════════════════════════════════════


class TestStoreItem:
    def test_fields(self):
        si = StoreItem(item_id="ITEM-0001", price_gold=5)
        assert si.item_id == "ITEM-0001"
        assert si.price_gold == 5
        assert si.price_silver == 0
        assert si.price_bronze == 0
        assert si.quantity == -1

    def test_frozen(self):
        si = _make_store_item()
        with pytest.raises(AttributeError):
            si.item_id = "ITEM-9999"  # type: ignore[misc]

    def test_roundtrip(self):
        si = _make_store_item()
        d = si.to_dict()
        si2 = StoreItem.from_dict(d)
        assert si == si2

    def test_create_factory(self):
        si = StoreItem.create("ITEM-0001", price_gold=10, quantity=5)
        assert si.item_id == "ITEM-0001"
        assert si.price_gold == 10
        assert si.quantity == 5
        assert si.added_at != ""

    def test_empty_item_id_rejected(self):
        with pytest.raises(StoreValidationError, match="Item ID"):
            StoreItem.create("", price_gold=10)

    def test_zero_price_rejected(self):
        with pytest.raises(StoreValidationError, match="price tier"):
            StoreItem.create("ITEM-0001")

    def test_negative_price_rejected(self):
        with pytest.raises(StoreValidationError, match="negative"):
            StoreItem.create("ITEM-0001", price_gold=-1)

    def test_negative_silver_rejected(self):
        with pytest.raises(StoreValidationError, match="negative"):
            StoreItem.create("ITEM-0001", price_silver=-5)

    def test_negative_bronze_rejected(self):
        with pytest.raises(StoreValidationError, match="negative"):
            StoreItem.create("ITEM-0001", price_bronze=-1)

    def test_invalid_quantity_rejected(self):
        with pytest.raises(StoreValidationError, match="Quantity"):
            StoreItem.create("ITEM-0001", price_gold=10, quantity=-2)

    def test_all_three_prices(self):
        si = StoreItem.create(
            "ITEM-0001", price_gold=1, price_silver=2, price_bronze=3,
        )
        assert si.price_gold == 1
        assert si.price_silver == 2
        assert si.price_bronze == 3

    def test_unlimited_quantity(self):
        si = StoreItem.create("ITEM-0001", price_gold=1, quantity=-1)
        assert si.quantity == -1

    def test_zero_quantity(self):
        si = StoreItem.create("ITEM-0001", price_gold=1, quantity=0)
        assert si.quantity == 0

    def test_from_dict_missing_optionals(self):
        data = {"item_id": "ITEM-0001"}
        si = StoreItem.from_dict(data)
        assert si.price_gold == 0
        assert si.quantity == -1


# ═══════════════════════════════════════════════════════════════
# Store
# ═══════════════════════════════════════════════════════════════


class TestStore:
    def test_fields(self):
        store = Store(
            id="STORE-0001", name="Smithy", description="A forge",
            author="Council",
        )
        assert store.id == "STORE-0001"
        assert store.name == "Smithy"
        assert store.status == "draft"
        assert store.store_type == "general"
        assert store.inventory == []
        assert store.version == 1

    def test_frozen(self):
        store = Store(id="STORE-0001", name="A", description="D", author="C")
        with pytest.raises(AttributeError):
            store.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        si = _make_store_item()
        store = Store.create(
            id="STORE-0001", name="Smithy", description="A forge",
            author="Council", store_type="blacksmith",
            lore="Ancient forge", inventory=[si],
            tags=["weapons"], metadata={"key": "val"},
        )
        d = store.to_dict()
        store2 = Store.from_dict(d)
        assert store == store2

    def test_create_factory(self):
        store = Store.create(
            id="STORE-0001", name="Smithy",
            description="A forge", author="Council",
        )
        assert store.status == "draft"
        assert store.version == 1
        assert store.created_at != ""
        assert store.updated_at != ""

    def test_defaults(self):
        store = Store(id="STORE-0001", name="A", description="D", author="C")
        assert store.lore == ""
        assert store.inventory == []
        assert store.tags == []
        assert store.location_id == ""
        assert store.owner == ""
        assert store.metadata == {}

    def test_from_dict_missing_optionals(self):
        data = {"id": "STORE-0001", "name": "A", "description": "D", "author": "C"}
        store = Store.from_dict(data)
        assert store.status == "draft"
        assert store.store_type == "general"
        assert store.inventory == []


# ═══════════════════════════════════════════════════════════════
# StoreManager Init
# ═══════════════════════════════════════════════════════════════


class TestStoreManagerInit:
    def test_creates_directory(self, tmp_path):
        mgr = StoreManager(stores_dir=tmp_path / "new_stores")
        assert mgr.directory.exists()

    def test_existing_directory(self, tmp_path):
        d = tmp_path / "stores"
        d.mkdir()
        mgr = StoreManager(stores_dir=d)
        assert mgr.directory == d

    def test_repr(self, tmp_path):
        mgr = _make_manager(tmp_path)
        r = repr(mgr)
        assert "StoreManager" in r
        assert "stores=0" in r


# ═══════════════════════════════════════════════════════════════
# Store Creation
# ═══════════════════════════════════════════════════════════════


class TestStoreCreation:
    def test_basic(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        assert store.id == "STORE-0001"
        assert store.name == "Ironhaven Smithy"
        assert store.status == "draft"
        assert store.store_type == "blacksmith"

    def test_sequential_ids(self, tmp_path):
        mgr = _make_manager(tmp_path)
        s1 = _create_sample(mgr, name="Alpha")
        s2 = _create_sample(mgr, name="Beta")
        assert s1.id == "STORE-0001"
        assert s2.id == "STORE-0002"

    def test_persistence(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        loaded = mgr.get(store.id)
        assert loaded.name == store.name
        assert loaded.author == store.author

    def test_with_all_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = mgr.create(
            "Smithy", "A forge",
            author="Council", store_type="blacksmith",
            location_id="LOC-0001", owner="Sage",
            tags=["weapons"], lore="Ancient forge",
            metadata={"origin": "test"},
        )
        assert store.store_type == "blacksmith"
        assert store.location_id == "LOC-0001"
        assert store.owner == "Sage"
        assert store.tags == ["weapons"]
        assert store.lore == "Ancient forge"

    def test_empty_name_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(StoreValidationError, match="Name"):
            mgr.create("", "Desc", author="Council")

    def test_empty_description_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(StoreValidationError, match="Description"):
            mgr.create("Smithy", "", author="Council")

    def test_empty_author_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(StoreValidationError, match="Author"):
            mgr.create("Smithy", "Desc", author="")

    def test_invalid_store_type_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(StoreValidationError, match="Invalid store type"):
            mgr.create("Smithy", "Desc", author="Council", store_type="imaginary")

    def test_whitespace_stripping(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = mgr.create("  Smithy  ", "  A forge  ", author="  Council  ")
        assert store.name == "Smithy"
        assert store.description == "A forge"
        assert store.author == "Council"

    def test_all_store_types(self, tmp_path):
        for st in ("general", "blacksmith", "alchemist", "enchanter", "tavern", "custom"):
            mgr = StoreManager(stores_dir=tmp_path / st)
            store = mgr.create("Test", "Desc", author="Council", store_type=st)
            assert store.store_type == st


# ═══════════════════════════════════════════════════════════════
# Store Retrieval
# ═══════════════════════════════════════════════════════════════


class TestStoreRetrieval:
    def test_get_by_id(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        loaded = mgr.get(store.id)
        assert loaded.id == store.id

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(StoreNotFoundError, match="STORE-9999"):
            mgr.get("STORE-9999")

    def test_list_all(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        stores = mgr.list_stores()
        assert len(stores) == 2

    def test_filter_by_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        s1 = _create_sample(mgr, name="Alpha")
        _create_sample(mgr, name="Beta")
        mgr.update_status(s1.id, "active")
        drafts = mgr.list_stores(status="draft")
        assert len(drafts) == 1
        assert drafts[0].name == "Beta"

    def test_filter_by_author(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", author="Council")
        _create_sample(mgr, name="Beta", author="Sage")
        result = mgr.list_stores(author="council")  # case-insensitive
        assert len(result) == 1
        assert result[0].name == "Alpha"

    def test_filter_by_tag(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", tags=["weapons"])
        _create_sample(mgr, name="Beta", tags=["potions"])
        result = mgr.list_stores(tag="weapons")
        assert len(result) == 1

    def test_filter_by_store_type(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr, name="Alpha", store_type="blacksmith")
        _create_sample(mgr, name="Beta", store_type="alchemist")
        result = mgr.list_stores(store_type="blacksmith")
        assert len(result) == 1
        assert result[0].name == "Alpha"

    def test_empty_list(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.list_stores() == []


# ═══════════════════════════════════════════════════════════════
# Status Lifecycle
# ═══════════════════════════════════════════════════════════════


class TestStatusLifecycle:
    def test_draft_to_active(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update_status(store.id, "active")
        assert updated.status == "active"

    def test_active_to_archived(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        mgr.update_status(store.id, "active")
        updated = mgr.update_status(store.id, "archived")
        assert updated.status == "archived"

    def test_skip_phase_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreLifecycleError):
            mgr.update_status(store.id, "archived")  # draft → archived

    def test_archived_terminal(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        mgr.update_status(store.id, "active")
        mgr.update_status(store.id, "archived")
        with pytest.raises(StoreLifecycleError):
            mgr.update_status(store.id, "active")

    def test_unknown_status(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreValidationError, match="Unknown status"):
            mgr.update_status(store.id, "imaginary")

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(StoreNotFoundError):
            mgr.update_status("STORE-9999", "active")

    def test_status_update_bumps_updated_at(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update_status(store.id, "active")
        assert updated.updated_at >= store.updated_at


# ═══════════════════════════════════════════════════════════════
# Inventory Management
# ═══════════════════════════════════════════════════════════════


class TestInventoryManagement:
    def test_add_item(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        si = _make_store_item()
        updated = mgr.add_inventory_item(store.id, si)
        assert len(updated.inventory) == 1
        assert updated.inventory[0].item_id == "ITEM-0001"

    def test_duplicate_item_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        si = _make_store_item()
        mgr.add_inventory_item(store.id, si)
        with pytest.raises(StoreValidationError, match="already in"):
            mgr.add_inventory_item(store.id, si)

    def test_remove_item(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        si1 = _make_store_item(item_id="ITEM-0001")
        si2 = _make_store_item(item_id="ITEM-0002")
        mgr.add_inventory_item(store.id, si1)
        mgr.add_inventory_item(store.id, si2)
        updated = mgr.remove_inventory_item(store.id, "ITEM-0001")
        assert len(updated.inventory) == 1
        assert updated.inventory[0].item_id == "ITEM-0002"

    def test_remove_nonexistent_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreValidationError, match="not found"):
            mgr.remove_inventory_item(store.id, "ITEM-9999")

    def test_update_price(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        si = _make_store_item()
        mgr.add_inventory_item(store.id, si)
        updated = mgr.update_inventory_item(
            store.id, "ITEM-0001", price_gold=50,
        )
        inv = updated.inventory[0]
        assert inv.price_gold == 50

    def test_update_quantity(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        si = _make_store_item(quantity=10)
        mgr.add_inventory_item(store.id, si)
        updated = mgr.update_inventory_item(
            store.id, "ITEM-0001", quantity=5,
        )
        assert updated.inventory[0].quantity == 5

    def test_update_nonexistent_raises(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreValidationError, match="not found"):
            mgr.update_inventory_item(store.id, "ITEM-9999", price_gold=1)

    def test_multiple_items(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        for i in range(10):
            si = _make_store_item(item_id=f"ITEM-{i:04d}")
            store = mgr.add_inventory_item(store.id, si)
        assert len(store.inventory) == 10

    def test_add_persists(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        si = _make_store_item()
        mgr.add_inventory_item(store.id, si)
        reloaded = mgr.get(store.id)
        assert len(reloaded.inventory) == 1


# ═══════════════════════════════════════════════════════════════
# Purchase
# ═══════════════════════════════════════════════════════════════


class _FakeAccount:
    """Minimal treasury account for purchase tests."""
    def __init__(self, account_id, gold=200, silver=0, bronze=0):
        self.account_id = account_id
        self.account_type = "user"
        self.owner_name = "Test"
        self.balance = type("Bal", (), {
            "gold": gold, "silver": silver, "bronze": bronze,
        })()
        self.created_at = ""
        self.updated_at = ""
        self.metadata = {}

    def to_dict(self):
        return {
            "account_id": self.account_id,
            "account_type": self.account_type,
            "owner_name": self.owner_name,
            "balance": {
                "gold": self.balance.gold,
                "silver": self.balance.silver,
                "bronze": self.balance.bronze,
            },
        }


class _FakeTreasury:
    """Minimal treasury mock for purchase tests."""
    def __init__(self, accounts=None, fail_transfer=False):
        self._accounts = {a.account_id: a for a in (accounts or [])}
        self._fail_transfer = fail_transfer

    def get(self, account_id):
        if account_id in self._accounts:
            return self._accounts[account_id]
        raise Exception(f"Account '{account_id}' not found")

    def transfer(self, from_id, to_id, gold=0, silver=0, bronze=0):
        if self._fail_transfer:
            raise Exception("Insufficient funds")
        from_acct = self.get(from_id)
        to_acct = self.get(to_id)
        return from_acct, to_acct


class TestStorePurchase:
    def _setup_store(self, tmp_path, quantity=-1, owner="Sage"):
        """Create an active store with one inventory item."""
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr, owner=owner)
        si = _make_store_item(quantity=quantity)
        mgr.add_inventory_item(store.id, si)
        mgr.update_status(store.id, "active")
        return mgr, store.id

    def test_successful_purchase(self, tmp_path):
        mgr, sid = self._setup_store(tmp_path)
        buyer = _FakeAccount("ACCT-user-human", gold=200)
        seller = _FakeAccount("ACCT-cm-sage", gold=100)
        treasury = _FakeTreasury(accounts=[buyer, seller])
        result = mgr.purchase(sid, "ITEM-0001", "ACCT-user-human", treasury)
        assert "store" in result
        assert "buyer_account" in result
        assert result["item"]["item_id"] == "ITEM-0001"

    def test_quantity_decrements(self, tmp_path):
        mgr, sid = self._setup_store(tmp_path, quantity=3)
        buyer = _FakeAccount("ACCT-user-human")
        seller = _FakeAccount("ACCT-cm-sage")
        treasury = _FakeTreasury(accounts=[buyer, seller])
        mgr.purchase(sid, "ITEM-0001", "ACCT-user-human", treasury)
        store = mgr.get(sid)
        assert store.inventory[0].quantity == 2

    def test_unlimited_stock_no_decrement(self, tmp_path):
        mgr, sid = self._setup_store(tmp_path, quantity=-1)
        buyer = _FakeAccount("ACCT-user-human")
        seller = _FakeAccount("ACCT-cm-sage")
        treasury = _FakeTreasury(accounts=[buyer, seller])
        mgr.purchase(sid, "ITEM-0001", "ACCT-user-human", treasury)
        store = mgr.get(sid)
        assert store.inventory[0].quantity == -1

    def test_out_of_stock(self, tmp_path):
        mgr, sid = self._setup_store(tmp_path, quantity=0)
        buyer = _FakeAccount("ACCT-user-human")
        seller = _FakeAccount("ACCT-cm-sage")
        treasury = _FakeTreasury(accounts=[buyer, seller])
        with pytest.raises(StorePurchaseError, match="out of stock"):
            mgr.purchase(sid, "ITEM-0001", "ACCT-user-human", treasury)

    def test_inactive_store(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        si = _make_store_item()
        mgr.add_inventory_item(store.id, si)
        # Store is still in draft status
        treasury = _FakeTreasury()
        with pytest.raises(StorePurchaseError, match="not active"):
            mgr.purchase(store.id, "ITEM-0001", "ACCT-user", treasury)

    def test_item_not_in_inventory(self, tmp_path):
        mgr, sid = self._setup_store(tmp_path)
        buyer = _FakeAccount("ACCT-user-human")
        seller = _FakeAccount("ACCT-cm-sage")
        treasury = _FakeTreasury(accounts=[buyer, seller])
        with pytest.raises(StorePurchaseError, match="not available"):
            mgr.purchase(sid, "ITEM-9999", "ACCT-user-human", treasury)

    def test_insufficient_funds(self, tmp_path):
        mgr, sid = self._setup_store(tmp_path)
        buyer = _FakeAccount("ACCT-user-human", gold=0)
        seller = _FakeAccount("ACCT-cm-sage")
        treasury = _FakeTreasury(
            accounts=[buyer, seller], fail_transfer=True,
        )
        with pytest.raises(StorePurchaseError, match="Payment failed"):
            mgr.purchase(sid, "ITEM-0001", "ACCT-user-human", treasury)

    def test_store_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        treasury = _FakeTreasury()
        with pytest.raises(StoreNotFoundError):
            mgr.purchase("STORE-9999", "ITEM-0001", "ACCT-user", treasury)


# ═══════════════════════════════════════════════════════════════
# Store Update
# ═══════════════════════════════════════════════════════════════


class TestStoreUpdate:
    def test_update_name(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update(store.id, name="New Smithy")
        assert updated.name == "New Smithy"

    def test_update_description(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update(store.id, description="A better forge")
        assert updated.description == "A better forge"

    def test_update_lore(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update(store.id, lore="Ancient texts speak of this place")
        assert updated.lore == "Ancient texts speak of this place"

    def test_update_store_type(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update(store.id, store_type="alchemist")
        assert updated.store_type == "alchemist"

    def test_invalid_store_type_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreValidationError, match="Invalid store type"):
            mgr.update(store.id, store_type="imaginary")

    def test_update_owner(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update(store.id, owner="Araushnee")
        assert updated.owner == "Araushnee"

    def test_immutable_field_rejected(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreValidationError, match="immutable"):
            mgr.update(store.id, id="STORE-9999")

    def test_author_immutable(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreValidationError, match="immutable"):
            mgr.update(store.id, author="Sage")

    def test_inventory_immutable(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        with pytest.raises(StoreValidationError, match="immutable"):
            mgr.update(store.id, inventory=[])

    def test_not_found(self, tmp_path):
        mgr = _make_manager(tmp_path)
        with pytest.raises(StoreNotFoundError):
            mgr.update("STORE-9999", name="Ghost")

    def test_multiple_fields(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update(
            store.id, name="New", description="New Desc",
            tags=["new-tag"],
        )
        assert updated.name == "New"
        assert updated.description == "New Desc"
        assert updated.tags == ["new-tag"]

    def test_bumps_updated_at(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        updated = mgr.update(store.id, name="Changed")
        assert updated.updated_at >= store.updated_at


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_unicode(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = mgr.create(
            "Bäckerei 日本",
            "描述 — bakery with émojis 🍞",
            author="Fõrge",
        )
        loaded = mgr.get(store.id)
        assert loaded.name == "Bäckerei 日本"

    def test_long_lore(self, tmp_path):
        mgr = _make_manager(tmp_path)
        long_text = "A" * 100_000
        store = mgr.create("Smithy", "Forge", author="Council", lore=long_text)
        loaded = mgr.get(store.id)
        assert len(loaded.lore) == 100_000

    def test_corrupt_json_skipped(self, tmp_path):
        mgr = _make_manager(tmp_path)
        _create_sample(mgr)
        corrupt = mgr.directory / "STORE-0099.json"
        corrupt.write_text("{bad json", encoding="utf-8")
        stores = mgr.list_stores()
        assert len(stores) == 1

    def test_persistence_roundtrip(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = mgr.create(
            "Smithy", "A forge",
            author="Council", store_type="blacksmith",
            lore="Ancient forge", tags=["weapons"],
            metadata={"origin": "test"},
        )
        si = _make_store_item(item_id="ITEM-0001")
        mgr.add_inventory_item(store.id, si)
        mgr.update_status(store.id, "active")

        # Reload from fresh manager
        mgr2 = StoreManager(stores_dir=mgr.directory)
        loaded = mgr2.get(store.id)
        assert loaded.name == "Smithy"
        assert loaded.status == "active"
        assert loaded.store_type == "blacksmith"
        assert len(loaded.inventory) == 1
        assert loaded.inventory[0].price_gold == 10

    def test_large_inventory(self, tmp_path):
        mgr = _make_manager(tmp_path)
        store = _create_sample(mgr)
        for i in range(100):
            si = _make_store_item(item_id=f"ITEM-{i:04d}")
            store = mgr.add_inventory_item(store.id, si)
        assert len(store.inventory) == 100


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(StoreNotFoundError, StoreError)
        assert issubclass(StoreValidationError, StoreError)
        assert issubclass(StoreLifecycleError, StoreError)
        assert issubclass(StorePurchaseError, StoreError)
        assert issubclass(StoreError, Exception)

    def test_not_found_fields(self):
        e = StoreNotFoundError("STORE-0001")
        assert e.store_id == "STORE-0001"
        assert "STORE-0001" in str(e)

    def test_validation_fields(self):
        e = StoreValidationError(["err1", "err2"])
        assert e.errors == ["err1", "err2"]
        assert "err1" in str(e)

    def test_validation_string(self):
        e = StoreValidationError("single error")
        assert e.errors == ["single error"]

    def test_lifecycle_fields(self):
        e = StoreLifecycleError("STORE-0001", "draft", "archived")
        assert e.store_id == "STORE-0001"
        assert e.current_status == "draft"
        assert e.requested_status == "archived"

    def test_purchase_error(self):
        e = StorePurchaseError("Out of stock")
        assert "Out of stock" in str(e)
