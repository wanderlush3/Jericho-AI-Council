"""
Tests for F-071 — Reputation Gameplay Effects.

Covers:
- Pure functions in core/reputation_effects.py
- Toggle behavior (enabled vs. disabled)
- Route integration (proposals, stores, reputation)
- Edge cases (unknown tiers, missing reputation data)
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# ─── Pure Function Tests ──────────────────────────────────────


class TestGetVoteWeightModifier(unittest.TestCase):
    """Test get_vote_weight_modifier with toggle on/off."""

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", True)
    def test_legendary_tier(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("legendary"), 1.10)

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", True)
    def test_distinguished_tier(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("distinguished"), 1.05)

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", True)
    def test_respected_tier(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("respected"), 1.00)

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", True)
    def test_neutral_tier(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("neutral"), 1.00)

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", True)
    def test_dubious_tier(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("dubious"), 0.95)

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", True)
    def test_disgraced_tier(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("disgraced"), 0.90)

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", True)
    def test_unknown_tier_returns_neutral(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("nonexistent"), 1.0)

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", False)
    def test_disabled_always_returns_one(self) -> None:
        from core.reputation_effects import get_vote_weight_modifier
        self.assertEqual(get_vote_weight_modifier("legendary"), 1.0)
        self.assertEqual(get_vote_weight_modifier("disgraced"), 1.0)


class TestGetPriceModifier(unittest.TestCase):
    """Test get_price_modifier with toggle on/off."""

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_legendary_discount(self) -> None:
        from core.reputation_effects import get_price_modifier
        self.assertEqual(get_price_modifier("legendary"), 0.85)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_distinguished_discount(self) -> None:
        from core.reputation_effects import get_price_modifier
        self.assertEqual(get_price_modifier("distinguished"), 0.90)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_respected_discount(self) -> None:
        from core.reputation_effects import get_price_modifier
        self.assertEqual(get_price_modifier("respected"), 0.95)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_neutral_no_change(self) -> None:
        from core.reputation_effects import get_price_modifier
        self.assertEqual(get_price_modifier("neutral"), 1.00)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_dubious_surcharge(self) -> None:
        from core.reputation_effects import get_price_modifier
        self.assertEqual(get_price_modifier("dubious"), 1.05)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_disgraced_surcharge(self) -> None:
        from core.reputation_effects import get_price_modifier
        self.assertEqual(get_price_modifier("disgraced"), 1.10)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", False)
    def test_disabled_always_returns_one(self) -> None:
        from core.reputation_effects import get_price_modifier
        self.assertEqual(get_price_modifier("legendary"), 1.0)
        self.assertEqual(get_price_modifier("disgraced"), 1.0)


class TestApplyPriceModifier(unittest.TestCase):
    """Test apply_price_modifier math."""

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_legendary_discount_applied(self) -> None:
        from core.reputation_effects import apply_price_modifier
        gold, silver, bronze = apply_price_modifier(100, 50, 200, "legendary")
        self.assertEqual(gold, 85)
        self.assertEqual(silver, 42)  # int(50 * 0.85) = 42
        self.assertEqual(bronze, 170)  # int(200 * 0.85) = 170

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_disgraced_surcharge_applied(self) -> None:
        from core.reputation_effects import apply_price_modifier
        gold, silver, bronze = apply_price_modifier(100, 50, 200, "disgraced")
        self.assertEqual(gold, 110)
        self.assertEqual(silver, 55)
        self.assertEqual(bronze, 220)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_neutral_no_change(self) -> None:
        from core.reputation_effects import apply_price_modifier
        gold, silver, bronze = apply_price_modifier(100, 50, 200, "neutral")
        self.assertEqual(gold, 100)
        self.assertEqual(silver, 50)
        self.assertEqual(bronze, 200)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", True)
    def test_zero_prices_stay_zero(self) -> None:
        from core.reputation_effects import apply_price_modifier
        gold, silver, bronze = apply_price_modifier(0, 0, 0, "legendary")
        self.assertEqual(gold, 0)
        self.assertEqual(silver, 0)
        self.assertEqual(bronze, 0)

    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", False)
    def test_disabled_returns_original(self) -> None:
        from core.reputation_effects import apply_price_modifier
        gold, silver, bronze = apply_price_modifier(100, 50, 200, "legendary")
        self.assertEqual(gold, 100)
        self.assertEqual(silver, 50)
        self.assertEqual(bronze, 200)


class TestCanFastTrack(unittest.TestCase):
    """Test can_fast_track with toggle on/off."""

    @patch("core.reputation_effects.REPUTATION_FAST_TRACK_ENABLED", True)
    def test_legendary_can_fast_track(self) -> None:
        from core.reputation_effects import can_fast_track
        self.assertTrue(can_fast_track("legendary"))

    @patch("core.reputation_effects.REPUTATION_FAST_TRACK_ENABLED", True)
    def test_distinguished_can_fast_track(self) -> None:
        from core.reputation_effects import can_fast_track
        self.assertTrue(can_fast_track("distinguished"))

    @patch("core.reputation_effects.REPUTATION_FAST_TRACK_ENABLED", True)
    def test_respected_cannot_fast_track(self) -> None:
        from core.reputation_effects import can_fast_track
        self.assertFalse(can_fast_track("respected"))

    @patch("core.reputation_effects.REPUTATION_FAST_TRACK_ENABLED", True)
    def test_neutral_cannot_fast_track(self) -> None:
        from core.reputation_effects import can_fast_track
        self.assertFalse(can_fast_track("neutral"))

    @patch("core.reputation_effects.REPUTATION_FAST_TRACK_ENABLED", True)
    def test_disgraced_cannot_fast_track(self) -> None:
        from core.reputation_effects import can_fast_track
        self.assertFalse(can_fast_track("disgraced"))

    @patch("core.reputation_effects.REPUTATION_FAST_TRACK_ENABLED", False)
    def test_disabled_nobody_can_fast_track(self) -> None:
        from core.reputation_effects import can_fast_track
        self.assertFalse(can_fast_track("legendary"))
        self.assertFalse(can_fast_track("distinguished"))


class TestCanAuthorProposals(unittest.TestCase):
    """Test can_author_proposals restriction."""

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", True)
    def test_disgraced_cannot_author(self) -> None:
        from core.reputation_effects import can_author_proposals
        self.assertFalse(can_author_proposals("disgraced"))

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", True)
    def test_dubious_can_author(self) -> None:
        from core.reputation_effects import can_author_proposals
        self.assertTrue(can_author_proposals("dubious"))

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", True)
    def test_neutral_can_author(self) -> None:
        from core.reputation_effects import can_author_proposals
        self.assertTrue(can_author_proposals("neutral"))

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", True)
    def test_legendary_can_author(self) -> None:
        from core.reputation_effects import can_author_proposals
        self.assertTrue(can_author_proposals("legendary"))

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", False)
    def test_disabled_disgraced_can_author(self) -> None:
        from core.reputation_effects import can_author_proposals
        self.assertTrue(can_author_proposals("disgraced"))


class TestCanOpenStores(unittest.TestCase):
    """Test can_open_stores restriction."""

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", True)
    def test_disgraced_cannot_open(self) -> None:
        from core.reputation_effects import can_open_stores
        self.assertFalse(can_open_stores("disgraced"))

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", True)
    def test_dubious_can_open(self) -> None:
        from core.reputation_effects import can_open_stores
        self.assertTrue(can_open_stores("dubious"))

    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", False)
    def test_disabled_disgraced_can_open(self) -> None:
        from core.reputation_effects import can_open_stores
        self.assertTrue(can_open_stores("disgraced"))


class TestGetFastTrackRejectionPenalty(unittest.TestCase):
    """Test fast-track rejection penalty value."""

    def test_returns_configured_penalty(self) -> None:
        from core.reputation_effects import get_fast_track_rejection_penalty
        penalty = get_fast_track_rejection_penalty()
        self.assertEqual(penalty, -4)

    def test_penalty_is_negative(self) -> None:
        from core.reputation_effects import get_fast_track_rejection_penalty
        self.assertLess(get_fast_track_rejection_penalty(), 0)


class TestGetEntityTier(unittest.TestCase):
    """Test get_entity_tier helper."""

    def test_returns_neutral_when_manager_unavailable(self) -> None:
        from core.reputation_effects import get_entity_tier
        # Pass a mock that raises
        mock_mgr = MagicMock()
        mock_mgr.get_score.side_effect = Exception("boom")
        tier = get_entity_tier("member:Test", reputation_manager=mock_mgr)
        self.assertEqual(tier, "neutral")

    def test_returns_tier_from_score(self) -> None:
        from core.reputation_effects import get_entity_tier
        mock_score = MagicMock()
        mock_score.tier = "legendary"
        mock_mgr = MagicMock()
        mock_mgr.get_score.return_value = mock_score
        tier = get_entity_tier("member:Hero", reputation_manager=mock_mgr)
        self.assertEqual(tier, "legendary")


# ─── StoreManager.purchase() Price Modifier Tests ─────────────


class TestStorePurchasePriceModifier(unittest.TestCase):
    """Test StoreManager.purchase with F-071 price_modifier parameter."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.stores_dir = Path(self.tmp) / "stores"
        self.stores_dir.mkdir()
        self.treasury_dir = Path(self.tmp) / "treasury"
        self.treasury_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _create_active_store(self) -> Any:
        from core.stores import StoreManager, StoreItem
        mgr = StoreManager(self.stores_dir)
        store = mgr.create(
            "Test Shop", "A test store", author="Tester",
            store_type="general",
        )
        item = StoreItem.create("ITEM-0001", price_gold=100, price_silver=50)
        mgr.add_inventory_item(store.id, item)
        mgr.update_status(store.id, "active")
        return mgr

    def _setup_treasury(self) -> Any:
        from core.treasury import TreasuryManager
        from config.settings import TAX_GOVERNMENT_ACCOUNT_ID
        tmgr = TreasuryManager(self.treasury_dir)
        tmgr.get_or_create("buyer", "user", "Buyer",
                           default_balance={"gold": 1000, "silver": 500, "bronze": 0})
        tmgr.get_or_create(TAX_GOVERNMENT_ACCOUNT_ID, "government", "Government")
        return tmgr

    def test_purchase_default_modifier(self) -> None:
        """Without modifier, buyer pays full price."""
        mgr = self._create_active_store()
        tmgr = self._setup_treasury()
        store = mgr.list_stores()[0]

        result = mgr.purchase(
            store.id, "ITEM-0001", "buyer", tmgr,
        )
        # Default modifier = 1.0, so adjusted price = listed price
        self.assertEqual(result["adjusted_price"]["gold"], 100)
        self.assertEqual(result["adjusted_price"]["silver"], 50)

    def test_purchase_discount_modifier(self) -> None:
        """Legendary buyer gets 15% discount."""
        mgr = self._create_active_store()
        tmgr = self._setup_treasury()
        store = mgr.list_stores()[0]

        result = mgr.purchase(
            store.id, "ITEM-0001", "buyer", tmgr,
            price_modifier=0.85,
        )
        self.assertEqual(result["adjusted_price"]["gold"], 85)
        self.assertEqual(result["adjusted_price"]["silver"], 42)  # int(50*0.85)

    def test_purchase_surcharge_modifier(self) -> None:
        """Disgraced buyer pays 10% surcharge."""
        mgr = self._create_active_store()
        tmgr = self._setup_treasury()
        store = mgr.list_stores()[0]

        result = mgr.purchase(
            store.id, "ITEM-0001", "buyer", tmgr,
            price_modifier=1.10,
        )
        self.assertEqual(result["adjusted_price"]["gold"], 110)
        self.assertEqual(result["adjusted_price"]["silver"], 55)


