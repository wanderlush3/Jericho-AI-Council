"""
Tests for Jericho Web Dashboard API (F-021).

Uses FastAPI's ``TestClient`` (backed by httpx) for synchronous API testing.
All tests use ``tmp_path`` fixtures so no real project data is touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from fastapi.testclient import TestClient

from core.web_api import create_app


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def members_dir(tmp_path):
    """Create a temporary members directory with two council members."""
    d = tmp_path / "members"
    d.mkdir()

    sage = {
        "name": "Sage",
        "role": "Ethics Advisor",
        "description": "Focuses on ethical concerns.",
        "personality": {"tone": "thoughtful", "style": "measured"},
        "api_provider": "openrouter",
        "model": "anthropic/claude-3.5-sonnet",
        "vote_weight": 1.0,
        "specialties": ["ethics", "philosophy"],
        "system_prompt": "You are Sage, the ethics advisor.",
    }
    logic = {
        "name": "Logic",
        "role": "Systems Thinker",
        "description": "Focuses on system design.",
        "personality": {"tone": "precise"},
        "api_provider": "mancer",
        "model": "celeste-v1.9",
        "vote_weight": 1.5,
        "specialties": ["systems", "architecture"],
        "system_prompt": "You are Logic, the systems thinker.",
    }

    (d / "sage.yaml").write_text(yaml.dump(sage), encoding="utf-8")
    (d / "logic.yaml").write_text(yaml.dump(logic), encoding="utf-8")
    return d


@pytest.fixture
def proposals_dir(tmp_path):
    """Create a temporary proposals directory with sample proposals."""
    d = tmp_path / "proposals"
    d.mkdir()

    p1 = {
        "id": "P-0001",
        "title": "Ethics Update",
        "description": "Expand ethical constraints",
        "author": "Sage",
        "category": "ethics",
        "status": "open",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "body": "Detailed body.",
        "reviews": [
            {"reviewer": "Logic", "stance": "support", "comment": "Good", "timestamp": "2026-01-02T00:00:00+00:00"}
        ],
        "metadata": {},
    }
    p2 = {
        "id": "P-0002",
        "title": "New Character",
        "description": "Add an explorer",
        "author": "Forge",
        "category": "character",
        "status": "draft",
        "created_at": "2026-01-03T00:00:00+00:00",
        "updated_at": "2026-01-03T00:00:00+00:00",
        "body": "",
        "reviews": [],
        "metadata": {},
    }

    (d / "P-0001.json").write_text(json.dumps(p1, indent=2), encoding="utf-8")
    (d / "P-0002.json").write_text(json.dumps(p2, indent=2), encoding="utf-8")
    return d


def _mock_voting_init(votes_dir, quorum=5, threshold=0.6):
    """Return a proper __init__ replacement for VotingEngine."""
    def init(self, v=None, q=None, t=None):
        self._dir = votes_dir
        self._quorum = quorum
        self._threshold = threshold
    return init


@pytest.fixture
def votes_dir(tmp_path):
    """Create a temporary votes directory with a sample record."""
    d = tmp_path / "votes"
    d.mkdir()

    rec = {
        "proposal_id": "P-0001",
        "status": "open",
        "votes": [
            {"voter": "Sage", "choice": "for", "reason": "Agree", "timestamp": "2026-01-01T00:00:00+00:00", "weight": 1.0},
            {"voter": "Logic", "choice": "against", "reason": "Needs work", "timestamp": "2026-01-01T01:00:00+00:00", "weight": 1.5},
        ],
        "vetoed": False,
        "veto_reason": "",
        "veto_timestamp": "",
        "opened_at": "2026-01-01T00:00:00+00:00",
        "closed_at": "",
        "metadata": {},
    }

    (d / "V-P-0001.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return d


@pytest.fixture
def characters_dir(tmp_path):
    """Create a temporary characters directory."""
    d = tmp_path / "characters"
    d.mkdir()

    ch = {
        "id": "CH-0001",
        "name": "Atlas",
        "description": "An explorer AI",
        "author": "Forge",
        "status": "active",
        "backstory": "Born in the digital frontier.",
        "traits": [
            {"trait_type": "personality", "name": "Curious", "description": "Always asking", "intensity": 0.8},
        ],
        "system_prompt": "You are Atlas.",
        "greeting": "Hello!",
        "example_messages": ["Let's explore."],
        "tags": ["explorer"],
        "version": 1,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "metadata": {},
    }

    (d / "CH-0001.json").write_text(json.dumps(ch, indent=2), encoding="utf-8")
    return d


@pytest.fixture
def client(members_dir, proposals_dir, votes_dir, characters_dir, tmp_path):
    """Create a TestClient with all data dirs mocked."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>Test</h1>", encoding="utf-8")

    with (
        patch("core.web_api.WEB_STATIC_DIR", static_dir),
        patch("core.web_api.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.registry.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.proposals.PROPOSALS_DIR", proposals_dir),
        patch("core.voting.VOTES_DIR", votes_dir),
        patch("core.characters.CHARACTERS_DIR", characters_dir),
    ):
        app = create_app()
        yield TestClient(app)


