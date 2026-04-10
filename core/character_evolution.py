"""
Jericho — Character Evolution (F-013)

Propose and vote on modifications to existing characters via the governance
system.  Each evolution goes through a structured lifecycle:

    draft → proposed → voting → decided → applied
                                        ↘ rejected

Overlay lifecycle (independent from governance):

    draft → active → archived

When overlay_status is "active", the evolution's changes override
the target entity's base system prompts at query time.

Storage: one JSON file per evolution in ``data/character_evolutions/``,
named ``EV-XXXX.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    EVOLUTION_DIR,
    EVOLUTION_OVERLAY_STATUSES,
    EVOLUTION_STATUSES,
    EVOLUTION_TARGETS,
    EVOLUTION_TYPES,
    MAX_EVOLUTION_CHANGES,
    MAX_EVOLUTION_HISTORY,
)
from core.characters import CharacterManager, CharacterTemplate, Trait
from core.memory import SharedMemory
from core.proposals import Proposal, ProposalManager
from core.utils import atomic_write
from core.voting import VotingEngine, Vote, VoteTally


# ─── Exceptions ────────────────────────────────────────────────


class EvolutionError(Exception):
    """Base exception for character-evolution errors."""


class EvolutionNotFoundError(EvolutionError):
    """Raised when an evolution record cannot be found."""

    def __init__(self, evolution_id: str) -> None:
        self.evolution_id = evolution_id
        super().__init__(f"Evolution not found: '{evolution_id}'")


class EvolutionValidationError(EvolutionError):
    """Raised when evolution data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class EvolutionStateError(EvolutionError):
    """Raised when an operation conflicts with current evolution state."""

    def __init__(self, evolution_id: str, message: str) -> None:
        self.evolution_id = evolution_id
        super().__init__(
            f"Evolution state error for '{evolution_id}': {message}"
        )


class EvolutionOverlayError(EvolutionError):
    """Raised when an overlay operation fails (e.g. multiple active overlays)."""


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"proposed"},
    "proposed": {"voting"},
    "voting": {"decided", "rejected"},
    "decided": {"applied"},
    "applied": set(),      # terminal
    "rejected": set(),     # terminal
}

# Overlay lifecycle transitions (independent from governance lifecycle)
_OVERLAY_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "archived"},
    "active": {"archived"},
    "archived": {"draft", "active"},    # allows re-activation
}


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class CharacterChange:
    """A single proposed change to a character."""

    change_type: str       # trait_add / trait_remove / trait_modify / field_update / version_bump
    field_name: str        # e.g. "backstory", "system_prompt", trait name
    old_value: Any = ""
    new_value: Any = ""
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterChange:
        return cls(
            change_type=data["change_type"],
            field_name=data["field_name"],
            old_value=data.get("old_value", ""),
            new_value=data.get("new_value", ""),
            rationale=data.get("rationale", ""),
        )

    @classmethod
    def create(
        cls,
        change_type: str,
        field_name: str,
        old_value: Any = "",
        new_value: Any = "",
        rationale: str = "",
    ) -> CharacterChange:
        """Factory with validation."""
        if change_type not in EVOLUTION_TYPES:
            raise EvolutionValidationError(
                [
                    f"Invalid change type '{change_type}' — must be one of "
                    f"{EVOLUTION_TYPES}"
                ]
            )
        if not field_name.strip():
            raise EvolutionValidationError(
                ["Field name must not be empty"]
            )
        return cls(
            change_type=change_type,
            field_name=field_name.strip(),
            old_value=old_value,
            new_value=new_value,
            rationale=rationale,
        )


