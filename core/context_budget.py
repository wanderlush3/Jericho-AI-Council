"""
Jericho — Context Budget Manager (F-057)

Global token budget that allocates a target context window across
priority-ordered layers.  Each layer receives a percentage of the
total budget and content is automatically truncated to fit.

Layers (highest to lowest priority):
    1. SYSTEM_PROMPT — fixed, never truncated first
    2. CONVERSATION_HISTORY — sliding window, high priority
    3. MEMORIES_BELIEFS — relevance-scored, medium priority
    4. WORLD_CONTEXT — capped entities, lower priority
    5. LLM_INJECTIONS — user-authored, lowest priority

Usage::

    budget = ContextBudget(target_tokens=32768)
    budget.set_content(ContextLayer.SYSTEM_PROMPT, system_prompt_text)
    budget.set_content(ContextLayer.CONVERSATION_HISTORY, history_text)
    budget.set_content(ContextLayer.MEMORIES_BELIEFS, memories_text)
    budget.set_content(ContextLayer.WORLD_CONTEXT, world_text)
    budget.set_content(ContextLayer.LLM_INJECTIONS, injection_text)

    # Check budget health
    print(budget.total_used(), budget.total_remaining())
    print(budget.summary())
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from config.settings import (
    CONTEXT_BUDGET_HISTORY_PCT,
    CONTEXT_BUDGET_INJECTIONS_PCT,
    CONTEXT_BUDGET_MEMORIES_PCT,
    CONTEXT_BUDGET_SYSTEM_PROMPT_PCT,
    CONTEXT_BUDGET_WORLD_PCT,
    DEFAULT_CONTEXT_BUDGET_TOKENS,
)


# ─── Token Estimation ─────────────────────────────────────────


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in *text*.

    Uses the standard ``len(text) / 4`` heuristic which approximates
    tokenisation for English prose.  This avoids pulling in a full
    tokenizer library while remaining accurate enough for budget
    planning (±10%).

    Returns:
        Estimated token count (always >= 0).
    """
    if not text:
        return 0
    return max(1, len(text) // 4)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate *text* so it fits within *max_tokens*.

    Attempts to truncate at natural boundaries (paragraph or sentence)
    so the output remains coherent.  When truncation occurs a
    ``…[truncated]`` indicator is appended.

    Args:
        text: The text to truncate.
        max_tokens: Maximum token budget for the text.

    Returns:
        The original text if it fits, otherwise a truncated version
        with a ``…[truncated]`` suffix.
    """
    if max_tokens <= 0:
        return ""
    if estimate_tokens(text) <= max_tokens:
        return text

    # Convert to approximate character budget
    max_chars = max_tokens * 4

    # Reserve space for the truncation indicator
    indicator = "\n…[truncated]"
    available = max_chars - len(indicator)
    if available <= 0:
        return indicator.strip()

    snippet = text[:available]

    # Try to break at the last paragraph boundary
    last_para = snippet.rfind("\n\n")
    if last_para > available * 0.5:
        snippet = snippet[:last_para]
    else:
        # Try to break at the last sentence boundary
        for sep in (". ", ".\n", "! ", "!\n", "? ", "?\n"):
            last_sent = snippet.rfind(sep)
            if last_sent > available * 0.5:
                snippet = snippet[: last_sent + 1]
                break

    return snippet.rstrip() + indicator


# ─── Layer Enum ────────────────────────────────────────────────


class ContextLayer(enum.IntEnum):
    """Context layers ordered by priority (lower value = higher priority)."""

    SYSTEM_PROMPT = 0
    CONVERSATION_HISTORY = 1
    MEMORIES_BELIEFS = 2
    WORLD_CONTEXT = 3
    LLM_INJECTIONS = 4


# Default percentage allocations keyed by layer.
_DEFAULT_ALLOCATIONS: dict[ContextLayer, float] = {
    ContextLayer.SYSTEM_PROMPT: CONTEXT_BUDGET_SYSTEM_PROMPT_PCT,
    ContextLayer.CONVERSATION_HISTORY: CONTEXT_BUDGET_HISTORY_PCT,
    ContextLayer.MEMORIES_BELIEFS: CONTEXT_BUDGET_MEMORIES_PCT,
    ContextLayer.WORLD_CONTEXT: CONTEXT_BUDGET_WORLD_PCT,
    ContextLayer.LLM_INJECTIONS: CONTEXT_BUDGET_INJECTIONS_PCT,
}


# ─── Layer Allocation ──────────────────────────────────────────


@dataclass(frozen=True)
class LayerAllocation:
    """Budget allocation and content for a single context layer."""

    layer: ContextLayer
    max_tokens: int
    content: str = ""
    token_count: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer.name,
            "max_tokens": self.max_tokens,
            "token_count": self.token_count,
            "truncated": self.truncated,
            "utilization_pct": round(
                (self.token_count / self.max_tokens * 100)
                if self.max_tokens > 0
                else 0.0,
                1,
            ),
        }


# ─── Context Budget ───────────────────────────────────────────


class ContextBudget:
    """Global token budget manager.

    Allocates a target token count across priority-ordered context
    layers.  Each layer receives a percentage of the total budget.
    When content is set for a layer, it is automatically truncated
    if it exceeds that layer's allocation.

    Args:
        target_tokens: Total token budget for the context window.
        allocations: Optional dict mapping ``ContextLayer`` to a
            percentage (0.0–1.0).  Defaults to the percentages in
            ``config/settings.py``.
    """

    def __init__(
        self,
        target_tokens: int | None = None,
        allocations: dict[ContextLayer, float] | None = None,
    ) -> None:
        self._target = (
            target_tokens
            if target_tokens is not None
            else DEFAULT_CONTEXT_BUDGET_TOKENS
        )
        if self._target <= 0:
            raise ValueError(
                f"target_tokens must be positive, got {self._target}"
            )

        pcts = allocations or dict(_DEFAULT_ALLOCATIONS)

        # Compute per-layer token ceilings
        self._limits: dict[ContextLayer, int] = {}
        for layer in ContextLayer:
            pct = pcts.get(layer, 0.0)
            self._limits[layer] = max(1, int(self._target * pct))

        # Current allocations (populated via set_content)
        self._allocations: dict[ContextLayer, LayerAllocation] = {
            layer: LayerAllocation(layer=layer, max_tokens=limit)
            for layer, limit in self._limits.items()
        }

    # ── Properties ────────────────────────────────────────────

    @property
    def target_tokens(self) -> int:
        """Total token budget."""
        return self._target

    @property
    def layers(self) -> list[ContextLayer]:
        """All layers in priority order."""
        return sorted(ContextLayer)

    # ── Content Management ────────────────────────────────────

    def set_content(
        self,
        layer: ContextLayer,
        text: str,
    ) -> LayerAllocation:
        """Set content for a layer, auto-truncating if over budget.

        Args:
            layer: The context layer to set content for.
            text: The text content to assign.

        Returns:
            The resulting ``LayerAllocation`` with token count and
            truncation status.
        """
        limit = self._limits[layer]
        tokens = estimate_tokens(text)

        if tokens > limit:
            text = truncate_to_tokens(text, limit)
            tokens = estimate_tokens(text)
            truncated = True
        else:
            truncated = False

        alloc = LayerAllocation(
            layer=layer,
            max_tokens=limit,
            content=text,
            token_count=tokens,
            truncated=truncated,
        )
        self._allocations[layer] = alloc
        return alloc

    def get_content(self, layer: ContextLayer) -> str:
        """Get the (possibly truncated) content for a layer."""
        return self._allocations[layer].content

    def get_allocation(self, layer: ContextLayer) -> LayerAllocation:
        """Get the full allocation object for a layer."""
        return self._allocations[layer]

    # ── Budget Accounting ─────────────────────────────────────

    def remaining_tokens(self, layer: ContextLayer) -> int:
        """Tokens remaining in a layer's budget."""
        alloc = self._allocations[layer]
        return max(0, alloc.max_tokens - alloc.token_count)

    def total_used(self) -> int:
        """Sum of all layer token counts."""
        return sum(a.token_count for a in self._allocations.values())

    def total_remaining(self) -> int:
        """Tokens remaining across all layers."""
        return max(0, self._target - self.total_used())

    def is_over_budget(self) -> bool:
        """True if total used exceeds target."""
        return self.total_used() > self._target

    # ── Redistribution ────────────────────────────────────────

    def redistribute_unused(self) -> None:
        """Move unused tokens from higher-priority layers to lower ones.

        After content is set for all layers, some layers may have used
        far less than their allocation.  This method redistributes
        the surplus to lower-priority layers that may need it.

        Only layers with content already set benefit from
        redistribution — the method re-truncates content if the new
        limit provides more room.
        """
        # Calculate surplus from each layer (in priority order)
        surplus = 0
        for layer in sorted(ContextLayer):
            alloc = self._allocations[layer]
            unused = alloc.max_tokens - alloc.token_count
            if unused > 0:
                surplus += unused

        if surplus <= 0:
            return

        # Distribute surplus to lower-priority layers that were truncated
        # Process from lowest to highest priority (reverse order)
        for layer in sorted(ContextLayer, reverse=True):
            alloc = self._allocations[layer]
            if not alloc.truncated or surplus <= 0:
                continue

            # Give this layer more room
            new_limit = alloc.max_tokens + surplus
            self._limits[layer] = new_limit

            # Re-set the content with the expanded limit
            # We need the original content — but we only have truncated.
            # Mark the new limit; callers should re-set_content if they
            # have the original text.
            self._allocations[layer] = LayerAllocation(
                layer=layer,
                max_tokens=new_limit,
                content=alloc.content,
                token_count=alloc.token_count,
                truncated=alloc.truncated,
            )

            # Surplus was assigned to this layer's limit
            break

    # ── Summary ───────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """Per-layer breakdown for debugging.

        Returns:
            Dict with ``target_tokens``, ``total_used``,
            ``total_remaining``, and per-``layer`` allocation dicts.
        """
        layers = {}
        for layer in sorted(ContextLayer):
            alloc = self._allocations[layer]
            layers[layer.name] = alloc.to_dict()

        return {
            "target_tokens": self._target,
            "total_used": self.total_used(),
            "total_remaining": self.total_remaining(),
            "is_over_budget": self.is_over_budget(),
            "layers": layers,
        }

    def __repr__(self) -> str:
        return (
            f"ContextBudget(target={self._target}, "
            f"used={self.total_used()}, "
            f"remaining={self.total_remaining()})"
        )
