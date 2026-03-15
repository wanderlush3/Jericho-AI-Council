"""
Tests for core/character_evolution.py — Character Evolution (F-013)

Covers: data models, lifecycle transitions, governance integration
(proposals + voting), change application, query methods, and edge cases.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from typing import Any

from core.character_evolution import (
    CharacterChange,
    CharacterEvolution,
    EvolutionError,
    EvolutionNotFoundError,
    EvolutionRecord,
    EvolutionStateError,
    EvolutionValidationError,
)
from core.characters import CharacterManager, CharacterTemplate, Trait
from core.proposals import ProposalManager
from core.voting import Vote, VotingEngine
from core.memory import SharedMemory


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def evo_dir(tmp_path: Path) -> Path:
    d = tmp_path / "evolutions"
    d.mkdir()
    return d


@pytest.fixture
def char_dir(tmp_path: Path) -> Path:
    d = tmp_path / "characters"
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
def char_mgr(char_dir: Path) -> CharacterManager:
    return CharacterManager(characters_dir=char_dir)


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
def active_character(char_mgr: CharacterManager) -> CharacterTemplate:
    """Create an active character for evolution tests."""
    trait = Trait.create("personality", "Curious", "Always asking questions", intensity=0.7)
    char = char_mgr.create(
        "Atlas", "An explorer AI",
        author="Forge",
        traits=[trait],
        backstory="Born in the depths of curiosity.",
        system_prompt="You are Atlas, an explorer.",
    )
    return char_mgr.update_status(char.id, "active")


@pytest.fixture
def evo(
    char_mgr: CharacterManager,
    proposals: ProposalManager,
    voting: VotingEngine,
    evo_dir: Path,
    shared_memory: SharedMemory,
) -> CharacterEvolution:
    return CharacterEvolution(
        character_manager=char_mgr,
        proposal_manager=proposals,
        voting_engine=voting,
        evolutions_dir=evo_dir,
        shared_memory=shared_memory,
    )


def _make_change(**kwargs: Any) -> CharacterChange:
    """Helper to create a change with sensible defaults."""
    defaults = {
        "change_type": "trait_add",
        "field_name": "bravery",
        "new_value": {
            "trait_type": "personality",
            "name": "bravery",
            "description": "Fearless in exploration",
            "intensity": 0.8,
        },
        "rationale": "Character needs more courage",
    }
    defaults.update(kwargs)
    return CharacterChange.create(**defaults)


# ─── TestCharacterChange ──────────────────────────────────────


class TestCharacterChange:
    """Tests for the CharacterChange data class."""

    def test_fields(self) -> None:
        c = CharacterChange(
            change_type="trait_add",
            field_name="bravery",
            old_value="",
            new_value="brave",
            rationale="needs it",
        )
        assert c.change_type == "trait_add"
        assert c.field_name == "bravery"
        assert c.new_value == "brave"

    def test_frozen(self) -> None:
        c = _make_change()
        with pytest.raises(AttributeError):
            c.field_name = "other"  # type: ignore[misc]

    def test_roundtrip(self) -> None:
        c = _make_change()
        restored = CharacterChange.from_dict(c.to_dict())
        assert restored.change_type == c.change_type
        assert restored.field_name == c.field_name
        assert restored.new_value == c.new_value
        assert restored.rationale == c.rationale

    def test_create_factory(self) -> None:
        c = CharacterChange.create(
            "field_update", "backstory",
            old_value="old", new_value="new",
            rationale="improve depth",
        )
        assert c.change_type == "field_update"
        assert c.field_name == "backstory"

    def test_invalid_change_type(self) -> None:
        with pytest.raises(EvolutionValidationError, match="Invalid change type"):
            CharacterChange.create("bad_type", "field")

    def test_empty_field_name(self) -> None:
        with pytest.raises(EvolutionValidationError, match="Field name"):
            CharacterChange.create("trait_add", "  ")


# ─── TestEvolutionRecord ──────────────────────────────────────


class TestEvolutionRecord:
    """Tests for the EvolutionRecord data class."""

    def test_fields(self) -> None:
        r = EvolutionRecord(
            evolution_id="EV-0001",
            character_id="CH-0001",
            author="Sage",
        )
        assert r.evolution_id == "EV-0001"
        assert r.character_id == "CH-0001"
        assert r.status == "draft"

    def test_frozen(self) -> None:
        r = EvolutionRecord.create("EV-0001", "CH-0001", "Sage")
        with pytest.raises(AttributeError):
            r.status = "applied"  # type: ignore[misc]

    def test_roundtrip(self) -> None:
        changes = [_make_change()]
        r = EvolutionRecord.create(
            "EV-0001", "CH-0001", "Sage",
            changes=changes,
            metadata={"key": "value"},
        )
        restored = EvolutionRecord.from_dict(r.to_dict())
        assert restored.evolution_id == r.evolution_id
        assert restored.character_id == r.character_id
        assert len(restored.changes) == 1
        assert restored.metadata == {"key": "value"}

    def test_create_factory(self) -> None:
        r = EvolutionRecord.create("EV-0001", "CH-0001", "Sage")
        assert r.status == "draft"
        assert r.created_at != ""
        assert r.updated_at != ""

    def test_empty_id(self) -> None:
        with pytest.raises(EvolutionValidationError, match="Evolution ID"):
            EvolutionRecord.create("", "CH-0001", "Sage")

    def test_empty_character_id(self) -> None:
        with pytest.raises(EvolutionValidationError, match="Character ID"):
            EvolutionRecord.create("EV-0001", "  ", "Sage")

    def test_empty_author(self) -> None:
        with pytest.raises(EvolutionValidationError, match="Author"):
            EvolutionRecord.create("EV-0001", "CH-0001", "")


# ─── TestCharacterEvolutionInit ───────────────────────────────


class TestCharacterEvolutionInit:
    """Tests for CharacterEvolution initialization."""

    def test_dir_creation(
        self,
        char_mgr: CharacterManager,
        proposals: ProposalManager,
        voting: VotingEngine,
        tmp_path: Path,
    ) -> None:
        new_dir = tmp_path / "new_evo"
        evo = CharacterEvolution(
            character_manager=char_mgr,
            proposal_manager=proposals,
            voting_engine=voting,
            evolutions_dir=new_dir,
        )
        assert evo.directory.exists()

    def test_properties(self, evo: CharacterEvolution) -> None:
        assert evo.character_manager is not None
        assert evo.proposal_manager is not None
        assert evo.voting_engine is not None

    def test_repr(self, evo: CharacterEvolution) -> None:
        r = repr(evo)
        assert "CharacterEvolution" in r
        assert "records=0" in r


# ─── TestCreateEvolution ──────────────────────────────────────


class TestCreateEvolution:
    """Tests for creating evolution records."""

    def test_basic(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(
            active_character.id,
            author="Sage",
            changes=[change],
        )
        assert rec.evolution_id == "EV-0001"
        assert rec.character_id == active_character.id
        assert rec.author == "Sage"
        assert rec.status == "draft"
        assert len(rec.changes) == 1

    def test_sequential_ids(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        r1 = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        r2 = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        assert r1.evolution_id == "EV-0001"
        assert r2.evolution_id == "EV-0002"

    def test_persistence(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        reloaded = evo.get(rec.evolution_id)
        assert reloaded.character_id == rec.character_id
        assert len(reloaded.changes) == 1

    def test_multiple_changes(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        changes = [
            _make_change(field_name="bravery"),
            CharacterChange.create(
                "field_update", "backstory",
                new_value="Updated backstory",
                rationale="Deeper lore",
            ),
        ]
        rec = evo.create_evolution(
            active_character.id, author="Sage", changes=changes,
        )
        assert len(rec.changes) == 2

    def test_no_changes(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        with pytest.raises(EvolutionValidationError, match="At least one change"):
            evo.create_evolution(
                active_character.id, author="Sage", changes=[],
            )

    def test_character_not_found(self, evo: CharacterEvolution) -> None:
        change = _make_change()
        from core.characters import CharacterNotFoundError
        with pytest.raises(CharacterNotFoundError):
            evo.create_evolution("CH-9999", author="Sage", changes=[change])

    def test_character_not_active(
        self,
        evo: CharacterEvolution,
        char_mgr: CharacterManager,
    ) -> None:
        trait = Trait.create("personality", "Test", "test", intensity=0.5)
        char = char_mgr.create("Draft Char", "A draft", author="Forge", traits=[trait])
        # char is still in draft status
        change = _make_change()
        with pytest.raises(EvolutionValidationError, match="must be in 'active'"):
            evo.create_evolution(char.id, author="Sage", changes=[change])

    def test_exceeds_max_changes(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        changes = [
            _make_change(field_name=f"trait_{i}")
            for i in range(11)
        ]
        with pytest.raises(EvolutionValidationError, match="exceeds maximum"):
            evo.create_evolution(
                active_character.id, author="Sage", changes=changes,
            )


# ─── TestSubmitForReview ──────────────────────────────────────


class TestSubmitForReview:
    """Tests for submitting evolutions for governance review."""

    def test_basic(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        assert rec.status == "proposed"
        assert rec.proposal_id != ""

    def test_creates_proposal(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        proposals: ProposalManager,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        proposal = proposals.get(rec.proposal_id)
        assert proposal.category == "character"
        assert proposal.author == "Sage"
        assert proposal.status == "open"

    def test_links_proposal_id(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        assert rec.proposal_id.startswith("P-")

    def test_already_submitted(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        evo.submit_for_review(rec.evolution_id)
        with pytest.raises(EvolutionStateError, match="Cannot transition"):
            evo.submit_for_review(rec.evolution_id)

    def test_not_found(self, evo: CharacterEvolution) -> None:
        with pytest.raises(EvolutionNotFoundError):
            evo.submit_for_review("EV-9999")

    def test_wrong_status(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        with pytest.raises(EvolutionStateError):
            evo.submit_for_review(rec.evolution_id)


# ─── TestOpenVoting ───────────────────────────────────────────


class TestOpenVoting:
    """Tests for opening voting on evolution proposals."""

    def test_basic(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        assert rec.status == "voting"

    def test_links_vote_record(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        assert rec.vote_record_id != ""
        assert voting.has_record(rec.proposal_id)

    def test_not_proposed(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        with pytest.raises(EvolutionStateError, match="Cannot transition"):
            evo.open_voting(rec.evolution_id)

    def test_already_voting(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        evo.open_voting(rec.evolution_id)
        with pytest.raises(EvolutionStateError):
            evo.open_voting(rec.evolution_id)

    def test_not_found(self, evo: CharacterEvolution) -> None:
        with pytest.raises(EvolutionNotFoundError):
            evo.open_voting("EV-9999")


# ─── TestResolve ──────────────────────────────────────────────


class TestResolve:
    """Tests for resolving evolution votes."""

    def _setup_voting(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> EvolutionRecord:
        """Helper: create → submit → open voting."""
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        return rec

    def test_approved(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(evo, active_character)
        # Cast approving votes (quorum=2, threshold=0.6)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "decided"
        assert "Approved" in rec.summary

    def test_rejected_below_threshold(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(evo, active_character)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "against"))
        voting.cast_vote(rec.proposal_id, Vote.create("Spark", "against"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "rejected"
        assert "Rejected" in rec.summary

    def test_rejected_no_quorum(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(evo, active_character)
        # Only 1 vote, quorum is 2
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "rejected"

    def test_already_resolved(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(evo, active_character)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        evo.resolve(rec.evolution_id)
        with pytest.raises(EvolutionStateError, match="Cannot resolve"):
            evo.resolve(rec.evolution_id)

    def test_not_in_voting(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        with pytest.raises(EvolutionStateError, match="must be 'voting'"):
            evo.resolve(rec.evolution_id)

    def test_handles_veto(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._setup_voting(evo, active_character)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        voting.veto(rec.proposal_id, "Not appropriate")
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "rejected"
        assert "VETOED" in rec.summary

    def test_not_found(self, evo: CharacterEvolution) -> None:
        with pytest.raises(EvolutionNotFoundError):
            evo.resolve("EV-9999")


# ─── TestApplyEvolution ───────────────────────────────────────


class TestApplyEvolution:
    """Tests for applying approved evolutions to characters."""

    def _approve(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
        changes: list[CharacterChange] | None = None,
    ) -> EvolutionRecord:
        """Helper: create → submit → vote → resolve (approved)."""
        effective = changes or [_make_change()]
        rec = evo.create_evolution(
            active_character.id, author="Sage", changes=effective,
        )
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        return evo.resolve(rec.evolution_id)

    def test_creates_new_version(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
        char_mgr: CharacterManager,
    ) -> None:
        rec = self._approve(evo, active_character, voting)
        template = evo.apply_evolution(rec.evolution_id)
        assert template.id != active_character.id
        assert template.version == active_character.version + 1
        # Original should be superseded
        original = char_mgr.get(active_character.id)
        assert original.status == "superseded"

    def test_applies_trait_add(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._approve(evo, active_character, voting)
        template = evo.apply_evolution(rec.evolution_id)
        trait_names = [t.name for t in template.traits]
        assert "bravery" in trait_names

    def test_applies_trait_remove(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        # Active character has "Curious" trait; add another first so we can remove
        evo_obj = evo
        char_mgr = evo_obj.character_manager
        extra_trait = Trait.create("values", "Honesty", "Always truthful", intensity=0.6)
        char_mgr.add_trait(active_character.id, extra_trait)

        changes = [
            CharacterChange.create(
                "trait_remove", "Curious",
                rationale="Character evolved past curiosity",
            ),
        ]
        rec = self._approve(evo, active_character, voting, changes=changes)
        template = evo.apply_evolution(rec.evolution_id)
        trait_names = [t.name for t in template.traits]
        assert "Curious" not in trait_names

    def test_applies_field_update(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        changes = [
            CharacterChange.create(
                "field_update", "backstory",
                old_value=active_character.backstory,
                new_value="A completely new origin story.",
                rationale="Better character depth",
            ),
        ]
        rec = self._approve(evo, active_character, voting, changes=changes)
        template = evo.apply_evolution(rec.evolution_id)
        assert template.backstory == "A completely new origin story."

    def test_links_applied_character_id(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._approve(evo, active_character, voting)
        template = evo.apply_evolution(rec.evolution_id)
        reloaded = evo.get(rec.evolution_id)
        assert reloaded.applied_character_id == template.id
        assert reloaded.status == "applied"

    def test_not_decided(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        with pytest.raises(EvolutionStateError, match="Cannot transition"):
            evo.apply_evolution(rec.evolution_id)

    def test_already_applied(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        rec = self._approve(evo, active_character, voting)
        evo.apply_evolution(rec.evolution_id)
        with pytest.raises(EvolutionStateError, match="Cannot transition"):
            evo.apply_evolution(rec.evolution_id)

    def test_not_found(self, evo: CharacterEvolution) -> None:
        with pytest.raises(EvolutionNotFoundError):
            evo.apply_evolution("EV-9999")


# ─── TestQueryMethods ─────────────────────────────────────────


class TestQueryMethods:
    """Tests for query/list methods."""

    def test_get(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        retrieved = evo.get(rec.evolution_id)
        assert retrieved.evolution_id == rec.evolution_id

    def test_not_found(self, evo: CharacterEvolution) -> None:
        with pytest.raises(EvolutionNotFoundError):
            evo.get("EV-9999")

    def test_list_all(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        evo.create_evolution(active_character.id, author="Sage", changes=[change])
        evo.create_evolution(active_character.id, author="Logic", changes=[change])
        all_evos = evo.list_evolutions()
        assert len(all_evos) == 2

    def test_filter_by_character_id(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        evo.create_evolution(active_character.id, author="Sage", changes=[change])
        filtered = evo.list_evolutions(character_id=active_character.id)
        assert len(filtered) == 1
        empty = evo.list_evolutions(character_id="CH-9999")
        assert len(empty) == 0

    def test_filter_by_status(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        evo.create_evolution(active_character.id, author="Sage", changes=[change])
        drafts = evo.list_evolutions(status="draft")
        assert len(drafts) == 1
        applied = evo.list_evolutions(status="applied")
        assert len(applied) == 0

    def test_filter_by_author(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        evo.create_evolution(active_character.id, author="Sage", changes=[change])
        evo.create_evolution(active_character.id, author="Logic", changes=[change])
        sage_evos = evo.list_evolutions(author="Sage")
        assert len(sage_evos) == 1
        assert sage_evos[0].author == "Sage"

    def test_has_evolution(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        assert evo.has_evolution(rec.evolution_id) is True
        assert evo.has_evolution("EV-9999") is False

    def test_corrupt_skip(
        self,
        evo: CharacterEvolution,
        evo_dir: Path,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        evo.create_evolution(active_character.id, author="Sage", changes=[change])
        # Write a corrupt file
        (evo_dir / "EV-0099.json").write_text("{bad json", encoding="utf-8")
        all_evos = evo.list_evolutions()
        assert len(all_evos) == 1  # corrupt file skipped


# ─── TestLifecycleIntegration ─────────────────────────────────


class TestLifecycleIntegration:
    """Tests for the full evolution lifecycle."""

    def test_full_happy_path(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
        char_mgr: CharacterManager,
    ) -> None:
        # Create
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        assert rec.status == "draft"

        # Submit
        rec = evo.submit_for_review(rec.evolution_id)
        assert rec.status == "proposed"

        # Vote
        rec = evo.open_voting(rec.evolution_id)
        assert rec.status == "voting"

        # Cast votes and resolve
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "decided"

        # Apply
        template = evo.apply_evolution(rec.evolution_id)
        assert template.status == "active"
        rec = evo.get(rec.evolution_id)
        assert rec.status == "applied"
        assert rec.applied_character_id == template.id

    def test_rejected_path(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "against"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "against"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "rejected"
        # Cannot apply rejected
        with pytest.raises(EvolutionStateError):
            evo.apply_evolution(rec.evolution_id)

    def test_cannot_skip_states(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        # Cannot go directly from draft to voting
        with pytest.raises(EvolutionStateError):
            evo.open_voting(rec.evolution_id)

    def test_persistence_roundtrip(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = _make_change()
        rec = evo.create_evolution(
            active_character.id, author="Sage", changes=[change],
            metadata={"reason": "testing"},
        )
        reloaded = evo.get(rec.evolution_id)
        assert reloaded.evolution_id == rec.evolution_id
        assert reloaded.metadata == {"reason": "testing"}
        assert len(reloaded.changes) == 1


# ─── TestEdgeCases ────────────────────────────────────────────


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_unicode(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        change = CharacterChange.create(
            "field_update", "backstory",
            new_value="生まれた場所は東京です 🎌",
            rationale="国際化テスト",
        )
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        reloaded = evo.get(rec.evolution_id)
        assert reloaded.changes[0].new_value == "生まれた場所は東京です 🎌"

    def test_multiple_changes(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        changes = [
            CharacterChange.create(
                "trait_add", "courage",
                new_value={
                    "trait_type": "personality",
                    "name": "courage",
                    "description": "Bold and fearless",
                    "intensity": 0.8,
                },
                rationale="Needs courage",
            ),
            CharacterChange.create(
                "field_update", "backstory",
                new_value="A fresh backstory.",
                rationale="depth",
            ),
            CharacterChange.create(
                "field_update", "system_prompt",
                new_value="You are a bold explorer.",
                rationale="better prompt",
            ),
        ]
        rec = evo.create_evolution(active_character.id, author="Sage", changes=changes)
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        template = evo.apply_evolution(rec.evolution_id)
        assert "courage" in [t.name for t in template.traits]
        assert template.backstory == "A fresh backstory."
        assert template.system_prompt == "You are a bold explorer."

    def test_large_rationale(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
    ) -> None:
        long_rationale = "x" * 5000
        change = CharacterChange.create(
            "trait_add", "wisdom",
            new_value={"trait_type": "values", "name": "wisdom",
                       "description": "Deep wisdom", "intensity": 0.9},
            rationale=long_rationale,
        )
        rec = evo.create_evolution(active_character.id, author="Sage", changes=[change])
        reloaded = evo.get(rec.evolution_id)
        assert len(reloaded.changes[0].rationale) == 5000

    def test_trait_modify(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        changes = [
            CharacterChange.create(
                "trait_modify", "Curious",
                old_value={"intensity": 0.7},
                new_value={
                    "trait_type": "personality",
                    "name": "Deeply Curious",
                    "description": "Obsessively inquisitive",
                    "intensity": 0.95,
                },
                rationale="Intensify curiosity",
            ),
        ]
        rec = evo.create_evolution(active_character.id, author="Sage", changes=changes)
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        template = evo.apply_evolution(rec.evolution_id)
        trait_names = [t.name for t in template.traits]
        assert "Deeply Curious" in trait_names

    def test_version_bump_change(
        self,
        evo: CharacterEvolution,
        active_character: CharacterTemplate,
        voting: VotingEngine,
    ) -> None:
        changes = [
            CharacterChange.create(
                "version_bump", "version",
                rationale="Formal version bump",
            ),
        ]
        rec = evo.create_evolution(active_character.id, author="Sage", changes=changes)
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        voting.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        voting.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        template = evo.apply_evolution(rec.evolution_id)
        assert template.version == active_character.version + 1


# ─── TestExceptions ───────────────────────────────────────────


class TestExceptions:
    """Tests for exception hierarchy and fields."""

    def test_hierarchy(self) -> None:
        assert issubclass(EvolutionNotFoundError, EvolutionError)
        assert issubclass(EvolutionValidationError, EvolutionError)
        assert issubclass(EvolutionStateError, EvolutionError)
        assert issubclass(EvolutionError, Exception)

    def test_not_found_fields(self) -> None:
        e = EvolutionNotFoundError("EV-0001")
        assert e.evolution_id == "EV-0001"
        assert "EV-0001" in str(e)

    def test_validation_fields(self) -> None:
        e = EvolutionValidationError(["err1", "err2"])
        assert e.errors == ["err1", "err2"]
        assert "err1" in str(e)

    def test_state_error_fields(self) -> None:
        e = EvolutionStateError("EV-0001", "bad state")
        assert e.evolution_id == "EV-0001"
        assert "bad state" in str(e)
