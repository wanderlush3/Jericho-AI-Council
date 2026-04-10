"""
Tests for Jericho Treasury / Obelisk System (F-032).

Covers ObeliskBalance, TreasuryAccount, TreasuryManager, and all
credit/debit/transfer/normalize operations.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.treasury import (
    AccountNotFoundError,
    InsufficientFundsError,
    ObeliskBalance,
    TreasuryAccount,
    TreasuryError,
    TreasuryManager,
    TreasuryValidationError,
    make_account_id,
)


# ─── ObeliskBalance ──────────────────────────────────────────


class TestObeliskBalance:
    """Tests for the ObeliskBalance dataclass."""

    def test_fields(self):
        b = ObeliskBalance(gold=10, silver=20, bronze=30)
        assert b.gold == 10
        assert b.silver == 20
        assert b.bronze == 30

    def test_defaults(self):
        b = ObeliskBalance()
        assert b.gold == 0
        assert b.silver == 0
        assert b.bronze == 0

    def test_frozen(self):
        b = ObeliskBalance(gold=1)
        with pytest.raises(FrozenInstanceError):
            b.gold = 2  # type: ignore[misc]

    def test_to_dict(self):
        b = ObeliskBalance(gold=5, silver=10, bronze=15)
        d = b.to_dict()
        assert d == {"gold": 5, "silver": 10, "bronze": 15}

    def test_from_dict(self):
        d = {"gold": 5, "silver": 10, "bronze": 15}
        b = ObeliskBalance.from_dict(d)
        assert b.gold == 5
        assert b.silver == 10
        assert b.bronze == 15

    def test_from_dict_missing_fields(self):
        b = ObeliskBalance.from_dict({})
        assert b.gold == 0
        assert b.silver == 0
        assert b.bronze == 0

    def test_roundtrip(self):
        b = ObeliskBalance(gold=100, silver=50, bronze=25)
        b2 = ObeliskBalance.from_dict(b.to_dict())
        assert b == b2

    def test_total_in_bronze(self):
        b = ObeliskBalance(gold=1, silver=1, bronze=1)
        # 1 gold = 10000 bronze, 1 silver = 100 bronze, 1 bronze = 1
        assert b.total_in_bronze() == 10101

    def test_total_in_bronze_zero(self):
        b = ObeliskBalance()
        assert b.total_in_bronze() == 0

    def test_total_in_gold_display(self):
        b = ObeliskBalance(gold=200, silver=0, bronze=0)
        assert b.total_in_gold_display() == "200.00"

    def test_total_in_gold_display_fractional(self):
        b = ObeliskBalance(gold=0, silver=50, bronze=0)
        assert b.total_in_gold_display() == "0.50"

    def test_create_factory(self):
        b = ObeliskBalance.create(gold=10, silver=5, bronze=3)
        assert b.gold == 10
        assert b.silver == 5
        assert b.bronze == 3

    def test_create_negative_gold_raises(self):
        with pytest.raises(TreasuryValidationError) as exc_info:
            ObeliskBalance.create(gold=-1)
        assert "Gold cannot be negative" in exc_info.value.errors[0]

    def test_create_negative_silver_raises(self):
        with pytest.raises(TreasuryValidationError):
            ObeliskBalance.create(silver=-1)

    def test_create_negative_bronze_raises(self):
        with pytest.raises(TreasuryValidationError):
            ObeliskBalance.create(bronze=-1)


# ─── TreasuryAccount ─────────────────────────────────────────


class TestTreasuryAccount:
    """Tests for the TreasuryAccount dataclass."""

    def test_fields(self):
        b = ObeliskBalance(gold=200)
        a = TreasuryAccount(
            account_id="ACCT-cm-sage",
            account_type="council_member",
            owner_name="Sage",
            balance=b,
        )
        assert a.account_id == "ACCT-cm-sage"
        assert a.account_type == "council_member"
        assert a.owner_name == "Sage"
        assert a.balance.gold == 200

    def test_frozen(self):
        a = TreasuryAccount(
            account_id="ACCT-cm-sage",
            account_type="council_member",
            owner_name="Sage",
        )
        with pytest.raises(FrozenInstanceError):
            a.owner_name = "X"  # type: ignore[misc]

    def test_to_dict_roundtrip(self):
        b = ObeliskBalance(gold=100, silver=50, bronze=25)
        a = TreasuryAccount(
            account_id="ACCT-cm-sage",
            account_type="council_member",
            owner_name="Sage",
            balance=b,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        a2 = TreasuryAccount.from_dict(a.to_dict())
        assert a2.account_id == a.account_id
        assert a2.balance.gold == a.balance.gold
        assert a2.balance.silver == a.balance.silver

    def test_create_factory(self):
        a = TreasuryAccount.create(
            account_id="ACCT-cm-sage",
            account_type="council_member",
            owner_name="Sage",
            balance=ObeliskBalance(gold=200),
        )
        assert a.account_id == "ACCT-cm-sage"
        assert a.created_at != ""
        assert a.updated_at != ""

    def test_create_empty_id_raises(self):
        with pytest.raises(TreasuryValidationError):
            TreasuryAccount.create(
                account_id="",
                account_type="council_member",
                owner_name="Sage",
            )

    def test_create_empty_owner_raises(self):
        with pytest.raises(TreasuryValidationError):
            TreasuryAccount.create(
                account_id="ACCT-cm-sage",
                account_type="council_member",
                owner_name="",
            )

    def test_create_invalid_type_raises(self):
        with pytest.raises(TreasuryValidationError) as exc_info:
            TreasuryAccount.create(
                account_id="ACCT-x",
                account_type="invalid",
                owner_name="Test",
            )
        assert "Invalid account type" in exc_info.value.errors[0]

    def test_create_whitespace_strip(self):
        a = TreasuryAccount.create(
            account_id="  ACCT-cm-sage  ",
            account_type="council_member",
            owner_name="  Sage  ",
        )
        assert a.account_id == "ACCT-cm-sage"
        assert a.owner_name == "Sage"


# ─── make_account_id ─────────────────────────────────────────


class TestMakeAccountId:
    """Tests for the make_account_id helper."""

    def test_council_member(self):
        assert make_account_id("council_member", "Sage") == "ACCT-cm-sage"

    def test_character(self):
        assert make_account_id("character", "CH-0001") == "ACCT-ch-ch-0001"

    def test_user(self):
        assert make_account_id("user", "Human") == "ACCT-user-human"

    def test_government(self):
        assert make_account_id("government", "Jericho") == "ACCT-gov-jericho"

    def test_whitespace_stripped(self):
        assert make_account_id("council_member", "  Sage  ") == "ACCT-cm-sage"

    def test_special_chars(self):
        result = make_account_id("council_member", "Dr. Strange!")
        assert result == "ACCT-cm-dr-strange"


# ─── TreasuryManager Init ────────────────────────────────────


class TestTreasuryManagerInit:
    """Tests for TreasuryManager initialization."""

    def test_creates_directory(self, tmp_path):
        d = tmp_path / "treasury"
        mgr = TreasuryManager(treasury_dir=d)
        assert d.exists()
        assert mgr.directory == d

    def test_existing_directory(self, tmp_path):
        d = tmp_path / "treasury"
        d.mkdir()
        mgr = TreasuryManager(treasury_dir=d)
        assert d.exists()

    def test_repr(self, tmp_path):
        d = tmp_path / "treasury"
        mgr = TreasuryManager(treasury_dir=d)
        r = repr(mgr)
        assert "TreasuryManager" in r
        assert "accounts=0" in r


# ─── Get / Create ────────────────────────────────────────────


class TestGetOrCreate:
    """Tests for get_or_create and get."""

    def test_creates_new_account(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        acct = mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        assert acct.account_id == "ACCT-cm-sage"
        assert acct.owner_name == "Sage"
        assert acct.balance.gold == 200  # default
        assert acct.balance.silver == 0
        assert acct.balance.bronze == 0

    def test_loads_existing(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        acct1 = mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct2 = mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        assert acct1.created_at == acct2.created_at

    def test_government_default_balance(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        acct = mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")
        assert acct.balance.gold == 1000

    def test_custom_default_balance(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        acct = mgr.get_or_create(
            "ACCT-cm-sage", "council_member", "Sage",
            default_balance={"gold": 500, "silver": 50, "bronze": 25},
        )
        assert acct.balance.gold == 500
        assert acct.balance.silver == 50
        assert acct.balance.bronze == 25

    def test_get_not_found_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        with pytest.raises(AccountNotFoundError) as exc_info:
            mgr.get("ACCT-nonexistent")
        assert "ACCT-nonexistent" in str(exc_info.value)

    def test_persistence(self, tmp_path):
        d = tmp_path / "treasury"
        mgr1 = TreasuryManager(treasury_dir=d)
        mgr1.get_or_create("ACCT-cm-sage", "council_member", "Sage")

        mgr2 = TreasuryManager(treasury_dir=d)
        acct = mgr2.get("ACCT-cm-sage")
        assert acct.owner_name == "Sage"
        assert acct.balance.gold == 200


# ─── Credit ──────────────────────────────────────────────────


class TestCredit:
    """Tests for credit operations."""

    def test_credit_gold(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.credit("ACCT-cm-sage", gold=50)
        assert acct.balance.gold == 250

    def test_credit_silver(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.credit("ACCT-cm-sage", silver=30)
        assert acct.balance.silver == 30

    def test_credit_bronze(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.credit("ACCT-cm-sage", bronze=500)
        assert acct.balance.bronze == 500

    def test_credit_multiple_tiers(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.credit("ACCT-cm-sage", gold=10, silver=20, bronze=30)
        assert acct.balance.gold == 210
        assert acct.balance.silver == 20
        assert acct.balance.bronze == 30

    def test_credit_persists(self, tmp_path):
        d = tmp_path / "treasury"
        mgr = TreasuryManager(treasury_dir=d)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.credit("ACCT-cm-sage", gold=50)

        mgr2 = TreasuryManager(treasury_dir=d)
        acct = mgr2.get("ACCT-cm-sage")
        assert acct.balance.gold == 250

    def test_credit_not_found_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        with pytest.raises(AccountNotFoundError):
            mgr.credit("ACCT-nonexistent", gold=10)

    def test_credit_negative_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        with pytest.raises(TreasuryValidationError):
            mgr.credit("ACCT-cm-sage", gold=-10)

    def test_credit_updates_timestamp(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        acct1 = mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct2 = mgr.credit("ACCT-cm-sage", gold=1)
        assert acct2.updated_at >= acct1.updated_at


# ─── Debit ───────────────────────────────────────────────────


class TestDebit:
    """Tests for debit operations."""

    def test_debit_gold(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.debit("ACCT-cm-sage", gold=50)
        assert acct.balance.gold == 150

    def test_debit_all_gold(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.debit("ACCT-cm-sage", gold=200)
        assert acct.balance.gold == 0

    def test_debit_insufficient_gold_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        with pytest.raises(InsufficientFundsError) as exc_info:
            mgr.debit("ACCT-cm-sage", gold=201)
        assert exc_info.value.tier == "gold"
        assert exc_info.value.requested == 201
        assert exc_info.value.available == 200

    def test_debit_insufficient_silver_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        with pytest.raises(InsufficientFundsError):
            mgr.debit("ACCT-cm-sage", silver=1)

    def test_debit_insufficient_bronze_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        with pytest.raises(InsufficientFundsError):
            mgr.debit("ACCT-cm-sage", bronze=1)

    def test_debit_not_found_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        with pytest.raises(AccountNotFoundError):
            mgr.debit("ACCT-nonexistent", gold=1)

    def test_debit_negative_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        with pytest.raises(TreasuryValidationError):
            mgr.debit("ACCT-cm-sage", gold=-1)

    def test_debit_persists(self, tmp_path):
        d = tmp_path / "treasury"
        mgr = TreasuryManager(treasury_dir=d)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.debit("ACCT-cm-sage", gold=100)

        mgr2 = TreasuryManager(treasury_dir=d)
        acct = mgr2.get("ACCT-cm-sage")
        assert acct.balance.gold == 100


# ─── Transfer ────────────────────────────────────────────────


class TestTransfer:
    """Tests for transfer operations."""

    def test_basic_transfer(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        from_acct, to_acct = mgr.transfer(
            "ACCT-cm-sage", "ACCT-cm-logic", gold=50
        )
        assert from_acct.balance.gold == 150
        assert to_acct.balance.gold == 250

    def test_transfer_multiple_tiers(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create(
            "ACCT-cm-sage", "council_member", "Sage",
            default_balance={"gold": 100, "silver": 50, "bronze": 200},
        )
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        from_acct, to_acct = mgr.transfer(
            "ACCT-cm-sage", "ACCT-cm-logic",
            gold=10, silver=5, bronze=20,
        )
        assert from_acct.balance.gold == 90
        assert from_acct.balance.silver == 45
        assert from_acct.balance.bronze == 180
        assert to_acct.balance.gold == 210
        assert to_acct.balance.silver == 5
        assert to_acct.balance.bronze == 20

    def test_transfer_insufficient_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")
        with pytest.raises(InsufficientFundsError):
            mgr.transfer("ACCT-cm-sage", "ACCT-cm-logic", gold=500)

    def test_transfer_same_account_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        with pytest.raises(TreasuryValidationError):
            mgr.transfer("ACCT-cm-sage", "ACCT-cm-sage", gold=10)

    def test_transfer_persists(self, tmp_path):
        d = tmp_path / "treasury"
        mgr = TreasuryManager(treasury_dir=d)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")
        mgr.transfer("ACCT-cm-sage", "ACCT-gov-jericho", gold=50)

        mgr2 = TreasuryManager(treasury_dir=d)
        sage = mgr2.get("ACCT-cm-sage")
        gov = mgr2.get("ACCT-gov-jericho")
        assert sage.balance.gold == 150
        assert gov.balance.gold == 1050


# ─── Normalize ───────────────────────────────────────────────


class TestNormalize:
    """Tests for the normalize operation."""

    def test_bronze_to_silver(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create(
            "ACCT-cm-sage", "council_member", "Sage",
            default_balance={"gold": 0, "silver": 0, "bronze": 150},
        )
        acct = mgr.normalize("ACCT-cm-sage")
        assert acct.balance.bronze == 50
        assert acct.balance.silver == 1
        assert acct.balance.gold == 0

    def test_silver_to_gold(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create(
            "ACCT-cm-sage", "council_member", "Sage",
            default_balance={"gold": 0, "silver": 250, "bronze": 0},
        )
        acct = mgr.normalize("ACCT-cm-sage")
        assert acct.balance.silver == 50
        assert acct.balance.gold == 2

    def test_cascade_conversion(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        # 10000 bronze = 100 silver = 1 gold
        mgr.get_or_create(
            "ACCT-cm-sage", "council_member", "Sage",
            default_balance={"gold": 0, "silver": 0, "bronze": 10050},
        )
        acct = mgr.normalize("ACCT-cm-sage")
        assert acct.balance.bronze == 50
        assert acct.balance.silver == 0
        assert acct.balance.gold == 1

    def test_no_change_needed(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create(
            "ACCT-cm-sage", "council_member", "Sage",
            default_balance={"gold": 5, "silver": 50, "bronze": 50},
        )
        acct = mgr.normalize("ACCT-cm-sage")
        assert acct.balance.gold == 5
        assert acct.balance.silver == 50
        assert acct.balance.bronze == 50

    def test_normalize_not_found_raises(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        with pytest.raises(AccountNotFoundError):
            mgr.normalize("ACCT-nonexistent")


# ─── Initialize Defaults ────────────────────────────────────


class TestInitializeDefaults:
    """Tests for initialize_defaults."""

    def test_creates_government_and_user(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        created = mgr.initialize_defaults()
        assert len(created) == 2  # government + user

        gov = mgr.get("ACCT-gov-jericho")
        assert gov.balance.gold == 1000
        assert gov.account_type == "government"

        user = mgr.get("ACCT-user-human")
        assert user.balance.gold == 200
        assert user.account_type == "user"

    def test_creates_council_member_accounts(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")

        # Mock registry with two members
        member1 = SimpleNamespace(name="Sage")
        member2 = SimpleNamespace(name="Logic")
        registry = SimpleNamespace(
            list_members=lambda: [member1, member2]
        )

        created = mgr.initialize_defaults(registry=registry)
        # gov + user + 2 members = 4
        assert len(created) == 4

        sage = mgr.get("ACCT-cm-sage")
        assert sage.balance.gold == 200
        assert sage.account_type == "council_member"

        logic = mgr.get("ACCT-cm-logic")
        assert logic.balance.gold == 200

    def test_creates_character_accounts(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")

        char1 = SimpleNamespace(id="CH-0001", name="Atlas", status="active")
        char_mgr = SimpleNamespace(
            list_characters=lambda status=None: [char1] if status == "active" else []
        )

        created = mgr.initialize_defaults(character_manager=char_mgr)
        # gov + user + 1 character = 3
        assert len(created) == 3

        atlas = mgr.get("ACCT-ch-ch-0001")
        assert atlas.balance.gold == 200
        assert atlas.owner_name == "Atlas"

    def test_skips_existing_accounts(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")

        # First init
        mgr.initialize_defaults()
        # Credit government
        mgr.credit("ACCT-gov-jericho", gold=500)

        # Second init should skip existing
        created = mgr.initialize_defaults()
        assert len(created) == 0

        gov = mgr.get("ACCT-gov-jericho")
        assert gov.balance.gold == 1500  # preserved, not reset

    def test_full_init(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")

        member1 = SimpleNamespace(name="Sage")
        registry = SimpleNamespace(list_members=lambda: [member1])

        char1 = SimpleNamespace(id="CH-0001", name="Atlas", status="active")
        char_mgr = SimpleNamespace(
            list_characters=lambda status=None: [char1] if status == "active" else []
        )

        created = mgr.initialize_defaults(
            registry=registry, character_manager=char_mgr
        )
        # gov + user + 1 member + 1 character = 4
        assert len(created) == 4


# ─── List Accounts ───────────────────────────────────────────


class TestListAccounts:
    """Tests for list_accounts."""

    def test_list_empty(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        assert mgr.list_accounts() == []

    def test_list_all(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")
        accounts = mgr.list_accounts()
        assert len(accounts) == 2

    def test_filter_by_type(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-gov-jericho", "government", "Jericho")

        cm_accounts = mgr.list_accounts(account_type="council_member")
        assert len(cm_accounts) == 1
        assert cm_accounts[0].account_id == "ACCT-cm-sage"

        gov_accounts = mgr.list_accounts(account_type="government")
        assert len(gov_accounts) == 1

    def test_corrupt_file_skipped(self, tmp_path):
        d = tmp_path / "treasury"
        d.mkdir()
        (d / "ACCT-bad.json").write_text("not json", encoding="utf-8")
        mgr = TreasuryManager(treasury_dir=d)
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        accounts = mgr.list_accounts()
        assert len(accounts) == 1


# ─── Edge Cases ──────────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_owner_name(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        acct = mgr.get_or_create("ACCT-cm-café", "council_member", "Café")
        assert acct.owner_name == "Café"

    def test_zero_amount_credit(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.credit("ACCT-cm-sage", gold=0, silver=0, bronze=0)
        assert acct.balance.gold == 200

    def test_zero_amount_debit(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        acct = mgr.debit("ACCT-cm-sage", gold=0, silver=0, bronze=0)
        assert acct.balance.gold == 200

    def test_large_amounts(self, tmp_path):
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create(
            "ACCT-gov-jericho", "government", "Jericho",
            default_balance={"gold": 1_000_000, "silver": 0, "bronze": 0},
        )
        acct = mgr.credit("ACCT-gov-jericho", gold=999_999)
        assert acct.balance.gold == 1_999_999

    def test_full_lifecycle(self, tmp_path):
        """Create → credit → debit → transfer → normalize lifecycle."""
        mgr = TreasuryManager(treasury_dir=tmp_path / "treasury")
        mgr.get_or_create("ACCT-cm-sage", "council_member", "Sage")
        mgr.get_or_create("ACCT-cm-logic", "council_member", "Logic")

        mgr.credit("ACCT-cm-sage", bronze=250)
        mgr.debit("ACCT-cm-sage", gold=100)
        mgr.transfer("ACCT-cm-sage", "ACCT-cm-logic", gold=50)

        sage = mgr.normalize("ACCT-cm-sage")
        assert sage.balance.gold == 50
        assert sage.balance.silver == 2
        assert sage.balance.bronze == 50


# ─── Exceptions ──────────────────────────────────────────────


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_hierarchy(self):
        assert issubclass(AccountNotFoundError, TreasuryError)
        assert issubclass(InsufficientFundsError, TreasuryError)
        assert issubclass(TreasuryValidationError, TreasuryError)

    def test_account_not_found_fields(self):
        err = AccountNotFoundError("ACCT-x")
        assert err.account_id == "ACCT-x"

    def test_insufficient_funds_fields(self):
        err = InsufficientFundsError("ACCT-x", "gold", 100, 50)
        assert err.account_id == "ACCT-x"
        assert err.tier == "gold"
        assert err.requested == 100
        assert err.available == 50

    def test_validation_fields(self):
        err = TreasuryValidationError(["error1", "error2"])
        assert len(err.errors) == 2
