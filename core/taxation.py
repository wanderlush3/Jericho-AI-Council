"""
Jericho — Obelisk Taxation System (F-034)

Government taxation mechanism with configurable rates, exemptions,
and an append-only event ledger.

Tax is collected on ``TreasuryManager.transfer()`` operations:
the recipient pays a percentage of the transferred amount, which
is credited to the government treasury account.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    TAX_POLICY_FILE,
    TAX_LEDGER_FILE,
    TAX_DEFAULT_RATE,
    TAX_GOVERNMENT_ACCOUNT_ID,
    OBELISK_CONVERSION_RATE,
)
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class TaxationError(Exception):
    """Base exception for taxation-system errors."""


class TaxationValidationError(TaxationError):
    """Raised when tax data fails validation."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(f"Validation failed: {'; '.join(errors)}")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class TaxPolicy:
    """Immutable snapshot of the current tax policy."""

    rate: float = 0.05          # 0.0 – 1.0
    enabled: bool = True
    exempt_account_types: tuple[str, ...] = ("government",)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rate": self.rate,
            "enabled": self.enabled,
            "exempt_account_types": list(self.exempt_account_types),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaxPolicy:
        exempt = data.get("exempt_account_types", ["government"])
        return cls(
            rate=float(data.get("rate", TAX_DEFAULT_RATE)),
            enabled=bool(data.get("enabled", True)),
            exempt_account_types=tuple(exempt),
            updated_at=data.get("updated_at", ""),
        )

    @classmethod
    def create(
        cls,
        *,
        rate: float = TAX_DEFAULT_RATE,
        enabled: bool = True,
        exempt_account_types: list[str] | tuple[str, ...] | None = None,
    ) -> TaxPolicy:
        """Factory with validation."""
        errors: list[str] = []
        if rate < 0.0 or rate > 1.0:
            errors.append(f"Tax rate must be between 0.0 and 1.0, got {rate}")
        if errors:
            raise TaxationValidationError(errors)
        now = datetime.now(timezone.utc).isoformat()
        exempt = tuple(exempt_account_types) if exempt_account_types is not None else ("government",)
        return cls(
            rate=rate,
            enabled=enabled,
            exempt_account_types=exempt,
            updated_at=now,
        )


