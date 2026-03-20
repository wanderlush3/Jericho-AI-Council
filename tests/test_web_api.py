"""
Tests for Jericho Web Dashboard API (F-021).

Uses FastAPI's ``TestClient`` (backed by httpx) for synchronous API testing.
All tests use ``tmp_path`` fixtures so no real project data is touched.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch
import webbrowser

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

    avatars_dir = tmp_path / "council_avatars"
    avatars_dir.mkdir()

    with (
        patch("core.web_api.WEB_STATIC_DIR", static_dir),
        patch("core.web_api.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.registry.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.proposals.PROPOSALS_DIR", proposals_dir),
        patch("core.voting.VOTES_DIR", votes_dir),
        patch("core.characters.CHARACTERS_DIR", characters_dir),
        patch("config.settings.COUNCIL_AVATARS_DIR", avatars_dir),
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

    def test_create_proposal_evolution_category(self, client, proposals_dir):
        """Evolution-category proposal can be created and listed."""
        evo_proposal = {
            "id": "P-0003",
            "title": "Evolve Atlas Courage",
            "description": "Add courage trait to Atlas",
            "author": "Sage",
            "category": "evolution",
            "status": "open",
            "created_at": "2026-01-04T00:00:00+00:00",
            "updated_at": "2026-01-04T00:00:00+00:00",
            "body": "",
            "reviews": [],
            "metadata": {},
        }
        (proposals_dir / "P-0003.json").write_text(
            json.dumps(evo_proposal, indent=2), encoding="utf-8",
        )
        resp = client.get("/api/proposals?category=evolution")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["category"] == "evolution"
        assert data[0]["title"] == "Evolve Atlas Courage"

    def test_evolution_category_in_settings(self):
        """'evolution' is a valid proposal category in settings."""
        from config.settings import PROPOSAL_CATEGORIES
        assert "evolution" in PROPOSAL_CATEGORIES


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


# ─── Veto Endpoints ──────────────────────────────────────────


class TestApiVoteVeto:
    """Tests for POST /api/votes/{id}/veto and /lift-veto."""

    def test_veto_success(self, client):
        resp = client.post("/api/votes/P-0001/veto", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["vetoed"] is True
        assert data["tally"]["vetoed"] is True

    def test_veto_with_reason(self, client):
        resp = client.post("/api/votes/P-0001/veto", json={"reason": "Not appropriate"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["vetoed"] is True
        assert data["veto_reason"] == "Not appropriate"

    def test_veto_already_vetoed(self, client):
        client.post("/api/votes/P-0001/veto", json={})
        resp = client.post("/api/votes/P-0001/veto", json={})
        assert resp.status_code == 400
        assert "already vetoed" in resp.json()["detail"].lower()

    def test_veto_not_found(self, client):
        resp = client.post("/api/votes/P-9999/veto", json={})
        assert resp.status_code == 404

    def test_lift_veto_success(self, client):
        client.post("/api/votes/P-0001/veto", json={"reason": "test"})
        resp = client.post("/api/votes/P-0001/lift-veto")
        assert resp.status_code == 200
        data = resp.json()
        assert data["vetoed"] is False
        assert data["tally"]["vetoed"] is False

    def test_lift_veto_not_vetoed(self, client):
        resp = client.post("/api/votes/P-0001/lift-veto")
        assert resp.status_code == 400
        assert "not vetoed" in resp.json()["detail"].lower()

    def test_lift_veto_not_found(self, client):
        resp = client.post("/api/votes/P-9999/lift-veto")
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
        assert "--no-browser" in result.output

    def test_web_opens_browser_by_default(self):
        """webbrowser.open is scheduled when --no-browser is not passed."""
        from click.testing import CliRunner
        from core.cli import cli

        runner = CliRunner(mix_stderr=False)
        with (
            patch("uvicorn.run") as mock_run,
            patch("threading.Timer") as mock_timer,
        ):
            mock_run.return_value = None
            result = runner.invoke(cli, ["web"])

        assert result.exit_code == 0
        mock_timer.assert_called_once_with(1.5, webbrowser.open, args=["http://127.0.0.1:8080"])
        mock_timer.return_value.start.assert_called_once()

    def test_web_no_browser_flag(self):
        """webbrowser.open is NOT scheduled when --no-browser is passed."""
        from click.testing import CliRunner
        from core.cli import cli

        runner = CliRunner(mix_stderr=False)
        with (
            patch("uvicorn.run") as mock_run,
            patch("threading.Timer") as mock_timer,
        ):
            mock_run.return_value = None
            result = runner.invoke(cli, ["web", "--no-browser"])

        assert result.exit_code == 0
        mock_timer.assert_not_called()


# ─── Chat Endpoints ──────────────────────────────────────────


def _make_chat_record(chat_id, member_name="Sage", title="Test Chat",
                      topic="", messages=None, closed_at="",
                      council_members=None, paused=False):
    """Build a raw chat JSON dict."""
    if council_members is None:
        council_members = [member_name] if member_name else []
    return {
        "chat_id": chat_id,
        "title": title,
        "member_name": member_name,
        "topic": topic,
        "messages": messages or [],
        "summary": "",
        "created_at": "2026-03-15T00:00:00+00:00",
        "closed_at": closed_at,
        "metadata": {},
        "council_members": council_members,
        "paused": paused,
    }


@pytest.fixture
def conversations_dir(tmp_path):
    """Create a temporary conversations directory."""
    d = tmp_path / "conversations"
    d.mkdir()
    return d


@pytest.fixture
def chat_client(members_dir, proposals_dir, votes_dir, characters_dir,
                conversations_dir, tmp_path):
    """TestClient with conversations_dir also mocked."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>Test</h1>", encoding="utf-8")

    avatars_dir = tmp_path / "council_avatars"
    avatars_dir.mkdir()

    with (
        patch("core.web_api.WEB_STATIC_DIR", static_dir),
        patch("core.web_api.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.registry.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.proposals.PROPOSALS_DIR", proposals_dir),
        patch("core.voting.VOTES_DIR", votes_dir),
        patch("core.characters.CHARACTERS_DIR", characters_dir),
        patch("core.human_chat.CONVERSATIONS_DIR", conversations_dir),
        patch("config.settings.CONVERSATIONS_DIR", conversations_dir),
        patch("config.settings.COUNCIL_AVATARS_DIR", avatars_dir),
    ):
        app = create_app()
        yield TestClient(app)


