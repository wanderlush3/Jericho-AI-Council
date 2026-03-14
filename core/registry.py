"""
Jericho — Council Member Registry (F-003)

Load, validate, and query council member YAML profiles.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from config.settings import COUNCIL_MEMBERS_DIR


# ─── Exceptions ────────────────────────────────────────────────


class MemberNotFoundError(KeyError):
    """Raised when a council member name is not found in the registry."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Council member not found: '{name}'")


class RegistryValidationError(ValueError):
    """Raised when a council member YAML file fails validation."""

    def __init__(self, filepath: Path, errors: list[str]) -> None:
        self.filepath = filepath
        self.errors = errors
        msg = f"Validation failed for {filepath.name}: {'; '.join(errors)}"
        super().__init__(msg)


# ─── Data Model ────────────────────────────────────────────────

REQUIRED_FIELDS = {"name", "role", "description", "api_provider", "model", "system_prompt"}
VALID_API_PROVIDERS = {"openrouter", "mancer"}


@dataclass(frozen=True)
class CouncilMember:
    """Immutable representation of a council member parsed from YAML."""

    name: str
    role: str
    description: str
    personality: dict = field(default_factory=dict)
    api_provider: str = ""
    model: str = ""
    vote_weight: float = 1.0
    specialties: list[str] = field(default_factory=list)
    system_prompt: str = ""
    source_file: Path | None = None

    @property
    def is_openrouter(self) -> bool:
        return self.api_provider == "openrouter"

    @property
    def is_mancer(self) -> bool:
        return self.api_provider == "mancer"


# ─── Registry ──────────────────────────────────────────────────


class CouncilRegistry:
    """
    Loads and manages council member profiles from YAML files.

    Usage:
        registry = CouncilRegistry()
        registry.load()
        sage = registry.get("Sage")
    """

    def __init__(self, members_dir: Path | None = None) -> None:
        self._members_dir = members_dir or COUNCIL_MEMBERS_DIR
        self._members: dict[str, CouncilMember] = {}

    # ── Loading ────────────────────────────────────────────────

    def load(self) -> CouncilRegistry:
        """
        Load all .yaml files from the members directory.

        Returns self for chaining: ``registry = CouncilRegistry().load()``

        Raises:
            RegistryValidationError: if any YAML file fails validation.
            FileNotFoundError: if the members directory does not exist.
        """
        if not self._members_dir.exists():
            raise FileNotFoundError(
                f"Council members directory not found: {self._members_dir}"
            )

        self._members.clear()

        for filepath in sorted(self._members_dir.glob("*.yaml")):
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                raise RegistryValidationError(filepath, ["File is empty or not valid YAML"])

            errors = self.validate(data, filepath)
            if errors:
                raise RegistryValidationError(filepath, errors)

            member = self._build_member(data, filepath)
            key = member.name.lower()

            if key in self._members:
                raise RegistryValidationError(
                    filepath,
                    [f"Duplicate member name '{member.name}' (conflicts with {self._members[key].source_file})"],
                )

            self._members[key] = member

        return self

    # ── Querying ───────────────────────────────────────────────

    def get(self, name: str) -> CouncilMember:
        """
        Case-insensitive lookup of a council member by name.

        Raises:
            MemberNotFoundError: if the name is not in the registry.
        """
        key = name.strip().lower()
        try:
            return self._members[key]
        except KeyError:
            raise MemberNotFoundError(name) from None

    def list_members(self) -> list[CouncilMember]:
        """Return all members sorted alphabetically by name."""
        return sorted(self._members.values(), key=lambda m: m.name.lower())

    def list_names(self) -> list[str]:
        """Return sorted list of member names."""
        return [m.name for m in self.list_members()]

    def members_by_provider(self, provider: str) -> list[CouncilMember]:
        """Return members filtered by API provider."""
        return [m for m in self.list_members() if m.api_provider == provider]

    # ── Validation ─────────────────────────────────────────────

    @staticmethod
    def validate(data: dict, filepath: Path | None = None) -> list[str]:
        """
        Validate a raw YAML dict against the member schema.

        Returns a list of error strings. Empty list means valid.
        """
        errors: list[str] = []

        if not isinstance(data, dict):
            return ["Expected a YAML mapping, got " + type(data).__name__]

        # Required fields
        for field_name in REQUIRED_FIELDS:
            if field_name not in data:
                errors.append(f"Missing required field: '{field_name}'")

        # api_provider value
        provider = data.get("api_provider")
        if provider is not None and provider not in VALID_API_PROVIDERS:
            errors.append(
                f"Invalid api_provider '{provider}' — must be one of {sorted(VALID_API_PROVIDERS)}"
            )

        # vote_weight must be positive
        weight = data.get("vote_weight")
        if weight is not None:
            if not isinstance(weight, (int, float)):
                errors.append(f"vote_weight must be a number, got {type(weight).__name__}")
            elif weight <= 0:
                errors.append(f"vote_weight must be positive, got {weight}")

        # personality structure
        personality = data.get("personality")
        if personality is not None and not isinstance(personality, dict):
            errors.append(f"personality must be a mapping, got {type(personality).__name__}")

        # specialties must be a list
        specialties = data.get("specialties")
        if specialties is not None and not isinstance(specialties, list):
            errors.append(f"specialties must be a list, got {type(specialties).__name__}")

        return errors

    # ── Internal ───────────────────────────────────────────────

    @staticmethod
    def _build_member(data: dict, filepath: Path) -> CouncilMember:
        """Construct a CouncilMember from validated YAML data."""
        return CouncilMember(
            name=data["name"],
            role=data["role"],
            description=data["description"],
            personality=data.get("personality", {}),
            api_provider=data["api_provider"],
            model=data["model"],
            vote_weight=float(data.get("vote_weight", 1.0)),
            specialties=list(data.get("specialties", [])),
            system_prompt=data["system_prompt"],
            source_file=filepath,
        )

    # ── Dunder methods ─────────────────────────────────────────

    def __len__(self) -> int:
        return len(self._members)

    def __contains__(self, name: str) -> bool:
        return name.strip().lower() in self._members

    def __iter__(self) -> Iterator[CouncilMember]:
        return iter(self.list_members())

    def __repr__(self) -> str:
        return f"CouncilRegistry(members={len(self._members)}, dir={self._members_dir})"
