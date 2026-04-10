"""
Jericho — World Items System

Filesystem-backed item management for the council's world. Items follow
the same lifecycle as locations (draft → active → archived) and can carry
typed properties.  Active items are injected into LLM context so council
members are aware of the artifacts and objects in their world.

Mirrors the structure and patterns of ``core.locations``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import ITEMS_DIR, ITEM_LEGALITY_STATUSES, ITEM_PROPERTY_TYPES, ITEM_STATUSES, ITEM_TIERS
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class ItemError(Exception):
    """Base exception for item-related errors."""


class ItemNotFoundError(ItemError):
    """Raised when a requested item does not exist."""

    def __init__(self, item_id: str) -> None:
        self.item_id = item_id
        super().__init__(f"Item '{item_id}' not found.")


class ItemValidationError(ItemError):
    """Raised when item data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


class ItemLifecycleError(ItemError):
    """Raised when an invalid status transition is attempted."""

    def __init__(
        self, item_id: str, current_status: str, requested_status: str,
    ) -> None:
        self.item_id = item_id
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(
            f"Cannot transition item '{item_id}' from "
            f"'{current_status}' to '{requested_status}'."
        )


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ItemProperty:
    """A named property of an item (e.g. 'Fire Enchantment')."""

    name: str
    description: str
    property_type: str = "custom"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ItemProperty:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            property_type=data.get("property_type", "custom"),
        )

    @classmethod
    def create(
        cls,
        name: str,
        description: str,
        property_type: str = "custom",
    ) -> ItemProperty:
        """Factory with validation."""
        if property_type not in ITEM_PROPERTY_TYPES:
            raise ItemValidationError(
                f"Property type '{property_type}' is not valid. "
                f"Must be one of: {', '.join(ITEM_PROPERTY_TYPES)}"
            )
        return cls(name=name, description=description, property_type=property_type)