class TestApiChat:
    """Tests for /api/chat endpoints."""

    # ── GET /api/chat — List ──────────────────────────────────

    def test_list_empty(self, chat_client):
        resp = chat_client.get("/api/chat")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_chats(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001", member_name="Sage", title="Ethics Q&A")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.get("/api/chat")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["chat_id"] == "WC-0001"

    def test_list_filter_by_member(self, chat_client, conversations_dir):
        r1 = _make_chat_record("WC-0001", member_name="Sage")
        r2 = _make_chat_record("WC-0002", member_name="Logic")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(r1, indent=2), encoding="utf-8"
        )
        (conversations_dir / "H-WC-0002.json").write_text(
            json.dumps(r2, indent=2), encoding="utf-8"
        )
        resp = chat_client.get("/api/chat?member=Sage")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["member_name"] == "Sage"

    def test_list_filter_by_closed(self, chat_client, conversations_dir):
        r1 = _make_chat_record("WC-0001", closed_at="")
        r2 = _make_chat_record("WC-0002", closed_at="2026-03-15T10:00:00+00:00")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(r1, indent=2), encoding="utf-8"
        )
        (conversations_dir / "H-WC-0002.json").write_text(
            json.dumps(r2, indent=2), encoding="utf-8"
        )
        resp = chat_client.get("/api/chat?closed=true")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["chat_id"] == "WC-0002"

    # ── GET /api/chat/{id} — Detail ───────────────────────────

    def test_detail_found(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001", messages=[
            {"role": "human", "speaker": "Human", "content": "Hello",
             "timestamp": "2026-03-15T00:01:00+00:00", "metadata": {}},
        ])
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.get("/api/chat/WC-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_id"] == "WC-0001"
        assert len(data["messages"]) == 1

    def test_detail_not_found(self, chat_client):
        resp = chat_client.get("/api/chat/WC-9999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    # ── POST /api/chat — Create ───────────────────────────────

    def test_create_success(self, chat_client, conversations_dir):
        resp = chat_client.post("/api/chat", json={
            "member_name": "Sage",
            "title": "New Ethics Chat",
            "topic": "alignment",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["chat_id"].startswith("WC-")
        assert data["title"] == "New Ethics Chat"
        assert data["member_name"] == "Sage"
        assert data["topic"] == "alignment"

    def test_create_missing_member(self, chat_client):
        resp = chat_client.post("/api/chat", json={
            "title": "No Member",
        })
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"]

    def test_create_missing_title(self, chat_client):
        resp = chat_client.post("/api/chat", json={
            "member_name": "Sage",
        })
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"]

    def test_create_invalid_member(self, chat_client):
        resp = chat_client.post("/api/chat", json={
            "member_name": "Nobody",
            "title": "Bad Chat",
        })
        assert resp.status_code == 400
        assert "Unknown" in resp.json()["detail"] or "Validation" in resp.json()["detail"]

    def test_create_sequential_ids(self, chat_client, conversations_dir):
        # Create first
        resp1 = chat_client.post("/api/chat", json={
            "member_name": "Sage", "title": "Chat 1",
        })
        assert resp1.json()["chat_id"] == "WC-0001"

        # Create second
        resp2 = chat_client.post("/api/chat", json={
            "member_name": "Logic", "title": "Chat 2",
        })
        assert resp2.json()["chat_id"] == "WC-0002"

    # ── POST /api/chat/{id}/send — Send ───────────────────────

    def test_send_success(self, chat_client, conversations_dir):
        # Create a chat first
        rec = _make_chat_record("WC-0001", member_name="Sage", title="Ethics Q&A")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )

        # Mock the API client to return a canned response
        from core.api_client import ChatResponse
        mock_response = ChatResponse(
            content="I believe in ethical AI.",
            model="anthropic/claude-3.5-sonnet",
            provider="openrouter",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            raw={},
        )
        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = chat_client.post("/api/chat/WC-0001/send", json={
                "content": "What are your core beliefs?",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert "agent_response" in data
        assert data["agent_response"] == "I believe in ethical AI."
        assert len(data["chat"]["messages"]) == 2  # human + agent

    def test_send_empty_content(self, chat_client):
        resp = chat_client.post("/api/chat/WC-0001/send", json={
            "content": "",
        })
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"]

    def test_send_not_found(self, chat_client):
        resp = chat_client.post("/api/chat/WC-9999/send", json={
            "content": "Hello",
        })
        assert resp.status_code == 404

    def test_send_closed_chat(self, chat_client, conversations_dir):
        rec = _make_chat_record(
            "WC-0001", closed_at="2026-03-15T10:00:00+00:00"
        )
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/send", json={
            "content": "Hello",
        })
        assert resp.status_code == 400
        assert "closed" in resp.json()["detail"].lower()

    # ── POST /api/chat/{id}/close — Close ─────────────────────

    def test_close_success(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/close", json={
            "summary": "Discussed ethics.",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["closed_at"]  # non-empty
        assert data["summary"] == "Discussed ethics."

    def test_close_already_closed(self, chat_client, conversations_dir):
        rec = _make_chat_record(
            "WC-0001", closed_at="2026-03-15T10:00:00+00:00"
        )
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/close", json={})
        assert resp.status_code == 400
        assert "closed" in resp.json()["detail"].lower()

    def test_close_not_found(self, chat_client):
        resp = chat_client.post("/api/chat/WC-9999/close", json={})
        assert resp.status_code == 404

    def test_close_without_body(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        # POST with empty body — should auto-generate summary
        resp = chat_client.post("/api/chat/WC-0001/close", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["closed_at"]

    # ── POST /api/chat/{id}/add-member ────────────────────────

    def test_add_member_success(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001", member_name="Sage",
                                council_members=["Sage"])
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/add-member", json={
            "member_name": "Logic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "Logic" in data["council_members"]
        assert len(data["council_members"]) == 2

    def test_add_member_unknown(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/add-member", json={
            "member_name": "Nobody",
        })
        assert resp.status_code == 400
        assert "unknown" in resp.json()["detail"].lower() or "Unknown" in resp.json()["detail"]

    def test_add_member_duplicate(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001", council_members=["Sage"])
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/add-member", json={
            "member_name": "Sage",
        })
        assert resp.status_code == 400
        assert "already" in resp.json()["detail"].lower()

    def test_add_member_closed_chat(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001",
                                closed_at="2026-03-15T10:00:00+00:00")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/add-member", json={
            "member_name": "Logic",
        })
        assert resp.status_code == 400
        assert "closed" in resp.json()["detail"].lower()

    def test_add_member_not_found(self, chat_client):
        resp = chat_client.post("/api/chat/WC-9999/add-member", json={
            "member_name": "Sage",
        })
        assert resp.status_code == 404

    # ── POST /api/chat/{id}/remove-member ─────────────────────

    def test_remove_member_success(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001",
                                council_members=["Sage", "Logic"])
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/remove-member", json={
            "member_name": "Logic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["council_members"] == ["Sage"]

    def test_remove_last_member(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001",
                                council_members=["Sage"])
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/remove-member", json={
            "member_name": "Sage",
        })
        assert resp.status_code == 400
        assert "last" in resp.json()["detail"].lower() or "Cannot" in resp.json()["detail"]

    def test_remove_member_not_present(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001",
                                council_members=["Sage"])
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/remove-member", json={
            "member_name": "Logic",
        })
        assert resp.status_code == 400
        assert "not in" in resp.json()["detail"].lower()

    # ── POST /api/chat/{id}/pause and resume ──────────────────

    def test_pause_resume_success(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        # Pause
        resp = chat_client.post("/api/chat/WC-0001/pause")
        assert resp.status_code == 200
        assert resp.json()["paused"] is True

        # Resume
        resp = chat_client.post("/api/chat/WC-0001/resume")
        assert resp.status_code == 200
        assert resp.json()["paused"] is False

    def test_pause_already_paused(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001", paused=True)
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/pause")
        assert resp.status_code == 400
        assert "paused" in resp.json()["detail"].lower()

    def test_resume_not_paused(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001", paused=False)
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/resume")
        assert resp.status_code == 400
        assert "not paused" in resp.json()["detail"].lower()

    def test_pause_closed_chat(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001",
                                closed_at="2026-03-15T10:00:00+00:00")
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )
        resp = chat_client.post("/api/chat/WC-0001/pause")
        assert resp.status_code == 400
        assert "closed" in resp.json()["detail"].lower()

    # ── Multi-member send auto-resumes ────────────────────────

    def test_send_paused_chat_auto_resumes(self, chat_client, conversations_dir):
        rec = _make_chat_record("WC-0001", member_name="Sage",
                                title="Ethics Q&A", paused=True)
        (conversations_dir / "H-WC-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8"
        )

        from core.api_client import ChatResponse
        mock_response = ChatResponse(
            content="Resumed and responding.",
            model="anthropic/claude-3.5-sonnet",
            provider="openrouter",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
            raw={},
        )
        with patch("core.api_client.APIClient.chat", return_value=mock_response):
            resp = chat_client.post("/api/chat/WC-0001/send", json={
                "content": "Continue please.",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_response"] == "Resumed and responding."


# ─── Council Update Endpoints ────────────────────────────────


class TestApiCouncilUpdate:
    """Tests for PUT /api/council/{name} and avatar endpoints."""

    def test_update_member_success(self, client, members_dir):
        """PUT valid editable fields updates the YAML."""
        resp = client.put("/api/council/Sage", json={
            "model": "anthropic/claude-3-opus",
            "vote_weight": 2.0,
            "traits": ["wise", "calm", "thoughtful"],
            "communication_style": "Very measured and diplomatic",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["model"] == "anthropic/claude-3-opus"
        assert data["vote_weight"] == 2.0
        assert data["personality"]["traits"] == ["wise", "calm", "thoughtful"]
        assert data["personality"]["communication_style"] == "Very measured and diplomatic"
        # Read-only fields unchanged
        assert data["role"] == "Ethics Advisor"
        assert data["specialties"] == ["ethics", "philosophy"]

        # Verify YAML file was actually updated
        updated = yaml.safe_load((members_dir / "sage.yaml").read_text(encoding="utf-8"))
        assert updated["model"] == "anthropic/claude-3-opus"
        assert updated["vote_weight"] == 2.0

    def test_update_member_readonly_fields_rejected(self, client):
        """Attempting to modify role/description/specialties returns 400."""
        resp = client.put("/api/council/Sage", json={
            "role": "New Role",
        })
        assert resp.status_code == 400
        assert "read-only" in resp.json()["detail"]

    def test_update_member_description_rejected(self, client):
        """Description is also read-only."""
        resp = client.put("/api/council/Sage", json={
            "description": "New description",
        })
        assert resp.status_code == 400
        assert "read-only" in resp.json()["detail"]

    def test_update_member_specialties_rejected(self, client):
        """Specialties is also read-only."""
        resp = client.put("/api/council/Sage", json={
            "specialties": ["new-specialty"],
        })
        assert resp.status_code == 400
        assert "read-only" in resp.json()["detail"]

    def test_update_member_invalid_provider(self, client):
        """Setting api_provider to invalid value returns 400."""
        resp = client.put("/api/council/Sage", json={
            "api_provider": "invalid_provider",
        })
        assert resp.status_code == 400
        assert "Validation failed" in resp.json()["detail"] or "Invalid" in resp.json()["detail"]

    def test_update_member_invalid_weight(self, client):
        """Setting vote_weight to 0 or negative returns 400."""
        resp = client.put("/api/council/Sage", json={
            "vote_weight": -1.0,
        })
        assert resp.status_code == 400

    def test_update_member_not_found(self, client):
        """PUT to nonexistent member returns 404."""
        resp = client.put("/api/council/Nobody", json={
            "model": "test",
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_update_system_prompt(self, client, members_dir):
        """System prompt is editable."""
        new_prompt = "You are a completely new Sage with updated instructions."
        resp = client.put("/api/council/Sage", json={
            "system_prompt": new_prompt,
        })
        assert resp.status_code == 200
        assert resp.json()["system_prompt"] == new_prompt

    def test_update_api_provider(self, client, members_dir):
        """Switching api_provider between mancer and openrouter works."""
        resp = client.put("/api/council/Sage", json={
            "api_provider": "mancer",
        })
        assert resp.status_code == 200
        assert resp.json()["api_provider"] == "mancer"

    def test_upload_avatar(self, client, tmp_path):
        """POST base64 image data saves avatar file."""
        import base64
        # Create a tiny valid PNG (1x1 white pixel)
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
            b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
            b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        b64 = base64.b64encode(png_bytes).decode()
        image_data = f"data:image/png;base64,{b64}"

        with patch("config.settings.COUNCIL_AVATARS_DIR", tmp_path / "avatars"):
            resp = client.post("/api/council/Sage/avatar-upload", json={
                "image_data": image_data,
                "zoom": 1.5,
                "offsetX": 10,
                "offsetY": -5,
            })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert "avatar_url" in resp.json()

    def test_get_avatar_not_found(self, client, tmp_path):
        """GET avatar for member without one returns 404."""
        with patch("config.settings.COUNCIL_AVATARS_DIR", tmp_path / "no_avatars"):
            resp = client.get("/api/council/Sage/avatar")
        assert resp.status_code == 404

    def test_get_avatar_member_not_found(self, client):
        """GET avatar for nonexistent member returns 404."""
        resp = client.get("/api/council/Nobody/avatar")
        assert resp.status_code == 404

    def test_upload_avatar_missing_data(self, client):
        """POST without image_data returns 400."""
        resp = client.post("/api/council/Sage/avatar-upload", json={
            "zoom": 1.0,
        })
        assert resp.status_code == 400
        assert "image_data" in resp.json()["detail"]

    def test_council_list_no_avatar_url_by_default(self, client):
        """Council list does not include avatar_url when no avatars uploaded."""
        resp = client.get("/api/council")
        assert resp.status_code == 200
        for member in resp.json():
            assert "avatar_url" not in member


# ─── User Description Endpoints ──────────────────────────────


class TestApiUserDescription:
    """Tests for /api/settings/user-description endpoints."""

    def test_get_user_description_empty(self, client, tmp_path):
        """GET returns empty description by default."""
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        with patch("core.api_keys.ENV_FILE", env_file):
            resp = client.get("/api/settings/user-description")
        assert resp.status_code == 200
        assert resp.json()["description"] == ""

    def test_save_and_get_user_description(self, client, tmp_path):
        """POST saves description and GET retrieves it."""
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        with patch("core.api_keys.ENV_FILE", env_file):
            resp = client.post("/api/settings/user-description", json={
                "description": "I'm a game developer working on AI tools.",
            })
            assert resp.status_code == 200
            assert resp.json()["description"] == "I'm a game developer working on AI tools."

            # Verify GET returns the same
            resp2 = client.get("/api/settings/user-description")
            assert resp2.status_code == 200
            assert resp2.json()["description"] == "I'm a game developer working on AI tools."

    def test_save_user_description_too_long(self, client, tmp_path):
        """POST rejects descriptions longer than 700 characters."""
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        with patch("core.api_keys.ENV_FILE", env_file):
            long_text = "a" * 701
            resp = client.post("/api/settings/user-description", json={
                "description": long_text,
            })
            assert resp.status_code == 400
            assert "700" in resp.json()["detail"]

    def test_save_user_description_at_max_length(self, client, tmp_path):
        """POST accepts description at exactly 700 characters."""
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        with patch("core.api_keys.ENV_FILE", env_file):
            exact_text = "b" * 700
            resp = client.post("/api/settings/user-description", json={
                "description": exact_text,
            })
            assert resp.status_code == 200
            assert len(resp.json()["description"]) == 700

    def test_save_user_description_empty(self, client, tmp_path):
        """POST accepts an empty description (clearing it)."""
        env_file = tmp_path / ".env"
        env_file.write_text("", encoding="utf-8")
        with patch("core.api_keys.ENV_FILE", env_file):
            resp = client.post("/api/settings/user-description", json={
                "description": "",
            })
            assert resp.status_code == 200
            assert resp.json()["description"] == ""


# ─── OpenRouter Model Options Endpoint ────────────────────────


class TestApiOpenRouterModels:
    """Tests for GET /api/settings/openrouter-models."""

    def test_returns_model_list(self, client):
        resp = client.get("/api/settings/openrouter-models")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert "Default" in data
        assert "mistralai/mistral-small-creative" in data
        assert "anthropic/claude-sonnet-4.6" in data
        assert len(data) >= 9  # 8 models + Default


# ─── Character CRUD Endpoints ────────────────────────────────


class TestApiCharacterCrud:
    """Tests for character create / update / status / avatar / export."""

    def test_create_character_success(self, client):
        """POST /api/characters creates a character and returns it."""
        resp = client.post("/api/characters", json={
            "name": "Luna",
            "description": "A mysterious oracle",
            "author": "Sage",
            "backstory": "Emerged from moonlight",
            "system_prompt": "You are Luna the oracle.",
            "greeting": "The stars speak through me.",
            "example_messages": ["What do you seek?"],
            "tags": ["oracle", "mystic"],
            "traits": [
                {"trait_type": "personality", "name": "Enigmatic",
                 "description": "Speaks in riddles", "intensity": 0.9},
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Luna"
        assert data["author"] == "Sage"
        assert data["status"] == "draft"
        assert data["id"].startswith("CH-")
        assert len(data["traits"]) == 1

    def test_create_character_missing_fields(self, client):
        """POST /api/characters without required fields returns 400."""
        resp = client.post("/api/characters", json={
            "name": "",
            "description": "Test",
            "author": "Test",
            "traits": [{"trait_type": "personality", "name": "T",
                        "description": "T", "intensity": 0.5}],
        })
        assert resp.status_code == 400

    def test_create_character_no_traits(self, client):
        """POST without traits returns 400 since traits are required."""
        resp = client.post("/api/characters", json={
            "name": "NoTrait",
            "description": "Test char",
            "author": "Tester",
            "traits": [],
        })
        assert resp.status_code == 400

    def test_update_character_success(self, client):
        """PUT /api/characters/{id} updates mutable fields."""
        resp = client.put("/api/characters/CH-0001", json={
            "name": "Atlas V2",
            "description": "An updated explorer",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Atlas V2"
        assert data["description"] == "An updated explorer"

    def test_update_character_not_found(self, client):
        resp = client.put("/api/characters/CH-9999", json={
            "name": "Ghost",
        })
        assert resp.status_code == 404

    def test_status_transition_draft_to_active(self, client, characters_dir):
        """Status transition from draft to active."""
        # The existing fixture character is 'active', so create a draft one
        import json as j
        draft = {
            "id": "CH-0002", "name": "Draftee", "description": "A draft char",
            "author": "Test", "status": "draft",
            "backstory": "", "traits": [
                {"trait_type": "personality", "name": "Bold",
                 "description": "D", "intensity": 0.5}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00", "metadata": {},
        }
        (characters_dir / "CH-0002.json").write_text(
            j.dumps(draft, indent=2), encoding="utf-8",
        )
        resp = client.put("/api/characters/CH-0002/status", json={
            "status": "active",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_status_invalid_transition(self, client, characters_dir):
        """Draft → archived is not allowed (must activate first)."""
        import json as j
        draft = {
            "id": "CH-0010", "name": "DraftOnly", "description": "D",
            "author": "Test", "status": "draft",
            "backstory": "", "traits": [
                {"trait_type": "personality", "name": "Shy",
                 "description": "D", "intensity": 0.5}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00", "metadata": {},
        }
        (characters_dir / "CH-0010.json").write_text(
            j.dumps(draft, indent=2), encoding="utf-8",
        )
        resp = client.put("/api/characters/CH-0010/status", json={
            "status": "archived",
        })
        assert resp.status_code == 400

    def test_avatar_upload_and_serve(self, client, tmp_path):
        """POST avatar then GET it back."""
        import base64
        from core.png_embed import create_minimal_png
        png = create_minimal_png()
        b64 = base64.b64encode(png).decode()
        image_data = f"data:image/png;base64,{b64}"

        with patch("config.settings.CHARACTER_AVATARS_DIR", tmp_path / "char_avatars"):
            resp = client.post("/api/characters/CH-0001/avatar-upload", json={
                "image_data": image_data,
            })
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"

            # Now GET the avatar
            resp2 = client.get("/api/characters/CH-0001/avatar")
            assert resp2.status_code == 200
            assert resp2.headers["content-type"] == "image/png"

    def test_avatar_not_found(self, client, tmp_path):
        """GET avatar for character without one returns 404."""
        with patch("config.settings.CHARACTER_AVATARS_DIR", tmp_path / "no_avatars"):
            resp = client.get("/api/characters/CH-0001/avatar")
        assert resp.status_code == 404

    def test_export_png(self, client, tmp_path):
        """GET export-png returns valid PNG with embedded character data."""
        import base64 as b64mod
        with patch("config.settings.CHARACTER_AVATARS_DIR", tmp_path / "no_avatars"):
            resp = client.get("/api/characters/CH-0001/export-png")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        png_bytes = resp.content
        assert png_bytes[:8] == b"\x89PNG\r\n\x1a\n"

        # Verify embedded data
        from core.png_embed import extract_character_from_png
        card = extract_character_from_png(png_bytes)
        assert card is not None
        assert card["spec"] == "chara_card_v2"
        assert card["data"]["name"] == "Atlas"

    def test_export_png_not_found(self, client, tmp_path):
        with patch("config.settings.CHARACTER_AVATARS_DIR", tmp_path / "no_avatars"):
            resp = client.get("/api/characters/CH-9999/export-png")
        assert resp.status_code == 404

    def test_list_characters_includes_avatar_url(self, client, tmp_path):
        """GET /api/characters includes avatar_url when avatar exists."""
        avatar_dir = tmp_path / "char_avatars"
        avatar_dir.mkdir()
        (avatar_dir / "CH-0001.png").write_bytes(b"fake png")
        with patch("config.settings.CHARACTER_AVATARS_DIR", avatar_dir):
            resp = client.get("/api/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["avatar_url"] == "/api/characters/CH-0001/avatar"

    # ── Bidirectional status transitions ──────────────────────

    def test_status_transition_archived_to_active(self, client, characters_dir):
        """Archived characters can be reactivated."""
        import json as j
        archived = {
            "id": "CH-0003", "name": "OldChar", "description": "Archived char",
            "author": "Test", "status": "archived",
            "backstory": "", "traits": [
                {"trait_type": "personality", "name": "Calm",
                 "description": "D", "intensity": 0.5}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00", "metadata": {},
        }
        (characters_dir / "CH-0003.json").write_text(
            j.dumps(archived, indent=2), encoding="utf-8",
        )
        resp = client.put("/api/characters/CH-0003/status", json={
            "status": "active",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "active"

    def test_status_transition_active_to_draft(self, client):
        """Active characters can revert to draft."""
        resp = client.put("/api/characters/CH-0001/status", json={
            "status": "draft",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    def test_status_transition_archived_to_draft(self, client, characters_dir):
        """Archived characters can revert to draft."""
        import json as j
        archived = {
            "id": "CH-0004", "name": "ArcDraft", "description": "Archived char",
            "author": "Test", "status": "archived",
            "backstory": "", "traits": [
                {"trait_type": "personality", "name": "Bold",
                 "description": "D", "intensity": 0.5}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00", "metadata": {},
        }
        (characters_dir / "CH-0004.json").write_text(
            j.dumps(archived, indent=2), encoding="utf-8",
        )
        resp = client.put("/api/characters/CH-0004/status", json={
            "status": "draft",
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "draft"

    # ── POST export-png with user-uploaded image ─────────────

    def test_export_png_with_uploaded_image(self, client, tmp_path):
        """POST /api/characters/{id}/export-png with uploaded PNG returns embedded PNG."""
        import base64 as b64mod
        from core.png_embed import create_minimal_png, extract_character_from_png

        png = create_minimal_png()
        b64 = b64mod.b64encode(png).decode()
        image_data = f"data:image/png;base64,{b64}"

        with patch("config.settings.CHARACTER_AVATARS_DIR", tmp_path / "no_avatars"):
            resp = client.post("/api/characters/CH-0001/export-png", json={
                "image_data": image_data,
            })
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        # Verify filename contains jericho_ prefix
        cd = resp.headers.get("content-disposition", "")
        assert "jericho_" in cd
        # Verify embedded data
        card = extract_character_from_png(resp.content)
        assert card is not None
        assert card["spec"] == "chara_card_v2"
        assert card["data"]["name"] == "Atlas"

    def test_export_png_upload_missing_data(self, client):
        """POST without image_data returns 400."""
        resp = client.post("/api/characters/CH-0001/export-png", json={})
        assert resp.status_code == 400
        assert "image_data" in resp.json()["detail"]

    def test_export_png_upload_not_png(self, client):
        """POST with non-PNG data returns 400."""
        import base64 as b64mod
        b64 = b64mod.b64encode(b"not a png file").decode()
        resp = client.post("/api/characters/CH-0001/export-png", json={
            "image_data": f"data:image/png;base64,{b64}",
        })
        assert resp.status_code == 400
        assert "not a valid PNG" in resp.json()["detail"]

    # ── Trait add / remove endpoints ─────────────────────────

    def test_add_trait_success(self, client):
        """POST /api/characters/{id}/traits adds a new trait."""
        resp = client.post("/api/characters/CH-0001/traits", json={
            "trait_type": "values",
            "name": "Brave",
            "description": "Fearless in the face of danger",
            "intensity": 0.8,
        })
        assert resp.status_code == 200
        traits = resp.json()["traits"]
        trait_names = [t["name"] for t in traits]
        assert "Brave" in trait_names

    def test_add_trait_duplicate(self, client):
        """POST duplicate trait name returns 400."""
        # The fixture CH-0001 has trait "Explorer" (from conftest)
        # First, get the existing traits to know what name to duplicate
        detail = client.get("/api/characters/CH-0001").json()
        existing_name = detail["traits"][0]["name"]
        resp = client.post("/api/characters/CH-0001/traits", json={
            "trait_type": "personality",
            "name": existing_name,
            "description": "dup",
            "intensity": 0.5,
        })
        assert resp.status_code == 400

    def test_remove_trait_success(self, client):
        """DELETE /api/characters/{id}/traits/{name} removes a trait."""
        # First add a spare trait so removal doesn't hit the min-1 guard
        client.post("/api/characters/CH-0001/traits", json={
            "trait_type": "custom",
            "name": "Temporary",
            "description": "Will be removed",
            "intensity": 0.3,
        })
        resp = client.delete("/api/characters/CH-0001/traits/Temporary")
        assert resp.status_code == 200
        trait_names = [t["name"] for t in resp.json()["traits"]]
        assert "Temporary" not in trait_names

    def test_remove_trait_last(self, client, characters_dir):
        """DELETE last trait returns 400."""
        import json as j
        single_trait = {
            "id": "CH-0005", "name": "Solo", "description": "One-trait char",
            "author": "Test", "status": "draft",
            "backstory": "", "traits": [
                {"trait_type": "personality", "name": "Lone",
                 "description": "Only trait", "intensity": 0.5}],
            "system_prompt": "", "greeting": "", "example_messages": [],
            "tags": [], "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00", "metadata": {},
        }
        (characters_dir / "CH-0005.json").write_text(
            j.dumps(single_trait, indent=2), encoding="utf-8",
        )
        resp = client.delete("/api/characters/CH-0005/traits/Lone")
        assert resp.status_code == 400


# ─── Memory Endpoints (F-028) ────────────────────────────────


@pytest.fixture
def memories_dir(tmp_path):
    """Create a temporary memories directory with sample data."""
    d = tmp_path / "memories"
    d.mkdir()
    return d


@pytest.fixture
def memory_client(members_dir, proposals_dir, votes_dir, characters_dir,
                  memories_dir, tmp_path):
    """TestClient with memories_dir also mocked."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>Test</h1>", encoding="utf-8")

    avatars_dir = tmp_path / "council_avatars"
    avatars_dir.mkdir()

    with (
        patch("core.web_api.WEB_STATIC_DIR", static_dir),
        patch("core.web_api.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.registry.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.proposals.PROPOSALS_DIR", proposals_dir),
        patch("core.voting.VOTES_DIR", votes_dir),
        patch("core.characters.CHARACTERS_DIR", characters_dir),
        patch("config.settings.MEMORIES_DIR", memories_dir),
        patch("core.memory.MEMORIES_DIR", memories_dir),
        patch("config.settings.COUNCIL_AVATARS_DIR", avatars_dir),
    ):
        app = create_app()
        yield TestClient(app)


class TestApiMemories:
    """Tests for /api/memories endpoints (F-028)."""

    # ── GET /api/memories — List ──────────────────────────────

    def test_list_members_empty_memories(self, memory_client):
        """GET /api/memories returns member list with zero counts when no memory files."""
        resp = memory_client.get("/api/memories")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2  # Sage + Logic
        names = {m["name"] for m in data}
        assert "Sage" in names
        assert "Logic" in names
        for m in data:
            assert m["belief_count"] == 0
            assert m["event_count"] == 0

    def test_list_members_with_beliefs(self, memory_client, memories_dir):
        """Member list reflects belief count."""
        sage_dir = memories_dir / "sage"
        sage_dir.mkdir()
        (sage_dir / "core_beliefs.json").write_text(
            json.dumps([
                {"topic": "safety", "content": "Safety first", "added_timestamp": "", "source": ""},
                {"topic": "ethics", "content": "Act ethically", "added_timestamp": "", "source": ""},
            ]),
            encoding="utf-8",
        )
        resp = memory_client.get("/api/memories")
        sage = [m for m in resp.json() if m["name"] == "Sage"][0]
        assert sage["belief_count"] == 2

    def test_list_members_has_role(self, memory_client):
        """Each member in the list has a role field."""
        resp = memory_client.get("/api/memories")
        for m in resp.json():
            assert "role" in m and m["role"]

    # ── GET /api/memories/{member} — Detail ───────────────────

    def test_member_detail_empty(self, memory_client):
        """Member detail returns empty beliefs and events for new member."""
        resp = memory_client.get("/api/memories/Sage")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Sage"
        assert data["beliefs"] == []
        assert data["events"] == []
        assert data["belief_count"] == 0
        assert data["event_count"] == 0

    def test_member_detail_with_beliefs(self, memory_client, memories_dir):
        """Member detail returns core beliefs."""
        sage_dir = memories_dir / "sage"
        sage_dir.mkdir()
        beliefs = [
            {"topic": "safety", "content": "Safety is paramount", "added_timestamp": "2026-01-01T00:00:00+00:00", "source": "session"},
        ]
        (sage_dir / "core_beliefs.json").write_text(json.dumps(beliefs), encoding="utf-8")

        resp = memory_client.get("/api/memories/Sage")
        data = resp.json()
        assert data["belief_count"] == 1
        assert data["beliefs"][0]["topic"] == "safety"
        assert data["beliefs"][0]["content"] == "Safety is paramount"

    def test_member_detail_with_events(self, memory_client, memories_dir):
        """Member detail returns recent session events."""
        sage_dir = memories_dir / "sage"
        sage_dir.mkdir()
        events = [
            {"timestamp": "2026-01-01T00:00:00+00:00", "session_id": "S-001", "event_type": "discussion", "content": "Talked about ethics", "source": "Sage", "metadata": {}},
            {"timestamp": "2026-01-01T01:00:00+00:00", "session_id": "S-001", "event_type": "vote", "content": "Voted for proposal", "source": "Sage", "metadata": {}},
        ]
        (sage_dir / "session_log.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events),
            encoding="utf-8",
        )
        resp = memory_client.get("/api/memories/Sage")
        data = resp.json()
        assert data["event_count"] == 2
        assert len(data["events"]) == 2
        # Recent events are newest first
        assert data["events"][0]["event_type"] == "vote"

    def test_member_detail_limit(self, memory_client, memories_dir):
        """Limit parameter restricts returned events."""
        sage_dir = memories_dir / "sage"
        sage_dir.mkdir()
        events = [
            {"timestamp": f"2026-01-01T{i:02d}:00:00+00:00", "session_id": "S-001",
             "event_type": "event", "content": f"Event {i}", "source": "", "metadata": {}}
            for i in range(10)
        ]
        (sage_dir / "session_log.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events),
            encoding="utf-8",
        )
        resp = memory_client.get("/api/memories/Sage?limit=3")
        data = resp.json()
        assert len(data["events"]) == 3
        assert data["event_count"] == 10  # total is still 10

    def test_member_detail_case_insensitive(self, memory_client):
        """Member lookup is case-insensitive."""
        resp = memory_client.get("/api/memories/sage")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Sage"

    def test_member_detail_not_found(self, memory_client):
        """Unknown member returns 404."""
        resp = memory_client.get("/api/memories/Nobody")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    # ── DELETE /api/memories/{member}/beliefs — Delete Belief ──

    def test_delete_belief_success(self, memory_client, memories_dir):
        """DELETE removes a belief and returns remaining count."""
        sage_dir = memories_dir / "sage"
        sage_dir.mkdir()
        beliefs = [
            {"topic": "safety", "content": "Safety first", "added_timestamp": "", "source": ""},
            {"topic": "ethics", "content": "Act ethically", "added_timestamp": "", "source": ""},
        ]
        (sage_dir / "core_beliefs.json").write_text(json.dumps(beliefs), encoding="utf-8")

        resp = memory_client.delete("/api/memories/Sage/beliefs?topic=safety")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "deleted"
        assert data["topic"] == "safety"
        assert data["remaining_beliefs"] == 1

        # Verify it's actually removed
        resp2 = memory_client.get("/api/memories/Sage")
        assert resp2.json()["belief_count"] == 1
        assert resp2.json()["beliefs"][0]["topic"] == "ethics"

    def test_delete_belief_missing_topic(self, memory_client):
        """DELETE without topic query param returns 400."""
        resp = memory_client.delete("/api/memories/Sage/beliefs")
        assert resp.status_code == 400
        assert "topic" in resp.json()["detail"]

    def test_delete_belief_unknown_topic(self, memory_client, memories_dir):
        """DELETE with non-existent topic returns 404."""
        sage_dir = memories_dir / "sage"
        sage_dir.mkdir()
        (sage_dir / "core_beliefs.json").write_text("[]", encoding="utf-8")

        resp = memory_client.delete("/api/memories/Sage/beliefs?topic=nonexistent")
        assert resp.status_code == 404
        assert "no belief" in resp.json()["detail"].lower()

    # ── GET /api/memories/shared — Shared Memory ──────────────

    def test_shared_memory_empty(self, memory_client):
        """Shared memory endpoint works with no data."""
        resp = memory_client.get("/api/memories/shared")
        assert resp.status_code == 200
        data = resp.json()
        assert data["decisions"] == []
        assert data["decision_count"] == 0
        assert data["history"] == ""

    def test_shared_memory_with_data(self, memory_client, memories_dir):
        """Shared memory returns decisions and history."""
        shared_dir = memories_dir / "shared"
        shared_dir.mkdir()

        decisions = [
            {"summary": "Approved character design", "timestamp": "2026-01-01T00:00:00+00:00"},
            {"summary": "Rejected expansion proposal", "timestamp": "2026-01-02T00:00:00+00:00"},
        ]
        (shared_dir / "decisions.jsonl").write_text(
            "\n".join(json.dumps(d) for d in decisions),
            encoding="utf-8",
        )
        (shared_dir / "history.md").write_text(
            "# Council History\n\nThe council was founded in 2026.",
            encoding="utf-8",
        )

        resp = memory_client.get("/api/memories/shared")
        data = resp.json()
        assert data["decision_count"] == 2
        assert data["decisions"][0]["summary"] == "Approved character design"
        assert "Council History" in data["history"]

    # ── GET /api/status — Memory stats ────────────────────────

    def test_status_includes_memories(self, memory_client, memories_dir):
        """Status endpoint includes memory statistics."""
        sage_dir = memories_dir / "sage"
        sage_dir.mkdir()
        (sage_dir / "core_beliefs.json").write_text(
            json.dumps([{"topic": "test", "content": "test", "added_timestamp": "", "source": ""}]),
            encoding="utf-8",
        )

        resp = memory_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "memories" in data
        assert data["memories"]["total_beliefs"] >= 1
        assert "members_with_memories" in data["memories"]


# ─── Evolutions Endpoints ────────────────────────────────────


def _make_evolution_record(
    evolution_id, character_id="CH-0001", author="Sage",
    status="draft", changes=None, proposal_id="", vote_record_id="",
    applied_character_id="",
):
    """Build a raw evolution JSON dict."""
    return {
        "evolution_id": evolution_id,
        "character_id": character_id,
        "author": author,
        "changes": changes or [
            {
                "change_type": "trait_add",
                "field_name": "brave",
                "old_value": "",
                "new_value": {
                    "trait_type": "personality",
                    "name": "Brave",
                    "description": "Fearless",
                    "intensity": 0.8,
                },
                "rationale": "Character needs bravery",
            },
        ],
        "proposal_id": proposal_id,
        "vote_record_id": vote_record_id,
        "status": status,
        "applied_character_id": applied_character_id,
        "summary": "",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "metadata": {},
    }


@pytest.fixture
def evolutions_dir(tmp_path):
    """Create a temporary evolutions directory."""
    d = tmp_path / "character_evolutions"
    d.mkdir()
    return d


@pytest.fixture
def evo_client(
    members_dir, proposals_dir, votes_dir, characters_dir,
    evolutions_dir, tmp_path,
):
    """TestClient with evolutions_dir also mocked."""
    static_dir = tmp_path / "web_static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<h1>Test</h1>", encoding="utf-8")

    avatars_dir = tmp_path / "council_avatars"
    avatars_dir.mkdir()

    with (
        patch("core.web_api.WEB_STATIC_DIR", static_dir),
        patch("core.web_api.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.web_api.EVOLUTION_DIR", evolutions_dir),
        patch("core.registry.COUNCIL_MEMBERS_DIR", members_dir),
        patch("core.proposals.PROPOSALS_DIR", proposals_dir),
        patch("core.voting.VOTES_DIR", votes_dir),
        patch("core.characters.CHARACTERS_DIR", characters_dir),
        patch("core.character_evolution.EVOLUTION_DIR", evolutions_dir),
        patch("config.settings.COUNCIL_AVATARS_DIR", avatars_dir),
    ):
        app = create_app()
        yield TestClient(app)


class TestApiEvolutions:
    """Tests for /api/evolutions endpoints."""

    # ── GET /api/evolutions — List ────────────────────────────

    def test_list_empty(self, evo_client):
        resp = evo_client.get("/api/evolutions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_records(self, evo_client, evolutions_dir):
        rec = _make_evolution_record("EV-0001")
        (evolutions_dir / "EV-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8",
        )
        resp = evo_client.get("/api/evolutions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["evolution_id"] == "EV-0001"

    def test_list_filter_by_status(self, evo_client, evolutions_dir):
        r1 = _make_evolution_record("EV-0001", status="draft")
        r2 = _make_evolution_record("EV-0002", status="proposed")
        (evolutions_dir / "EV-0001.json").write_text(
            json.dumps(r1, indent=2), encoding="utf-8",
        )
        (evolutions_dir / "EV-0002.json").write_text(
            json.dumps(r2, indent=2), encoding="utf-8",
        )
        resp = evo_client.get("/api/evolutions?status=draft")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["evolution_id"] == "EV-0001"

    def test_list_filter_by_character(self, evo_client, evolutions_dir):
        r1 = _make_evolution_record("EV-0001", character_id="CH-0001")
        r2 = _make_evolution_record("EV-0002", character_id="CH-0002")
        (evolutions_dir / "EV-0001.json").write_text(
            json.dumps(r1, indent=2), encoding="utf-8",
        )
        (evolutions_dir / "EV-0002.json").write_text(
            json.dumps(r2, indent=2), encoding="utf-8",
        )
        resp = evo_client.get("/api/evolutions?character_id=CH-0001")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["character_id"] == "CH-0001"

    # ── GET /api/evolutions/{id} — Detail ─────────────────────

    def test_detail_found(self, evo_client, evolutions_dir):
        rec = _make_evolution_record("EV-0001")
        (evolutions_dir / "EV-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8",
        )
        resp = evo_client.get("/api/evolutions/EV-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["evolution_id"] == "EV-0001"
        assert data["author"] == "Sage"
        assert len(data["changes"]) == 1

    def test_detail_not_found(self, evo_client):
        resp = evo_client.get("/api/evolutions/EV-9999")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    # ── POST /api/evolutions — Create ─────────────────────────

    def test_create_success(self, evo_client, evolutions_dir):
        resp = evo_client.post("/api/evolutions", json={
            "character_id": "CH-0001",
            "author": "Sage",
            "changes": [
                {
                    "change_type": "field_update",
                    "field_name": "backstory",
                    "new_value": "A new backstory",
                    "rationale": "More detail needed",
                },
            ],
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["evolution_id"].startswith("EV-")
        assert data["status"] == "draft"
        assert data["character_id"] == "CH-0001"
        assert len(data["changes"]) == 1

    def test_create_missing_fields(self, evo_client):
        resp = evo_client.post("/api/evolutions", json={
            "character_id": "",
            "author": "",
        })
        assert resp.status_code == 400
        assert "required" in resp.json()["detail"]

    def test_create_character_not_found(self, evo_client):
        resp = evo_client.post("/api/evolutions", json={
            "character_id": "CH-9999",
            "author": "Sage",
            "changes": [
                {
                    "change_type": "field_update",
                    "field_name": "backstory",
                    "new_value": "test",
                    "rationale": "test",
                },
            ],
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"]

    def test_create_character_not_active(
        self, evo_client, characters_dir,
    ):
        # Create a draft character
        draft_ch = {
            "id": "CH-0099",
            "name": "Draft",
            "description": "Draft character",
            "author": "Sage",
            "status": "draft",
            "backstory": "...",
            "traits": [
                {"trait_type": "personality", "name": "Shy",
                 "description": "Quiet", "intensity": 0.5},
            ],
            "system_prompt": "You are Draft.",
            "greeting": "",
            "example_messages": [],
            "tags": [],
            "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "metadata": {},
        }
        (characters_dir / "CH-0099.json").write_text(
            json.dumps(draft_ch, indent=2), encoding="utf-8",
        )
        resp = evo_client.post("/api/evolutions", json={
            "character_id": "CH-0099",
            "author": "Sage",
            "changes": [
                {
                    "change_type": "field_update",
                    "field_name": "backstory",
                    "new_value": "updated",
                    "rationale": "test",
                },
            ],
        })
        assert resp.status_code == 400
        assert "active" in resp.json()["detail"].lower()

    # ── GET /api/status — Evolutions count ────────────────────

    def test_status_includes_evolutions(self, evo_client, evolutions_dir):
        rec = _make_evolution_record("EV-0001")
        (evolutions_dir / "EV-0001.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8",
        )
        resp = evo_client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "evolutions" in data
        assert data["evolutions"]["count"] == 1
        assert "draft" in data["evolutions"]["by_status"]

    # ── GET /api/evolutions/timelines — List ──────────────────

    def test_timelines_list(self, evo_client):
        resp = evo_client.get("/api/evolutions/timelines")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # Should contain at least Atlas (our test character)
        assert len(data) >= 1
        assert data[0]["character_name"] == "Atlas"

    # ── GET /api/evolutions/timelines/{id} — Detail ───────────

    def test_timeline_detail(self, evo_client):
        resp = evo_client.get("/api/evolutions/timelines/CH-0001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_name"] == "Atlas"
        assert "version_chain" in data
        assert "snapshots" in data

    def test_timeline_detail_not_found(self, evo_client):
        resp = evo_client.get("/api/evolutions/timelines/CH-9999")
        assert resp.status_code == 404

    # ── GET /api/evolutions/diff — Diff ───────────────────────

    def test_diff_same_version(self, evo_client):
        resp = evo_client.get(
            "/api/evolutions/diff?old=CH-0001&new=CH-0001",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_id"] == "CH-0001"
        assert data["new_id"] == "CH-0001"
        assert "(no differences)" in data["diffs"]

    def test_diff_not_found(self, evo_client):
        resp = evo_client.get(
            "/api/evolutions/diff?old=CH-9999&new=CH-0001",
        )
        assert resp.status_code == 404


# ─── Council Promotion Endpoints ─────────────────────────────


class TestApiCouncilPromotion:
    """Tests for GET /api/council/candidates and POST /api/council/promote."""

    def test_candidates_lists_non_council_characters(self, client):
        """Active characters not on the council should appear as candidates."""
        resp = client.get("/api/council/candidates")
        assert resp.status_code == 200
        data = resp.json()
        # Atlas is active and not a council member (Sage, Logic are council)
        names = [c["name"] for c in data]
        assert "Atlas" in names
        # Council members should not appear
        assert "Sage" not in names
        assert "Logic" not in names

    def test_candidates_has_expected_fields(self, client):
        resp = client.get("/api/council/candidates")
        data = resp.json()
        assert len(data) >= 1
        candidate = data[0]
        for field in ("id", "name", "description", "status", "api_provider", "model"):
            assert field in candidate

    def test_candidates_excludes_non_active(self, client, characters_dir):
        """Draft characters should not appear as candidates."""
        draft_char = {
            "id": "CH-0002",
            "name": "Phantom",
            "description": "A draft character",
            "author": "Forge",
            "status": "draft",
            "backstory": "",
            "traits": [{"trait_type": "personality", "name": "Shy", "description": "Quiet", "intensity": 0.5}],
            "system_prompt": "You are Phantom.",
            "greeting": "",
            "example_messages": [],
            "tags": [],
            "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "metadata": {},
        }
        (characters_dir / "CH-0002.json").write_text(
            json.dumps(draft_char, indent=2), encoding="utf-8",
        )
        resp = client.get("/api/council/candidates")
        names = [c["name"] for c in resp.json()]
        assert "Phantom" not in names

    def test_candidates_excludes_same_name_as_council(self, client, characters_dir):
        """A character named 'Sage' (same as council member) should not appear."""
        sage_char = {
            "id": "CH-0003",
            "name": "Sage",
            "description": "An active character with same name",
            "author": "Forge",
            "status": "active",
            "backstory": "",
            "traits": [{"trait_type": "personality", "name": "Wise", "description": "Wise", "intensity": 0.9}],
            "system_prompt": "You are Sage the character.",
            "greeting": "",
            "example_messages": [],
            "tags": [],
            "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "metadata": {},
        }
        (characters_dir / "CH-0003.json").write_text(
            json.dumps(sage_char, indent=2), encoding="utf-8",
        )
        resp = client.get("/api/council/candidates")
        names = [c["name"] for c in resp.json()]
        assert "Sage" not in names

    def test_promote_success(self, client, members_dir):
        """Promote Atlas to council — should create YAML file."""
        resp = client.post("/api/council/promote", json={
            "character_id": "CH-0001",
            "role": "Explorer Lead",
            "role_description": "Leads expeditions and scouts new territories",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["name"] == "Atlas"
        assert data["role"] == "Explorer Lead"
        assert data["description"] == "Leads expeditions and scouts new territories"
        # YAML file should now exist
        yaml_path = members_dir / "atlas.yaml"
        assert yaml_path.exists()

    def test_promote_missing_role(self, client):
        resp = client.post("/api/council/promote", json={
            "character_id": "CH-0001",
            "role": "",
            "role_description": "Some duties",
        })
        assert resp.status_code == 400
        assert "role" in resp.json()["detail"].lower()

    def test_promote_missing_description(self, client):
        resp = client.post("/api/council/promote", json={
            "character_id": "CH-0001",
            "role": "Explorer",
            "role_description": "",
        })
        assert resp.status_code == 400
        assert "role_description" in resp.json()["detail"].lower()

    def test_promote_invalid_character(self, client):
        resp = client.post("/api/council/promote", json={
            "character_id": "CH-9999",
            "role": "Explorer",
            "role_description": "Duties",
        })
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_promote_already_on_council(self, client, characters_dir):
        """A character with the name of an existing council member can't be promoted."""
        sage_char = {
            "id": "CH-0010",
            "name": "Sage",
            "description": "Character named Sage",
            "author": "Forge",
            "status": "active",
            "backstory": "",
            "traits": [{"trait_type": "personality", "name": "Wise", "description": "Wise", "intensity": 0.9}],
            "system_prompt": "You are Sage.",
            "greeting": "",
            "example_messages": [],
            "tags": [],
            "version": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
            "metadata": {},
        }
        (characters_dir / "CH-0010.json").write_text(
            json.dumps(sage_char, indent=2), encoding="utf-8",
        )
        resp = client.post("/api/council/promote", json={
            "character_id": "CH-0010",
            "role": "Advisor",
            "role_description": "Advises",
        })
        assert resp.status_code == 400
        assert "already" in resp.json()["detail"].lower()

