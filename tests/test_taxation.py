"""
Tests for Jericho Taxation System (F-034).

Covers TaxPolicy, TaxEvent, TaxationManager, and integration
with TreasuryManager.transfer().
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from core.taxation import (
    TaxationError,
    TaxationManager,
    TaxationValidationError,
    TaxEvent,
    TaxPolicy,
)
from core.treasury import (
    ObeliskBalance,
    TreasuryAccount,
    TreasuryManager,
    TreasuryValidationError,
)


# ─── TaxPolicy ───────────────────────────────────────────────


class TestTaxPolicy:
    """Tests for the TaxPolicy dataclass."""

    def test_fields(self):
        p = TaxPolicy(rate=0.10, enabled=True, exempt_account_types=("government",))
        assert p.rate == 0.10
        assert p.enabled is True
        assert p.exempt_account_types == ("government",)

    def test_defaults(self):
        p = TaxPolicy()
        assert p.rate == 0.05
        assert p.enabled is True
        assert p.exempt_account_types == ("government",)

    def test_frozen(self):
        p = TaxPolicy()
        with pytest.raises(FrozenInstanceError):
            p.rate = 0.20  # type: ignore[misc]

    def test_to_dict(self):
        p = TaxPolicy(rate=0.10, enabled=False)
        d = p.to_dict()
        assert d["rate"] == 0.10
        assert d["enabled"] is False
        assert d["exempt_account_types"] == ["government"]

    def test_from_dict(self):
        d = {"rate": 0.15, "enabled": True, "exempt_account_types": ["government", "user"]}
        p = TaxPolicy.from_dict(d)
        assert p.rate == 0.15
        assert p.exempt_account_types == ("government", "user")

    def test_from_dict_missing_fields(self):
        p = TaxPolicy.from_dict({})
        assert p.rate == 0.05
        assert p.enabled is True

    def test_roundtrip(self):
        p = TaxPolicy(rate=0.20, enabled=False, exempt_account_types=("government", "user"))
        p2 = TaxPolicy.from_dict(p.to_dict())
        assert p.rate == p2.rate
        assert p.enabled == p2.enabled
        assert p.exempt_account_types == p2.exempt_account_types

    def test_create_factory(self):
        p = TaxPolicy.create(rate=0.10, enabled=True)
        assert p.rate == 0.10
        assert p.updated_at != ""

    def test_create_invalid_rate_too_high(self):
        with pytest.raises(TaxationValidationError) as exc_info:
            TaxPolicy.create(rate=1.5)
        assert "between 0.0 and 1.0" in exc_info.value.errors[0]

    def test_create_invalid_rate_negative(self):
        with pytest.raises(TaxationValidationError):
            TaxPolicy.create(rate=-0.1)

    def test_create_rate_zero(self):
        p = TaxPolicy.create(rate=0.0)
        assert p.rate == 0.0

    def test_create_rate_one(self):
        p = TaxPolicy.create(rate=1.0)
        assert p.rate == 1.0

    def test_create_custom_exempt(self):
        p = TaxPolicy.create(exempt_account_types=["government", "user"])
        assert p.exempt_account_types == ("government", "user")


# ─── TaxEvent ────────────────────────────────────────────────


class TestTaxEvent:
    """Tests for the TaxEvent dataclass."""

    def test_fields(self):
        e = TaxEvent(
            event_id="TX-000001",
            from_account="ACCT-cm-sage",
            to_account="ACCT-cm-logic",
            transaction_gold=50,
            tax_gold=2,
            tax_rate=0.05,
        )
        assert e.event_id == "TX-000001"
        assert e.from_account == "ACCT-cm-sage"
        assert e.transaction_gold == 50
        assert e.tax_gold == 2

    def test_frozen(self):
        e = TaxEvent(event_id="TX-000001", from_account="A", to_account="B")
        with pytest.raises(FrozenInstanceError):
            e.event_id = "TX-999"  # type: ignore[misc]

    def test_to_dict(self):
        e = TaxEvent(event_id="TX-000001", from_account="A", to_account="B", tax_gold=5)
        d = e.to_dict()
        assert d["event_id"] == "TX-000001"
        assert d["tax_gold"] == 5

    def test_from_dict(self):
        d = {"event_id": "TX-000001", "from_account": "A", "to_account": "B", "tax_gold": 5}
        e = TaxEvent.from_dict(d)
        assert e.event_id == "TX-000001"
        assert e.tax_gold == 5

    def test_roundtrip(self):
        e = TaxEvent(
            event_id="TX-000001", from_account="A", to_account="B",
            transaction_gold=50, transaction_silver=10,
            tax_gold=2, tax_silver=0, tax_bronze=50,
            tax_rate=0.05, timestamp="2026-01-01",
        )
        e2 = TaxEvent.from_dict(e.to_dict())
        assert e.event_id == e2.event_id
        assert e.tax_gold == e2.tax_gold
        assert e.tax_bronze == e2.tax_bronze

    def test_create_factory(self):
        e = TaxEvent.create(
            event_id="TX-000001",
            from_account="A",
            to_account="B",
            transaction_gold=100,
            tax_gold=5,
            tax_rate=0.05,
        )
        assert e.timestamp != ""
        assert e.event_id == "TX-000001"

    def test_defaults(self):
        e = TaxEvent(event_id="TX-000001", from_account="A", to_account="B")
        assert e.transaction_gold == 0
        assert e.tax_gold == 0
        assert e.tax_rate == 0.0
        assert e.metadata == {}


# ─── TaxationManager Init ───────────────────────────────────


class TestTaxationManagerInit:
    """Tests for TaxationManager initialization."""

    def test_creates_default_policy(self, tmp_path):
        policy_file = tmp_path / "tax_policy.json"
        ledger_file = tmp_path / "tax_ledger.jsonl"
        mgr = TaxationManager(policy_file=policy_file, ledger_file=ledger_file)
        assert policy_file.exists()
        policy = mgr.get_policy()
        assert policy.rate == 0.05
        assert policy.enabled is True

    def test_loads_existing_policy(self, tmp_path):
        policy_file = tmp_path / "tax_policy.json"
        ledger_file = tmp_path / "tax_ledger.jsonl"

        # Write a custom policy
        policy_data = {"rate": 0.10, "enabled": False, "exempt_account_types": ["government"]}
        policy_file.write_text(json.dumps(policy_data), encoding="utf-8")

        mgr = TaxationManager(policy_file=policy_file, ledger_file=ledger_file)
        policy = mgr.get_policy()
        assert policy.rate == 0.10
        assert policy.enabled is False

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        policy_file = nested / "tax_policy.json"
        ledger_file = nested / "tax_ledger.jsonl"
        mgr = TaxationManager(policy_file=policy_file, ledger_file=ledger_file)
        assert nested.exists()

    def test_repr(self, tmp_path):
        policy_file = tmp_path / "tax_policy.json"
        ledger_file = tmp_path / "tax_ledger.jsonl"
        mgr = TaxationManager(policy_file=policy_file, ledger_file=ledger_file)
        r = repr(mgr)
        assert "TaxationManager" in r
        assert "rate=0.05" in r


# ─── Get / Update Policy ────────────────────────────────────


class TestGetSetPolicy:
    """Tests for policy get and update."""

    def _make_mgr(self, tmp_path):
        return TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )

    def test_get_default(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        p = mgr.get_policy()
        assert p.rate == 0.05
        assert p.enabled is True

    def test_update_rate(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        p = mgr.update_policy(rate=0.10)
        assert p.rate == 0.10
        # Persisted
        p2 = mgr.get_policy()
        assert p2.rate == 0.10

    def test_update_enabled(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        p = mgr.update_policy(enabled=False)
        assert p.enabled is False

    def test_update_exemptions(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        p = mgr.update_policy(exempt_account_types=["government", "user"])
        assert p.exempt_account_types == ("government", "user")

    def test_update_invalid_rate(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        with pytest.raises(TaxationValidationError):
            mgr.update_policy(rate=2.0)

    def test_partial_update_preserves_other_fields(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr.update_policy(rate=0.15)
        p = mgr.update_policy(enabled=False)
        assert p.rate == 0.15
        assert p.enabled is False

    def test_persistence_across_instances(self, tmp_path):
        pf = tmp_path / "tax_policy.json"
        lf = tmp_path / "tax_ledger.jsonl"
        mgr1 = TaxationManager(policy_file=pf, ledger_file=lf)
        mgr1.update_policy(rate=0.20)

        mgr2 = TaxationManager(policy_file=pf, ledger_file=lf)
        assert mgr2.get_policy().rate == 0.20


# ─── Calculate Tax ──────────────────────────────────────────


class TestCalculateTax:
    """Tests for tax calculation."""

    def _make_mgr(self, tmp_path, rate=0.05):
        mgr = TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )
        mgr.update_policy(rate=rate)
        return mgr

    def test_basic_gold_tax(self, tmp_path):
        mgr = self._make_mgr(tmp_path, rate=0.10)
        tax = mgr.calculate_tax("council_member", "council_member", gold=100)
        # 100 gold = 1_000_000 bronze, 10% = 100_000 bronze = 10 gold
        assert tax["gold"] == 10
        assert tax["silver"] == 0
        assert tax["bronze"] == 0

    def test_zero_rate(self, tmp_path):
        mgr = self._make_mgr(tmp_path, rate=0.0)
        tax = mgr.calculate_tax("council_member", "council_member", gold=100)
        assert tax == {"gold": 0, "silver": 0, "bronze": 0}

    def test_exempt_from_account(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        tax = mgr.calculate_tax("government", "council_member", gold=100)
        assert tax == {"gold": 0, "silver": 0, "bronze": 0}

    def test_exempt_to_account(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        tax = mgr.calculate_tax("council_member", "government", gold=100)
        assert tax == {"gold": 0, "silver": 0, "bronze": 0}

    def test_disabled_policy(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        mgr.update_policy(enabled=False)
        tax = mgr.calculate_tax("council_member", "council_member", gold=100)
        assert tax == {"gold": 0, "silver": 0, "bronze": 0}

    def test_silver_tax(self, tmp_path):
        mgr = self._make_mgr(tmp_path, rate=0.10)
        tax = mgr.calculate_tax("council_member", "council_member", silver=100)
        # 100 silver = 10_000 bronze, 10% = 1000 bronze = 10 silver
        assert tax["gold"] == 0
        assert tax["silver"] == 10
        assert tax["bronze"] == 0

    def test_bronze_tax(self, tmp_path):
        mgr = self._make_mgr(tmp_path, rate=0.10)
        tax = mgr.calculate_tax("council_member", "council_member", bronze=1000)
        # 1000 bronze, 10% = 100 bronze = 1 silver
        assert tax["gold"] == 0
        assert tax["silver"] == 1
        assert tax["bronze"] == 0

    def test_mixed_tiers(self, tmp_path):
        mgr = self._make_mgr(tmp_path, rate=0.05)
        tax = mgr.calculate_tax(
            "council_member", "council_member",
            gold=10, silver=50, bronze=200,
        )
        # 10 gold = 100_000 bronze
        # 50 silver = 5_000 bronze
        # 200 bronze
        # total = 105_200 bronze
        # 5% = 5_260 bronze
        # 5_260 / 10_000 = 0 gold, remainder 5_260
        # 5_260 / 100 = 52 silver, remainder 60 bronze
        assert tax["gold"] == 0
        assert tax["silver"] == 52
        assert tax["bronze"] == 60

    def test_very_small_transfer(self, tmp_path):
        mgr = self._make_mgr(tmp_path, rate=0.05)
        tax = mgr.calculate_tax("council_member", "council_member", bronze=1)
        # 1 bronze * 0.05 = 0.05, floor = 0
        assert tax == {"gold": 0, "silver": 0, "bronze": 0}

    def test_rounding_floor(self, tmp_path):
        mgr = self._make_mgr(tmp_path, rate=0.05)
        tax = mgr.calculate_tax("council_member", "council_member", bronze=99)
        # 99 * 0.05 = 4.95, floor = 4 bronze
        assert tax["bronze"] == 4
        assert tax["silver"] == 0

    def test_zero_transfer(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        tax = mgr.calculate_tax("council_member", "council_member", gold=0)
        assert tax == {"gold": 0, "silver": 0, "bronze": 0}


# ─── Collect Tax ────────────────────────────────────────────


class TestCollectTax:
    """Tests for tax collection with a real TreasuryManager."""

    def _setup(self, tmp_path, rate=0.10):
        treasury_dir = tmp_path / "treasury"
        tax_mgr = TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )
        tax_mgr.update_policy(rate=rate)
        mgr = TreasuryManager(treasury_dir=treasury_dir)
        return mgr, tax_mgr

    def test_basic_collection(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        event = tax_mgr.collect_tax(
            from_account_id="ACCT-cm-sage",
            to_account_id="ACCT-cm-logic",
            from_account_type="council_member",
            to_account_type="council_member",
            gold=100,
            treasury_manager=mgr,
        )

        assert event is not None
        assert event.tax_gold == 10
        assert event.from_account == "ACCT-cm-sage"
        assert event.to_account == "ACCT-cm-logic"

    def test_recipient_debited(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        # Credit Logic first so they have enough after tax deduction
        mgr.credit("ACCT-cm-logic", gold=100)

        tax_mgr.collect_tax(
            from_account_id="ACCT-cm-sage",
            to_account_id="ACCT-cm-logic",
            from_account_type="council_member",
            to_account_type="council_member",
            gold=100,
            treasury_manager=mgr,
        )

        logic = mgr.get("ACCT-cm-logic")
        # Started with 200 + 100 credit = 300, then debited 10 gold tax
        assert logic.balance.gold == 290

    def test_government_credited(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        mgr.credit("ACCT-cm-logic", gold=100)

        tax_mgr.collect_tax(
            from_account_id="ACCT-cm-sage",
            to_account_id="ACCT-cm-logic",
            from_account_type="council_member",
            to_account_type="council_member",
            gold=100,
            treasury_manager=mgr,
        )

        gov = mgr.get("ACCT-gov-jericho")
        assert gov.balance.gold == 1010  # 1000 + 10 tax

    def test_ledger_appended(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        mgr.credit("ACCT-cm-logic", gold=100)

        tax_mgr.collect_tax(
            from_account_id="ACCT-cm-sage",
            to_account_id="ACCT-cm-logic",
            from_account_type="council_member",
            to_account_type="council_member",
            gold=100,
            treasury_manager=mgr,
        )

        events = tax_mgr.list_events()
        assert len(events) == 1
        assert events[0].tax_gold == 10

    def test_exempt_transfer_no_tax(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")

        event = tax_mgr.collect_tax(
            from_account_id="ACCT-gov-jericho",
            to_account_id="ACCT-cm-sage",
            from_account_type="government",
            to_account_type="council_member",
            gold=100,
            treasury_manager=mgr,
        )
        assert event is None

    def test_no_treasury_manager_raises(self, tmp_path):
        _, tax_mgr = self._setup(tmp_path, rate=0.10)
        with pytest.raises(TaxationError, match="treasury_manager"):
            tax_mgr.collect_tax(
                from_account_id="A",
                to_account_id="B",
                from_account_type="council_member",
                to_account_type="council_member",
                gold=100,
            )

    def test_multiple_collections(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        mgr.credit("ACCT-cm-logic", gold=50)
        mgr.credit("ACCT-cm-sage", gold=50)

        tax_mgr.collect_tax(
            from_account_id="ACCT-cm-sage",
            to_account_id="ACCT-cm-logic",
            from_account_type="council_member",
            to_account_type="council_member",
            gold=50,
            treasury_manager=mgr,
        )
        tax_mgr.collect_tax(
            from_account_id="ACCT-cm-logic",
            to_account_id="ACCT-cm-sage",
            from_account_type="council_member",
            to_account_type="council_member",
            gold=30,
            treasury_manager=mgr,
        )

        events = tax_mgr.list_events()
        assert len(events) == 2


# ─── Tax Events ──────────────────────────────────────────────


class TestTaxEvents:
    """Tests for event listing and filtering."""

    def _make_mgr(self, tmp_path):
        return TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )

    def test_list_empty(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        assert mgr.list_events() == []

    def test_list_after_manual_append(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"

        event = TaxEvent.create(
            event_id="TX-000001", from_account="A", to_account="B",
            transaction_gold=100, tax_gold=5, tax_rate=0.05,
        )
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict()) + "\n")

        events = mgr.list_events()
        assert len(events) == 1
        assert events[0].event_id == "TX-000001"

    def test_filter_by_from_account(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"

        for i, from_acct in enumerate(["A", "B", "A"]):
            event = TaxEvent.create(
                event_id=f"TX-{i:06d}", from_account=from_acct, to_account="C",
                tax_gold=1, tax_rate=0.05,
            )
            with open(ledger, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

        events = mgr.list_events(from_account="A")
        assert len(events) == 2

    def test_filter_by_to_account(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"

        for i, to_acct in enumerate(["X", "Y", "X"]):
            event = TaxEvent.create(
                event_id=f"TX-{i:06d}", from_account="A", to_account=to_acct,
                tax_gold=1, tax_rate=0.05,
            )
            with open(ledger, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

        events = mgr.list_events(to_account="X")
        assert len(events) == 2

    def test_limit(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"

        for i in range(10):
            event = TaxEvent.create(
                event_id=f"TX-{i:06d}", from_account="A", to_account="B",
                tax_gold=1, tax_rate=0.05,
            )
            with open(ledger, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

        events = mgr.list_events(limit=3)
        assert len(events) == 3

    def test_newest_first(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"

        for i in range(3):
            event = TaxEvent.create(
                event_id=f"TX-{i:06d}", from_account="A", to_account="B",
                tax_gold=i, tax_rate=0.05,
            )
            with open(ledger, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

        events = mgr.list_events()
        assert events[0].event_id == "TX-000002"
        assert events[2].event_id == "TX-000000"

    def test_corrupt_lines_skipped(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"
        ledger.write_text(
            "not json\n"
            + json.dumps(TaxEvent.create(
                event_id="TX-000001", from_account="A", to_account="B",
                tax_gold=1, tax_rate=0.05,
            ).to_dict()) + "\n",
            encoding="utf-8",
        )

        events = mgr.list_events()
        assert len(events) == 1

    def test_comment_lines_skipped(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"
        ledger.write_text(
            "# this is a comment\n"
            + json.dumps(TaxEvent.create(
                event_id="TX-000001", from_account="A", to_account="B",
                tax_gold=1, tax_rate=0.05,
            ).to_dict()) + "\n",
            encoding="utf-8",
        )

        events = mgr.list_events()
        assert len(events) == 1

    def test_clear_ledger(self, tmp_path):
        mgr = self._make_mgr(tmp_path)
        ledger = tmp_path / "tax_ledger.jsonl"
        ledger.write_text(
            json.dumps(TaxEvent.create(
                event_id="TX-000001", from_account="A", to_account="B",
                tax_gold=1, tax_rate=0.05,
            ).to_dict()) + "\n",
            encoding="utf-8",
        )
        mgr.clear_ledger()
        assert not ledger.exists()
        assert mgr.list_events() == []


# ─── Total Collected ────────────────────────────────────────


class TestTotalCollected:
    """Tests for total tax collected."""

    def test_empty(self, tmp_path):
        mgr = TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )
        total = mgr.get_total_collected()
        assert total == {"gold": 0, "silver": 0, "bronze": 0}

    def test_sum_of_events(self, tmp_path):
        mgr = TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )
        ledger = tmp_path / "tax_ledger.jsonl"
        for i in range(3):
            event = TaxEvent.create(
                event_id=f"TX-{i:06d}", from_account="A", to_account="B",
                tax_gold=5, tax_silver=2, tax_bronze=10, tax_rate=0.05,
            )
            with open(ledger, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict()) + "\n")

        total = mgr.get_total_collected()
        assert total == {"gold": 15, "silver": 6, "bronze": 30}


# ─── Treasury Integration ───────────────────────────────────


class TestTreasuryIntegration:
    """Tests for transfer() with taxation_manager wired in."""

    def _setup(self, tmp_path, rate=0.10):
        treasury_dir = tmp_path / "treasury"
        tax_mgr = TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )
        tax_mgr.update_policy(rate=rate)
        mgr = TreasuryManager(
            treasury_dir=treasury_dir,
            taxation_manager=tax_mgr,
        )
        return mgr, tax_mgr

    def test_transfer_collects_tax(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        from_acct, to_acct = mgr.transfer("ACCT-cm-sage", "ACCT-cm-logic", gold=100)

        # Sender deducted 100 gold
        assert from_acct.balance.gold == 100  # 200 - 100
        # Recipient got 100 gold minus 10 gold tax
        assert to_acct.balance.gold == 290  # 200 + 100 - 10

        # Government received tax
        gov = mgr.get("ACCT-gov-jericho")
        assert gov.balance.gold == 1010

        # Tax event recorded
        events = tax_mgr.list_events()
        assert len(events) == 1

    def test_transfer_no_tax_when_disabled(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        tax_mgr.update_policy(enabled=False)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        from_acct, to_acct = mgr.transfer("ACCT-cm-sage", "ACCT-cm-logic", gold=100)

        assert to_acct.balance.gold == 300  # 200 + 100, no tax
        gov = mgr.get("ACCT-gov-jericho")
        assert gov.balance.gold == 1000  # unchanged

    def test_transfer_collect_tax_false(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        from_acct, to_acct = mgr.transfer(
            "ACCT-cm-sage", "ACCT-cm-logic", gold=100, collect_tax=False,
        )

        assert to_acct.balance.gold == 300  # 200 + 100, no tax

    def test_transfer_exempt_government_no_tax(self, tmp_path):
        mgr, tax_mgr = self._setup(tmp_path, rate=0.10)
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")

        from_acct, to_acct = mgr.transfer(
            "ACCT-gov-jericho", "ACCT-cm-sage", gold=100,
        )

        # Government is exempt — no tax on this transfer
        assert to_acct.balance.gold == 300  # 200 + 100
        events = tax_mgr.list_events()
        assert len(events) == 0

    def test_transfer_without_taxation_manager(self, tmp_path):
        """Transfer works normally when no TaxationManager is provided."""
        treasury_dir = tmp_path / "treasury"
        mgr = TreasuryManager(treasury_dir=treasury_dir)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")

        from_acct, to_acct = mgr.transfer("ACCT-cm-sage", "ACCT-cm-logic", gold=50)

        assert from_acct.balance.gold == 150
        assert to_acct.balance.gold == 250


# ─── Edge Cases ──────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_in_metadata(self, tmp_path):
        mgr = TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )
        event = TaxEvent.create(
            event_id="TX-000001",
            from_account="ACCT-cm-café",
            to_account="ACCT-cm-naïve",
            tax_gold=1,
            tax_rate=0.05,
            metadata={"note": "Transferencia con ñ"},
        )
        ledger = tmp_path / "tax_ledger.jsonl"
        with open(ledger, "a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

        events = mgr.list_events()
        assert len(events) == 1
        assert events[0].from_account == "ACCT-cm-café"
        assert events[0].metadata["note"] == "Transferencia con ñ"

    def test_full_lifecycle(self, tmp_path):
        """Create policy → update → transfer with tax → verify events."""
        treasury_dir = tmp_path / "treasury"
        tax_mgr = TaxationManager(
            policy_file=tmp_path / "tax_policy.json",
            ledger_file=tmp_path / "tax_ledger.jsonl",
        )

        # Start disabled
        tax_mgr.update_policy(enabled=False)
        assert tax_mgr.get_policy().enabled is False

        # Enable and set rate
        tax_mgr.update_policy(rate=0.10, enabled=True)
        assert tax_mgr.get_policy().rate == 0.10

        # Wire into treasury
        mgr = TreasuryManager(
            treasury_dir=treasury_dir,
            taxation_manager=tax_mgr,
        )
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        # Transfer with tax
        mgr.transfer("ACCT-cm-sage", "ACCT-cm-logic", gold=50)

        # Verify
        events = tax_mgr.list_events()
        assert len(events) == 1
        assert events[0].tax_gold == 5

        total = tax_mgr.get_total_collected()
        assert total["gold"] == 5

    def test_persistence_roundtrip(self, tmp_path):
        """Events survive manager re-instantiation."""
        pf = tmp_path / "tax_policy.json"
        lf = tmp_path / "tax_ledger.jsonl"

        mgr1 = TaxationManager(policy_file=pf, ledger_file=lf)
        # Write an event manually
        with open(lf, "a", encoding="utf-8") as f:
            f.write(json.dumps(TaxEvent.create(
                event_id="TX-000001", from_account="A", to_account="B",
                tax_gold=5, tax_rate=0.05,
            ).to_dict()) + "\n")

        mgr2 = TaxationManager(policy_file=pf, ledger_file=lf)
        events = mgr2.list_events()
        assert len(events) == 1
        assert events[0].tax_gold == 5


# ─── Exceptions ──────────────────────────────────────────────


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_hierarchy(self):
        assert issubclass(TaxationValidationError, TaxationError)

    def test_validation_fields(self):
        err = TaxationValidationError(["error1", "error2"])
        assert len(err.errors) == 2
        assert "error1" in str(err)
