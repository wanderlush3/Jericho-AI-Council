"""
Jericho -- Memory Influence (F-018)

Memories affect agent responses via context injection with relevance
scoring.  The engine scores and selects the most relevant memories
and beliefs for a given conversational context, formats them as
markdown, and returns text suitable for injection into any prompt
builder.

Scoring uses hybrid similarity: semantic embedding cosine similarity
(primary) combined with keyword-based Jaccard similarity (secondary).
When sentence-transformers is not installed, scoring falls back to
pure Jaccard.  Core beliefs receive a configurable boost multiplier
because they represent persistent stance rather than ephemeral
session events.

Time-weighted decay gently reduces the influence of older memories
using an exponential half-life formula.  Memory summarization
condenses old sessions via an LLM call after a configurable session
threshold.  Contested memories allow agents to hold divergent
recollections of the same event.
"""

from __future__ import annotations

import logging
import math
import os
import random
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    CONTESTED_MEMORY_ENABLED,
    CONTESTED_MEMORY_PROBABILITY,
    CONTEXT_MAX_WORLD_ITEMS,
    CONTEXT_MAX_WORLD_LOCATIONS,
    DEFAULT_SUMMARIZATION_MODEL,
    DEFAULT_SUMMARIZATION_PROVIDER,
    EMBEDDING_JACCARD_WEIGHT,
    EMBEDDING_SIMILARITY_WEIGHT,
    ITEMS_DIR,
    LOCATIONS_DIR,
    MEMORIES_DIR,
    MEMORY_CACHE_ENABLED,
    MEMORY_CACHE_TTL_SECONDS,
    MEMORY_DECAY_ENABLED,
    MEMORY_DECAY_HALF_LIFE_DAYS,
    MEMORY_DECAY_MIN_FACTOR,
    MEMORY_INFLUENCE_BELIEF_BOOST,
    MEMORY_INFLUENCE_MAX_BELIEFS,
    MEMORY_INFLUENCE_MAX_MEMORIES,
    MEMORY_INFLUENCE_MIN_RELEVANCE,
    MEMORY_SUMMARIZATION_ENABLED,
    MEMORY_SUMMARIZATION_KEEP_RECENT,
    MEMORY_SUMMARIZATION_SESSION_THRESHOLD,
    SUMMARIZATION_MODEL_ENV,
    SUMMARIZATION_PROVIDER_ENV,
)
from core.memory import AgentMemory, CoreBelief, MemoryEntry

logger = logging.getLogger(__name__)


# ─── Exceptions ────────────────────────────────────────────────


class MemoryInfluenceError(Exception):
    """Base exception for memory-influence errors."""


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ScoredMemory:
    """A MemoryEntry annotated with a relevance score."""

    entry: MemoryEntry
    relevance_score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry": self.entry.to_dict(),
            "relevance_score": self.relevance_score,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoredMemory:
        return cls(
            entry=MemoryEntry.from_dict(data["entry"]),
            relevance_score=data.get("relevance_score", 0.0),
            reason=data.get("reason", ""),
        )


@dataclass(frozen=True)
class ScoredBelief:
    """A CoreBelief annotated with a relevance score."""

    belief: CoreBelief
    relevance_score: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "belief": self.belief.to_dict(),
            "relevance_score": self.relevance_score,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoredBelief:
        return cls(
            belief=CoreBelief.from_dict(data["belief"]),
            relevance_score=data.get("relevance_score", 0.0),
            reason=data.get("reason", ""),
        )


@dataclass(frozen=True)
class MemoryContext:
    """
    Bundled result of memory influence scoring.

    Contains the top-scored beliefs and memories plus a pre-rendered
    markdown string suitable for direct injection into any prompt.
    """

    member_name: str
    beliefs: list[ScoredBelief] = field(default_factory=list)
    memories: list[ScoredMemory] = field(default_factory=list)
    formatted_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "member_name": self.member_name,
            "beliefs": [b.to_dict() for b in self.beliefs],
            "memories": [m.to_dict() for m in self.memories],
            "formatted_text": self.formatted_text,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryContext:
        return cls(
            member_name=data["member_name"],
            beliefs=[ScoredBelief.from_dict(b) for b in data.get("beliefs", [])],
            memories=[ScoredMemory.from_dict(m) for m in data.get("memories", [])],
            formatted_text=data.get("formatted_text", ""),
        )

    @property
    def has_content(self) -> bool:
        """True if there is at least one belief or memory."""
        return bool(self.beliefs or self.memories)


