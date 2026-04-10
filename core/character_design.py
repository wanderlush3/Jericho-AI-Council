"""
Jericho — Collaborative Character Design (F-012)

Council members contribute to AI character creation via structured prompts.
A multi-phase design process (concept → traits → backstory → prompt → review)
produces a ``CharacterTemplate`` that can be managed by the character system.

Storage:
    Each design session gets a JSON file in ``data/character_designs/``
    named ``CD-XXXX.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    CHARACTER_DESIGNS_DIR,
    DEFAULT_DESIGN_PHASES,
    MAX_DESIGN_CONTRIBUTORS,
)
from core.api_client import APIClient, ChatMessage, ChatResponse
from core.characters import CharacterManager, CharacterTemplate, Trait
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.registry import CouncilMember, CouncilRegistry
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class DesignError(Exception):
    """Base exception for character-design errors."""


class DesignNotFoundError(DesignError):
    """Raised when a design record cannot be found."""

    def __init__(self, design_id: str) -> None:
        self.design_id = design_id
        super().__init__(f"Design not found: '{design_id}'")


class DesignValidationError(DesignError):
    """Raised when design data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class DesignStateError(DesignError):
    """Raised when an operation conflicts with current design state."""

    def __init__(self, design_id: str, message: str) -> None:
        self.design_id = design_id
        super().__init__(
            f"Design state error for '{design_id}': {message}"
        )


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class DesignContribution:
    """A single contribution from a council member to a design phase."""

    speaker: str
    content: str
    phase: str = ""
    parsed_data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DesignContribution:
        return cls(
            speaker=data["speaker"],
            content=data["content"],
            phase=data.get("phase", ""),
            parsed_data=data.get("parsed_data", {}),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        speaker: str,
        content: str,
        phase: str = "",
        parsed_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DesignContribution:
        """Factory that auto-fills the timestamp."""
        return cls(
            speaker=speaker,
            content=content,
            phase=phase,
            parsed_data=parsed_data or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class DesignRecord:
    """Persistent record of a collaborative character design session."""

    design_id: str
    title: str
    contributors: list[str] = field(default_factory=list)
    contributions: list[DesignContribution] = field(default_factory=list)
    current_phase: str = ""
    phases_completed: list[str] = field(default_factory=list)
    target_character_id: str = ""  # links to CharacterManager after assembly
    status: str = "open"  # open / closed
    summary: str = ""
    created_at: str = ""
    closed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["contributions"] = [c.to_dict() for c in self.contributions]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DesignRecord:
        contributions = [
            DesignContribution.from_dict(c)
            for c in data.get("contributions", [])
        ]
        return cls(
            design_id=data["design_id"],
            title=data["title"],
            contributors=list(data.get("contributors", [])),
            contributions=contributions,
            current_phase=data.get("current_phase", ""),
            phases_completed=list(data.get("phases_completed", [])),
            target_character_id=data.get("target_character_id", ""),
            status=data.get("status", "open"),
            summary=data.get("summary", ""),
            created_at=data.get("created_at", ""),
            closed_at=data.get("closed_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        design_id: str,
        title: str,
        contributors: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DesignRecord:
        """Factory that auto-fills the created_at timestamp."""
        if not design_id.strip():
            raise DesignValidationError(
                ["Design ID must not be empty"]
            )
        if not title.strip():
            raise DesignValidationError(["Title must not be empty"])
        return cls(
            design_id=design_id.strip(),
            title=title.strip(),
            contributors=contributors or [],
            contributions=[],
            current_phase="",
            phases_completed=[],
            target_character_id="",
            status="open",
            summary="",
            created_at=datetime.now(timezone.utc).isoformat(),
            closed_at="",
            metadata=metadata or {},
        )


# ─── Helpers ───────────────────────────────────────────────────




def _build_concept_prompt(
    record: DesignRecord,
    member: CouncilMember,
) -> str:
    """Build a prompt asking the member to propose a character concept."""
    parts = [
        f"## Character Design: {record.title}",
        f"**Design ID:** {record.design_id}",
        f"\nYou are participating in a collaborative character design session.",
        f"\n### Phase: Concept",
        f"In this phase, propose a character concept. Include:",
        f"- **Name**: A distinctive character name",
        f"- **Role**: What this character does or represents",
        f"- **Core Identity**: 2-3 sentences described in character.",
        f"\n---",
        f"As **{member.name}** ({member.role}), propose your vision for "
        f"this character. Draw on your unique perspective and expertise. "
        f"Be creative but concise.",
    ]
    return "\n".join(parts)


def _build_traits_prompt(
    record: DesignRecord,
    member: CouncilMember,
    prior: list[DesignContribution],
) -> str:
    """Build a prompt asking the member to propose character traits."""
    parts = [
        f"## Character Design: {record.title}",
        f"**Design ID:** {record.design_id}",
        f"\n### Phase: Traits",
        f"Propose personality traits, values, and flaws for this character.",
        f"For each trait include:",
        f"- **Type**: personality, values, flaws, or a custom type",
        f"- **Name**: A short trait name",
        f"- **Description**: What this trait means for the character",
        f"- **Intensity**: A value from 0.0 (subtle) to 1.0 (dominant)",
    ]

    if prior:
        parts.append("\n### Prior Contributions")
        for c in prior[-10:]:
            parts.append(f"**{c.speaker}** ({c.phase}): {c.content}")

    parts.append(
        f"\n---\n"
        f"As **{member.name}** ({member.role}), suggest 2-3 traits that "
        f"would make this character compelling. Consider the prior "
        f"contributions above."
    )
    return "\n".join(parts)


def _build_backstory_prompt(
    record: DesignRecord,
    member: CouncilMember,
    prior: list[DesignContribution],
) -> str:
    """Build a prompt asking the member to develop backstory elements."""
    parts = [
        f"## Character Design: {record.title}",
        f"**Design ID:** {record.design_id}",
        f"\n### Phase: Backstory",
        f"Develop the character's backstory. Consider:",
        f"- **Origin**: Where they came from",
        f"- **Key Events**: Formative experiences",
        f"- **Motivations**: What drives them",
    ]

    if prior:
        parts.append("\n### Prior Contributions")
        for c in prior[-10:]:
            parts.append(f"**{c.speaker}** ({c.phase}): {c.content}")

    parts.append(
        f"\n---\n"
        f"As **{member.name}** ({member.role}), contribute backstory "
        f"elements that build on the concept and traits above. Keep it "
        f"to a focused paragraph."
    )
    return "\n".join(parts)


def _build_prompt_prompt(
    record: DesignRecord,
    member: CouncilMember,
    prior: list[DesignContribution],
) -> str:
    """Build a prompt asking the member to craft a system prompt / greeting."""
    parts = [
        f"## Character Design: {record.title}",
        f"**Design ID:** {record.design_id}",
        f"\n### Phase: Prompt",
        f"Craft the character's AI system prompt and opening greeting.",
        f"The system prompt should instruct an LLM to roleplay as this "
        f"character consistently. The greeting is the character's first "
        f"message to a new user.",
    ]

    if prior:
        parts.append("\n### Prior Contributions")
        for c in prior[-10:]:
            parts.append(f"**{c.speaker}** ({c.phase}): {c.content}")

    parts.append(
        f"\n---\n"
        f"As **{member.name}** ({member.role}), draft a system prompt "
        f"and greeting that capture the character's essence based on "
        f"everything contributed so far."
    )
    return "\n".join(parts)


def _build_review_prompt(
    record: DesignRecord,
    member: CouncilMember,
    prior: list[DesignContribution],
) -> str:
    """Build a prompt asking the member to review the character holistically."""
    parts = [
        f"## Character Design: {record.title}",
        f"**Design ID:** {record.design_id}",
        f"\n### Phase: Review",
        f"Review the character design holistically. Consider:",
        f"- **Consistency**: Do all elements fit together?",
        f"- **Depth**: Is the character well-rounded?",
        f"- **Engagement**: Will users enjoy interacting with this character?",
        f"- **Improvements**: What could be refined?",
    ]

    if prior:
        parts.append("\n### All Contributions")
        for c in prior[-10:]:
            parts.append(f"**{c.speaker}** ({c.phase}): {c.content}")

    parts.append(
        f"\n---\n"
        f"As **{member.name}** ({member.role}), provide your review of "
        f"this character. Highlight strengths and suggest improvements. "
        f"Be constructive and specific."
    )
    return "\n".join(parts)


_PROMPT_BUILDERS = {
    "concept": _build_concept_prompt,
    "traits": _build_traits_prompt,
    "backstory": _build_backstory_prompt,
    "prompt": _build_prompt_prompt,
    "review": _build_review_prompt,
}


# ─── Character Designer ──────────────────────────────────────


class CharacterDesigner:
    """
    Orchestrates collaborative character design by council members.

    Each design session runs through multiple phases (concept, traits,
    backstory, prompt, review) where each contributor provides their
    perspective.  After all phases, the contributions are assembled
    into a ``CharacterTemplate`` via ``CharacterManager``.

    Usage::

        registry = CouncilRegistry().load()
        chars = CharacterManager()
        async with APIClient() as client:
            designer = CharacterDesigner(
                registry=registry,
                api_client=client,
                character_manager=chars,
            )
            rec = designer.create_design(
                "CD-001", "A Curious Explorer",
                contributors=["Forge", "Spark", "Sage"],
            )
            rec = await designer.run_all_phases("CD-001")
            template = designer.assemble_character("CD-001")
            rec = designer.close_design("CD-001")
    """

    _ID_PATTERN = re.compile(r"^CD-(\d{4})\.json$")

    def __init__(
        self,
        *,
        registry: CouncilRegistry,
        api_client: APIClient,
        character_manager: CharacterManager,
        designs_dir: Path | None = None,
        shared_memory: SharedMemory | None = None,
    ) -> None:
        self._registry = registry
        self._api_client = api_client
        self._character_manager = character_manager
        self._dir = designs_dir or CHARACTER_DESIGNS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._shared_memory = shared_memory or SharedMemory()

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def registry(self) -> CouncilRegistry:
        return self._registry

    @property
    def character_manager(self) -> CharacterManager:
        return self._character_manager

    # ── Design Lifecycle ──────────────────────────────────────

    def create_design(
        self,
        design_id: str,
        title: str,
        *,
        contributors: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> DesignRecord:
        """
        Create a new collaborative design session.

        Validates contributors are real council members.

        Raises:
            DesignValidationError: if inputs are invalid.
            DesignError: if a design with this ID already exists.
        """
        filepath = self._filepath(design_id.strip())
        if filepath.exists():
            raise DesignError(
                f"Design already exists: '{design_id}'"
            )

        contributors = contributors or []

        # Validate minimum contributors
        if len(contributors) < 1:
            raise DesignValidationError(
                ["At least 1 contributor is required"]
            )

        # Validate contributor count
        if len(contributors) > MAX_DESIGN_CONTRIBUTORS:
            raise DesignValidationError(
                [
                    f"Contributor count {len(contributors)} exceeds "
                    f"maximum of {MAX_DESIGN_CONTRIBUTORS}"
                ]
            )

        # Validate all contributors are real members
        known_names = [n.lower() for n in self._registry.list_names()]
        for name in contributors:
            if name.lower() not in known_names:
                raise DesignValidationError(
                    [f"Unknown council member: '{name}'"]
                )

        record = DesignRecord.create(
            design_id=design_id,
            title=title,
            contributors=contributors,
            metadata=metadata,
        )
        self._save(record)
        return record

    async def run_phase(
        self,
        design_id: str,
        phase_name: str,
        member_names: list[str] | None = None,
    ) -> DesignRecord:
        """
        Run one design phase where each contributor provides input.

        Each contributor sees all prior contributions and adds their
        perspective for the current phase.

        Args:
            design_id: The design session to run.
            phase_name: The phase to run (concept, traits, backstory,
                prompt, review).
            member_names: Specific members to participate. If None,
                uses all contributors from the design record.

        Raises:
            DesignNotFoundError: if the design doesn't exist.
            DesignStateError: if the design is closed.
            DesignValidationError: if the phase name is invalid.
        """
        record = self.get(design_id)

        if record.status != "open":
            raise DesignStateError(
                design_id, "Design is closed"
            )

        if phase_name not in DEFAULT_DESIGN_PHASES:
            raise DesignValidationError(
                [
                    f"Unknown phase '{phase_name}' — must be one of "
                    f"{DEFAULT_DESIGN_PHASES}"
                ]
            )

        effective_members = member_names or list(record.contributors)
        new_contributions: list[DesignContribution] = []

        for name in effective_members:
            member = self._registry.get(name)

            # Collect all prior contributions + new ones from this phase
            all_prior = list(record.contributions) + new_contributions

            # Build phase-appropriate prompt
            if phase_name == "concept":
                prompt = _build_concept_prompt(record, member)
            else:
                builder = _PROMPT_BUILDERS[phase_name]
                prompt = builder(record, member, all_prior)

            # Send to API
            messages = [ChatMessage(role="user", content=prompt)]
            response = await self._api_client.chat(member, messages)

            contribution = DesignContribution.create(
                speaker=member.name,
                content=response.content,
                phase=phase_name,
                metadata={
                    "model": response.model,
                    "provider": response.provider,
                },
            )
            new_contributions.append(contribution)

            # Record to agent memory
            agent_mem = AgentMemory(member.name)
            agent_mem.append_session_event(
                MemoryEntry.create(
                    session_id=design_id,
                    event_type="character_design",
                    content=(
                        f"Contributed to character design '{record.title}' "
                        f"({phase_name} phase): {response.content[:200]}"
                    ),
                    source="character_design",
                )
            )

        # Update record with new contributions and phase tracking
        all_contributions = list(record.contributions) + new_contributions
        phases_completed = list(record.phases_completed)
        if phase_name not in phases_completed:
            phases_completed.append(phase_name)

        record = DesignRecord(
            design_id=record.design_id,
            title=record.title,
            contributors=list(record.contributors),
            contributions=all_contributions,
            current_phase=phase_name,
            phases_completed=phases_completed,
            target_character_id=record.target_character_id,
            status=record.status,
            summary=record.summary,
            created_at=record.created_at,
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )
        self._save(record)
        return record

    async def run_all_phases(
        self,
        design_id: str,
        member_names: list[str] | None = None,
        phases: list[str] | None = None,
    ) -> DesignRecord:
        """
        Run all remaining design phases (or a custom list).

        Args:
            design_id: The design to run.
            member_names: Specific members to participate. If None,
                uses all contributors from the design record.
            phases: Custom phase list. If None, runs all phases from
                DEFAULT_DESIGN_PHASES that haven't been completed yet.

        Returns:
            The final DesignRecord with all contributions.

        Raises:
            DesignNotFoundError: if the design doesn't exist.
            DesignStateError: if the design is closed.
        """
        record = self.get(design_id)

        if record.status != "open":
            raise DesignStateError(
                design_id, "Design is closed"
            )

        target_phases = phases or list(DEFAULT_DESIGN_PHASES)
        remaining = [
            p for p in target_phases
            if p not in record.phases_completed
        ]

        for phase in remaining:
            record = await self.run_phase(
                design_id, phase, member_names
            )

        return record

    def assemble_character(
        self,
        design_id: str,
        *,
        author: str = "Council",
    ) -> CharacterTemplate:
        """
        Parse all contributions and create a ``CharacterTemplate``.

        Extracts character data from each phase's contributions:
        - **concept**: name + description
        - **traits**: parsed or generated traits
        - **backstory**: combined backstory text
        - **prompt**: system prompt and greeting
        - **review**: stored in metadata

        The resulting template is linked back to the design via
        ``metadata["design_id"]``.

        Raises:
            DesignNotFoundError: if the design doesn't exist.
            DesignStateError: if the design is closed.
        """
        record = self.get(design_id)

        if record.status != "open":
            raise DesignStateError(
                design_id, "Design is closed"
            )

        # Extract data from each phase
        concept_text = self._gather_phase_text(record, "concept")
        traits_text = self._gather_phase_text(record, "traits")
        backstory_text = self._gather_phase_text(record, "backstory")
        prompt_text = self._gather_phase_text(record, "prompt")
        review_text = self._gather_phase_text(record, "review")

        # Build character name and description from concept
        name = self._extract_name(concept_text, record.title)
        description = concept_text[:500] if concept_text else record.title

        # Build traits — create defaults from the contributions
        traits = self._extract_traits(traits_text)

        # Assemble backstory
        backstory = backstory_text

        # Extract system prompt and greeting
        system_prompt = prompt_text
        greeting = ""

        # Create character via CharacterManager
        template = self._character_manager.create(
            name,
            description,
            author=author,
            backstory=backstory,
            traits=traits,
            system_prompt=system_prompt,
            greeting=greeting,
            tags=["council-designed"],
            metadata={
                "design_id": design_id,
                "contributors": list(record.contributors),
                "review": review_text,
            },
        )

        # Link the character back to the design record
        record = DesignRecord(
            design_id=record.design_id,
            title=record.title,
            contributors=list(record.contributors),
            contributions=list(record.contributions),
            current_phase=record.current_phase,
            phases_completed=list(record.phases_completed),
            target_character_id=template.id,
            status=record.status,
            summary=record.summary,
            created_at=record.created_at,
            closed_at=record.closed_at,
            metadata=dict(record.metadata),
        )
        self._save(record)

        return template

    def close_design(
        self,
        design_id: str,
        summary: str = "",
    ) -> DesignRecord:
        """
        Close a design session and persist summary to shared memory.

        Raises:
            DesignNotFoundError: if the design doesn't exist.
            DesignStateError: if the design is already closed.
        """
        record = self.get(design_id)

        if record.status != "open":
            raise DesignStateError(
                design_id, "Design is already closed"
            )

        now = datetime.now(timezone.utc).isoformat()
        final_summary = summary or self._generate_summary(record)

        record = DesignRecord(
            design_id=record.design_id,
            title=record.title,
            contributors=list(record.contributors),
            contributions=list(record.contributions),
            current_phase=record.current_phase,
            phases_completed=list(record.phases_completed),
            target_character_id=record.target_character_id,
            status="closed",
            summary=final_summary,
            created_at=record.created_at,
            closed_at=now,
            metadata=dict(record.metadata),
        )
        self._save(record)

        # Record to shared memory
        self._shared_memory.record_decision({
            "type": "design_closed",
            "design_id": record.design_id,
            "title": record.title,
            "contributors": record.contributors,
            "phases_completed": record.phases_completed,
            "contribution_count": len(record.contributions),
            "target_character_id": record.target_character_id,
            "summary": final_summary,
            "closed_at": now,
        })

        self._shared_memory.append_history(
            f"### Character Design: {record.title} ({record.design_id})\n"
            f"**Closed:** {now}\n"
            f"**Contributors:** {', '.join(record.contributors)}\n"
            f"**Phases:** {', '.join(record.phases_completed)}\n"
            f"**Character:** {record.target_character_id or 'not assembled'}\n\n"
            f"{final_summary}\n"
        )

        return record

    # ── Query ─────────────────────────────────────────────────

    def get(self, design_id: str) -> DesignRecord:
        """
        Load a design record by ID.

        Raises:
            DesignNotFoundError: if no design file exists.
        """
        filepath = self._filepath(design_id)
        if not filepath.exists():
            raise DesignNotFoundError(design_id)
        return self._load(filepath)

    def list_designs(
        self,
        *,
        status: str | None = None,
        contributor: str | None = None,
    ) -> list[DesignRecord]:
        """
        Return all designs, optionally filtered.

        Args:
            status: Filter by status (open/closed).
            contributor: Filter to designs including this member.
        """
        records: list[DesignRecord] = []
        for filepath in sorted(self._dir.glob("CD-*.json")):
            try:
                rec = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if status is not None and rec.status != status:
                continue
            if contributor is not None:
                if contributor.lower() not in [
                    c.lower() for c in rec.contributors
                ]:
                    continue
            records.append(rec)
        return records

    def has_design(self, design_id: str) -> bool:
        """Check if a design record exists."""
        return self._filepath(design_id).exists()

    def get_contributions(
        self,
        design_id: str,
        *,
        speaker: str | None = None,
        phase: str | None = None,
    ) -> list[DesignContribution]:
        """
        Get design contributions, optionally filtered.

        Raises:
            DesignNotFoundError: if no design exists.
        """
        record = self.get(design_id)
        results = list(record.contributions)
        if speaker is not None:
            speaker_lower = speaker.lower()
            results = [
                c for c in results if c.speaker.lower() == speaker_lower
            ]
        if phase is not None:
            results = [
                c for c in results if c.phase == phase
            ]
        return results

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, design_id: str) -> Path:
        return self._dir / f"CD-{design_id}.json"

    def _save(self, record: DesignRecord) -> None:
        payload = json.dumps(
            record.to_dict(), indent=2, ensure_ascii=False
        )
        atomic_write(self._filepath(record.design_id), payload + "\n")

    def _load(self, filepath: Path) -> DesignRecord:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return DesignRecord.from_dict(data)

    def _gather_phase_text(
        self, record: DesignRecord, phase: str
    ) -> str:
        """Concatenate all contribution content for a given phase."""
        parts = [
            c.content
            for c in record.contributions
            if c.phase == phase
        ]
        return "\n\n".join(parts)

    def _extract_name(self, concept_text: str, fallback: str) -> str:
        """Extract a character name from concept text, or use fallback."""
        if not concept_text:
            return fallback

        # Look for "Name: something" pattern
        for line in concept_text.split("\n"):
            line_stripped = line.strip()
            if line_stripped.lower().startswith("name:"):
                name = line_stripped.split(":", 1)[1].strip()
                # Remove markdown bold markers
                name = name.replace("**", "").strip()
                if name:
                    return name

        # Fallback: use first non-empty line, truncated
        for line in concept_text.split("\n"):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                # Trim to first sentence or first 50 chars
                name = stripped.split(".")[0][:50].strip()
                if name:
                    return name

        return fallback

    def _extract_traits(self, traits_text: str) -> list[Trait]:
        """Extract traits from contribution text, with sensible defaults."""
        if not traits_text:
            return [
                Trait.create("personality", "Collaborative",
                             "Designed through council collaboration",
                             intensity=0.5),
            ]

        traits: list[Trait] = []
        seen_names: set[str] = set()

        # Try to parse structured trait mentions
        for line in traits_text.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Look for lines with trait-like content
            # Pattern: "- **Name**: Description" or "- Name: Description"
            if line.startswith("-") or line.startswith("*"):
                clean = line.lstrip("-*").strip()
                # Try to split on colon
                if ":" in clean:
                    name_part, desc_part = clean.split(":", 1)
                    name_part = name_part.replace("**", "").strip()
                    desc_part = desc_part.strip()
                    if name_part and desc_part and name_part.lower() not in seen_names:
                        seen_names.add(name_part.lower())
                        trait_type = self._guess_trait_type(name_part, desc_part)
                        traits.append(
                            Trait.create(
                                trait_type, name_part, desc_part,
                                intensity=0.5,
                            )
                        )

        # Ensure at least one trait
        if not traits:
            traits.append(
                Trait.create("personality", "Collaborative",
                             "Designed through council collaboration",
                             intensity=0.5),
            )

        return traits

    def _guess_trait_type(self, name: str, description: str) -> str:
        """Guess the trait type from name and description text."""
        combined = (name + " " + description).lower()
        if any(w in combined for w in ("flaw", "weakness", "struggle",
                                        "fear", "insecure")):
            return "flaws"
        if any(w in combined for w in ("value", "moral", "belief",
                                        "principle", "ethic")):
            return "values"
        return "personality"

    def _generate_summary(self, record: DesignRecord) -> str:
        """Generate a default summary from design data."""
        contributor_str = ", ".join(record.contributors)
        contrib_count = len(record.contributions)
        phases_str = ", ".join(record.phases_completed) or "none"

        parts = [
            f"Character design '{record.title}' with {contrib_count} "
            f"contributions across phases: {phases_str}.",
        ]
        parts.append(f"Contributors: {contributor_str}.")
        if record.target_character_id:
            parts.append(
                f"Assembled as character {record.target_character_id}."
            )
        return " ".join(parts)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("CD-*.json")))
        return f"CharacterDesigner(designs={count}, dir={self._dir})"
