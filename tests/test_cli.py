"""
Tests for Jericho CLI Interface (F-014).

Uses ``click.testing.CliRunner`` for isolated, synchronous CLI testing.
All tests use ``tmp_path`` fixtures so no real project data is touched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from click.testing import CliRunner

from core.cli import cli


# ─── Mock Helpers ──────────────────────────────────────────────


def _mock_voting_init(votes_dir, quorum=5, threshold=0.6):
    """Return a proper __init__ replacement for VotingEngine that returns None."""
    def init(self, v=None, q=None, t=None):
        self._dir = votes_dir
        self._quorum = quorum
        self._threshold = threshold
    return init


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def runner():
    """Click CliRunner with mixed stderr."""
    return CliRunner(mix_stderr=False)


@pytest.fixture
def members_dir(tmp_path):
    """Create a temporary members directory with two council members."""
    d = tmp_path / "members"
    d.mkdir()

    sage = {
        "name": "Sage",
        "role": "Ethics Advisor",
        "description": "Focuses on ethical concerns.",
        "personality": {"tone": "thoughtful", "style": "measured"},
        "api_provider": "openrouter",
        "model": "anthropic/claude-3.5-sonnet",
        "vote_weight": 1.0,
        "specialties": ["ethics", "philosophy"],
        "system_prompt": "You are Sage, the ethics advisor.",
    }
    logic = {
        "name": "Logic",
        "role": "Systems Thinker",
        "description": "Focuses on system design.",
        "personality": {"tone": "precise"},
        "api_provider": "mancer",
        "model": "celeste-v1.9",
        "vote_weight": 1.5,
        "specialties": ["systems", "architecture"],
        "system_prompt": "You are Logic, the systems thinker.",
    }

    (d / "sage.yaml").write_text(yaml.dump(sage), encoding="utf-8")
    (d / "logic.yaml").write_text(yaml.dump(logic), encoding="utf-8")
    return d


@pytest.fixture
def proposals_dir(tmp_path):
    """Create a temporary proposals directory with sample proposals."""
    d = tmp_path / "proposals"
    d.mkdir()

    p1 = {
        "id": "P-0001",
        "title": "Ethics Update",
        "description": "Expand ethical constraints",
        "author": "Sage",
        "category": "ethics",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "body": "Detailed proposal body here.",
        "reviews": [
            {"reviewer": "Logic", "stance": "support", "comment": "Good idea", "timestamp": "2026-01-02T00:00:00+00:00"}
        ],
        "metadata": {},
    }
    p2 = {
        "id": "P-0002",
        "title": "New Character Proposal",
        "description": "Add an explorer character",
        "author": "Forge",
        "category": "character",
        "status": "draft",
        "created_at": "2026-01-03T00:00:00+00:00",
        "updated_at": "2026-01-03T00:00:00+00:00",
        "body": "",
        "reviews": [],
        "metadata": {},
    }

    (d / "P-0001.json").write_text(json.dumps(p1, indent=2), encoding="utf-8")
    (d / "P-0002.json").write_text(json.dumps(p2, indent=2), encoding="utf-8")
    return d


@pytest.fixture
def votes_dir(tmp_path):
    """Create a temporary votes directory with a sample record."""
    d = tmp_path / "votes"
    d.mkdir()

    rec = {
        "proposal_id": "P-0001",
        "status": "open",
        "votes": [
            {"voter": "Sage", "choice": "for", "reason": "Strongly agree", "timestamp": "2026-01-01T00:00:00+00:00", "weight": 1.0},
            {"voter": "Logic", "choice": "against", "reason": "Needs work", "timestamp": "2026-01-01T01:00:00+00:00", "weight": 1.5},
        ],
        "vetoed": False,
        "veto_reason": "",
        "veto_timestamp": "",
        "opened_at": "2026-01-01T00:00:00+00:00",
        "closed_at": "",
        "metadata": {},
    }

    (d / "V-P-0001.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return d


@pytest.fixture
def characters_dir(tmp_path):
    """Create a temporary characters directory with a sample character."""
    d = tmp_path / "characters"
    d.mkdir()

    ch = {
        "id": "CH-0001",
        "name": "Atlas",
        "description": "An explorer AI",
        "author": "Forge",
        "status": "active",
        "backstory": "Born in the digital frontier.",
        "traits": [
            {"trait_type": "personality", "name": "Curious", "description": "Always asking questions", "intensity": 0.8},
            {"trait_type": "values", "name": "Honesty", "description": "Values truth above all", "intensity": 0.9},
        ],
        "system_prompt": "You are Atlas, an explorer of digital worlds.",
        "greeting": "Hello, fellow explorer!",
        "example_messages": ["Let's discover something new."],
        "tags": ["explorer", "curious"],
        "version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "metadata": {},
    }

    (d / "CH-0001.json").write_text(json.dumps(ch, indent=2), encoding="utf-8")
    return d


# ─── Council Command Tests ────────────────────────────────────


class TestCouncilList:
    """Tests for ``jericho council list``."""

    def test_list_all(self, runner, members_dir):
        with patch("core.cli.CouncilRegistry.__init__", lambda self, d=None: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})):
            result = runner.invoke(cli, ["council", "list"])
        assert result.exit_code == 0
        assert "Sage" in result.output
        assert "Logic" in result.output
        assert "member" in result.output

    def test_list_filter_provider(self, runner, members_dir):
        with patch("core.cli.CouncilRegistry.__init__", lambda self, d=None: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})):
            result = runner.invoke(cli, ["council", "list", "--provider", "mancer"])
        assert result.exit_code == 0
        assert "Logic" in result.output
        assert "member" in result.output

    def test_list_empty(self, runner, tmp_path):
        empty = tmp_path / "empty_members"
        empty.mkdir()
        with patch("core.cli.CouncilRegistry.__init__", lambda self, d=None: setattr(self, '_members_dir', empty) or setattr(self, '_members', {})):
            result = runner.invoke(cli, ["council", "list"])
        assert result.exit_code == 0
        assert "No council members found" in result.output


class TestCouncilShow:
    """Tests for ``jericho council show``."""

    def test_show_member(self, runner, members_dir):
        with patch("core.cli.CouncilRegistry.__init__", lambda self, d=None: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})):
            result = runner.invoke(cli, ["council", "show", "Sage"])
        assert result.exit_code == 0
        assert "Sage" in result.output
        assert "Ethics Advisor" in result.output
        assert "openrouter" in result.output

    def test_show_personality(self, runner, members_dir):
        with patch("core.cli.CouncilRegistry.__init__", lambda self, d=None: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})):
            result = runner.invoke(cli, ["council", "show", "Sage"])
        assert "Personality:" in result.output
        assert "thoughtful" in result.output

    def test_show_specialties(self, runner, members_dir):
        with patch("core.cli.CouncilRegistry.__init__", lambda self, d=None: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})):
            result = runner.invoke(cli, ["council", "show", "Logic"])
        assert "Specialties:" in result.output
        assert "systems" in result.output

    def test_show_nonexistent(self, runner, members_dir):
        with patch("core.cli.CouncilRegistry.__init__", lambda self, d=None: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})):
            result = runner.invoke(cli, ["council", "show", "Nobody"])
        assert result.exit_code != 0
        assert "not found" in result.stderr


# ─── Proposals Command Tests ─────────────────────────────────


class TestProposalsList:
    """Tests for ``jericho proposals list``."""

    def test_list_all(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "list"])
        assert result.exit_code == 0
        assert "P-0001" in result.output
        assert "P-0002" in result.output
        assert "proposal" in result.output

    def test_list_filter_status(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "list", "--status", "draft"])
        assert result.exit_code == 0
        assert "P-0002" in result.output
        assert "P-0001" not in result.output

    def test_list_filter_category(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "list", "--category", "ethics"])
        assert result.exit_code == 0
        assert "P-0001" in result.output
        assert "proposal" in result.output

    def test_list_filter_author(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "list", "--author", "Forge"])
        assert result.exit_code == 0
        assert "P-0002" in result.output

    def test_list_empty(self, runner, tmp_path):
        empty = tmp_path / "empty_proposals"
        empty.mkdir()
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', empty)):
            result = runner.invoke(cli, ["proposals", "list"])
        assert result.exit_code == 0
        assert "No proposals found" in result.output


class TestProposalsShow:
    """Tests for ``jericho proposals show``."""

    def test_show_proposal(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "show", "P-0001"])
        assert result.exit_code == 0
        assert "Ethics Update" in result.output
        assert "Sage" in result.output
        assert "ethics" in result.output
        assert "open" in result.output

    def test_show_with_reviews(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "show", "P-0001"])
        assert "Reviews" in result.output
        assert "Logic" in result.output
        assert "support" in result.output

    def test_show_with_body(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "show", "P-0001"])
        assert "Body:" in result.output
        assert "Detailed proposal body" in result.output

    def test_show_nonexistent(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, ["proposals", "show", "P-9999"])
        assert result.exit_code != 0
        assert "not found" in result.stderr


class TestProposalsCreate:
    """Tests for ``jericho proposals create``."""

    def test_create_proposal(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, [
                "proposals", "create",
                "--title", "New Ethics Rule",
                "--description", "Add a new ethics requirement",
                "--author", "Sage",
                "--category", "ethics",
            ])
        assert result.exit_code == 0
        assert "Created proposal" in result.output
        assert "P-0003" in result.output

    def test_create_with_body(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, [
                "proposals", "create",
                "--title", "Detailed Proposal",
                "--description", "Has a body",
                "--author", "Logic",
                "--category", "governance",
                "--body", "This is the detailed body text.",
            ])
        assert result.exit_code == 0
        assert "Created proposal" in result.output

    def test_create_invalid_category(self, runner, proposals_dir):
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, [
                "proposals", "create",
                "--title", "Bad Proposal",
                "--description", "Invalid category",
                "--author", "Sage",
                "--category", "invalid_category",
            ])
        assert result.exit_code != 0

    def test_create_missing_required(self, runner, proposals_dir):
        """Missing --title should cause click to error."""
        with patch("core.cli.ProposalManager.__init__", lambda self, d=None: setattr(self, '_dir', proposals_dir)):
            result = runner.invoke(cli, [
                "proposals", "create",
                "--description", "No title provided",
                "--author", "Sage",
                "--category", "ethics",
            ])
        assert result.exit_code != 0


# ─── Vote Command Tests ──────────────────────────────────────


class TestVoteList:
    """Tests for ``jericho vote list``."""

    def test_list_all(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)):
            result = runner.invoke(cli, ["vote", "list"])
        assert result.exit_code == 0
        assert "P-0001" in result.output
        assert "record" in result.output

    def test_list_empty(self, runner, tmp_path):
        empty = tmp_path / "empty_votes"
        empty.mkdir()
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(empty)):
            result = runner.invoke(cli, ["vote", "list"])
        assert result.exit_code == 0
        assert "No vote records found" in result.output


class TestVoteShow:
    """Tests for ``jericho vote show``."""

    def test_show_tally(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir, quorum=2)):
            result = runner.invoke(cli, ["vote", "show", "P-0001"])
        assert result.exit_code == 0
        assert "P-0001" in result.output
        assert "For:" in result.output
        assert "Against:" in result.output
        assert "Approval:" in result.output

    def test_show_individual_votes(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir, quorum=2)):
            result = runner.invoke(cli, ["vote", "show", "P-0001"])
        assert "Sage: for" in result.output
        assert "Logic: against" in result.output

    def test_show_nonexistent(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)):
            result = runner.invoke(cli, ["vote", "show", "P-9999"])
        assert result.exit_code != 0
        assert "No vote record" in result.stderr


class TestVoteCast:
    """Tests for ``jericho vote cast``."""

    def test_cast_vote(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)):
            result = runner.invoke(cli, [
                "vote", "cast", "P-0001",
                "--voter", "Drift",
                "--choice", "for",
                "--reason", "I agree",
            ])
        assert result.exit_code == 0
        assert "Vote cast" in result.output
        assert "Drift" in result.output

    def test_cast_duplicate(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)):
            result = runner.invoke(cli, [
                "vote", "cast", "P-0001",
                "--voter", "Sage",
                "--choice", "for",
            ])
        assert result.exit_code != 0
        assert "already voted" in result.stderr

    def test_cast_invalid_choice(self, runner, votes_dir):
        """Click's choice validation should reject invalid choices."""
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)):
            result = runner.invoke(cli, [
                "vote", "cast", "P-0001",
                "--voter", "Drift",
                "--choice", "maybe",
            ])
        assert result.exit_code != 0


