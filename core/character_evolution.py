"""
Jericho — Character Evolution (F-013)

Propose and vote on modifications to existing characters via the governance
system.  Each evolution goes through a structured lifecycle:

    draft → proposed → voting → decided → applied
                                        ↘ rejected

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
    EVOLUTION_STATUSES,
    EVOLUTION_TYPES,
    MAX_EVOLUTION_CHANGES,
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


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"proposed"},
    "proposed": {"voting"},
    "voting": {"decided", "rejected"},
    "decided": {"applied"},
    "applied": set(),      # terminal
    "rejected": set(),     # terminal
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
    character_id: str
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
        return cls(
            evolution_id=data["evolution_id"],
            character_id=data["character_id"],
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
        )

    @classmethod
    def create(
        cls,
        evolution_id: str,
        character_id: str,
        author: str,
        changes: list[CharacterChange] | None = None,
        metadata: dict[str, Any] | None = None,
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
        )


# ─── Helpers ───────────────────────────────────────────────────

# _atomic_write is imported from core.utils


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

        next_id = self._next_id()
        record = EvolutionRecord.create(
            evolution_id=next_id,
            character_id=character_id.strip(),
            author=author.strip(),
            changes=effective_changes,
            metadata=metadata,
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

        now = datetime.now(timezone.utc).isoformat()
        updated = EvolutionRecord(
            evolution_id=record.evolution_id,
            character_id=record.character_id,
            author=record.author,
            changes=list(record.changes),
            proposal_id=proposal.id,
            vote_record_id=record.vote_record_id,
            status="proposed",
            applied_character_id=record.applied_character_id,
            summary=record.summary,
            created_at=record.created_at,
            updated_at=now,
            metadata=dict(record.metadata),
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

        now = datetime.now(timezone.utc).isoformat()
        updated = EvolutionRecord(
            evolution_id=record.evolution_id,
            character_id=record.character_id,
            author=record.author,
            changes=list(record.changes),
            proposal_id=record.proposal_id,
            vote_record_id=vote_record.proposal_id,
            status="voting",
            applied_character_id=record.applied_character_id,
            summary=record.summary,
            created_at=record.created_at,
            updated_at=now,
            metadata=dict(record.metadata),
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

        updated = EvolutionRecord(
            evolution_id=record.evolution_id,
            character_id=record.character_id,
            author=record.author,
            changes=list(record.changes),
            proposal_id=record.proposal_id,
            vote_record_id=record.vote_record_id,
            status=new_status,
            applied_character_id=record.applied_character_id,
            summary=summary,
            created_at=record.created_at,
            updated_at=now,
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
        updated = EvolutionRecord(
            evolution_id=record.evolution_id,
            character_id=record.character_id,
            author=record.author,
            changes=list(record.changes),
            proposal_id=record.proposal_id,
            vote_record_id=record.vote_record_id,
            status="applied",
            applied_character_id=new_template.id,
            summary=record.summary,
            created_at=record.created_at,
            updated_at=now,
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
