"""
Tests for the Reputation System (F-069).

Covers:
- ReputationEvent creation, serialization, validation
- ReputationScore construction and tier assignment
- ReputationManager: record, score, events, leaderboard
- Decay factor mechanics
- Tier boundary testing
- Default reputation stance / perceived tier
- Thread-safety (concurrent recording)
- Storage: JSONL roundtrip, corrupt file handling
- API endpoints via TestClient
"""

from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from core.reputation import (
    REPUTATION_DEFAULT_POINTS,
    REPUTATION_EVENT_TYPES,
    REPUTATION_TIERS,
    VALID_DEFAULT_STANCES,
    ReputationError,
    ReputationEvent,
    ReputationManager,
    ReputationScore,
    ReputationValidationError,
    tier_emoji,
    tier_for_score,
)


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def rep_dir(tmp_path: Path) -> Path:
    d = tmp_path / "reputation"
    d.mkdir()
    return d


@pytest.fixture
def mgr(rep_dir: Path) -> ReputationManager:
    return ReputationManager(rep_dir, decay_enabled=False)


@pytest.fixture
def mgr_decay(rep_dir: Path) -> ReputationManager:
    return ReputationManager(
        rep_dir,
        decay_enabled=True,
        decay_half_life_days=120,
        decay_min_factor=0.1,
    )


# ═══════════════════════════════════════════════════════════════
# TestReputationEvent
# ═══════════════════════════════════════════════════════════════


class TestReputationEvent:

    def test_create_fills_timestamp(self):
        evt = ReputationEvent.create(
            id="REP-000001",
            entity_id="member:sage",
            event_type="vote_cast",
            points=2,
            reason="Voted on P-0001",
        )
        assert evt.id == "REP-000001"
        assert evt.entity_id == "member:sage"
        assert evt.event_type == "vote_cast"
        assert evt.points == 2
        assert evt.timestamp  # auto-filled

    def test_to_dict_roundtrip(self):
        evt = ReputationEvent.create(
            id="REP-000002",
            entity_id="character:ch-0001",
            event_type="gift_given",
            points=5,
            reason="Gifted sword",
            source_id="ITEM-0003",
        )
        d = evt.to_dict()
        restored = ReputationEvent.from_dict(d)
        assert restored.id == evt.id
        assert restored.entity_id == evt.entity_id
        assert restored.event_type == evt.event_type
        assert restored.points == evt.points
        assert restored.reason == evt.reason
        assert restored.source_id == evt.source_id
        assert restored.timestamp == evt.timestamp

    def test_from_dict_defaults(self):
        evt = ReputationEvent.from_dict({
            "id": "REP-000003",
            "entity_id": "member:logic",
            "event_type": "custom",
            "points": -5,
        })
        assert evt.reason == ""
        assert evt.source_id == ""
        assert evt.timestamp == ""

    def test_frozen(self):
        evt = ReputationEvent.create(
            id="REP-000004",
            entity_id="member:sage",
            event_type="custom",
            points=0,
        )
        with pytest.raises(AttributeError):
            evt.points = 999  # type: ignore

    def test_negative_points(self):
        evt = ReputationEvent.create(
            id="REP-000005",
            entity_id="member:sage",
            event_type="proposal_rejected",
            points=-2,
        )
        assert evt.points == -2


# ═══════════════════════════════════════════════════════════════
# TestReputationScore
# ═══════════════════════════════════════════════════════════════


class TestReputationScore:

    def test_basic_score(self):
        s = ReputationScore(
            entity_id="member:sage",
            raw_score=55,
            decayed_score=52.3,
            tier="respected",
            tier_emoji="✨",
            event_count=10,
            last_event_at="2026-01-01T00:00:00+00:00",
        )
        assert s.entity_id == "member:sage"
        assert s.raw_score == 55
        assert s.decayed_score == 52.3
        assert s.tier == "respected"
        assert s.event_count == 10

    def test_to_dict(self):
        s = ReputationScore(
            entity_id="member:logic",
            raw_score=0,
            decayed_score=0.0,
            tier="neutral",
            tier_emoji="👤",
            event_count=0,
        )
        d = s.to_dict()
        assert d["entity_id"] == "member:logic"
        assert d["tier"] == "neutral"

    def test_zero_score(self):
        s = ReputationScore(
            entity_id="member:x",
            raw_score=0,
            decayed_score=0.0,
            tier="neutral",
            tier_emoji="👤",
            event_count=0,
        )
        assert s.tier == "neutral"

    def test_negative_score(self):
        s = ReputationScore(
            entity_id="member:y",
            raw_score=-30,
            decayed_score=-30.0,
            tier="disgraced",
            tier_emoji="🚫",
            event_count=5,
        )
        assert s.tier == "disgraced"


