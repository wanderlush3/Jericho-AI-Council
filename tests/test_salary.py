"""
Tests for Jericho Salary / Payroll System.

Covers SalaryManager: first-run disbursement, interval gating,
correct credit amounts, account auto-creation, and idempotency.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.salary import SalaryManager


# ─── Helpers ─────────────────────────────────────────────────


def _make_registry(names: list[str]):
    """Mock CouncilRegistry with given member names."""
    members = [SimpleNamespace(name=n) for n in names]
    registry = SimpleNamespace(
        list_members=lambda: members,
    )
    # .load() returns self
    return SimpleNamespace(load=lambda: registry)


def _make_char_mgr(chars: list[dict]):
    """Mock CharacterManager with given characters.

    Each dict: {"id": "CH-0001", "name": "Atlas", "status": "active"}
    """
    objects = [SimpleNamespace(**c) for c in chars]

    def list_characters(status=None):
        if status is not None:
            return [o for o in objects if o.status == status]
        return list(objects)

    return SimpleNamespace(list_characters=list_characters)


# ─── Fixtures ────────────────────────────────────────────────


@pytest.fixture()
def salary_env(tmp_path, monkeypatch):
    """Set up isolated treasury + salary dirs and patch managers."""
    treasury_dir = tmp_path / "treasury"
    treasury_dir.mkdir()
    ledger_path = tmp_path / "salary_ledger.json"

    # Patch config paths
    monkeypatch.setattr("config.settings.TREASURY_DIR", treasury_dir)

    # Create mock registry & character manager
    registry = _make_registry(["Sage", "Logic"])
    char_mgr = _make_char_mgr([
        {"id": "CH-0001", "name": "Atlas", "status": "active"},
        {"id": "CH-0002", "name": "Inactive", "status": "draft"},
    ])

    # Patch imports inside salary._disburse
    monkeypatch.setattr(
        "core.salary.SalaryManager._get_registry", lambda self: registry,
    ) if hasattr(SalaryManager, "_get_registry") else None

    # Monkey-patch the registry and char manager imports in the salary module
    import core.salary as sal_mod
    original_disburse = sal_mod.SalaryManager._disburse

    def patched_disburse(self_inner):
        """Call original _disburse but with patched imports."""
        import core.registry
        import core.characters
        import core.treasury

        orig_registry_cls = core.registry.CouncilRegistry
        orig_charmgr_cls = core.characters.CharacterManager
        orig_treasury_dir = core.treasury.TREASURY_DIR

        # Patch
        core.registry.CouncilRegistry = lambda: registry
        core.characters.CharacterManager = lambda: char_mgr
        monkeypatch.setattr("core.treasury.TREASURY_DIR", treasury_dir)

        try:
            # We need to inline the logic since the inner function
            # re-imports the modules.  Let's just call it with patched
            # config.settings.TREASURY_DIR which TreasuryManager __init__ uses.
            original_disburse(self_inner)
        finally:
            core.registry.CouncilRegistry = orig_registry_cls
            core.characters.CharacterManager = orig_charmgr_cls

    monkeypatch.setattr(sal_mod.SalaryManager, "_disburse", patched_disburse)

    mgr = SalaryManager(ledger_path=ledger_path)
    return SimpleNamespace(
        mgr=mgr,
        ledger_path=ledger_path,
        treasury_dir=treasury_dir,
    )


# ─── First Run ───────────────────────────────────────────────


class TestFirstRun:
    """When no ledger exists, salaries should be disbursed immediately."""

    def test_first_run_disburses(self, salary_env):
        assert not salary_env.ledger_path.exists()
        result = salary_env.mgr.check_and_pay()
        assert result is True
        assert salary_env.ledger_path.exists()

    def test_first_run_creates_ledger_with_timestamp(self, salary_env):
        salary_env.mgr.check_and_pay()
        data = json.loads(salary_env.ledger_path.read_text(encoding="utf-8"))
        assert "last_paid" in data
        # Timestamp should be recent (within last 60 seconds)
        ts = datetime.fromisoformat(data["last_paid"])
        assert (datetime.now(timezone.utc) - ts).total_seconds() < 60

    def test_first_run_credits_council_members(self, salary_env):
        salary_env.mgr.check_and_pay()
        from core.treasury import TreasuryManager
        tmgr = TreasuryManager(treasury_dir=salary_env.treasury_dir)
        sage = tmgr.get("ACCT-cm-sage")
        assert sage.balance.gold >= 200  # default 200 + salary 200 = 400
        logic = tmgr.get("ACCT-cm-logic")
        assert logic.balance.gold >= 200

    def test_first_run_credits_user(self, salary_env):
        salary_env.mgr.check_and_pay()
        from core.treasury import TreasuryManager
        tmgr = TreasuryManager(treasury_dir=salary_env.treasury_dir)
        user = tmgr.get("ACCT-user-human")
        assert user.balance.gold >= 200

    def test_first_run_credits_active_characters_only(self, salary_env):
        salary_env.mgr.check_and_pay()
        from core.treasury import TreasuryManager, AccountNotFoundError
        tmgr = TreasuryManager(treasury_dir=salary_env.treasury_dir)
        atlas = tmgr.get("ACCT-ch-ch-0001")
        assert atlas.balance.gold >= 100

        # Draft character should NOT have an account
        with pytest.raises(AccountNotFoundError):
            tmgr.get("ACCT-ch-ch-0002")


# ─── Interval Gating ────────────────────────────────────────


class TestIntervalGating:
    """Salaries should only disburse after the configured interval."""

    def test_within_interval_no_disburse(self, salary_env):
        # Simulate recent payroll (2 days ago)
        recent = datetime.now(timezone.utc) - timedelta(days=2)
        salary_env.ledger_path.write_text(
            json.dumps({"last_paid": recent.isoformat()}),
            encoding="utf-8",
        )
        result = salary_env.mgr.check_and_pay()
        assert result is False

    def test_at_interval_boundary_disburses(self, salary_env):
        # Exactly 7 days ago
        boundary = datetime.now(timezone.utc) - timedelta(days=7)
        salary_env.ledger_path.write_text(
            json.dumps({"last_paid": boundary.isoformat()}),
            encoding="utf-8",
        )
        result = salary_env.mgr.check_and_pay()
        assert result is True

    def test_past_interval_disburses(self, salary_env):
        # 10 days ago
        old = datetime.now(timezone.utc) - timedelta(days=10)
        salary_env.ledger_path.write_text(
            json.dumps({"last_paid": old.isoformat()}),
            encoding="utf-8",
        )
        result = salary_env.mgr.check_and_pay()
        assert result is True


# ─── Credit Amounts ──────────────────────────────────────────


class TestCreditAmounts:
    """Validate the correct gold amounts are credited."""

    def test_council_member_gets_200_gold(self, salary_env):
        salary_env.mgr.check_and_pay()
        from core.treasury import TreasuryManager
        tmgr = TreasuryManager(treasury_dir=salary_env.treasury_dir)
        sage = tmgr.get("ACCT-cm-sage")
        # Default balance is 200 + salary 200 = 400
        assert sage.balance.gold == 400

    def test_user_gets_200_gold(self, salary_env):
        salary_env.mgr.check_and_pay()
        from core.treasury import TreasuryManager
        tmgr = TreasuryManager(treasury_dir=salary_env.treasury_dir)
        user = tmgr.get("ACCT-user-human")
        assert user.balance.gold == 400

    def test_character_gets_100_gold(self, salary_env):
        salary_env.mgr.check_and_pay()
        from core.treasury import TreasuryManager
        tmgr = TreasuryManager(treasury_dir=salary_env.treasury_dir)
        atlas = tmgr.get("ACCT-ch-ch-0001")
        # Default balance is 200 + salary 100 = 300
        assert atlas.balance.gold == 300


# ─── Idempotency ─────────────────────────────────────────────


class TestIdempotency:
    """Double-calling within interval should not double-pay."""

    def test_double_call_no_double_pay(self, salary_env):
        salary_env.mgr.check_and_pay()  # first — disburses
        salary_env.mgr.check_and_pay()  # second — should skip

        from core.treasury import TreasuryManager
        tmgr = TreasuryManager(treasury_dir=salary_env.treasury_dir)
        sage = tmgr.get("ACCT-cm-sage")
        # Should be 200 (default) + 200 (one salary), NOT +400
        assert sage.balance.gold == 400


# ─── Corrupt Ledger ──────────────────────────────────────────


class TestCorruptLedger:
    """Corrupt ledger file should be treated as first run."""

    def test_corrupt_json_treated_as_first_run(self, salary_env):
        salary_env.ledger_path.write_text("NOT VALID JSON", encoding="utf-8")
        result = salary_env.mgr.check_and_pay()
        assert result is True