# ─── Reputation Hooks Fast-Track Tests ────────────────────────


class TestOnProposalDecidedFastTrack(unittest.TestCase):
    """Test on_proposal_decided with fast_tracked flag."""

    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        self.rep_dir = Path(self.tmp) / "reputation"
        self.rep_dir.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rejected_normal_uses_default_penalty(self) -> None:
        """Non-fast-tracked rejection uses default penalty (-2)."""
        from core.reputation import ReputationManager
        from core.reputation_hooks import on_proposal_decided

        mgr = ReputationManager(self.rep_dir, decay_enabled=False)
        mock_tally = MagicMock()
        mock_tally.approved = False

        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_proposal_decided("P-0001", mock_tally, "TestAuthor")

        score = mgr.get_score("member:TestAuthor")
        self.assertEqual(score.raw_score, -2)  # default penalty

    def test_rejected_fast_tracked_uses_enhanced_penalty(self) -> None:
        """Fast-tracked rejection uses enhanced penalty (-4)."""
        from core.reputation import ReputationManager
        from core.reputation_hooks import on_proposal_decided

        mgr = ReputationManager(self.rep_dir, decay_enabled=False)
        mock_tally = MagicMock()
        mock_tally.approved = False

        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_proposal_decided("P-0002", mock_tally, "TestAuthor", fast_tracked=True)

        score = mgr.get_score("member:TestAuthor")
        self.assertEqual(score.raw_score, -4)  # enhanced penalty

    def test_approved_fast_tracked_normal_reward(self) -> None:
        """Approved fast-tracked proposal gets normal reward."""
        from core.reputation import ReputationManager
        from core.reputation_hooks import on_proposal_decided

        mgr = ReputationManager(self.rep_dir, decay_enabled=False)
        mock_tally = MagicMock()
        mock_tally.approved = True

        with patch("core.reputation_hooks._get_mgr", return_value=mgr):
            on_proposal_decided("P-0003", mock_tally, "TestAuthor", fast_tracked=True)

        score = mgr.get_score("member:TestAuthor")
        self.assertEqual(score.raw_score, 5)  # default approved reward


