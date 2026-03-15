"""
Jericho — Memory Influence (F-018)

Memories affect agent responses via context injection with relevance
scoring.  The engine scores and selects the most relevant memories
and beliefs for a given conversational context, formats them as
markdown, and returns text suitable for injection into any prompt
builder.

Scoring uses keyword-based Jaccard similarity.  Core beliefs receive
a configurable boost multiplier because they represent persistent
stance rather than ephemeral session events.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.settings import (
    MEMORIES_DIR,
    MEMORY_INFLUENCE_BELIEF_BOOST,
    MEMORY_INFLUENCE_MAX_BELIEFS,
    MEMORY_INFLUENCE_MAX_MEMORIES,
    MEMORY_INFLUENCE_MIN_RELEVANCE,
)
from core.memory import AgentMemory, CoreBelief, MemoryEntry


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

    # ── Scoring ───────────────────────────────────────────────

    def score_memories(
        self,
        entries: list[MemoryEntry],
        context_keywords: list[str],
    ) -> list[ScoredMemory]:
        """
        Score memory entries against context keywords.

        Returns a list of ScoredMemory objects sorted by descending
        relevance, filtered to those above min_relevance, limited
        to memory_limit results.
        """
        context_tokens = _tokenise(" ".join(context_keywords))
        scored: list[ScoredMemory] = []

        for entry in entries:
            entry_tokens = _tokenise(
                f"{entry.content} {entry.event_type} {entry.source}"
            )
            score = _jaccard(context_tokens, entry_tokens)

            if score >= self._min_relevance:
                # Build human-readable reason
                overlap = context_tokens & entry_tokens
                reason = (
                    f"Matched keywords: {', '.join(sorted(overlap))}"
                    if overlap
                    else "General relevance"
                )
                scored.append(
                    ScoredMemory(
                        entry=entry,
                        relevance_score=round(score, 4),
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

        Beliefs receive a boost multiplier since they represent
        persistent stance.  Returns scored beliefs sorted by
        descending relevance, filtered and limited.
        """
        context_tokens = _tokenise(" ".join(context_keywords))
        scored: list[ScoredBelief] = []

        for belief in beliefs:
            belief_tokens = _tokenise(f"{belief.topic} {belief.content}")
            raw_score = _jaccard(context_tokens, belief_tokens)
            boosted = min(raw_score * self._belief_boost, 1.0)

            if boosted >= self._min_relevance:
                overlap = context_tokens & belief_tokens
                reason = (
                    f"Belief on '{belief.topic}' matched: "
                    f"{', '.join(sorted(overlap))}"
                    if overlap
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

    def build_context(
        self,
        member_name: str,
        context_keywords: list[str],
        *,
        memories_dir: Path | None = None,
    ) -> MemoryContext:
        """
        Build a complete MemoryContext for a member.

        Loads the member's core beliefs and recent session memories,
        scores them against the given context keywords, and returns
        a MemoryContext with pre-formatted text.

        Args:
            member_name: Council member name (case-insensitive).
            context_keywords: Words/phrases describing the current topic.
            memories_dir: Override the memories directory (for testing).

        Returns:
            MemoryContext with scored beliefs, memories, and formatted text.
        """
        base_dir = memories_dir or self._memories_dir
        agent_mem = AgentMemory(member_name, memories_dir=base_dir)

        # Load raw data
        beliefs = agent_mem.read_core_beliefs()
        recent = agent_mem.get_recent_memories(limit=50)  # over-fetch, then score

        # Score against context
        scored_beliefs = self.score_beliefs(beliefs, context_keywords)
        scored_memories = self.score_memories(recent, context_keywords)

        # Format for prompt injection
        formatted = self.format_for_prompt(scored_beliefs, scored_memories)

        return MemoryContext(
            member_name=member_name.strip().lower(),
            beliefs=scored_beliefs,
            memories=scored_memories,
            formatted_text=formatted,
        )

    # ── Formatting ────────────────────────────────────────────

    @staticmethod
    def format_for_prompt(
        beliefs: list[ScoredBelief],
        memories: list[ScoredMemory],
    ) -> str:
        """
        Render scored beliefs and memories as markdown for prompt
        injection.

        Returns an empty string if there is nothing to inject.
        """
        parts: list[str] = []

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

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"MemoryInfluence("
            f"memory_limit={self._memory_limit}, "
            f"belief_limit={self._belief_limit}, "
            f"min_relevance={self._min_relevance}, "
            f"belief_boost={self._belief_boost})"
        )