class TestVoteVeto:
    """Tests for ``jericho vote veto``."""

    def test_veto(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)):
            result = runner.invoke(cli, [
                "vote", "veto", "P-0001",
                "--reason", "Needs more discussion",
            ])
        assert result.exit_code == 0
        assert "Veto applied" in result.output

    def test_veto_nonexistent(self, runner, votes_dir):
        with patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)):
            result = runner.invoke(cli, ["vote", "veto", "P-9999"])
        assert result.exit_code != 0


# ─── Characters Command Tests ────────────────────────────────


class TestCharactersList:
    """Tests for ``jericho characters list``."""

    def test_list_all(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "list"])
        assert result.exit_code == 0
        assert "CH-0001" in result.output
        assert "Atlas" in result.output
        assert "character" in result.output

    def test_list_filter_status(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "list", "--status", "draft"])
        assert result.exit_code == 0
        assert "No characters found" in result.output

    def test_list_filter_author(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "list", "--author", "Forge"])
        assert result.exit_code == 0
        assert "Atlas" in result.output

    def test_list_filter_tag(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "list", "--tag", "explorer"])
        assert result.exit_code == 0
        assert "Atlas" in result.output

    def test_list_empty(self, runner, tmp_path):
        empty = tmp_path / "empty_chars"
        empty.mkdir()
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', empty)):
            result = runner.invoke(cli, ["characters", "list"])
        assert result.exit_code == 0
        assert "No characters found" in result.output


