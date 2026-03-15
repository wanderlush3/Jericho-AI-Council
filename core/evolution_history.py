"""
Jericho — Prompt Evolution History (F-020)

Read-only timeline engine that traces character version chains through
evolution records, producing an ordered history of what changed, when,
and why — displayable via Rich-formatted CLI output.

Data sources (all read-only):
    - CharacterManager  — templates with metadata["previous_version"] links
    - CharacterEvolution — evolution records linking changes to proposals/votes
    - ProposalManager    — proposal details backing each evolution
    - VotingEngine       — vote tallies for each governance decision
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from core.characters import CharacterManager, CharacterTemplate, Trait
from core.character_evolution import CharacterEvolution, EvolutionRecord


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class VersionSnapshot:
    """Compact snapshot of a single character version."""

    character_id: str
    name: str
    version: int
    status: str
    author: str
    traits_summary: str          # e.g. "Curious (0.7), Brave (0.5)"
    trait_count: int
    system_prompt_excerpt: str   # first 120 chars
    backstory_excerpt: str       # first 120 chars
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    previous_version: str = ""   # CH-XXXX or ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VersionSnapshot:
        return cls(
            character_id=data["character_id"],
            name=data["name"],
            version=data["version"],
            status=data["status"],
            author=data["author"],
            traits_summary=data.get("traits_summary", ""),
            trait_count=data.get("trait_count", 0),
            system_prompt_excerpt=data.get("system_prompt_excerpt", ""),
            backstory_excerpt=data.get("backstory_excerpt", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            previous_version=data.get("previous_version", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class EvolutionEvent:
    """A governance event that caused a character to evolve."""

    evolution_id: str
    character_id: str         # the character that was evolved
    author: str
    changes_summary: str      # compact description of changes
    change_count: int
    proposal_id: str = ""
    vote_result: str = ""     # "Approved (80.0%)" / "Rejected" / ""
    status: str = ""          # evolution status
    applied_character_id: str = ""   # new version ID after apply
    timestamp: str = ""       # created_at of the evolution
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvolutionEvent:
        return cls(
            evolution_id=data["evolution_id"],
            character_id=data["character_id"],
            author=data["author"],
            changes_summary=data.get("changes_summary", ""),
            change_count=data.get("change_count", 0),
            proposal_id=data.get("proposal_id", ""),
            vote_result=data.get("vote_result", ""),
            status=data.get("status", ""),
            applied_character_id=data.get("applied_character_id", ""),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class CharacterTimeline:
    """Complete evolution timeline for a character lineage."""

    character_name: str
    version_chain: list[str] = field(default_factory=list)   # oldest → newest
    snapshots: list[VersionSnapshot] = field(default_factory=list)
    events: list[EvolutionEvent] = field(default_factory=list)
    latest_version: str = ""     # current head of chain

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["snapshots"] = [s.to_dict() for s in self.snapshots]
        d["events"] = [e.to_dict() for e in self.events]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterTimeline:
        snapshots = [
            VersionSnapshot.from_dict(s) for s in data.get("snapshots", [])
        ]
        events = [
            EvolutionEvent.from_dict(e) for e in data.get("events", [])
        ]
        return cls(
            character_name=data["character_name"],
            version_chain=data.get("version_chain", []),
            snapshots=snapshots,
            events=events,
            latest_version=data.get("latest_version", ""),
        )


# ─── Helpers ───────────────────────────────────────────────────


def _summarise_traits(traits: list[Trait]) -> str:
    """Produce a compact trait summary like 'Curious (0.7), Brave (0.5)'."""
    if not traits:
        return "(none)"
    parts = [f"{t.name} ({t.intensity:.1f})" for t in traits[:6]]
    if len(traits) > 6:
        parts.append(f"+{len(traits) - 6} more")
    return ", ".join(parts)


def _truncate(text: str, length: int = 120) -> str:
    """Truncate text to *length* chars with ellipsis."""
    if not text:
        return ""
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


def _summarise_changes(changes: list) -> str:
    """Compact summary of evolution changes."""
    if not changes:
        return "(no changes)"
    parts = []
    for c in changes[:5]:
        parts.append(f"{c.change_type}:{c.field_name}")
    if len(changes) > 5:
        parts.append(f"+{len(changes) - 5} more")
    return ", ".join(parts)


def _build_vote_result(evolution: EvolutionRecord) -> str:
    """Build a human-readable vote result from evolution metadata."""
    tally = evolution.metadata.get("tally", {})
    if not tally:
        if evolution.status == "rejected":
            return "Rejected"
        return ""
    approval = tally.get("approval_rate", 0)
    approved = tally.get("approved", False)
    result = "Approved" if approved else "Rejected"
    return f"{result} ({approval:.0%})"


# ─── Evolution History Engine ─────────────────────────────────


class EvolutionHistory:
    """
    Read-only aggregator that builds visual timelines of character evolution.

    Usage::

        chars = CharacterManager()
        evo = CharacterEvolution(...)
        history = EvolutionHistory(
            character_manager=chars,
            evolution_manager=evo,
        )
        timeline = history.build_timeline("CH-0003")
    """

    def __init__(
        self,
        *,
        character_manager: CharacterManager,
        evolution_manager: CharacterEvolution | None = None,
    ) -> None:
        self._characters = character_manager
        self._evolutions = evolution_manager

    # ── Properties ────────────────────────────────────────────

    @property
    def character_manager(self) -> CharacterManager:
        return self._characters

    @property
    def evolution_manager(self) -> CharacterEvolution | None:
        return self._evolutions

    # ── Get Version Chain ─────────────────────────────────────

    def get_version_chain(self, character_id: str) -> list[str]:
        """
        Walk the ``metadata["previous_version"]`` links from *character_id*
        back to the original, then return the chain in chronological order
        (oldest first).

        Guards against circular links by tracking visited IDs.

        Raises:
            CharacterNotFoundError: if *character_id* does not exist.
        """
        chain: list[str] = []
        visited: set[str] = set()
        current_id = character_id

        # Validate the initial character exists (let exception propagate)
        self._characters.get(current_id)

        while current_id:
            if current_id in visited:
                break  # circular guard
            visited.add(current_id)
            chain.append(current_id)
            try:
                char = self._characters.get(current_id)
            except Exception:
                break  # missing intermediate version
            prev = char.metadata.get("previous_version", "")
            current_id = prev

        chain.reverse()  # oldest first
        return chain

    # ── Get Snapshot ───────────────────────────────────────────

    def get_snapshot(self, character_id: str) -> VersionSnapshot:
        """
        Build a compact snapshot for a single character version.

        Raises:
            CharacterNotFoundError: if *character_id* does not exist.
        """
        char = self._characters.get(character_id)
        return self._make_snapshot(char)

    # ── Build Timeline ────────────────────────────────────────

    def build_timeline(self, character_id: str) -> CharacterTimeline:
        """
        Build the complete evolution timeline for the lineage containing
        *character_id*.

        This walks the version chain, builds a snapshot for each version,
        and collects all evolution events referencing any version in the
        chain.

        Raises:
            CharacterNotFoundError: if *character_id* does not exist.
        """
        # Validate the character exists
        head = self._characters.get(character_id)

        chain = self.get_version_chain(character_id)

        # Build snapshots for each version in the chain
        snapshots: list[VersionSnapshot] = []
        for cid in chain:
            try:
                snap = self.get_snapshot(cid)
                snapshots.append(snap)
            except Exception:
                continue  # skip missing intermediate versions

        # Collect evolution events
        events: list[EvolutionEvent] = []
        if self._evolutions is not None:
            chain_set = set(chain)
            all_evolutions = self._evolutions.list_evolutions()
            for evo in all_evolutions:
                if evo.character_id in chain_set:
                    events.append(self._make_event(evo))
            # Sort events by timestamp
            events.sort(key=lambda e: e.timestamp)

        return CharacterTimeline(
            character_name=head.name,
            version_chain=chain,
            snapshots=snapshots,
            events=events,
            latest_version=chain[-1] if chain else character_id,
        )

    # ── List Timelines ────────────────────────────────────────

    def list_timelines(self) -> list[CharacterTimeline]:
        """
        Build timelines for all "head" characters — those that are NOT
        superseded by another version (i.e., they are the latest in their
        lineage).

        Returns timelines sorted by character name.
        """
        all_chars = self._characters.list_characters()

        # Find IDs that are referenced as previous_version by another
        superseded_ids: set[str] = set()
        for c in all_chars:
            prev = c.metadata.get("previous_version", "")
            if prev:
                superseded_ids.add(prev)

        # Heads are characters not in superseded_ids
        heads = [c for c in all_chars if c.id not in superseded_ids]

        timelines: list[CharacterTimeline] = []
        for head in heads:
            try:
                timeline = self.build_timeline(head.id)
                timelines.append(timeline)
            except Exception:
                continue

        timelines.sort(key=lambda t: t.character_name.lower())
        return timelines

    # ── Diff Versions ─────────────────────────────────────────

    def diff_versions(
        self,
        old_id: str,
        new_id: str,
    ) -> list[str]:
        """
        Produce a human-readable diff between two character versions.

        Returns a list of change description strings, e.g.:
            - "+ Trait: Brave (personality, 0.7)"
            - "- Trait: Timid (personality, 0.3)"
            - "~ Name: 'Atlas' → 'Atlas Prime'"

        Raises:
            CharacterNotFoundError: if either character does not exist.
        """
        old = self._characters.get(old_id)
        new = self._characters.get(new_id)

        diffs: list[str] = []

        # Compare simple fields
        for field_name in ("name", "description", "backstory", "system_prompt", "greeting"):
            old_val = getattr(old, field_name)
            new_val = getattr(new, field_name)
            if old_val != new_val:
                diffs.append(
                    f"~ {field_name.replace('_', ' ').title()}: "
                    f"'{_truncate(old_val, 40)}' → '{_truncate(new_val, 40)}'"
                )

        # Compare version
        if old.version != new.version:
            diffs.append(f"~ Version: {old.version} → {new.version}")

        # Compare traits
        old_traits = {t.name.lower(): t for t in old.traits}
        new_traits = {t.name.lower(): t for t in new.traits}

        # Removed traits
        for name_lower, trait in old_traits.items():
            if name_lower not in new_traits:
                diffs.append(
                    f"- Trait: {trait.name} ({trait.trait_type}, {trait.intensity:.1f})"
                )

        # Added traits
        for name_lower, trait in new_traits.items():
            if name_lower not in old_traits:
                diffs.append(
                    f"+ Trait: {trait.name} ({trait.trait_type}, {trait.intensity:.1f})"
                )

        # Modified traits (same name, different values)
        for name_lower in old_traits:
            if name_lower in new_traits:
                ot = old_traits[name_lower]
                nt = new_traits[name_lower]
                changes = []
                if ot.trait_type != nt.trait_type:
                    changes.append(f"type: {ot.trait_type}→{nt.trait_type}")
                if ot.description != nt.description:
                    changes.append("description changed")
                if abs(ot.intensity - nt.intensity) > 0.001:
                    changes.append(f"intensity: {ot.intensity:.1f}→{nt.intensity:.1f}")
                if changes:
                    diffs.append(
                        f"~ Trait: {nt.name} ({', '.join(changes)})"
                    )

        # Compare tags
        old_tags = set(old.tags)
        new_tags = set(new.tags)
        for tag in sorted(old_tags - new_tags):
            diffs.append(f"- Tag: #{tag}")
        for tag in sorted(new_tags - old_tags):
            diffs.append(f"+ Tag: #{tag}")

        if not diffs:
            diffs.append("(no differences)")

        return diffs

    # ── Internal Helpers ──────────────────────────────────────

    def _make_snapshot(self, char: CharacterTemplate) -> VersionSnapshot:
        """Build a VersionSnapshot from a CharacterTemplate."""
        return VersionSnapshot(
            character_id=char.id,
            name=char.name,
            version=char.version,
            status=char.status,
            author=char.author,
            traits_summary=_summarise_traits(char.traits),
            trait_count=len(char.traits),
            system_prompt_excerpt=_truncate(char.system_prompt),
            backstory_excerpt=_truncate(char.backstory),
            tags=list(char.tags),
            created_at=char.created_at,
            updated_at=char.updated_at,
            previous_version=char.metadata.get("previous_version", ""),
            metadata=dict(char.metadata),
        )

    def _make_event(self, evo: EvolutionRecord) -> EvolutionEvent:
        """Build an EvolutionEvent from an EvolutionRecord."""
        return EvolutionEvent(
            evolution_id=evo.evolution_id,
            character_id=evo.character_id,
            author=evo.author,
            changes_summary=_summarise_changes(evo.changes),
            change_count=len(evo.changes),
            proposal_id=evo.proposal_id,
            vote_result=_build_vote_result(evo),
            status=evo.status,
            applied_character_id=evo.applied_character_id,
            timestamp=evo.created_at,
            metadata=dict(evo.metadata),
        )

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        char_count = len(self._characters.list_characters())
        return f"EvolutionHistory(characters={char_count})"