# ═══════════════════════════════════════════════════════════════
# TestTierAssignment
# ═══════════════════════════════════════════════════════════════


class TestTierAssignment:

    def test_legendary(self):
        name, emoji = tier_for_score(200)
        assert name == "legendary"
        name2, _ = tier_for_score(500)
        assert name2 == "legendary"

    def test_distinguished(self):
        name, _ = tier_for_score(100)
        assert name == "distinguished"
        name2, _ = tier_for_score(199)
        assert name2 == "distinguished"

    def test_respected(self):
        name, _ = tier_for_score(50)
        assert name == "respected"
        name2, _ = tier_for_score(99)
        assert name2 == "respected"

    def test_neutral(self):
        name, _ = tier_for_score(0)
        assert name == "neutral"
        name2, _ = tier_for_score(49)
        assert name2 == "neutral"

    def test_dubious(self):
        name, _ = tier_for_score(-1)
        assert name == "dubious"
        name2, _ = tier_for_score(-25)
        assert name2 == "dubious"

    def test_disgraced(self):
        name, _ = tier_for_score(-26)
        assert name == "disgraced"
        name2, _ = tier_for_score(-1000)
        assert name2 == "disgraced"


# ═══════════════════════════════════════════════════════════════
# TestTierEmoji
# ═══════════════════════════════════════════════════════════════


class TestTierEmoji:

    def test_known_tiers(self):
        assert tier_emoji("legendary") == "⭐"
        assert tier_emoji("neutral") == "👤"
        assert tier_emoji("disgraced") == "🚫"

    def test_unknown_tier(self):
        assert tier_emoji("unknown") == "👤"


# ═══════════════════════════════════════════════════════════════
# TestReputationManager
# ═══════════════════════════════════════════════════════════════


