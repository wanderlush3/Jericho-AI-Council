"""
Jericho — Location System (F-026)

Structured JSON format for world-location definitions with features,
lore, hierarchical parent/child relationships, and lifecycle tracking.

Lifecycle:  draft → active → archived

Storage: one JSON file per location in ``data/locations/``, named ``LOC-XXXX.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    LOCATION_INJECTION_MAX_LENGTH,
    LOCATIONS_DIR,
    LOCATION_STATUSES,
    LOCATION_FEATURE_TYPES,
)
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class LocationError(Exception):
    """Base exception for location-system errors."""


class LocationNotFoundError(LocationError):
    """Raised when a location ID is not found on disk."""

    def __init__(self, location_id: str) -> None:
        self.location_id = location_id
        super().__init__(f"Location not found: '{location_id}'")


class LocationValidationError(LocationError):
    """Raised when location data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


class LocationLifecycleError(LocationError):
    """Raised when a status transition is not allowed."""

    def __init__(self, location_id: str, current: str, requested: str) -> None:
        self.location_id = location_id
        self.current_status = current
        self.requested_status = requested
        super().__init__(
            f"Cannot transition '{location_id}' from '{current}' to '{requested}'"
        )


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"archived", "draft"},
    "archived": set(),  # terminal
}


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class LocationFeature:
    """A notable feature of a location (e.g. a landmark, building, etc.)."""

    name: str
    description: str
    feature_type: str = "custom"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LocationFeature:
        return cls(
            name=data["name"],
            description=data["description"],
            feature_type=data.get("feature_type", "custom"),
        )

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        feature_type: str = "custom",
    ) -> LocationFeature:
        """Factory with feature_type validation."""
        if feature_type not in LOCATION_FEATURE_TYPES:
            raise LocationValidationError(
                [f"Feature type must be one of {LOCATION_FEATURE_TYPES}, got '{feature_type}'"]
            )
        return cls(
            name=name,
            description=description,
            feature_type=feature_type,
        )