# ─── Route Integration Tests (Proposals) ─────────────────────


class TestProposalRouteDisgracedRestriction(unittest.TestCase):
    """Test that disgraced entities are blocked from creating proposals."""

    def test_disgraced_author_returns_403(self) -> None:
        """POST /api/proposals returns 403 when author is disgraced."""
        from core.routes.proposals import api_proposal_create
        from fastapi import HTTPException

        body = {
            "author": "BadActor",
            "title": "Evil Plan",
            "description": "A terrible proposal",
            "category": "general",
        }

        with patch("core.reputation_effects.get_entity_tier", return_value="disgraced"):
            with self.assertRaises(HTTPException) as ctx:
                api_proposal_create(body)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("disgraced", ctx.exception.detail)

    def test_neutral_author_allowed(self) -> None:
        """POST /api/proposals proceeds normally for neutral-tier author."""
        from core.routes.proposals import api_proposal_create

        body = {
            "author": "Sage",
            "title": "Good Plan",
            "description": "A great proposal",
            "category": "general",
        }

        # Mock all the deep dependencies away
        mock_pmgr = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.id = "P-0001"
        mock_proposal.to_dict.return_value = {"id": "P-0001", "status": "open"}
        mock_pmgr.create.return_value = mock_proposal
        mock_pmgr.update_status.return_value = mock_proposal

        with patch("core.reputation_effects.get_entity_tier", return_value="neutral"), \
             patch("core.routes.proposals.get_proposal_manager", return_value=mock_pmgr), \
             patch("core.reputation_hooks.on_proposal_authored"), \
             patch("core.routes.proposals.get_registry") as mock_reg, \
             patch("core.routes.proposals._make_discussion_manager") as mock_dmgr:
            mock_reg.return_value.list_names.return_value = ["Sage"]
            mock_disc = MagicMock()
            mock_disc.to_dict.return_value = {"id": "P-0001"}
            mock_dmgr.return_value.create_discussion.return_value = mock_disc

            result = api_proposal_create(body)
            self.assertEqual(result["id"], "P-0001")
            self.assertFalse(result["fast_tracked"])


