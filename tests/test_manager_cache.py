"""
Jericho — Manager Cache Tests

Tests for the lazy-init singleton manager cache: thread-safety,
lazy initialization, invalidation, and cache isolation.

The manager_cache module uses deferred imports inside each accessor
function, so patches must target the original module (e.g.
``core.registry.CouncilRegistry``) rather than ``core.manager_cache.CouncilRegistry``.
"""

from __future__ import annotations

import threading
from unittest.mock import patch, MagicMock

import pytest

from core import manager_cache


# ─── Setup / Teardown ──────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_cache():
    """Ensure every test starts and ends with a clean cache."""
    manager_cache.invalidate_all()
    yield
    manager_cache.invalidate_all()


# ─── Helpers ──────────────────────────────────────────────────

# Map each accessor to its import path for patching
_ACCESSOR_MAP = {
    "registry": ("core.registry.CouncilRegistry", manager_cache.get_registry, True),
    "api_client": ("core.api_client.APIClient", manager_cache.get_api_client, False),
    "character_manager": ("core.characters.CharacterManager", manager_cache.get_character_manager, False),
    "location_manager": ("core.locations.LocationManager", manager_cache.get_location_manager, False),
    "item_manager": ("core.items.ItemManager", manager_cache.get_item_manager, False),
    "law_manager": ("core.laws.LawManager", manager_cache.get_law_manager, False),
    "story_manager": ("core.story.StoryManager", manager_cache.get_story_manager, False),
    "proposal_manager": ("core.proposals.ProposalManager", manager_cache.get_proposal_manager, False),
    "voting_engine": ("core.voting.VotingEngine", manager_cache.get_voting_engine, False),
    "treasury_manager": ("core.treasury.TreasuryManager", manager_cache.get_treasury_manager, False),
    "store_manager": ("core.stores.StoreManager", manager_cache.get_store_manager, False),
    "memory_influence": ("core.memory_influence.MemoryInfluence", manager_cache.get_memory_influence, False),
}


def _make_mock(needs_load: bool) -> MagicMock:
    """Create a mock instance, optionally with .load() chain."""
    m = MagicMock()
    if needs_load:
        m.load.return_value = m
    return m


# ─── Lazy Init Tests ──────────────────────────────────────────


class TestLazyInit:
    """Verify managers are created on first access, not at import time."""

    @pytest.mark.parametrize("name", list(_ACCESSOR_MAP.keys()))
    def test_lazy_creates_on_first_call(self, name):
        patch_target, accessor, needs_load = _ACCESSOR_MAP[name]
        mock_instance = _make_mock(needs_load)

        with patch(patch_target, return_value=mock_instance):
            result = accessor()
            assert result is mock_instance


# ─── Singleton Tests ──────────────────────────────────────────


class TestSingleton:
    """Verify that repeated calls return the same instance."""

    @pytest.mark.parametrize("name", ["registry", "api_client", "character_manager"])
    def test_returns_same_instance(self, name):
        patch_target, accessor, needs_load = _ACCESSOR_MAP[name]
        mock_instance = _make_mock(needs_load)

        with patch(patch_target, return_value=mock_instance) as MockCls:
            first = accessor()
            second = accessor()
            assert first is second
            MockCls.assert_called_once()

    def test_all_accessors_independent(self):
        """Verify different managers are independent singletons."""
        mock_char = MagicMock()
        mock_loc = MagicMock()

        with patch("core.characters.CharacterManager", return_value=mock_char), \
             patch("core.locations.LocationManager", return_value=mock_loc):
            char = manager_cache.get_character_manager()
            loc = manager_cache.get_location_manager()
            assert char is not loc
            assert char is mock_char
            assert loc is mock_loc


# ─── Invalidation Tests ──────────────────────────────────────


