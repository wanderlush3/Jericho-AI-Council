"""
Jericho — Rich Terminal Dashboard (F-015)

Rich-powered display functions for the CLI.  Every render method writes to
the console directly.  The ``Console`` is injectable for testing — create
a ``DashboardRenderer(console=Console(file=StringIO()))`` and read the
captured output.
"""

from __future__ import annotations

from typing import Any, Sequence

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


# ─── Status → colour mapping ──────────────────────────────────

STATUS_COLOURS: dict[str, str] = {
    # proposal / vote statuses
    "draft": "dim",
    "open": "green",
    "under_review": "yellow",
    "decided": "blue",
    "withdrawn": "red",
    "closed": "dim",
    # character statuses
    "active": "green",
    "archived": "dim",
    "superseded": "yellow",
    # evolution statuses
    "proposed": "cyan",
    "voting": "yellow",
    "applied": "green",
    "rejected": "red",
}


def _style_status(status: str) -> Text:
    """Return a Rich ``Text`` for *status* with its mapped colour."""
    colour = STATUS_COLOURS.get(status, "white")
    return Text(status, style=colour)


def _truncate(text: str, length: int = 60) -> str:
    """Truncate *text* to *length* characters with an ellipsis."""
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


# ─── Dashboard Renderer ──────────────────────────────────────