class TestReputationManager:

    def test_record_event_creates_file(self, mgr: ReputationManager):
        evt = mgr.record_event("member:sage", "vote_cast", reason="Voted")
        assert evt.id == "REP-000001"
        assert evt.entity_id == "member:sage"
        assert evt.points == 2  # default for vote_cast

        # File should exist
        filepath = mgr.directory / "member_sage.jsonl"
        assert filepath.exists()
        lines = filepath.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1

    def test_record_event_with_custom_points(self, mgr: ReputationManager):
        evt = mgr.record_event(
            "member:sage", "custom", points=-10,
            reason="Penalty for misconduct",
        )
        assert evt.points == -10
        assert evt.event_type == "custom"

    def test_record_event_validation_empty_entity(self, mgr: ReputationManager):
        with pytest.raises(ReputationValidationError, match="entity_id"):
            mgr.record_event("", "vote_cast")

    def test_record_event_validation_bad_type(self, mgr: ReputationManager):
        with pytest.raises(ReputationValidationError, match="Unknown event_type"):
            mgr.record_event("member:sage", "invalid_type")

    def test_get_score_no_events(self, mgr: ReputationManager):
        score = mgr.get_score("member:sage")
        assert score.raw_score == 0
        assert score.decayed_score == 0.0
        assert score.tier == "neutral"
        assert score.event_count == 0

    def test_get_score_with_events(self, mgr: ReputationManager):
        mgr.record_event("member:sage", "vote_cast", reason="Vote 1")
        mgr.record_event("member:sage", "vote_cast", reason="Vote 2")
        mgr.record_event("member:sage", "proposal_authored", reason="P-001")
        score = mgr.get_score("member:sage")
        # 2 + 2 + 10 = 14
        assert score.raw_score == 14
        assert score.event_count == 3
        assert score.tier == "neutral"  # 14 < 50

    def test_get_events_ordering(self, mgr: ReputationManager):
        mgr.record_event("member:sage", "vote_cast", reason="First")
        mgr.record_event("member:sage", "gift_given", reason="Second")
        events = mgr.get_events("member:sage")
        # Most recent first
        assert events[0].reason == "Second"
        assert events[1].reason == "First"

    def test_get_events_limit(self, mgr: ReputationManager):
        for i in range(10):
            mgr.record_event("member:sage", "vote_cast", reason=f"Vote {i}")
        events = mgr.get_events("member:sage", limit=3)
        assert len(events) == 3

    def test_get_leaderboard(self, mgr: ReputationManager):
        # Sage: 14 points
        mgr.record_event("member:sage", "proposal_authored")
        mgr.record_event("member:sage", "vote_cast")
        mgr.record_event("member:sage", "vote_cast")
        # Logic: 5 points
        mgr.record_event("member:logic", "proposal_approved")

        board = mgr.get_leaderboard()
        assert len(board) == 2
        assert board[0].entity_id == "member:sage"
        assert board[1].entity_id == "member:logic"

    def test_leaderboard_limit(self, mgr: ReputationManager):
        for i in range(5):
            mgr.record_event(f"member:m{i}", "vote_cast")
        board = mgr.get_leaderboard(limit=3)
        assert len(board) == 3

    def test_sequential_ids(self, mgr: ReputationManager):
        e1 = mgr.record_event("member:sage", "vote_cast")
        e2 = mgr.record_event("member:logic", "vote_cast")
        e3 = mgr.record_event("member:sage", "gift_given")
        assert e1.id == "REP-000001"
        assert e2.id == "REP-000002"
        assert e3.id == "REP-000003"

    def test_default_points_lookup(self, mgr: ReputationManager):
        evt = mgr.record_event("member:sage", "proposal_authored")
        assert evt.points == REPUTATION_DEFAULT_POINTS["proposal_authored"]

    def test_repr(self, mgr: ReputationManager):
        r = repr(mgr)
        assert "ReputationManager" in r
        assert "decay=off" in r


# ═══════════════════════════════════════════════════════════════
# TestDecayFactor
# ═══════════════════════════════════════════════════════════════


class TestDecayFactor:

    def test_fresh_event_no_decay(self, mgr_decay: ReputationManager):
        now = datetime.now(timezone.utc).isoformat()
        factor = mgr_decay._decay_factor(now)
        assert factor >= 0.99  # basically 1.0

    def test_aged_event_decays(self, mgr_decay: ReputationManager):
        # 120 days ago → factor should be ~0.5
        old = (datetime.now(timezone.utc) - timedelta(days=120)).isoformat()
        factor = mgr_decay._decay_factor(old)
        assert 0.45 <= factor <= 0.55

    def test_very_old_event_hits_floor(self, mgr_decay: ReputationManager):
        # 1000 days ago → should hit min_factor
        ancient = (datetime.now(timezone.utc) - timedelta(days=1000)).isoformat()
        factor = mgr_decay._decay_factor(ancient)
        assert factor == 0.1

    def test_decay_disabled(self, mgr: ReputationManager):
        old = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()
        factor = mgr._decay_factor(old)
        assert factor == 1.0  # decay disabled

    def test_empty_timestamp(self, mgr_decay: ReputationManager):
        assert mgr_decay._decay_factor("") == 1.0

    def test_invalid_timestamp(self, mgr_decay: ReputationManager):
        assert mgr_decay._decay_factor("not-a-date") == 1.0

    def test_decayed_score_calculation(self, mgr_decay: ReputationManager):
        # Record event, score should include decay
        evt = mgr_decay.record_event("member:sage", "proposal_authored")
        score = mgr_decay.get_score("member:sage")
        # Fresh event: decay factor ≈ 1.0
        assert score.decayed_score > 9.5  # 10 * ~1.0


# ═══════════════════════════════════════════════════════════════
# TestDefaultReputationStance
# ═══════════════════════════════════════════════════════════════


