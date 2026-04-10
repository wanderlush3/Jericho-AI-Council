"""
Tests for F-042: Participant System (Explore Section).

Covers:
- GET /api/participants/available — merged council + character list
- POST /api/explore/{location_id}/look-around — participants integration
- Max 10 participant validation
- Backward compatibility (no participants)
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from dataclasses import dataclass, field

from fastapi.testclient import TestClient


# ─── Helpers ───────────────────────────────────────────────────


@dataclass(frozen=True)
class _FakeCouncilMember:
    name: str
    role: str
    description: str
    personality: dict = field(default_factory=dict)
    api_provider: str = "openrouter"
    model: str = "test-model"
    vote_weight: float = 1.0
    specialties: list = field(default_factory=list)
    system_prompt: str = ""
    source_file: Path | None = None


@dataclass
class _FakeCharacter:
    id: str
    name: str
    description: str = ""
    backstory: str = ""
    system_prompt: str = ""
    status: str = "active"
    traits: list = field(default_factory=list)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "backstory": self.backstory,
            "system_prompt": self.system_prompt,
            "status": self.status,
        }


@dataclass
class _FakeLocation:
    id: str
    name: str
    description: str
    status: str = "active"
    lore: str = ""
    coordinates: str = ""
    tags: list = field(default_factory=list)
    features: list = field(default_factory=list)
    parent_location_id: str | None = None


_FAKE_COUNCIL = [
    _FakeCouncilMember(
        name="Sage",
        role="Ethics Advisor",
        description="Guides moral decisions",
        system_prompt="You are Sage, an ethics expert.",
        specialties=["ethics", "philosophy"],
    ),
    _FakeCouncilMember(
        name="Nova",
        role="Innovation Lead",
        description="Drives creative solutions",
        system_prompt="You are Nova, a creative thinker.",
    ),
]

_FAKE_CHARS = [
    _FakeCharacter(
        id="CH-0001",
        name="Atlas",
        description="An adventurous explorer",
        backstory="Born in the wilds",
        system_prompt="You are Atlas.",
    ),
    _FakeCharacter(
        id="CH-0002",
        name="Luna",
        description="A mysterious scholar",
        backstory="Studied ancient texts",
        system_prompt="You are Luna.",
    ),
]

_FAKE_LOC = _FakeLocation(
    id="LOC-0001",
    name="Ironhaven",
    description="A bustling port city",
    lore="Founded by sea traders.",
)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def fake_avatar_dirs(tmp_path):
    """Create empty avatar dirs."""
    council_dir = tmp_path / "council_avatars"
    council_dir.mkdir()
    char_dir = tmp_path / "character_avatars"
    char_dir.mkdir()
    return council_dir, char_dir


@pytest.fixture
def client(tmp_path, fake_avatar_dirs):
    """Create a test FastAPI client with mocked managers."""
    from core.exploration import ExplorationManager

    council_av_dir, char_av_dir = fake_avatar_dirs
    exploration_dir = tmp_path / "exploration"
    exploration_dir.mkdir()
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    locations_dir = tmp_path / "locations"
    locations_dir.mkdir()
    scenes_file = exploration_dir / "scenes.json"

    # Real exploration manager
    real_expl_mgr = ExplorationManager(
        scenes_file=scenes_file,
        exploration_dir=exploration_dir,
    )

    # Mock LocationManager
    mock_loc_mgr = MagicMock()
    mock_loc_mgr.get.side_effect = _loc_get
    mock_loc_mgr.list_locations.return_value = [_FAKE_LOC]

    # Mock council registry
    mock_registry = MagicMock()
    mock_registry.load.return_value = mock_registry
    mock_registry.list_members.return_value = list(_FAKE_COUNCIL)

    # Mock character manager
    mock_char_mgr = MagicMock()
    mock_char_mgr.list_characters.return_value = list(_FAKE_CHARS)
    mock_char_mgr.get.side_effect = _char_get

    # Mock image manager
    from core.image_manager import ImageManager
    real_img_mgr = ImageManager(images_dir=images_dir)

    with patch("core.locations.LocationManager", return_value=mock_loc_mgr), \
         patch("core.exploration.ExplorationManager", return_value=real_expl_mgr) as MockExplMgr, \
         patch("core.image_manager.ImageManager", return_value=real_img_mgr), \
         patch("core.characters.CharacterManager", return_value=mock_char_mgr), \
         patch("core.registry.CouncilRegistry", return_value=mock_registry), \
         patch("config.settings.COUNCIL_AVATARS_DIR", council_av_dir), \
         patch("config.settings.CHARACTER_AVATARS_DIR", char_av_dir):

        MockExplMgr.get_navigation_targets = ExplorationManager.get_navigation_targets
        MockExplMgr.build_look_around_description = ExplorationManager.build_look_around_description

        from core.web_api import create_app
        app = create_app()
        yield TestClient(app)


def _loc_get(location_id):
    if location_id == _FAKE_LOC.id:
        return _FAKE_LOC
    from core.locations import LocationNotFoundError
    raise LocationNotFoundError(location_id)


def _char_get(char_id):
    for c in _FAKE_CHARS:
        if c.id == char_id:
            return c
    from core.characters import CharacterNotFoundError
    raise CharacterNotFoundError(char_id)


# ─── Participants Available Tests ──────────────────────────────


class TestParticipantsAvailable:
    """Tests for GET /api/participants/available."""

    def test_returns_list(self, client):
        resp = client.get("/api/participants/available")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_includes_council_members(self, client):
        resp = client.get("/api/participants/available")
        data = resp.json()
        council = [p for p in data if p["type"] == "council"]
        assert len(council) == 2
        names = {p["name"] for p in council}
        assert "Sage" in names
        assert "Nova" in names

    def test_includes_active_characters(self, client):
        resp = client.get("/api/participants/available")
        data = resp.json()
        characters = [p for p in data if p["type"] == "character"]
        assert len(characters) == 2
        names = {p["name"] for p in characters}
        assert "Atlas" in names
        assert "Luna" in names

    def test_participant_fields(self, client):
        resp = client.get("/api/participants/available")
        data = resp.json()
        assert len(data) == 4  # 2 council + 2 characters
        for p in data:
            assert "id" in p
            assert "name" in p
            assert "type" in p
            assert p["type"] in ("council", "character")
            assert "description" in p
            assert "avatar_url" in p

    def test_council_ids_lowercase(self, client):
        resp = client.get("/api/participants/available")
        data = resp.json()
        council = [p for p in data if p["type"] == "council"]
        for p in council:
            assert p["id"] == p["id"].lower()
            assert p["id"] == p["name"].lower()

    def test_character_ids_are_original(self, client):
        resp = client.get("/api/participants/available")
        data = resp.json()
        characters = [p for p in data if p["type"] == "character"]
        ids = {p["id"] for p in characters}
        assert "CH-0001" in ids
        assert "CH-0002" in ids

    def test_roles_present_for_council(self, client):
        resp = client.get("/api/participants/available")
        data = resp.json()
        council = [p for p in data if p["type"] == "council"]
        for p in council:
            assert p.get("role"), f"No role for {p['name']}"


# ─── Look Around with Participants Tests ─────────────────────


class TestLookAroundParticipants:
    """Tests for POST /api/explore/{location_id}/look-around with participants."""

    def test_look_around_participants_too_many(self, client):
        """Reject when more than 10 participants."""
        participants = [
            {"id": f"member-{i}", "type": "council"}
            for i in range(11)
        ]
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": participants},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"]
        assert "Too many participants" in detail
        assert "Maximum is 10" in detail

    def test_look_around_11_participants_rejected(self, client):
        """Exactly 11 participants should be rejected."""
        participants = [
            {"id": f"p-{i}", "type": "character"}
            for i in range(11)
        ]
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": participants},
        )
        assert resp.status_code == 400

    def test_look_around_participants_exactly_10(self, client):
        """10 participants should pass validation (may fail at template)."""
        participants = [
            {"id": f"member-{i}", "type": "council"}
            for i in range(10)
        ]
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": participants},
        )
        # Should not fail on participant-count validation
        if resp.status_code == 400:
            detail = resp.json()["detail"]
            assert "Too many participants" not in detail

    def test_look_around_participants_not_list(self, client):
        """Reject when participants is not a list."""
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": "sage"},
        )
        assert resp.status_code == 400
        assert "'participants' must be a list" in resp.json()["detail"]

    def test_look_around_participants_string_dict(self, client):
        """Reject when participants is a dict."""
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": {"id": "sage"}},
        )
        assert resp.status_code == 400
        assert "'participants' must be a list" in resp.json()["detail"]

    def test_look_around_empty_participants(self, client):
        """Empty participants list is fine (backward compatible)."""
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": []},
        )
        # Should pass participant validation; may fail on template
        if resp.status_code == 400:
            detail = resp.json()["detail"]
            assert "participant" not in detail.lower()

    def test_look_around_no_participants_key(self, client):
        """Missing participants key is backward compatible."""
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={},
        )
        # Should pass participant validation; may fail on template
        if resp.status_code == 400:
            detail = resp.json()["detail"]
            assert "participant" not in detail.lower()

    def test_look_around_location_not_found(self, client):
        """404 for non-existent location."""
        resp = client.post(
            "/api/explore/LOC-9999/look-around",
            json={"participants": []},
        )
        assert resp.status_code == 404


# ─── Mixed Participant Tests ────────────────────────────────


class TestMixedParticipants:
    """Test mixed council + character participant combinations."""

    def test_mixed_participants_passes_validation(self, client):
        """Mix of council and character participants is accepted."""
        participants = [
            {"id": "sage", "type": "council"},
            {"id": "nova", "type": "council"},
            {"id": "CH-0001", "type": "character"},
        ]
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": participants},
        )
        # Should not fail on participant validation
        if resp.status_code == 400:
            detail = resp.json()["detail"]
            assert "participant" not in detail.lower()

    def test_max_boundary_mixed(self, client):
        """Exactly 10 mixed participants passes validation."""
        participants = [
            {"id": f"council-{i}", "type": "council"}
            for i in range(5)
        ] + [
            {"id": f"CH-{i:04d}", "type": "character"}
            for i in range(5)
        ]
        assert len(participants) == 10
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": participants},
        )
        if resp.status_code == 400:
            detail = resp.json()["detail"]
            assert "Too many participants" not in detail

    def test_slightly_over_max_mixed(self, client):
        """11 mixed participants is rejected."""
        participants = [
            {"id": f"council-{i}", "type": "council"}
            for i in range(6)
        ] + [
            {"id": f"CH-{i:04d}", "type": "character"}
            for i in range(5)
        ]
        assert len(participants) == 11
        resp = client.post(
            f"/api/explore/{_FAKE_LOC.id}/look-around",
            json={"participants": participants},
        )
        assert resp.status_code == 400
        assert "Too many participants" in resp.json()["detail"]
