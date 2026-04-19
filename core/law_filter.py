"""
Jericho — Conditional Law Injection (F-060)

Scores laws against conversational context keywords using Jaccard
similarity and only injects laws whose relevance score meets a
configurable threshold.  This prevents irrelevant laws (e.g. taxation
rules) from wasting tokens in unrelated conversations (e.g. character
backstory discussion).

The scorer reuses the tokenisation and Jaccard utilities from
``memory_influence.py`` for consistency.

Usage::

    from core.law_filter import LawFilter
    lf = LawFilter()
    relevant = lf.filter_laws(all_active_laws, ["trade", "economy"])
    # → only laws whose title/description/body/tags match the keywords
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from config.settings import (
    LAW_RELEVANCE_ENABLED,
    LAW_RELEVANCE_MIN_SCORE,
)
from core.memory_influence import _jaccard, _tokenise

log = logging.getLogger(__name__)


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ScoredLaw:
    """A Law annotated with a relevance score."""

    law: Any  # core.laws.Law — kept as Any to avoid circular import
    relevance_score: float = 0.0
    matched_keywords: frozenset[str] = field(default_factory=frozenset)

    def to_dict(self) -> dict[str, Any]:
        return {
            "law_id": self.law.id,
            "title": self.law.title,
            "relevance_score": self.relevance_score,
            "matched_keywords": sorted(self.matched_keywords),
        }


# ─── Law Filter ────────────────────────────────────────────────


class LawFilter:
    """
    Scores and filters laws against conversational context keywords.

    Uses Jaccard similarity between the context keywords and a
    composite text derived from each law's title, description, body,
    and tags.  Laws scoring below ``min_score`` are discarded.

    When ``enabled`` is False, all laws pass through unfiltered
    (backward-compatible behaviour).

    Args:
        enabled: Toggle filtering on/off.  Defaults to
            ``LAW_RELEVANCE_ENABLED`` from settings.
        min_score: Minimum Jaccard score to include a law.
            Defaults to ``LAW_RELEVANCE_MIN_SCORE`` from settings.
    """

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        min_score: float | None = None,
    ) -> None:
        self._enabled = (
            enabled if enabled is not None else LAW_RELEVANCE_ENABLED
        )
        self._min_score = (
            min_score if min_score is not None else LAW_RELEVANCE_MIN_SCORE
        )

    # ── Properties ────────────────────────────────────────────

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def min_score(self) -> float:
        return self._min_score

    # ── Scoring ───────────────────────────────────────────────

    @staticmethod
    def _law_text(law: Any) -> str:
        """Build a composite text from a law's searchable fields."""
        parts: list[str] = [
            law.title or "",
            law.description or "",
            getattr(law, "body", "") or "",
        ]
        tags = getattr(law, "tags", []) or []
        parts.extend(tags)
        return " ".join(parts)

    def score_law(
        self,
        law: Any,
        context_tokens: set[str],
    ) -> ScoredLaw:
        """
        Score a single law against pre-tokenised context keywords.

        Returns a ``ScoredLaw`` with the Jaccard score and the set
        of overlapping keywords.
        """
        law_text = self._law_text(law)
        law_tokens = _tokenise(law_text)
        score = _jaccard(context_tokens, law_tokens)
        overlap = context_tokens & law_tokens
        return ScoredLaw(
            law=law,
            relevance_score=round(score, 4),
            matched_keywords=frozenset(overlap),
        )

    def filter_laws(
        self,
        laws: list[Any],
        context_keywords: list[str],
        *,
        limit: int | None = None,
    ) -> list[ScoredLaw]:
        """
        Score and filter laws against context keywords.

        When filtering is disabled, all laws are returned (scored but
        unfiltered) to maintain backward compatibility.

        Args:
            laws: List of ``Law`` objects to score.
            context_keywords: Words/phrases describing the current
                conversational context.
            limit: Maximum number of laws to return.  Applied after
                filtering and sorting.

        Returns:
            List of ``ScoredLaw`` objects sorted by descending
            relevance score.
        """
        if not laws:
            return []

        context_text = " ".join(context_keywords)
        context_tokens = _tokenise(context_text)

        # If no meaningful context keywords, return all laws
        # (no basis for filtering)
        if not context_tokens:
            scored = [
                ScoredLaw(law=law, relevance_score=0.0)
                for law in laws
            ]
            if limit is not None:
                scored = scored[:limit]
            return scored

        scored: list[ScoredLaw] = []
        for law in laws:
            sl = self.score_law(law, context_tokens)

            if self._enabled and sl.relevance_score < self._min_score:
                continue

            scored.append(sl)

        # Sort by score descending, then by law title for stability
        scored.sort(
            key=lambda s: (s.relevance_score, s.law.title),
            reverse=True,
        )

        if limit is not None:
            scored = scored[:limit]

        return scored

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"LawFilter(enabled={self._enabled}, "
            f"min_score={self._min_score})"
        )
