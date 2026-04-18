"""
Tests for core/context_builder.py (F-064)

Verifies:
1. The new module is importable and exports the expected symbols
2. Backward-compatible imports from core.routes.explore still work
3. The _helpers re-export still works
4. The extracted vote helpers in core.voting work correctly
5. The extracted story chat helpers in core.story work correctly
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


# ─── Import Verification ─────────────────────────────────────


class TestContextBuilderImports:
    """Verify the new core.context_builder module is importable."""

    def test_import_build_participant_context(self):
        from core.context_builder import build_participant_context
        assert callable(build_participant_context)

    def test_import_underscore_alias(self):
        from core.context_builder import _build_participant_context
        assert callable(_build_participant_context)

    def test_import_participant_max(self):
        from core.context_builder import PARTICIPANT_MAX
        assert PARTICIPANT_MAX == 10

    def test_alias_is_same_function(self):
        from core.context_builder import (
            build_participant_context,
            _build_participant_context,
        )
        assert build_participant_context is _build_participant_context


class TestBackwardCompatImports:
    """Verify backward-compatible imports from core.routes.explore."""

    def test_import_from_explore(self):
        from core.routes.explore import _build_participant_context
        assert callable(_build_participant_context)

    def test_import_participant_max_from_explore(self):
        from core.routes.explore import _PARTICIPANT_MAX
        assert _PARTICIPANT_MAX == 10

    def test_same_function_as_context_builder(self):
        from core.context_builder import build_participant_context
        from core.routes.explore import _build_participant_context
        assert build_participant_context is _build_participant_context


class TestHelpersReExport:
    """Verify _helpers.py re-export works."""

    def test_import_from_helpers(self):
        from core.routes._helpers import _build_participant_context
        assert callable(_build_participant_context)


# ─── Vote Helpers (F-064) ────────────────────────────────────


class TestBuildVotePrompt:
    """Tests for core.voting.build_vote_prompt."""

    def test_basic_prompt_structure(self):
        from core.voting import build_vote_prompt

        proposal = MagicMock()
        proposal.title = "Test Proposal"
        proposal.id = "PROP-0001"
        proposal.category = "ethics"
        proposal.author = "Sage"
        proposal.description = "A test proposal"

        member = MagicMock()
        member.name = "Oracle"
        member.role = "Mystic Advisor"

        prompt = build_vote_prompt(proposal, member)
        assert "Test Proposal" in prompt
        assert "PROP-0001" in prompt
        assert "ethics" in prompt
        assert "Sage" in prompt
        assert "Oracle" in prompt
        assert "Mystic Advisor" in prompt
        assert "VOTE: for" in prompt
        assert "VOTE: against" in prompt
        assert "VOTE: abstain" in prompt

    def test_includes_discussion_context(self):
        from core.voting import build_vote_prompt

        proposal = MagicMock()
        proposal.title = "Test"
        proposal.id = "P-1"
        proposal.category = "law"
        proposal.author = "User"
        proposal.description = "Desc"

        member = MagicMock()
        member.name = "M"
        member.role = "R"

        prompt = build_vote_prompt(
            proposal, member,
            discussion_context="\n\n## Discussion Summary\nSome discussion",
        )
        assert "Discussion Summary" in prompt

    def test_includes_memory_block(self):
        from core.voting import build_vote_prompt

        proposal = MagicMock()
        proposal.title = "Test"
        proposal.id = "P-1"
        proposal.category = "law"
        proposal.author = "User"
        proposal.description = "Desc"

        member = MagicMock()
        member.name = "M"
        member.role = "R"

        prompt = build_vote_prompt(
            proposal, member,
            memory_block="\n\nRelevant memory about trade",
        )
        assert "Relevant memory about trade" in prompt


class TestParseVoteResponse:
    """Tests for core.voting.parse_vote_response."""

    def test_parse_for_vote(self):
        from core.voting import parse_vote_response
        choice, reason = parse_vote_response("VOTE: for\nI agree with this.")
        assert choice == "for"
        assert "agree" in reason

    def test_parse_against_vote(self):
        from core.voting import parse_vote_response
        choice, reason = parse_vote_response("VOTE: against\nI disagree.")
        assert choice == "against"
        assert "disagree" in reason

    def test_parse_abstain_vote(self):
        from core.voting import parse_vote_response
        choice, reason = parse_vote_response("VOTE: abstain\nNot sure.")
        assert choice == "abstain"

    def test_default_abstain_for_unparseable(self):
        from core.voting import parse_vote_response
        choice, reason = parse_vote_response("I have no opinion on this matter")
        assert choice == "abstain"

    def test_case_insensitive(self):
        from core.voting import parse_vote_response
        choice, _ = parse_vote_response("vote: FOR\nStrongly in favor!")
        assert choice == "for"

    def test_no_space_after_colon(self):
        from core.voting import parse_vote_response
        choice, _ = parse_vote_response("VOTE:for\nYes.")
        assert choice == "for"


# ─── Story Chat Helpers (F-064) ──────────────────────────────


class TestStoryChatHelpers:
    """Tests for story chat helpers extracted to core.story."""

    def test_get_story_round_default(self):
        from core.story import get_story_round
        record = MagicMock()
        record.metadata = {}
        assert get_story_round(record) == 0

    def test_get_story_round_with_value(self):
        from core.story import get_story_round
        record = MagicMock()
        record.metadata = {"story_round": 3}
        assert get_story_round(record) == 3

    def test_get_story_round_none_metadata(self):
        from core.story import get_story_round
        record = MagicMock()
        record.metadata = None
        assert get_story_round(record) == 0

    def test_is_story_chat_at_limit_false(self):
        from core.story import is_story_chat_at_limit
        record = MagicMock()
        record.metadata = {"story_round": 2, "story_max_rounds": 5}
        assert is_story_chat_at_limit(record) is False

    def test_is_story_chat_at_limit_true(self):
        from core.story import is_story_chat_at_limit
        record = MagicMock()
        record.metadata = {"story_round": 5, "story_max_rounds": 5}
        assert is_story_chat_at_limit(record) is True

    def test_is_story_chat_at_limit_default_max(self):
        from core.story import is_story_chat_at_limit, STORY_CHAT_MAX_ROUNDS
        record = MagicMock()
        record.metadata = {"story_round": STORY_CHAT_MAX_ROUNDS}
        assert is_story_chat_at_limit(record) is True

    def test_story_chat_max_rounds_constant(self):
        from core.story import STORY_CHAT_MAX_ROUNDS
        assert STORY_CHAT_MAX_ROUNDS == 5

    def test_increment_story_round(self):
        from core.story import increment_story_round

        mock_record = MagicMock()
        mock_record.metadata = {"story_round": 2}
        mock_record.to_dict.return_value = {
            "chat_id": "STC-0001",
            "metadata": {"story_round": 2},
        }

        mock_hc = MagicMock()
        mock_hc.get.return_value = mock_record

        with patch("core.human_chat.HumanChatRecord") as mock_hcr:
            mock_hcr.from_dict.return_value = MagicMock()
            result = increment_story_round(mock_hc, "STC-0001")

        assert result == 3
        mock_hc._save.assert_called_once()
