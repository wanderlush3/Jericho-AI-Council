"""
Jericho — Character Template System (F-011)

Structured YAML format for AI character definitions with traits, backstory,
system prompt, and lifecycle tracking.

Lifecycle:  draft → active → archived
            draft → active → superseded  (when a new version replaces this one)

Storage: one JSON file per character in ``data/characters/``, named ``CH-XXXX.json``.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from config.settings import (
    CHARACTERS_DIR,
    CHARACTER_STATUSES,
)
from core.utils import atomic_write, make_id_lock


# ─── Exceptions ────────────────────────────────────────────────


class CharacterError(Exception):
    """Base exception for character-system errors."""


class CharacterNotFoundError(CharacterError):
    """Raised when a character ID is not found on disk."""

    def __init__(self, character_id: str) -> None:
        self.character_id = character_id
        super().__init__(f"Character not found: '{character_id}'")


class CharacterValidationError(CharacterError):
    """Raised when character data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class CharacterLifecycleError(CharacterError):
    """Raised when a status transition is not allowed."""

    def __init__(self, character_id: str, current: str, requested: str) -> None:
        self.character_id = character_id
        self.current_status = current
        self.requested_status = requested
        super().__init__(
            f"Cannot transition '{character_id}' from '{current}' to '{requested}'"
        )


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"archived", "superseded", "draft"},
    "archived": {"active", "draft"},
    "superseded": set(),     # terminal (versioning)
}


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class Trait:
    """A single character trait with type, name, description, and intensity."""

    trait_type: str     # personality / values / flaws / custom
    name: str
    description: str
    intensity: float = 0.5  # 0.0–1.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trait:
        return cls(
            trait_type=data["trait_type"],
            name=data["name"],
            description=data["description"],
            intensity=data.get("intensity", 0.5),
        )

    @classmethod
    def create(
        cls,
        trait_type: str,
        name: str,
        description: str,
        intensity: float = 0.5,
    ) -> Trait:
        """Factory with intensity validation."""
        if not (0.0 <= intensity <= 1.0):
            raise CharacterValidationError(
                [f"Trait intensity must be 0.0–1.0, got {intensity}"]
            )
        return cls(
            trait_type=trait_type,
            name=name,
            description=description,
            intensity=intensity,
        )