class DashboardRenderer:
    """Rich-powered renderer for all CLI display."""

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()

    # ── Council Members ────────────────────────────────────

    def render_member_list(self, members: Sequence[Any]) -> None:
        """Render a table of council members."""
        if not members:
            self.console.print("[dim]No council members found.[/dim]")
            return

        table = Table(
            title="Council Members",
            title_style="bold cyan",
            border_style="dim",
            show_lines=False,
        )
        table.add_column("Name", style="bold")
        table.add_column("Role")
        table.add_column("Provider", style="magenta")
        table.add_column("Model", style="dim")

        for m in members:
            table.add_row(m.name, m.role, m.api_provider, m.model)

        self.console.print(table)
        self.console.print(f"\n[bold]{len(members)}[/bold] member(s)", highlight=False)

    def render_member_detail(self, member: Any) -> None:
        """Render a detailed panel for a single council member."""
        lines: list[str] = [
            f"[bold]Name:[/bold]         {member.name}",
            f"[bold]Role:[/bold]         {member.role}",
            f"[bold]Description:[/bold]  {member.description}",
            f"[bold]Provider:[/bold]     {member.api_provider}",
            f"[bold]Model:[/bold]        {member.model}",
            f"[bold]Vote Weight:[/bold]  {member.vote_weight}",
        ]

        if member.specialties:
            lines.append(f"[bold]Specialties:[/bold]  {', '.join(member.specialties)}")

        if member.personality:
            lines.append("[bold]Personality:[/bold]")
            for key, value in member.personality.items():
                lines.append(f"  [dim]{key}:[/dim] {value}")

        panel = Panel(
            "\n".join(lines),
            title=f"[bold cyan]{member.name}[/bold cyan]",
            border_style="cyan",
        )
        self.console.print(panel)

    # ── Proposals ──────────────────────────────────────────

    def render_proposal_list(self, proposals: Sequence[Any]) -> None:
        """Render a table of proposals."""
        if not proposals:
            self.console.print("[dim]No proposals found.[/dim]")
            return

        table = Table(
            title="Proposals",
            title_style="bold cyan",
            border_style="dim",
            show_lines=False,
        )
        table.add_column("ID", style="bold")
        table.add_column("Status")
        table.add_column("Category", style="magenta")
        table.add_column("Author")
        table.add_column("Title")

        for p in proposals:
            table.add_row(
                p.id,
                _style_status(p.status),
                p.category,
                p.author,
                _truncate(p.title, 30),
            )

        self.console.print(table)
        self.console.print(f"\n[bold]{len(proposals)}[/bold] proposal(s)", highlight=False)

    def render_proposal_detail(self, proposal: Any) -> None:
        """Render a detailed panel for a single proposal."""
        lines: list[str] = [
            f"[bold]ID:[/bold]          {proposal.id}",
            f"[bold]Title:[/bold]       {proposal.title}",
            f"[bold]Author:[/bold]      {proposal.author}",
            f"[bold]Category:[/bold]    {proposal.category}",
            f"[bold]Status:[/bold]      {proposal.status}",
            f"[bold]Created:[/bold]     {proposal.created_at}",
            f"[bold]Updated:[/bold]     {proposal.updated_at}",
        ]

        if proposal.description:
            lines.append(f"\n[bold]Description:[/bold]\n  {proposal.description}")

        if proposal.body:
            lines.append(f"\n[bold]Body:[/bold]\n  {proposal.body}")

        if proposal.reviews:
            lines.append(f"\n[bold]Reviews ({len(proposal.reviews)}):[/bold]")
            for r in proposal.reviews:
                stance_col = {"support": "green", "oppose": "red", "neutral": "yellow"}.get(
                    r.stance, "white"
                )
                lines.append(
                    f"  [{stance_col}]\[{r.stance}][/{stance_col}] {r.reviewer}: {r.comment}"
                )

        panel = Panel(
            "\n".join(lines),
            title=f"[bold cyan]{proposal.id}[/bold cyan]",
            border_style="cyan",
        )
        self.console.print(panel)

    # ── Votes ──────────────────────────────────────────────

    def render_vote_list(self, records: Sequence[Any]) -> None:
        """Render a table of vote records."""
        if not records:
            self.console.print("[dim]No vote records found.[/dim]")
            return

        table = Table(
            title="Vote Records",
            title_style="bold cyan",
            border_style="dim",
            show_lines=False,
        )
        table.add_column("Proposal", style="bold")
        table.add_column("Status")
        table.add_column("Votes", justify="right")
        table.add_column("Vetoed")

        for rec in records:
            vetoed_txt = Text("Yes", style="red bold") if rec.vetoed else Text("No", style="dim")
            table.add_row(
                rec.proposal_id,
                _style_status(rec.status),
                str(len(rec.votes)),
                vetoed_txt,
            )

        self.console.print(table)
        self.console.print(f"\n[bold]{len(records)}[/bold] record(s)", highlight=False)

    def render_vote_detail(self, tally: Any, record: Any) -> None:
        """Render a detailed panel for a vote tally + record."""
        # Build approval bar
        pct = tally.approval_rate
        bar_width = 20
        filled = int(pct * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        bar_colour = "green" if pct >= 0.6 else "red"

        lines: list[str] = [
            f"[bold]Proposal:[/bold]     {record.proposal_id}",
            f"[bold]Status:[/bold]       {record.status}",
            f"[bold]Total Votes:[/bold]  {tally.total_votes}",
            f"[bold]For:[/bold]          {tally.votes_for} (weighted: {tally.weighted_for:.1f})",
            f"[bold]Against:[/bold]      {tally.votes_against} (weighted: {tally.weighted_against:.1f})",
            f"[bold]Abstain:[/bold]      {tally.votes_abstain} (weighted: {tally.weighted_abstain:.1f})",
            f"[bold]Approval:[/bold]     [{bar_colour}]{bar} {pct:.0%}[/{bar_colour}]",
            f"[bold]Quorum Met:[/bold]   {'[green]Yes[/green]' if tally.quorum_met else '[red]No[/red]'}",
            f"[bold]Threshold:[/bold]    {'[green]Met[/green]' if tally.threshold_met else '[red]Not Met[/red]'}",
            f"[bold]Vetoed:[/bold]       {'[red bold]Yes[/red bold]' if tally.vetoed else '[dim]No[/dim]'}",
            f"[bold]Approved:[/bold]     {'[green bold]Yes[/green bold]' if tally.approved else '[red]No[/red]'}",
        ]

        if record.votes:
            lines.append(f"\n[bold]Votes ({len(record.votes)}):[/bold]")
            for v in record.votes:
                choice_col = {"for": "green", "against": "red", "abstain": "yellow"}.get(
                    v.choice, "white"
                )
                reason = f" — {v.reason}" if v.reason else ""
                lines.append(
                    f"  {v.voter}: [{choice_col}]{v.choice}[/{choice_col}] (w={v.weight}){reason}"
                )

        panel = Panel(
            "\n".join(lines),
            title=f"[bold cyan]Vote — {record.proposal_id}[/bold cyan]",
            border_style="cyan",
        )
        self.console.print(panel)

    # ── Characters ─────────────────────────────────────────

    def render_character_list(self, characters: Sequence[Any]) -> None:
        """Render a table of character templates."""
        if not characters:
            self.console.print("[dim]No characters found.[/dim]")
            return

        table = Table(
            title="Characters",
            title_style="bold cyan",
            border_style="dim",
            show_lines=False,
        )
        table.add_column("ID", style="bold")
        table.add_column("Status")
        table.add_column("Author")
        table.add_column("v", justify="right")
        table.add_column("Name")

        for c in characters:
            table.add_row(
                c.id,
                _style_status(c.status),
                c.author,
                str(c.version),
                _truncate(c.name, 25),
            )

        self.console.print(table)
        self.console.print(f"\n[bold]{len(characters)}[/bold] character(s)", highlight=False)

    def render_character_detail(self, character: Any) -> None:
        """Render a detailed panel for a single character template."""
        lines: list[str] = [
            f"[bold]ID:[/bold]          {character.id}",
            f"[bold]Name:[/bold]        {character.name}",
            f"[bold]Author:[/bold]      {character.author}",
            f"[bold]Status:[/bold]      {character.status}",
            f"[bold]Version:[/bold]     {character.version}",
            f"[bold]Created:[/bold]     {character.created_at}",
            f"[bold]Updated:[/bold]     {character.updated_at}",
        ]

        if character.description:
            lines.append(f"\n[bold]Description:[/bold]\n  {character.description}")

        if character.backstory:
            lines.append(f"\n[bold]Backstory:[/bold]\n  {_truncate(character.backstory, 200)}")

        if character.traits:
            lines.append(f"\n[bold]Traits ({len(character.traits)}):[/bold]")
            for t in character.traits:
                intensity_bar = "●" * int(t.intensity * 5) + "○" * (5 - int(t.intensity * 5))
                lines.append(
                    f"  [magenta][{t.trait_type}][/magenta] {t.name}: {t.description} "
                    f"[dim]{intensity_bar}[/dim]"
                )

        if character.tags:
            tag_text = " ".join(f"[cyan]#{tag}[/cyan]" for tag in character.tags)
            lines.append(f"\n[bold]Tags:[/bold] {tag_text}")

        if character.system_prompt:
            lines.append(
                f"\n[bold]System Prompt:[/bold]\n  [dim]{_truncate(character.system_prompt, 200)}[/dim]"
            )

        if character.greeting:
            lines.append(
                f"\n[bold]Greeting:[/bold]\n  [italic]{_truncate(character.greeting, 200)}[/italic]"
            )

        panel = Panel(
            "\n".join(lines),
            title=f"[bold cyan]{character.name}[/bold cyan]",
            border_style="cyan",
        )
        self.console.print(panel)

    # ── Status Dashboard ───────────────────────────────────

    def render_status_dashboard(self, stats: dict[str, Any]) -> None:
        """Render the full project status dashboard.

        *stats* is a dict with keys: ``members``, ``providers``,
        ``proposals``, ``proposal_statuses``, ``votes``,
        ``vote_statuses``, ``characters``, ``character_statuses``.
        Values that are ``None`` indicate a load failure.
        """
        self.console.print()
        self.console.print(
            Panel(
                "[bold]Jericho AI Council[/bold] — Project Status",
                style="bold cyan",
                border_style="cyan",
            )
        )

        # Council members
        member_count = stats.get("members")
        if member_count is not None:
            lines = [f"[bold]{member_count}[/bold] member(s)"]
            for prov, count in sorted(stats.get("providers", {}).items()):
                lines.append(f"  [magenta]{prov}:[/magenta] {count}")
            self.console.print(Panel("\n".join(lines), title="[bold]Council[/bold]", border_style="dim"))
        else:
            self.console.print(Panel("[red]Unable to load[/red]", title="[bold]Council[/bold]", border_style="dim"))

        # Proposals
        prop_count = stats.get("proposals")
        if prop_count is not None:
            lines = [f"[bold]{prop_count}[/bold] proposal(s)"]
            for s, count in sorted(stats.get("proposal_statuses", {}).items()):
                lines.append(f"  {_style_status(s)}: {count}")
            # Use renderable directly since we have Text objects
            self._print_status_panel("Proposals", prop_count, stats.get("proposal_statuses", {}))
        else:
            self.console.print(Panel("[red]Unable to load[/red]", title="[bold]Proposals[/bold]", border_style="dim"))

        # Vote records
        vote_count = stats.get("votes")
        if vote_count is not None:
            self._print_status_panel("Vote Records", vote_count, stats.get("vote_statuses", {}))
        else:
            self.console.print(Panel("[red]Unable to load[/red]", title="[bold]Vote Records[/bold]", border_style="dim"))

        # Characters
        char_count = stats.get("characters")
        if char_count is not None:
            self._print_status_panel("Characters", char_count, stats.get("character_statuses", {}))
        else:
            self.console.print(Panel("[red]Unable to load[/red]", title="[bold]Characters[/bold]", border_style="dim"))

    def _print_status_panel(self, title: str, count: int, statuses: dict[str, int]) -> None:
        """Print a status panel for a section of the dashboard."""
        lines = [f"[bold]{count}[/bold] total"]
        for s, cnt in sorted(statuses.items()):
            colour = STATUS_COLOURS.get(s, "white")
            lines.append(f"  [{colour}]{s}:[/{colour}] {cnt}")
        self.console.print(Panel("\n".join(lines), title=f"[bold]{title}[/bold]", border_style="dim"))

    # ── Feedback Messages ──────────────────────────────────

    def render_success(self, message: str) -> None:
        """Print a success message."""
        self.console.print(f"[green]✓[/green] {message}", highlight=False)

    def render_error(self, message: str) -> None:
        """Print an error message to stderr."""
        self.console.print(f"[red bold]Error:[/red bold] {message}", highlight=False)
