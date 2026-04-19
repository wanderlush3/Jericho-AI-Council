"""
Jericho — Obelisk Treasury System (F-032)

Monetary system with three coin tiers: Bronze, Silver, Gold.
Conversion rate: 100 Bronze = 1 Silver, 100 Silver = 1 Gold.

Each entity (council member, character, user, government) has an account
stored as ``ACCT-<slug>.json`` in ``data/treasury/``.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    TREASURY_DIR,
    OBELISK_CONVERSION_RATE,
    OBELISK_DEFAULT_BALANCE,
    OBELISK_GOVERNMENT_BALANCE,
    OBELISK_ACCOUNT_TYPES,
)
from core.utils import atomic_write

log = logging.getLogger(__name__)


# ─── Exceptions ────────────────────────────────────────────────


class TreasuryError(Exception):
    """Base exception for treasury-system errors."""


class AccountNotFoundError(TreasuryError):
    """Raised when an account ID is not found."""

    def __init__(self, account_id: str) -> None:
        self.account_id = account_id
        super().__init__(f"Treasury account not found: '{account_id}'")


class InsufficientFundsError(TreasuryError):
    """Raised when a debit exceeds available funds."""

    def __init__(self, account_id: str, tier: str, requested: int, available: int) -> None:
        self.account_id = account_id
        self.tier = tier
        self.requested = requested
        self.available = available
        super().__init__(
            f"Insufficient {tier} Obelisk in '{account_id}': "
            f"requested {requested}, available {available}"
        )


class TreasuryValidationError(TreasuryError):
    """Raised when treasury data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ObeliskBalance:
    """Immutable representation of an Obelisk balance across all three tiers."""

    gold: int = 0
    silver: int = 0
    bronze: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)

    def total_in_bronze(self) -> int:
        """Convert the entire balance to its bronze equivalent."""
        rate = OBELISK_CONVERSION_RATE
        return (self.gold * rate * rate) + (self.silver * rate) + self.bronze

    def total_in_gold_display(self) -> str:
        """Human-readable gold equivalent (e.g. '200.00')."""
        rate = OBELISK_CONVERSION_RATE
        total_bronze = self.total_in_bronze()
        gold_equiv = total_bronze / (rate * rate)
        return f"{gold_equiv:.2f}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ObeliskBalance:
        return cls(
            gold=int(data.get("gold", 0)),
            silver=int(data.get("silver", 0)),
            bronze=int(data.get("bronze", 0)),
        )

    @classmethod
    def create(cls, gold: int = 0, silver: int = 0, bronze: int = 0) -> ObeliskBalance:
        """Factory with validation."""
        errors: list[str] = []
        if gold < 0:
            errors.append(f"Gold cannot be negative: {gold}")
        if silver < 0:
            errors.append(f"Silver cannot be negative: {silver}")
        if bronze < 0:
            errors.append(f"Bronze cannot be negative: {bronze}")
        if errors:
            raise TreasuryValidationError(errors)
        return cls(gold=gold, silver=silver, bronze=bronze)


