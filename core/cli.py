"""
Jericho — CLI Interface (F-014 + F-015 Rich Dashboard)

Click-based 'jericho' command with subcommands for council, proposals,
vote, characters, and status.  Output is rendered with Rich via the
:class:`~core.dashboard.DashboardRenderer`.

Entry point: ``jericho = "core.cli:cli"`` (configured in pyproject.toml).
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from config.settings import (
    CHARACTERS_DIR,
    COUNCIL_MEMBERS_DIR,
    PROPOSALS_DIR,
    VOTES_DIR,
)
from core.characters import CharacterManager, CharacterNotFoundError
from core.dashboard import DashboardRenderer
from core.proposals import ProposalManager, ProposalNotFoundError
from core.registry import CouncilRegistry, MemberNotFoundError
from core.voting import VoteNotFoundError, VotingEngine

# Module-level renderer — used by all commands.
_renderer = DashboardRenderer()


# ─── Helpers ───────────────────────────────────────────────────


def _error(message: str) -> None:
    """Print an error message to stderr and exit."""
    click.echo(f"Error: {message}", err=True)
    sys.exit(1)


def _load_registry(members_dir: Path | None = None) -> CouncilRegistry:
    """Load the council registry, handling common errors."""
    try:
        return CouncilRegistry(members_dir).load()
    except FileNotFoundError as exc:
        _error(str(exc))
    except Exception as exc:
        _error(f"Failed to load council registry: {exc}")


# ─── Top-Level CLI Group ──────────────────────────────────────


@click.group()
@click.version_option(version="0.1.0", prog_name="jericho")
def cli() -> None:
    """Jericho AI Council — collaborative AI character design through democratic governance."""


# ═══════════════════════════════════════════════════════════════
# Council Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def council() -> None:
    """Manage council members."""


@council.command("list")
@click.option("--provider", type=str, default=None, help="Filter by API provider (openrouter/mancer).")
def council_list(provider: str | None) -> None:
    """List all council members."""
    registry = _load_registry()

    if provider:
        members = registry.members_by_provider(provider)
    else:
        members = registry.list_members()

    _renderer.render_member_list(members)


@council.command("show")
@click.argument("name")
def council_show(name: str) -> None:
    """Show details for a specific council member."""
    registry = _load_registry()

    try:
        member = registry.get(name)
    except MemberNotFoundError:
        _error(f"Council member '{name}' not found.")
        return  # pragma: no cover — _error exits

    _renderer.render_member_detail(member)


# ═══════════════════════════════════════════════════════════════
# Proposals Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def proposals() -> None:
    """Manage governance proposals."""


@proposals.command("list")
@click.option("--status", type=str, default=None, help="Filter by status.")
@click.option("--category", type=str, default=None, help="Filter by category.")
@click.option("--author", type=str, default=None, help="Filter by author.")
def proposals_list(status: str | None, category: str | None, author: str | None) -> None:
    """List proposals with optional filters."""
    mgr = ProposalManager()
    items = mgr.list_proposals(status=status, category=category, author=author)

    _renderer.render_proposal_list(items)


@proposals.command("show")
@click.argument("proposal_id")
def proposals_show(proposal_id: str) -> None:
    """Show full details of a proposal."""
    mgr = ProposalManager()

    try:
        p = mgr.get(proposal_id)
    except ProposalNotFoundError:
        _error(f"Proposal '{proposal_id}' not found.")
        return

    _renderer.render_proposal_detail(p)


@proposals.command("create")
@click.option("--title", required=True, help="Proposal title.")
@click.option("--description", "desc", required=True, help="Proposal description.")
@click.option("--author", required=True, help="Author name.")
@click.option("--category", required=True, help="Category (character/governance/ethics/expansion/general).")
@click.option("--body", default="", help="Optional detailed body text.")
def proposals_create(title: str, desc: str, author: str, category: str, body: str) -> None:
    """Create a new proposal."""
    mgr = ProposalManager()

    try:
        p = mgr.create(title, desc, author=author, category=category, body=body)
    except Exception as exc:
        _error(str(exc))
        return

    _renderer.render_success(f"Created proposal {p.id}: {p.title}")


# ═══════════════════════════════════════════════════════════════
# Vote Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def vote() -> None:
    """Manage voting on proposals."""


@vote.command("list")
@click.option("--status", type=str, default=None, help="Filter by status (open/closed).")
def vote_list(status: str | None) -> None:
    """List vote records."""
    engine = VotingEngine()
    records = engine.list_records(status=status)

    _renderer.render_vote_list(records)


@vote.command("show")
@click.argument("proposal_id")
def vote_show(proposal_id: str) -> None:
    """Show vote tally for a proposal."""
    engine = VotingEngine()

    try:
        tally = engine.tally(proposal_id)
        record = engine.get(proposal_id)
    except VoteNotFoundError:
        _error(f"No vote record for proposal '{proposal_id}'.")
        return

    _renderer.render_vote_detail(tally, record)


@vote.command("cast")
@click.argument("proposal_id")
@click.option("--voter", required=True, help="Voter name.")
@click.option("--choice", required=True, type=click.Choice(["for", "against", "abstain"]), help="Vote choice.")
@click.option("--reason", default="", help="Optional reason for the vote.")
@click.option("--weight", default=1.0, type=float, help="Vote weight (default 1.0).")
def vote_cast(proposal_id: str, voter: str, choice: str, reason: str, weight: float) -> None:
    """Cast a vote on a proposal."""
    from core.voting import Vote

    engine = VotingEngine()

    try:
        v = Vote.create(voter=voter, choice=choice, reason=reason, weight=weight)
        engine.cast_vote(proposal_id, v)
    except Exception as exc:
        _error(str(exc))
        return

    _renderer.render_success(f"Vote cast: {voter} voted '{choice}' on {proposal_id}")


@vote.command("veto")
@click.argument("proposal_id")
@click.option("--reason", default="", help="Reason for the veto.")
def vote_veto(proposal_id: str, reason: str) -> None:
    """Apply human veto to a proposal vote."""
    engine = VotingEngine()

    try:
        engine.veto(proposal_id, reason=reason)
    except Exception as exc:
        _error(str(exc))
        return

    _renderer.render_success(f"Veto applied to {proposal_id}")


# ═══════════════════════════════════════════════════════════════
# Characters Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def characters() -> None:
    """Manage AI character templates."""


@characters.command("list")
@click.option("--status", type=str, default=None, help="Filter by status.")
@click.option("--author", type=str, default=None, help="Filter by author.")
@click.option("--tag", type=str, default=None, help="Filter by tag.")
def characters_list(status: str | None, author: str | None, tag: str | None) -> None:
    """List character templates."""
    mgr = CharacterManager()
    items = mgr.list_characters(status=status, author=author, tag=tag)

    _renderer.render_character_list(items)


@characters.command("show")
@click.argument("character_id")
def characters_show(character_id: str) -> None:
    """Show details for a character template."""
    mgr = CharacterManager()

    try:
        c = mgr.get(character_id)
    except CharacterNotFoundError:
        _error(f"Character '{character_id}' not found.")
        return

    _renderer.render_character_detail(c)


@characters.command("export")
@click.argument("character_id")
@click.option("--output", "output_path", type=click.Path(), default=None, help="Output file path.")
def characters_export(character_id: str, output_path: str | None) -> None:
    """Export a character template as YAML."""
    mgr = CharacterManager()

    try:
        out = Path(output_path) if output_path else None
        yaml_str = mgr.export_yaml(character_id, output_path=out)
    except CharacterNotFoundError:
        _error(f"Character '{character_id}' not found.")
        return
    except Exception as exc:
        _error(str(exc))
        return

    if output_path:
        _renderer.render_success(f"Exported {character_id} to {output_path}")
    else:
        click.echo(yaml_str)


# ═══════════════════════════════════════════════════════════════
# Analytics Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def analytics() -> None:
    """View session analytics — participation, voting patterns, proposals."""


@analytics.command("overview")
def analytics_overview() -> None:
    """Show full analytics report: proposals, voting, sessions, top members."""
    from core.analytics import SessionAnalytics

    pmgr = ProposalManager()
    engine = VotingEngine()
    sa = SessionAnalytics(proposal_manager=pmgr, voting_engine=engine)

    try:
        report = sa.full_report()
    except Exception as exc:
        _error(f"Failed to generate analytics report: {exc}")
        return

    _renderer.render_analytics_overview(report)


@analytics.command("member")
@click.argument("name")
def analytics_member(name: str) -> None:
    """Show activity stats for a specific council member."""
    from core.analytics import SessionAnalytics

    pmgr = ProposalManager()
    engine = VotingEngine()
    sa = SessionAnalytics(proposal_manager=pmgr, voting_engine=engine)

    try:
        stats = sa.member_stats(name)
    except Exception as exc:
        _error(f"Failed to get stats for '{name}': {exc}")
        return

    _renderer.render_member_stats(name, stats)


# ═══════════════════════════════════════════════════════════════
# Memory Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def memory() -> None:
    """View agent memory — core beliefs and recent session memories."""


@memory.command("beliefs")
@click.argument("member_name")
def memory_beliefs(member_name: str) -> None:
    """Show core beliefs for a council member."""
    from core.memory import AgentMemory

    agent_mem = AgentMemory(member_name)

    try:
        beliefs = agent_mem.read_core_beliefs()
    except Exception as exc:
        _error(f"Failed to read beliefs for '{member_name}': {exc}")
        return

    _renderer.render_member_beliefs(member_name, beliefs)


@memory.command("recent")
@click.argument("member_name")
@click.option("--limit", default=10, type=int, help="Number of recent memories to show.")
def memory_recent(member_name: str, limit: int) -> None:
    """Show recent session memories for a council member."""
    from core.memory import AgentMemory

    agent_mem = AgentMemory(member_name)

    try:
        memories = agent_mem.get_recent_memories(limit=limit)
    except Exception as exc:
        _error(f"Failed to read memories for '{member_name}': {exc}")
        return

    _renderer.render_recent_memories(member_name, memories)


# ═══════════════════════════════════════════════════════════════
# Expansion Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def expansion() -> None:
    """Manage council expansion proposals."""


@expansion.command("list")
@click.option("--status", type=str, default=None, help="Filter by status.")
@click.option("--author", type=str, default=None, help="Filter by author.")
def expansion_list(status: str | None, author: str | None) -> None:
    """List council expansion records."""
    from core.council_expansion import CouncilExpansion

    registry = _load_registry()
    proposals_mgr = ProposalManager()
    engine = VotingEngine()
    exp = CouncilExpansion(
        registry=registry,
        proposal_manager=proposals_mgr,
        voting_engine=engine,
    )
    records = exp.list_expansions(status=status, author=author)
    _renderer.render_expansion_list(records)


@expansion.command("show")
@click.argument("expansion_id")
def expansion_show(expansion_id: str) -> None:
    """Show details for a council expansion record."""
    from core.council_expansion import CouncilExpansion, ExpansionNotFoundError

    registry = _load_registry()
    proposals_mgr = ProposalManager()
    engine = VotingEngine()
    exp = CouncilExpansion(
        registry=registry,
        proposal_manager=proposals_mgr,
        voting_engine=engine,
    )
    try:
        record = exp.get(expansion_id)
    except ExpansionNotFoundError:
        _error(f"Expansion '{expansion_id}' not found.")
        return

    _renderer.render_expansion_detail(record)


# ═══════════════════════════════════════════════════════════════
# History Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def history() -> None:
    """View character evolution history — timelines, version diffs."""


@history.command("timeline")
@click.argument("character_id")
def history_timeline(character_id: str) -> None:
    """Show the full evolution timeline for a character lineage."""
    from core.evolution_history import EvolutionHistory

    chars = CharacterManager()

    # Optionally load evolution manager if available
    evo_mgr = None
    try:
        from core.character_evolution import CharacterEvolution
        from core.proposals import ProposalManager as _PM
        from core.voting import VotingEngine as _VE

        evo_mgr = CharacterEvolution(
            character_manager=chars,
            proposal_manager=_PM(),
            voting_engine=_VE(),
        )
    except Exception:
        pass  # proceed without evolution data

    hist = EvolutionHistory(character_manager=chars, evolution_manager=evo_mgr)

    try:
        timeline = hist.build_timeline(character_id)
    except Exception as exc:
        _error(f"Failed to build timeline for '{character_id}': {exc}")
        return

    _renderer.render_evolution_timeline(timeline)


@history.command("diff")
@click.argument("old_id")
@click.argument("new_id")
def history_diff(old_id: str, new_id: str) -> None:
    """Compare two character versions side by side."""
    from core.evolution_history import EvolutionHistory

    chars = CharacterManager()
    hist = EvolutionHistory(character_manager=chars)

    try:
        diffs = hist.diff_versions(old_id, new_id)
    except Exception as exc:
        _error(f"Failed to diff '{old_id}' and '{new_id}': {exc}")
        return

    _renderer.render_version_diff(old_id, new_id, diffs)


@history.command("list")
def history_list() -> None:
    """List all characters with their evolution history."""
    from core.evolution_history import EvolutionHistory

    chars = CharacterManager()

    evo_mgr = None
    try:
        from core.character_evolution import CharacterEvolution
        from core.proposals import ProposalManager as _PM
        from core.voting import VotingEngine as _VE

        evo_mgr = CharacterEvolution(
            character_manager=chars,
            proposal_manager=_PM(),
            voting_engine=_VE(),
        )
    except Exception:
        pass

    hist = EvolutionHistory(character_manager=chars, evolution_manager=evo_mgr)

    try:
        timelines = hist.list_timelines()
    except Exception as exc:
        _error(f"Failed to list timelines: {exc}")
        return

    _renderer.render_timeline_list(timelines)


# ═══════════════════════════════════════════════════════════════
# Status Command
# ═══════════════════════════════════════════════════════════════


@cli.command()
def status() -> None:
    """Show project overview — counts of members, proposals, characters, votes."""
    stats: dict = {}

    # Council members
    try:
        registry = CouncilRegistry().load()
        stats["members"] = len(registry)
        providers: dict[str, int] = {}
        for m in registry:
            providers[m.api_provider] = providers.get(m.api_provider, 0) + 1
        stats["providers"] = providers
    except Exception:
        stats["members"] = None

    # Proposals
    try:
        pmgr = ProposalManager()
        all_proposals = pmgr.list_proposals()
        stats["proposals"] = len(all_proposals)
        statuses: dict[str, int] = {}
        for p in all_proposals:
            statuses[p.status] = statuses.get(p.status, 0) + 1
        stats["proposal_statuses"] = statuses
    except Exception:
        stats["proposals"] = None

    # Vote records
    try:
        engine = VotingEngine()
        all_records = engine.list_records()
        stats["votes"] = len(all_records)
        vote_statuses: dict[str, int] = {}
        for r in all_records:
            vote_statuses[r.status] = vote_statuses.get(r.status, 0) + 1
        stats["vote_statuses"] = vote_statuses
    except Exception:
        stats["votes"] = None

    # Characters
    try:
        cmgr = CharacterManager()
        all_chars = cmgr.list_characters()
        stats["characters"] = len(all_chars)
        char_statuses: dict[str, int] = {}
        for c in all_chars:
            char_statuses[c.status] = char_statuses.get(c.status, 0) + 1
        stats["character_statuses"] = char_statuses
    except Exception:
        stats["characters"] = None

    _renderer.render_status_dashboard(stats)


# ═══════════════════════════════════════════════════════════════
# Report Commands
# ═══════════════════════════════════════════════════════════════


@cli.group()
def report() -> None:
    """Generate and manage governance reports."""


@report.command("generate")
@click.option("--title", default=None, help="Custom report title.")
@click.option("--sections", default=None, help="Comma-separated sections to include (council,proposals,votes,characters,analytics).")
@click.option("--output", "output_path", type=click.Path(), default=None, help="Save report to this file path.")
@click.option("--save", is_flag=True, default=False, help="Save report to the default reports directory.")
def report_generate(title: str | None, sections: str | None, output_path: str | None, save: bool) -> None:
    """Generate a governance report as Markdown."""
    from core.analytics import SessionAnalytics
    from core.reports import ReportGenerator

    registry = None
    try:
        registry = CouncilRegistry().load()
    except Exception:
        pass

    pmgr = ProposalManager()
    engine = VotingEngine()
    cmgr = CharacterManager()
    analytics = SessionAnalytics(proposal_manager=pmgr, voting_engine=engine)

    gen = ReportGenerator(
        registry=registry,
        proposal_manager=pmgr,
        voting_engine=engine,
        character_manager=cmgr,
        analytics_engine=analytics,
    )

    section_list = [s.strip() for s in sections.split(",")] if sections else None

    try:
        rpt = gen.full_report(title=title, sections=section_list)
    except Exception as exc:
        _error(f"Failed to generate report: {exc}")
        return

    if output_path:
        path = gen.save_report(rpt, path=Path(output_path))
        _renderer.render_success(f"Report saved to {path}")
    elif save:
        path = gen.save_report(rpt)
        _renderer.render_success(f"Report saved to {path}")
    else:
        click.echo(rpt.to_markdown())


@report.command("list")
def report_list() -> None:
    """List previously generated reports."""
    from core.reports import ReportGenerator

    gen = ReportGenerator()
    reports = gen.list_reports()

    if not reports:
        click.echo("No saved reports found.")
        return

    _renderer.render_success(f"Found {len(reports)} saved reports:")
    for r in reports:
        click.echo(f"  • {r['report_id']}  ({r['filename']})")


# ═══════════════════════════════════════════════════════════════
# Web Dashboard Command
# ═══════════════════════════════════════════════════════════════


@cli.command()
@click.option("--host", default="127.0.0.1", help="Host to bind to.")
@click.option("--port", default=8080, type=int, help="Port to listen on.")
def web(host: str, port: int) -> None:
    """Launch the web dashboard in your browser."""
    import uvicorn

    click.echo(f"🏛️  Jericho Web Dashboard → http://{host}:{port}")
    uvicorn.run("core.web_api:app", host=host, port=port, log_level="info")


# ─── Entry Point ──────────────────────────────────────────────

if __name__ == "__main__":
    cli()