class TestDefaultReputationStance:

    def test_perceived_tier_with_events(self, mgr: ReputationManager):
        # Record enough events to reach "respected"
        for _ in range(5):
            mgr.record_event("member:logic", "proposal_authored")
        # 5 * 10 = 50 → respected
        tier, emoji = mgr.get_perceived_tier(
            "Sage", "member:logic",
            default_stances={"sage": "dubious"},
        )
        assert tier == "respected"

    def test_perceived_tier_no_events_uses_stance(self, mgr: ReputationManager):
        tier, emoji = mgr.get_perceived_tier(
            "Drift", "member:logic",
            default_stances={"drift": "dubious"},
        )
        assert tier == "dubious"
        assert emoji == "⚠️"

    def test_perceived_tier_no_events_no_stance_defaults_neutral(self, mgr: ReputationManager):
        tier, emoji = mgr.get_perceived_tier(
            "Unknown", "member:logic",
            default_stances={"sage": "respected"},
        )
        assert tier == "neutral"

    def test_perceived_tier_invalid_stance_defaults_neutral(self, mgr: ReputationManager):
        tier, emoji = mgr.get_perceived_tier(
            "Sage", "member:logic",
            default_stances={"sage": "invalid_stance"},
        )
        assert tier == "neutral"

    def test_perceived_tier_case_insensitive(self, mgr: ReputationManager):
        tier, _ = mgr.get_perceived_tier(
            "SAGE", "member:logic",
            default_stances={"sage": "respected"},
        )
        assert tier == "respected"

    def test_perceived_tier_no_stances_dict(self, mgr: ReputationManager):
        tier, _ = mgr.get_perceived_tier("Sage", "member:logic")
        assert tier == "neutral"


# ═══════════════════════════════════════════════════════════════
# TestStoragePersistence
# ═══════════════════════════════════════════════════════════════


class TestStoragePersistence:

    def test_jsonl_roundtrip(self, rep_dir: Path):
        mgr1 = ReputationManager(rep_dir, decay_enabled=False)
        mgr1.record_event("member:sage", "vote_cast", reason="Vote 1")
        mgr1.record_event("member:sage", "gift_given", reason="Gift 1")

        # Create a new manager pointing at the same dir
        mgr2 = ReputationManager(rep_dir, decay_enabled=False)
        score = mgr2.get_score("member:sage")
        assert score.raw_score == 7  # 2 + 5
        assert score.event_count == 2

    def test_corrupt_line_handled(self, rep_dir: Path):
        # Write a valid event then a corrupt line
        filepath = rep_dir / "member_sage.jsonl"
        valid = json.dumps({
            "id": "REP-000001",
            "entity_id": "member:sage",
            "event_type": "vote_cast",
            "points": 2,
        })
        filepath.write_text(valid + "\n" + "not valid json\n", encoding="utf-8")

        mgr = ReputationManager(rep_dir, decay_enabled=False)
        events = mgr.get_events("member:sage")
        assert len(events) == 1  # corrupt line skipped

    def test_empty_file_handled(self, rep_dir: Path):
        filepath = rep_dir / "member_sage.jsonl"
        filepath.write_text("", encoding="utf-8")

        mgr = ReputationManager(rep_dir, decay_enabled=False)
        score = mgr.get_score("member:sage")
        assert score.event_count == 0

    def test_entity_filename_mapping(self, mgr: ReputationManager):
        assert mgr._entity_filename("member:sage") == "member_sage"
        assert mgr._entity_filename("character:CH-0001") == "character_ch-0001"
        assert mgr._entity_filename("member:The Great Sage") == "member_the_great_sage"

    def test_entity_id_from_filename(self, mgr: ReputationManager):
        assert mgr._entity_id_from_filename("member_sage") == "member:sage"
        assert mgr._entity_id_from_filename("character_ch-0001") == "character:ch-0001"
        assert mgr._entity_id_from_filename("nounderscore") is None


# ═══════════════════════════════════════════════════════════════
# TestThreadSafety
# ═══════════════════════════════════════════════════════════════


