"""
Tests for core/council_expansion.py — Council Expansion (F-019)

Covers: data models, lifecycle transitions, governance integration
(proposals + voting), YAML generation, query methods, and edge cases.
"""

from __future__ import annotations

import json
import yaml
import pytest
from pathlib import Path
from typing import Any

from core.council_expansion import (
    CouncilExpansion,
    ExpansionError,
    ExpansionNotFoundError,
    ExpansionRecord,
    ExpansionStateError,
    ExpansionValidationError,
    MemberSpec,
)
from core.registry import CouncilRegistry, CouncilMember
from core.proposals import ProposalManager
from core.voting import Vote, VotingEngine
from core.memory import SharedMemory


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def exp_dir(tmp_path: Path) -> Path:
    d = tmp_path / "expansions"
    d.mkdir()
    return d


@pytest.fixture
def members_dir(tmp_path: Path) -> Path:
    d = tmp_path / "members"
    d.mkdir()
    return d


@pytest.fixture
def proposals_dir(tmp_path: Path) -> Path:
    d = tmp_path / "proposals"
    d.mkdir()
    return d


@pytest.fixture
def votes_dir(tmp_path: Path) -> Path:
    d = tmp_path / "votes"
    d.mkdir()
    return d


@pytest.fixture
def shared_dir(tmp_path: Path) -> Path:
    d = tmp_path / "shared"
    d.mkdir()
    return d


@pytest.fixture
def registry(members_dir: Path) -> CouncilRegistry:
    """Create a registry with a few initial members."""
    for name, role, provider in [
        ("Sage", "Ethics Advisor", "openrouter"),
        ("Spark", "Creative Director", "openrouter"),
        ("Logic", "Systems Analyst", "mancer"),
    ]:
        filepath = members_dir / f"{name.lower()}.yaml"
        data = {
            "name": name,
            "role": role,
            "description": f"{name} description",
            "api_provider": provider,
            "model": "test-model",
            "system_prompt": f"You are {name}.",
        }
        filepath.write_text(
            yaml.dump(data, default_flow_style=False), encoding="utf-8"
        )
    return CouncilRegistry(members_dir=members_dir).load()


@pytest.fixture
def proposals(proposals_dir: Path) -> ProposalManager:
    return ProposalManager(proposals_dir=proposals_dir)


@pytest.fixture
def voting(votes_dir: Path) -> VotingEngine:
    return VotingEngine(votes_dir=votes_dir, quorum=2, threshold=0.6)


@pytest.fixture
def shared_memory(shared_dir: Path) -> SharedMemory:
    return SharedMemory(shared_dir=shared_dir)


@pytest.fixture
def expansion(
    registry: CouncilRegistry,
    proposals: ProposalManager,
    voting: VotingEngine,
    exp_dir: Path,
    members_dir: Path,
    shared_memory: SharedMemory,
) -> CouncilExpansion:
    return CouncilExpansion(
        registry=registry,
        proposal_manager=proposals,
        voting_engine=voting,
        expansions_dir=exp_dir,
        members_dir=members_dir,
        shared_memory=shared_memory,
    )


def _make_spec(**kwargs: Any) -> MemberSpec:
    """Helper to create a MemberSpec with sensible defaults."""
    defaults = {
        "name": "Nova",
        "role": "Innovation Advisor",
        "description": "Explores new ideas and unconventional solutions",
        "api_provider": "openrouter",
        "model": "anthropic/claude-3.5-sonnet",
        "system_prompt": "You are Nova, the Innovation Advisor on the Jericho Council.",
    }
    defaults.update(kwargs)
    return MemberSpec.create(**defaults)


# ─── TestMemberSpec ───────────────────────────────────────────


