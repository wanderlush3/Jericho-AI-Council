"""
Jericho — World Stores System (F-036)

Commercial establishments where Items can be listed for sale and purchased
using Obelisk currency.  Bridges the Items (F-035) and Treasury (F-032)
systems to give the Jericho economy a purpose.

Lifecycle:  draft → active → archived

Storage: one JSON file per store in ``data/stores/``, named ``STORE-XXXX.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import STORE_INJECTION_MAX_LENGTH, STORES_DIR, STORE_STATUSES, STORE_TYPES
from core.utils import atomic_write, make_id_lock


# ─── Exceptions ────────────────────────────────────────────────


class StoreError(Exception):
    """Base exception for store-system errors."""


class StoreNotFoundError(StoreError):
    """Raised when a store ID is not found on disk."""

    def __init__(self, store_id: str) -> None:
        self.store_id = store_id
        super().__init__(f"Store not found: '{store_id}'")


class StoreValidationError(StoreError):
    """Raised when store data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


class StoreLifecycleError(StoreError):
    """Raised when an invalid status transition is attempted."""

    def __init__(
        self, store_id: str, current_status: str, requested_status: str,
    ) -> None:
        self.store_id = store_id
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(
            f"Cannot transition store '{store_id}' from "
            f"'{current_status}' to '{requested_status}'."
        )


class StorePurchaseError(StoreError):
    """Raised when a purchase cannot be completed."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class StoreItem:
    """An item listed for sale in a store."""

    item_id: str
    price_gold: int = 0
    price_silver: int = 0
    price_bronze: int = 0
    quantity: int = -1  # -1 = unlimited
    added_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoreItem:
        return cls(
            item_id=data["item_id"],
            price_gold=int(data.get("price_gold", 0)),
            price_silver=int(data.get("price_silver", 0)),
            price_bronze=int(data.get("price_bronze", 0)),
            quantity=int(data.get("quantity", -1)),
            added_at=data.get("added_at", ""),
        )

    @classmethod
    def create(
        cls,
        item_id: str,
        *,
        price_gold: int = 0,
        price_silver: int = 0,
        price_bronze: int = 0,
        quantity: int = -1,
    ) -> StoreItem:
        """Factory with validation."""
        errors: list[str] = []
        if not item_id.strip():
            errors.append("Item ID is required.")
        if price_gold < 0:
            errors.append("Gold price cannot be negative.")
        if price_silver < 0:
            errors.append("Silver price cannot be negative.")
        if price_bronze < 0:
            errors.append("Bronze price cannot be negative.")
        if price_gold == 0 and price_silver == 0 and price_bronze == 0:
            errors.append("At least one price tier must be set.")
        if quantity < -1:
            errors.append("Quantity must be -1 (unlimited) or >= 0.")
        if errors:
            raise StoreValidationError(errors)
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            item_id=item_id.strip(),
            price_gold=price_gold,
            price_silver=price_silver,
            price_bronze=price_bronze,
            quantity=quantity,
            added_at=now,
        )


@dataclass(frozen=True)
class Store:
    """Immutable snapshot of a world store."""

    id: str
    name: str
    description: str
    author: str
    status: str = "draft"
    store_type: str = "general"
    location_id: str = ""
    owner: str = ""
    inventory: list[StoreItem] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    lore: str = ""
    llm_injection: str = ""
    version: int = 1
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["inventory"] = [si.to_dict() for si in self.inventory]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Store:
        inventory = [
            StoreItem.from_dict(si)
            for si in data.get("inventory", [])
        ]
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            author=data.get("author", ""),
            status=data.get("status", "draft"),
            store_type=data.get("store_type", "general"),
            location_id=data.get("location_id", ""),
            owner=data.get("owner", ""),
            inventory=inventory,
            tags=data.get("tags", []),
            lore=data.get("lore", ""),
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
        store_type: str = "general",
        location_id: str = "",
        owner: str = "",
        inventory: list[StoreItem] | None = None,
        tags: list[str] | None = None,
        lore: str = "",
        llm_injection: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Store:
        """Factory that sets timestamps and defaults."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            name=name,
            description=description,
            author=author,
            status="draft",
            store_type=store_type,
            location_id=location_id,
            owner=owner,
            inventory=inventory or [],
            tags=tags or [],
            lore=lore,
            llm_injection=llm_injection,
            version=1,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Valid Lifecycle Transitions ───────────────────────────────

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active"},
    "active": {"archived", "draft"},
    "archived": set(),  # terminal
}


# ─── Store Manager ────────────────────────────────────────────