@dataclass
class _CacheEntry:
    """Internal cache entry for MemoryContext results."""

    context: MemoryContext
    created_at: float  # time.monotonic() timestamp
    skip_world_entities: bool


# ─── Tokenisation ──────────────────────────────────────────────

# Simple word-boundary tokeniser: splits on non-alphanumeric, lowercases.
_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)

# Stop words filtered from keyword sets to improve relevance signal.
_STOP_WORDS: frozenset[str] = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "is", "it", "be", "as", "was",
        "are", "this", "that", "from", "not", "has", "have", "had",
        "will", "can", "do", "does", "did", "been", "being", "would",
        "should", "could", "may", "might", "must", "shall", "its",
        "they", "them", "their", "we", "our", "you", "your", "he",
        "she", "him", "her", "i", "me", "my", "no", "yes", "so",
        "if", "then", "than", "too", "also", "just", "about", "up",
        "out", "all", "some", "any", "each", "every", "more",
    }
)


def _tokenise(text: str) -> set[str]:
    """Extract a set of meaningful lowercase tokens from *text*."""
    words = {w.lower() for w in _WORD_RE.findall(text)}
    return words - _STOP_WORDS


def _jaccard(set_a: set[str], set_b: set[str]) -> float:
    """Jaccard similarity between two token sets (0.0–1.0)."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


# ─── Sentinel for default embedding provider ─────────────────
_SENTINEL = object()

# ─── Memory Influence Engine ──────────────────────────────────


class MemoryInfluence:
    """
    Scores and selects the most relevant memories and beliefs for
    a given conversational context.

    Usage::

        mi = MemoryInfluence()
        ctx = mi.build_context("sage", ["ethics", "safety", "AI autonomy"])
        if ctx.has_content:
            prompt += "\\n" + ctx.formatted_text
    """

    def __init__(
        self,
        *,
        memory_limit: int | None = None,
        belief_limit: int | None = None,
        min_relevance: float | None = None,
        belief_boost: float | None = None,
        memories_dir: Path | None = None,
        embedding_provider: Any | None = _SENTINEL,
        decay_enabled: bool | None = None,
        decay_half_life_days: float | None = None,
        decay_min_factor: float | None = None,
        summarization_enabled: bool | None = None,
        contested_enabled: bool | None = None,
        contested_probability: float | None = None,
        cache_enabled: bool | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> None:
        self._memory_limit = (
            memory_limit if memory_limit is not None
            else MEMORY_INFLUENCE_MAX_MEMORIES
        )
        self._belief_limit = (
            belief_limit if belief_limit is not None
            else MEMORY_INFLUENCE_MAX_BELIEFS
        )
        self._min_relevance = (
            min_relevance if min_relevance is not None
            else MEMORY_INFLUENCE_MIN_RELEVANCE
        )
        self._belief_boost = (
            belief_boost if belief_boost is not None
            else MEMORY_INFLUENCE_BELIEF_BOOST
        )
        self._memories_dir = memories_dir or MEMORIES_DIR

        # Embedding provider: lazy-default via singleton, or explicitly
        # injected (use None to force Jaccard-only mode)
        if embedding_provider is _SENTINEL:
            from core.embeddings import get_embedding_provider
            self._embeddings = get_embedding_provider()
        else:
            self._embeddings = embedding_provider

        # Decay settings
        self._decay_enabled = (
            decay_enabled if decay_enabled is not None
            else MEMORY_DECAY_ENABLED
        )
        self._decay_half_life = (
            decay_half_life_days if decay_half_life_days is not None
            else MEMORY_DECAY_HALF_LIFE_DAYS
        )
        self._decay_min = (
            decay_min_factor if decay_min_factor is not None
            else MEMORY_DECAY_MIN_FACTOR
        )

        # Summarization settings
        self._summarization_enabled = (
            summarization_enabled if summarization_enabled is not None
            else MEMORY_SUMMARIZATION_ENABLED
        )

        # Contested memory settings
        self._contested_enabled = (
            contested_enabled if contested_enabled is not None
            else CONTESTED_MEMORY_ENABLED
        )
        self._contested_probability = (
            contested_probability if contested_probability is not None
            else CONTESTED_MEMORY_PROBABILITY
        )

        # Cache settings (F-059)
        self._cache_enabled = (
            cache_enabled if cache_enabled is not None
            else MEMORY_CACHE_ENABLED
        )
        self._cache_ttl = (
            cache_ttl_seconds if cache_ttl_seconds is not None
            else MEMORY_CACHE_TTL_SECONDS
        )
        self._cache: dict[tuple[str, frozenset[str]], _CacheEntry] = {}

    # ── Properties ────────────────────────────────────────────

    @property
    def memory_limit(self) -> int:
        return self._memory_limit

    @property
    def belief_limit(self) -> int:
        return self._belief_limit

    @property
    def min_relevance(self) -> float:
        return self._min_relevance

    @property
    def belief_boost(self) -> float:
        return self._belief_boost

    @property
    def decay_enabled(self) -> bool:
        return self._decay_enabled

    @property
    def decay_half_life(self) -> float:
        return self._decay_half_life

    @property
    def decay_min_factor(self) -> float:
        return self._decay_min

    @property
    def summarization_enabled(self) -> bool:
        return self._summarization_enabled

    @property
    def contested_enabled(self) -> bool:
        return self._contested_enabled

    @property
    def contested_probability(self) -> float:
        return self._contested_probability

    @property
    def cache_enabled(self) -> bool:
        return self._cache_enabled

    @property
    def cache_ttl(self) -> float:
        return self._cache_ttl

    @property
    def cache_size(self) -> int:
        """Number of entries currently in the cache."""
        return len(self._cache)

    # ── Scoring ───────────────────────────────────────────────────────

    @property
    def embeddings_available(self) -> bool:
        """Whether semantic embeddings are available for scoring."""
        return (
            self._embeddings is not None
            and self._embeddings.is_available
        )

    def _hybrid_score(
        self,
        context_text: str,
        candidate_text: str,
        context_tokens: set[str],
        candidate_tokens: set[str],
    ) -> tuple[float, str]:
        """
        Compute a hybrid score combining embedding similarity and
        Jaccard similarity.  Returns ``(score, reason)``.

        When embeddings are available::

            score = emb_weight * cosine_sim + jac_weight * jaccard_sim

        When embeddings are unavailable::

            score = jaccard_sim
        """
        jaccard_sim = _jaccard(context_tokens, candidate_tokens)
        overlap = context_tokens & candidate_tokens

        if self.embeddings_available:
            emb_sim = self._embeddings.similarity(context_text, candidate_text)
            # Clamp to [0, 1]
            emb_sim = max(0.0, min(emb_sim, 1.0))
            score = (
                EMBEDDING_SIMILARITY_WEIGHT * emb_sim
                + EMBEDDING_JACCARD_WEIGHT * jaccard_sim
            )
            reason_parts: list[str] = []
            if emb_sim >= 0.3:
                reason_parts.append(f"Semantic match ({emb_sim:.2f})")
            if overlap:
                reason_parts.append(
                    f"Keywords: {', '.join(sorted(overlap))}"
                )
            reason = "; ".join(reason_parts) if reason_parts else "General relevance"
        else:
            score = jaccard_sim
            reason = (
                f"Matched keywords: {', '.join(sorted(overlap))}"
                if overlap
                else "General relevance"
            )

        return round(score, 4), reason

    # ── Time Decay ────────────────────────────────────────────────────

    def _compute_decay_factor(self, timestamp: str) -> float:
        """
        Compute a time-decay factor for a memory entry.

        Uses an exponential half-life formula::

            factor = max(min_factor, 0.5 ^ (age_days / half_life_days))

        A 30-day half-life means a memory from 30 days ago retains
        ~50% freshness.  The floor ensures no memory drops to zero.
        Returns 1.0 when decay is disabled.
        """
        if not self._decay_enabled or self._decay_half_life <= 0:
            return 1.0

        try:
            # Handle both offset-aware and naive ISO timestamps
            ts = datetime.fromisoformat(timestamp)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            age_days = max((now - ts).total_seconds() / 86400, 0.0)
        except (ValueError, TypeError):
            return 1.0  # Unparseable timestamp → no penalty

        factor = math.pow(0.5, age_days / self._decay_half_life)
        return max(self._decay_min, factor)

    def score_memories(
        self,
        entries: list[MemoryEntry],
        context_keywords: list[str],
    ) -> list[ScoredMemory]:
        """
        Score memory entries against context keywords.

        Uses hybrid scoring (embedding + Jaccard) when embeddings are
        available, otherwise falls back to pure Jaccard.  When decay
        is enabled, each score is multiplied by a freshness factor
        derived from the entry's timestamp.

        Returns a list of ScoredMemory objects sorted by descending
        relevance, filtered to those above min_relevance, limited
        to memory_limit results.
        """
        if not entries:
            return []

        context_text = " ".join(context_keywords)
        context_tokens = _tokenise(context_text)
        scored: list[ScoredMemory] = []

        # Pre-compute all entry texts
        entry_texts = [
            f"{entry.content} {entry.event_type} {entry.source}"
            for entry in entries
        ]

        # Batch compute embedding similarities (one encode pass)
        emb_scores: list[float] | None = None
        if self.embeddings_available:
            emb_scores = self._embeddings.batch_similarity(
                context_text, entry_texts,
            )

        for idx, entry in enumerate(entries):
            entry_text = entry_texts[idx]
            entry_tokens = _tokenise(entry_text)
            jaccard_sim = _jaccard(context_tokens, entry_tokens)
            overlap = context_tokens & entry_tokens

            if emb_scores is not None:
                emb_sim = max(0.0, min(emb_scores[idx], 1.0))
                raw_score = (
                    EMBEDDING_SIMILARITY_WEIGHT * emb_sim
                    + EMBEDDING_JACCARD_WEIGHT * jaccard_sim
                )
                reason_parts: list[str] = []
                if emb_sim >= 0.3:
                    reason_parts.append(f"Semantic match ({emb_sim:.2f})")
                if overlap:
                    reason_parts.append(
                        f"Keywords: {', '.join(sorted(overlap))}"
                    )
                reason = "; ".join(reason_parts) if reason_parts else "General relevance"
            else:
                raw_score = jaccard_sim
                reason = (
                    f"Matched keywords: {', '.join(sorted(overlap))}"
                    if overlap
                    else "General relevance"
                )

            raw_score = round(raw_score, 4)

            # Apply time decay
            decay = self._compute_decay_factor(entry.timestamp)
            score = round(raw_score * decay, 4)

            if decay < 1.0 and raw_score > 0:
                reason += f" (freshness: {decay:.0%})"

            if score >= self._min_relevance:
                scored.append(
                    ScoredMemory(
                        entry=entry,
                        relevance_score=score,
                        reason=reason,
                    )
                )

        # Sort by score descending, then by timestamp descending (recent first)
        scored.sort(
            key=lambda s: (s.relevance_score, s.entry.timestamp),
            reverse=True,
        )
        return scored[: self._memory_limit]

    def score_beliefs(
        self,
        beliefs: list[CoreBelief],
        context_keywords: list[str],
    ) -> list[ScoredBelief]:
        """
        Score core beliefs against context keywords.

        Uses hybrid scoring (embedding + Jaccard) when embeddings are
        available, otherwise falls back to pure Jaccard.  Beliefs
        receive a boost multiplier since they represent persistent
        stance.  Returns scored beliefs sorted by descending
        relevance, filtered and limited.
        """
        if not beliefs:
            return []

        context_text = " ".join(context_keywords)
        context_tokens = _tokenise(context_text)
        scored: list[ScoredBelief] = []

        # Pre-compute all belief texts
        belief_texts = [
            f"{belief.topic} {belief.content}" for belief in beliefs
        ]

        # Batch compute embedding similarities (one encode pass)
        emb_scores: list[float] | None = None
        if self.embeddings_available:
            emb_scores = self._embeddings.batch_similarity(
                context_text, belief_texts,
            )

        for idx, belief in enumerate(beliefs):
            belief_text = belief_texts[idx]
            belief_tokens = _tokenise(belief_text)
            jaccard_sim = _jaccard(context_tokens, belief_tokens)
            overlap = context_tokens & belief_tokens

            if emb_scores is not None:
                emb_sim = max(0.0, min(emb_scores[idx], 1.0))
                raw_score = (
                    EMBEDDING_SIMILARITY_WEIGHT * emb_sim
                    + EMBEDDING_JACCARD_WEIGHT * jaccard_sim
                )
                reason_parts: list[str] = []
                if emb_sim >= 0.3:
                    reason_parts.append(f"Semantic match ({emb_sim:.2f})")
                if overlap:
                    reason_parts.append(
                        f"Keywords: {', '.join(sorted(overlap))}"
                    )
                raw_reason = "; ".join(reason_parts) if reason_parts else "General relevance"
            else:
                raw_score = jaccard_sim
                raw_reason = (
                    f"Matched keywords: {', '.join(sorted(overlap))}"
                    if overlap
                    else "General relevance"
                )

            raw_score = round(raw_score, 4)
            boosted = min(raw_score * self._belief_boost, 1.0)

            if boosted >= self._min_relevance:
                reason = (
                    f"Belief on '{belief.topic}': {raw_reason}"
                    if raw_reason != "General relevance"
                    else f"Belief on '{belief.topic}'"
                )
                scored.append(
                    ScoredBelief(
                        belief=belief,
                        relevance_score=round(boosted, 4),
                        reason=reason,
                    )
                )

        scored.sort(key=lambda s: s.relevance_score, reverse=True)
        return scored[: self._belief_limit]

    # ── Context Building ──────────────────────────────────────

    @staticmethod
    def _make_cache_key(
        member_name: str,
        context_keywords: list[str],
    ) -> tuple[str, frozenset[str]]:
        """Build a deterministic cache key from member name + keywords.

        The key is ``(normalised_name, frozenset_of_lowered_keywords)``
        so keyword order does not affect cache hits.
        """
        normalised = member_name.strip().lower()
        kw_set = frozenset(k.strip().lower() for k in context_keywords if k.strip())
        return (normalised, kw_set)

    def _get_cached(
        self,
        key: tuple[str, frozenset[str]],
        skip_world_entities: bool,
    ) -> MemoryContext | None:
        """Return a cached MemoryContext if it exists and is still fresh."""
        entry = self._cache.get(key)
        if entry is None:
            return None
        age = time.monotonic() - entry.created_at
        if age > self._cache_ttl:
            # Stale — remove and miss
            del self._cache[key]
            return None
        # If previous cache was with world entities but caller now wants
        # to skip (or vice-versa), treat as a miss so world context is
        # correct.  We could store both variants, but for simplicity
        # we just invalidate on mismatch.
        if entry.skip_world_entities != skip_world_entities:
            del self._cache[key]
            return None
        return entry.context

    def _put_cached(
        self,
        key: tuple[str, frozenset[str]],
        context: MemoryContext,
        skip_world_entities: bool,
    ) -> None:
        """Store a MemoryContext in the cache."""
        self._cache[key] = _CacheEntry(
            context=context,
            created_at=time.monotonic(),
            skip_world_entities=skip_world_entities,
        )

    def clear_cache(self, member_name: str | None = None) -> int:
        """Clear cached MemoryContext entries.

        Args:
            member_name: If provided, only clear entries for this member.
                If ``None``, clear the entire cache.

        Returns:
            Number of entries removed.
        """
        if member_name is None:
            count = len(self._cache)
            self._cache.clear()
            return count
        normalised = member_name.strip().lower()
        keys_to_remove = [
            k for k in self._cache if k[0] == normalised
        ]
        for k in keys_to_remove:
            del self._cache[k]
        return len(keys_to_remove)

    def build_context(
        self,
        member_name: str,
        context_keywords: list[str],
        *,
        memories_dir: Path | None = None,
        locations_dir: Path | None = None,
        items_dir: Path | None = None,
        skip_world_entities: bool = False,
    ) -> MemoryContext:
        """
        Build a complete MemoryContext for a member.

        Loads the member's core beliefs and recent session memories,
        scores them against the given context keywords, and returns
        a MemoryContext with pre-formatted text.  Active world
        locations and items are also included so the member is aware
        of the world the council inhabits.

        When summarization is enabled and enough sessions have
        accumulated, previously-summarized entries are also included
        in the scoring pool.

        Results are cached by ``(member_name, keyword_set)`` for up
        to ``cache_ttl`` seconds (F-059).  Repeated calls with the
        same member and keywords return the cached result without
        re-scoring.  Pass ``cache_enabled=False`` at construction
        time or toggle ``MEMORY_CACHE_ENABLED`` to disable.

        Args:
            member_name: Council member name (case-insensitive).
            context_keywords: Words/phrases describing the current topic.
            memories_dir: Override the memories directory (for testing).
            locations_dir: Override the locations directory (for testing).
            items_dir: Override the items directory (for testing).
            skip_world_entities: When True, omit world locations and
                items from the context.  Use this when the caller's
                chat history already contains world context (F-055).

        Returns:
            MemoryContext with scored beliefs, memories, and formatted text.
        """
        # F-059: Check cache first
        cache_key: tuple[str, frozenset[str]] | None = None
        if self._cache_enabled:
            cache_key = self._make_cache_key(member_name, context_keywords)
            cached = self._get_cached(cache_key, skip_world_entities)
            if cached is not None:
                return cached

        base_dir = memories_dir or self._memories_dir
        agent_mem = AgentMemory(member_name, memories_dir=base_dir)

        # Load raw data
        beliefs = agent_mem.read_core_beliefs()
        recent = agent_mem.get_recent_memories(limit=50)  # over-fetch, then score

        # Include summarized memories in the scoring pool
        if self._summarization_enabled:
            summarized = agent_mem.read_summarized_log()
            if summarized:
                recent = summarized + recent

        # Score against context
        scored_beliefs = self.score_beliefs(beliefs, context_keywords)
        scored_memories = self.score_memories(recent, context_keywords)

        # Load contested memories for scored results
        contested_map: dict[str, list[dict[str, Any]]] = {}
        if self._contested_enabled:
            contested_map = self._load_contested_for_scored(
                agent_mem, scored_memories,
            )

        # Load active locations and items (capped to prevent unbounded growth)
        # F-055: Skip when the caller's chat history already has world context
        if skip_world_entities:
            active_locations = []
            active_items = []
        else:
            active_locations = self._load_active_locations(locations_dir)[
                :CONTEXT_MAX_WORLD_LOCATIONS
            ]
            active_items = self._load_active_items(items_dir)[
                :CONTEXT_MAX_WORLD_ITEMS
            ]

        # Format for prompt injection
        formatted = self.format_for_prompt(
            scored_beliefs, scored_memories,
            locations=active_locations,
            items=active_items,
            contested=contested_map,
        )

        result = MemoryContext(
            member_name=member_name.strip().lower(),
            beliefs=scored_beliefs,
            memories=scored_memories,
            formatted_text=formatted,
        )

        # F-059: Store in cache
        if self._cache_enabled and cache_key is not None:
            self._put_cached(cache_key, result, skip_world_entities)

        return result

    @staticmethod
    def _load_contested_for_scored(
        agent_mem: AgentMemory,
        scored_memories: list[ScoredMemory],
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Load contested memories keyed by event_id for the scored set.

        Uses session_id+timestamp as event_id to match records.
        """
        all_contested = agent_mem.read_contested_memories()
        if not all_contested:
            return {}
        event_ids = {
            f"{sm.entry.session_id}:{sm.entry.timestamp}"
            for sm in scored_memories
        }
        result: dict[str, list[dict[str, Any]]] = {}
        for rec in all_contested:
            eid = rec.get("event_id", "")
            if eid in event_ids:
                result.setdefault(eid, []).append(rec)
        return result

    # ── Formatting ────────────────────────────────────────────

    @staticmethod
    def format_for_prompt(
        beliefs: list[ScoredBelief],
        memories: list[ScoredMemory],
        *,
        locations: list[Any] | None = None,
        items: list[Any] | None = None,
        contested: dict[str, list[dict[str, Any]]] | None = None,
    ) -> str:
        """
        Render scored beliefs, memories, world locations, and world
        items as markdown for prompt injection.

        When *contested* is provided, divergent recollections appear
        as sub-bullets under the relevant memory.

        Returns an empty string if there is nothing to inject.
        """
        parts: list[str] = []
        contested = contested or {}

        if beliefs:
            parts.append("### Your Core Beliefs (Relevant to This Context)")
            for sb in beliefs:
                parts.append(
                    f"- **{sb.belief.topic}**: {sb.belief.content}"
                )

        if memories:
            parts.append("\n### Your Relevant Memories")
            for sm in memories:
                parts.append(
                    f"- [{sm.entry.event_type}] {sm.entry.content}"
                )
                # Append contested perspectives if any
                event_id = f"{sm.entry.session_id}:{sm.entry.timestamp}"
                divergent = contested.get(event_id, [])
                for rec in divergent:
                    member = rec.get("member_name", "unknown")
                    alt_content = rec.get("content", "")
                    parts.append(
                        f"  - *[{member}'s recollection]:* {alt_content}"
                    )

        if locations:
            parts.append("\n### World Locations (Your Known World)")
            for loc in locations:
                line = f"- **{loc.name}**: {loc.description}"
                if loc.lore:
                    line += f" — {loc.lore[:200]}"
                parts.append(line)
                for feat in loc.features:
                    parts.append(
                        f"  - *{feat.name}* ({feat.feature_type}): {feat.description}"
                    )

        if items:
            parts.append("\n### World Items (Known Artifacts & Objects)")
            for item in items:
                line = f"- **{item.name}**: {item.description}"
                if item.lore:
                    line += f" — {item.lore[:200]}"
                if item.rarity:
                    line += f" [{item.rarity}]"
                parts.append(line)
                for prop in item.properties:
                    parts.append(
                        f"  - *{prop.name}* ({prop.property_type}): {prop.description}"
                    )

        if not parts:
            return ""

        return "\n".join(parts)

    # ── Convenience ───────────────────────────────────────────

    @staticmethod
    def extract_keywords(text: str) -> list[str]:
        """
        Extract meaningful keywords from arbitrary text.

        Useful for callers that need to derive context_keywords
        from a title, agenda, or topic string.
        """
        tokens = _tokenise(text)
        return sorted(tokens)

    # ── Location Loading ───────────────────────────────────────

    @staticmethod
    def _load_active_locations(
        locations_dir: Path | None = None,
    ) -> list[Any]:
        """Load all active locations from disk.

        Returns an empty list if the locations module is not available
        or no active locations exist.
        """
        try:
            from core.locations import LocationManager
            mgr = LocationManager(locations_dir=locations_dir)
            return mgr.list_locations(status="active")
        except Exception:
            return []

    # ── Item Loading ────────────────────────────────────────────

    @staticmethod
    def _load_active_items(
        items_dir: Path | None = None,
    ) -> list[Any]:
        """Load all active items from disk.

        Returns an empty list if the items module is not available
        or no active items exist.
        """
        try:
            from core.items import ItemManager
            mgr = ItemManager(items_dir=items_dir)
            return mgr.list_items(status="active")
        except Exception:
            return []

    # ── LLM-Based Summarization ────────────────────────────────

    @staticmethod
    def _get_summarization_config() -> tuple[str, str]:
        """
        Resolve the summarization LLM provider and model from env
        vars, falling back to defaults from settings.
        """
        provider = (
            os.environ.get(SUMMARIZATION_PROVIDER_ENV, "").strip()
            or DEFAULT_SUMMARIZATION_PROVIDER
        )
        model = (
            os.environ.get(SUMMARIZATION_MODEL_ENV, "").strip()
            or DEFAULT_SUMMARIZATION_MODEL
        )
        return provider, model

    @staticmethod
    async def summarize_sessions_llm(
        agent_mem: AgentMemory,
        keep_recent: int | None = None,
    ) -> list[MemoryEntry]:
        """
        Summarize old sessions using an LLM call.

        Groups eligible old sessions, sends each group's content to
        the configured summarization provider/model, and writes the
        condensed summary back as a new MemoryEntry in the
        summarized log.

        Returns the list of newly-created summary entries.
        """
        if keep_recent is None:
            keep_recent = MEMORY_SUMMARIZATION_KEEP_RECENT

        session_ids = agent_mem.get_unique_session_ids()
        if len(session_ids) < MEMORY_SUMMARIZATION_SESSION_THRESHOLD:
            return []

        groups = agent_mem.get_sessions_needing_summary(
            keep_recent=keep_recent,
        )
        if not groups:
            return []

        provider, model = MemoryInfluence._get_summarization_config()
        summaries: list[MemoryEntry] = []

        for group in groups:
            combined = "\n".join(
                f"[{e.event_type}] {e.content}" for e in group
            )
            session_id = group[0].session_id

            prompt = (
                f"Summarize the following session memories from session "
                f"{session_id} into a single concise paragraph.  "
                f"Preserve key events, decisions, and emotional tone.  "
                f"Do not add anything not present in the original.\n\n"
                f"{combined}"
            )

            try:
                summary_text = await MemoryInfluence._call_llm(
                    provider, model, prompt,
                )
            except Exception as exc:
                logger.warning(
                    "Summarization LLM call failed for session %s: %s",
                    session_id, exc,
                )
                continue

            summary_entry = MemoryEntry.create(
                session_id=session_id,
                event_type="summary",
                content=summary_text.strip(),
                source="summarization",
                metadata={"original_count": len(group)},
            )
            agent_mem.write_summarized_entry(summary_entry)
            summaries.append(summary_entry)

        return summaries

    @staticmethod
    async def _call_llm(
        provider: str, model: str, prompt: str,
    ) -> str:
        """
        Make a one-shot LLM call for summarization.

        Uses the same API client infrastructure as the rest of
        Jericho but with an ephemeral CouncilMember stub.
        """
        from core.api_client import APIClient, ChatMessage
        from core.registry import CouncilMember

        stub = CouncilMember(
            name="_summarizer",
            role="Memory Summarizer",
            description="Internal memory summarization agent",
            api_provider=provider,
            model=model,
            system_prompt=(
                "You are a precise memory summarizer. "
                "Condense the given session memories into a single "
                "concise paragraph preserving key events, decisions, "
                "and emotional tone. Do not fabricate details."
            ),
        )
        message = ChatMessage(role="user", content=prompt)

        async with APIClient() as client:
            response = await client.chat(
                stub, [message],
                temperature=0.3,
                max_tokens=512,
            )
        return response.content

    # ── Contested Memory Generation ──────────────────────────

    @staticmethod
    async def maybe_generate_contested_memory(
        agent_mem: AgentMemory,
        member_name: str,
        entry: MemoryEntry,
        *,
        probability: float | None = None,
    ) -> dict[str, Any] | None:
        """
        Probabilistically generate a contested (divergent) memory.

        With the configured probability, calls the LLM to produce
        an alternative recollection of the given memory entry from
        the perspective of the named member.

        Returns the contested record if generated, None otherwise.
        """
        prob = probability if probability is not None else CONTESTED_MEMORY_PROBABILITY
        if prob <= 0 or random.random() > prob:
            return None

        event_id = f"{entry.session_id}:{entry.timestamp}"
        provider, model = MemoryInfluence._get_summarization_config()

        prompt = (
            f"You are {member_name}. Briefly restate the following event "
            f"from your own subjective perspective. Your recollection "
            f"may differ slightly from the original — you might "
            f"emphasize different details, misremember a minor fact, "
            f"or reinterpret the emotional tone. Keep it to 1-2 "
            f"sentences.\n\nOriginal event: {entry.content}"
        )

        try:
            alt_text = await MemoryInfluence._call_llm(
                provider, model, prompt,
            )
        except Exception as exc:
            logger.warning(
                "Contested memory LLM call failed: %s", exc,
            )
            return None

        return agent_mem.record_contested_memory(
            event_id=event_id,
            member_name=member_name,
            content=alt_text.strip(),
            original_content=entry.content,
        )

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"MemoryInfluence("
            f"memory_limit={self._memory_limit}, "
            f"belief_limit={self._belief_limit}, "
            f"min_relevance={self._min_relevance}, "
            f"belief_boost={self._belief_boost}, "
            f"decay={self._decay_enabled}, "
            f"summarization={self._summarization_enabled}, "
            f"cache={self._cache_enabled}, "
            f"cache_ttl={self._cache_ttl})"
        )