@dataclass(frozen=True)
class Item:
    """A world item with properties, lifecycle, and metadata."""

    id: str
    name: str
    description: str
    author: str
    status: str = "draft"
    lore: str = ""
    properties: list[ItemProperty] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    rarity: str = ""
    tier: str = ""
    legality: str = ""
    owner: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "author": self.author,
            "status": self.status,
            "lore": self.lore,
            "properties": [p.to_dict() for p in self.properties],
            "tags": list(self.tags),
            "rarity": self.rarity,
            "tier": self.tier,
            "legality": self.legality,
            "owner": self.owner,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Item:
        props = [
            ItemProperty.from_dict(p)
            for p in data.get("properties", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            status=data.get("status", "draft"),
            lore=data.get("lore", ""),
            properties=props,
            tags=data.get("tags", []),
            rarity=data.get("rarity", ""),
            tier=data.get("tier", ""),
            legality=data.get("legality", ""),
            owner=data.get("owner", ""),
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
        properties: list[ItemProperty] | None = None,
        tags: list[str] | None = None,
        rarity: str = "",
        tier: str = "",
        legality: str = "",
        owner: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Item:
        """Factory that sets timestamps and defaults."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            name=name,
            description=description,
            author=author,
            status="draft",
            lore=lore,
            properties=properties or [],
            tags=tags or [],
            rarity=rarity,
            tier=tier,
            legality=legality,
            owner=owner,
            version=1,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"archived"},
    "archived": set(),  # terminal
}


# ─── Item Manager ──────────────────────────────────────────────


class ItemManager:
    """Filesystem-backed CRUD manager for world items.

    Each item is stored as ``ITEM-XXXX.json`` in the items directory.
    """

    def __init__(self, items_dir: Path | None = None) -> None:
        self._dir = items_dir or ITEMS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Properties ────────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    # ── CRUD ──────────────────────────────────────────────────

    def create(
        self,
        name: str,
        description: str,
        *,
        author: str = "",
        lore: str = "",
        properties: list[ItemProperty] | None = None,
        tags: list[str] | None = None,
        rarity: str = "",
        tier: str = "",
        legality: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Item:
        """Create and persist a new item in draft status."""
        # Validate
        name = name.strip()
        description = description.strip()
        author = author.strip()
        tier = tier.strip()

        errors: list[str] = []
        if not name:
            errors.append("Name is required.")
        if not description:
            errors.append("Description is required.")
        if not author:
            errors.append("Author is required.")
        if tier and tier not in ITEM_TIERS:
            errors.append(
                f"Invalid tier '{tier}'. Must be one of: {', '.join(ITEM_TIERS)}"
            )
        legality = legality.strip() if isinstance(legality, str) else legality
        if legality and legality not in ITEM_LEGALITY_STATUSES:
            errors.append(
                f"Invalid legality '{legality}'. Must be one of: {', '.join(ITEM_LEGALITY_STATUSES)}"
            )
        if errors:
            raise ItemValidationError(errors)

        item_id = self._next_id()
        item = Item.create(
            id=item_id,
            name=name,
            description=description,
            author=author,
            lore=lore,
            properties=properties or [],
            tags=tags or [],
            rarity=rarity,
            tier=tier,
            legality=legality,
            metadata=metadata or {},
        )
        self._save(item)
        return item

    def get(self, item_id: str) -> Item:
        """Load a single item by ID."""
        path = self._dir / f"{item_id}.json"
        if not path.exists():
            raise ItemNotFoundError(item_id)
        data = json.loads(path.read_text(encoding="utf-8"))
        return Item.from_dict(data)

    def list_items(
        self,
        *,
        status: str | None = None,
        author: str | None = None,
        tag: str | None = None,
    ) -> list[Item]:
        """List items with optional filters."""
        items: list[Item] = []
        for path in sorted(self._dir.glob("ITEM-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                item = Item.from_dict(data)
            except Exception:
                continue  # skip corrupt files

            if status and item.status != status:
                continue
            if author and item.author.lower() != author.lower():
                continue
            if tag and tag.lower() not in [t.lower() for t in item.tags]:
                continue
            items.append(item)
        return items

    # ── Status Lifecycle ──────────────────────────────────────

    def update_status(self, item_id: str, new_status: str) -> Item:
        """Transition an item to a new lifecycle status."""
        if new_status not in ITEM_STATUSES:
            raise ItemValidationError(
                f"Unknown status '{new_status}'. "
                f"Must be one of: {', '.join(ITEM_STATUSES)}"
            )

        item = self.get(item_id)
        allowed = _VALID_TRANSITIONS.get(item.status, set())
        if new_status not in allowed:
            raise ItemLifecycleError(item_id, item.status, new_status)

        # Tier is mandatory before activation
        if new_status == "active" and not item.tier:
            raise ItemValidationError(
                "A tier must be set before activating an item. "
                f"Valid tiers: {', '.join(ITEM_TIERS)}"
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = Item.from_dict({
            **item.to_dict(),
            "status": new_status,
            "updated_at": now,
        })
        self._save(updated)
        return updated

    # ── Property Management ───────────────────────────────────

    def add_property(self, item_id: str, prop: ItemProperty) -> Item:
        """Add a property to an item (name must be unique)."""
        item = self.get(item_id)
        existing_names = {p.name.lower() for p in item.properties}
        if prop.name.lower() in existing_names:
            raise ItemValidationError(
                f"Property '{prop.name}' already exists on this item."
            )

        now = datetime.now(timezone.utc).isoformat()
        new_props = list(item.properties) + [prop]
        updated = Item.from_dict({
            **item.to_dict(),
            "properties": [p.to_dict() for p in new_props],
            "updated_at": now,
        })
        self._save(updated)
        return updated

    def remove_property(self, item_id: str, property_name: str) -> Item:
        """Remove a property by name (case-insensitive)."""
        item = self.get(item_id)
        target = property_name.strip().lower()
        new_props = [p for p in item.properties if p.name.lower() != target]
        if len(new_props) == len(item.properties):
            raise ItemValidationError(
                f"Property '{property_name}' not found on this item."
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = Item.from_dict({
            **item.to_dict(),
            "properties": [p.to_dict() for p in new_props],
            "updated_at": now,
        })
        self._save(updated)
        return updated

    # ── General Update ────────────────────────────────────────

    def update(self, item_id: str, **fields: Any) -> Item:
        """Update mutable fields on an item."""
        immutable = {"id", "author", "status", "created_at", "version"}
        bad = set(fields.keys()) & immutable
        if bad:
            raise ItemValidationError(
                f"Cannot update immutable field(s): {', '.join(sorted(bad))}"
            )

        # Validate tier if provided
        if "tier" in fields:
            tier_val = fields["tier"].strip() if isinstance(fields["tier"], str) else fields["tier"]
            if tier_val and tier_val not in ITEM_TIERS:
                raise ItemValidationError(
                    f"Invalid tier '{tier_val}'. "
                    f"Must be one of: {', '.join(ITEM_TIERS)}"
                )

        # Validate legality if provided
        if "legality" in fields:
            leg_val = fields["legality"].strip() if isinstance(fields["legality"], str) else fields["legality"]
            if leg_val and leg_val not in ITEM_LEGALITY_STATUSES:
                raise ItemValidationError(
                    f"Invalid legality '{leg_val}'. "
                    f"Must be one of: {', '.join(ITEM_LEGALITY_STATUSES)}"
                )

        item = self.get(item_id)
        now = datetime.now(timezone.utc).isoformat()
        data = item.to_dict()
        data.update(fields)
        data["updated_at"] = now
        updated = Item.from_dict(data)
        self._save(updated)
        return updated

    # ── Internal Helpers ──────────────────────────────────────

    def _next_id(self) -> str:
        """Generate next sequential ITEM-XXXX id."""
        existing = sorted(self._dir.glob("ITEM-*.json"))
        if not existing:
            return "ITEM-0001"
        last = existing[-1].stem  # e.g. "ITEM-0005"
        num = int(last.split("-")[1]) + 1
        return f"ITEM-{num:04d}"

    def _save(self, item: Item) -> None:
        """Atomic write of item to disk."""
        path = self._dir / f"{item.id}.json"
        data = json.dumps(item.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(path, data + "\n")

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("ITEM-*.json")))
        return f"ItemManager(dir={self._dir!r}, items={count})"