_INVALIDATION_MAP = {
    "registry": (
        "core.registry.CouncilRegistry",
        manager_cache.get_registry,
        manager_cache.invalidate_registry,
        True,
    ),
    "character_manager": (
        "core.characters.CharacterManager",
        manager_cache.get_character_manager,
        manager_cache.invalidate_character_manager,
        False,
    ),
    "location_manager": (
        "core.locations.LocationManager",
        manager_cache.get_location_manager,
        manager_cache.invalidate_location_manager,
        False,
    ),
    "item_manager": (
        "core.items.ItemManager",
        manager_cache.get_item_manager,
        manager_cache.invalidate_item_manager,
        False,
    ),
    "law_manager": (
        "core.laws.LawManager",
        manager_cache.get_law_manager,
        manager_cache.invalidate_law_manager,
        False,
    ),
    "story_manager": (
        "core.story.StoryManager",
        manager_cache.get_story_manager,
        manager_cache.invalidate_story_manager,
        False,
    ),
    "proposal_manager": (
        "core.proposals.ProposalManager",
        manager_cache.get_proposal_manager,
        manager_cache.invalidate_proposal_manager,
        False,
    ),
    "voting_engine": (
        "core.voting.VotingEngine",
        manager_cache.get_voting_engine,
        manager_cache.invalidate_voting_engine,
        False,
    ),
    "treasury_manager": (
        "core.treasury.TreasuryManager",
        manager_cache.get_treasury_manager,
        manager_cache.invalidate_treasury_manager,
        False,
    ),
    "store_manager": (
        "core.stores.StoreManager",
        manager_cache.get_store_manager,
        manager_cache.invalidate_store_manager,
        False,
    ),
    "memory_influence": (
        "core.memory_influence.MemoryInfluence",
        manager_cache.get_memory_influence,
        manager_cache.invalidate_memory_influence,
        False,
    ),
}


class TestInvalidation:
    """Verify that invalidation clears the cached singleton."""

    @pytest.mark.parametrize("name", list(_INVALIDATION_MAP.keys()))
    def test_invalidate_creates_new_instance(self, name):
        patch_target, accessor, invalidator, needs_load = _INVALIDATION_MAP[name]
        mock1 = _make_mock(needs_load)
        mock2 = _make_mock(needs_load)

        with patch(patch_target, side_effect=[mock1, mock2]) as MockCls:
            first = accessor()
            invalidator()
            second = accessor()

            assert first is not second
            assert first is mock1
            assert second is mock2
            assert MockCls.call_count == 2

    def test_invalidate_all_clears_everything(self):
        """Invalidate all caches and verify each accessor creates anew."""
        mock_char1, mock_char2 = MagicMock(), MagicMock()
        mock_loc1, mock_loc2 = MagicMock(), MagicMock()

        with patch("core.characters.CharacterManager", side_effect=[mock_char1, mock_char2]), \
             patch("core.locations.LocationManager", side_effect=[mock_loc1, mock_loc2]):
            char1 = manager_cache.get_character_manager()
            loc1 = manager_cache.get_location_manager()

            manager_cache.invalidate_all()

            char2 = manager_cache.get_character_manager()
            loc2 = manager_cache.get_location_manager()

            assert char1 is not char2
            assert loc1 is not loc2

    def test_invalidate_idempotent(self):
        """Calling invalidate when cache is empty should not error."""
        manager_cache.invalidate_all()
        manager_cache.invalidate_registry()
        manager_cache.invalidate_character_manager()
        manager_cache.invalidate_location_manager()
        manager_cache.invalidate_item_manager()
        manager_cache.invalidate_law_manager()
        manager_cache.invalidate_story_manager()
        manager_cache.invalidate_proposal_manager()
        manager_cache.invalidate_voting_engine()
        manager_cache.invalidate_treasury_manager()
        manager_cache.invalidate_store_manager()
        manager_cache.invalidate_memory_influence()
        # No exception raised

    def test_invalidate_all_includes_api_client(self):
        """invalidate_all should also clear the API client."""
        mock1 = MagicMock()
        mock2 = MagicMock()

        with patch("core.api_client.APIClient", side_effect=[mock1, mock2]):
            first = manager_cache.get_api_client()
            manager_cache.invalidate_all()
            second = manager_cache.get_api_client()

            assert first is not second
            assert first is mock1
            assert second is mock2