class TestMemberSpec:
    """Tests for the MemberSpec data class."""

    def test_fields(self) -> None:
        s = MemberSpec(
            name="Nova",
            role="Innovation",
            description="New ideas",
            api_provider="openrouter",
            model="test-model",
            system_prompt="You are Nova.",
        )
        assert s.name == "Nova"
        assert s.role == "Innovation"
        assert s.api_provider == "openrouter"
        assert s.vote_weight == 1.0

    def test_frozen(self) -> None:
        s = _make_spec()
        with pytest.raises(AttributeError):
            s.name = "Other"  # type: ignore[misc]

    def test_roundtrip(self) -> None:
        s = _make_spec(
            personality={"traits": ["curious"]},
            specialties=["innovation"],
        )
        restored = MemberSpec.from_dict(s.to_dict())
        assert restored.name == s.name
        assert restored.role == s.role
        assert restored.personality == {"traits": ["curious"]}
        assert restored.specialties == ["innovation"]

    def test_create_factory(self) -> None:
        s = MemberSpec.create(
            "Nova", "Innovation", "New ideas",
            api_provider="mancer",
            model="test-model",
            system_prompt="You are Nova.",
        )
        assert s.name == "Nova"
        assert s.api_provider == "mancer"

    def test_to_yaml(self) -> None:
        s = _make_spec(
            specialties=["innovation", "creativity"],
            personality={"traits": ["bold", "curious"]},
        )
        yaml_str = s.to_yaml()
        assert "# Council Member: Nova — Innovation Advisor" in yaml_str
        parsed = yaml.safe_load(yaml_str.split("\n", 1)[1])  # skip comment
        assert parsed["name"] == "Nova"
        assert parsed["role"] == "Innovation Advisor"
        assert parsed["api_provider"] == "openrouter"
        assert parsed["specialties"] == ["innovation", "creativity"]

    def test_invalid_provider(self) -> None:
        with pytest.raises(ExpansionValidationError, match="Invalid api_provider"):
            MemberSpec.create(
                "Nova", "Role", "Desc",
                api_provider="bad_provider",
                model="m", system_prompt="p",
            )

    def test_empty_name(self) -> None:
        with pytest.raises(ExpansionValidationError, match="Name must not be empty"):
            MemberSpec.create(
                "  ", "Role", "Desc",
                api_provider="openrouter",
                model="m", system_prompt="p",
            )


# ─── TestExpansionRecord ──────────────────────────────────────


class TestExpansionRecord:
    """Tests for the ExpansionRecord data class."""

    def test_fields(self) -> None:
        spec = _make_spec()
        r = ExpansionRecord(
            expansion_id="CE-0001",
            author="Sage",
            member_spec=spec,
        )
        assert r.expansion_id == "CE-0001"
        assert r.author == "Sage"
        assert r.status == "draft"
        assert r.member_spec.name == "Nova"

    def test_frozen(self) -> None:
        spec = _make_spec()
        r = ExpansionRecord.create("CE-0001", "Sage", spec)
        with pytest.raises(AttributeError):
            r.status = "applied"  # type: ignore[misc]

    def test_roundtrip(self) -> None:
        spec = _make_spec()
        r = ExpansionRecord.create(
            "CE-0001", "Sage", spec, metadata={"key": "value"},
        )
        restored = ExpansionRecord.from_dict(r.to_dict())
        assert restored.expansion_id == r.expansion_id
        assert restored.author == r.author
        assert restored.member_spec.name == "Nova"
        assert restored.metadata == {"key": "value"}

    def test_create_factory(self) -> None:
        spec = _make_spec()
        r = ExpansionRecord.create("CE-0001", "Sage", spec)
        assert r.status == "draft"
        assert r.created_at != ""
        assert r.updated_at != ""

    def test_empty_id(self) -> None:
        spec = _make_spec()
        with pytest.raises(ExpansionValidationError, match="Expansion ID"):
            ExpansionRecord.create("", "Sage", spec)

    def test_empty_author(self) -> None:
        spec = _make_spec()
        with pytest.raises(ExpansionValidationError, match="Author"):
            ExpansionRecord.create("CE-0001", "  ", spec)

    def test_whitespace_strip(self) -> None:
        spec = _make_spec()
        r = ExpansionRecord.create("  CE-0001  ", "  Sage  ", spec)
        assert r.expansion_id == "CE-0001"
        assert r.author == "Sage"


# ─── TestCouncilExpansionInit ─────────────────────────────────


