"""
Jericho — Reputation Auto-Recording Hooks (F-070)

Thin observer functions that record reputation events at key action points.
Each hook is designed to be called from route endpoints after a successful
action.  All hooks swallow exceptions to ensure reputation recording never
breaks primary workflows.

Usage from a route::

    from core.reputation_hooks import on_vote_cast
    on_vote_cast("Sage", "P-0001", "for")
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.items import GiftRecord
    from core.voting import VoteTally

log = logging.getLogger(__name__)


def _get_mgr():
    """Lazy import to avoid circular imports at module load time."""
    from core.manager_cache import get_reputation_manager
    return get_reputation_manager()


# ── Vote Cast ────────────────────────────────────────────────


def on_vote_cast(voter: str, proposal_id: str, choice: str) -> None:
    """Record a reputation event when a council member casts a vote.

    Args:
        voter: Council member name (e.g. "Sage").
        proposal_id: The proposal being voted on (e.g. "P-0001").
        choice: The vote choice ("for", "against", "abstain").
    """
    try:
        mgr = _get_mgr()
        mgr.record_event(
            f"member:{voter}",
            "vote_cast",
            reason=f"Voted '{choice}' on {proposal_id}",
            source_id=proposal_id,
        )
    except Exception:
        log.debug("reputation_hooks.on_vote_cast failed", exc_info=True)


# ── Proposal Authored ────────────────────────────────────────


def on_proposal_authored(author: str, proposal_id: str) -> None:
    """Record a reputation event when a proposal is created.

    Args:
        author: The proposal author name (e.g. "Sage").
        proposal_id: The new proposal ID (e.g. "P-0012").
    """
    try:
        mgr = _get_mgr()
        mgr.record_event(
            f"member:{author}",
            "proposal_authored",
            reason=f"Authored proposal {proposal_id}",
            source_id=proposal_id,
        )
    except Exception:
        log.debug("reputation_hooks.on_proposal_authored failed", exc_info=True)


# ── Proposal Decided ─────────────────────────────────────────


def on_proposal_decided(
    proposal_id: str,
    tally: VoteTally,
    author: str,
    *,
    fast_tracked: bool = False,
) -> None:
    """Record a reputation event when a proposal vote closes.

    Records ``proposal_approved`` or ``proposal_rejected`` for the
    proposal's author.  Fast-tracked proposals that are rejected incur
    an enhanced penalty (F-071).

    Args:
        proposal_id: The proposal that was decided.
        tally: The computed VoteTally with an ``approved`` bool.
        author: The proposal author who gains/loses reputation.
        fast_tracked: If True and rejected, apply enhanced penalty.
    """
    try:
        mgr = _get_mgr()
        if tally.approved:
            mgr.record_event(
                f"member:{author}",
                "proposal_approved",
                reason=f"Proposal {proposal_id} approved",
                source_id=proposal_id,
            )
        else:
            # F-071: Enhanced penalty for rejected fast-tracked proposals
            penalty_points = None  # use default (-2)
            reason_suffix = ""
            if fast_tracked:
                from core.reputation_effects import get_fast_track_rejection_penalty
                penalty_points = get_fast_track_rejection_penalty()
                reason_suffix = " (fast-tracked — enhanced penalty)"
            mgr.record_event(
                f"member:{author}",
                "proposal_rejected",
                points=penalty_points,
                reason=f"Proposal {proposal_id} rejected{reason_suffix}",
                source_id=proposal_id,
            )
    except Exception:
        log.debug("reputation_hooks.on_proposal_decided failed", exc_info=True)


# ── Gift Given / Received ────────────────────────────────────


def on_gift_given(gift: GiftRecord) -> None:
    """Record reputation events when an item is gifted.

    Creates two events:
    - ``gift_given`` for the sender
    - ``gift_received`` for the receiver

    Args:
        gift: The GiftRecord from ItemManager.gift_item().
    """
    try:
        mgr = _get_mgr()
        from_type = gift.from_owner.get("type", "user")
        from_name = gift.from_owner.get("name", "unknown")
        to_type = gift.to_owner.get("type", "user")
        to_name = gift.to_owner.get("name", "unknown")

        # Map owner type to entity prefix
        prefix_map = {
            "council_member": "member",
            "character": "character",
            "user": "member",
        }

        sender_entity = f"{prefix_map.get(from_type, 'member')}:{from_name}"
        receiver_entity = f"{prefix_map.get(to_type, 'member')}:{to_name}"

        mgr.record_event(
            sender_entity,
            "gift_given",
            reason=f"Gifted {gift.item_name} to {to_name}",
            source_id=gift.item_id,
        )
        mgr.record_event(
            receiver_entity,
            "gift_received",
            reason=f"Received {gift.item_name} from {from_name}",
            source_id=gift.item_id,
        )
    except Exception:
        log.debug("reputation_hooks.on_gift_given failed", exc_info=True)


# ── Discussion Participated ──────────────────────────────────


def on_discussion_participated(
    participants: list[str],
    proposal_id: str,
) -> None:
    """Record reputation events when a discussion round completes.

    One ``discussion_participated`` event per participant.

    Args:
        participants: List of council member names.
        proposal_id: The proposal being discussed.
    """
    try:
        mgr = _get_mgr()
        for name in participants:
            try:
                mgr.record_event(
                    f"member:{name}",
                    "discussion_participated",
                    reason=f"Participated in discussion on {proposal_id}",
                    source_id=proposal_id,
                )
            except Exception:
                log.debug(
                    "reputation_hooks.on_discussion_participated failed for %s",
                    name, exc_info=True,
                )
    except Exception:
        log.debug("reputation_hooks.on_discussion_participated failed", exc_info=True)


# ── Session Participated ─────────────────────────────────────


def on_session_participated(
    participants: list[str],
    session_id: str,
) -> None:
    """Record reputation events when a council session round completes.

    One ``session_participated`` event per participant.

    Args:
        participants: List of council member names.
        session_id: The council session ID.
    """
    try:
        mgr = _get_mgr()
        for name in participants:
            try:
                mgr.record_event(
                    f"member:{name}",
                    "session_participated",
                    reason=f"Participated in council session {session_id}",
                    source_id=session_id,
                )
            except Exception:
                log.debug(
                    "reputation_hooks.on_session_participated failed for %s",
                    name, exc_info=True,
                )
    except Exception:
        log.debug("reputation_hooks.on_session_participated failed", exc_info=True)


# ── Purchase Made ────────────────────────────────────────────


def on_purchase(
    buyer_entity_id: str,
    item_name: str,
    store_name: str,
    price_gold: int = 0,
) -> None:
    """Record a reputation event when a store purchase is completed.

    Args:
        buyer_entity_id: Entity ID of the buyer (e.g. "member:Sage").
        item_name: Name of the purchased item.
        store_name: Name of the store.
        price_gold: Gold amount paid (for description only).
    """
    if not buyer_entity_id:
        return
    try:
        mgr = _get_mgr()
        mgr.record_event(
            buyer_entity_id,
            "purchase_made",
            reason=f"Purchased {item_name} from {store_name} for {price_gold}g",
            source_id=store_name,
        )
    except Exception:
        log.debug("reputation_hooks.on_purchase failed", exc_info=True)