@dataclass(frozen=True)
class EvolutionRecord:
    """Persistent record of a character evolution proposal."""

    evolution_id: str
    character_id: str              # backward-compat alias for target_id
    author: str
    changes: list[CharacterChange] = field(default_factory=list)
    proposal_id: str = ""          # links to ProposalManager
    vote_record_id: str = ""       # links to VotingEngine
    status: str = "draft"
    applied_character_id: str = "" # new version after apply
    summary: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    # ── New fields (Evolution Expansion) ──
    name: str = ""                     # user-friendly evolution name
    sequence_number: int = 0          # auto-incremented per target
    target_type: str = "character"    # "character" or "council_member"
    target_id: str = ""               # canonical target identifier
    overlay_status: str = "draft"     # "draft" / "active" / "archived"
    rollback_of: str = ""             # ID of evolution this rolls back (if rollback)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["changes"] = [c.to_dict() for c in self.changes]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvolutionRecord:
        changes = [
            CharacterChange.from_dict(c)
            for c in data.get("changes", [])
        ]
        # Backward-compat: use character_id as target_id if target_id not set
        target_id = data.get("target_id", "") or data.get("character_id", "")
        return cls(
            evolution_id=data["evolution_id"],
            character_id=data.get("character_id", target_id),
            author=data["author"],
            changes=changes,
            proposal_id=data.get("proposal_id", ""),
            vote_record_id=data.get("vote_record_id", ""),
            status=data.get("status", "draft"),
            applied_character_id=data.get("applied_character_id", ""),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
            name=data.get("name", ""),
            sequence_number=data.get("sequence_number", 0),
            target_type=data.get("target_type", "character"),
            target_id=target_id,
            overlay_status=data.get("overlay_status", "draft"),
            rollback_of=data.get("rollback_of", ""),
        )

    @classmethod
    def create(
        cls,
        evolution_id: str,
        character_id: str,
        author: str,
        changes: list[CharacterChange] | None = None,
        metadata: dict[str, Any] | None = None,
        *,
        name: str = "",
        sequence_number: int = 0,
        target_type: str = "character",
        target_id: str = "",
    ) -> EvolutionRecord:
        """Factory that auto-fills timestamps."""
        if not evolution_id.strip():
            raise EvolutionValidationError(
                ["Evolution ID must not be empty"]
            )
        if not character_id.strip():
            raise EvolutionValidationError(
                ["Character ID must not be empty"]
            )
        if not author.strip():
            raise EvolutionValidationError(
                ["Author must not be empty"]
            )
        effective_target_id = (target_id or character_id).strip()
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            evolution_id=evolution_id.strip(),
            character_id=character_id.strip(),
            author=author.strip(),
            changes=changes or [],
            proposal_id="",
            vote_record_id="",
            status="draft",
            applied_character_id="",
            summary="",
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
            name=name.strip(),
            sequence_number=sequence_number,
            target_type=target_type,
            target_id=effective_target_id,
            overlay_status="draft",
            rollback_of="",
        )


# ─── Helpers ───────────────────────────────────────────────────




# ─── Character Evolution ──────────────────────────────────────