@dataclass(frozen=True)
class CharacterTemplate:
    """Immutable snapshot of a character template loaded from (or about to be saved to) disk."""

    id: str
    name: str
    description: str
    author: str
    status: str = "draft"
    backstory: str = ""
    physical_description: str = ""
    traits: list[Trait] = field(default_factory=list)
    system_prompt: str = ""
    greeting: str = ""
    example_messages: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    api_provider: str = "openrouter"
    model: str = "Default"
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterTemplate:
        traits = [Trait.from_dict(t) for t in data.get("traits", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            author=data["author"],
            status=data.get("status", "draft"),
            backstory=data.get("backstory", ""),
            physical_description=data.get("physical_description", ""),
            traits=traits,
            system_prompt=data.get("system_prompt", ""),
            greeting=data.get("greeting", ""),
            example_messages=data.get("example_messages", []),
            tags=data.get("tags", []),
            api_provider=data.get("api_provider", "openrouter"),
            model=data.get("model", "Default"),
            version=data.get("version", 1),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        id: str,
        name: str,
        description: str,
        author: str,
        backstory: str = "",
        physical_description: str = "",
        traits: list[Trait] | None = None,
        system_prompt: str = "",
        greeting: str = "",
        example_messages: list[str] | None = None,
        tags: list[str] | None = None,
        api_provider: str = "openrouter",
        model: str = "Default",
        version: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> CharacterTemplate:
        """Factory that auto-fills timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            name=name,
            description=description,
            author=author,
            status="draft",
            backstory=backstory,
            physical_description=physical_description,
            traits=traits or [],
            system_prompt=system_prompt,
            greeting=greeting,
            example_messages=example_messages or [],
            tags=tags or [],
            api_provider=api_provider,
            model=model,
            version=version,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Helpers ───────────────────────────────────────────────────




# ─── Character Manager ────────────────────────────────────────


class CharacterManager:
    """
    Filesystem-backed character template store.

    Each character is stored as ``CH-XXXX.json`` in the characters directory.

    Usage::

        mgr = CharacterManager()
        trait = Trait.create("personality", "Curious", "Always asking questions")
        char = mgr.create("Atlas", "An explorer AI", author="Forge", traits=[trait])
        mgr.update_status(char.id, "active")
        exported = mgr.export_yaml(char.id)
    """

    _ID_PATTERN = re.compile(r"^CH-(\d{4})\.json$")

    def __init__(self, characters_dir: Path | None = None) -> None:
        self._dir = characters_dir or CHARACTERS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._id_lock = make_id_lock()

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    # ── Create ────────────────────────────────────────────────

    def create(
        self,
        name: str,
        description: str,
        *,
        author: str,
        backstory: str = "",
        physical_description: str = "",
        traits: list[Trait] | None = None,
        system_prompt: str = "",
        greeting: str = "",
        example_messages: list[str] | None = None,
        tags: list[str] | None = None,
        api_provider: str = "openrouter",
        model: str = "Default",
        metadata: dict[str, Any] | None = None,
    ) -> CharacterTemplate:
        """
        Create a new character template in *draft* status.

        Auto-generates a sequential ``CH-XXXX`` ID.

        Raises:
            CharacterValidationError: if required fields are empty or no traits provided.
        """
        errors: list[str] = []
        if not name.strip():
            errors.append("Name must not be empty")
        if not description.strip():
            errors.append("Description must not be empty")
        if not author.strip():
            errors.append("Author must not be empty")
        effective_traits = traits or []
        if not effective_traits:
            errors.append("At least one trait is required")
        if errors:
            raise CharacterValidationError(errors)

        with self._id_lock:
            next_id = self._next_id()
            character = CharacterTemplate.create(
                id=next_id,
                name=name.strip(),
                description=description.strip(),
                author=author.strip(),
                backstory=backstory,
                physical_description=physical_description,
                traits=effective_traits,
                system_prompt=system_prompt,
                greeting=greeting,
                example_messages=example_messages,
                tags=tags,
                api_provider=api_provider,
                model=model,
                metadata=metadata,
            )
            self._save(character)

        # Auto-create a memory directory for the new character (F-074)
        from core.chat_helpers import character_memory_name
        from core.memory import AgentMemory
        AgentMemory(character_memory_name(character.name))

        return character

    # ── Read ──────────────────────────────────────────────────

    def get(self, character_id: str) -> CharacterTemplate:
        """
        Load a character by ID.

        Raises:
            CharacterNotFoundError: if no file exists for that ID.
        """
        filepath = self._filepath(character_id)
        if not filepath.exists():
            raise CharacterNotFoundError(character_id)
        return self._load(filepath)

    def list_characters(
        self,
        *,
        status: str | None = None,
        author: str | None = None,
        tag: str | None = None,
    ) -> list[CharacterTemplate]:
        """
        Return characters sorted by ID, with optional filters.
        """
        characters: list[CharacterTemplate] = []
        for filepath in sorted(self._dir.glob("CH-*.json")):
            try:
                c = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if status is not None and c.status != status:
                continue
            if author is not None and c.author.lower() != author.strip().lower():
                continue
            if tag is not None and tag.lower() not in [t.lower() for t in c.tags]:
                continue
            characters.append(c)
        return characters

    # ── Update ────────────────────────────────────────────────

    def update(self, character_id: str, **fields: Any) -> CharacterTemplate:
        """
        Update mutable fields on a character template.

        Accepted keyword args: ``name``, ``description``, ``backstory``,
        ``system_prompt``, ``greeting``, ``example_messages``, ``tags``,
        ``metadata``.

        Raises:
            CharacterNotFoundError: if character does not exist.
            CharacterValidationError: if name or description would become empty.
        """
        character = self.get(character_id)

        MUTABLE = {
            "name", "description", "backstory", "physical_description",
            "system_prompt",
            "greeting", "example_messages", "tags", "metadata",
            "api_provider", "model",
        }
        unknown = set(fields) - MUTABLE
        if unknown:
            raise CharacterValidationError(
                [f"Cannot update immutable/unknown fields: {unknown}"]
            )

        new_name = fields.get("name", character.name)
        new_desc = fields.get("description", character.description)
        if isinstance(new_name, str) and not new_name.strip():
            raise CharacterValidationError(["Name must not be empty"])
        if isinstance(new_desc, str) and not new_desc.strip():
            raise CharacterValidationError(["Description must not be empty"])

        now = datetime.now(timezone.utc).isoformat()
        overrides: dict[str, Any] = {"updated_at": now}
        for key in ("name", "description", "backstory", "physical_description",
                    "system_prompt",
                    "greeting", "example_messages", "tags", "metadata",
                    "api_provider", "model"):
            if key in fields:
                overrides[key] = fields[key]
        updated = dataclasses.replace(character, **overrides)
        self._save(updated)
        return updated

    # ── Status Lifecycle ──────────────────────────────────────

    def update_status(self, character_id: str, new_status: str) -> CharacterTemplate:
        """
        Transition a character to *new_status*.

        Raises:
            CharacterNotFoundError: if character does not exist.
            CharacterLifecycleError: if the transition is invalid.
            CharacterValidationError: if *new_status* is not a known status.
        """
        if new_status not in CHARACTER_STATUSES:
            raise CharacterValidationError(
                [f"Unknown status '{new_status}' — must be one of {CHARACTER_STATUSES}"]
            )

        character = self.get(character_id)
        allowed = _VALID_TRANSITIONS.get(character.status, set())

        if new_status not in allowed:
            raise CharacterLifecycleError(character_id, character.status, new_status)

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(
            character, status=new_status, updated_at=now,
        )
        self._save(updated)
        return updated

    # ── Trait Management ──────────────────────────────────────

    def add_trait(self, character_id: str, trait: Trait) -> CharacterTemplate:
        """
        Append a trait to a character.

        Raises:
            CharacterNotFoundError: if character does not exist.
            CharacterValidationError: if a trait with the same name already exists.
        """
        character = self.get(character_id)

        existing_names = {t.name.lower() for t in character.traits}
        if trait.name.lower() in existing_names:
            raise CharacterValidationError(
                [f"Trait '{trait.name}' already exists on character '{character_id}'"]
            )

        now = datetime.now(timezone.utc).isoformat()
        new_traits = list(character.traits) + [trait]
        updated = dataclasses.replace(
            character, traits=new_traits, updated_at=now,
        )
        self._save(updated)
        return updated

    def remove_trait(self, character_id: str, trait_name: str) -> CharacterTemplate:
        """
        Remove a trait by name (case-insensitive).

        Raises:
            CharacterNotFoundError: if character does not exist.
            CharacterValidationError: if trait not found or removal would leave zero traits.
        """
        character = self.get(character_id)

        new_traits = [t for t in character.traits if t.name.lower() != trait_name.strip().lower()]
        if len(new_traits) == len(character.traits):
            raise CharacterValidationError(
                [f"Trait '{trait_name}' not found on character '{character_id}'"]
            )
        if not new_traits:
            raise CharacterValidationError(
                [f"Cannot remove last trait — at least one trait is required"]
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(
            character, traits=new_traits, updated_at=now,
        )
        self._save(updated)
        return updated

    # ── Update Fields ─────────────────────────────────────────

    _MUTABLE_FIELDS = {
        "name", "description", "backstory", "system_prompt",
        "greeting", "example_messages", "tags", "metadata",
        "api_provider", "model",
    }

    def update(self, character_id: str, **fields: Any) -> CharacterTemplate:
        """
        Update mutable fields on a character.

        Only ``name``, ``description``, ``backstory``, ``system_prompt``,
        ``greeting``, ``example_messages``, ``tags``, and ``metadata``
        may be changed.  Bumps ``updated_at``.

        Raises:
            CharacterNotFoundError: if character does not exist.
            CharacterValidationError: if an immutable field is specified.
        """
        invalid = set(fields) - self._MUTABLE_FIELDS
        if invalid:
            raise CharacterValidationError(
                [f"Cannot update immutable field(s): {', '.join(sorted(invalid))}"]
            )

        character = self.get(character_id)

        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(character, updated_at=now, **fields)
        self._save(updated)
        return updated

    # ── Export YAML ────────────────────────────────────────────

    def export_yaml(
        self,
        character_id: str,
        output_path: Path | None = None,
    ) -> str:
        """
        Export a character template to YAML format.

        If *output_path* is given, writes the YAML to that file.
        Always returns the YAML string.

        Raises:
            CharacterNotFoundError: if character does not exist.
        """
        character = self.get(character_id)

        # Build a clean dict for YAML output
        yaml_data: dict[str, Any] = {
            "id": character.id,
            "name": character.name,
            "description": character.description,
            "author": character.author,
            "version": character.version,
            "status": character.status,
        }

        if character.backstory:
            yaml_data["backstory"] = character.backstory

        if character.traits:
            yaml_data["traits"] = [t.to_dict() for t in character.traits]

        if character.system_prompt:
            yaml_data["system_prompt"] = character.system_prompt

        if character.greeting:
            yaml_data["greeting"] = character.greeting

        if character.example_messages:
            yaml_data["example_messages"] = list(character.example_messages)

        if character.tags:
            yaml_data["tags"] = list(character.tags)

        if character.metadata:
            yaml_data["metadata"] = dict(character.metadata)

        yaml_data["created_at"] = character.created_at
        yaml_data["updated_at"] = character.updated_at

        yaml_str = yaml.dump(
            yaml_data,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

        if output_path is not None:
            atomic_write(output_path, yaml_str)

        return yaml_str

    # ── Versioning ────────────────────────────────────────────

    def create_version(self, character_id: str) -> CharacterTemplate:
        """
        Create a new version of a character template.

        - The original is transitioned to ``superseded``.
        - A new character is created with incremented version and a link
          to the original via ``metadata["previous_version"]``.

        Raises:
            CharacterNotFoundError: if character does not exist.
            CharacterLifecycleError: if original is not in ``active`` status.
        """
        original = self.get(character_id)

        if original.status != "active":
            raise CharacterLifecycleError(
                character_id, original.status, "superseded (via create_version)"
            )

        # Supersede the original
        self.update_status(character_id, "superseded")

        # Create new version
        with self._id_lock:
            next_id = self._next_id()
            now = datetime.now(timezone.utc).isoformat()
            new_meta = dict(original.metadata)
            new_meta["previous_version"] = original.id

            new_char = dataclasses.replace(
                original,
                id=next_id,
                status="draft",
                version=original.version + 1,
                created_at=now,
                updated_at=now,
                metadata=new_meta,
            )
            self._save(new_char)
        return new_char

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, character_id: str) -> Path:
        return self._dir / f"{character_id}.json"

    def _save(self, character: CharacterTemplate) -> None:
        payload = json.dumps(character.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(character.id), payload + "\n")

    def _load(self, filepath: Path) -> CharacterTemplate:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return CharacterTemplate.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential CH-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("CH-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"CH-{max_num + 1:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("CH-*.json")))
        return f"CharacterManager(characters={count}, dir={self._dir})"
