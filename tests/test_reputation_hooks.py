"""
Tests for Reputation Auto-Recording Hooks (F-070).

Covers:
- Each on_* hook records the correct event type, entity, reason, source_id
- Each on_* hook swallows exceptions without raising
- on_proposal_decided differentiates approved vs rejected
- on_gift_given records both gift_given and gift_received
- on_discussion_participated records one event per participant
- on_session_participated records one event per participant
- Integration tests via TestClient for proposal create and gift
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from core.reputation import ReputationManager
from core.reputation_hooks import (
    on_vote_cast,
    on_proposal_authored,
    on_proposal_decided,
    on_gift_given,
    on_discussion_participated,
    on_session_participated,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def rep_dir(tmp_path: Path) -> Path:
    d = tmp_path / "reputation"
    d.mkdir()
    return d


@pytest.fixture
def mgr(rep_dir: Path) -> ReputationManager:
    return ReputationManager(rep_dir, decay_enabled=False)


@pytest.fixture
def mock_mgr():
    """Return a mock ReputationManager."""
    m = MagicMock(spec=ReputationManager)
    return m


@pytest.fixture
def _patch_mgr(mock_mgr):
    """Patch _get_mgr to return our mock."""
    with patch("core.reputation_hooks._get_mgr", return_value=mock_mgr):
        yield


# ═══════════════════════════════════════════════════════════════
# TestOnVoteCast
# ═══════════════════════════════════════════════════════════════


class TestOnVoteCast:

    def test_records_correct_event(self, mock_mgr, _patch_mgr):
        on_vote_cast("Sage", "P-0001", "for")
        mock_mgr.record_event.assert_called_once_with(
            "member:Sage",
            "vote_cast",
            reason="Voted 'for' on P-0001",
            source_id="P-0001",
        )

    def test_includes_choice_in_reason(self, mock_mgr, _patch_mgr):
        on_vote_cast("Logic", "P-0002", "against")
        args = mock_mgr.record_event.call_args
        assert "against" in args.kwargs["reason"]

    def test_swallows_exceptions(self, mock_mgr, _patch_mgr):
        mock_mgr.record_event.side_effect = RuntimeError("db down")
        # Should not raise
        on_vote_cast("Sage", "P-0001", "for")


# ═══════════════════════════════════════════════════════════════
# TestOnProposalAuthored
# ═══════════════════════════════════════════════════════════════


class TestOnProposalAuthored:

    def test_records_correct_event(self, mock_mgr, _patch_mgr):
        on_proposal_authored("Sage", "P-0012")
        mock_mgr.record_event.assert_called_once_with(
            "member:Sage",
            "proposal_authored",
            reason="Authored proposal P-0012",
            source_id="P-0012",
        )

    def test_swallows_exceptions(self, mock_mgr, _patch_mgr):
        mock_mgr.record_event.side_effect = RuntimeError("boom")
        on_proposal_authored("Sage", "P-0012")


# ═══════════════════════════════════════════════════════════════
# TestOnProposalDecided
# ═══════════════════════════════════════════════════════════════


class TestOnProposalDecided:

    def _make_tally(self, approved: bool):
        tally = MagicMock()
        tally.approved = approved
        return tally

    def test_approved_records_proposal_approved(self, mock_mgr, _patch_mgr):
        tally = self._make_tally(approved=True)
        on_proposal_decided("P-0001", tally, "Sage")
        mock_mgr.record_event.assert_called_once_with(
            "member:Sage",
            "proposal_approved",
            reason="Proposal P-0001 approved",
            source_id="P-0001",
        )

    def test_rejected_records_proposal_rejected(self, mock_mgr, _patch_mgr):
        tally = self._make_tally(approved=False)
        on_proposal_decided("P-0001", tally, "Logic")
        mock_mgr.record_event.assert_called_once_with(
            "member:Logic",
            "proposal_rejected",
            points=None,
            reason="Proposal P-0001 rejected",
            source_id="P-0001",
        )

    def test_swallows_exceptions(self, mock_mgr, _patch_mgr):
        tally = self._make_tally(approved=True)
        mock_mgr.record_event.side_effect = RuntimeError("fail")
        on_proposal_decided("P-0001", tally, "Sage")


# ═══════════════════════════════════════════════════════════════
# TestOnGiftGiven
# ═══════════════════════════════════════════════════════════════


class TestOnGiftGiven:

    def _make_gift(self, from_type="council_member", to_type="council_member"):
        gift = MagicMock()
        gift.from_owner = {"name": "Sage", "type": from_type}
        gift.to_owner = {"name": "Logic", "type": to_type}
        gift.item_name = "Sword of Truth"
        gift.item_id = "ITEM-0001"
        return gift

    def test_records_both_gift_given_and_received(self, mock_mgr, _patch_mgr):
        gift = self._make_gift()
        on_gift_given(gift)

        assert mock_mgr.record_event.call_count == 2
        calls = mock_mgr.record_event.call_args_list

        # Gift given
        assert calls[0] == call(
            "member:Sage",
            "gift_given",
            reason="Gifted Sword of Truth to Logic",
            source_id="ITEM-0001",
        )
        # Gift received
        assert calls[1] == call(
            "member:Logic",
            "gift_received",
            reason="Received Sword of Truth from Sage",
            source_id="ITEM-0001",
        )

    def test_character_entity_prefix(self, mock_mgr, _patch_mgr):
        gift = self._make_gift(from_type="character", to_type="user")
        on_gift_given(gift)
        calls = mock_mgr.record_event.call_args_list
        # Character uses "character:" prefix
        assert calls[0].args[0] == "character:Sage"
        # User uses "member:" prefix
        assert calls[1].args[0] == "member:Logic"

    def test_swallows_exceptions(self, mock_mgr, _patch_mgr):
        gift = self._make_gift()
        mock_mgr.record_event.side_effect = RuntimeError("oops")
        on_gift_given(gift)


# ═══════════════════════════════════════════════════════════════
# TestOnDiscussionParticipated
# ═══════════════════════════════════════════════════════════════


class TestOnDiscussionParticipated:

    def test_records_one_event_per_participant(self, mock_mgr, _patch_mgr):
        on_discussion_participated(["Sage", "Logic", "Drift"], "P-0001")
        assert mock_mgr.record_event.call_count == 3

        for i, name in enumerate(["Sage", "Logic", "Drift"]):
            assert mock_mgr.record_event.call_args_list[i] == call(
                f"member:{name}",
                "discussion_participated",
                reason="Participated in discussion on P-0001",
                source_id="P-0001",
            )

    def test_empty_participants_no_calls(self, mock_mgr, _patch_mgr):
        on_discussion_participated([], "P-0001")
        mock_mgr.record_event.assert_not_called()

    def test_swallows_per_participant_exceptions(self, mock_mgr, _patch_mgr):
        mock_mgr.record_event.side_effect = RuntimeError("fail")
        # Should not raise even though each call fails
        on_discussion_participated(["Sage", "Logic"], "P-0001")

    def test_swallows_top_level_exception(self):
        with patch("core.reputation_hooks._get_mgr", side_effect=RuntimeError("no mgr")):
            on_discussion_participated(["Sage"], "P-0001")


# ═══════════════════════════════════════════════════════════════
# TestOnSessionParticipated
# ═══════════════════════════════════════════════════════════════


class TestOnSessionParticipated:

    def test_records_one_event_per_participant(self, mock_mgr, _patch_mgr):
        on_session_participated(["Sage", "Logic"], "CS-0001")
        assert mock_mgr.record_event.call_count == 2

        for i, name in enumerate(["Sage", "Logic"]):
            assert mock_mgr.record_event.call_args_list[i] == call(
                f"member:{name}",
                "session_participated",
                reason="Participated in council session CS-0001",
                source_id="CS-0001",
            )

    def test_empty_participants_no_calls(self, mock_mgr, _patch_mgr):
        on_session_participated([], "CS-0001")
        mock_mgr.record_event.assert_not_called()

    def test_swallows_exceptions(self, mock_mgr, _patch_mgr):
        mock_mgr.record_event.side_effect = RuntimeError("fail")
        on_session_participated(["Sage"], "CS-0001")

    def test_swallows_top_level_exception(self):
        with patch("core.reputation_hooks._get_mgr", side_effect=RuntimeError("no mgr")):
            on_session_participated(["Sage"], "CS-0001")


# ═══════════════════════════════════════════════════════════════
# TestHooksWithRealManager — integration with ReputationManager
# ═══════════════════════════════════════════════════════════════


class TestHooksWithRealManager:
    """Test hooks recording real events into a temp ReputationManager."""

    def test_vote_cast_creates_event(self, mgr, rep_dir):
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_vote_cast("Sage", "P-0001", "for")
        events = mgr.get_events("member:Sage")
        assert len(events) == 1
        assert events[0].event_type == "vote_cast"
        assert events[0].source_id == "P-0001"

    def test_proposal_authored_creates_event(self, mgr, rep_dir):
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_proposal_authored("Logic", "P-0010")
        events = mgr.get_events("member:Logic")
        assert len(events) == 1
        assert events[0].event_type == "proposal_authored"
        assert events[0].points == 10

    def test_proposal_decided_approved(self, mgr, rep_dir):
        tally = MagicMock()
        tally.approved = True
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_proposal_decided("P-0001", tally, "Sage")
        events = mgr.get_events("member:Sage")
        assert len(events) == 1
        assert events[0].event_type == "proposal_approved"
        assert events[0].points == 5

    def test_proposal_decided_rejected(self, mgr, rep_dir):
        tally = MagicMock()
        tally.approved = False
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_proposal_decided("P-0002", tally, "Logic")
        events = mgr.get_events("member:Logic")
        assert len(events) == 1
        assert events[0].event_type == "proposal_rejected"
        assert events[0].points == -2

    def test_gift_creates_two_events(self, mgr, rep_dir):
        gift = MagicMock()
        gift.from_owner = {"name": "Sage", "type": "council_member"}
        gift.to_owner = {"name": "Logic", "type": "council_member"}
        gift.item_name = "Golden Ring"
        gift.item_id = "ITEM-0005"
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_gift_given(gift)

        sender_events = mgr.get_events("member:Sage")
        assert len(sender_events) == 1
        assert sender_events[0].event_type == "gift_given"
        assert sender_events[0].points == 5

        receiver_events = mgr.get_events("member:Logic")
        assert len(receiver_events) == 1
        assert receiver_events[0].event_type == "gift_received"
        assert receiver_events[0].points == 1

    def test_discussion_creates_per_participant_events(self, mgr, rep_dir):
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_discussion_participated(["Sage", "Logic", "Drift"], "P-0001")

        for name in ["Sage", "Logic", "Drift"]:
            events = mgr.get_events(f"member:{name}")
            assert len(events) == 1
            assert events[0].event_type == "discussion_participated"
            assert events[0].points == 2

    def test_session_creates_per_participant_events(self, mgr, rep_dir):
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_session_participated(["Logic", "Drift"], "CS-0003")

        for name in ["Logic", "Drift"]:
            events = mgr.get_events(f"member:{name}")
            assert len(events) == 1
            assert events[0].event_type == "session_participated"
            assert events[0].points == 3

    def test_vote_cast_shows_on_leaderboard(self, mgr, rep_dir):
        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_vote_cast("Sage", "P-0001", "for")
            on_vote_cast("Logic", "P-0001", "against")
            on_proposal_authored("Sage", "P-0001")

        board = mgr.get_leaderboard()
        assert len(board) == 2
        sage = next(s for s in board if s.entity_id == "member:sage")
        logic = next(s for s in board if s.entity_id == "member:logic")
        assert sage.raw_score == 12  # 2 (vote) + 10 (authored)
        assert logic.raw_score == 2   # 2 (vote)
