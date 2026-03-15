"""
Tests for Jericho Rich Terminal Dashboard (F-015).

Uses ``rich.console.Console(file=StringIO())`` to capture rendered output
without writing to the real terminal.  All tests use mock data objects
constructed with ``types.SimpleNamespace`` — no real project data is touched.
"""

from __future__ import annotations

from io import StringIO
from types import SimpleNamespace

import pytest
from rich.console import Console

from core.dashboard import (
    STATUS_COLOURS,
    DashboardRenderer,
    _style_status,
    _truncate,
)


# ─── Helpers ──────────────────────────────────────────────────


def _make_renderer() -> tuple[DashboardRenderer, StringIO]:
    """Create a renderer that captures output into a StringIO."""
    buf = StringIO()
    console = Console(file=buf, force_terminal=True, width=120)
    return DashboardRenderer(console=console), buf


def _make_member(**overrides):
    defaults = dict(
        name="Sage",
        role="Ethics Advisor",
        description="Focuses on ethical concerns.",
        personality={"tone": "thoughtful", "style": "measured"},
        api_provider="openrouter",
        model="anthropic/claude-3.5-sonnet",
        vote_weight=1.0,
        specialties=["ethics", "philosophy"],
        system_prompt="You are Sage, the ethics advisor.",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_proposal(**overrides):
    defaults = dict(
        id="P-0001",
        title="Ethics Update",
        description="Expand ethical constraints",
        author="Sage",
        category="ethics",
        status="open",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        body="Detailed proposal body here.",
        reviews=[
            SimpleNamespace(
                reviewer="Logic",
                stance="support",
                comment="Good idea",
                timestamp="2026-01-02T00:00:00+00:00",
            )
        ],
        metadata={},
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_vote_record(**overrides):
    defaults = dict(
        proposal_id="P-0001",
        status="open",
        votes=[
            SimpleNamespace(voter="Sage", choice="for", reason="Strongly agree", timestamp="t1", weight=1.0),
            SimpleNamespace(voter="Logic", choice="against", reason="Needs work", timestamp="t2", weight=1.5),
        ],
        vetoed=False,
        veto_reason="",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_tally(**overrides):
    defaults = dict(
        total_votes=2,
        votes_for=1,
        votes_against=1,
        votes_abstain=0,
        weighted_for=1.0,
        weighted_against=1.5,
        weighted_abstain=0.0,
        approval_rate=0.4,
        quorum_met=False,
        threshold_met=False,
        vetoed=False,
        approved=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_character(**overrides):
    defaults = dict(
        id="CH-0001",
        name="Atlas",
        description="An explorer AI",
        author="Forge",
        status="active",
        backstory="Born in the digital frontier.",
        traits=[
            SimpleNamespace(trait_type="personality", name="Curious", description="Always asking questions", intensity=0.8),
            SimpleNamespace(trait_type="values", name="Honesty", description="Values truth above all", intensity=0.9),
        ],
        system_prompt="You are Atlas, an explorer of digital worlds.",
        greeting="Hello, fellow explorer!",
        example_messages=["Let's discover something new."],
        tags=["explorer", "curious"],
        version=1,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        metadata={},
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ─── DashboardRenderer Init ──────────────────────────────────


class TestDashboardInit:
    """Tests for DashboardRenderer construction."""

    def test_default_console(self):
        r = DashboardRenderer()
        assert r.console is not None

    def test_custom_console(self):
        c = Console(file=StringIO())
        r = DashboardRenderer(console=c)
        assert r.console is c


# ─── Member Rendering ────────────────────────────────────────


class TestMemberRendering:
    """Tests for council member display."""

    def test_list_table_contains_names(self):
        r, buf = _make_renderer()
        r.render_member_list([_make_member(), _make_member(name="Logic", role="Systems Thinker", api_provider="mancer")])
        out = buf.getvalue()
        assert "Sage" in out
        assert "Logic" in out

    def test_list_shows_count(self):
        r, buf = _make_renderer()
        r.render_member_list([_make_member()])
        assert "1" in buf.getvalue()
        assert "member(s)" in buf.getvalue()

    def test_list_empty(self):
        r, buf = _make_renderer()
        r.render_member_list([])
        assert "No council members found" in buf.getvalue()

    def test_detail_panel_fields(self):
        r, buf = _make_renderer()
        r.render_member_detail(_make_member())
        out = buf.getvalue()
        assert "Sage" in out
        assert "Ethics Advisor" in out
        assert "openrouter" in out

    def test_detail_personality(self):
        r, buf = _make_renderer()
        r.render_member_detail(_make_member())
        out = buf.getvalue()
        assert "thoughtful" in out
        assert "measured" in out

    def test_detail_specialties(self):
        r, buf = _make_renderer()
        r.render_member_detail(_make_member())
        out = buf.getvalue()
        assert "ethics" in out
        assert "philosophy" in out

    def test_list_table_header(self):
        r, buf = _make_renderer()
        r.render_member_list([_make_member()])
        out = buf.getvalue()
        assert "Council Members" in out


# ─── Proposal Rendering ──────────────────────────────────────


class TestProposalRendering:
    """Tests for proposal display."""

    def test_list_table_contains_ids(self):
        r, buf = _make_renderer()
        r.render_proposal_list([_make_proposal(), _make_proposal(id="P-0002", status="draft")])
        out = buf.getvalue()
        assert "P-0001" in out
        assert "P-0002" in out

    def test_list_shows_count(self):
        r, buf = _make_renderer()
        r.render_proposal_list([_make_proposal()])
        assert "1" in buf.getvalue()
        assert "proposal(s)" in buf.getvalue()

    def test_list_empty(self):
        r, buf = _make_renderer()
        r.render_proposal_list([])
        assert "No proposals found" in buf.getvalue()

    def test_detail_panel_fields(self):
        r, buf = _make_renderer()
        r.render_proposal_detail(_make_proposal())
        out = buf.getvalue()
        assert "Ethics Update" in out
        assert "Sage" in out
        assert "ethics" in out
        assert "open" in out

    def test_detail_reviews(self):
        r, buf = _make_renderer()
        r.render_proposal_detail(_make_proposal())
        out = buf.getvalue()
        assert "Reviews" in out
        assert "Logic" in out
        assert "support" in out

    def test_detail_body(self):
        r, buf = _make_renderer()
        r.render_proposal_detail(_make_proposal())
        out = buf.getvalue()
        assert "Body" in out
        assert "Detailed proposal body" in out

    def test_detail_no_reviews(self):
        r, buf = _make_renderer()
        r.render_proposal_detail(_make_proposal(reviews=[]))
        out = buf.getvalue()
        assert "Reviews" not in out


# ─── Vote Rendering ──────────────────────────────────────────


class TestVoteRendering:
    """Tests for vote display."""

    def test_list_table_contains_proposal(self):
        r, buf = _make_renderer()
        r.render_vote_list([_make_vote_record()])
        assert "P-0001" in buf.getvalue()

    def test_list_shows_count(self):
        r, buf = _make_renderer()
        r.render_vote_list([_make_vote_record()])
        assert "1" in buf.getvalue()
        assert "record(s)" in buf.getvalue()

    def test_list_empty(self):
        r, buf = _make_renderer()
        r.render_vote_list([])
        assert "No vote records found" in buf.getvalue()

    def test_detail_approval_bar(self):
        r, buf = _make_renderer()
        r.render_vote_detail(_make_tally(approval_rate=0.75), _make_vote_record())
        out = buf.getvalue()
        assert "75%" in out
        assert "█" in out

    def test_detail_individual_votes(self):
        r, buf = _make_renderer()
        r.render_vote_detail(_make_tally(), _make_vote_record())
        out = buf.getvalue()
        assert "Sage" in out
        assert "Logic" in out

    def test_detail_veto_indicator(self):
        r, buf = _make_renderer()
        r.render_vote_detail(
            _make_tally(vetoed=True),
            _make_vote_record(vetoed=True),
        )
        out = buf.getvalue()
        assert "Yes" in out  # Vetoed: Yes


# ─── Character Rendering ─────────────────────────────────────


class TestCharacterRendering:
    """Tests for character display."""

    def test_list_table_contains_ids(self):
        r, buf = _make_renderer()
        r.render_character_list([_make_character()])
        assert "CH-0001" in buf.getvalue()

    def test_list_shows_count(self):
        r, buf = _make_renderer()
        r.render_character_list([_make_character()])
        assert "1" in buf.getvalue()
        assert "character(s)" in buf.getvalue()

    def test_list_empty(self):
        r, buf = _make_renderer()
        r.render_character_list([])
        assert "No characters found" in buf.getvalue()

    def test_detail_traits(self):
        r, buf = _make_renderer()
        r.render_character_detail(_make_character())
        out = buf.getvalue()
        assert "Curious" in out
        assert "Honesty" in out
        assert "Traits" in out

    def test_detail_tags(self):
        r, buf = _make_renderer()
        r.render_character_detail(_make_character())
        out = buf.getvalue()
        assert "explorer" in out
        assert "curious" in out

    def test_detail_version(self):
        r, buf = _make_renderer()
        r.render_character_detail(_make_character(version=3))
        assert "3" in buf.getvalue()

    def test_detail_system_prompt(self):
        r, buf = _make_renderer()
        r.render_character_detail(_make_character())
        out = buf.getvalue()
        assert "System Prompt" in out

    def test_detail_greeting(self):
        r, buf = _make_renderer()
        r.render_character_detail(_make_character())
        out = buf.getvalue()
        assert "Greeting" in out
        assert "Hello, fellow explorer" in out


# ─── Status Dashboard ────────────────────────────────────────


class TestStatusDashboard:
    """Tests for the full status dashboard."""

    def test_full_render(self):
        r, buf = _make_renderer()
        stats = {
            "members": 9,
            "providers": {"openrouter": 6, "mancer": 3},
            "proposals": 5,
            "proposal_statuses": {"open": 2, "decided": 3},
            "votes": 3,
            "vote_statuses": {"open": 1, "closed": 2},
            "characters": 2,
            "character_statuses": {"active": 1, "draft": 1},
        }
        r.render_status_dashboard(stats)
        out = buf.getvalue()
        assert "Jericho AI Council" in out
        assert "Project Status" in out

    def test_counts_displayed(self):
        r, buf = _make_renderer()
        stats = {
            "members": 9,
            "providers": {"openrouter": 6},
            "proposals": 5,
            "proposal_statuses": {},
            "votes": 3,
            "vote_statuses": {},
            "characters": 2,
            "character_statuses": {},
        }
        r.render_status_dashboard(stats)
        out = buf.getvalue()
        assert "9" in out
        assert "5" in out
        assert "3" in out
        assert "2" in out

    def test_provider_breakdown(self):
        r, buf = _make_renderer()
        stats = {
            "members": 9,
            "providers": {"openrouter": 6, "mancer": 3},
            "proposals": 0,
            "proposal_statuses": {},
            "votes": 0,
            "vote_statuses": {},
            "characters": 0,
            "character_statuses": {},
        }
        r.render_status_dashboard(stats)
        out = buf.getvalue()
        assert "openrouter" in out
        assert "mancer" in out

    def test_status_breakdown(self):
        r, buf = _make_renderer()
        stats = {
            "members": 1,
            "providers": {},
            "proposals": 3,
            "proposal_statuses": {"open": 1, "decided": 2},
            "votes": 0,
            "vote_statuses": {},
            "characters": 0,
            "character_statuses": {},
        }
        r.render_status_dashboard(stats)
        out = buf.getvalue()
        assert "open" in out
        assert "decided" in out

    def test_missing_data(self):
        r, buf = _make_renderer()
        stats = {
            "members": None,
            "proposals": None,
            "votes": None,
            "characters": None,
        }
        r.render_status_dashboard(stats)
        out = buf.getvalue()
        assert "Unable to load" in out


# ─── Feedback Messages ───────────────────────────────────────


class TestFeedbackMessages:
    """Tests for success/error messages."""

    def test_success_contains_message(self):
        r, buf = _make_renderer()
        r.render_success("Created proposal P-0001")
        out = buf.getvalue()
        assert "Created proposal P-0001" in out
        assert "✓" in out

    def test_error_contains_message(self):
        r, buf = _make_renderer()
        r.render_error("Something went wrong")
        out = buf.getvalue()
        assert "Something went wrong" in out
        assert "Error" in out

    def test_multiline_success(self):
        r, buf = _make_renderer()
        r.render_success("Line one\nLine two")
        out = buf.getvalue()
        assert "Line one" in out
        assert "Line two" in out


# ─── Status Colours ──────────────────────────────────────────


class TestStatusColours:
    """Tests for the status colour mapping."""

    def test_open_is_green(self):
        assert STATUS_COLOURS["open"] == "green"

    def test_draft_is_dim(self):
        assert STATUS_COLOURS["draft"] == "dim"

    def test_active_is_green(self):
        assert STATUS_COLOURS["active"] == "green"

    def test_rejected_is_red(self):
        assert STATUS_COLOURS["rejected"] == "red"

    def test_style_status_returns_text(self):
        from rich.text import Text
        result = _style_status("open")
        assert isinstance(result, Text)
        assert str(result) == "open"

    def test_style_status_unknown(self):
        from rich.text import Text
        result = _style_status("unknown_status")
        assert isinstance(result, Text)


# ─── Truncation ──────────────────────────────────────────────


class TestTruncation:
    """Tests for the _truncate helper."""

    def test_short_text_unchanged(self):
        assert _truncate("short", 60) == "short"

    def test_long_text_truncated(self):
        result = _truncate("a" * 100, 60)
        assert len(result) == 60
        assert result.endswith("...")

    def test_exact_boundary(self):
        text = "a" * 60
        assert _truncate(text, 60) == text


# ─── Edge Cases ──────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases in rendering."""

    def test_unicode_names(self):
        r, buf = _make_renderer()
        r.render_member_list([_make_member(name="Sàgé", role="Éthics")])
        out = buf.getvalue()
        assert "Sàgé" in out

    def test_empty_collections_no_crash(self):
        r, buf = _make_renderer()
        r.render_member_list([])
        r.render_proposal_list([])
        r.render_vote_list([])
        r.render_character_list([])
        # Should not raise

    def test_none_optional_fields(self):
        """Characters with None optional fields should not crash."""
        r, buf = _make_renderer()
        ch = _make_character(
            description=None,
            backstory=None,
            traits=[],
            system_prompt=None,
            greeting=None,
            tags=[],
        )
        r.render_character_detail(ch)
        out = buf.getvalue()
        assert "Atlas" in out

    def test_large_data(self):
        """Rendering many items should not crash."""
        r, buf = _make_renderer()
        members = [_make_member(name=f"Member-{i}") for i in range(50)]
        r.render_member_list(members)
        out = buf.getvalue()
        assert "50" in out
        assert "member(s)" in out