@dataclass(frozen=True)
class Location:
    """Immutable snapshot of a world location."""

    id: str
    name: str
    description: str
    author: str
    status: str = "draft"
    lore: str = ""
    features: list[LocationFeature] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    parent_location_id: str = ""
    coordinates: str = ""
    llm_injection: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Location:
        features = [LocationFeature.from_dict(f) for f in data.get("features", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            author=data["author"],
            status=data.get("status", "draft"),
            lore=data.get("lore", ""),
            features=features,
            tags=data.get("tags", []),
            parent_location_id=data.get("parent_location_id", ""),
            coordinates=data.get("coordinates", ""),
            llm_injection=data.get("llm_injection", ""),
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
        lore: str = "",
        features: list[LocationFeature] | None = None,
        tags: list[str] | None = None,
        parent_location_id: str = "",
        coordinates: str = "",
        llm_injection: str = "",
        version: int = 1,
        metadata: dict[str, Any] | None = None,
    ) -> Location:
        """Factory that auto-fills timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            name=name,
            description=description,
            author=author,
            status="draft",
            lore=lore,
            features=features or [],
            tags=tags or [],
            parent_location_id=parent_location_id,
            coordinates=coordinates,
            llm_injection=llm_injection,
            version=version,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Location Manager ────────────────────────────────────────


class LocationManager:
    """
    Filesystem-backed location store.

    Each location is stored as ``LOC-XXXX.json`` in the locations directory.

    Usage::

        mgr = LocationManager()
        feature = LocationFeature.create("Great Hall", "A massive stone hall", "building")
        loc = mgr.create("Ironhaven", "A fortified port city", author="Council", features=[feature])
        mgr.update_status(loc.id, "active")
    """

    _ID_PATTERN = re.compile(r"^LOC-(\d{4})\.json$")

    def __init__(self, locations_dir: Path | None = None) -> None:
        self._dir = locations_dir or LOCATIONS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

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
        lore: str = "",
        features: list[LocationFeature] | None = None,
        tags: list[str] | None = None,
        parent_location_id: str = "",
        coordinates: str = "",
        llm_injection: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Location:
        """
        Create a new location in *draft* status.

        Auto-generates a sequential ``LOC-XXXX`` ID.

        Raises:
            LocationValidationError: if required fields are empty.
        """
        errors: list[str] = []
        if not name.strip():
            errors.append("Name must not be empty")
        if not description.strip():
            errors.append("Description must not be empty")
        if not author.strip():
            errors.append("Author must not be empty")
        if llm_injection and len(llm_injection) > LOCATION_INJECTION_MAX_LENGTH:
            errors.append(
                f"LLM injection text exceeds maximum length of "
                f"{LOCATION_INJECTION_MAX_LENGTH} characters "
                f"(got {len(llm_injection)})"
            )
        if errors:
            raise LocationValidationError(errors)

        # Validate parent exists if specified
        if parent_location_id:
            parent_path = self._filepath(parent_location_id)
            if not parent_path.exists():
                raise LocationValidationError(
                    [f"Parent location not found: '{parent_location_id}'"]
                )

        next_id = self._next_id()
        location = Location.create(
            id=next_id,
            name=name.strip(),
            description=description.strip(),
            author=author.strip(),
            lore=lore,
            features=features or [],
            tags=tags,
            parent_location_id=parent_location_id,
            coordinates=coordinates,
            llm_injection=llm_injection,
            metadata=metadata,
        )
        self._save(location)
        return location

    # ── Read ──────────────────────────────────────────────────

    def get(self, location_id: str) -> Location:
        """
        Load a location by ID.

        Raises:
            LocationNotFoundError: if no file exists for that ID.
        """
        filepath = self._filepath(location_id)
        if not filepath.exists():
            raise LocationNotFoundError(location_id)
        return self._load(filepath)

    def list_locations(
        self,
        *,
        status: str | None = None,
        author: str | None = None,
        tag: str | None = None,
        parent_location_id: str | None = None,
    ) -> list[Location]:
        """
        Return locations sorted by ID, with optional filters.
        """
        locations: list[Location] = []
        for filepath in sorted(self._dir.glob("LOC-*.json")):
            try:
                loc = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if status is not None and loc.status != status:
                continue
            if author is not None and loc.author.lower() != author.strip().lower():
                continue
            if tag is not None and tag.lower() not in [t.lower() for t in loc.tags]:
                continue
            if parent_location_id is not None and loc.parent_location_id != parent_location_id:
                continue
            locations.append(loc)
        return locations

    # ── Status Lifecycle ──────────────────────────────────────

    def update_status(self, location_id: str, new_status: str) -> Location:
        """
        Transition a location to *new_status*.

        Raises:
            LocationNotFoundError: if location does not exist.
            LocationLifecycleError: if the transition is invalid.
            LocationValidationError: if *new_status* is not a known status.
        """
        if new_status not in LOCATION_STATUSES:
            raise LocationValidationError(
                [f"Unknown status '{new_status}' — must be one of {LOCATION_STATUSES}"]
            )

        location = self.get(location_id)
        allowed = _VALID_TRANSITIONS.get(location.status, set())

        if new_status not in allowed:
            raise LocationLifecycleError(location_id, location.status, new_status)

        now = datetime.now(timezone.utc).isoformat()
        updated = Location(
            id=location.id,
            name=location.name,
            description=location.description,
            author=location.author,
            status=new_status,
            lore=location.lore,
            features=list(location.features),
            tags=list(location.tags),
            parent_location_id=location.parent_location_id,
            coordinates=location.coordinates,
            llm_injection=location.llm_injection,
            version=location.version,
            created_at=location.created_at,
            updated_at=now,
            metadata=dict(location.metadata),
        )
        self._save(updated)
        return updated

    # ── Feature Management ────────────────────────────────────

    def add_feature(self, location_id: str, feature: LocationFeature) -> Location:
        """
        Append a feature to a location.

        Raises:
            LocationNotFoundError: if location does not exist.
            LocationValidationError: if a feature with the same name already exists.
        """
        location = self.get(location_id)

        existing_names = {f.name.lower() for f in location.features}
        if feature.name.lower() in existing_names:
            raise LocationValidationError(
                [f"Feature '{feature.name}' already exists on location '{location_id}'"]
            )

        now = datetime.now(timezone.utc).isoformat()
        new_features = list(location.features) + [feature]
        updated = Location(
            id=location.id,
            name=location.name,
            description=location.description,
            author=location.author,
            status=location.status,
            lore=location.lore,
            features=new_features,
            tags=list(location.tags),
            parent_location_id=location.parent_location_id,
            coordinates=location.coordinates,
            llm_injection=location.llm_injection,
            version=location.version,
            created_at=location.created_at,
            updated_at=now,
            metadata=dict(location.metadata),
        )
        self._save(updated)
        return updated

    def remove_feature(self, location_id: str, feature_name: str) -> Location:
        """
        Remove a feature by name (case-insensitive).

        Raises:
            LocationNotFoundError: if location does not exist.
            LocationValidationError: if feature not found.
        """
        location = self.get(location_id)

        new_features = [f for f in location.features if f.name.lower() != feature_name.strip().lower()]
        if len(new_features) == len(location.features):
            raise LocationValidationError(
                [f"Feature '{feature_name}' not found on location '{location_id}'"]
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = Location(
            id=location.id,
            name=location.name,
            description=location.description,
            author=location.author,
            status=location.status,
            lore=location.lore,
            features=new_features,
            tags=list(location.tags),
            parent_location_id=location.parent_location_id,
            coordinates=location.coordinates,
            llm_injection=location.llm_injection,
            version=location.version,
            created_at=location.created_at,
            updated_at=now,
            metadata=dict(location.metadata),
        )
        self._save(updated)
        return updated

    # ── Update Fields ─────────────────────────────────────────

    _MUTABLE_FIELDS = {
        "name", "description", "lore", "tags", "metadata",
        "parent_location_id", "coordinates", "llm_injection",
    }

    def update(self, location_id: str, **fields: Any) -> Location:
        """
        Update mutable fields on a location.

        Only ``name``, ``description``, ``lore``, ``tags``, ``metadata``,
        ``parent_location_id``, and ``coordinates`` may be changed.
        Bumps ``updated_at``.

        Raises:
            LocationNotFoundError: if location does not exist.
            LocationValidationError: if an immutable field is specified.
        """
        invalid = set(fields) - self._MUTABLE_FIELDS
        if invalid:
            raise LocationValidationError(
                [f"Cannot update immutable field(s): {', '.join(sorted(invalid))}"]
            )

        # Validate llm_injection length if provided
        if "llm_injection" in fields:
            inj = fields["llm_injection"]
            if isinstance(inj, str) and len(inj) > LOCATION_INJECTION_MAX_LENGTH:
                raise LocationValidationError(
                    [f"LLM injection text exceeds maximum length of "
                     f"{LOCATION_INJECTION_MAX_LENGTH} characters "
                     f"(got {len(inj)})"]
                )

        location = self.get(location_id)

        now = datetime.now(timezone.utc).isoformat()
        updated = Location(
            id=location.id,
            name=fields.get("name", location.name),
            description=fields.get("description", location.description),
            author=location.author,
            status=location.status,
            lore=fields.get("lore", location.lore),
            features=list(location.features),
            tags=fields.get("tags", list(location.tags)),
            parent_location_id=fields.get("parent_location_id", location.parent_location_id),
            coordinates=fields.get("coordinates", location.coordinates),
            llm_injection=fields.get("llm_injection", location.llm_injection),
            version=location.version,
            created_at=location.created_at,
            updated_at=now,
            metadata=fields.get("metadata", dict(location.metadata)),
        )
        self._save(updated)
        return updated

    # ── Children ──────────────────────────────────────────────

    def get_children(self, location_id: str) -> list[Location]:
        """
        Find all locations whose ``parent_location_id`` matches *location_id*.
        """
        return self.list_locations(parent_location_id=location_id)

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, location_id: str) -> Path:
        return self._dir / f"{location_id}.json"

    def _save(self, location: Location) -> None:
        payload = json.dumps(location.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(location.id), payload + "\n")

    def _load(self, filepath: Path) -> Location:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return Location.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential LOC-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("LOC-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"LOC-{max_num + 1:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("LOC-*.json")))
        return f"LocationManager(locations={count}, dir={self._dir})"
