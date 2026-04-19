"""
Jericho — Reputation Gameplay Effects (F-071)

Pure functions that translate reputation tiers into gameplay modifiers.
Every function checks its feature toggle and returns a neutral value when
the toggle is disabled — callers never need to check toggles themselves.

Integration points:
- ``core/routes/proposals.py``: vote weight, fast-track, disgraced restriction
- ``core/routes/stores.py``: price modifier, disgraced restriction
"""

from __future__ import annotations

import logging

from config.settings import (
    REPUTATION_FAST_TRACK_REJECTION_PENALTY,
    REPUTATION_FAST_TRACK_TIERS,
    REPUTATION_FAST_TRACK_ENABLED,
    REPUTATION_PRICE_MODIFIERS,
    REPUTATION_RESTRICTIONS_ENABLED,
    REPUTATION_STORE_PRICES_ENABLED,
    REPUTATION_VOTE_WEIGHT_ENABLED,
    REPUTATION_VOTE_WEIGHT_MODIFIERS,
)

log = logging.getLogger(__name__)


# ─── Vote Weight ──────────────────────────────────────────────


def get_vote_weight_modifier(tier: str) -> float:
    """Return a multiplier (0.90–1.10) for vote weight based on tier.

    When ``REPUTATION_VOTE_WEIGHT_ENABLED`` is False, always returns 1.0.
    """
    if not REPUTATION_VOTE_WEIGHT_ENABLED:
        return 1.0
    return REPUTATION_VOTE_WEIGHT_MODIFIERS.get(tier, 1.0)


# ─── Store Prices ─────────────────────────────────────────────


def get_price_modifier(tier: str) -> float:
    """Return a multiplier (0.85–1.15) for store prices based on tier.

    When ``REPUTATION_STORE_PRICES_ENABLED`` is False, always returns 1.0.
    """
    if not REPUTATION_STORE_PRICES_ENABLED:
        return 1.0
    return REPUTATION_PRICE_MODIFIERS.get(tier, 1.0)


def apply_price_modifier(
    base_gold: int,
    base_silver: int,
    base_bronze: int,
    tier: str,
) -> tuple[int, int, int]:
    """Apply reputation price modifier to a set of prices.

    Returns adjusted ``(gold, silver, bronze)`` as integers (floored).
    Prices never go below 0.  When disabled, returns original prices.
    """
    modifier = get_price_modifier(tier)
    if modifier == 1.0:
        return base_gold, base_silver, base_bronze

    adjusted_gold = max(0, int(base_gold * modifier))
    adjusted_silver = max(0, int(base_silver * modifier))
    adjusted_bronze = max(0, int(base_bronze * modifier))
    return adjusted_gold, adjusted_silver, adjusted_bronze


# ─── Fast-Track ───────────────────────────────────────────────


def can_fast_track(tier: str) -> bool:
    """Return True if this tier qualifies for proposal fast-tracking.

    When ``REPUTATION_FAST_TRACK_ENABLED`` is False, always returns False.
    """
    if not REPUTATION_FAST_TRACK_ENABLED:
        return False
    return tier in REPUTATION_FAST_TRACK_TIERS


def get_fast_track_rejection_penalty() -> int:
    """Return the reputation penalty for rejected fast-tracked proposals.

    This overrides the default ``proposal_rejected`` penalty of -2.
    """
    return REPUTATION_FAST_TRACK_REJECTION_PENALTY


# ─── Restrictions (Disgraced) ─────────────────────────────────


def can_author_proposals(tier: str) -> bool:
    """Return False if the entity is disgraced and restrictions are active.

    When ``REPUTATION_RESTRICTIONS_ENABLED`` is False, always returns True.
    """
    if not REPUTATION_RESTRICTIONS_ENABLED:
        return True
    return tier != "disgraced"


def can_open_stores(tier: str) -> bool:
    """Return False if the entity is disgraced and restrictions are active.

    When ``REPUTATION_RESTRICTIONS_ENABLED`` is False, always returns True.
    """
    if not REPUTATION_RESTRICTIONS_ENABLED:
        return True
    return tier != "disgraced"


# ─── Tier Lookup Helper ──────────────────────────────────────


def get_entity_tier(
    entity_id: str,
    reputation_manager: object | None = None,
) -> str:
    """Look up the current reputation tier for an entity.

    Returns ``"neutral"`` if the reputation manager is unavailable or
    the entity has no recorded events.  Never raises.

    Args:
        entity_id: e.g. ``"member:Sage"`` or ``"character:CH-0001"``
        reputation_manager: A ``ReputationManager`` instance (optional).
            If ``None``, attempts to load via ``manager_cache``.
    """
    try:
        if reputation_manager is None:
            from core.manager_cache import get_reputation_manager
            reputation_manager = get_reputation_manager()
        score = reputation_manager.get_score(entity_id)  # type: ignore[union-attr]
        return score.tier
    except Exception:
        log.debug(
            "Could not resolve reputation tier for %s, defaulting to neutral",
            entity_id,
            exc_info=True,
        )
        return "neutral"
