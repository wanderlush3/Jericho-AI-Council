"""
Jericho — Salary / Payroll System

Hidden automatic payroll that runs on web-server startup.
Every SALARY_INTERVAL_DAYS (default 7) each council member and user
receives SALARY_COUNCIL_USER_AMOUNT Gold Obelisk, and each active
character receives SALARY_CHARACTER_AMOUNT Gold Obelisk.

State is persisted in ``data/salary_ledger.json``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    SALARY_LEDGER_FILE,
    SALARY_INTERVAL_DAYS,
    SALARY_COUNCIL_USER_AMOUNT,
    SALARY_CHARACTER_AMOUNT,
)

log = logging.getLogger(__name__)


class SalaryManager:
    """Automatic payroll manager.

    Usage::

        mgr = SalaryManager()
        mgr.check_and_pay()   # call once at startup
    """

    def __init__(self, ledger_path: Path | None = None) -> None:
        self._ledger = ledger_path or SALARY_LEDGER_FILE
        self._ledger.parent.mkdir(parents=True, exist_ok=True)

    # ── Public ────────────────────────────────────────────────

    def check_and_pay(self) -> bool:
        """Check whether a payroll run is due and execute it if so.

        Returns ``True`` if funds were disbursed, ``False`` otherwise.
        """
        data = self._load_ledger()

        if data is None:
            # First run ever — no ledger exists.  Disburse immediately.
            log.info("Salary: first run — disbursing initial salaries.")
            self._disburse()
            return True

        last_paid = datetime.fromisoformat(data["last_paid"])
        elapsed = datetime.now(timezone.utc) - last_paid

        if elapsed.days >= SALARY_INTERVAL_DAYS:
            log.info(
                "Salary: %d days since last payroll (threshold %d) — disbursing.",
                elapsed.days,
                SALARY_INTERVAL_DAYS,
            )
            self._disburse()
            return True

        log.debug(
            "Salary: only %d days since last payroll — skipping.",
            elapsed.days,
        )
        return False

    # ── Internal ──────────────────────────────────────────────

    def _disburse(self) -> None:
        """Credit salaries to all eligible accounts and update the ledger."""
        from core.registry import CouncilRegistry
        from core.characters import CharacterManager
        from core.treasury import TreasuryManager, make_account_id

        treasury = TreasuryManager()

        # ── Council members: 200 Gold each ────────────────────
        try:
            registry = CouncilRegistry().load()
            for member in registry.list_members():
                acct_id = make_account_id("council_member", member.name)
                treasury.get_or_create(acct_id, "council_member", member.name)
                treasury.credit(acct_id, gold=SALARY_COUNCIL_USER_AMOUNT)
                log.info(
                    "Salary: credited %d Gold to council member %s (%s)",
                    SALARY_COUNCIL_USER_AMOUNT,
                    member.name,
                    acct_id,
                )
        except Exception:
            log.exception("Salary: failed to pay council members")

        # ── User: 200 Gold ────────────────────────────────────
        try:
            user_id = make_account_id("user", "Human")
            treasury.get_or_create(user_id, "user", "Human")
            treasury.credit(user_id, gold=SALARY_COUNCIL_USER_AMOUNT)
            log.info(
                "Salary: credited %d Gold to user (%s)",
                SALARY_COUNCIL_USER_AMOUNT,
                user_id,
            )
        except Exception:
            log.exception("Salary: failed to pay user")

        # ── Active characters: 100 Gold each ──────────────────
        try:
            char_mgr = CharacterManager()
            for char in char_mgr.list_characters(status="active"):
                acct_id = make_account_id("character", char.id)
                treasury.get_or_create(acct_id, "character", char.name)
                treasury.credit(acct_id, gold=SALARY_CHARACTER_AMOUNT)
                log.info(
                    "Salary: credited %d Gold to character %s (%s)",
                    SALARY_CHARACTER_AMOUNT,
                    char.name,
                    acct_id,
                )
        except Exception:
            log.exception("Salary: failed to pay characters")

        # ── Update ledger ─────────────────────────────────────
        self._save_ledger({"last_paid": datetime.now(timezone.utc).isoformat()})
        log.info("Salary: payroll complete — ledger updated.")

    # ── Ledger I/O ────────────────────────────────────────────

    def _load_ledger(self) -> dict[str, Any] | None:
        if not self._ledger.exists():
            return None
        try:
            return json.loads(self._ledger.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, KeyError):
            log.warning("Salary: corrupt ledger — treating as first run.")
            return None

    def _save_ledger(self, data: dict[str, Any]) -> None:
        self._ledger.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