class TestCharactersShow:
    """Tests for ``jericho characters show``."""

    def test_show_character(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "show", "CH-0001"])
        assert result.exit_code == 0
        assert "Atlas" in result.output
        assert "Forge" in result.output
        assert "active" in result.output

    def test_show_traits(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "show", "CH-0001"])
        assert "Traits" in result.output
        assert "Curious" in result.output
        assert "Honesty" in result.output

    def test_show_tags(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "show", "CH-0001"])
        assert "Tags:" in result.output
        assert "explorer" in result.output

    def test_show_system_prompt(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "show", "CH-0001"])
        assert "System Prompt:" in result.output

    def test_show_greeting(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "show", "CH-0001"])
        assert "Greeting:" in result.output

    def test_show_nonexistent(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "show", "CH-9999"])
        assert result.exit_code != 0
        assert "not found" in result.stderr


class TestCharactersExport:
    """Tests for ``jericho characters export``."""

    def test_export_to_stdout(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "export", "CH-0001"])
        assert result.exit_code == 0
        # YAML output should contain key character fields
        assert "Atlas" in result.output
        assert "traits" in result.output

    def test_export_to_file(self, runner, characters_dir, tmp_path):
        output_file = tmp_path / "exported.yaml"
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, [
                "characters", "export", "CH-0001",
                "--output", str(output_file),
            ])
        assert result.exit_code == 0
        assert "Exported" in result.output
        assert output_file.exists()
        content = output_file.read_text(encoding="utf-8")
        assert "Atlas" in content

    def test_export_nonexistent(self, runner, characters_dir):
        with patch("core.cli.CharacterManager.__init__", lambda self, d=None: setattr(self, '_dir', characters_dir)):
            result = runner.invoke(cli, ["characters", "export", "CH-9999"])
        assert result.exit_code != 0
        assert "not found" in result.stderr


