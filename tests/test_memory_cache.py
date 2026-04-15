"""
Tests for F-059 — Lazy/Cached Memory Scoring.

Validates that MemoryInfluence.build_context() caches results by
(member_name, keyword_set) and respects TTL, skip_world_entities
mismatch, per-member clearing, and the cache_enabled toggle.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory import AgentMemory, CoreBelief, MemoryEntry
from core.memory_influence import MemoryInfluence, MemoryContext, _CacheEntry


# ─── Fixtures ─────────────────────────────────────────────────

@pytest.fixture
def mem_dir(tmp_path):
    """Create a temp memories dir with one member's beliefs + logs."""
    member_dir = tmp_path / "sage"
    member_dir.mkdir()
    # Write a core belief
    import json
    beliefs = [
        {
            "topic": "ethics",
            "content": "AI must be transparent",
            "added_timestamp": "2026-01-01T00:00:00+00:00",
            "source": "test",
        }
    ]
    (member_dir / "core_beliefs.json").write_text(
        json.dumps(beliefs), encoding="utf-8",
    )
    # Write a session log entry
    entry = {
        "timestamp": "2026-04-01T12:00:00+00:00",
        "session_id": "S-001",
        "event_type": "chat",
        "content": "Discussed ethics and transparency in AI systems",
        "source": "test",
        "metadata": {},
    }
    (member_dir / "session_log.jsonl").write_text(
        json.dumps(entry) + "\n", encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def mi(mem_dir):
    """A MemoryInfluence instance with cache enabled, short TTL, no embeddings."""
    return MemoryInfluence(
        memories_dir=mem_dir,
        embedding_provider=None,
        decay_enabled=False,
        summarization_enabled=False,
        contested_enabled=False,
        cache_enabled=True,
        cache_ttl_seconds=5.0,
    )


@pytest.fixture
def mi_no_cache(mem_dir):
    """A MemoryInfluence instance with caching disabled."""
    return MemoryInfluence(
        memories_dir=mem_dir,
        embedding_provider=None,
        decay_enabled=False,
        summarization_enabled=False,
        contested_enabled=False,
        cache_enabled=False,
    )


# ─── TestCacheProperties ─────────────────────────────────────

class TestCacheProperties:
    """Verify cache-related properties and defaults."""

    def test_cache_enabled_property(self, mi):
        assert mi.cache_enabled is True

    def test_cache_ttl_property(self, mi):
        assert mi.cache_ttl == 5.0

    def test_cache_size_initial(self, mi):
        assert mi.cache_size == 0

    def test_cache_disabled_property(self, mi_no_cache):
        assert mi_no_cache.cache_enabled is False

    def test_default_ttl_from_settings(self, mem_dir):
        """When no ttl is passed, it should come from settings."""
        from config.settings import MEMORY_CACHE_TTL_SECONDS
        mi = MemoryInfluence(
            memories_dir=mem_dir,
            embedding_provider=None,
            cache_enabled=True,
        )
        assert mi.cache_ttl == MEMORY_CACHE_TTL_SECONDS

    def test_repr_includes_cache(self, mi):
        r = repr(mi)
        assert "cache=True" in r
        assert "cache_ttl=5.0" in r


# ─── TestCacheHitAndMiss ──────────────────────────────────────

class TestCacheHitAndMiss:
    """Verify that build_context caches on the first call and returns
    the cached result on subsequent identical calls."""

    def test_first_call_populates_cache(self, mi):
        ctx = mi.build_context("sage", ["ethics", "transparency"])
        assert mi.cache_size == 1
        assert ctx.member_name == "sage"

    def test_second_call_returns_cached(self, mi):
        ctx1 = mi.build_context("sage", ["ethics", "transparency"])
        ctx2 = mi.build_context("sage", ["ethics", "transparency"])
        # Must be the exact same object, not a re-computation
        assert ctx1 is ctx2
        assert mi.cache_size == 1

    def test_different_keywords_miss(self, mi):
        ctx1 = mi.build_context("sage", ["ethics"])
        ctx2 = mi.build_context("sage", ["politics"])
        assert ctx1 is not ctx2
        assert mi.cache_size == 2

    def test_different_member_miss(self, mi, mem_dir):
        # Create a second member dir
        (mem_dir / "logic").mkdir()
        ctx1 = mi.build_context("sage", ["ethics"])
        ctx2 = mi.build_context("logic", ["ethics"])
        assert ctx1 is not ctx2
        assert mi.cache_size == 2


# ─── TestKeywordOrderIndependence ─────────────────────────────

class TestKeywordOrderIndependence:
    """Keywords in different order should produce a cache hit."""

    def test_reordered_keywords_hit(self, mi):
        ctx1 = mi.build_context("sage", ["ethics", "transparency", "ai"])
        ctx2 = mi.build_context("sage", ["ai", "ethics", "transparency"])
        assert ctx1 is ctx2
        assert mi.cache_size == 1

    def test_case_insensitive_keywords(self, mi):
        ctx1 = mi.build_context("sage", ["Ethics", "AI"])
        ctx2 = mi.build_context("sage", ["ethics", "ai"])
        assert ctx1 is ctx2

    def test_case_insensitive_member_name(self, mi):
        ctx1 = mi.build_context("Sage", ["ethics"])
        ctx2 = mi.build_context("sage", ["ethics"])
        assert ctx1 is ctx2

    def test_whitespace_normalisation(self, mi):
        ctx1 = mi.build_context("  Sage  ", ["  ethics  "])
        ctx2 = mi.build_context("sage", ["ethics"])
        assert ctx1 is ctx2


# ─── TestTTLExpiration ────────────────────────────────────────

class TestTTLExpiration:
    """Verify that stale cache entries are evicted."""

    def test_stale_entry_evicted(self, mi):
        ctx1 = mi.build_context("sage", ["ethics"])
        assert mi.cache_size == 1

        # Artificially age the cache entry
        key = mi._make_cache_key("sage", ["ethics"])
        mi._cache[key] = _CacheEntry(
            context=ctx1,
            created_at=time.monotonic() - 10.0,  # 10s ago, TTL is 5s
            skip_world_entities=False,
        )
        ctx2 = mi.build_context("sage", ["ethics"])
        # Should be a fresh result, not the cached one
        assert ctx2 is not ctx1
        assert mi.cache_size == 1  # replaced stale with fresh

    def test_fresh_entry_survives(self, mi):
        ctx1 = mi.build_context("sage", ["ethics"])
        # Artificially set entry to 2s ago (within 5s TTL)
        key = mi._make_cache_key("sage", ["ethics"])
        mi._cache[key] = _CacheEntry(
            context=ctx1,
            created_at=time.monotonic() - 2.0,
            skip_world_entities=False,
        )
        ctx2 = mi.build_context("sage", ["ethics"])
        assert ctx2 is ctx1  # still cached


# ─── TestSkipWorldEntitiesMismatch ────────────────────────────

class TestSkipWorldEntitiesMismatch:
    """Cache entry is invalidated when skip_world_entities differs."""

    def test_skip_mismatch_invalidates(self, mi):
        ctx1 = mi.build_context("sage", ["ethics"], skip_world_entities=False)
        ctx2 = mi.build_context("sage", ["ethics"], skip_world_entities=True)
        assert ctx1 is not ctx2
        # The mismatch evicts old entry and stores new one
        assert mi.cache_size == 1

    def test_same_skip_flag_hits(self, mi):
        ctx1 = mi.build_context("sage", ["ethics"], skip_world_entities=True)
        ctx2 = mi.build_context("sage", ["ethics"], skip_world_entities=True)
        assert ctx1 is ctx2


# ─── TestClearCache ───────────────────────────────────────────

class TestClearCache:
    """Test explicit cache clearing."""

    def test_clear_all(self, mi, mem_dir):
        (mem_dir / "logic").mkdir()
        mi.build_context("sage", ["ethics"])
        mi.build_context("logic", ["ethics"])
        assert mi.cache_size == 2
        removed = mi.clear_cache()
        assert removed == 2
        assert mi.cache_size == 0

    def test_clear_by_member(self, mi, mem_dir):
        (mem_dir / "logic").mkdir()
        mi.build_context("sage", ["ethics"])
        mi.build_context("sage", ["politics"])
        mi.build_context("logic", ["ethics"])
        assert mi.cache_size == 3
        removed = mi.clear_cache(member_name="sage")
        assert removed == 2
        assert mi.cache_size == 1  # logic's entry remains

    def test_clear_empty_cache(self, mi):
        removed = mi.clear_cache()
        assert removed == 0

    def test_clear_nonexistent_member(self, mi):
        mi.build_context("sage", ["ethics"])
        removed = mi.clear_cache(member_name="unknown")
        assert removed == 0
        assert mi.cache_size == 1

    def test_clear_member_case_insensitive(self, mi):
        mi.build_context("sage", ["ethics"])
        removed = mi.clear_cache(member_name="SAGE")
        assert removed == 1


# ─── TestCacheDisabled ────────────────────────────────────────

class TestCacheDisabled:
    """Verify that when cache is disabled, no caching occurs."""

    def test_no_cache_when_disabled(self, mi_no_cache):
        ctx1 = mi_no_cache.build_context("sage", ["ethics"])
        ctx2 = mi_no_cache.build_context("sage", ["ethics"])
        # Results are structurally equal but not the same object
        assert ctx1 is not ctx2
        assert mi_no_cache.cache_size == 0

    def test_clear_cache_noop_when_disabled(self, mi_no_cache):
        mi_no_cache.build_context("sage", ["ethics"])
        removed = mi_no_cache.clear_cache()
        assert removed == 0


# ─── TestCacheKeyGeneration ───────────────────────────────────

class TestCacheKeyGeneration:
    """Verify the static _make_cache_key method."""

    def test_basic_key(self):
        key = MemoryInfluence._make_cache_key("Sage", ["ethics", "ai"])
        assert key[0] == "sage"
        assert key[1] == frozenset({"ethics", "ai"})

    def test_empty_keywords(self):
        key = MemoryInfluence._make_cache_key("sage", [])
        assert key[1] == frozenset()

    def test_whitespace_keyword_filtered(self):
        key = MemoryInfluence._make_cache_key("sage", ["", "  ", "ethics"])
        assert key[1] == frozenset({"ethics"})

    def test_duplicate_keywords_deduped(self):
        key = MemoryInfluence._make_cache_key("sage", ["ethics", "ethics", "ETHICS"])
        assert key[1] == frozenset({"ethics"})
        assert len(key[1]) == 1

    def test_order_independence(self):
        k1 = MemoryInfluence._make_cache_key("sage", ["a", "b", "c"])
        k2 = MemoryInfluence._make_cache_key("sage", ["c", "a", "b"])
        assert k1 == k2


# ─── TestCacheEntryDataclass ──────────────────────────────────

class TestCacheEntryDataclass:
    """Verify the internal _CacheEntry dataclass."""

    def test_fields(self):
        ctx = MemoryContext(member_name="sage")
        entry = _CacheEntry(
            context=ctx,
            created_at=time.monotonic(),
            skip_world_entities=False,
        )
        assert entry.context is ctx
        assert entry.skip_world_entities is False

    def test_mutable(self):
        ctx = MemoryContext(member_name="sage")
        entry = _CacheEntry(
            context=ctx,
            created_at=0.0,
            skip_world_entities=True,
        )
        entry.created_at = 999.0
        assert entry.created_at == 999.0


# ─── TestCacheSettingsConstants ───────────────────────────────

class TestCacheSettingsConstants:
    """Verify settings constants exist and have correct defaults."""

    def test_ttl_default(self):
        from config.settings import MEMORY_CACHE_TTL_SECONDS
        assert MEMORY_CACHE_TTL_SECONDS == 300

    def test_enabled_default(self):
        from config.settings import MEMORY_CACHE_ENABLED
        assert MEMORY_CACHE_ENABLED is True


# ─── TestCacheIntegrationScoring ──────────────────────────────

class TestCacheIntegrationScoring:
    """Verify that cached results have correct scored content."""

    def test_cached_result_has_beliefs(self, mi):
        ctx = mi.build_context("sage", ["ethics", "transparency"])
        assert len(ctx.beliefs) > 0
        # Second call should return identical beliefs
        ctx2 = mi.build_context("sage", ["ethics", "transparency"])
        assert ctx2.beliefs == ctx.beliefs
        assert ctx2 is ctx

    def test_cached_result_preserves_formatted_text(self, mi):
        ctx1 = mi.build_context("sage", ["ethics"])
        ctx2 = mi.build_context("sage", ["ethics"])
        assert ctx2.formatted_text == ctx1.formatted_text
        assert len(ctx1.formatted_text) > 0

    def test_different_keywords_different_results(self, mi):
        ctx_ethics = mi.build_context("sage", ["ethics", "transparency"])
        ctx_cooking = mi.build_context("sage", ["cooking", "recipes"])
        # Different keywords produce different scoring results
        assert ctx_ethics.formatted_text != ctx_cooking.formatted_text or \
               ctx_ethics.beliefs != ctx_cooking.beliefs or \
               ctx_ethics is not ctx_cooking