@dataclass(frozen=True)
class TreasuryAccount:
    """Immutable snapshot of a treasury account."""

    account_id: str
    account_type: str    # council_member | character | user | government
    owner_name: str
    balance: ObeliskBalance = field(default_factory=ObeliskBalance)
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["balance"] = self.balance.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TreasuryAccount:
        return cls(
            account_id=data["account_id"],
            account_type=data["account_type"],
            owner_name=data["owner_name"],
            balance=ObeliskBalance.from_dict(data.get("balance", {})),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        account_id: str,
        account_type: str,
        owner_name: str,
        balance: ObeliskBalance | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> TreasuryAccount:
        """Factory with auto-timestamps and validation."""
        errors: list[str] = []
        if not account_id.strip():
            errors.append("Account ID must not be empty")
        if not owner_name.strip():
            errors.append("Owner name must not be empty")
        if account_type not in OBELISK_ACCOUNT_TYPES:
            errors.append(
                f"Invalid account type '{account_type}' — "
                f"must be one of {OBELISK_ACCOUNT_TYPES}"
            )
        if errors:
            raise TreasuryValidationError(errors)

        now = datetime.now(timezone.utc).isoformat()
        return cls(
            account_id=account_id.strip(),
            account_type=account_type,
            owner_name=owner_name.strip(),
            balance=balance or ObeliskBalance(),
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Slug Helper ───────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    return _SLUG_RE.sub("-", name.strip().lower()).strip("-")


def make_account_id(account_type: str, name: str) -> str:
    """Build a canonical account ID from type and name.

    Examples:
        make_account_id("council_member", "Sage") -> "ACCT-cm-sage"
        make_account_id("character", "CH-0001") -> "ACCT-ch-ch-0001"
        make_account_id("user", "Human") -> "ACCT-user-human"
        make_account_id("government", "Jericho") -> "ACCT-gov-jericho"
    """
    prefix_map = {
        "council_member": "cm",
        "character": "ch",
        "user": "user",
        "government": "gov",
    }
    prefix = prefix_map.get(account_type, account_type[:3])
    slug = _slugify(name)
    return f"ACCT-{prefix}-{slug}"


# ─── Treasury Manager ─────────────────────────────────────────


class TreasuryManager:
    """
    Filesystem-backed Obelisk treasury.

    Each account is stored as ``ACCT-<slug>.json`` in the treasury directory.

    Usage::

        mgr = TreasuryManager()
        acct = mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.credit("ACCT-cm-sage", gold=50)
        acct = mgr.debit("ACCT-cm-sage", silver=10)
    """

    def __init__(
        self,
        treasury_dir: Path | None = None,
        taxation_manager: Any | None = None,
    ) -> None:
        self._dir = treasury_dir or TREASURY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._taxation_manager = taxation_manager

    @property
    def directory(self) -> Path:
        return self._dir

    # ── Get / Create ─────────────────────────────────────────

    def get(self, account_id: str) -> TreasuryAccount:
        """Load an account by ID. Raises AccountNotFoundError if missing."""
        filepath = self._filepath(account_id)
        if not filepath.exists():
            raise AccountNotFoundError(account_id)
        return self._load(filepath)

    def get_or_create(
        self,
        account_id: str,
        account_type: str,
        owner_name: str,
        default_balance: dict[str, int] | None = None,
    ) -> TreasuryAccount:
        """Load existing account or create with default balance."""
        filepath = self._filepath(account_id)
        if filepath.exists():
            return self._load(filepath)

        if default_balance is None:
            if account_type == "government":
                default_balance = dict(OBELISK_GOVERNMENT_BALANCE)
            else:
                default_balance = dict(OBELISK_DEFAULT_BALANCE)

        balance = ObeliskBalance.create(**default_balance)
        account = TreasuryAccount.create(
            account_id=account_id,
            account_type=account_type,
            owner_name=owner_name,
            balance=balance,
        )
        self._save(account)
        return account

    # ── List ──────────────────────────────────────────────────

    def list_accounts(
        self, *, account_type: str | None = None
    ) -> list[TreasuryAccount]:
        """Return accounts sorted by ID, with optional type filter."""
        accounts: list[TreasuryAccount] = []
        for filepath in sorted(self._dir.glob("ACCT-*.json")):
            try:
                acct = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue
            if account_type is not None and acct.account_type != account_type:
                continue
            accounts.append(acct)
        return accounts

    # ── Credit / Debit ───────────────────────────────────────

    def credit(
        self,
        account_id: str,
        gold: int = 0,
        silver: int = 0,
        bronze: int = 0,
    ) -> TreasuryAccount:
        """Add funds to an account. Returns updated account."""
        account = self.get(account_id)
        errors: list[str] = []
        if gold < 0:
            errors.append("Gold credit cannot be negative")
        if silver < 0:
            errors.append("Silver credit cannot be negative")
        if bronze < 0:
            errors.append("Bronze credit cannot be negative")
        if errors:
            raise TreasuryValidationError(errors)

        new_balance = ObeliskBalance(
            gold=account.balance.gold + gold,
            silver=account.balance.silver + silver,
            bronze=account.balance.bronze + bronze,
        )
        return self._update_balance(account, new_balance)

    def debit(
        self,
        account_id: str,
        gold: int = 0,
        silver: int = 0,
        bronze: int = 0,
    ) -> TreasuryAccount:
        """Remove funds from an account. Raises InsufficientFundsError if short."""
        account = self.get(account_id)
        errors: list[str] = []
        if gold < 0:
            errors.append("Gold debit cannot be negative")
        if silver < 0:
            errors.append("Silver debit cannot be negative")
        if bronze < 0:
            errors.append("Bronze debit cannot be negative")
        if errors:
            raise TreasuryValidationError(errors)

        if account.balance.gold < gold:
            raise InsufficientFundsError(account_id, "gold", gold, account.balance.gold)
        if account.balance.silver < silver:
            raise InsufficientFundsError(account_id, "silver", silver, account.balance.silver)
        if account.balance.bronze < bronze:
            raise InsufficientFundsError(account_id, "bronze", bronze, account.balance.bronze)

        new_balance = ObeliskBalance(
            gold=account.balance.gold - gold,
            silver=account.balance.silver - silver,
            bronze=account.balance.bronze - bronze,
        )
        return self._update_balance(account, new_balance)

    # ── Transfer ─────────────────────────────────────────────

    def transfer(
        self,
        from_id: str,
        to_id: str,
        gold: int = 0,
        silver: int = 0,
        bronze: int = 0,
        *,
        collect_tax: bool = True,
    ) -> tuple[TreasuryAccount, TreasuryAccount]:
        """Transfer funds between accounts. Returns (from_acct, to_acct).

        When *collect_tax* is True and a ``taxation_manager`` was provided
        to this TreasuryManager, tax is automatically collected from the
        recipient and credited to the government account.
        """
        if from_id == to_id:
            raise TreasuryValidationError(["Cannot transfer to the same account"])

        # Debit first (validates funds), then credit
        from_acct = self.debit(from_id, gold=gold, silver=silver, bronze=bronze)
        to_acct = self.credit(to_id, gold=gold, silver=silver, bronze=bronze)

        # Collect tax if enabled
        if collect_tax and self._taxation_manager is not None:
            try:
                self._taxation_manager.collect_tax(
                    from_account_id=from_id,
                    to_account_id=to_id,
                    from_account_type=from_acct.account_type,
                    to_account_type=to_acct.account_type,
                    gold=gold,
                    silver=silver,
                    bronze=bronze,
                    treasury_manager=self,
                )
                # Reload accounts to reflect tax deduction
                to_acct = self.get(to_id)
            except Exception:
                log.warning(
                    "Tax collection failed for transfer %s -> %s",
                    from_id, to_id, exc_info=True,
                )

        return from_acct, to_acct

    # ── Normalize ────────────────────────────────────────────

    def normalize(self, account_id: str) -> TreasuryAccount:
        """Auto-convert excess coins upward.

        E.g. 150 bronze → 1 silver + 50 bronze.
        """
        account = self.get(account_id)
        rate = OBELISK_CONVERSION_RATE

        bronze = account.balance.bronze
        silver = account.balance.silver
        gold = account.balance.gold

        # Bronze → Silver
        if bronze >= rate:
            carry = bronze // rate
            bronze = bronze % rate
            silver += carry

        # Silver → Gold
        if silver >= rate:
            carry = silver // rate
            silver = silver % rate
            gold += carry

        new_balance = ObeliskBalance(gold=gold, silver=silver, bronze=bronze)
        return self._update_balance(account, new_balance)

    # ── Initialize Defaults ──────────────────────────────────

    def initialize_defaults(
        self,
        registry=None,
        character_manager=None,
    ) -> list[TreasuryAccount]:
        """Create default accounts for all known entities.

        - Council members: 200 Gold each
        - Active characters: 200 Gold each
        - User: 200 Gold
        - Government: 1000 Gold

        Skips accounts that already exist. Returns list of newly created accounts.
        """
        created: list[TreasuryAccount] = []

        # Government
        gov_id = make_account_id("government", "Jericho")
        if not self._filepath(gov_id).exists():
            acct = self.get_or_create(gov_id, "government", "Jericho")
            created.append(acct)

        # User
        user_id = make_account_id("user", "Human")
        if not self._filepath(user_id).exists():
            acct = self.get_or_create(user_id, "user", "Human")
            created.append(acct)

        # Council members
        if registry is not None:
            for member in registry.list_members():
                acct_id = make_account_id("council_member", member.name)
                if not self._filepath(acct_id).exists():
                    acct = self.get_or_create(
                        acct_id, "council_member", member.name
                    )
                    created.append(acct)

        # Characters (active only)
        if character_manager is not None:
            for char in character_manager.list_characters(status="active"):
                acct_id = make_account_id("character", char.id)
                if not self._filepath(acct_id).exists():
                    acct = self.get_or_create(
                        acct_id, "character", char.name,
                    )
                    created.append(acct)

        return created

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, account_id: str) -> Path:
        return self._dir / f"{account_id}.json"

    def _save(self, account: TreasuryAccount) -> None:
        payload = json.dumps(account.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(account.account_id), payload + "\n")

    def _load(self, filepath: Path) -> TreasuryAccount:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return TreasuryAccount.from_dict(data)

    def _update_balance(
        self, account: TreasuryAccount, new_balance: ObeliskBalance
    ) -> TreasuryAccount:
        """Save an account with an updated balance and timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        updated = dataclasses.replace(
            account, balance=new_balance, updated_at=now,
        )
        self._save(updated)
        return updated

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("ACCT-*.json")))
        return f"TreasuryManager(accounts={count}, dir={self._dir})"