# ─── Status Command Tests ────────────────────────────────────


class TestStatusCommand:
    """Tests for ``jericho status``."""

    def test_status_output(self, runner, members_dir, proposals_dir, votes_dir, characters_dir):
        with (
            patch("core.cli.CouncilRegistry.__init__", lambda self: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})),
            patch("core.cli.ProposalManager.__init__", lambda self: setattr(self, '_dir', proposals_dir)),
            patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)),
            patch("core.cli.CharacterManager.__init__", lambda self: setattr(self, '_dir', characters_dir)),
        ):
            result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Jericho AI Council" in result.output
        assert "Council" in result.output
        assert "Proposals" in result.output
        assert "Vote Records" in result.output
        assert "Characters" in result.output

    def test_status_counts(self, runner, members_dir, proposals_dir, votes_dir, characters_dir):
        with (
            patch("core.cli.CouncilRegistry.__init__", lambda self: setattr(self, '_members_dir', members_dir) or setattr(self, '_members', {})),
            patch("core.cli.ProposalManager.__init__", lambda self: setattr(self, '_dir', proposals_dir)),
            patch("core.cli.VotingEngine.__init__", _mock_voting_init(votes_dir)),
            patch("core.cli.CharacterManager.__init__", lambda self: setattr(self, '_dir', characters_dir)),
        ):
            result = runner.invoke(cli, ["status"])

        # Rich panels render counts as bold numbers with "total" text
        assert "2" in result.output  # members count or proposals count
        assert "1" in result.output  # votes or characters count

    def test_status_graceful_on_missing_data(self, runner, tmp_path):
        """Status should not crash if data directories are missing."""
        # Don't patch — let it use default paths that may not exist;
        # the status command has try/except that handles this.
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "Jericho AI Council" in result.output