class TestCouncilExpansionInit:
    """Tests for CouncilExpansion initialization."""

    def test_dir_creation(
        self,
        registry: CouncilRegistry,
        proposals: ProposalManager,
        voting: VotingEngine,
        tmp_path: Path,
    ) -> None:
        new_dir = tmp_path / "new_exp"
        exp = CouncilExpansion(
            registry=registry,
            proposal_manager=proposals,
            voting_engine=voting,
            expansions_dir=new_dir,
        )
        assert exp.directory.exists()

    def test_properties(self, expansion: CouncilExpansion) -> None:
        assert expansion.registry is not None
        assert expansion.proposal_manager is not None
        assert expansion.voting_engine is not None

    def test_repr(self, expansion: CouncilExpansion) -> None:
        r = repr(expansion)
        assert "CouncilExpansion" in r
        assert "records=0" in r


# ─── TestCreateExpansion ──────────────────────────────────────


class TestCreateExpansion:
    """Tests for creating expansion records."""

    def test_basic(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        assert rec.expansion_id == "CE-0001"
        assert rec.author == "Sage"
        assert rec.status == "draft"
        assert rec.member_spec.name == "Nova"

    def test_sequential_ids(self, expansion: CouncilExpansion) -> None:
        r1 = expansion.create_expansion(_make_spec(name="Nova1"), author="Sage")
        r2 = expansion.create_expansion(_make_spec(name="Nova2"), author="Sage")
        assert r1.expansion_id == "CE-0001"
        assert r2.expansion_id == "CE-0002"

    def test_persistence(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        reloaded = expansion.get(rec.expansion_id)
        assert reloaded.member_spec.name == "Nova"
        assert reloaded.author == "Sage"

    def test_with_metadata(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(
            spec, author="Sage", metadata={"priority": "high"},
        )
        assert rec.metadata == {"priority": "high"}

    def test_exceeds_max_council_size(
        self,
        proposals: ProposalManager,
        voting: VotingEngine,
        exp_dir: Path,
        tmp_path: Path,
        shared_memory: SharedMemory,
    ) -> None:
        # Create a registry at MAX_COUNCIL_SIZE
        members_dir = tmp_path / "full_council"
        members_dir.mkdir()
        from config.settings import MAX_COUNCIL_SIZE
        for i in range(MAX_COUNCIL_SIZE):
            filepath = members_dir / f"member_{i}.yaml"
            data = {
                "name": f"Member{i}",
                "role": "Role",
                "description": "Desc",
                "api_provider": "openrouter",
                "model": "m",
                "system_prompt": "p",
            }
            filepath.write_text(yaml.dump(data), encoding="utf-8")
        full_reg = CouncilRegistry(members_dir=members_dir).load()

        exp = CouncilExpansion(
            registry=full_reg,
            proposal_manager=proposals,
            voting_engine=voting,
            expansions_dir=exp_dir,
            members_dir=members_dir,
            shared_memory=shared_memory,
        )
        spec = _make_spec(name="Overflow")
        with pytest.raises(ExpansionValidationError, match="maximum size"):
            exp.create_expansion(spec, author="Sage")

    def test_duplicate_name(self, expansion: CouncilExpansion) -> None:
        # "Sage" already exists in the registry fixture
        spec = _make_spec(name="Sage")
        with pytest.raises(ExpansionValidationError, match="already exists"):
            expansion.create_expansion(spec, author="Logic")

    def test_empty_author(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        with pytest.raises(ExpansionValidationError, match="Author"):
            expansion.create_expansion(spec, author="  ")

    def test_duplicate_name_case_insensitive(
        self, expansion: CouncilExpansion,
    ) -> None:
        spec = _make_spec(name="SAGE")
        with pytest.raises(ExpansionValidationError, match="already exists"):
            expansion.create_expansion(spec, author="Logic")


# ─── TestSubmitForReview ──────────────────────────────────────


class TestSubmitForReview:
    """Tests for submitting expansions for governance review."""

    def test_basic(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        assert rec.status == "proposed"
        assert rec.proposal_id != ""

    def test_creates_proposal(
        self,
        expansion: CouncilExpansion,
        proposals: ProposalManager,
    ) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        proposal = proposals.get(rec.proposal_id)
        assert proposal.category == "expansion"
        assert proposal.author == "Sage"
        assert proposal.status == "open"

    def test_links_proposal_id(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        assert rec.proposal_id.startswith("P-")

    def test_already_submitted(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        expansion.submit_for_review(rec.expansion_id)
        with pytest.raises(ExpansionStateError, match="Cannot transition"):
            expansion.submit_for_review(rec.expansion_id)

    def test_not_found(self, expansion: CouncilExpansion) -> None:
        with pytest.raises(ExpansionNotFoundError):
            expansion.submit_for_review("CE-9999")

    def test_wrong_status(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        with pytest.raises(ExpansionStateError):
            expansion.submit_for_review(rec.expansion_id)


# ─── TestOpenVoting ───────────────────────────────────────────


class TestOpenVoting:
    """Tests for opening voting on expansion proposals."""

    def test_basic(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        assert rec.status == "voting"

    def test_links_vote_record(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        assert rec.vote_record_id != ""
        assert voting.has_record(rec.proposal_id)

    def test_not_proposed(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        with pytest.raises(ExpansionStateError, match="Cannot transition"):
            expansion.open_voting(rec.expansion_id)

    def test_already_voting(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        expansion.open_voting(rec.expansion_id)
        with pytest.raises(ExpansionStateError):
            expansion.open_voting(rec.expansion_id)

    def test_not_found(self, expansion: CouncilExpansion) -> None:
        with pytest.raises(ExpansionNotFoundError):
            expansion.open_voting("CE-9999")


# ─── TestResolve ──────────────────────────────────────────────


class TestResolve:
    """Tests for resolving expansion votes."""

    def _setup_voting(
        self,
        expansion: CouncilExpansion,
    ) -> ExpansionRecord:
        """Helper: create → submit → open voting."""
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        return rec

    def test_approved(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(expansion)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = expansion.resolve(rec.expansion_id)
        assert rec.status == "decided"
        assert "Approved" in rec.summary

    def test_rejected_below_threshold(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(expansion)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "against"))
        voting.cast_vote(rec.proposal_id, Vote.create("Spark", "against"))
        rec = expansion.resolve(rec.expansion_id)
        assert rec.status == "rejected"
        assert "Rejected" in rec.summary

    def test_rejected_no_quorum(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(expansion)
        # Only 1 vote, quorum is 2
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        rec = expansion.resolve(rec.expansion_id)
        assert rec.status == "rejected"

    def test_already_resolved(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(expansion)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        expansion.resolve(rec.expansion_id)
        with pytest.raises(ExpansionStateError, match="Cannot resolve"):
            expansion.resolve(rec.expansion_id)

    def test_not_in_voting(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        with pytest.raises(ExpansionStateError, match="must be 'voting'"):
            expansion.resolve(rec.expansion_id)

    def test_handles_veto(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(expansion)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        voting.veto(rec.proposal_id, "Not appropriate")
        rec = expansion.resolve(rec.expansion_id)
        assert rec.status == "rejected"
        assert "VETOED" in rec.summary

    def test_not_found(self, expansion: CouncilExpansion) -> None:
        with pytest.raises(ExpansionNotFoundError):
            expansion.resolve("CE-9999")


# ─── TestApplyExpansion ───────────────────────────────────────


class TestApplyExpansion:
    """Tests for applying approved expansions."""

    def _approve(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
        spec: MemberSpec | None = None,
    ) -> ExpansionRecord:
        """Helper: create → submit → vote → resolve (approved)."""
        effective = spec or _make_spec()
        rec = expansion.create_expansion(effective, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        return expansion.resolve(rec.expansion_id)

    def test_writes_yaml_file(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
        members_dir: Path,
    ) -> None:
        rec = self._approve(expansion, voting)
        rec = expansion.apply_expansion(rec.expansion_id)
        yaml_path = members_dir / "nova.yaml"
        assert yaml_path.exists()
        assert rec.applied_member_file == str(yaml_path)

    def test_correct_yaml_content(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
        members_dir: Path,
    ) -> None:
        spec = _make_spec(
            specialties=["innovation", "creativity"],
            personality={"traits": ["bold"]},
        )
        rec = self._approve(expansion, voting, spec=spec)
        expansion.apply_expansion(rec.expansion_id)
        yaml_path = members_dir / "nova.yaml"
        content = yaml_path.read_text(encoding="utf-8")
        # Skip the comment line
        parsed = yaml.safe_load(content.split("\n", 1)[1])
        assert parsed["name"] == "Nova"
        assert parsed["role"] == "Innovation Advisor"
        assert parsed["api_provider"] == "openrouter"
        assert parsed["specialties"] == ["innovation", "creativity"]

    def test_links_applied_member_file(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        rec = self._approve(expansion, voting)
        rec = expansion.apply_expansion(rec.expansion_id)
        reloaded = expansion.get(rec.expansion_id)
        assert reloaded.applied_member_file != ""
        assert reloaded.status == "applied"

    def test_not_decided(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        with pytest.raises(ExpansionStateError, match="Cannot transition"):
            expansion.apply_expansion(rec.expansion_id)

    def test_already_applied(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        rec = self._approve(expansion, voting)
        expansion.apply_expansion(rec.expansion_id)
        with pytest.raises(ExpansionStateError, match="Cannot transition"):
            expansion.apply_expansion(rec.expansion_id)

    def test_not_found(self, expansion: CouncilExpansion) -> None:
        with pytest.raises(ExpansionNotFoundError):
            expansion.apply_expansion("CE-9999")


# ─── TestQueryMethods ─────────────────────────────────────────


class TestQueryMethods:
    """Tests for query/list methods."""

    def test_get(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        retrieved = expansion.get(rec.expansion_id)
        assert retrieved.expansion_id == rec.expansion_id

    def test_not_found(self, expansion: CouncilExpansion) -> None:
        with pytest.raises(ExpansionNotFoundError):
            expansion.get("CE-9999")

    def test_list_all(self, expansion: CouncilExpansion) -> None:
        expansion.create_expansion(_make_spec(name="Nova1"), author="Sage")
        expansion.create_expansion(_make_spec(name="Nova2"), author="Logic")
        all_exps = expansion.list_expansions()
        assert len(all_exps) == 2

    def test_filter_by_status(self, expansion: CouncilExpansion) -> None:
        expansion.create_expansion(_make_spec(name="Nova1"), author="Sage")
        drafts = expansion.list_expansions(status="draft")
        assert len(drafts) == 1
        applied = expansion.list_expansions(status="applied")
        assert len(applied) == 0

    def test_filter_by_author(self, expansion: CouncilExpansion) -> None:
        expansion.create_expansion(_make_spec(name="Nova1"), author="Sage")
        expansion.create_expansion(_make_spec(name="Nova2"), author="Logic")
        sage_exps = expansion.list_expansions(author="Sage")
        assert len(sage_exps) == 1
        assert sage_exps[0].author == "Sage"

    def test_has_expansion(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        assert expansion.has_expansion(rec.expansion_id)
        assert not expansion.has_expansion("CE-9999")

    def test_combined_filters(self, expansion: CouncilExpansion) -> None:
        expansion.create_expansion(_make_spec(name="Nova1"), author="Sage")
        expansion.create_expansion(_make_spec(name="Nova2"), author="Logic")
        filtered = expansion.list_expansions(status="draft", author="Sage")
        assert len(filtered) == 1

    def test_corrupt_file_skipped(
        self, expansion: CouncilExpansion, exp_dir: Path,
    ) -> None:
        expansion.create_expansion(_make_spec(), author="Sage")
        # Write a corrupt file
        corrupt_path = exp_dir / "CE-0099.json"
        corrupt_path.write_text("{bad json", encoding="utf-8")
        all_exps = expansion.list_expansions()
        assert len(all_exps) == 1  # corrupt file skipped


# ─── TestLifecycleIntegration ─────────────────────────────────


class TestLifecycleIntegration:
    """Tests for full lifecycle paths."""

    def test_full_happy_path(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
        members_dir: Path,
    ) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        assert rec.status == "draft"

        rec = expansion.submit_for_review(rec.expansion_id)
        assert rec.status == "proposed"

        rec = expansion.open_voting(rec.expansion_id)
        assert rec.status == "voting"

        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = expansion.resolve(rec.expansion_id)
        assert rec.status == "decided"

        rec = expansion.apply_expansion(rec.expansion_id)
        assert rec.status == "applied"
        assert (members_dir / "nova.yaml").exists()

    def test_rejected_path(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
    ) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "against"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "against"))
        rec = expansion.resolve(rec.expansion_id)
        assert rec.status == "rejected"
        # Cannot apply a rejected expansion
        with pytest.raises(ExpansionStateError):
            expansion.apply_expansion(rec.expansion_id)

    def test_cannot_skip_states(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        with pytest.raises(ExpansionStateError, match="Cannot transition"):
            expansion.open_voting(rec.expansion_id)

    def test_persistence_roundtrip(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec(
            personality={"traits": ["bold"]},
            specialties=["innovation"],
        )
        rec = expansion.create_expansion(spec, author="Sage")
        reloaded = expansion.get(rec.expansion_id)
        assert reloaded.member_spec.name == "Nova"
        assert reloaded.member_spec.personality == {"traits": ["bold"]}
        assert reloaded.member_spec.specialties == ["innovation"]


# ─── TestEdgeCases ────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_unicode_member(self, expansion: CouncilExpansion) -> None:
        spec = _make_spec(
            name="Résumé",
            role="Répondeur",
            description="Gère les réponses 🌍",
            system_prompt="Tu es Résumé.",
        )
        rec = expansion.create_expansion(spec, author="Sage")
        reloaded = expansion.get(rec.expansion_id)
        assert reloaded.member_spec.name == "Résumé"
        assert "🌍" in reloaded.member_spec.description

    def test_long_system_prompt(self, expansion: CouncilExpansion) -> None:
        long_prompt = "You are Nova. " * 500
        spec = _make_spec(system_prompt=long_prompt)
        rec = expansion.create_expansion(spec, author="Sage")
        reloaded = expansion.get(rec.expansion_id)
        assert len(reloaded.member_spec.system_prompt) > 5000

    def test_shared_memory_recording(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
        shared_memory: SharedMemory,
    ) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        expansion.resolve(rec.expansion_id)

        decisions = shared_memory.read_decisions()
        assert any(
            d.get("type") == "expansion_resolved" for d in decisions
        )

    def test_apply_records_history(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
        shared_memory: SharedMemory,
    ) -> None:
        spec = _make_spec()
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = expansion.resolve(rec.expansion_id)
        expansion.apply_expansion(rec.expansion_id)

        history = shared_memory.read_history()
        assert "Nova" in history
        assert "Council Expansion" in history

    def test_member_name_with_spaces(
        self,
        expansion: CouncilExpansion,
        voting: VotingEngine,
        members_dir: Path,
    ) -> None:
        spec = _make_spec(name="Red Nova")
        rec = expansion.create_expansion(spec, author="Sage")
        rec = expansion.submit_for_review(rec.expansion_id)
        rec = expansion.open_voting(rec.expansion_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = expansion.resolve(rec.expansion_id)
        rec = expansion.apply_expansion(rec.expansion_id)
        # Filename should use underscores
        assert (members_dir / "red_nova.yaml").exists()


# ─── TestExceptions ───────────────────────────────────────────


class TestExceptions:
    """Tests for exception hierarchy and fields."""

    def test_hierarchy(self) -> None:
        assert issubclass(ExpansionNotFoundError, ExpansionError)
        assert issubclass(ExpansionValidationError, ExpansionError)
        assert issubclass(ExpansionStateError, ExpansionError)
        assert issubclass(ExpansionError, Exception)

    def test_not_found_fields(self) -> None:
        err = ExpansionNotFoundError("CE-0001")
        assert err.expansion_id == "CE-0001"
        assert "CE-0001" in str(err)

    def test_validation_fields(self) -> None:
        err = ExpansionValidationError(["error1", "error2"])
        assert err.errors == ["error1", "error2"]
        assert "error1" in str(err)

    def test_state_error_fields(self) -> None:
        err = ExpansionStateError("CE-0001", "bad transition")
        assert err.expansion_id == "CE-0001"
        assert "bad transition" in str(err)
