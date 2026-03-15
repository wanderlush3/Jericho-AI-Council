"""
Jericho — Governance Report Generator (F-022)

Read-only engine that aggregates data from existing managers and produces
structured Markdown documents covering council roster, proposals, votes,
characters, and analytics.

This module performs **no reads of its own** — it delegates to existing
managers and formats the results as shareable Markdown reports.

Usage::

    from core.reports import ReportGenerator

    generator = ReportGenerator(
        registry=CouncilRegistry().load(),
        proposal_manager=ProposalManager(),
        voting_engine=VotingEngine(),
        character_manager=CharacterManager(),
        analytics_engine=SessionAnalytics(...),
    )
    report = generator.full_report()
    md = report.to_markdown()
    generator.save_report(report)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import REPORTS_DIR, REPORT_SECTIONS
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class ReportError(Exception):
    """Base exception for report errors."""


class ReportNotFoundError(ReportError):
    """Raised when a saved report cannot be found."""

    def __init__(self, report_id: str) -> None:
        self.report_id = report_id
        super().__init__(f"Report '{report_id}' not found.")


class ReportValidationError(ReportError):
    """Raised when report input data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ReportSection:
    """A single section of a governance report."""

    title: str
    content: str
    section_type: str = "general"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReportSection:
        return cls(
            title=data["title"],
            content=data["content"],
            section_type=data.get("section_type", "general"),
        )

    @classmethod
    def create(
        cls,
        title: str,
        content: str,
        section_type: str = "general",
    ) -> ReportSection:
        return cls(
            title=title.strip(),
            content=content,
            section_type=section_type.strip(),
        )


