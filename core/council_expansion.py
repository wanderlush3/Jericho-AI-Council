"""
Jericho — Council Expansion (F-019)

Agents can propose adding new council members via the governance system.
Each expansion goes through a structured lifecycle:

    draft → proposed → voting → decided → applied
                                        ↘ rejected

Storage: one JSON file per expansion in ``data/council_expansions/``,
named ``CE-XXXX.json``.
"""

from __future__ import annotations

import json
import re
import yaml
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    EXPANSION_DIR,
    EXPANSION_STATUSES,
    MAX_COUNCIL_SIZE,
)
from core.registry import CouncilRegistry, VALID_API_PROVIDERS
from core.memory import SharedMemory
from core.proposals import ProposalManager
from core.utils import atomic_write, make_id_lock
from core.voting import VotingEngine


# ─── Exceptions ────────────────────────────────────────────────


class ExpansionError(Exception):
    """Base exception for council-expansion errors."""


class ExpansionNotFoundError(ExpansionError):
    """Raised when an expansion record cannot be found."""

    def __init__(self, expansion_id: str) -> None:
        self.expansion_id = expansion_id
        super().__init__(f"Expansion not found: '{expansion_id}'")


class ExpansionValidationError(ExpansionError):
    """Raised when expansion data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class ExpansionStateError(ExpansionError):
    """Raised when an operation conflicts with current expansion state."""

    def __init__(self, expansion_id: str, message: str) -> None:
        self.expansion_id = expansion_id
        super().__init__(
            f"Expansion state error for '{expansion_id}': {message}"
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
class MemberSpec:
    """Specification for a proposed new council member."""

    name: str
    role: str
    description: str
    personality: dict = field(default_factory=dict)
    api_provider: str = ""
    model: str = ""
    vote_weight: float = 1.0
    specialties: list[str] = field(default_factory=list)
    system_prompt: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemberSpec:
        return cls(
            name=data["name"],
            role=data["role"],
            description=data["description"],
            personality=data.get("personality", {}),
            api_provider=data.get("api_provider", ""),
            model=data.get("model", ""),
            vote_weight=float(data.get("vote_weight", 1.0)),
            specialties=list(data.get("specialties", [])),
            system_prompt=data.get("system_prompt", ""),
        )

    @classmethod
    def create(
        cls,
        name: str,
        role: str,
        description: str,
        *,
        personality: dict | None = None,
        api_provider: str = "openrouter",
        model: str = "anthropic/claude-3.5-sonnet",
        vote_weight: float = 1.0,
        specialties: list[str] | None = None,
        system_prompt: str = "",
    ) -> MemberSpec:
        """Factory with validation."""
        errors: list[str] = []
        if not name.strip():
            errors.append("Name must not be empty")
        if not role.strip():
            errors.append("Role must not be empty")
        if not description.strip():
            errors.append("Description must not be empty")
        if not api_provider.strip():
            errors.append("API provider must not be empty")
        if api_provider.strip() and api_provider.strip() not in VALID_API_PROVIDERS:
            errors.append(
                f"Invalid api_provider '{api_provider}' — must be one of "
                f"{sorted(VALID_API_PROVIDERS)}"
            )
        if not model.strip():
            errors.append("Model must not be empty")
        if not system_prompt.strip():
            errors.append("System prompt must not be empty")
        if vote_weight <= 0:
            errors.append(f"vote_weight must be positive, got {vote_weight}")
        if errors:
            raise ExpansionValidationError(errors)
        return cls(
            name=name.strip(),
            role=role.strip(),
            description=description.strip(),
            personality=personality or {},
            api_provider=api_provider.strip(),
            model=model.strip(),
            vote_weight=vote_weight,
            specialties=specialties or [],
            system_prompt=system_prompt.strip(),
        )

    def to_yaml(self) -> str:
        """Produce a YAML string matching the council/members/*.yaml format."""
        data: dict[str, Any] = {
            "name": self.name,
            "role": self.role,
            "description": self.description,
        }
        if self.personality:
            data["personality"] = dict(self.personality)
        data["api_provider"] = self.api_provider
        data["model"] = self.model
        data["vote_weight"] = self.vote_weight
        if self.specialties:
            data["specialties"] = list(self.specialties)
        data["system_prompt"] = self.system_prompt
        header = f"# Council Member: {self.name} — {self.role}\n"
        return header + yaml.dump(
            data,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


@dataclass(frozen=True)
class ExpansionRecord:
    """Persistent record of a council expansion proposal."""

    expansion_id: str
    author: str
    member_spec: MemberSpec | None = None
    proposal_id: str = ""          # links to ProposalManager
    vote_record_id: str = ""       # links to VotingEngine
    status: str = "draft"
    applied_member_file: str = ""  # path to written YAML file
    summary: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["member_spec"] = self.member_spec.to_dict() if self.member_spec else {}
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExpansionRecord:
        spec_data = data.get("member_spec", {})
        spec = MemberSpec.from_dict(spec_data) if spec_data else None
        return cls(
            expansion_id=data["expansion_id"],
            author=data["author"],
            member_spec=spec,
            proposal_id=data.get("proposal_id", ""),
            vote_record_id=data.get("vote_record_id", ""),
            status=data.get("status", "draft"),
            applied_member_file=data.get("applied_member_file", ""),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        expansion_id: str,
        author: str,
        member_spec: MemberSpec,
        metadata: dict[str, Any] | None = None,
    ) -> ExpansionRecord:
        """Factory that auto-fills timestamps."""
        if not expansion_id.strip():
            raise ExpansionValidationError(
                ["Expansion ID must not be empty"]
            )
        if not author.strip():
            raise ExpansionValidationError(
                ["Author must not be empty"]
            )
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            expansion_id=expansion_id.strip(),
            author=author.strip(),
            member_spec=member_spec,
            proposal_id="",
            vote_record_id="",
            status="draft",
            applied_member_file="",
            summary="",
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Helpers ───────────────────────────────────────────────────




# ─── Council Expansion ─────────────────────────────────────────


class CouncilExpansion:
    """
    Governance-backed council member addition system.

    Each expansion creates a proposal, goes through voting, and if
    approved, writes a new YAML profile to the council members directory.

    Usage::

        registry = CouncilRegistry().load()
        proposals = ProposalManager()
        engine = VotingEngine()
        expansion = CouncilExpansion(
            registry=registry,
            proposal_manager=proposals,
            voting_engine=engine,
        )

        spec = MemberSpec.create(
            "Nova", "Innovation Advisor", "Explores new ideas",
            api_provider="openrouter",
            model="anthropic/claude-3.5-sonnet",
            system_prompt="You are Nova...",
        )
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        # ... cast votes ...
        rec = expansion.resolve(rec.expansion_id)
        if rec.status == "decided":
            rec = expansion.apply_expansion(rec.expansion_id)
    """

    _ID_PATTERN = re.compile(r"^CE-(\d{4})\.json$")

    def __init__(
        self,
        *,
        registry: CouncilRegistry,
        proposal_manager: ProposalManager,
        voting_engine: VotingEngine,
        expansions_dir: Path | None = None,
        members_dir: Path | None = None,
        shared_memory: SharedMemory | None = None,
    ) -> None:
        self._registry = registry
        self._proposals = proposal_manager
        self._voting = voting_engine
        self._dir = expansions_dir or EXPANSION_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._members_dir = members_dir or self._registry._members_dir
        self._shared_memory = shared_memory or SharedMemory()
        self._id_lock = make_id_lock()

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def registry(self) -> CouncilRegistry:
        return self._registry

    @property
    def proposal_manager(self) -> ProposalManager:
        return self._proposals

    @property
    def voting_engine(self) -> VotingEngine:
        return self._voting

    # ── Create ────────────────────────────────────────────────

    def create_expansion(
        self,
        member_spec: MemberSpec,
        *,
        author: str,
        metadata: dict[str, Any] | None = None,
    ) -> ExpansionRecord:
        """
        Create a new council expansion in *draft* status.

        Auto-generates a sequential ``CE-XXXX`` ID.  Validates that
        MAX_COUNCIL_SIZE would not be exceeded and that the proposed
        member name is not already in the registry.

        Raises:
            ExpansionValidationError: if inputs are invalid.
        """
        errors: list[str] = []
        if not author.strip():
            errors.append("Author must not be empty")

        # Check council size limit
        current_size = len(self._registry)
        if current_size >= MAX_COUNCIL_SIZE:
            errors.append(
                f"Council already at maximum size ({MAX_COUNCIL_SIZE})"
            )

        # Check name uniqueness (case-insensitive)
        if member_spec.name.strip().lower() in self._registry:
            errors.append(
                f"A council member named '{member_spec.name}' already exists"
            )

        if errors:
            raise ExpansionValidationError(errors)

        with self._id_lock:
            next_id = self._next_id()
            record = ExpansionRecord.create(
                expansion_id=next_id,
                author=author.strip(),
                member_spec=member_spec,
                metadata=metadata,
            )
            self._save(record)
        return record

    # ── Submit for Review ─────────────────────────────────────

    def submit_for_review(self, expansion_id: str) -> ExpansionRecord:
        """
        Create a governance proposal for this expansion and transition
        to ``proposed`` status.

        Creates a ``Proposal`` via ``ProposalManager`` with
        category ``"expansion"`` and links the proposal ID.

        Raises:
            ExpansionNotFoundError: if expansion doesn't exist.
            ExpansionStateError: if not in ``draft`` status.
        """
        record = self.get(expansion_id)
        self._validate_transition(record, "proposed")

        spec = record.member_spec
        description = (
            f"Proposal to add new council member:\n"
            f"- **Name:** {spec.name}\n"
            f"- **Role:** {spec.role}\n"
            f"- **Description:** {spec.description}\n"
            f"- **Provider:** {spec.api_provider}\n"
            f"- **Model:** {spec.model}\n"
        )

        # Create proposal via ProposalManager
        proposal = self._proposals.create(
            f"Add Council Member: {spec.name}",
            description,
            author=record.author,
            category="expansion",
            body=json.dumps(
                spec.to_dict(),
                indent=2,
                ensure_ascii=False,
            ),
            metadata={
                "expansion_id": record.expansion_id,
                "member_name": spec.name,
            },
        )

        # Transition proposal to open
        self._proposals.update_status(proposal.id, "open")

        now = datetime.now(timezone.utc).isoformat()
        updated = ExpansionRecord(
            expansion_id=record.expansion_id,
            author=record.author,
            member_spec=record.member_spec,
            proposal_id=proposal.id,
            vote_record_id=record.vote_record_id,
            status="proposed",
            applied_member_file=record.applied_member_file,
            summary=record.summary,
            created_at=record.created_at,
            updated_at=now,
            metadata=dict(record.metadata),
        )
        self._save(updated)
        return updated

    # ── Open Voting ───────────────────────────────────────────

    def open_voting(self, expansion_id: str) -> ExpansionRecord:
        """
        Open voting on the linked proposal and transition to ``voting``.

        Raises:
            ExpansionNotFoundError: if expansion doesn't exist.
            ExpansionStateError: if not in ``proposed`` status.
        """
        record = self.get(expansion_id)
        self._validate_transition(record, "voting")

        if not record.proposal_id:
            raise ExpansionStateError(
                expansion_id,
                "No proposal linked — call submit_for_review first",
            )

        # Transition proposal to under_review
        self._proposals.update_status(record.proposal_id, "under_review")

        # Open voting via VotingEngine
        vote_record = self._voting.open_voting(
            record.proposal_id,
            metadata={
                "expansion_id": record.expansion_id,
                "member_name": record.member_spec.name,
            },
        )

        now = datetime.now(timezone.utc).isoformat()
        updated = ExpansionRecord(
            expansion_id=record.expansion_id,
            author=record.author,
            member_spec=record.member_spec,
            proposal_id=record.proposal_id,
            vote_record_id=vote_record.proposal_id,
            status="voting",
            applied_member_file=record.applied_member_file,
            summary=record.summary,
            created_at=record.created_at,
            updated_at=now,
            metadata=dict(record.metadata),
        )
        self._save(updated)
        return updated

    # ── Resolve ───────────────────────────────────────────────

    def resolve(self, expansion_id: str) -> ExpansionRecord:
        """
        Tally votes and transition to ``decided`` (approved) or
        ``rejected``.

        Closes voting, tallies results, and transitions the proposal
        to ``decided`` status.

        Raises:
            ExpansionNotFoundError: if expansion doesn't exist.
            ExpansionStateError: if not in ``voting`` status.
        """
        record = self.get(expansion_id)

        if record.status != "voting":
            raise ExpansionStateError(
                expansion_id,
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
            f"{',' + ' VETOED' if tally.vetoed else ''})"
        )

        updated = ExpansionRecord(
            expansion_id=record.expansion_id,
            author=record.author,
            member_spec=record.member_spec,
            proposal_id=record.proposal_id,
            vote_record_id=record.vote_record_id,
            status=new_status,
            applied_member_file=record.applied_member_file,
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
            "type": "expansion_resolved",
            "expansion_id": record.expansion_id,
            "member_name": record.member_spec.name,
            "result": new_status,
            "tally": tally.to_dict(),
            "resolved_at": now,
        })

        return updated

    # ── Apply Expansion ───────────────────────────────────────

    def apply_expansion(self, expansion_id: str) -> ExpansionRecord:
        """
        Write the approved member profile as a YAML file to the
        council members directory.

        Raises:
            ExpansionNotFoundError: if expansion doesn't exist.
            ExpansionStateError: if not in ``decided`` status.
        """
        record = self.get(expansion_id)
        self._validate_transition(record, "applied")

        spec = record.member_spec
        yaml_content = spec.to_yaml()
        filename = f"{spec.name.lower().replace(' ', '_')}.yaml"
        member_filepath = self._members_dir / filename

        atomic_write(member_filepath, yaml_content)

        now = datetime.now(timezone.utc).isoformat()
        updated = ExpansionRecord(
            expansion_id=record.expansion_id,
            author=record.author,
            member_spec=record.member_spec,
            proposal_id=record.proposal_id,
            vote_record_id=record.vote_record_id,
            status="applied",
            applied_member_file=str(member_filepath),
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
            "type": "expansion_applied",
            "expansion_id": record.expansion_id,
            "member_name": spec.name,
            "member_file": str(member_filepath),
            "applied_at": now,
        })

        self._shared_memory.append_history(
            f"### Council Expansion: {record.expansion_id}\n"
            f"**Applied:** {now}\n"
            f"**New Member:** {spec.name} ({spec.role})\n"
            f"**Author:** {record.author}\n\n"
            f"{record.summary}\n"
        )

        return updated

    # ── Query ─────────────────────────────────────────────────

    def get(self, expansion_id: str) -> ExpansionRecord:
        """
        Load an expansion record by ID.

        Raises:
            ExpansionNotFoundError: if no expansion file exists.
        """
        filepath = self._filepath(expansion_id)
        if not filepath.exists():
            raise ExpansionNotFoundError(expansion_id)
        return self._load(filepath)

    def list_expansions(
        self,
        *,
        status: str | None = None,
        author: str | None = None,
    ) -> list[ExpansionRecord]:
        """
        Return expansions sorted by ID, with optional filters.
        """
        expansions: list[ExpansionRecord] = []
        for filepath in sorted(self._dir.glob("CE-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if status is not None and rec.status != status:
                continue
            if author is not None and rec.author.lower() != author.strip().lower():
                continue
            expansions.append(rec)
        return expansions

    def has_expansion(self, expansion_id: str) -> bool:
        """Check if an expansion record exists."""
        return self._filepath(expansion_id).exists()

    # ── Internal: Lifecycle ───────────────────────────────────

    def _validate_transition(
        self,
        record: ExpansionRecord,
        new_status: str,
    ) -> None:
        """Validate a lifecycle transition."""
        if new_status not in EXPANSION_STATUSES:
            raise ExpansionValidationError(
                [
                    f"Unknown status '{new_status}' — must be one of "
                    f"{EXPANSION_STATUSES}"
                ]
            )
        allowed = _VALID_TRANSITIONS.get(record.status, set())
        if new_status not in allowed:
            raise ExpansionStateError(
                record.expansion_id,
                f"Cannot transition from '{record.status}' to '{new_status}'",
            )

    # ── Internal: Persistence ─────────────────────────────────

    def _filepath(self, expansion_id: str) -> Path:
        return self._dir / f"{expansion_id}.json"

    def _save(self, record: ExpansionRecord) -> None:
        payload = json.dumps(record.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(record.expansion_id), payload + "\n")

    def _load(self, filepath: Path) -> ExpansionRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return ExpansionRecord.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential CE-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("CE-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"CE-{max_num + 1:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("CE-*.json")))
        return f"CouncilExpansion(records={count}, dir={self._dir})"