class CharacterEvolution:
    """
    Governance-backed character modification system.

    Each evolution creates a proposal, goes through voting, and if
    approved, creates a new version of the character with the proposed
    changes applied.

    Usage::

        chars = CharacterManager()
        proposals = ProposalManager()
        engine = VotingEngine()
        evo = CharacterEvolution(
            character_manager=chars,
            proposal_manager=proposals,
            voting_engine=engine,
        )

        # Create evolution with changes
        change = CharacterChange.create("trait_add", "courage",
                                        new_value={"trait_type": "personality",
                                                    "name": "courage",
                                                    "description": "Brave",
                                                    "intensity": 0.7},
                                        rationale="Needs more bravery")
        rec = evo.create_evolution("CH-0001", author="Sage", changes=[change])

        # Submit for governance review
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)

        # After votes are cast...
        rec = evo.resolve(rec.evolution_id)
        if rec.status == "decided":
            template = evo.apply_evolution(rec.evolution_id)
    """

    _ID_PATTERN = re.compile(r"^EV-(\d{4})\.json$")

    def __init__(
        self,
        *,
        character_manager: CharacterManager,
        proposal_manager: ProposalManager,
        voting_engine: VotingEngine,
        evolutions_dir: Path | None = None,
        shared_memory: SharedMemory | None = None,
    ) -> None:
        self._characters = character_manager
        self._proposals = proposal_manager
        self._voting = voting_engine
        self._dir = evolutions_dir or EVOLUTION_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._shared_memory = shared_memory or SharedMemory()

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def character_manager(self) -> CharacterManager:
        return self._characters

    @property
    def proposal_manager(self) -> ProposalManager:
        return self._proposals

    @property
    def voting_engine(self) -> VotingEngine:
        return self._voting

    # ── Create ────────────────────────────────────────────────

    def create_evolution(
        self,
        character_id: str,
        *,
        author: str,
        changes: list[CharacterChange] | None = None,
        metadata: dict[str, Any] | None = None,
        name: str = "",
        target_type: str = "character",
    ) -> EvolutionRecord:
        """
        Create a new character evolution in *draft* status.

        Auto-generates a sequential ``EV-XXXX`` ID.  Validates that
        the target character exists and is in ``active`` status.

        Raises:
            EvolutionValidationError: if inputs are invalid or char
                is not active.
            CharacterNotFoundError: if character doesn't exist.
        """
        errors: list[str] = []
        if not character_id.strip():
            errors.append("Character ID must not be empty")
        if not author.strip():
            errors.append("Author must not be empty")

        effective_changes = changes or []
        if not effective_changes:
            errors.append("At least one change is required")
        if len(effective_changes) > MAX_EVOLUTION_CHANGES:
            errors.append(
                f"Change count {len(effective_changes)} exceeds "
                f"maximum of {MAX_EVOLUTION_CHANGES}"
            )
        if errors:
            raise EvolutionValidationError(errors)

        # Validate character exists and is active
        character = self._characters.get(character_id)
        if character.status != "active":
            raise EvolutionValidationError(
                [
                    f"Character '{character_id}' must be in 'active' status "
                    f"to evolve, current status: '{character.status}'"
                ]
            )

        target_id = character_id.strip()
        next_id = self._next_id()
        seq_num = self._next_sequence_number(target_id, target_type)
        evo_name = name or f"Evolution #{seq_num} for {character.name}"

        record = EvolutionRecord.create(
            evolution_id=next_id,
            character_id=character_id.strip(),
            author=author.strip(),
            changes=effective_changes,
            metadata=metadata,
            name=evo_name,
            sequence_number=seq_num,
            target_type=target_type,
            target_id=target_id,
        )
        self._save(record)
        return record

    # ── Submit for Review ─────────────────────────────────────

    def submit_for_review(self, evolution_id: str) -> EvolutionRecord:
        """
        Create a governance proposal for this evolution and transition
        to ``proposed`` status.

        Creates a ``Proposal`` via ``ProposalManager`` with
        category ``"character"`` and links the proposal ID.

        Raises:
            EvolutionNotFoundError: if evolution doesn't exist.
            EvolutionStateError: if not in ``draft`` status.
        """
        record = self.get(evolution_id)
        self._validate_transition(record, "proposed")

        # Build proposal description from changes
        change_lines = []
        for c in record.changes:
            change_lines.append(
                f"- **{c.change_type}** on `{c.field_name}`: {c.rationale}"
            )
        description = (
            f"Character evolution for {record.character_id}:\n"
            + "\n".join(change_lines)
        )

        # Create proposal via ProposalManager
        proposal = self._proposals.create(
            f"Evolve {record.character_id}",
            description,
            author=record.author,
            category="character",
            body=json.dumps(
                [c.to_dict() for c in record.changes],
                indent=2,
                ensure_ascii=False,
            ),
            metadata={
                "evolution_id": record.evolution_id,
                "character_id": record.character_id,
            },
        )

        # Transition proposal to open
        self._proposals.update_status(proposal.id, "open")

        updated = self._rebuild(
            record,
            proposal_id=proposal.id,
            status="proposed",
        )
        self._save(updated)
        return updated

    # ── Open Voting ───────────────────────────────────────────

    def open_voting(self, evolution_id: str) -> EvolutionRecord:
        """
        Open voting on the linked proposal and transition to ``voting``.

        Raises:
            EvolutionNotFoundError: if evolution doesn't exist.
            EvolutionStateError: if not in ``proposed`` status.
        """
        record = self.get(evolution_id)
        self._validate_transition(record, "voting")

        if not record.proposal_id:
            raise EvolutionStateError(
                evolution_id,
                "No proposal linked — call submit_for_review first",
            )

        # Transition proposal to under_review
        self._proposals.update_status(record.proposal_id, "under_review")

        # Open voting via VotingEngine
        vote_record = self._voting.open_voting(
            record.proposal_id,
            metadata={
                "evolution_id": record.evolution_id,
                "character_id": record.character_id,
            },
        )

        updated = self._rebuild(
            record,
            vote_record_id=vote_record.proposal_id,
            status="voting",
        )
        self._save(updated)
        return updated

    # ── Resolve ───────────────────────────────────────────────

    def resolve(self, evolution_id: str) -> EvolutionRecord:
        """
        Tally votes and transition to ``decided`` (approved) or
        ``rejected``.

        Closes voting, tallies results, and transitions the proposal
        to ``decided`` status.

        Raises:
            EvolutionNotFoundError: if evolution doesn't exist.
            EvolutionStateError: if not in ``voting`` status.
        """
        record = self.get(evolution_id)

        if record.status != "voting":
            raise EvolutionStateError(
                evolution_id,
                f"Cannot resolve — status is '{record.status}', "
                f"must be 'voting'",
            )

        # Close voting and get tally
        self._voting.close_voting(record.proposal_id)
        tally = self._voting.tally(record.proposal_id)

        # Transition proposal to decided
        self._proposals.update_status(record.proposal_id, "decided")

        new_status = "decided" if tally.approved else "rejected"
        now = datetime.now(timezone.utc).isoformat()
        summary = (
            f"{'Approved' if tally.approved else 'Rejected'}: "
            f"{tally.votes_for} for, {tally.votes_against} against, "
            f"{tally.votes_abstain} abstain "
            f"(approval rate: {tally.approval_rate:.1%}, "
            f"quorum: {'met' if tally.quorum_met else 'not met'}"
            f"{', VETOED' if tally.vetoed else ''})"
        )

        updated = self._rebuild(
            record,
            status=new_status,
            summary=summary,
            metadata={
                **record.metadata,
                "tally": tally.to_dict(),
            },
        )
        self._save(updated)

        # Record to shared memory
        self._shared_memory.record_decision({
            "type": "evolution_resolved",
            "evolution_id": record.evolution_id,
            "character_id": record.character_id,
            "result": new_status,
            "tally": tally.to_dict(),
            "resolved_at": now,
        })

        return updated

    # ── Apply Evolution ───────────────────────────────────────

    def apply_evolution(self, evolution_id: str) -> CharacterTemplate:
        """
        Apply approved changes to the character by creating a new version.

        Creates a new version of the character via
        ``CharacterManager.create_version()``, then applies each change
        to the new version.

        Raises:
            EvolutionNotFoundError: if evolution doesn't exist.
            EvolutionStateError: if not in ``decided`` status.
        """
        record = self.get(evolution_id)
        self._validate_transition(record, "applied")

        # Create new version (supersedes the original)
        new_template = self._characters.create_version(record.character_id)

        # Apply each change to the new version
        for change in record.changes:
            new_template = self._apply_change(new_template, change)

        # Activate the new version
        new_template = self._characters.update_status(new_template.id, "active")

        now = datetime.now(timezone.utc).isoformat()
        updated = self._rebuild(
            record,
            status="applied",
            applied_character_id=new_template.id,
            metadata={
                **record.metadata,
                "applied_at": now,
            },
        )
        self._save(updated)

        # Record to shared memory
        self._shared_memory.record_decision({
            "type": "evolution_applied",
            "evolution_id": record.evolution_id,
            "character_id": record.character_id,
            "new_character_id": new_template.id,
            "changes_applied": len(record.changes),
            "applied_at": now,
        })

        self._shared_memory.append_history(
            f"### Character Evolution: {record.evolution_id}\n"
            f"**Applied:** {now}\n"
            f"**Character:** {record.character_id} → {new_template.id}\n"
            f"**Author:** {record.author}\n"
            f"**Changes:** {len(record.changes)}\n\n"
            f"{record.summary}\n"
        )

        return new_template

    # ── Query ─────────────────────────────────────────────────

    def get(self, evolution_id: str) -> EvolutionRecord:
        """
        Load an evolution record by ID.

        Raises:
            EvolutionNotFoundError: if no evolution file exists.
        """
        filepath = self._filepath(evolution_id)
        if not filepath.exists():
            raise EvolutionNotFoundError(evolution_id)
        return self._load(filepath)

    def list_evolutions(
        self,
        *,
        character_id: str | None = None,
        status: str | None = None,
        author: str | None = None,
        target_type: str | None = None,
        overlay_status: str | None = None,
    ) -> list[EvolutionRecord]:
        """
        Return evolutions sorted by ID, with optional filters.
        """
        evolutions: list[EvolutionRecord] = []
        for filepath in sorted(self._dir.glob("EV-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if character_id is not None and rec.character_id != character_id:
                continue
            if status is not None and rec.status != status:
                continue
            if author is not None and rec.author.lower() != author.strip().lower():
                continue
            if target_type is not None and rec.target_type != target_type:
                continue
            if overlay_status is not None and rec.overlay_status != overlay_status:
                continue
            evolutions.append(rec)
        return evolutions

    def has_evolution(self, evolution_id: str) -> bool:
        """Check if an evolution record exists."""
        return self._filepath(evolution_id).exists()

    # ── Internal: Apply Changes ───────────────────────────────

    def _apply_change(
        self,
        template: CharacterTemplate,
        change: CharacterChange,
    ) -> CharacterTemplate:
        """Apply a single CharacterChange to a template."""
        if change.change_type == "trait_add":
            trait_data = change.new_value if isinstance(change.new_value, dict) else {}
            trait = Trait(
                trait_type=trait_data.get("trait_type", "personality"),
                name=trait_data.get("name", change.field_name),
                description=trait_data.get("description", ""),
                intensity=trait_data.get("intensity", 0.5),
            )
            template = self._characters.add_trait(template.id, trait)

        elif change.change_type == "trait_remove":
            template = self._characters.remove_trait(template.id, change.field_name)

        elif change.change_type == "trait_modify":
            # Remove old trait, add modified one
            try:
                template = self._characters.remove_trait(template.id, change.field_name)
            except Exception:
                pass  # trait may not exist yet
            trait_data = change.new_value if isinstance(change.new_value, dict) else {}
            trait = Trait(
                trait_type=trait_data.get("trait_type", "personality"),
                name=trait_data.get("name", change.field_name),
                description=trait_data.get("description", ""),
                intensity=trait_data.get("intensity", 0.5),
            )
            template = self._characters.add_trait(template.id, trait)

        elif change.change_type == "field_update":
            template = self._characters.update(
                template.id,
                **{change.field_name: change.new_value},
            )

        elif change.change_type == "version_bump":
            # Already handled by create_version — this is a no-op marker
            pass

        return template

    # ── Internal: Lifecycle ───────────────────────────────────

    def _validate_transition(
        self,
        record: EvolutionRecord,
        new_status: str,
    ) -> None:
        """Validate a lifecycle transition."""
        if new_status not in EVOLUTION_STATUSES:
            raise EvolutionValidationError(
                [
                    f"Unknown status '{new_status}' — must be one of "
                    f"{EVOLUTION_STATUSES}"
                ]
            )
        allowed = _VALID_TRANSITIONS.get(record.status, set())
        if new_status not in allowed:
            raise EvolutionStateError(
                record.evolution_id,
                f"Cannot transition from '{record.status}' to '{new_status}'",
            )

    # ── Internal: Record Rebuilder ────────────────────────────

    def _rebuild(
        self,
        record: EvolutionRecord,
        **overrides: Any,
    ) -> EvolutionRecord:
        """Create a new EvolutionRecord from an existing one with overrides.

        Since EvolutionRecord is frozen, this is the canonical way to
        update fields.  Automatically bumps ``updated_at``.
        """
        base = record.to_dict()
        base["updated_at"] = datetime.now(timezone.utc).isoformat()
        base.update(overrides)
        # Preserve changes list from the original if not overridden
        if "changes" not in overrides:
            base["changes"] = [c.to_dict() for c in record.changes]
        return EvolutionRecord.from_dict(base)

    # ── Overlay Status Management ─────────────────────────────

    def update_overlay_status(
        self,
        evolution_id: str,
        new_overlay_status: str,
    ) -> EvolutionRecord:
        """
        Transition the overlay status of an evolution.

        Only one evolution can be ``active`` per target at a time.
        Activating an evolution automatically archives any previously
        active evolution for the same target.

        Raises:
            EvolutionNotFoundError: if evolution doesn't exist.
            EvolutionOverlayError: if the transition is invalid.
        """
        if new_overlay_status not in EVOLUTION_OVERLAY_STATUSES:
            raise EvolutionOverlayError(
                f"Unknown overlay status '{new_overlay_status}' — "
                f"must be one of {EVOLUTION_OVERLAY_STATUSES}"
            )

        record = self.get(evolution_id)

        allowed = _OVERLAY_TRANSITIONS.get(record.overlay_status, set())
        if new_overlay_status not in allowed:
            raise EvolutionOverlayError(
                f"Cannot transition overlay from '{record.overlay_status}' "
                f"to '{new_overlay_status}'"
            )

        # Mutual exclusion: archive the current active overlay for this target
        if new_overlay_status == "active":
            target_id = record.target_id or record.character_id
            target_type = record.target_type
            current_active = self.get_active_overlay(target_id, target_type)
            if current_active and current_active.evolution_id != evolution_id:
                self._save(self._rebuild(
                    current_active,
                    overlay_status="archived",
                ))

        updated = self._rebuild(record, overlay_status=new_overlay_status)
        self._save(updated)
        return updated

    def get_active_overlay(
        self,
        target_id: str,
        target_type: str = "character",
    ) -> EvolutionRecord | None:
        """
        Return the single active overlay for a target, or ``None``.
        """
        for filepath in self._dir.glob("EV-*.json"):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue
            effective_target = rec.target_id or rec.character_id
            if (
                effective_target == target_id
                and rec.target_type == target_type
                and rec.overlay_status == "active"
            ):
                return rec
        return None

    # ── Rollback ──────────────────────────────────────────────

    def rollback(self, evolution_id: str, *, author: str = "") -> EvolutionRecord:
        """
        Create a new rollback evolution that reverses a previous one.

        The rolled-back evolution gets its overlay archived.
        Returns the new rollback evolution record in ``draft`` status.

        Raises:
            EvolutionNotFoundError: if evolution doesn't exist.
            EvolutionStateError: if evolution was never applied/active.
        """
        source = self.get(evolution_id)

        if source.status not in ("applied", "decided") and source.overlay_status != "active":
            raise EvolutionStateError(
                evolution_id,
                "Can only roll back evolutions that are applied/decided "
                "or have an active overlay",
            )

        # Build reverse changes
        reverse_changes: list[CharacterChange] = []
        for c in source.changes:
            reverse_changes.append(CharacterChange(
                change_type="rollback",
                field_name=c.field_name,
                old_value=c.new_value,     # flip old/new
                new_value=c.old_value,
                rationale=f"Rollback of {evolution_id}: {c.rationale}",
            ))

        target_id = source.target_id or source.character_id
        target_type = source.target_type

        next_id = self._next_id()
        seq_num = self._next_sequence_number(target_id, target_type)
        rollback_author = author or source.author

        record = EvolutionRecord.create(
            evolution_id=next_id,
            character_id=source.character_id,
            author=rollback_author,
            changes=reverse_changes,
            metadata={"rollback_source": evolution_id},
            name=f"Rollback of {evolution_id}",
            sequence_number=seq_num,
            target_type=target_type,
            target_id=target_id,
        )
        # Mark the rollback_of field
        record = self._rebuild(record, rollback_of=evolution_id)
        self._save(record)

        # Archive the source evolution's overlay
        if source.overlay_status == "active":
            self._save(self._rebuild(source, overlay_status="archived"))

        return record

    def rollback_to_version(
        self,
        target_id: str,
        version_id: str,
        *,
        author: str = "system",
        target_type: str = "character",
    ) -> EvolutionRecord:
        """
        Roll back a target to a specific character version by archiving
        all overlays and creating a field_update evolution that snapshots
        the version's key fields.

        Returns the new evolution record.
        """
        # Archive all active overlays for this target
        for filepath in self._dir.glob("EV-*.json"):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue
            effective_target = rec.target_id or rec.character_id
            if (
                effective_target == target_id
                and rec.target_type == target_type
                and rec.overlay_status == "active"
            ):
                self._save(self._rebuild(rec, overlay_status="archived"))

        # For character targets, load the version to capture its state
        changes: list[CharacterChange] = []
        if target_type == "character":
            version = self._characters.get(version_id)
            changes.append(CharacterChange(
                change_type="field_update",
                field_name="system_prompt",
                old_value="",
                new_value=version.system_prompt,
                rationale=f"Restore system_prompt from version {version_id}",
            ))
            if version.backstory:
                changes.append(CharacterChange(
                    change_type="field_update",
                    field_name="backstory",
                    old_value="",
                    new_value=version.backstory,
                    rationale=f"Restore backstory from version {version_id}",
                ))

        if not changes:
            # Minimal rollback marker
            changes.append(CharacterChange(
                change_type="rollback",
                field_name="version_rollback",
                old_value="",
                new_value=version_id,
                rationale=f"Rollback to version {version_id}",
            ))

        next_id = self._next_id()
        seq_num = self._next_sequence_number(target_id, target_type)

        record = EvolutionRecord.create(
            evolution_id=next_id,
            character_id=target_id,
            author=author,
            changes=changes,
            metadata={"rollback_to_version": version_id},
            name=f"Rollback to {version_id}",
            sequence_number=seq_num,
            target_type=target_type,
            target_id=target_id,
        )
        self._save(record)
        return record

    # ── Council Member Evolution ──────────────────────────────

    def create_council_evolution(
        self,
        member_name: str,
        *,
        author: str,
        changes: list[CharacterChange] | None = None,
        name: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> EvolutionRecord:
        """
        Create a new evolution for a council member (direct, no governance).

        Council member evolutions use ``target_type="council_member"``
        and are tracked/rollbackable but do not require proposals or votes.

        Raises:
            EvolutionValidationError: if inputs are invalid.
        """
        errors: list[str] = []
        if not member_name.strip():
            errors.append("Member name must not be empty")
        if not author.strip():
            errors.append("Author must not be empty")

        effective_changes = changes or []
        if not effective_changes:
            errors.append("At least one change is required")
        if len(effective_changes) > MAX_EVOLUTION_CHANGES:
            errors.append(
                f"Change count {len(effective_changes)} exceeds "
                f"maximum of {MAX_EVOLUTION_CHANGES}"
            )
        if errors:
            raise EvolutionValidationError(errors)

        # Validate council member exists
        from core.registry import CouncilRegistry, MemberNotFoundError
        registry = CouncilRegistry().load()
        try:
            member = registry.get(member_name)
        except MemberNotFoundError:
            raise EvolutionValidationError(
                [f"Council member '{member_name}' not found"]
            )

        target_id = f"CM-{member.name}"
        next_id = self._next_id()
        seq_num = self._next_sequence_number(target_id, "council_member")

        record = EvolutionRecord.create(
            evolution_id=next_id,
            character_id=target_id,
            author=author.strip(),
            changes=effective_changes,
            metadata={
                **(metadata or {}),
                "member_name": member.name,
                "member_role": member.role,
            },
            name=name or f"Evolution #{seq_num} for {member.name}",
            sequence_number=seq_num,
            target_type="council_member",
            target_id=target_id,
        )
        self._save(record)
        return record

    # ── Create from Proposal (Auto-fill) ──────────────────────

    def create_from_proposal(
        self,
        proposal_id: str,
        *,
        author: str = "",
    ) -> EvolutionRecord:
        """
        Auto-create an evolution from an approved evolution-category proposal.

        Reads the proposal body (expected to be a JSON list of change dicts)
        and pre-populates an EvolutionRecord in ``draft`` status.

        Raises:
            EvolutionValidationError: if proposal not found, not approved,
                or body is unparseable.
        """
        try:
            proposal = self._proposals.get(proposal_id)
        except Exception:
            raise EvolutionValidationError(
                [f"Proposal '{proposal_id}' not found"]
            )

        if proposal.status != "decided":
            raise EvolutionValidationError(
                [f"Proposal '{proposal_id}' is not in 'decided' status "
                 f"(current: '{proposal.status}')"]
            )

        # Parse changes from proposal body
        changes: list[CharacterChange] = []
        if proposal.body:
            try:
                raw_changes = json.loads(proposal.body)
                if isinstance(raw_changes, list):
                    for rc in raw_changes:
                        changes.append(CharacterChange.from_dict(rc))
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # body wasn't a changes list — that's OK

        # Extract character_id from proposal metadata
        prop_meta = proposal.metadata if hasattr(proposal, "metadata") else {}
        if isinstance(prop_meta, dict):
            character_id = prop_meta.get("character_id", "")
        else:
            character_id = ""

        evo_author = author or proposal.author
        evo_name = f"From proposal: {proposal.title}"

        next_id = self._next_id()

        if character_id:
            target_id = character_id
        else:
            target_id = "PENDING"

        seq_num = self._next_sequence_number(target_id, "character") if target_id != "PENDING" else 0

        record = EvolutionRecord.create(
            evolution_id=next_id,
            character_id=character_id or "PENDING",
            author=evo_author,
            changes=changes,
            metadata={
                "source_proposal_id": proposal_id,
                "source_proposal_title": proposal.title,
            },
            name=evo_name,
            sequence_number=seq_num,
            target_type="character",
            target_id=target_id,
        )
        self._save(record)
        return record

    # ── Enhanced create_evolution (with naming) ───────────────

    def create_named_evolution(
        self,
        character_id: str,
        *,
        author: str,
        name: str = "",
        changes: list[CharacterChange] | None = None,
        metadata: dict[str, Any] | None = None,
        target_type: str = "character",
    ) -> EvolutionRecord:
        """
        Enhanced create that includes naming and sequence tracking.

        Same validation as ``create_evolution`` but also assigns a
        human-friendly name and sequence number.
        """
        errors: list[str] = []
        if not character_id.strip():
            errors.append("Character ID must not be empty")
        if not author.strip():
            errors.append("Author must not be empty")

        effective_changes = changes or []
        if not effective_changes:
            errors.append("At least one change is required")
        if len(effective_changes) > MAX_EVOLUTION_CHANGES:
            errors.append(
                f"Change count {len(effective_changes)} exceeds "
                f"maximum of {MAX_EVOLUTION_CHANGES}"
            )
        if errors:
            raise EvolutionValidationError(errors)

        # Validate character exists and is active
        character = self._characters.get(character_id)
        if character.status != "active":
            raise EvolutionValidationError(
                [
                    f"Character '{character_id}' must be in 'active' status "
                    f"to evolve, current status: '{character.status}'"
                ]
            )

        target_id = character_id.strip()
        next_id = self._next_id()
        seq_num = self._next_sequence_number(target_id, target_type)
        evo_name = name or f"Evolution #{seq_num} for {character.name}"

        record = EvolutionRecord.create(
            evolution_id=next_id,
            character_id=character_id.strip(),
            author=author.strip(),
            changes=effective_changes,
            metadata=metadata,
            name=evo_name,
            sequence_number=seq_num,
            target_type=target_type,
            target_id=target_id,
        )
        self._save(record)
        return record

    # ── Query (enhanced) ──────────────────────────────────────

    def list_targets_with_active_overlays(self) -> list[dict[str, Any]]:
        """
        Return a list of targets that have an active evolution overlay.

        Each entry contains ``target_id``, ``target_type``, ``evolution_id``,
        and ``name``.
        """
        results: list[dict[str, Any]] = []
        for filepath in sorted(self._dir.glob("EV-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue
            if rec.overlay_status == "active":
                results.append({
                    "target_id": rec.target_id or rec.character_id,
                    "target_type": rec.target_type,
                    "evolution_id": rec.evolution_id,
                    "name": rec.name,
                })
        return results

    # ── Internal: Sequence Numbering ──────────────────────────

    def _next_sequence_number(
        self,
        target_id: str,
        target_type: str,
    ) -> int:
        """Return the next sequence number for a target entity."""
        max_seq = 0
        for filepath in self._dir.glob("EV-*.json"):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue
            effective_target = rec.target_id or rec.character_id
            if effective_target == target_id and rec.target_type == target_type:
                max_seq = max(max_seq, rec.sequence_number)
        return max_seq + 1

    # ── Internal: Persistence ─────────────────────────────────

    def _filepath(self, evolution_id: str) -> Path:
        return self._dir / f"{evolution_id}.json"

    def _save(self, record: EvolutionRecord) -> None:
        payload = json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(record.evolution_id), payload + "\n")

    def _load(self, filepath: Path) -> EvolutionRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return EvolutionRecord.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential EV-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("EV-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"EV-{max_num + 1:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("EV-*.json")))
        return f"CharacterEvolution(records={count}, dir={self._dir})"