class TestProposalFastTrackRoute(unittest.TestCase):
    """Test fast-track proposal creation."""

    def test_fast_track_skips_discussion(self) -> None:
        """Fast-tracked proposal returns None discussion."""
        from core.routes.proposals import api_proposal_create

        body = {
            "author": "Hero",
            "title": "Urgent Plan",
            "description": "Needs quick action",
            "category": "general",
            "fast_track": True,
        }

        mock_pmgr = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.id = "P-0002"
        mock_proposal.to_dict.return_value = {"id": "P-0002", "status": "open_to_review"}
        mock_pmgr.create.return_value = mock_proposal
        mock_pmgr.update_status.return_value = mock_proposal

        with patch("core.reputation_effects.get_entity_tier", return_value="legendary"), \
             patch("core.routes.proposals.get_proposal_manager", return_value=mock_pmgr), \
             patch("core.reputation_hooks.on_proposal_authored"):

            result = api_proposal_create(body)
            self.assertIsNone(result["discussion"])
            self.assertTrue(result["fast_tracked"])

    def test_fast_track_downgraded_for_ineligible(self) -> None:
        """Ineligible author's fast_track is silently downgraded."""
        from core.routes.proposals import api_proposal_create

        body = {
            "author": "Normal",
            "title": "Plan",
            "description": "Normal proposal",
            "category": "general",
            "fast_track": True,
        }

        mock_pmgr = MagicMock()
        mock_proposal = MagicMock()
        mock_proposal.id = "P-0003"
        mock_proposal.to_dict.return_value = {"id": "P-0003", "status": "open"}
        mock_pmgr.create.return_value = mock_proposal
        mock_pmgr.update_status.return_value = mock_proposal

        with patch("core.reputation_effects.get_entity_tier", return_value="neutral"), \
             patch("core.routes.proposals.get_proposal_manager", return_value=mock_pmgr), \
             patch("core.reputation_hooks.on_proposal_authored"), \
             patch("core.routes.proposals.get_registry") as mock_reg, \
             patch("core.routes.proposals._make_discussion_manager") as mock_dmgr:
            mock_reg.return_value.list_names.return_value = ["Sage"]
            mock_disc = MagicMock()
            mock_disc.to_dict.return_value = {"id": "P-0003"}
            mock_dmgr.return_value.create_discussion.return_value = mock_disc

            result = api_proposal_create(body)
            self.assertFalse(result["fast_tracked"])
            self.assertIsNotNone(result["discussion"])


