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

from config.settings import (
    CONSUMABLE_INJECTION_TTL_HOURS,
    ITEM_INJECTION_MAX_LENGTH,
    ITEMS_DIR,
    ITEM_LEGALITY_STATUSES,
    ITEM_PROPERTY_TYPES,
    ITEM_STATUSES,
    ITEM_TIERS,
)
from core.utils import atomic_write, make_id_lock

# Valid owner types for owned_by entries
OWNER_TYPES = ("user", "character", "council_member")


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
    owned_by: list[dict[str, str]] = field(default_factory=list)
    llm_injection: str = ""
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
            "owned_by": [dict(o) for o in self.owned_by],
            "llm_injection": self.llm_injection,
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
        # Backward compat: migrate legacy "owner" string → owned_by list
        owned_by = data.get("owned_by", [])
        if not owned_by and data.get("owner"):
            owned_by = [{"name": data["owner"], "type": "user"}]
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
            owned_by=owned_by,
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
        properties: list[ItemProperty] | None = None,
        tags: list[str] | None = None,
        rarity: str = "",
        tier: str = "",
        legality: str = "",
        owned_by: list[dict[str, str]] | None = None,
        llm_injection: str = "",
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
            owned_by=owned_by or [],
            llm_injection=llm_injection,
            version=1,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── LLM Injection Expiry Helper ──────────────────────────────


def is_injection_active(item: Item) -> bool:
    """Check whether an item's LLM injection is currently active.

    - Non-consumable items: injection is **static** (always active)
    - Consumable items: injection expires after
      ``CONSUMABLE_INJECTION_TTL_HOURS`` hours from ``updated_at``
    - Items with empty ``llm_injection``: always returns ``False``
    """
    if not item.llm_injection:
        return False

    if item.tier != "consumable":
        return True  # permanent / degradable — static injection

    # Consumable: check expiry against updated_at
    if not item.updated_at:
        return False

    try:
        updated = datetime.fromisoformat(item.updated_at)
        now = datetime.now(timezone.utc)
        elapsed_hours = (now - updated).total_seconds() / 3600
        return elapsed_hours <= CONSUMABLE_INJECTION_TTL_HOURS
    except (ValueError, TypeError):
        return False


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"archived"},
    "archived": set(),  # terminal
}


# ─── Owned-By Validation ──────────────────────────────────────


def validate_owned_by(entries: list[Any]) -> list[str]:
    """Validate a list of owned_by entries, returning error messages."""
    errors: list[str] = []
    if not isinstance(entries, list):
        errors.append("owned_by must be a list.")
        return errors
    seen: set[tuple[str, str]] = set()
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"owned_by[{i}] must be a dict.")
            continue
        name = entry.get("name", "").strip() if isinstance(entry.get("name"), str) else ""
        otype = entry.get("type", "").strip() if isinstance(entry.get("type"), str) else ""
        if not name:
            errors.append(f"owned_by[{i}].name must not be empty.")
        if otype not in OWNER_TYPES:
            errors.append(
                f"owned_by[{i}].type '{otype}' is invalid. "
                f"Must be one of: {', '.join(OWNER_TYPES)}"
            )
        key = (name.lower(), otype)
        if key in seen:
            errors.append(
                f"Duplicate owned_by entry: name='{name}', type='{otype}'."
            )
        seen.add(key)
    return errors


# ─── Item Manager ──────────────────────────────────────────────