# ─── Help Output Tests ───────────────────────────────────────


class TestHelpOutput:
    """Ensure all groups and commands have help text."""

    def test_top_level_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "council" in result.output
        assert "proposals" in result.output
        assert "vote" in result.output
        assert "characters" in result.output
        assert "status" in result.output

    def test_council_help(self, runner):
        result = runner.invoke(cli, ["council", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "show" in result.output

    def test_proposals_help(self, runner):
        result = runner.invoke(cli, ["proposals", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "show" in result.output
        assert "create" in result.output

    def test_vote_help(self, runner):
        result = runner.invoke(cli, ["vote", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "show" in result.output
        assert "cast" in result.output
        assert "veto" in result.output

    def test_characters_help(self, runner):
        result = runner.invoke(cli, ["characters", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "show" in result.output
        assert "export" in result.output

    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output


# ─── Error Handling Tests ─────────────────────────────────────


class TestErrorHandling:
    """Tests for graceful error handling."""

    def test_unknown_subcommand(self, runner):
        result = runner.invoke(cli, ["nonexistent"])
        assert result.exit_code != 0

    def test_council_show_missing_arg(self, runner):
        result = runner.invoke(cli, ["council", "show"])
        assert result.exit_code != 0

    def test_proposals_show_missing_arg(self, runner):
        result = runner.invoke(cli, ["proposals", "show"])
        assert result.exit_code != 0

    def test_vote_cast_missing_options(self, runner):
        result = runner.invoke(cli, ["vote", "cast", "P-0001"])
        assert result.exit_code != 0

    def test_characters_export_missing_arg(self, runner):
        result = runner.invoke(cli, ["characters", "export"])
        assert result.exit_code != 0


# ─── Truncate Helper Tests ───────────────────────────────────


class TestTruncateHelper:
    """Tests for the _truncate helper function."""

    def test_short_text_unchanged(self):
        from core.dashboard import _truncate
        assert _truncate("short", 60) == "short"

    def test_long_text_truncated(self):
        from core.dashboard import _truncate
        result = _truncate("a" * 100, 60)
        assert len(result) == 60
        assert result.endswith("...")

    def test_exact_length(self):
        from core.dashboard import _truncate
        text = "a" * 60
        assert _truncate(text, 60) == text