# ─── Route Integration Tests (Stores) ────────────────────────


class TestStoreRouteDisgracedRestriction(unittest.TestCase):
    """Test that disgraced entities cannot create stores."""

    def test_disgraced_author_returns_403(self) -> None:
        """POST /api/stores returns 403 when author is disgraced."""
        from core.routes.stores import api_store_create
        from fastapi import HTTPException

        body = {
            "name": "Shady Shop",
            "description": "Totally legit",
            "author": "BadActor",
        }

        with patch("core.reputation_effects.get_entity_tier", return_value="disgraced"):
            with self.assertRaises(HTTPException) as ctx:
                api_store_create(body)
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("disgraced", ctx.exception.detail)


# ─── Reputation Effects Endpoint Tests ────────────────────────


class TestReputationEffectsEndpoint(unittest.TestCase):
    """Test GET /api/reputation/{entity_id}/effects."""

    def test_effects_endpoint_returns_all_fields(self) -> None:
        """The effects endpoint returns all expected gameplay effect fields."""
        from core.routes.reputation import get_entity_effects

        mock_score = MagicMock()
        mock_score.tier = "distinguished"
        mock_score.tier_emoji = "🏆"
        mock_score.decayed_score = 120.5

        mock_mgr = MagicMock()
        mock_mgr.get_score.return_value = mock_score

        with patch("core.routes.reputation.get_reputation_manager", return_value=mock_mgr):
            result = get_entity_effects("member:Sage")

        self.assertEqual(result["entity_id"], "member:Sage")
        self.assertEqual(result["tier"], "distinguished")
        effects = result["effects"]
        self.assertIn("vote_weight_modifier", effects)
        self.assertIn("price_modifier", effects)
        self.assertIn("can_author_proposals", effects)
        self.assertIn("can_open_stores", effects)
        self.assertIn("can_fast_track", effects)
        self.assertIn("vote_weight_enabled", effects)
        self.assertIn("store_prices_enabled", effects)
        self.assertIn("restrictions_enabled", effects)
        self.assertIn("fast_track_enabled", effects)

    def test_effects_for_disgraced_entity(self) -> None:
        """Disgraced entity sees restrictions in effects response."""
        from core.routes.reputation import get_entity_effects

        mock_score = MagicMock()
        mock_score.tier = "disgraced"
        mock_score.tier_emoji = "🚫"
        mock_score.decayed_score = -50.0

        mock_mgr = MagicMock()
        mock_mgr.get_score.return_value = mock_score

        with patch("core.routes.reputation.get_reputation_manager", return_value=mock_mgr):
            result = get_entity_effects("member:BadActor")

        effects = result["effects"]
        self.assertFalse(effects["can_author_proposals"])
        self.assertFalse(effects["can_open_stores"])
        self.assertFalse(effects["can_fast_track"])
        self.assertAlmostEqual(effects["vote_weight_modifier"], 0.90)
        self.assertAlmostEqual(effects["price_modifier"], 1.10)

    def test_effects_for_legendary_entity(self) -> None:
        """Legendary entity sees all positive effects."""
        from core.routes.reputation import get_entity_effects

        mock_score = MagicMock()
        mock_score.tier = "legendary"
        mock_score.tier_emoji = "⭐"
        mock_score.decayed_score = 250.0

        mock_mgr = MagicMock()
        mock_mgr.get_score.return_value = mock_score

        with patch("core.routes.reputation.get_reputation_manager", return_value=mock_mgr):
            result = get_entity_effects("member:Hero")

        effects = result["effects"]
        self.assertTrue(effects["can_author_proposals"])
        self.assertTrue(effects["can_open_stores"])
        self.assertTrue(effects["can_fast_track"])
        self.assertAlmostEqual(effects["vote_weight_modifier"], 1.10)
        self.assertAlmostEqual(effects["price_modifier"], 0.85)


