"""
Tests for core.registry — Council Member Registry (F-003)
"""

import pytest
import yaml
from pathlib import Path

from core.registry import (
    CouncilMember,
    CouncilRegistry,
    MemberNotFoundError,
    RegistryValidationError,
    REQUIRED_FIELDS,
    VALID_API_PROVIDERS,
)
from config.settings import COUNCIL_MEMBERS_DIR


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def registry() -> CouncilRegistry:
    """A registry loaded from the real council/members/ directory."""
    return CouncilRegistry().load()


@pytest.fixture
def empty_registry(tmp_path: Path) -> CouncilRegistry:
    """A registry pointed at an empty directory."""
    return CouncilRegistry(members_dir=tmp_path).load()


def _write_yaml(directory: Path, filename: str, data: dict) -> Path:
    """Helper to write a YAML file into a directory."""
    filepath = directory / filename
    with open(filepath, "w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return filepath


def _minimal_member_data(**overrides) -> dict:
    """Return a minimal valid member data dict, with optional overrides."""
    base = {
        "name": "TestAgent",
        "role": "Tester",
        "description": "A test council member",
        "api_provider": "openrouter",
        "model": "anthropic/claude-3.5-sonnet",
        "system_prompt": "You are a test agent.",
    }
    base.update(overrides)
    return base


# ─── Loading Tests ─────────────────────────────────────────────


class TestRegistryLoading:
    """Tests for loading council members from YAML files."""

    def test_load_real_members(self, registry: CouncilRegistry) -> None:
        """The real council/members/ directory should have 9 members."""
        assert len(registry) == 9

    def test_load_returns_self(self) -> None:
        """load() returns self for chaining."""
        reg = CouncilRegistry()
        result = reg.load()
        assert result is reg

    def test_all_expected_names_present(self, registry: CouncilRegistry) -> None:
        """All 9 known council members should be present."""
        expected = {"Anchor", "Drift", "Echo", "Forge", "Lens", "Logic", "Pulse", "Sage", "Spark"}
        actual = set(registry.list_names())
        assert actual == expected

    def test_load_empty_directory(self, empty_registry: CouncilRegistry) -> None:
        """Loading from an empty directory yields zero members."""
        assert len(empty_registry) == 0
        assert empty_registry.list_names() == []

    def test_load_nonexistent_directory(self, tmp_path: Path) -> None:
        """Loading from a nonexistent directory raises FileNotFoundError."""
        bad_dir = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            CouncilRegistry(members_dir=bad_dir).load()

    def test_load_single_custom_member(self, tmp_path: Path) -> None:
        """A single valid YAML file should produce a single member."""
        _write_yaml(tmp_path, "alpha.yaml", _minimal_member_data(name="Alpha"))
        reg = CouncilRegistry(members_dir=tmp_path).load()
        assert len(reg) == 1
        assert reg.get("Alpha").role == "Tester"

    def test_load_duplicate_name_raises(self, tmp_path: Path) -> None:
        """Two YAML files with the same member name should raise RegistryValidationError."""
        _write_yaml(tmp_path, "a.yaml", _minimal_member_data(name="Dupe"))
        _write_yaml(tmp_path, "b.yaml", _minimal_member_data(name="Dupe"))
        with pytest.raises(RegistryValidationError, match="Duplicate member name"):
            CouncilRegistry(members_dir=tmp_path).load()

    def test_load_empty_yaml_raises(self, tmp_path: Path) -> None:
        """An empty YAML file should raise RegistryValidationError."""
        filepath = tmp_path / "empty.yaml"
        filepath.write_text("", encoding="utf-8")
        with pytest.raises(RegistryValidationError, match="empty"):
            CouncilRegistry(members_dir=tmp_path).load()


# ─── Query Tests ───────────────────────────────────────────────


class TestRegistryQueries:
    """Tests for querying members from a loaded registry."""

    def test_get_by_exact_name(self, registry: CouncilRegistry) -> None:
        member = registry.get("Sage")
        assert member.name == "Sage"
        assert member.role == "Ethics Advisor"

    def test_get_case_insensitive_lower(self, registry: CouncilRegistry) -> None:
        member = registry.get("sage")
        assert member.name == "Sage"

    def test_get_case_insensitive_upper(self, registry: CouncilRegistry) -> None:
        member = registry.get("SAGE")
        assert member.name == "Sage"

    def test_get_case_insensitive_mixed(self, registry: CouncilRegistry) -> None:
        member = registry.get("sAgE")
        assert member.name == "Sage"

    def test_get_with_whitespace_stripped(self, registry: CouncilRegistry) -> None:
        member = registry.get("  Sage  ")
        assert member.name == "Sage"

    def test_get_nonexistent_raises(self, registry: CouncilRegistry) -> None:
        with pytest.raises(MemberNotFoundError):
            registry.get("NonExistent")

    def test_member_not_found_error_has_name(self) -> None:
        err = MemberNotFoundError("Ghost")
        assert err.name == "Ghost"
        assert "Ghost" in str(err)

    def test_list_members_sorted(self, registry: CouncilRegistry) -> None:
        members = registry.list_members()
        names = [m.name for m in members]
        assert names == sorted(names, key=str.lower)

    def test_list_names_sorted(self, registry: CouncilRegistry) -> None:
        names = registry.list_names()
        assert names == sorted(names, key=str.lower)

    def test_members_by_provider_openrouter(self, registry: CouncilRegistry) -> None:
        openrouter_members = registry.members_by_provider("openrouter")
        assert len(openrouter_members) == 6
        assert all(m.api_provider == "openrouter" for m in openrouter_members)

    def test_members_by_provider_mancer(self, registry: CouncilRegistry) -> None:
        mancer_members = registry.members_by_provider("mancer")
        assert len(mancer_members) == 3
        assert all(m.api_provider == "mancer" for m in mancer_members)


# ─── CouncilMember Tests ──────────────────────────────────────


class TestCouncilMember:
    """Tests for the CouncilMember dataclass."""

    def test_sage_fields(self, registry: CouncilRegistry) -> None:
        sage = registry.get("Sage")
        assert sage.name == "Sage"
        assert sage.role == "Ethics Advisor"
        assert sage.api_provider == "openrouter"
        assert sage.model == "anthropic/claude-3.5-sonnet"
        assert sage.vote_weight == 1.0
        assert "ethics" in sage.specialties
        assert sage.source_file is not None
        assert sage.source_file.name == "sage.yaml"
        assert isinstance(sage.personality, dict)
        assert "traits" in sage.personality
        assert "thoughtful" in sage.personality["traits"]
        assert len(sage.system_prompt) > 0

    def test_drift_uses_mancer(self, registry: CouncilRegistry) -> None:
        drift = registry.get("Drift")
        assert drift.api_provider == "mancer"
        assert drift.is_mancer is True
        assert drift.is_openrouter is False

    def test_sage_uses_openrouter(self, registry: CouncilRegistry) -> None:
        sage = registry.get("Sage")
        assert sage.is_openrouter is True
        assert sage.is_mancer is False

    def test_frozen_dataclass(self, registry: CouncilRegistry) -> None:
        sage = registry.get("Sage")
        with pytest.raises(AttributeError):
            sage.name = "Modified"  # type: ignore[misc]


# ─── Validation Tests ──────────────────────────────────────────


class TestValidation:
    """Tests for the validate() static method."""

    def test_valid_minimal_data(self) -> None:
        errors = CouncilRegistry.validate(_minimal_member_data())
        assert errors == []

    def test_missing_name(self) -> None:
        data = _minimal_member_data()
        del data["name"]
        errors = CouncilRegistry.validate(data)
        assert any("name" in e for e in errors)

    def test_missing_multiple_fields(self) -> None:
        data = _minimal_member_data()
        del data["name"]
        del data["role"]
        errors = CouncilRegistry.validate(data)
        assert len(errors) >= 2

    def test_invalid_api_provider(self) -> None:
        data = _minimal_member_data(api_provider="invalid_provider")
        errors = CouncilRegistry.validate(data)
        assert any("api_provider" in e for e in errors)

    def test_negative_vote_weight(self) -> None:
        data = _minimal_member_data(vote_weight=-1.0)
        errors = CouncilRegistry.validate(data)
        assert any("vote_weight" in e for e in errors)

    def test_zero_vote_weight(self) -> None:
        data = _minimal_member_data(vote_weight=0)
        errors = CouncilRegistry.validate(data)
        assert any("vote_weight" in e for e in errors)

    def test_string_vote_weight(self) -> None:
        data = _minimal_member_data(vote_weight="heavy")
        errors = CouncilRegistry.validate(data)
        assert any("vote_weight" in e for e in errors)

    def test_personality_not_dict(self) -> None:
        data = _minimal_member_data(personality="not a dict")
        errors = CouncilRegistry.validate(data)
        assert any("personality" in e for e in errors)

    def test_specialties_not_list(self) -> None:
        data = _minimal_member_data(specialties="not a list")
        errors = CouncilRegistry.validate(data)
        assert any("specialties" in e for e in errors)

    def test_non_dict_input(self) -> None:
        errors = CouncilRegistry.validate("not a dict")  # type: ignore[arg-type]
        assert any("mapping" in e for e in errors)

    def test_malformed_yaml_file_raises(self, tmp_path: Path) -> None:
        """A YAML file with missing required fields should raise on load()."""
        _write_yaml(tmp_path, "bad.yaml", {"name": "Incomplete"})
        with pytest.raises(RegistryValidationError):
            CouncilRegistry(members_dir=tmp_path).load()


# ─── Dunder Method Tests ──────────────────────────────────────


class TestDunderMethods:
    """Tests for __len__, __contains__, __iter__, __repr__."""

    def test_len(self, registry: CouncilRegistry) -> None:
        assert len(registry) == 9

    def test_contains_case_insensitive(self, registry: CouncilRegistry) -> None:
        assert "Sage" in registry
        assert "sage" in registry
        assert "SAGE" in registry

    def test_not_contains(self, registry: CouncilRegistry) -> None:
        assert "Ghost" not in registry

    def test_iter(self, registry: CouncilRegistry) -> None:
        members = list(registry)
        assert len(members) == 9
        assert all(isinstance(m, CouncilMember) for m in members)

    def test_repr(self, registry: CouncilRegistry) -> None:
        r = repr(registry)
        assert "CouncilRegistry" in r
        assert "9" in r
