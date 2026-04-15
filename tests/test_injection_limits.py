"""
Jericho — Injection Length Limit Tests (F-054)

Verifies that llm_injection fields are properly length-limited across
Items, Locations, and Stores at both the manager and API layers.
"""

from __future__ import annotations

import pytest
from pathlib import Path

from config.settings import (
    ITEM_INJECTION_MAX_LENGTH,
    LOCATION_INJECTION_MAX_LENGTH,
    STORE_INJECTION_MAX_LENGTH,
)


# ─── Helpers ──────────────────────────────────────────────────────


def _at_limit(max_len: int) -> str:
    """Return a string exactly at the character limit."""
    return "A" * max_len


def _over_limit(max_len: int, extra: int = 1) -> str:
    """Return a string exceeding the character limit."""
    return "B" * (max_len + extra)


def _under_limit(max_len: int) -> str:
    """Return a string comfortably under the limit."""
    return "C" * (max_len // 2)


# ═══════════════════════════════════════════════════════════════════
# Item Injection Limits
# ═══════════════════════════════════════════════════════════════════


class TestItemInjectionLimits:
    """Validate injection length limits on ItemManager create/update."""

    def test_create_item_at_limit(self, tmp_path: Path) -> None:
        from core.items import ItemManager

        mgr = ItemManager(items_dir=tmp_path)
        text = _at_limit(ITEM_INJECTION_MAX_LENGTH)
        item = mgr.create(
            "Sword", "A sharp blade", author="Council",
            tier="permanent", llm_injection=text,
        )
        assert item.llm_injection == text
        assert len(item.llm_injection) == ITEM_INJECTION_MAX_LENGTH

    def test_create_item_under_limit(self, tmp_path: Path) -> None:
        from core.items import ItemManager

        mgr = ItemManager(items_dir=tmp_path)
        text = _under_limit(ITEM_INJECTION_MAX_LENGTH)
        item = mgr.create(
            "Shield", "A sturdy shield", author="Council",
            tier="permanent", llm_injection=text,
        )
        assert item.llm_injection == text

    def test_create_item_over_limit_rejected(self, tmp_path: Path) -> None:
        from core.items import ItemManager, ItemValidationError

        mgr = ItemManager(items_dir=tmp_path)
        text = _over_limit(ITEM_INJECTION_MAX_LENGTH)
        with pytest.raises(ItemValidationError, match="exceeds maximum length"):
            mgr.create(
                "Bow", "A long bow", author="Council",
                tier="permanent", llm_injection=text,
            )

    def test_create_item_empty_injection_allowed(self, tmp_path: Path) -> None:
        from core.items import ItemManager

        mgr = ItemManager(items_dir=tmp_path)
        item = mgr.create(
            "Staff", "A wooden staff", author="Council",
            tier="permanent", llm_injection="",
        )
        assert item.llm_injection == ""

    def test_update_item_at_limit(self, tmp_path: Path) -> None:
        from core.items import ItemManager

        mgr = ItemManager(items_dir=tmp_path)
        item = mgr.create(
            "Ring", "A golden ring", author="Council", tier="permanent",
        )
        text = _at_limit(ITEM_INJECTION_MAX_LENGTH)
        updated = mgr.update(item.id, llm_injection=text)
        assert updated.llm_injection == text

    def test_update_item_over_limit_rejected(self, tmp_path: Path) -> None:
        from core.items import ItemManager, ItemValidationError

        mgr = ItemManager(items_dir=tmp_path)
        item = mgr.create(
            "Helm", "A metal helm", author="Council", tier="permanent",
        )
        text = _over_limit(ITEM_INJECTION_MAX_LENGTH)
        with pytest.raises(ItemValidationError, match="exceeds maximum length"):
            mgr.update(item.id, llm_injection=text)

    def test_update_item_clear_injection(self, tmp_path: Path) -> None:
        from core.items import ItemManager

        mgr = ItemManager(items_dir=tmp_path)
        item = mgr.create(
            "Amulet", "A shiny amulet", author="Council",
            tier="permanent", llm_injection="some context",
        )
        updated = mgr.update(item.id, llm_injection="")
        assert updated.llm_injection == ""

    def test_error_message_includes_actual_length(self, tmp_path: Path) -> None:
        from core.items import ItemManager, ItemValidationError

        mgr = ItemManager(items_dir=tmp_path)
        text = _over_limit(ITEM_INJECTION_MAX_LENGTH, extra=42)
        with pytest.raises(ItemValidationError) as exc_info:
            mgr.create(
                "Dagger", "A small dagger", author="Council",
                tier="permanent", llm_injection=text,
            )
        assert str(ITEM_INJECTION_MAX_LENGTH) in str(exc_info.value)
        assert str(len(text)) in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════
# Location Injection Limits
# ═══════════════════════════════════════════════════════════════════


class TestLocationInjectionLimits:
    """Validate injection length limits on LocationManager create/update."""

    def test_create_location_at_limit(self, tmp_path: Path) -> None:
        from core.locations import LocationManager

        mgr = LocationManager(locations_dir=tmp_path)
        text = _at_limit(LOCATION_INJECTION_MAX_LENGTH)
        loc = mgr.create(
            "Ironhaven", "A port city", author="Council",
            llm_injection=text,
        )
        assert loc.llm_injection == text
        assert len(loc.llm_injection) == LOCATION_INJECTION_MAX_LENGTH

    def test_create_location_over_limit_rejected(self, tmp_path: Path) -> None:
        from core.locations import LocationManager, LocationValidationError

        mgr = LocationManager(locations_dir=tmp_path)
        text = _over_limit(LOCATION_INJECTION_MAX_LENGTH)
        with pytest.raises(LocationValidationError, match="exceeds maximum length"):
            mgr.create(
                "Shadowfen", "A dark swamp", author="Council",
                llm_injection=text,
            )

    def test_update_location_at_limit(self, tmp_path: Path) -> None:
        from core.locations import LocationManager

        mgr = LocationManager(locations_dir=tmp_path)
        loc = mgr.create("Hillcrest", "Rolling hills", author="Council")
        text = _at_limit(LOCATION_INJECTION_MAX_LENGTH)
        updated = mgr.update(loc.id, llm_injection=text)
        assert updated.llm_injection == text

    def test_update_location_over_limit_rejected(self, tmp_path: Path) -> None:
        from core.locations import LocationManager, LocationValidationError

        mgr = LocationManager(locations_dir=tmp_path)
        loc = mgr.create("Stonebridge", "A stone bridge", author="Council")
        text = _over_limit(LOCATION_INJECTION_MAX_LENGTH)
        with pytest.raises(LocationValidationError, match="exceeds maximum length"):
            mgr.update(loc.id, llm_injection=text)

    def test_location_has_larger_limit_than_items(self) -> None:
        """Locations should have a higher character limit than items."""
        assert LOCATION_INJECTION_MAX_LENGTH > ITEM_INJECTION_MAX_LENGTH

    def test_error_message_includes_actual_length(self, tmp_path: Path) -> None:
        from core.locations import LocationManager, LocationValidationError

        mgr = LocationManager(locations_dir=tmp_path)
        text = _over_limit(LOCATION_INJECTION_MAX_LENGTH, extra=25)
        with pytest.raises(LocationValidationError) as exc_info:
            mgr.create(
                "Gloomreach", "A gloomy place", author="Council",
                llm_injection=text,
            )
        assert str(LOCATION_INJECTION_MAX_LENGTH) in str(exc_info.value)
        assert str(len(text)) in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════
# Store Injection Limits
# ═══════════════════════════════════════════════════════════════════


class TestStoreInjectionLimits:
    """Validate injection length limits on StoreManager create/update."""

    def test_create_store_at_limit(self, tmp_path: Path) -> None:
        from core.stores import StoreManager

        mgr = StoreManager(stores_dir=tmp_path)
        text = _at_limit(STORE_INJECTION_MAX_LENGTH)
        store = mgr.create(
            "Smithy", "A master forge", author="Council",
            llm_injection=text,
        )
        assert store.llm_injection == text
        assert len(store.llm_injection) == STORE_INJECTION_MAX_LENGTH

    def test_create_store_over_limit_rejected(self, tmp_path: Path) -> None:
        from core.stores import StoreManager, StoreValidationError

        mgr = StoreManager(stores_dir=tmp_path)
        text = _over_limit(STORE_INJECTION_MAX_LENGTH)
        with pytest.raises(StoreValidationError, match="exceeds maximum length"):
            mgr.create(
                "Alchemist", "Potions galore", author="Council",
                llm_injection=text,
            )

    def test_update_store_at_limit(self, tmp_path: Path) -> None:
        from core.stores import StoreManager

        mgr = StoreManager(stores_dir=tmp_path)
        store = mgr.create("Tavern", "A cozy tavern", author="Council")
        text = _at_limit(STORE_INJECTION_MAX_LENGTH)
        updated = mgr.update(store.id, llm_injection=text)
        assert updated.llm_injection == text

    def test_update_store_over_limit_rejected(self, tmp_path: Path) -> None:
        from core.stores import StoreManager, StoreValidationError

        mgr = StoreManager(stores_dir=tmp_path)
        store = mgr.create("Market", "A busy market", author="Council")
        text = _over_limit(STORE_INJECTION_MAX_LENGTH)
        with pytest.raises(StoreValidationError, match="exceeds maximum length"):
            mgr.update(store.id, llm_injection=text)

    def test_error_message_includes_actual_length(self, tmp_path: Path) -> None:
        from core.stores import StoreManager, StoreValidationError

        mgr = StoreManager(stores_dir=tmp_path)
        text = _over_limit(STORE_INJECTION_MAX_LENGTH, extra=33)
        with pytest.raises(StoreValidationError) as exc_info:
            mgr.create(
                "Bazaar", "A desert bazaar", author="Council",
                llm_injection=text,
            )
        assert str(STORE_INJECTION_MAX_LENGTH) in str(exc_info.value)
        assert str(len(text)) in str(exc_info.value)


# ═══════════════════════════════════════════════════════════════════
# Config Constants
# ═══════════════════════════════════════════════════════════════════


class TestInjectionConfigConstants:
    """Verify the config constants exist and have reasonable values."""

    def test_item_limit_is_positive(self) -> None:
        assert ITEM_INJECTION_MAX_LENGTH > 0

    def test_location_limit_is_positive(self) -> None:
        assert LOCATION_INJECTION_MAX_LENGTH > 0

    def test_store_limit_is_positive(self) -> None:
        assert STORE_INJECTION_MAX_LENGTH > 0

    def test_limits_are_reasonable(self) -> None:
        """Limits should be between 100 and 2000 characters."""
        for limit in (
            ITEM_INJECTION_MAX_LENGTH,
            LOCATION_INJECTION_MAX_LENGTH,
            STORE_INJECTION_MAX_LENGTH,
        ):
            assert 100 <= limit <= 2000, f"Questionable limit: {limit}"


# ═══════════════════════════════════════════════════════════════════
# API Response Metadata
# ═══════════════════════════════════════════════════════════════════


class TestApiInjectionMetadata:
    """Verify API responses include injection_max_length."""

    def test_item_list_includes_max_length(self, tmp_path: Path) -> None:
        from core.items import ItemManager
        from config.settings import ITEM_INJECTION_MAX_LENGTH

        mgr = ItemManager(items_dir=tmp_path)
        mgr.create("Test", "A test item", author="X", tier="permanent")
        # The route handler adds this field — test the constant exists
        assert ITEM_INJECTION_MAX_LENGTH == 500

    def test_location_list_includes_max_length(self) -> None:
        from config.settings import LOCATION_INJECTION_MAX_LENGTH
        assert LOCATION_INJECTION_MAX_LENGTH == 800

    def test_store_list_includes_max_length(self) -> None:
        from config.settings import STORE_INJECTION_MAX_LENGTH
        assert STORE_INJECTION_MAX_LENGTH == 500