# ─── Settings Constants Tests ─────────────────────────────────


class TestSettingsConstants(unittest.TestCase):
    """Verify F-071 settings are present and sane."""

    def test_vote_weight_modifiers_exist(self) -> None:
        from config.settings import REPUTATION_VOTE_WEIGHT_MODIFIERS
        self.assertIn("legendary", REPUTATION_VOTE_WEIGHT_MODIFIERS)
        self.assertIn("disgraced", REPUTATION_VOTE_WEIGHT_MODIFIERS)
        # All values should be between 0.5 and 1.5
        for v in REPUTATION_VOTE_WEIGHT_MODIFIERS.values():
            self.assertGreaterEqual(v, 0.5)
            self.assertLessEqual(v, 1.5)

    def test_price_modifiers_exist(self) -> None:
        from config.settings import REPUTATION_PRICE_MODIFIERS
        self.assertIn("legendary", REPUTATION_PRICE_MODIFIERS)
        self.assertIn("disgraced", REPUTATION_PRICE_MODIFIERS)
        for v in REPUTATION_PRICE_MODIFIERS.values():
            self.assertGreaterEqual(v, 0.5)
            self.assertLessEqual(v, 1.5)

    def test_fast_track_tiers_exist(self) -> None:
        from config.settings import REPUTATION_FAST_TRACK_TIERS
        self.assertIn("legendary", REPUTATION_FAST_TRACK_TIERS)
        self.assertIn("distinguished", REPUTATION_FAST_TRACK_TIERS)
        self.assertNotIn("neutral", REPUTATION_FAST_TRACK_TIERS)

    def test_toggles_exist(self) -> None:
        from config.settings import (
            REPUTATION_VOTE_WEIGHT_ENABLED,
            REPUTATION_STORE_PRICES_ENABLED,
            REPUTATION_FAST_TRACK_ENABLED,
            REPUTATION_RESTRICTIONS_ENABLED,
        )
        self.assertIsInstance(REPUTATION_VOTE_WEIGHT_ENABLED, bool)
        self.assertIsInstance(REPUTATION_STORE_PRICES_ENABLED, bool)
        self.assertIsInstance(REPUTATION_FAST_TRACK_ENABLED, bool)
        self.assertIsInstance(REPUTATION_RESTRICTIONS_ENABLED, bool)

    def test_fast_track_rejection_penalty(self) -> None:
        from config.settings import REPUTATION_FAST_TRACK_REJECTION_PENALTY
        self.assertEqual(REPUTATION_FAST_TRACK_REJECTION_PENALTY, -4)
        self.assertLess(REPUTATION_FAST_TRACK_REJECTION_PENALTY, -2)


# ─── All Toggles Disabled Integration ─────────────────────────


class TestAllTogglesDisabled(unittest.TestCase):
    """When all toggles are off, all effects return neutral values."""

    @patch("core.reputation_effects.REPUTATION_VOTE_WEIGHT_ENABLED", False)
    @patch("core.reputation_effects.REPUTATION_STORE_PRICES_ENABLED", False)
    @patch("core.reputation_effects.REPUTATION_FAST_TRACK_ENABLED", False)
    @patch("core.reputation_effects.REPUTATION_RESTRICTIONS_ENABLED", False)
    def test_all_effects_neutral(self) -> None:
        from core.reputation_effects import (
            get_vote_weight_modifier,
            get_price_modifier,
            can_fast_track,
            can_author_proposals,
            can_open_stores,
        )

        for tier in ("legendary", "distinguished", "respected",
                      "neutral", "dubious", "disgraced"):
            self.assertEqual(get_vote_weight_modifier(tier), 1.0,
                             f"vote weight should be 1.0 for {tier}")
            self.assertEqual(get_price_modifier(tier), 1.0,
                             f"price modifier should be 1.0 for {tier}")
            self.assertFalse(can_fast_track(tier),
                             f"fast track should be False for {tier}")
            self.assertTrue(can_author_proposals(tier),
                            f"can_author should be True for {tier}")
            self.assertTrue(can_open_stores(tier),
                            f"can_open should be True for {tier}")


if __name__ == "__main__":
    unittest.main()