class TestThreadSafety:

    def test_concurrent_recording(self, rep_dir: Path):
        """Multiple threads recording events should not lose events."""
        mgr = ReputationManager(rep_dir, decay_enabled=False)
        n_threads = 5
        n_events_per_thread = 10
        errors: list[str] = []

        def worker(thread_id: int):
            try:
                for i in range(n_events_per_thread):
                    mgr.record_event(
                        "member:sage",
                        "vote_cast",
                        reason=f"Thread {thread_id} event {i}",
                    )
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Errors during concurrent recording: {errors}"
        events = mgr.get_events("member:sage", limit=999)
        assert len(events) == n_threads * n_events_per_thread

    def test_concurrent_different_entities(self, rep_dir: Path):
        """Concurrent writes to different entities should not interfere."""
        mgr = ReputationManager(rep_dir, decay_enabled=False)
        entities = [f"member:member{i}" for i in range(5)]

        def worker(entity_id: str):
            for _ in range(5):
                mgr.record_event(entity_id, "vote_cast")

        threads = [threading.Thread(target=worker, args=(eid,)) for eid in entities]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        board = mgr.get_leaderboard()
        assert len(board) == 5
        for score in board:
            assert score.event_count == 5


# ═══════════════════════════════════════════════════════════════
# TestApiReputation
# ═══════════════════════════════════════════════════════════════


class TestApiReputation:
    """Test reputation API endpoints via FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def _setup_client(self, rep_dir: Path, monkeypatch):
        """Patch ReputationManager to use temp dir."""
        from core import manager_cache
        manager_cache.invalidate_all()

        test_mgr = ReputationManager(rep_dir, decay_enabled=False)
        monkeypatch.setattr(
            "core.manager_cache.get_reputation_manager",
            lambda: test_mgr,
        )
        self.mgr = test_mgr

        from core.web_api import create_app
        from fastapi.testclient import TestClient
        self.app = create_app()
        self.client = TestClient(self.app)

    def test_get_leaderboard_empty(self):
        resp = self.client.get("/api/reputation")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_entity_score_no_events(self):
        resp = self.client.get("/api/reputation/member:sage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entity_id"] == "member:sage"
        assert data["tier"] == "neutral"
        assert data["event_count"] == 0

    def test_record_event_and_score(self):
        resp = self.client.post("/api/reputation/member:sage/events", json={
            "event_type": "vote_cast",
            "reason": "Voted on P-0001",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["event"]["points"] == 2
        assert data["score"]["raw_score"] == 2

    def test_record_event_custom_points(self):
        resp = self.client.post("/api/reputation/member:sage/events", json={
            "event_type": "custom",
            "points": 100,
            "reason": "Admin award",
        })
        assert resp.status_code == 200
        assert resp.json()["event"]["points"] == 100

    def test_record_event_invalid_type(self):
        resp = self.client.post("/api/reputation/member:sage/events", json={
            "event_type": "nonexistent",
        })
        assert resp.status_code == 400

    def test_get_events_history(self):
        self.client.post("/api/reputation/member:echo/events", json={
            "event_type": "vote_cast", "reason": "Event 1",
        })
        self.client.post("/api/reputation/member:echo/events", json={
            "event_type": "gift_given", "reason": "Event 2",
        })
        resp = self.client.get("/api/reputation/member:echo/events")
        assert resp.status_code == 200
        events = resp.json()
        assert len(events) == 2
        # Most recent first
        assert events[0]["reason"] == "Event 2"

    def test_get_stances(self):
        resp = self.client.get("/api/reputation/stances")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        # Should have default stances from settings
        assert "sage" in data


# ═══════════════════════════════════════════════════════════════
# TestConstants
# ═══════════════════════════════════════════════════════════════


class TestConstants:

    def test_event_types_nonempty(self):
        assert len(REPUTATION_EVENT_TYPES) > 0

    def test_all_event_types_have_default_points(self):
        for et in REPUTATION_EVENT_TYPES:
            assert et in REPUTATION_DEFAULT_POINTS

    def test_tiers_ordered_descending(self):
        scores = [t[1] for t in REPUTATION_TIERS]
        assert scores == sorted(scores, reverse=True)

    def test_valid_default_stances_subset_of_tiers(self):
        tier_names = {t[0] for t in REPUTATION_TIERS}
        assert VALID_DEFAULT_STANCES.issubset(tier_names)