# ─── Thread Safety Tests ──────────────────────────────────────


class TestThreadSafety:
    """Verify that concurrent access produces correct results."""

    def test_concurrent_get_same_instance(self):
        """Multiple threads accessing get_character_manager get the same instance."""
        mock_instance = MagicMock()

        with patch("core.characters.CharacterManager", return_value=mock_instance) as MockCls:
            results = []
            barrier = threading.Barrier(10)

            def worker():
                barrier.wait()
                results.append(manager_cache.get_character_manager())

            threads = [threading.Thread(target=worker) for _ in range(10)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            # All threads should get the same instance
            assert all(r is mock_instance for r in results)
            # Constructor should be called exactly once
            MockCls.assert_called_once()

    def test_concurrent_get_and_invalidate(self):
        """Concurrent reads and invalidations should not crash."""
        with patch("core.locations.LocationManager", return_value=MagicMock()):
            errors = []

            def reader():
                try:
                    for _ in range(50):
                        manager_cache.get_location_manager()
                except Exception as e:
                    errors.append(e)

            def invalidator():
                try:
                    for _ in range(50):
                        manager_cache.invalidate_location_manager()
                except Exception as e:
                    errors.append(e)

            threads = (
                [threading.Thread(target=reader) for _ in range(5)]
                + [threading.Thread(target=invalidator) for _ in range(3)]
            )
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert errors == [], f"Threading errors: {errors}"

    def test_concurrent_invalidate_all(self):
        """Concurrent invalidate_all calls should not deadlock."""
        errors = []

        def worker():
            try:
                for _ in range(20):
                    manager_cache.invalidate_all()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"Deadlock or threading errors: {errors}"


# ─── Registry .load() Chain ──────────────────────────────────


class TestRegistryLoadChain:
    """Registry accessor has special .load() chaining — verify it."""

    def test_load_called_on_new_instance(self):
        mock_instance = MagicMock()
        mock_instance.load.return_value = mock_instance

        with patch("core.registry.CouncilRegistry", return_value=mock_instance):
            result = manager_cache.get_registry()
            mock_instance.load.assert_called_once()
            assert result is mock_instance

    def test_load_not_called_on_cache_hit(self):
        mock_instance = MagicMock()
        mock_instance.load.return_value = mock_instance

        with patch("core.registry.CouncilRegistry", return_value=mock_instance):
            manager_cache.get_registry()
            manager_cache.get_registry()
            # load() should only be called once
            mock_instance.load.assert_called_once()


# ─── Edge Cases ───────────────────────────────────────────────


class TestEdgeCases:
    """Miscellaneous edge cases."""

    def test_get_after_invalidate_returns_fresh(self):
        """Invalidation followed by get returns a new instance."""
        mock1 = MagicMock()
        mock2 = MagicMock()

        with patch("core.stores.StoreManager", side_effect=[mock1, mock2]):
            first = manager_cache.get_store_manager()
            manager_cache.invalidate_store_manager()
            second = manager_cache.get_store_manager()

            assert first is mock1
            assert second is mock2
            assert first is not second

    def test_different_managers_independent_invalidation(self):
        """Invalidating one manager does not affect others."""
        mock_char = MagicMock()
        mock_loc = MagicMock()

        with patch("core.characters.CharacterManager", return_value=mock_char), \
             patch("core.locations.LocationManager", return_value=mock_loc):
            char = manager_cache.get_character_manager()
            loc = manager_cache.get_location_manager()

            # Invalidate only characters
            manager_cache.invalidate_character_manager()

            # Location should still be cached
            loc_again = manager_cache.get_location_manager()
            assert loc_again is loc
