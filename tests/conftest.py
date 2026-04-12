"""
Jericho — Shared Test Fixtures (F-017)

Reusable pytest fixtures for integration and unit tests.
Consolidates directory setup, mock objects, and manager factories
that were previously duplicated across test files.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.api_client import ChatResponse
from core.characters import CharacterManager, CharacterTemplate, Trait
from core.locations import LocationManager
from core.manager_cache import invalidate_all
from core.memory import AgentMemory, SharedMemory
from core.proposals import ProposalManager
from core.registry import CouncilMember, CouncilRegistry
from core.voting import VotingEngine


# ─── Cache Invalidation ───────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_manager_cache():
    """Invalidate the manager singleton cache before every test.

    This ensures test-provided mocks and tmp-directory managers
    are not bypassed by a stale singleton from a previous test.
    """
    invalidate_all()
    yield
    invalidate_all()


# ─── Directory Fixtures ────────────────────────────────────────


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> dict[str, Path]:
    """Create all standard project subdirectories under tmp_path."""
    dirs = {
        "proposals": tmp_path / "proposals",
        "votes": tmp_path / "votes",
        "characters": tmp_path / "characters",
        "evolutions": tmp_path / "evolutions",
        "conversations": tmp_path / "conversations",
        "discussions": tmp_path / "discussions",
        "designs": tmp_path / "designs",
        "memories": tmp_path / "memories",
        "shared": tmp_path / "memories" / "shared",
        "locations": tmp_path / "locations",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


# ─── Council Member Helpers ────────────────────────────────────


def make_member(
    name: str = "Sage",
    role: str = "Ethics",
    api_provider: str = "openrouter",
    model: str = "test-model",
) -> CouncilMember:
    """Create a CouncilMember with sensible defaults."""
    return CouncilMember(
        name=name,
        role=role,
        description=f"{name} description",
        api_provider=api_provider,
        model=model,
        system_prompt=f"You are {name}.",
    )


def mock_registry(*members: CouncilMember) -> CouncilRegistry:
    """Build a mock registry pre-loaded with the given members."""
    reg = MagicMock(spec=CouncilRegistry)
    member_dict = {m.name.lower(): m for m in members}
    reg.get.side_effect = lambda name: member_dict[name.strip().lower()]
    reg.list_names.return_value = [m.name for m in members]
    reg.list_members.return_value = list(members)
    reg.__len__ = lambda self: len(members)
    reg.__contains__ = lambda self, n: n.strip().lower() in member_dict
    return reg


def mock_api_client(content: str = "Acknowledged.") -> AsyncMock:
    """Build mock async API client that returns a canned ChatResponse."""
    client = AsyncMock()
    client.chat = AsyncMock(return_value=ChatResponse(
        content=content,
        model="test-model",
        provider="openrouter",
    ))
    return client


# ─── Standard Members ──────────────────────────────────────────


SAGE = make_member("Sage", "Ethics")
LOGIC = make_member("Logic", "Systems")
SPARK = make_member("Spark", "Creative", api_provider="mancer")


@pytest.fixture
def members():
    """Three standard council members: Sage, Logic, Spark."""
    return SAGE, LOGIC, SPARK


@pytest.fixture
def registry(members):
    """A mock CouncilRegistry loaded with standard members."""
    return mock_registry(*members)


@pytest.fixture
def api_client():
    """A mock async API client returning 'Acknowledged.'."""
    return mock_api_client()


# ─── Manager Factories ────────────────────────────────────────


@pytest.fixture
def proposal_mgr(tmp_dirs: dict[str, Path]) -> ProposalManager:
    """ProposalManager backed by tmp directory."""
    return ProposalManager(proposals_dir=tmp_dirs["proposals"])


@pytest.fixture
def voting_engine(tmp_dirs: dict[str, Path]) -> VotingEngine:
    """VotingEngine (quorum=2, threshold=60%) backed by tmp directory."""
    return VotingEngine(
        votes_dir=tmp_dirs["votes"], quorum=2, threshold=0.6,
    )


@pytest.fixture
def character_mgr(tmp_dirs: dict[str, Path]) -> CharacterManager:
    """CharacterManager backed by tmp directory."""
    return CharacterManager(characters_dir=tmp_dirs["characters"])


@pytest.fixture
def shared_memory(tmp_dirs: dict[str, Path]) -> SharedMemory:
    """SharedMemory backed by tmp directory."""
    return SharedMemory(shared_dir=tmp_dirs["shared"])


@pytest.fixture
def location_mgr(tmp_dirs: dict[str, Path]) -> LocationManager:
    """LocationManager backed by tmp directory."""
    return LocationManager(locations_dir=tmp_dirs["locations"])