class StoreManager:
    """Filesystem-backed CRUD manager for world stores.

    Each store is stored as ``STORE-XXXX.json`` in the stores directory.

    Usage::

        mgr = StoreManager()
        store = mgr.create("Ironhaven Smithy", "A master forge", author="Council")
        mgr.add_inventory_item(store.id, StoreItem.create("ITEM-0001", price_gold=10))
        mgr.update_status(store.id, "active")
    """

    _ID_PATTERN = re.compile(r"^STORE-(\d{4})\.json$")

    def __init__(self, stores_dir: Path | None = None) -> None:
        self._dir = stores_dir or STORES_DIR
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
        author: str = "",
        store_type: str = "general",
        location_id: str = "",
        owner: str = "",
        tags: list[str] | None = None,
        lore: str = "",
        llm_injection: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Store:
        """Create a new store in draft status."""
        errors: list[str] = []
        if not name.strip():
            errors.append("Name is required.")
        if not description.strip():
            errors.append("Description is required.")
        if not author.strip():
            errors.append("Author is required.")
        if store_type and store_type not in STORE_TYPES:
            errors.append(
                f"Invalid store type '{store_type}'. "
                f"Must be one of: {', '.join(STORE_TYPES)}"
            )
        if llm_injection and len(llm_injection) > STORE_INJECTION_MAX_LENGTH:
            errors.append(
                f"LLM injection text exceeds maximum length of "
                f"{STORE_INJECTION_MAX_LENGTH} characters "
                f"(got {len(llm_injection)})."
            )
        if errors:
            raise StoreValidationError(errors)

        with self._id_lock:
            store_id = self._next_id()
            store = Store.create(
                id=store_id,
                name=name.strip(),
                description=description.strip(),
                author=author.strip(),
                store_type=store_type,
                location_id=location_id.strip() if location_id else "",
                owner=owner.strip() if owner else "",
                tags=tags or [],
                lore=lore,
                llm_injection=llm_injection,
                metadata=metadata or {},
            )
            self._save(store)
        return store

    # ── Read ──────────────────────────────────────────────────

    def get(self, store_id: str) -> Store:
        """Load a single store by ID."""
        filepath = self._filepath(store_id)
        if not filepath.exists():
            raise StoreNotFoundError(store_id)
        return self._load(filepath)

    def list_stores(
        self,
        *,
        status: str | None = None,
        author: str | None = None,
        tag: str | None = None,
        store_type: str | None = None,
    ) -> list[Store]:
        """List stores with optional filters."""
        stores: list[Store] = []
        for filepath in sorted(self._dir.glob("STORE-*.json")):
            try:
                store = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files

            if status and store.status != status:
                continue
            if author and store.author.lower() != author.lower():
                continue
            if tag and tag.lower() not in [t.lower() for t in store.tags]:
                continue
            if store_type and store.store_type != store_type:
                continue
            stores.append(store)
        return stores

    # ── Status Lifecycle ──────────────────────────────────────

    def update_status(self, store_id: str, new_status: str) -> Store:
        """Transition a store to a new lifecycle status."""
        if new_status not in STORE_STATUSES:
            raise StoreValidationError(
                f"Unknown status '{new_status}'. "
                f"Must be one of: {', '.join(STORE_STATUSES)}"
            )

        store = self.get(store_id)
        allowed = _VALID_TRANSITIONS.get(store.status, set())
        if new_status not in allowed:
            raise StoreLifecycleError(store_id, store.status, new_status)

        now = datetime.now(timezone.utc).isoformat()
        updated = Store.from_dict({
            **store.to_dict(),
            "status": new_status,
            "updated_at": now,
        })
        self._save(updated)
        return updated

    # ── Inventory Management ──────────────────────────────────

    def add_inventory_item(self, store_id: str, item: StoreItem) -> Store:
        """Add an item to a store's inventory (item_id must be unique)."""
        store = self.get(store_id)
        existing_ids = {si.item_id for si in store.inventory}
        if item.item_id in existing_ids:
            raise StoreValidationError(
                f"Item '{item.item_id}' is already in this store's inventory."
            )

        now = datetime.now(timezone.utc).isoformat()
        new_inventory = list(store.inventory) + [item]
        updated = Store.from_dict({
            **store.to_dict(),
            "inventory": [si.to_dict() for si in new_inventory],
            "updated_at": now,
        })
        self._save(updated)
        return updated

    def remove_inventory_item(self, store_id: str, item_id: str) -> Store:
        """Remove an item from a store's inventory."""
        store = self.get(store_id)
        new_inventory = [si for si in store.inventory if si.item_id != item_id]
        if len(new_inventory) == len(store.inventory):
            raise StoreValidationError(
                f"Item '{item_id}' not found in this store's inventory."
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = Store.from_dict({
            **store.to_dict(),
            "inventory": [si.to_dict() for si in new_inventory],
            "updated_at": now,
        })
        self._save(updated)
        return updated

    def update_inventory_item(
        self, store_id: str, item_id: str, **fields: Any,
    ) -> Store:
        """Update price/quantity of an existing inventory entry."""
        store = self.get(store_id)
        found = False
        new_inventory: list[StoreItem] = []
        for si in store.inventory:
            if si.item_id == item_id:
                found = True
                data = si.to_dict()
                data.update(fields)
                new_inventory.append(StoreItem.from_dict(data))
            else:
                new_inventory.append(si)

        if not found:
            raise StoreValidationError(
                f"Item '{item_id}' not found in this store's inventory."
            )

        now = datetime.now(timezone.utc).isoformat()
        updated = Store.from_dict({
            **store.to_dict(),
            "inventory": [si.to_dict() for si in new_inventory],
            "updated_at": now,
        })
        self._save(updated)
        return updated

    # ── Purchase ──────────────────────────────────────────────

    def purchase(
        self,
        store_id: str,
        item_id: str,
        buyer_account_id: str,
        treasury_manager: Any,
    ) -> dict[str, Any]:
        """Execute a purchase: debit buyer, credit store owner, decrement stock.

        Args:
            store_id: ID of the store.
            item_id: ID of the item to purchase.
            buyer_account_id: Treasury account ID of the buyer.
            treasury_manager: A TreasuryManager instance for fund transfers.

        Returns:
            Dict with ``store``, ``item``, ``buyer_account``, ``seller_account`` keys.

        Raises:
            StoreNotFoundError: If store does not exist.
            StorePurchaseError: If store is not active, item not in stock,
                or buyer has insufficient funds.
        """
        store = self.get(store_id)
        if store.status != "active":
            raise StorePurchaseError(
                f"Store '{store_id}' is not active (status: {store.status})."
            )

        # Find the item in inventory
        listing: StoreItem | None = None
        for si in store.inventory:
            if si.item_id == item_id:
                listing = si
                break
        if listing is None:
            raise StorePurchaseError(
                f"Item '{item_id}' is not available in store '{store_id}'."
            )

        # Check stock
        if listing.quantity == 0:
            raise StorePurchaseError(
                f"Item '{item_id}' is out of stock in store '{store_id}'."
            )

        # Determine seller account — use store owner or fall back to government
        from core.treasury import make_account_id
        if store.owner:
            seller_account_id = make_account_id("character", store.owner)
            # Try council_member if character account doesn't exist
            try:
                treasury_manager.get(seller_account_id)
            except Exception:
                seller_account_id = make_account_id("council_member", store.owner)
        else:
            from config.settings import TAX_GOVERNMENT_ACCOUNT_ID
            seller_account_id = TAX_GOVERNMENT_ACCOUNT_ID

        # Execute the transfer (debit buyer → credit seller)
        try:
            buyer_acct, seller_acct = treasury_manager.transfer(
                buyer_account_id,
                seller_account_id,
                gold=listing.price_gold,
                silver=listing.price_silver,
                bronze=listing.price_bronze,
            )
        except Exception as exc:
            raise StorePurchaseError(f"Payment failed: {exc}")

        # Decrement quantity (if not unlimited)
        if listing.quantity > 0:
            new_qty = listing.quantity - 1
            self.update_inventory_item(store_id, item_id, quantity=new_qty)

        # Reload store after inventory update
        store = self.get(store_id)
        return {
            "store": store.to_dict(),
            "item": listing.to_dict(),
            "buyer_account": buyer_acct.to_dict(),
            "seller_account": seller_acct.to_dict(),
        }

    # ── General Update ────────────────────────────────────────

    _MUTABLE_FIELDS = {
        "name", "description", "lore", "tags", "metadata",
        "location_id", "owner", "store_type", "llm_injection",
    }

    def update(self, store_id: str, **fields: Any) -> Store:
        """Update mutable fields on a store."""
        immutable = {"id", "author", "status", "created_at", "version", "inventory"}
        bad = set(fields.keys()) & immutable
        if bad:
            raise StoreValidationError(
                f"Cannot update immutable field(s): {', '.join(sorted(bad))}"
            )

        # Validate store_type if provided
        if "store_type" in fields:
            st = fields["store_type"]
            if st and st not in STORE_TYPES:
                raise StoreValidationError(
                    f"Invalid store type '{st}'. "
                    f"Must be one of: {', '.join(STORE_TYPES)}"
                )

        # Validate llm_injection length if provided
        if "llm_injection" in fields:
            inj = fields["llm_injection"]
            if isinstance(inj, str) and len(inj) > STORE_INJECTION_MAX_LENGTH:
                raise StoreValidationError(
                    f"LLM injection text exceeds maximum length of "
                    f"{STORE_INJECTION_MAX_LENGTH} characters "
                    f"(got {len(inj)})."
                )

        store = self.get(store_id)
        now = datetime.now(timezone.utc).isoformat()
        data = store.to_dict()
        data.update(fields)
        data["updated_at"] = now
        updated = Store.from_dict(data)
        self._save(updated)
        return updated

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, store_id: str) -> Path:
        return self._dir / f"{store_id}.json"

    def _save(self, store: Store) -> None:
        payload = json.dumps(store.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(store.id), payload + "\n")

    def _load(self, filepath: Path) -> Store:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return Store.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential STORE-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("STORE-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"STORE-{max_num + 1:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("STORE-*.json")))
        return f"StoreManager(stores={count}, dir={self._dir})"