# ─── Status Endpoint ─────────────────────────────────────────


class TestApiStatus:
    """Tests for GET /api/status."""

    def test_status_returns_counts(self, client):
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["members"]["count"] == 2
        assert data["proposals"]["count"] == 2
        assert data["votes"]["count"] == 1
        assert data["characters"]["count"] == 1

    def test_status_has_provider_breakdown(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        providers = data["members"]["providers"]
        assert "openrouter" in providers
        assert "mancer" in providers

    def test_status_has_proposal_breakdown(self, client):
        resp = client.get("/api/status")
        data = resp.json()
        assert "open" in data["proposals"]["by_status"]
        assert "draft" in data["proposals"]["by_status"]


# ─── Council Endpoints ───────────────────────────────────────


class TestApiCouncil:
    """Tests for /api/council endpoints."""

    def test_list_all_members(self, client):
        resp = client.get("/api/council")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {m["name"] for m in data}
        assert "Sage" in names
        assert "Logic" in names

    def test_member_has_expected_fields(self, client):
        resp = client.get("/api/council")
        member = resp.json()[0]
        for field in ("name", "role", "description", "personality", "api_provider", "model", "vote_weight", "specialties", "system_prompt"):
            assert field in member

    def test_get_member_detail(self, client):
        resp = client.get("/api/council/Sage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Sage"
        assert data["role"] == "Ethics Advisor"
        assert "ethics" in data["specialties"]

    def test_get_member_case_insensitive(self, client):
        resp = client.get("/api/council/sage")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Sage"

    def test_member_not_found(self, client):
        resp = client.get("/api/council/Nobody")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]


# ─── Proposals Endpoints ─────────────────────────────────────


class TestApiProposals:
    """Tests for /api/proposals endpoints."""

    def test_list_all_proposals(self, client):
        resp = client.get("/api/proposals")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_filter_by_status(self, client):
        resp = client.get("/api/proposals?status=draft")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "P-0002"

    def test_list_filter_by_category(self, client):
        resp = client.get("/api/proposals?category=ethics")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "P-0001"

    def test_list_filter_by_author(self, client):
        resp = client.get("/api/proposals?author=Forge")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["author"] == "Forge"

    def test_get_proposal_detail(self, client):
        resp = client.get("/api/proposals/P-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Ethics Update"
        assert data["status"] == "open"
        assert len(data["reviews"]) == 1

    def test_proposal_not_found(self, client):
        resp = client.get("/api/proposals/P-9999")
        assert resp.status_code == 404


# ─── Votes Endpoints ─────────────────────────────────────────


class TestApiVotes:
    """Tests for /api/votes endpoints."""

    def test_list_all_votes(self, client):
        resp = client.get("/api/votes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["proposal_id"] == "P-0001"

    def test_vote_has_tally(self, client):
        resp = client.get("/api/votes")
        data = resp.json()
        rec = data[0]
        assert rec.get("tally") is not None

    def test_get_vote_detail(self, client):
        resp = client.get("/api/votes/P-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["proposal_id"] == "P-0001"
        assert "tally" in data
        assert data["tally"]["votes_for"] >= 0

    def test_vote_not_found(self, client):
        resp = client.get("/api/votes/P-9999")
        assert resp.status_code == 404


# ─── Characters Endpoints ────────────────────────────────────


class TestApiCharacters:
    """Tests for /api/characters endpoints."""

    def test_list_all_characters(self, client):
        resp = client.get("/api/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Atlas"

    def test_list_filter_by_status(self, client):
        resp = client.get("/api/characters?status=active")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_filter_by_author(self, client):
        resp = client.get("/api/characters?author=Forge")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_filter_by_tag(self, client):
        resp = client.get("/api/characters?tag=explorer")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_filter_no_match(self, client):
        resp = client.get("/api/characters?status=draft")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_get_character_detail(self, client):
        resp = client.get("/api/characters/CH-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Atlas"
        assert data["status"] == "active"
        assert len(data["traits"]) == 1
        assert data["traits"][0]["name"] == "Curious"

    def test_character_not_found(self, client):
        resp = client.get("/api/characters/CH-9999")
        assert resp.status_code == 404


# ─── Static / Index ──────────────────────────────────────────


class TestStaticServing:
    """Tests for static file serving."""

    def test_index_html(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Test" in resp.text


# ─── Help Output ─────────────────────────────────────────────


class TestWebCLICommand:
    """Tests for the ``jericho web`` CLI command."""

    def test_web_help(self):
        from click.testing import CliRunner
        from core.cli import cli

        runner = CliRunner(mix_stderr=False)
        result = runner.invoke(cli, ["web", "--help"])
        assert result.exit_code == 0
        assert "Launch the web dashboard" in result.output
        assert "--host" in result.output
        assert "--port" in result.output