@dataclass(frozen=True)
class GovernanceReport:
    """A complete governance report composed of sections."""

    report_id: str
    title: str
    sections: list[ReportSection] = field(default_factory=list)
    generated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "title": self.title,
            "sections": [s.to_dict() for s in self.sections],
            "generated_at": self.generated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GovernanceReport:
        return cls(
            report_id=data["report_id"],
            title=data["title"],
            sections=[ReportSection.from_dict(s) for s in data.get("sections", [])],
            generated_at=data.get("generated_at", ""),
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def create(
        cls,
        report_id: str,
        title: str,
        sections: list[ReportSection] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GovernanceReport:
        report_id = report_id.strip()
        title = title.strip()
        if not report_id:
            raise ReportValidationError(["report_id cannot be empty"])
        if not title:
            raise ReportValidationError(["title cannot be empty"])
        return cls(
            report_id=report_id,
            title=title,
            sections=list(sections or []),
            generated_at=datetime.now(timezone.utc).isoformat(),
            metadata=dict(metadata or {}),
        )

    def to_markdown(self) -> str:
        """Render the full report as a Markdown document."""
        lines: list[str] = []
        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(f"*Generated: {self.generated_at}*  ")
        lines.append(f"*Report ID: {self.report_id}*")
        lines.append("")

        for section in self.sections:
            lines.append(f"## {section.title}")
            lines.append("")
            lines.append(section.content)
            lines.append("")

        return "\n".join(lines)


# ─── Report Generator ─────────────────────────────────────────


class ReportGenerator:
    """
    Read-only governance report generator for the Jericho AI Council.

    Aggregates data from existing managers and produces structured
    Markdown report documents.  All managers are optional — sections
    for unavailable managers are silently skipped.

    Usage::

        generator = ReportGenerator(
            registry=CouncilRegistry().load(),
            proposal_manager=ProposalManager(),
        )
        report = generator.full_report()
        generator.save_report(report)
    """

    def __init__(
        self,
        *,
        registry: Any | None = None,
        proposal_manager: Any | None = None,
        voting_engine: Any | None = None,
        character_manager: Any | None = None,
        analytics_engine: Any | None = None,
        reports_dir: Path | None = None,
    ) -> None:
        self._registry = registry
        self._proposals = proposal_manager
        self._voting = voting_engine
        self._characters = character_manager
        self._analytics = analytics_engine
        self._reports_dir = reports_dir or REPORTS_DIR

    # ── Properties ────────────────────────────────────────────

    @property
    def registry(self) -> Any | None:
        return self._registry

    @property
    def proposal_manager(self) -> Any | None:
        return self._proposals

    @property
    def voting_engine(self) -> Any | None:
        return self._voting

    @property
    def character_manager(self) -> Any | None:
        return self._characters

    @property
    def analytics_engine(self) -> Any | None:
        return self._analytics

    @property
    def reports_dir(self) -> Path:
        return self._reports_dir

    # ── Section Builders ──────────────────────────────────────

    def council_roster_section(self) -> ReportSection | None:
        """Generate a council roster section with member table."""
        if self._registry is None:
            return None

        try:
            members = self._registry.list_members()
        except Exception:
            return None

        if not members:
            return ReportSection.create(
                "Council Roster",
                "No council members found.",
                section_type="council",
            )

        lines: list[str] = []
        lines.append(f"**{len(members)} council members**")
        lines.append("")
        lines.append("| Name | Role | Provider | Model | Weight | Specialties |")
        lines.append("|------|------|----------|-------|--------|-------------|")

        for m in members:
            specialties = ", ".join(m.specialties) if m.specialties else "—"
            lines.append(
                f"| {m.name} | {m.role} | {m.api_provider} "
                f"| {m.model} | {m.vote_weight} | {specialties} |"
            )

        return ReportSection.create(
            "Council Roster",
            "\n".join(lines),
            section_type="council",
        )

    def proposals_section(
        self,
        status: str | None = None,
    ) -> ReportSection | None:
        """Generate a proposals summary section."""
        if self._proposals is None:
            return None

        try:
            proposals = self._proposals.list_proposals(status=status)
        except Exception:
            return None

        if not proposals:
            label = f" (status={status})" if status else ""
            return ReportSection.create(
                "Proposals",
                f"No proposals found{label}.",
                section_type="proposals",
            )

        lines: list[str] = []
        lines.append(f"**{len(proposals)} proposals**")
        lines.append("")
        lines.append("| ID | Title | Author | Category | Status | Reviews | Created |")
        lines.append("|----|-------|--------|----------|--------|---------|---------|")

        for p in proposals:
            title = p.title if len(p.title) <= 50 else p.title[:47] + "…"
            reviews = len(p.reviews) if p.reviews else 0
            created = p.created_at[:10] if p.created_at else "—"
            lines.append(
                f"| {p.id} | {title} | {p.author} "
                f"| {p.category} | {p.status} | {reviews} | {created} |"
            )

        # Add per-proposal detail after the table
        for p in proposals:
            lines.append("")
            lines.append(f"### {p.id}: {p.title}")
            lines.append("")
            lines.append(f"- **Author:** {p.author}")
            lines.append(f"- **Category:** {p.category}")
            lines.append(f"- **Status:** {p.status}")
            if p.description:
                lines.append(f"- **Description:** {p.description}")
            if p.reviews:
                lines.append(f"- **Reviews:** {len(p.reviews)}")
                for r in p.reviews:
                    comment = r.comment or "—"
                    lines.append(f"  - {r.reviewer}: **{r.stance}** — {comment}")

        return ReportSection.create(
            "Proposals",
            "\n".join(lines),
            section_type="proposals",
        )

    def voting_section(self) -> ReportSection | None:
        """Generate a voting summary section with tallies."""
        if self._voting is None:
            return None

        try:
            records = self._voting.list_records()
        except Exception:
            return None

        if not records:
            return ReportSection.create(
                "Vote Records",
                "No vote records found.",
                section_type="votes",
            )

        lines: list[str] = []
        lines.append(f"**{len(records)} vote records**")
        lines.append("")
        lines.append(
            "| Proposal | Status | Votes | For | Against | Abstain "
            "| Approval | Quorum | Vetoed |"
        )
        lines.append(
            "|----------|--------|-------|-----|---------|-------- "
            "|----------|--------|--------|"
        )

        for r in records:
            try:
                tally = self._voting.tally(r.proposal_id)
                v_for = tally.votes_for
                v_against = tally.votes_against
                v_abstain = tally.votes_abstain
                approval = f"{round(tally.approval_rate * 100)}%"
                quorum = "✅" if tally.quorum_met else "❌"
            except Exception:
                v_for = v_against = v_abstain = 0
                approval = "—"
                quorum = "—"

            vetoed = "🚫" if r.vetoed else "—"
            num_votes = len(r.votes) if r.votes else 0
            lines.append(
                f"| {r.proposal_id} | {r.status} | {num_votes} "
                f"| {v_for} | {v_against} | {v_abstain} "
                f"| {approval} | {quorum} | {vetoed} |"
            )

        return ReportSection.create(
            "Vote Records",
            "\n".join(lines),
            section_type="votes",
        )

    def characters_section(
        self,
        status: str | None = None,
    ) -> ReportSection | None:
        """Generate a characters summary section."""
        if self._characters is None:
            return None

        try:
            characters = self._characters.list_characters(status=status)
        except Exception:
            return None

        if not characters:
            label = f" (status={status})" if status else ""
            return ReportSection.create(
                "Characters",
                f"No characters found{label}.",
                section_type="characters",
            )

        lines: list[str] = []
        lines.append(f"**{len(characters)} character templates**")
        lines.append("")
        lines.append("| ID | Name | Author | Status | Version | Traits | Tags |")
        lines.append("|----|------|--------|--------|---------|--------|------|")

        for c in characters:
            num_traits = len(c.traits) if c.traits else 0
            tags = ", ".join(f"#{t}" for t in c.tags) if c.tags else "—"
            lines.append(
                f"| {c.id} | {c.name} | {c.author} "
                f"| {c.status} | v{c.version} | {num_traits} | {tags} |"
            )

        # Per-character detail
        for c in characters:
            lines.append("")
            lines.append(f"### {c.id}: {c.name}")
            lines.append("")
            lines.append(f"- **Author:** {c.author}")
            lines.append(f"- **Status:** {c.status}")
            lines.append(f"- **Version:** {c.version}")
            if c.description:
                lines.append(f"- **Description:** {c.description}")
            if c.traits:
                lines.append(f"- **Traits ({len(c.traits)}):**")
                for t in c.traits:
                    intensity = f"{round(t.intensity * 100)}%" if t.intensity else "—"
                    lines.append(
                        f"  - {t.name} ({t.trait_type}): "
                        f"{t.description} [{intensity}]"
                    )

        return ReportSection.create(
            "Characters",
            "\n".join(lines),
            section_type="characters",
        )

    def analytics_section(self) -> ReportSection | None:
        """Generate an analytics summary section."""
        if self._analytics is None:
            return None

        try:
            report = self._analytics.full_report()
        except Exception:
            return None

        ps = report.proposal_stats
        vs = report.voting_stats
        ss = report.session_stats
        top = report.top_participants

        lines: list[str] = []

        # Proposal stats
        lines.append("### Proposal Statistics")
        lines.append("")
        lines.append(f"- **Total proposals:** {ps.total}")
        lines.append(f"- **Approval rate:** {round(ps.approval_rate * 100)}%")
        if ps.by_status:
            lines.append("- **By status:** " + ", ".join(
                f"{k}: {v}" for k, v in ps.by_status.items()
            ))
        if ps.by_category:
            lines.append("- **By category:** " + ", ".join(
                f"{k}: {v}" for k, v in ps.by_category.items()
            ))
        lines.append("")

        # Voting stats
        lines.append("### Voting Statistics")
        lines.append("")
        lines.append(f"- **Total records:** {vs.total_records}")
        lines.append(f"- **Total votes cast:** {vs.total_votes_cast}")
        lines.append(f"- **Avg votes per record:** {vs.avg_votes_per_record}")
        lines.append(
            f"- **Quorum achievement:** "
            f"{round(vs.quorum_achievement_rate * 100)}%"
        )
        lines.append(f"- **Approval rate:** {round(vs.approval_rate * 100)}%")
        lines.append(f"- **Vetoes:** {vs.veto_count}")
        lines.append("")

        # Session stats
        lines.append("### Session Statistics")
        lines.append("")
        lines.append(f"- **Total sessions:** {ss.total_sessions}")
        lines.append(
            f"- **Avg messages per session:** {ss.avg_messages_per_session}"
        )
        lines.append(f"- **Avg participants:** {ss.avg_participants}")
        lines.append("")

        # Top participants
        if top:
            lines.append("### Top Participants")
            lines.append("")
            lines.append("| Rank | Member | Activity Score |")
            lines.append("|------|--------|----------------|")
            for i, (name, score) in enumerate(top, 1):
                lines.append(f"| #{i} | {name} | {score} |")

        return ReportSection.create(
            "Analytics",
            "\n".join(lines),
            section_type="analytics",
        )

    # ── Full Report ───────────────────────────────────────────

    def full_report(
        self,
        title: str | None = None,
        report_id: str | None = None,
        sections: list[str] | None = None,
    ) -> GovernanceReport:
        """
        Generate a comprehensive governance report.

        Args:
            title: Report title (default: "Jericho AI Council — Governance Report").
            report_id: Unique report identifier (auto-generated if omitted).
            sections: List of section types to include (default: all available).
                Valid types: "council", "proposals", "votes", "characters", "analytics".
        """
        title = title or "Jericho AI Council — Governance Report"
        report_id = report_id or self._generate_report_id()
        requested = sections or list(REPORT_SECTIONS)

        builders = {
            "council": self.council_roster_section,
            "proposals": self.proposals_section,
            "votes": self.voting_section,
            "characters": self.characters_section,
            "analytics": self.analytics_section,
        }

        built_sections: list[ReportSection] = []
        for section_name in requested:
            builder = builders.get(section_name)
            if builder is None:
                continue
            result = builder()
            if result is not None:
                built_sections.append(result)

        return GovernanceReport.create(
            report_id=report_id,
            title=title,
            sections=built_sections,
            metadata={"requested_sections": requested},
        )

    # ── Persistence ───────────────────────────────────────────

    def save_report(
        self,
        report: GovernanceReport,
        path: Path | None = None,
    ) -> Path:
        """
        Save a report as a Markdown file.

        Args:
            report: The report to save.
            path: Optional custom output path.  Defaults to
                ``REPORTS_DIR / f"{report.report_id}.md"``.

        Returns:
            The path the report was written to.
        """
        self._reports_dir.mkdir(parents=True, exist_ok=True)
        target = path or (self._reports_dir / f"{report.report_id}.md")
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(target, report.to_markdown())
        return target

    def list_reports(self) -> list[dict[str, Any]]:
        """
        List previously saved reports in the reports directory.

        Returns a list of dicts with 'report_id', 'filename', and 'path'.
        """
        if not self._reports_dir.exists():
            return []

        result: list[dict[str, Any]] = []
        for f in sorted(self._reports_dir.glob("*.md")):
            result.append({
                "report_id": f.stem,
                "filename": f.name,
                "path": str(f),
            })
        return result

    def get_report(self, report_id: str) -> str:
        """
        Read a previously saved report by its ID.

        Returns the raw Markdown content.
        """
        target = self._reports_dir / f"{report_id}.md"
        if not target.exists():
            raise ReportNotFoundError(report_id)
        return target.read_text(encoding="utf-8")

    # ── Helpers ───────────────────────────────────────────────

    def _generate_report_id(self) -> str:
        """Generate a timestamped report ID."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"R-{ts}"

    def __repr__(self) -> str:
        sources: list[str] = []
        if self._registry is not None:
            sources.append("registry")
        if self._proposals is not None:
            sources.append("proposals")
        if self._voting is not None:
            sources.append("voting")
        if self._characters is not None:
            sources.append("characters")
        if self._analytics is not None:
            sources.append("analytics")
        return f"ReportGenerator(sources=[{', '.join(sources)}])"