@dataclass(frozen=True)
class TaxEvent:
    """Immutable record of a single tax collection event."""

    event_id: str
    from_account: str
    to_account: str
    transaction_gold: int = 0
    transaction_silver: int = 0
    transaction_bronze: int = 0
    tax_gold: int = 0
    tax_silver: int = 0
    tax_bronze: int = 0
    tax_rate: float = 0.0
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaxEvent:
        return cls(
            event_id=data.get("event_id", ""),
            from_account=data.get("from_account", ""),
            to_account=data.get("to_account", ""),
            transaction_gold=int(data.get("transaction_gold", 0)),
            transaction_silver=int(data.get("transaction_silver", 0)),
            transaction_bronze=int(data.get("transaction_bronze", 0)),
            tax_gold=int(data.get("tax_gold", 0)),
            tax_silver=int(data.get("tax_silver", 0)),
            tax_bronze=int(data.get("tax_bronze", 0)),
            tax_rate=float(data.get("tax_rate", 0.0)),
            timestamp=data.get("timestamp", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        event_id: str,
        from_account: str,
        to_account: str,
        transaction_gold: int = 0,
        transaction_silver: int = 0,
        transaction_bronze: int = 0,
        tax_gold: int = 0,
        tax_silver: int = 0,
        tax_bronze: int = 0,
        tax_rate: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> TaxEvent:
        """Factory with auto-timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            event_id=event_id,
            from_account=from_account,
            to_account=to_account,
            transaction_gold=transaction_gold,
            transaction_silver=transaction_silver,
            transaction_bronze=transaction_bronze,
            tax_gold=tax_gold,
            tax_silver=tax_silver,
            tax_bronze=tax_bronze,
            tax_rate=tax_rate,
            timestamp=now,
            metadata=metadata or {},
        )


# ─── Taxation Manager ─────────────────────────────────────────


class TaxationManager:
    """
    Manages tax policy and collection for the Obelisk treasury.

    Tax is calculated on the bronze-equivalent of the transfer amount,
    then converted back to gold/silver/bronze tiers.

    Usage::

        tax_mgr = TaxationManager()
        policy = tax_mgr.get_policy()
        tax = tax_mgr.calculate_tax("ACCT-cm-sage", "ACCT-cm-logic", gold=50)
        event = tax_mgr.collect_tax("ACCT-cm-sage", "ACCT-cm-logic",
                                     gold=50, treasury_manager=treasury)
    """

    def __init__(
        self,
        policy_file: Path | None = None,
        ledger_file: Path | None = None,
        gov_account_id: str = TAX_GOVERNMENT_ACCOUNT_ID,
    ) -> None:
        self._policy_file = policy_file or TAX_POLICY_FILE
        self._ledger_file = ledger_file or TAX_LEDGER_FILE

        # Ensure parent directories exist
        self._policy_file.parent.mkdir(parents=True, exist_ok=True)
        self._ledger_file.parent.mkdir(parents=True, exist_ok=True)

        self._gov_account_id = gov_account_id
        self._event_counter = 0

        # Load or create default policy
        if not self._policy_file.exists():
            self._save_policy(TaxPolicy.create())

    @property
    def government_account_id(self) -> str:
        return self._gov_account_id

    # ── Policy ───────────────────────────────────────────────

    def get_policy(self) -> TaxPolicy:
        """Load current tax policy from disk."""
        return self._load_policy()

    def update_policy(
        self,
        *,
        rate: float | None = None,
        enabled: bool | None = None,
        exempt_account_types: list[str] | None = None,
    ) -> TaxPolicy:
        """Update and persist the tax policy. Returns new policy."""
        current = self._load_policy()
        new_rate = rate if rate is not None else current.rate
        new_enabled = enabled if enabled is not None else current.enabled
        new_exempt = (
            tuple(exempt_account_types) if exempt_account_types is not None
            else current.exempt_account_types
        )
        policy = TaxPolicy.create(
            rate=new_rate,
            enabled=new_enabled,
            exempt_account_types=list(new_exempt),
        )
        self._save_policy(policy)
        return policy

    # ── Tax Calculation ──────────────────────────────────────

    def calculate_tax(
        self,
        from_account_type: str,
        to_account_type: str,
        gold: int = 0,
        silver: int = 0,
        bronze: int = 0,
    ) -> dict[str, int]:
        """Calculate tax amounts for a transfer.

        Returns dict with ``gold``, ``silver``, ``bronze`` tax amounts.
        Returns all zeros if the transfer is exempt or tax is disabled.
        """
        policy = self._load_policy()

        # Check if tax is disabled or transfer is exempt
        if not policy.enabled or policy.rate <= 0.0:
            return {"gold": 0, "silver": 0, "bronze": 0}

        if from_account_type in policy.exempt_account_types:
            return {"gold": 0, "silver": 0, "bronze": 0}
        if to_account_type in policy.exempt_account_types:
            return {"gold": 0, "silver": 0, "bronze": 0}

        # Convert entire transfer to bronze equivalent
        rate = OBELISK_CONVERSION_RATE
        total_bronze = (gold * rate * rate) + (silver * rate) + bronze

        # Calculate tax in bronze (floor)
        tax_bronze_total = int(math.floor(total_bronze * policy.rate))

        if tax_bronze_total <= 0:
            return {"gold": 0, "silver": 0, "bronze": 0}

        # Convert tax back to tiers
        tax_gold = tax_bronze_total // (rate * rate)
        remainder = tax_bronze_total % (rate * rate)
        tax_silver = remainder // rate
        tax_bronze_final = remainder % rate

        return {
            "gold": int(tax_gold),
            "silver": int(tax_silver),
            "bronze": int(tax_bronze_final),
        }

    # ── Tax Collection ───────────────────────────────────────

    def collect_tax(
        self,
        from_account_id: str,
        to_account_id: str,
        from_account_type: str,
        to_account_type: str,
        gold: int = 0,
        silver: int = 0,
        bronze: int = 0,
        *,
        treasury_manager: Any = None,
    ) -> TaxEvent | None:
        """Collect tax on a transfer.

        Debits tax from ``to_account`` (recipient pays) and credits
        the government account. Appends a TaxEvent to the ledger.

        Returns the TaxEvent, or None if no tax was collected
        (exempt or zero tax).

        Requires a ``treasury_manager`` with ``debit()`` and ``credit()``
        methods.
        """
        tax = self.calculate_tax(
            from_account_type, to_account_type,
            gold=gold, silver=silver, bronze=bronze,
        )

        # Check if any tax is due
        if tax["gold"] == 0 and tax["silver"] == 0 and tax["bronze"] == 0:
            return None

        if treasury_manager is None:
            raise TaxationError(
                "A treasury_manager is required to collect tax"
            )

        # Debit tax from recipient
        treasury_manager.debit(
            to_account_id,
            gold=tax["gold"],
            silver=tax["silver"],
            bronze=tax["bronze"],
        )

        # Credit government
        treasury_manager.credit(
            self._gov_account_id,
            gold=tax["gold"],
            silver=tax["silver"],
            bronze=tax["bronze"],
        )

        # Record event
        self._event_counter += 1
        event_id = f"TX-{self._event_counter:06d}"
        event = TaxEvent.create(
            event_id=event_id,
            from_account=from_account_id,
            to_account=to_account_id,
            transaction_gold=gold,
            transaction_silver=silver,
            transaction_bronze=bronze,
            tax_gold=tax["gold"],
            tax_silver=tax["silver"],
            tax_bronze=tax["bronze"],
            tax_rate=self._load_policy().rate,
        )
        self._append_event(event)
        return event

    # ── Event Log ────────────────────────────────────────────

    def list_events(
        self,
        *,
        limit: int | None = None,
        from_account: str | None = None,
        to_account: str | None = None,
    ) -> list[TaxEvent]:
        """Read tax events from the ledger.

        Returns newest-first. Optional filters by from/to account.
        """
        events: list[TaxEvent] = []
        if not self._ledger_file.exists():
            return events

        for line in self._ledger_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
                event = TaxEvent.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                continue

            if from_account and event.from_account != from_account:
                continue
            if to_account and event.to_account != to_account:
                continue
            events.append(event)

        # Newest first
        events.reverse()

        if limit is not None and limit > 0:
            events = events[:limit]

        return events

    def get_total_collected(self) -> dict[str, int]:
        """Sum of all tax ever collected, returned as gold/silver/bronze.

        The result is *not* normalized — it's the raw sum of each tier.
        """
        events = self.list_events()
        total_gold = sum(e.tax_gold for e in events)
        total_silver = sum(e.tax_silver for e in events)
        total_bronze = sum(e.tax_bronze for e in events)
        return {"gold": total_gold, "silver": total_silver, "bronze": total_bronze}

    def clear_ledger(self) -> None:
        """Delete all recorded tax events. For admin / testing."""
        if self._ledger_file.exists():
            self._ledger_file.unlink()

    # ── Internal ──────────────────────────────────────────────

    def _load_policy(self) -> TaxPolicy:
        if not self._policy_file.exists():
            return TaxPolicy.create()
        text = self._policy_file.read_text(encoding="utf-8")
        data = json.loads(text)
        return TaxPolicy.from_dict(data)

    def _save_policy(self, policy: TaxPolicy) -> None:
        payload = json.dumps(policy.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._policy_file, payload + "\n")

    def _append_event(self, event: TaxEvent) -> None:
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with open(self._ledger_file, "a", encoding="utf-8") as f:
            f.write(line)

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        try:
            policy = self._load_policy()
            return (
                f"TaxationManager(rate={policy.rate}, "
                f"enabled={policy.enabled})"
            )
        except Exception:
            return "TaxationManager()"