class ItemManager:
    """Filesystem-backed CRUD manager for world items.

    Each item is stored as ``ITEM-XXXX.json`` in the items directory.
    """

    def __init__(self, items_dir: Path | None = None) -> None:
        self._dir = items_dir or ITEMS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._id_lock = make_id_lock()

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
        owned_by: list[dict[str, str]] | None = None,
        llm_injection: str = "",
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
        if llm_injection and len(llm_injection) > ITEM_INJECTION_MAX_LENGTH:
            errors.append(
                f"LLM injection text exceeds maximum length of "
                f"{ITEM_INJECTION_MAX_LENGTH} characters "
                f"(got {len(llm_injection)})."
            )
        if owned_by:
            errors.extend(validate_owned_by(owned_by))
        if errors:
            raise ItemValidationError(errors)

        with self._id_lock:
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
                owned_by=owned_by or [],
                llm_injection=llm_injection,
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
        # llm_injection is explicitly mutable
        bad = set(fields.keys()) & immutable
        if bad:
            raise ItemValidationError(
                f"Cannot update immutable field(s): {', '.join(sorted(bad))}"
            )

        # Validate llm_injection length if provided
        if "llm_injection" in fields:
            inj = fields["llm_injection"]
            if isinstance(inj, str) and len(inj) > ITEM_INJECTION_MAX_LENGTH:
                raise ItemValidationError(
                    f"LLM injection text exceeds maximum length of "
                    f"{ITEM_INJECTION_MAX_LENGTH} characters "
                    f"(got {len(inj)})."
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

        # Validate owned_by if provided
        if "owned_by" in fields:
            ob_errors = validate_owned_by(fields["owned_by"])
            if ob_errors:
                raise ItemValidationError(ob_errors)

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

    # ── Gift Giving (F-068) ──────────────────────────────────

    def gift_item(
        self,
        item_id: str,
        *,
        from_owner: dict[str, str],
        to_owner: dict[str, str],
        message: str = "",
    ) -> "GiftRecord":
        """Transfer ownership of an item from one owner to another.

        Validates:
        - Item exists and is active
        - ``from_owner`` is currently in ``owned_by``
        - ``to_owner`` is a valid owner entry and not already an owner
        - ``from_owner`` and ``to_owner`` are not the same

        Returns a :class:`GiftRecord` capturing the transfer.
        """
        item = self.get(item_id)

        # Must be active
        if item.status != "active":
            raise ItemValidationError(
                f"Item '{item_id}' must be active to gift "
                f"(current status: {item.status})."
            )

        # Validate to_owner structure
        ob_errors = validate_owned_by([to_owner])
        if ob_errors:
            raise ItemValidationError(ob_errors)

        # Normalize for comparison (case-insensitive name, exact type)
        from_key = (
            from_owner.get("name", "").strip().lower(),
            from_owner.get("type", "").strip(),
        )
        to_key = (
            to_owner.get("name", "").strip().lower(),
            to_owner.get("type", "").strip(),
        )

        if from_key == to_key:
            raise ItemValidationError(
                "Cannot gift an item to the same owner."
            )

        # Verify from_owner exists in owned_by
        current_keys = [
            (o.get("name", "").strip().lower(), o.get("type", "").strip())
            for o in item.owned_by
        ]
        if from_key not in current_keys:
            raise ItemValidationError(
                f"'{from_owner.get('name', '')}' ({from_owner.get('type', '')}) "
                f"is not a current owner of item '{item_id}'."
            )

        # Verify to_owner is not already an owner
        if to_key in current_keys:
            raise ItemValidationError(
                f"'{to_owner.get('name', '')}' ({to_owner.get('type', '')}) "
                f"already owns item '{item_id}'."
            )

        # Build new owned_by: remove from_owner, add to_owner
        new_owned_by = [
            o for o in item.owned_by
            if (o.get("name", "").strip().lower(), o.get("type", "").strip()) != from_key
        ]
        new_owned_by.append({
            "name": to_owner["name"].strip(),
            "type": to_owner["type"].strip(),
        })

        now = datetime.now(timezone.utc).isoformat()
        updated = Item.from_dict({
            **item.to_dict(),
            "owned_by": [dict(o) for o in new_owned_by],
            "updated_at": now,
        })
        self._save(updated)

        return GiftRecord(
            item_id=item_id,
            item_name=item.name,
            from_owner=from_owner,
            to_owner=to_owner,
            message=message,
            timestamp=now,
        )

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("ITEM-*.json")))
        return f"ItemManager(dir={self._dir!r}, items={count})"


# ─── Gift Record (F-068) ──────────────────────────────────────


@dataclass(frozen=True)
class GiftRecord:
    """Captures a completed gift transfer for downstream processing."""

    item_id: str
    item_name: str
    from_owner: dict[str, str]
    to_owner: dict[str, str]
    message: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "item_name": self.item_name,
            "from_owner": dict(self.from_owner),
            "to_owner": dict(self.to_owner),
            "message": self.message,
            "timestamp": self.timestamp,
        }
