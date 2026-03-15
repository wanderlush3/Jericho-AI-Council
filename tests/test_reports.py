"""
Jericho — Tests for Governance Report Generator (F-022)

Tests for core/reports.py: ReportSection, GovernanceReport,
ReportGenerator engine, section builders, persistence, and edge cases.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.reports import (
    GovernanceReport,
    ReportError,
    ReportGenerator,
    ReportNotFoundError,
    ReportSection,
    ReportValidationError,
)
from core.proposals import ProposalManager, Review
from core.voting import Vote, VotingEngine
from core.characters import CharacterManager, Trait


# ─── Helpers ──────────────────────────────────────────────────


def _make_proposal_manager(tmp_path: Path) -> ProposalManager:
    return ProposalManager(proposals_dir=tmp_path / "proposals")


def _make_voting_engine(tmp_path: Path) -> VotingEngine:
    return VotingEngine(votes_dir=tmp_path / "votes", quorum=2, threshold=0.6)


def _make_character_manager(tmp_path: Path) -> CharacterManager:
    return CharacterManager(characters_dir=tmp_path / "characters")


class _FakeRegistry:
    """Minimal mock that mimics CouncilRegistry."""

    def __init__(self, members: list | None = None) -> None:
        self._members = members or []

    def list_members(self) -> list:
        return list(self._members)


class _FakeMember:
    """Minimal mock of a CouncilMember."""

    def __init__(
        self,
        name: str = "Sage",
        role: str = "Ethics Officer",
        api_provider: str = "openrouter",
        model: str = "claude-3.5-sonnet",
        vote_weight: float = 1.0,
        specialties: list[str] | None = None,
    ) -> None:
        self.name = name
        self.role = role
        self.api_provider = api_provider
        self.model = model
        self.vote_weight = vote_weight
        self.specialties = specialties if specialties is not None else ["ethics", "philosophy"]


class _FakeAnalytics:
    """Minimal mock that mimics SessionAnalytics.full_report()."""

    def __init__(self, report=None) -> None:
        self._report = report

    def full_report(self):
        if self._report is not None:
            return self._report
        # Return a minimal AnalyticsReport-like object
        return _FakeAnalyticsReport()


class _FakeAnalyticsReport:
    """Minimal mock of AnalyticsReport."""

    def __init__(self) -> None:
        self.proposal_stats = _FakeProposalStats()
        self.voting_stats = _FakeVotingStats()
        self.session_stats = _FakeSessionStats()
        self.top_participants = [("Sage", 10), ("Logic", 7)]


class _FakeProposalStats:
    total = 5
    approval_rate = 0.6
    by_status = {"draft": 2, "decided": 3}
    by_category = {"ethics": 3, "governance": 2}


class _FakeVotingStats:
    total_records = 3
    total_votes_cast = 15
    avg_votes_per_record = 5.0
    quorum_achievement_rate = 1.0
    approval_rate = 0.6667
    veto_count = 0


class _FakeSessionStats:
    total_sessions = 4
    avg_messages_per_session = 12.5
    avg_participants = 3.0


def _seed_proposals(mgr: ProposalManager, count: int = 3) -> list:
    proposals = []
    categories = ["ethics", "governance", "character"]
    authors = ["Sage", "Logic", "Spark"]
    for i in range(count):
        p = mgr.create(
            f"Proposal {i + 1}",
            f"Description for proposal {i + 1}",
            author=authors[i % 3],
            category=categories[i % 3],
        )
        proposals.append(p)
    return proposals


def _seed_characters(mgr: CharacterManager, count: int = 2) -> list:
    characters = []
    for i in range(count):
        trait = Trait.create(
            "personality", f"trait_{i}", f"A personality trait {i}", intensity=0.7
        )
        c = mgr.create(
            f"Character {i + 1}",
            f"A test character {i + 1}",
            author=["Forge", "Spark"][i % 2],
            traits=[trait],
            tags=["test", f"tag{i}"],
        )
        characters.append(c)
    return characters


def _seed_votes(engine: VotingEngine, proposal_ids: list[str]) -> None:
    for pid in proposal_ids:
        engine.open_voting(pid)
        engine.cast_vote(pid, Vote.create("Sage", "for"))
        engine.cast_vote(pid, Vote.create("Logic", "for"))
        engine.cast_vote(pid, Vote.create("Spark", "against"))


# ═══════════════════════════════════════════════════════════════
# ReportSection
# ═══════════════════════════════════════════════════════════════


class TestReportSection:
    def test_fields(self):
        s = ReportSection(title="Council", content="Members listed.", section_type="council")
        assert s.title == "Council"
        assert s.content == "Members listed."
        assert s.section_type == "council"

    def test_frozen(self):
        s = ReportSection(title="Test", content="Content")
        with pytest.raises(AttributeError):
            s.title = "Changed"  # type: ignore[misc]

    def test_defaults(self):
        s = ReportSection(title="Test", content="")
        assert s.section_type == "general"

    def test_to_dict(self):
        s = ReportSection(title="Test", content="Data", section_type="votes")
        d = s.to_dict()
        assert d["title"] == "Test"
        assert d["content"] == "Data"
        assert d["section_type"] == "votes"

    def test_roundtrip(self):
        s = ReportSection.create("Council", "Members listed.", section_type="council")
        d = s.to_dict()
        s2 = ReportSection.from_dict(d)
        assert s == s2

    def test_create_factory(self):
        s = ReportSection.create("  Council  ", "Content", section_type="  council  ")
        assert s.title == "Council"
        assert s.section_type == "council"


# ═══════════════════════════════════════════════════════════════
# GovernanceReport
# ═══════════════════════════════════════════════════════════════


class TestGovernanceReport:
    def test_fields(self):
        r = GovernanceReport(
            report_id="R-001",
            title="Test Report",
            generated_at="2026-01-01T00:00:00+00:00",
        )
        assert r.report_id == "R-001"
        assert r.title == "Test Report"
        assert r.sections == []
        assert r.metadata == {}

    def test_frozen(self):
        r = GovernanceReport(report_id="R-001", title="Test")
        with pytest.raises(AttributeError):
            r.title = "Changed"  # type: ignore[misc]

    def test_to_dict(self):
        section = ReportSection.create("Council", "Content")
        r = GovernanceReport(
            report_id="R-001",
            title="Test",
            sections=[section],
            generated_at="2026-01-01",
            metadata={"key": "value"},
        )
        d = r.to_dict()
        assert d["report_id"] == "R-001"
        assert len(d["sections"]) == 1
        assert d["metadata"]["key"] == "value"

    def test_roundtrip(self):
        section = ReportSection.create("Council", "Content", section_type="council")
        r = GovernanceReport.create(
            "R-001",
            "Report Title",
            sections=[section],
            metadata={"version": 1},
        )
        d = r.to_dict()
        r2 = GovernanceReport.from_dict(d)
        assert r2.report_id == r.report_id
        assert r2.title == r.title
        assert len(r2.sections) == 1
        assert r2.metadata == r.metadata

    def test_create_factory(self):
        r = GovernanceReport.create("  R-001  ", "  My Report  ")
        assert r.report_id == "R-001"
        assert r.title == "My Report"
        assert r.generated_at != ""

    def test_create_empty_id_raises(self):
        with pytest.raises(ReportValidationError) as exc_info:
            GovernanceReport.create("", "Title")
        assert "report_id" in str(exc_info.value)

    def test_create_empty_title_raises(self):
        with pytest.raises(ReportValidationError) as exc_info:
            GovernanceReport.create("R-001", "  ")
        assert "title" in str(exc_info.value)

    def test_to_markdown(self):
        sections = [
            ReportSection.create("Council", "| Name |\n|------|\n| Sage |"),
            ReportSection.create("Votes", "No votes."),
        ]
        r = GovernanceReport.create("R-001", "Governance Report", sections=sections)
        md = r.to_markdown()
        assert "# Governance Report" in md
        assert "## Council" in md
        assert "| Sage |" in md
        assert "## Votes" in md
        assert "No votes." in md
        assert "R-001" in md

    def test_to_markdown_empty_sections(self):
        r = GovernanceReport.create("R-001", "Empty Report")
        md = r.to_markdown()
        assert "# Empty Report" in md
        assert "R-001" in md


# ═══════════════════════════════════════════════════════════════
# ReportGenerator Init
# ═══════════════════════════════════════════════════════════════


class TestReportGeneratorInit:
    def test_with_all_managers(self, tmp_path):
        registry = _FakeRegistry()
        pm = _make_proposal_manager(tmp_path)
        ve = _make_voting_engine(tmp_path)
        cm = _make_character_manager(tmp_path)
        analytics = _FakeAnalytics()

        gen = ReportGenerator(
            registry=registry,
            proposal_manager=pm,
            voting_engine=ve,
            character_manager=cm,
            analytics_engine=analytics,
            reports_dir=tmp_path / "reports",
        )
        assert gen.registry is registry
        assert gen.proposal_manager is pm
        assert gen.voting_engine is ve
        assert gen.character_manager is cm
        assert gen.analytics_engine is analytics

    def test_with_no_managers(self):
        gen = ReportGenerator()
        assert gen.registry is None
        assert gen.proposal_manager is None
        assert gen.voting_engine is None
        assert gen.character_manager is None
        assert gen.analytics_engine is None

    def test_repr(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        gen = ReportGenerator(proposal_manager=pm)
        r = repr(gen)
        assert "ReportGenerator" in r
        assert "proposals" in r
        assert "registry" not in r


# ═══════════════════════════════════════════════════════════════
# Council Roster Section
# ═══════════════════════════════════════════════════════════════


class TestCouncilRosterSection:
    def test_generates_table(self):
        members = [
            _FakeMember("Sage", "Ethics Officer", specialties=["ethics"]),
            _FakeMember("Logic", "Systems Analyst", specialties=["systems", "analysis"]),
        ]
        gen = ReportGenerator(registry=_FakeRegistry(members))
        section = gen.council_roster_section()

        assert section is not None
        assert section.title == "Council Roster"
        assert section.section_type == "council"
        assert "Sage" in section.content
        assert "Logic" in section.content
        assert "| Name |" in section.content
        assert "2 council members" in section.content

    def test_empty_registry(self):
        gen = ReportGenerator(registry=_FakeRegistry([]))
        section = gen.council_roster_section()
        assert section is not None
        assert "No council members found" in section.content

    def test_no_registry(self):
        gen = ReportGenerator()
        section = gen.council_roster_section()
        assert section is None

    def test_specialties_formatting(self):
        members = [
            _FakeMember("Sage", specialties=["ethics", "philosophy", "morality"]),
        ]
        gen = ReportGenerator(registry=_FakeRegistry(members))
        section = gen.council_roster_section()
        assert "ethics, philosophy, morality" in section.content

    def test_empty_specialties(self):
        members = [_FakeMember("Sage", specialties=[])]
        gen = ReportGenerator(registry=_FakeRegistry(members))
        section = gen.council_roster_section()
        assert "—" in section.content


# ═══════════════════════════════════════════════════════════════
# Proposals Section
# ═══════════════════════════════════════════════════════════════



class TestProposalsSection:
    def test_generates_table(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm, 3)
        gen = ReportGenerator(proposal_manager=pm)
        section = gen.proposals_section()

        assert section is not None
        assert section.title == "Proposals"
        assert section.section_type == "proposals"
        assert "3 proposals" in section.content
        assert "P-0001" in section.content
        assert "Sage" in section.content

    def test_with_status_filter(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm, 3)
        pm.update_status("P-0001", "open")

        gen = ReportGenerator(proposal_manager=pm)
        section = gen.proposals_section(status="open")
        assert section is not None
        assert "1 proposals" in section.content

    def test_empty_proposals(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        gen = ReportGenerator(proposal_manager=pm)
        section = gen.proposals_section()
        assert section is not None
        assert "No proposals found" in section.content

    def test_no_proposal_manager(self):
        gen = ReportGenerator()
        section = gen.proposals_section()
        assert section is None

    def test_includes_detail(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Ethics Review", "Review framework", author="Sage", category="ethics")
        gen = ReportGenerator(proposal_manager=pm)
        section = gen.proposals_section()
        assert "### P-0001: Ethics Review" in section.content
        assert "**Author:** Sage" in section.content

    def test_includes_reviews(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        p = pm.create("Test", "Desc", author="Sage", category="ethics")
        pm.update_status(p.id, "open")
        review = Review.create("Logic", "support", comment="Looks good")
        pm.add_review(p.id, review)

        gen = ReportGenerator(proposal_manager=pm)
        section = gen.proposals_section()
        assert "Logic" in section.content
        assert "support" in section.content
        assert "Looks good" in section.content


# ═══════════════════════════════════════════════════════════════
# Voting Section
# ═══════════════════════════════════════════════════════════════


class TestVotingSection:
    def test_generates_table(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        proposals = _seed_proposals(pm, 2)
        ve = _make_voting_engine(tmp_path)
        _seed_votes(ve, [p.id for p in proposals])

        gen = ReportGenerator(voting_engine=ve)
        section = gen.voting_section()

        assert section is not None
        assert section.title == "Vote Records"
        assert section.section_type == "votes"
        assert "2 vote records" in section.content
        assert "P-0001" in section.content

    def test_shows_tally(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))
        ve.cast_vote("P-0001", Vote.create("Spark", "against"))

        gen = ReportGenerator(voting_engine=ve)
        section = gen.voting_section()
        # 2 for, 1 against = 67% approval
        assert "67%" in section.content
        assert "✅" in section.content  # quorum met (2 >= 2)

    def test_empty_records(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        gen = ReportGenerator(voting_engine=ve)
        section = gen.voting_section()
        assert "No vote records found" in section.content

    def test_no_voting_engine(self):
        gen = ReportGenerator()
        section = gen.voting_section()
        assert section is None

    def test_veto_indicator(self, tmp_path):
        ve = _make_voting_engine(tmp_path)
        ve.open_voting("P-0001")
        ve.veto("P-0001", "Overruled")
        gen = ReportGenerator(voting_engine=ve)
        section = gen.voting_section()
        assert "🚫" in section.content


# ═══════════════════════════════════════════════════════════════
# Characters Section
# ═══════════════════════════════════════════════════════════════


class TestCharactersSection:
    def test_generates_table(self, tmp_path):
        cm = _make_character_manager(tmp_path)
        _seed_characters(cm, 2)
        gen = ReportGenerator(character_manager=cm)
        section = gen.characters_section()

        assert section is not None
        assert section.title == "Characters"
        assert section.section_type == "characters"
        assert "2 character templates" in section.content
        assert "Character 1" in section.content

    def test_includes_traits(self, tmp_path):
        cm = _make_character_manager(tmp_path)
        _seed_characters(cm, 1)
        gen = ReportGenerator(character_manager=cm)
        section = gen.characters_section()
        assert "trait_0" in section.content
        assert "70%" in section.content

    def test_includes_tags(self, tmp_path):
        cm = _make_character_manager(tmp_path)
        _seed_characters(cm, 1)
        gen = ReportGenerator(character_manager=cm)
        section = gen.characters_section()
        assert "#test" in section.content

    def test_empty_characters(self, tmp_path):
        cm = _make_character_manager(tmp_path)
        gen = ReportGenerator(character_manager=cm)
        section = gen.characters_section()
        assert "No characters found" in section.content

    def test_no_character_manager(self):
        gen = ReportGenerator()
        section = gen.characters_section()
        assert section is None

    def test_with_status_filter(self, tmp_path):
        cm = _make_character_manager(tmp_path)
        chars = _seed_characters(cm, 2)
        cm.update_status(chars[0].id, "active")
        gen = ReportGenerator(character_manager=cm)
        section = gen.characters_section(status="active")
        assert "1 character templates" in section.content


# ═══════════════════════════════════════════════════════════════
# Analytics Section
# ═══════════════════════════════════════════════════════════════


class TestAnalyticsSection:
    def test_generates_content(self):
        gen = ReportGenerator(analytics_engine=_FakeAnalytics())
        section = gen.analytics_section()

        assert section is not None
        assert section.title == "Analytics"
        assert section.section_type == "analytics"
        assert "Proposal Statistics" in section.content
        assert "Voting Statistics" in section.content
        assert "Session Statistics" in section.content

    def test_includes_stats(self):
        gen = ReportGenerator(analytics_engine=_FakeAnalytics())
        section = gen.analytics_section()
        assert "Total proposals:** 5" in section.content
        assert "Total records:** 3" in section.content
        assert "Total sessions:** 4" in section.content

    def test_includes_top_participants(self):
        gen = ReportGenerator(analytics_engine=_FakeAnalytics())
        section = gen.analytics_section()
        assert "Top Participants" in section.content
        assert "Sage" in section.content
        assert "Logic" in section.content

    def test_no_analytics_engine(self):
        gen = ReportGenerator()
        section = gen.analytics_section()
        assert section is None


# ═══════════════════════════════════════════════════════════════
# Full Report
# ═══════════════════════════════════════════════════════════════


class TestFullReport:
    def test_generates_report(self, tmp_path):
        members = [_FakeMember("Sage")]
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm, 2)

        gen = ReportGenerator(
            registry=_FakeRegistry(members),
            proposal_manager=pm,
            reports_dir=tmp_path / "reports",
        )
        report = gen.full_report()

        assert report.report_id.startswith("R-")
        assert report.title == "Jericho AI Council — Governance Report"
        assert len(report.sections) >= 2  # council + proposals
        assert report.generated_at != ""

    def test_custom_title(self, tmp_path):
        gen = ReportGenerator(
            registry=_FakeRegistry([_FakeMember("Sage")]),
            reports_dir=tmp_path / "reports",
        )
        report = gen.full_report(title="Custom Report")
        assert report.title == "Custom Report"

    def test_custom_report_id(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        report = gen.full_report(report_id="MY-REPORT")
        assert report.report_id == "MY-REPORT"

    def test_selective_sections(self, tmp_path):
        members = [_FakeMember("Sage")]
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm)

        gen = ReportGenerator(
            registry=_FakeRegistry(members),
            proposal_manager=pm,
            reports_dir=tmp_path / "reports",
        )
        report = gen.full_report(sections=["council"])
        # Only council section should be present
        assert len(report.sections) == 1
        assert report.sections[0].section_type == "council"

    def test_graceful_degradation(self, tmp_path):
        """All managers are None — report has no sections."""
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        report = gen.full_report()
        assert report.sections == []
        assert report.report_id.startswith("R-")

    def test_metadata_includes_requested(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        report = gen.full_report(sections=["council", "votes"])
        assert report.metadata["requested_sections"] == ["council", "votes"]

    def test_to_markdown_output(self, tmp_path):
        members = [_FakeMember("Sage")]
        gen = ReportGenerator(
            registry=_FakeRegistry(members),
            analytics_engine=_FakeAnalytics(),
            reports_dir=tmp_path / "reports",
        )
        report = gen.full_report()
        md = report.to_markdown()
        assert "## Council Roster" in md
        assert "## Analytics" in md
        assert "Sage" in md


# ═══════════════════════════════════════════════════════════════
# Save / List / Get Reports
# ═══════════════════════════════════════════════════════════════


class TestReportPersistence:
    def test_save_report(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        report = GovernanceReport.create("R-TEST", "Test Report")
        path = gen.save_report(report)

        assert path.exists()
        assert path.name == "R-TEST.md"
        content = path.read_text(encoding="utf-8")
        assert "# Test Report" in content

    def test_save_custom_path(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        report = GovernanceReport.create("R-CUSTOM", "Custom")
        custom = tmp_path / "custom_output" / "my_report.md"
        path = gen.save_report(report, path=custom)

        assert path == custom
        assert path.exists()

    def test_save_creates_directory(self, tmp_path):
        reports_dir = tmp_path / "nested" / "reports"
        gen = ReportGenerator(reports_dir=reports_dir)
        report = GovernanceReport.create("R-001", "Test")
        path = gen.save_report(report)
        assert path.exists()

    def test_list_reports_empty(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        assert gen.list_reports() == []

    def test_list_reports(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        r1 = GovernanceReport.create("R-001", "First Report")
        r2 = GovernanceReport.create("R-002", "Second Report")
        gen.save_report(r1)
        gen.save_report(r2)

        reports = gen.list_reports()
        assert len(reports) == 2
        assert reports[0]["report_id"] == "R-001"
        assert reports[1]["report_id"] == "R-002"

    def test_get_report(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        report = GovernanceReport.create("R-001", "My Report")
        gen.save_report(report)

        content = gen.get_report("R-001")
        assert "# My Report" in content

    def test_get_report_not_found(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        with pytest.raises(ReportNotFoundError) as exc_info:
            gen.get_report("R-MISSING")
        assert exc_info.value.report_id == "R-MISSING"

    def test_save_overwrites(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        r1 = GovernanceReport.create("R-001", "Version 1")
        r2 = GovernanceReport.create("R-001", "Version 2")
        gen.save_report(r1)
        gen.save_report(r2)

        content = gen.get_report("R-001")
        assert "Version 2" in content
        assert "Version 1" not in content


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    def test_unicode_content(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        pm.create("Éthique 🌍", "Description avec des accents", author="Sage", category="ethics")
        gen = ReportGenerator(proposal_manager=pm, reports_dir=tmp_path / "reports")
        section = gen.proposals_section()
        assert "Éthique 🌍" in section.content

    def test_unicode_in_report(self, tmp_path):
        gen = ReportGenerator(reports_dir=tmp_path / "reports")
        section = ReportSection.create("Cöuncil", "Ünîcödé content 日本語")
        report = GovernanceReport.create("R-001", "Ünîcödé Report", sections=[section])
        path = gen.save_report(report)
        content = path.read_text(encoding="utf-8")
        assert "Ünîcödé" in content
        assert "日本語" in content

    def test_long_proposal_title_truncated(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        long_title = "A" * 100
        pm.create(long_title, "Desc", author="Sage", category="ethics")
        gen = ReportGenerator(proposal_manager=pm)
        section = gen.proposals_section()
        # Table row should have truncated title
        assert "…" in section.content

    def test_many_proposals(self, tmp_path):
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm, 20)
        gen = ReportGenerator(proposal_manager=pm)
        section = gen.proposals_section()
        assert "20 proposals" in section.content

    def test_many_characters(self, tmp_path):
        cm = _make_character_manager(tmp_path)
        _seed_characters(cm, 10)
        gen = ReportGenerator(character_manager=cm)
        section = gen.characters_section()
        assert "10 character templates" in section.content

    def test_full_lifecycle(self, tmp_path):
        """Generate, save, list, get — full lifecycle."""
        members = [_FakeMember("Sage"), _FakeMember("Logic")]
        pm = _make_proposal_manager(tmp_path)
        _seed_proposals(pm, 2)
        ve = _make_voting_engine(tmp_path)
        _seed_votes(ve, ["P-0001"])

        gen = ReportGenerator(
            registry=_FakeRegistry(members),
            proposal_manager=pm,
            voting_engine=ve,
            analytics_engine=_FakeAnalytics(),
            reports_dir=tmp_path / "reports",
        )

        # Generate
        report = gen.full_report(report_id="R-LIFECYCLE")
        assert len(report.sections) >= 3

        # Save
        path = gen.save_report(report)
        assert path.exists()

        # List
        reports = gen.list_reports()
        assert len(reports) == 1

        # Get
        content = gen.get_report("R-LIFECYCLE")
        assert "Sage" in content
        assert "P-0001" in content

    def test_report_id_generation(self):
        gen = ReportGenerator()
        report = gen.full_report()
        assert report.report_id.startswith("R-")
        assert len(report.report_id) > 5  # R- + timestamp


# ═══════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(ReportNotFoundError, ReportError)
        assert issubclass(ReportValidationError, ReportError)
        assert issubclass(ReportError, Exception)

    def test_not_found_fields(self):
        e = ReportNotFoundError("R-001")
        assert e.report_id == "R-001"
        assert "R-001" in str(e)

    def test_validation_fields(self):
        e = ReportValidationError(["error1", "error2"])
        assert e.errors == ["error1", "error2"]
        assert "error1" in str(e)
        assert "error2" in str(e)

    def test_base_exception(self):
        e = ReportError("test")
        assert str(e) == "test"
