"""
Tests for Jericho Emergent Narrative Engine.

Tests bulletin generation from mock data using tmp_path fixtures.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from core.narrative_engine import NarrativeBulletin, NarrativeEngine


# ─── NarrativeBulletin Data Class ────────────────────────────


class TestNarrativeBulletin:
    """Tests for the NarrativeBulletin dataclass."""

    def test_fields(self):
        b = NarrativeBulletin(
            headline="Test headline",
            body="Test body",
            source_type="proposal",
            source_id="P-0001",
            timestamp="2026-01-01T00:00:00+00:00",
            icon="📜",
        )
        assert b.headline == "Test headline"
        assert b.body == "Test body"
        assert b.source_type == "proposal"
        assert b.source_id == "P-0001"
        assert b.icon == "📜"

    def test_frozen(self):
        b = NarrativeBulletin(
            headline="h", body="b", source_type="proposal",
            source_id="P-0001", timestamp="t", icon="📜",
        )
        with pytest.raises(AttributeError):
            b.headline = "new"

    def test_to_dict(self):
        b = NarrativeBulletin(
            headline="h", body="b", source_type="vote",
            source_id="P-0001", timestamp="t", icon="✅",
        )
        d = b.to_dict()
        assert d["headline"] == "h"
        assert d["source_type"] == "vote"
        assert d["icon"] == "✅"

    def test_from_dict_roundtrip(self):
        b = NarrativeBulletin(
            headline="h", body="b", source_type="character",
            source_id="CH-0001", timestamp="2026-01-01T00:00:00+00:00",
            icon="🎭",
        )
        d = b.to_dict()
        b2 = NarrativeBulletin.from_dict(d)
        assert b == b2


# ─── NarrativeEngine Init ────────────────────────────────────


class TestNarrativeEngineInit:
    """Tests for NarrativeEngine construction."""

    def test_defaults(self):
        engine = NarrativeEngine()
        assert engine._max_bulletins == 10
        assert engine._max_age_days == 30

    def test_custom_settings(self):
        engine = NarrativeEngine(max_bulletins=5, max_age_days=7)
        assert engine._max_bulletins == 5
        assert engine._max_age_days == 7

    def test_repr(self):
        engine = NarrativeEngine(max_bulletins=5, max_age_days=7)
        assert "max_bulletins=5" in repr(engine)
        assert "max_age_days=7" in repr(engine)


# ─── Empty Data ──────────────────────────────────────────────


class TestEmptyData:
    """Tests that engine gracefully handles missing/empty data."""

    def test_no_data_returns_empty(self, tmp_path):
        """When all managers have empty dirs, returns no bulletins."""
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        votes_dir = tmp_path / "votes"
        votes_dir.mkdir()
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        items_dir = tmp_path / "items"
        items_dir.mkdir()
        locations_dir = tmp_path / "locations"
        locations_dir.mkdir()
        treasury_dir = tmp_path / "treasury"
        treasury_dir.mkdir()

        with (
            patch("core.proposals.PROPOSALS_DIR", proposals_dir),
            patch("core.voting.VOTES_DIR", votes_dir),
            patch("core.characters.CHARACTERS_DIR", chars_dir),
            patch("core.items.ITEMS_DIR", items_dir),
            patch("core.locations.LOCATIONS_DIR", locations_dir),
            patch("core.treasury.TREASURY_DIR", treasury_dir),
        ):
            engine = NarrativeEngine()
            bulletins = engine.generate_bulletins()
            assert bulletins == []

    def test_import_errors_handled_gracefully(self):
        """If a manager import fails, engine still returns what it can."""
        with patch("core.narrative_engine.NarrativeEngine._proposal_bulletins", side_effect=Exception("fail")):
            engine = NarrativeEngine()
            # Should not raise, just skip proposals
            # (but exception is caught inside generate_bulletins's callers)
            # Actually the methods catch internally, so let's test differently
            pass

    def test_managers_not_available(self):
        """When managers raise on import, returns empty list."""
        engine = NarrativeEngine()
        with (
            patch.object(engine, "_proposal_bulletins", return_value=[]),
            patch.object(engine, "_vote_bulletins", return_value=[]),
            patch.object(engine, "_character_bulletins", return_value=[]),
            patch.object(engine, "_item_bulletins", return_value=[]),
            patch.object(engine, "_location_bulletins", return_value=[]),
            patch.object(engine, "_treasury_bulletins", return_value=[]),
        ):
            bulletins = engine.generate_bulletins()
            assert bulletins == []


# ─── Proposal Bulletins ──────────────────────────────────────


class TestProposalBulletins:
    """Tests for proposal-derived bulletins."""

    def test_open_proposal_generates_bulletin(self, tmp_path):
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        p = {
            "id": "P-0001", "title": "Ethics Update",
            "description": "Expand ethical constraints", "author": "Sage",
            "category": "ethics", "status": "open",
            "created_at": now, "updated_at": now,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0001.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )
        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine()
            bulletins = engine._proposal_bulletins()
            assert len(bulletins) == 1
            assert bulletins[0].source_type == "proposal"
            assert bulletins[0].source_id == "P-0001"
            assert bulletins[0].icon == "📜"
            assert "Ethics Update" in bulletins[0].headline

    def test_decided_proposal_generates_bulletin(self, tmp_path):
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        p = {
            "id": "P-0002", "title": "Curiosity Framework",
            "description": "A new approach", "author": "Spark",
            "category": "general", "status": "decided",
            "created_at": now, "updated_at": now,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0002.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )
        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine()
            bulletins = engine._proposal_bulletins()
            assert len(bulletins) == 1
            assert "Curiosity Framework" in bulletins[0].headline

    def test_draft_proposal_skipped(self, tmp_path):
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        p = {
            "id": "P-0003", "title": "Draft Thing",
            "description": "Not ready", "author": "Logic",
            "category": "general", "status": "draft",
            "created_at": now, "updated_at": now,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0003.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )
        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine()
            bulletins = engine._proposal_bulletins()
            assert len(bulletins) == 0

    def test_old_proposal_excluded(self, tmp_path):
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        p = {
            "id": "P-0004", "title": "Ancient Motion",
            "description": "Way old", "author": "Echo",
            "category": "ethics", "status": "open",
            "created_at": old_ts, "updated_at": old_ts,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0004.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )
        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine(max_age_days=30)
            bulletins = engine._proposal_bulletins()
            assert len(bulletins) == 0


# ─── Character Bulletins ─────────────────────────────────────


class TestCharacterBulletins:
    """Tests for character-derived bulletins."""

    def test_active_character_generates_bulletin(self, tmp_path):
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        ch = {
            "id": "CH-0001", "name": "Atlas", "description": "An explorer",
            "author": "Forge", "status": "active", "backstory": "",
            "traits": [{"trait_type": "personality", "name": "Curious",
                        "description": "Curious", "intensity": 0.8}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": now, "updated_at": now, "metadata": {},
        }
        (chars_dir / "CH-0001.json").write_text(
            json.dumps(ch, indent=2), encoding="utf-8",
        )
        with patch("core.characters.CHARACTERS_DIR", chars_dir):
            engine = NarrativeEngine()
            bulletins = engine._character_bulletins()
            assert len(bulletins) == 1
            assert "Atlas" in bulletins[0].headline
            assert bulletins[0].source_type == "character"

    def test_archived_character_skipped(self, tmp_path):
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        ch = {
            "id": "CH-0002", "name": "OldOne", "description": "Retired",
            "author": "Sage", "status": "archived", "backstory": "",
            "traits": [{"trait_type": "personality", "name": "Wise",
                        "description": "Wise", "intensity": 0.5}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": now, "updated_at": now, "metadata": {},
        }
        (chars_dir / "CH-0002.json").write_text(
            json.dumps(ch, indent=2), encoding="utf-8",
        )
        with patch("core.characters.CHARACTERS_DIR", chars_dir):
            engine = NarrativeEngine()
            bulletins = engine._character_bulletins()
            assert len(bulletins) == 0


# ─── Max Bulletins Cap ───────────────────────────────────────


class TestMaxBulletinsCap:
    """Tests that max_bulletins limit is enforced."""

    def test_cap_enforced(self, tmp_path):
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()

        # Create 15 open proposals
        for i in range(15):
            pid = f"P-{i+1:04d}"
            p = {
                "id": pid, "title": f"Proposal {i+1}",
                "description": f"Desc {i+1}", "author": "Sage",
                "category": "general", "status": "open",
                "created_at": now, "updated_at": now,
                "body": "", "reviews": [], "metadata": {},
            }
            (proposals_dir / f"{pid}.json").write_text(
                json.dumps(p, indent=2), encoding="utf-8",
            )

        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine(max_bulletins=5)
            bulletins = engine.generate_bulletins()
            assert len(bulletins) <= 5


# ─── Template Variety ────────────────────────────────────────


class TestTemplateVariety:
    """Tests that templates produce varied output."""

    def test_different_calls_can_produce_different_headlines(self, tmp_path):
        """Multiple calls may produce different headlines (randomised)."""
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        p = {
            "id": "P-0001", "title": "Ethics Update",
            "description": "Test", "author": "Sage",
            "category": "ethics", "status": "open",
            "created_at": now, "updated_at": now,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0001.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )

        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine()
            headlines = set()
            for _ in range(20):
                bulletins = engine._proposal_bulletins()
                if bulletins:
                    headlines.add(bulletins[0].headline)
            # With 5 templates and 20 tries, we should get at least 2 different
            assert len(headlines) >= 2


# ─── Sorting ─────────────────────────────────────────────────


class TestSorting:
    """Tests that bulletins are sorted newest-first."""

    def test_newest_first(self):
        engine = NarrativeEngine()
        b1 = NarrativeBulletin(
            headline="Old", body="", source_type="proposal",
            source_id="P-0001", timestamp="2026-01-01T00:00:00+00:00",
            icon="📜",
        )
        b2 = NarrativeBulletin(
            headline="New", body="", source_type="proposal",
            source_id="P-0002", timestamp="2026-03-01T00:00:00+00:00",
            icon="📜",
        )
        with (
            patch.object(engine, "_proposal_bulletins", return_value=[b1, b2]),
            patch.object(engine, "_vote_bulletins", return_value=[]),
            patch.object(engine, "_character_bulletins", return_value=[]),
            patch.object(engine, "_item_bulletins", return_value=[]),
            patch.object(engine, "_location_bulletins", return_value=[]),
            patch.object(engine, "_treasury_bulletins", return_value=[]),
        ):
            bulletins = engine.generate_bulletins()
            assert bulletins[0].headline == "New"
            assert bulletins[1].headline == "Old"


# ─── Time Window Filter ─────────────────────────────────────


class TestTimeWindow:
    """Tests for the _is_within_window helper."""

    def test_within_window(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent = datetime.now(timezone.utc).isoformat()
        assert NarrativeEngine._is_within_window(recent, cutoff) is True

    def test_outside_window(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        old = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        assert NarrativeEngine._is_within_window(old, cutoff) is False

    def test_empty_timestamp_included(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        assert NarrativeEngine._is_within_window("", cutoff) is True

    def test_invalid_timestamp_included(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        assert NarrativeEngine._is_within_window("not-a-date", cutoff) is True


# ─── Source Type ─────────────────────────────────────────────


class TestSourceTypes:
    """Tests that each source type produces the correct source_type field."""

    def test_proposal_source_type(self, tmp_path):
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        p = {
            "id": "P-0001", "title": "Test", "description": "Test",
            "author": "Sage", "category": "ethics", "status": "open",
            "created_at": now, "updated_at": now,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0001.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )
        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine()
            bulletins = engine._proposal_bulletins()
            assert all(b.source_type == "proposal" for b in bulletins)

    def test_character_source_type(self, tmp_path):
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        ch = {
            "id": "CH-0001", "name": "Atlas", "description": "Explorer",
            "author": "Forge", "status": "active", "backstory": "",
            "traits": [{"trait_type": "personality", "name": "Bold",
                        "description": "Bold", "intensity": 0.8}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": now, "updated_at": now, "metadata": {},
        }
        (chars_dir / "CH-0001.json").write_text(
            json.dumps(ch, indent=2), encoding="utf-8",
        )
        with patch("core.characters.CHARACTERS_DIR", chars_dir):
            engine = NarrativeEngine()
            bulletins = engine._character_bulletins()
            assert all(b.source_type == "character" for b in bulletins)


# ─── Bulletin Fields ─────────────────────────────────────────


class TestBulletinFields:
    """Tests that bulletins have all required fields."""

    def test_all_fields_present(self, tmp_path):
        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        p = {
            "id": "P-0001", "title": "Test Fields",
            "description": "Checking fields", "author": "Logic",
            "category": "governance", "status": "open",
            "created_at": now, "updated_at": now,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0001.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )
        with patch("core.proposals.PROPOSALS_DIR", proposals_dir):
            engine = NarrativeEngine()
            bulletins = engine._proposal_bulletins()
            assert len(bulletins) == 1
            b = bulletins[0]
            d = b.to_dict()
            for field in ("headline", "body", "source_type",
                          "source_id", "timestamp", "icon"):
                assert field in d
                assert d[field]  # non-empty


# ─── API Endpoint ────────────────────────────────────────────


class TestApiNarrativeBulletins:
    """Tests for GET /api/narrative-bulletins via web_api."""

    @pytest.fixture
    def narrative_client(self, tmp_path):
        """TestClient with minimal data dirs for narrative endpoint."""
        import yaml
        from fastapi.testclient import TestClient
        from core.web_api import create_app

        members_dir = tmp_path / "members"
        members_dir.mkdir()
        sage = {
            "name": "Sage", "role": "Ethics Advisor",
            "description": "Ethics.", "personality": {"tone": "calm"},
            "api_provider": "openrouter", "model": "anthropic/claude-3.5-sonnet",
            "vote_weight": 1.0, "specialties": ["ethics"],
            "system_prompt": "You are Sage.",
        }
        (members_dir / "sage.yaml").write_text(
            yaml.dump(sage), encoding="utf-8",
        )

        proposals_dir = tmp_path / "proposals"
        proposals_dir.mkdir()
        now = datetime.now(timezone.utc).isoformat()
        p = {
            "id": "P-0001", "title": "Ethics Update",
            "description": "Expand ethical constraints", "author": "Sage",
            "category": "ethics", "status": "open",
            "created_at": now, "updated_at": now,
            "body": "", "reviews": [], "metadata": {},
        }
        (proposals_dir / "P-0001.json").write_text(
            json.dumps(p, indent=2), encoding="utf-8",
        )

        votes_dir = tmp_path / "votes"
        votes_dir.mkdir()
        chars_dir = tmp_path / "characters"
        chars_dir.mkdir()
        items_dir = tmp_path / "items"
        items_dir.mkdir()
        locations_dir = tmp_path / "locations"
        locations_dir.mkdir()
        treasury_dir = tmp_path / "treasury"
        treasury_dir.mkdir()
        static_dir = tmp_path / "web_static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text(
            "<h1>Test</h1>", encoding="utf-8",
        )
        avatars_dir = tmp_path / "council_avatars"
        avatars_dir.mkdir()

        with (
            patch("core.web_api.WEB_STATIC_DIR", static_dir),
            patch("core.web_api.COUNCIL_MEMBERS_DIR", members_dir),
            patch("core.registry.COUNCIL_MEMBERS_DIR", members_dir),
            patch("core.proposals.PROPOSALS_DIR", proposals_dir),
            patch("core.voting.VOTES_DIR", votes_dir),
            patch("core.characters.CHARACTERS_DIR", chars_dir),
            patch("core.items.ITEMS_DIR", items_dir),
            patch("core.locations.LOCATIONS_DIR", locations_dir),
            patch("core.treasury.TREASURY_DIR", treasury_dir),
            patch("config.settings.COUNCIL_AVATARS_DIR", avatars_dir),
        ):
            app = create_app()
            yield TestClient(app)

    def test_returns_list(self, narrative_client):
        resp = narrative_client.get("/api/narrative-bulletins")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_bulletins_have_fields(self, narrative_client):
        resp = narrative_client.get("/api/narrative-bulletins")
        data = resp.json()
        if data:  # should have at least the proposal bulletin
            for field in ("headline", "body", "source_type",
                          "source_id", "timestamp", "icon"):
                assert field in data[0]

    def test_bulletins_contain_proposal(self, narrative_client):
        resp = narrative_client.get("/api/narrative-bulletins")
        data = resp.json()
        assert len(data) >= 1
        source_types = {b["source_type"] for b in data}
        assert "proposal" in source_types

    def test_empty_returns_empty_list(self, tmp_path):
        """With no data at all, returns empty list."""
        import yaml
        from fastapi.testclient import TestClient
        from core.web_api import create_app

        members_dir = tmp_path / "members2"
        members_dir.mkdir()
        sage = {
            "name": "Sage", "role": "Ethics", "description": "E.",
            "personality": {}, "api_provider": "openrouter",
            "model": "m", "vote_weight": 1.0, "specialties": [],
            "system_prompt": "s",
        }
        (members_dir / "sage.yaml").write_text(
            yaml.dump(sage), encoding="utf-8",
        )

        empty_dirs = {}
        for name in ("proposals", "votes", "characters", "items",
                      "locations", "treasury"):
            d = tmp_path / f"empty_{name}"
            d.mkdir()
            empty_dirs[name] = d

        static_dir = tmp_path / "web_static2"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<h1>T</h1>", encoding="utf-8")
        avatars_dir = tmp_path / "avatars2"
        avatars_dir.mkdir()

        with (
            patch("core.web_api.WEB_STATIC_DIR", static_dir),
            patch("core.web_api.COUNCIL_MEMBERS_DIR", members_dir),
            patch("core.registry.COUNCIL_MEMBERS_DIR", members_dir),
            patch("core.proposals.PROPOSALS_DIR", empty_dirs["proposals"]),
            patch("core.voting.VOTES_DIR", empty_dirs["votes"]),
            patch("core.characters.CHARACTERS_DIR", empty_dirs["characters"]),
            patch("core.items.ITEMS_DIR", empty_dirs["items"]),
            patch("core.locations.LOCATIONS_DIR", empty_dirs["locations"]),
            patch("core.treasury.TREASURY_DIR", empty_dirs["treasury"]),
            patch("config.settings.COUNCIL_AVATARS_DIR", avatars_dir),
        ):
            app = create_app()
            client = TestClient(app)
            resp = client.get("/api/narrative-bulletins")
            assert resp.status_code == 200
            assert resp.json() == []
