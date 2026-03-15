"""
Tests for core.evolution_history — Prompt Evolution History (F-020).
"""

from __future__ import annotations

import json
import pytest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.characters import CharacterManager, CharacterTemplate, Trait
from core.character_evolution import (
    CharacterEvolution,
    CharacterChange,
    EvolutionRecord,
)
from core.evolution_history import (
    EvolutionHistory,
    VersionSnapshot,
    EvolutionEvent,
    CharacterTimeline,
    _summarise_traits,
    _summarise_changes,
    _truncate,
    _build_vote_result,
)


# ─── Helpers ───────────────────────────────────────────────────


def _make_trait(name: str = "Curious", trait_type: str = "personality",
                intensity: float = 0.7) -> Trait:
    return Trait(trait_type=trait_type, name=name,
                 description=f"A {name.lower()} trait", intensity=intensity)


def _make_character(char_id: str, name: str = "Atlas", version: int = 1,
                    status: str = "active", author: str = "Forge",
                    traits: list | None = None,
                    previous_version: str = "",
                    backstory: str = "A brave explorer",
                    system_prompt: str = "You are Atlas.",
                    tags: list[str] | None = None) -> CharacterTemplate:
    meta = {}
    if previous_version:
        meta["previous_version"] = previous_version
    return CharacterTemplate(
        id=char_id,
        name=name,
        description=f"{name} description",
        author=author,
        status=status,
        backstory=backstory,
        traits=traits or [_make_trait()],
        system_prompt=system_prompt,
        greeting="Hello!",
        tags=tags or ["explorer"],
        version=version,
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        metadata=meta,
    )


def _make_evolution(evo_id: str, char_id: str, status: str = "applied",
                    author: str = "Sage",
                    applied_char_id: str = "",
                    proposal_id: str = "P-0001",
                    tally: dict | None = None) -> EvolutionRecord:
    meta = {}
    if tally:
        meta["tally"] = tally
    return EvolutionRecord(
        evolution_id=evo_id,
        character_id=char_id,
        author=author,
        changes=[
            CharacterChange(
                change_type="trait_add",
                field_name="brave",
                new_value={"trait_type": "personality", "name": "brave",
                           "description": "Bold", "intensity": 0.8},
                rationale="Needs bravery",
            ),
        ],
        proposal_id=proposal_id,
        vote_record_id=proposal_id,
        status=status,
        applied_character_id=applied_char_id,
        summary="Evolution applied" if status == "applied" else "",
        created_at="2026-01-02T00:00:00+00:00",
        updated_at="2026-01-02T00:00:00+00:00",
        metadata=meta,
    )


def _mock_char_manager(characters: list[CharacterTemplate]) -> MagicMock:
    mgr = MagicMock(spec=CharacterManager)
    char_map = {c.id: c for c in characters}
    from core.characters import CharacterNotFoundError

    def _get(cid):
        if cid not in char_map:
            raise CharacterNotFoundError(cid)
        return char_map[cid]

    mgr.get.side_effect = _get
    mgr.list_characters.return_value = characters
    return mgr


def _mock_evo_manager(evolutions: list[EvolutionRecord]) -> MagicMock:
    mgr = MagicMock(spec=CharacterEvolution)
    mgr.list_evolutions.return_value = evolutions
    return mgr


# ═══════════════════════════════════════════════════════════════
# VersionSnapshot Tests
# ═══════════════════════════════════════════════════════════════


class TestVersionSnapshot:
    """Tests for the VersionSnapshot data class."""

    def test_fields(self):
        snap = VersionSnapshot(
            character_id="CH-0001", name="Atlas", version=1,
            status="active", author="Forge",
            traits_summary="Curious (0.7)", trait_count=1,
            system_prompt_excerpt="You are...",
            backstory_excerpt="A brave...",
        )
        assert snap.character_id == "CH-0001"
        assert snap.name == "Atlas"
        assert snap.version == 1
        assert snap.trait_count == 1

    def test_frozen(self):
        snap = VersionSnapshot(
            character_id="CH-0001", name="Atlas", version=1,
            status="active", author="Forge",
            traits_summary="", trait_count=0,
            system_prompt_excerpt="", backstory_excerpt="",
        )
        with pytest.raises(AttributeError):
            snap.name = "Changed"  # type: ignore[misc]

    def test_roundtrip(self):
        snap = VersionSnapshot(
            character_id="CH-0001", name="Atlas", version=2,
            status="superseded", author="Forge",
            traits_summary="Curious (0.7), Brave (0.5)",
            trait_count=2,
            system_prompt_excerpt="You are Atlas.",
            backstory_excerpt="A brave explorer",
            tags=["explorer"],
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
            previous_version="CH-0000",
            metadata={"key": "value"},
        )
        d = snap.to_dict()
        restored = VersionSnapshot.from_dict(d)
        assert restored == snap

    def test_defaults(self):
        snap = VersionSnapshot(
            character_id="CH-0001", name="Atlas", version=1,
            status="active", author="Forge",
            traits_summary="", trait_count=0,
            system_prompt_excerpt="", backstory_excerpt="",
        )
        assert snap.tags == []
        assert snap.created_at == ""
        assert snap.previous_version == ""
        assert snap.metadata == {}

    def test_from_dict_missing_optionals(self):
        data = {
            "character_id": "CH-0001", "name": "X", "version": 1,
            "status": "active", "author": "A",
        }
        snap = VersionSnapshot.from_dict(data)
        assert snap.traits_summary == ""
        assert snap.tags == []


# ═══════════════════════════════════════════════════════════════
# EvolutionEvent Tests
# ═══════════════════════════════════════════════════════════════


class TestEvolutionEvent:
    """Tests for the EvolutionEvent data class."""

    def test_fields(self):
        evt = EvolutionEvent(
            evolution_id="EV-0001", character_id="CH-0001",
            author="Sage", changes_summary="trait_add:brave",
            change_count=1, proposal_id="P-0001",
            vote_result="Approved (80%)", status="applied",
        )
        assert evt.evolution_id == "EV-0001"
        assert evt.change_count == 1

    def test_frozen(self):
        evt = EvolutionEvent(
            evolution_id="EV-0001", character_id="CH-0001",
            author="Sage", changes_summary="", change_count=0,
        )
        with pytest.raises(AttributeError):
            evt.author = "X"  # type: ignore[misc]

    def test_roundtrip(self):
        evt = EvolutionEvent(
            evolution_id="EV-0001", character_id="CH-0001",
            author="Sage", changes_summary="trait_add:brave",
            change_count=1, proposal_id="P-0001",
            vote_result="Approved (80%)", status="applied",
            applied_character_id="CH-0002",
            timestamp="2026-01-02T00:00:00+00:00",
            metadata={"tally": {"approved": True}},
        )
        d = evt.to_dict()
        restored = EvolutionEvent.from_dict(d)
        assert restored == evt

    def test_defaults(self):
        evt = EvolutionEvent(
            evolution_id="EV-0001", character_id="CH-0001",
            author="Sage", changes_summary="", change_count=0,
        )
        assert evt.proposal_id == ""
        assert evt.vote_result == ""
        assert evt.applied_character_id == ""

    def test_from_dict_minimal(self):
        data = {
            "evolution_id": "EV-0001", "character_id": "CH-0001",
            "author": "Sage",
        }
        evt = EvolutionEvent.from_dict(data)
        assert evt.changes_summary == ""
        assert evt.change_count == 0


# ═══════════════════════════════════════════════════════════════
# CharacterTimeline Tests
# ═══════════════════════════════════════════════════════════════


class TestCharacterTimeline:
    """Tests for the CharacterTimeline data class."""

    def test_fields(self):
        tl = CharacterTimeline(
            character_name="Atlas",
            version_chain=["CH-0001", "CH-0002"],
            latest_version="CH-0002",
        )
        assert tl.character_name == "Atlas"
        assert len(tl.version_chain) == 2

    def test_chain_ordering(self):
        tl = CharacterTimeline(
            character_name="Atlas",
            version_chain=["CH-0001", "CH-0002", "CH-0003"],
        )
        assert tl.version_chain[0] == "CH-0001"  # oldest first
        assert tl.version_chain[-1] == "CH-0003"  # newest last

    def test_roundtrip(self):
        snap = VersionSnapshot(
            character_id="CH-0001", name="Atlas", version=1,
            status="active", author="Forge",
            traits_summary="Curious (0.7)", trait_count=1,
            system_prompt_excerpt="You are Atlas.",
            backstory_excerpt="Explorer",
        )
        evt = EvolutionEvent(
            evolution_id="EV-0001", character_id="CH-0001",
            author="Sage", changes_summary="trait_add:brave",
            change_count=1,
        )
        tl = CharacterTimeline(
            character_name="Atlas",
            version_chain=["CH-0001"],
            snapshots=[snap],
            events=[evt],
            latest_version="CH-0001",
        )
        d = tl.to_dict()
        restored = CharacterTimeline.from_dict(d)
        assert restored.character_name == tl.character_name
        assert len(restored.snapshots) == 1
        assert len(restored.events) == 1

    def test_defaults(self):
        tl = CharacterTimeline(character_name="Atlas")
        assert tl.version_chain == []
        assert tl.snapshots == []
        assert tl.events == []
        assert tl.latest_version == ""


# ═══════════════════════════════════════════════════════════════
# Helper Function Tests
# ═══════════════════════════════════════════════════════════════


class TestHelpers:
    """Tests for module-level helper functions."""

    def test_summarise_traits_empty(self):
        assert _summarise_traits([]) == "(none)"

    def test_summarise_traits_few(self):
        traits = [_make_trait("Curious", intensity=0.7)]
        result = _summarise_traits(traits)
        assert "Curious (0.7)" in result

    def test_summarise_traits_overflow(self):
        traits = [_make_trait(f"Trait{i}") for i in range(8)]
        result = _summarise_traits(traits)
        assert "+2 more" in result

    def test_truncate_short(self):
        assert _truncate("hello", 10) == "hello"

    def test_truncate_long(self):
        result = _truncate("a" * 200, 120)
        assert len(result) == 120
        assert result.endswith("...")

    def test_truncate_empty(self):
        assert _truncate("") == ""

    def test_summarise_changes_empty(self):
        assert _summarise_changes([]) == "(no changes)"

    def test_summarise_changes_overflow(self):
        changes = [
            CharacterChange(change_type=f"type{i}", field_name=f"field{i}")
            for i in range(7)
        ]
        result = _summarise_changes(changes)
        assert "+2 more" in result

    def test_build_vote_result_approved(self):
        evo = _make_evolution(
            "EV-0001", "CH-0001",
            tally={"approval_rate": 0.8, "approved": True},
        )
        result = _build_vote_result(evo)
        assert "Approved" in result
        assert "80%" in result

    def test_build_vote_result_rejected_with_tally(self):
        evo = _make_evolution(
            "EV-0001", "CH-0001", status="rejected",
            tally={"approval_rate": 0.3, "approved": False},
        )
        result = _build_vote_result(evo)
        assert "Rejected" in result

    def test_build_vote_result_no_tally(self):
        evo = _make_evolution("EV-0001", "CH-0001", status="draft")
        result = _build_vote_result(evo)
        assert result == ""

    def test_build_vote_result_rejected_no_tally(self):
        evo = _make_evolution("EV-0001", "CH-0001", status="rejected")
        result = _build_vote_result(evo)
        assert result == "Rejected"


# ═══════════════════════════════════════════════════════════════
# EvolutionHistory Init Tests
# ═══════════════════════════════════════════════════════════════


class TestEvolutionHistoryInit:
    """Tests for constructor and properties."""

    def test_constructor(self):
        chars = _mock_char_manager([])
        evo = _mock_evo_manager([])
        history = EvolutionHistory(character_manager=chars, evolution_manager=evo)
        assert history.character_manager is chars
        assert history.evolution_manager is evo

    def test_evolution_manager_optional(self):
        chars = _mock_char_manager([])
        history = EvolutionHistory(character_manager=chars)
        assert history.evolution_manager is None

    def test_repr(self):
        chars = _mock_char_manager([_make_character("CH-0001")])
        history = EvolutionHistory(character_manager=chars)
        r = repr(history)
        assert "EvolutionHistory" in r
        assert "1" in r


# ═══════════════════════════════════════════════════════════════
# Version Chain Tests
# ═══════════════════════════════════════════════════════════════


class TestGetVersionChain:
    """Tests for get_version_chain()."""

    def test_single_version(self):
        ch = _make_character("CH-0001")
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        chain = history.get_version_chain("CH-0001")
        assert chain == ["CH-0001"]

    def test_multi_version_chain(self):
        ch1 = _make_character("CH-0001", version=1, status="superseded")
        ch2 = _make_character("CH-0002", version=2, previous_version="CH-0001",
                              status="superseded")
        ch3 = _make_character("CH-0003", version=3, previous_version="CH-0002")
        chars = _mock_char_manager([ch1, ch2, ch3])
        history = EvolutionHistory(character_manager=chars)

        chain = history.get_version_chain("CH-0003")
        assert chain == ["CH-0001", "CH-0002", "CH-0003"]

    def test_chain_oldest_first(self):
        ch1 = _make_character("CH-0001", version=1, status="superseded")
        ch2 = _make_character("CH-0002", version=2, previous_version="CH-0001")
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        chain = history.get_version_chain("CH-0002")
        assert chain[0] == "CH-0001"
        assert chain[-1] == "CH-0002"

    def test_circular_guard(self):
        """Circular previous_version links should not cause infinite loops."""
        ch1 = _make_character("CH-0001", version=1, previous_version="CH-0002")
        ch2 = _make_character("CH-0002", version=2, previous_version="CH-0001")
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        chain = history.get_version_chain("CH-0001")
        # Should not loop forever; both IDs should appear at most once
        assert len(chain) <= 2

    def test_missing_intermediate(self):
        """Missing intermediate version should stop chain walk gracefully."""
        ch3 = _make_character("CH-0003", version=3, previous_version="CH-0002")
        # CH-0002 does not exist
        chars = _mock_char_manager([ch3])
        history = EvolutionHistory(character_manager=chars)

        chain = history.get_version_chain("CH-0003")
        # Should include CH-0003, stop at CH-0002 (not found)
        assert "CH-0003" in chain

    def test_not_found(self):
        chars = _mock_char_manager([])
        history = EvolutionHistory(character_manager=chars)
        from core.characters import CharacterNotFoundError
        with pytest.raises(CharacterNotFoundError):
            history.get_version_chain("CH-9999")


# ═══════════════════════════════════════════════════════════════
# Snapshot Tests
# ═══════════════════════════════════════════════════════════════


class TestGetSnapshot:
    """Tests for get_snapshot()."""

    def test_basic(self):
        ch = _make_character("CH-0001")
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        snap = history.get_snapshot("CH-0001")
        assert snap.character_id == "CH-0001"
        assert snap.name == "Atlas"
        assert snap.version == 1

    def test_with_traits(self):
        traits = [_make_trait("Curious", intensity=0.7), _make_trait("Brave", intensity=0.5)]
        ch = _make_character("CH-0001", traits=traits)
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        snap = history.get_snapshot("CH-0001")
        assert snap.trait_count == 2
        assert "Curious" in snap.traits_summary
        assert "Brave" in snap.traits_summary

    def test_with_metadata(self):
        ch = _make_character("CH-0002", previous_version="CH-0001")
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        snap = history.get_snapshot("CH-0002")
        assert snap.previous_version == "CH-0001"

    def test_system_prompt_excerpt(self):
        ch = _make_character("CH-0001", system_prompt="A" * 200)
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        snap = history.get_snapshot("CH-0001")
        assert len(snap.system_prompt_excerpt) <= 120

    def test_not_found(self):
        chars = _mock_char_manager([])
        history = EvolutionHistory(character_manager=chars)
        from core.characters import CharacterNotFoundError
        with pytest.raises(CharacterNotFoundError):
            history.get_snapshot("CH-9999")


# ═══════════════════════════════════════════════════════════════
# Build Timeline Tests
# ═══════════════════════════════════════════════════════════════


class TestBuildTimeline:
    """Tests for build_timeline()."""

    def test_single_version_no_evolutions(self):
        ch = _make_character("CH-0001")
        chars = _mock_char_manager([ch])
        evo = _mock_evo_manager([])
        history = EvolutionHistory(character_manager=chars, evolution_manager=evo)

        tl = history.build_timeline("CH-0001")
        assert tl.character_name == "Atlas"
        assert tl.version_chain == ["CH-0001"]
        assert len(tl.snapshots) == 1
        assert len(tl.events) == 0

    def test_multi_version_with_evolutions(self):
        ch1 = _make_character("CH-0001", version=1, status="superseded")
        ch2 = _make_character("CH-0002", version=2, previous_version="CH-0001")
        evo1 = _make_evolution("EV-0001", "CH-0001", applied_char_id="CH-0002")
        chars = _mock_char_manager([ch1, ch2])
        evo_mgr = _mock_evo_manager([evo1])
        history = EvolutionHistory(character_manager=chars, evolution_manager=evo_mgr)

        tl = history.build_timeline("CH-0002")
        assert tl.version_chain == ["CH-0001", "CH-0002"]
        assert len(tl.snapshots) == 2
        assert len(tl.events) == 1
        assert tl.events[0].evolution_id == "EV-0001"

    def test_events_sorted_by_timestamp(self):
        ch = _make_character("CH-0001")
        evo1 = _make_evolution("EV-0001", "CH-0001")
        evo2 = EvolutionRecord(
            evolution_id="EV-0002", character_id="CH-0001",
            author="Logic",
            changes=[CharacterChange(change_type="field_update", field_name="name")],
            status="draft",
            created_at="2025-12-01T00:00:00+00:00",
            updated_at="2025-12-01T00:00:00+00:00",
        )
        chars = _mock_char_manager([ch])
        evo_mgr = _mock_evo_manager([evo1, evo2])
        history = EvolutionHistory(character_manager=chars, evolution_manager=evo_mgr)

        tl = history.build_timeline("CH-0001")
        assert len(tl.events) == 2
        # evo2 is earlier → sorted first
        assert tl.events[0].evolution_id == "EV-0002"
        assert tl.events[1].evolution_id == "EV-0001"

    def test_latest_version(self):
        ch1 = _make_character("CH-0001", version=1, status="superseded")
        ch2 = _make_character("CH-0002", version=2, previous_version="CH-0001")
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        tl = history.build_timeline("CH-0002")
        assert tl.latest_version == "CH-0002"

    def test_no_evolution_manager(self):
        ch = _make_character("CH-0001")
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        tl = history.build_timeline("CH-0001")
        assert len(tl.events) == 0

    def test_not_found(self):
        chars = _mock_char_manager([])
        history = EvolutionHistory(character_manager=chars)
        from core.characters import CharacterNotFoundError
        with pytest.raises(CharacterNotFoundError):
            history.build_timeline("CH-9999")

    def test_irrelevant_evolutions_excluded(self):
        ch = _make_character("CH-0001")
        evo_other = _make_evolution("EV-0001", "CH-9999")  # different char
        chars = _mock_char_manager([ch])
        evo_mgr = _mock_evo_manager([evo_other])
        history = EvolutionHistory(character_manager=chars, evolution_manager=evo_mgr)

        tl = history.build_timeline("CH-0001")
        assert len(tl.events) == 0


# ═══════════════════════════════════════════════════════════════
# List Timelines Tests
# ═══════════════════════════════════════════════════════════════


class TestListTimelines:
    """Tests for list_timelines()."""

    def test_empty(self):
        chars = _mock_char_manager([])
        history = EvolutionHistory(character_manager=chars)

        result = history.list_timelines()
        assert result == []

    def test_filters_superseded(self):
        ch1 = _make_character("CH-0001", version=1, status="superseded")
        ch2 = _make_character("CH-0002", version=2, previous_version="CH-0001")
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        timelines = history.list_timelines()
        # Only CH-0002 is a "head" (CH-0001 is superseded_ids because
        # CH-0002's previous_version points to it)
        assert len(timelines) == 1
        assert timelines[0].latest_version == "CH-0002"

    def test_multiple_lineages(self):
        ch1 = _make_character("CH-0001", name="Alpha")
        ch2 = _make_character("CH-0002", name="Beta")
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        timelines = history.list_timelines()
        assert len(timelines) == 2
        # Sorted by name
        assert timelines[0].character_name == "Alpha"
        assert timelines[1].character_name == "Beta"

    def test_complex_chain(self):
        """Three versions deep, only head should produce a timeline."""
        ch1 = _make_character("CH-0001", version=1, status="superseded")
        ch2 = _make_character("CH-0002", version=2, previous_version="CH-0001",
                              status="superseded")
        ch3 = _make_character("CH-0003", version=3, previous_version="CH-0002")
        chars = _mock_char_manager([ch1, ch2, ch3])
        history = EvolutionHistory(character_manager=chars)

        timelines = history.list_timelines()
        assert len(timelines) == 1
        assert timelines[0].version_chain == ["CH-0001", "CH-0002", "CH-0003"]


# ═══════════════════════════════════════════════════════════════
# Diff Versions Tests
# ═══════════════════════════════════════════════════════════════


class TestDiffVersions:
    """Tests for diff_versions()."""

    def test_no_changes(self):
        ch = _make_character("CH-0001")
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0001")
        assert diffs == ["(no differences)"]

    def test_trait_added(self):
        ch1 = _make_character("CH-0001", traits=[_make_trait("Curious")])
        ch2 = _make_character("CH-0002", traits=[_make_trait("Curious"), _make_trait("Brave", intensity=0.5)])
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0002")
        added = [d for d in diffs if d.startswith("+ Trait")]
        assert len(added) == 1
        assert "Brave" in added[0]

    def test_trait_removed(self):
        ch1 = _make_character("CH-0001", traits=[_make_trait("Curious"), _make_trait("Timid")])
        ch2 = _make_character("CH-0002", traits=[_make_trait("Curious")])
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0002")
        removed = [d for d in diffs if d.startswith("- Trait")]
        assert len(removed) == 1
        assert "Timid" in removed[0]

    def test_field_updated(self):
        ch1 = _make_character("CH-0001", backstory="Old backstory")
        ch2 = _make_character("CH-0002", backstory="New backstory")
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0002")
        field_changes = [d for d in diffs if d.startswith("~ Backstory")]
        assert len(field_changes) == 1
        assert "Old backstory" in field_changes[0]
        assert "New backstory" in field_changes[0]

    def test_multiple_changes(self):
        ch1 = _make_character("CH-0001", name="Atlas", backstory="Old",
                              traits=[_make_trait("Curious")])
        ch2 = _make_character("CH-0002", name="Atlas Prime", backstory="New",
                              traits=[_make_trait("Curious"), _make_trait("Brave")])
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0002")
        # Should have: name change, backstory change, trait added
        assert len(diffs) >= 3

    def test_version_change(self):
        ch1 = _make_character("CH-0001", version=1)
        ch2 = _make_character("CH-0002", version=2)
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0002")
        version_changes = [d for d in diffs if "Version" in d]
        assert len(version_changes) == 1
        assert "1" in version_changes[0]
        assert "2" in version_changes[0]

    def test_trait_modified(self):
        ch1 = _make_character("CH-0001", traits=[_make_trait("Curious", intensity=0.3)])
        ch2 = _make_character("CH-0002", traits=[_make_trait("Curious", intensity=0.9)])
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0002")
        modified = [d for d in diffs if d.startswith("~ Trait")]
        assert len(modified) == 1
        assert "intensity" in modified[0]

    def test_tag_changes(self):
        ch1 = _make_character("CH-0001", tags=["explorer", "hero"])
        ch2 = _make_character("CH-0002", tags=["explorer", "warrior"])
        chars = _mock_char_manager([ch1, ch2])
        history = EvolutionHistory(character_manager=chars)

        diffs = history.diff_versions("CH-0001", "CH-0002")
        removed_tags = [d for d in diffs if d.startswith("- Tag")]
        added_tags = [d for d in diffs if d.startswith("+ Tag")]
        assert len(removed_tags) == 1
        assert "#hero" in removed_tags[0]
        assert len(added_tags) == 1
        assert "#warrior" in added_tags[0]

    def test_not_found(self):
        chars = _mock_char_manager([])
        history = EvolutionHistory(character_manager=chars)
        from core.characters import CharacterNotFoundError
        with pytest.raises(CharacterNotFoundError):
            history.diff_versions("CH-0001", "CH-0002")


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_characters(self):
        ch = _make_character("CH-0001", name="Герой", backstory="探検家の物語",
                             system_prompt="你是一个AI")
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        snap = history.get_snapshot("CH-0001")
        assert snap.name == "Герой"

    def test_long_chain(self):
        """Build a chain of 10 versions."""
        characters = []
        for i in range(1, 11):
            prev = f"CH-{i-1:04d}" if i > 1 else ""
            status = "superseded" if i < 10 else "active"
            ch = _make_character(f"CH-{i:04d}", version=i,
                                 previous_version=prev, status=status)
            characters.append(ch)
        chars = _mock_char_manager(characters)
        history = EvolutionHistory(character_manager=chars)

        chain = history.get_version_chain("CH-0010")
        assert len(chain) == 10
        assert chain[0] == "CH-0001"
        assert chain[-1] == "CH-0010"

    def test_evolution_with_no_changes(self):
        """Evolution record with empty changes list."""
        ch = _make_character("CH-0001")
        evo = EvolutionRecord(
            evolution_id="EV-0001", character_id="CH-0001",
            author="Sage", changes=[], status="draft",
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-01T00:00:00+00:00",
        )
        chars = _mock_char_manager([ch])
        evo_mgr = _mock_evo_manager([evo])
        history = EvolutionHistory(character_manager=chars, evolution_manager=evo_mgr)

        tl = history.build_timeline("CH-0001")
        assert len(tl.events) == 1
        assert tl.events[0].changes_summary == "(no changes)"

    def test_snapshot_to_dict_roundtrip(self):
        ch = _make_character("CH-0001")
        chars = _mock_char_manager([ch])
        history = EvolutionHistory(character_manager=chars)

        snap = history.get_snapshot("CH-0001")
        d = snap.to_dict()
        restored = VersionSnapshot.from_dict(d)
        assert restored.character_id == snap.character_id
        assert restored.name == snap.name

    def test_timeline_with_mixed_evolution_statuses(self):
        """Timeline should include evolutions of all statuses."""
        ch = _make_character("CH-0001")
        evo_draft = _make_evolution("EV-0001", "CH-0001", status="draft")
        evo_applied = _make_evolution("EV-0002", "CH-0001", status="applied")
        evo_rejected = _make_evolution("EV-0003", "CH-0001", status="rejected")
        chars = _mock_char_manager([ch])
        evo_mgr = _mock_evo_manager([evo_draft, evo_applied, evo_rejected])
        history = EvolutionHistory(character_manager=chars, evolution_manager=evo_mgr)

        tl = history.build_timeline("CH-0001")
        assert len(tl.events) == 3


# ═══════════════════════════════════════════════════════════════
# Dashboard Rendering Tests
# ═══════════════════════════════════════════════════════════════


class TestDashboardRendering:
    """Tests for dashboard render methods for evolution history."""

    def _make_console(self):
        from io import StringIO
        from rich.console import Console
        buf = StringIO()
        return Console(file=buf, force_terminal=True, width=120), buf

    def test_render_evolution_timeline(self):
        from core.dashboard import DashboardRenderer

        console, buf = self._make_console()
        renderer = DashboardRenderer(console=console)

        snap1 = VersionSnapshot(
            character_id="CH-0001", name="Atlas", version=1,
            status="superseded", author="Forge",
            traits_summary="Curious (0.7)", trait_count=1,
            system_prompt_excerpt="You are Atlas.",
            backstory_excerpt="A brave explorer",
        )
        snap2 = VersionSnapshot(
            character_id="CH-0002", name="Atlas", version=2,
            status="active", author="Forge",
            traits_summary="Curious (0.7), Brave (0.5)", trait_count=2,
            system_prompt_excerpt="You are Atlas v2.",
            backstory_excerpt="A seasoned explorer",
        )
        evt = EvolutionEvent(
            evolution_id="EV-0001", character_id="CH-0001",
            author="Sage", changes_summary="trait_add:brave",
            change_count=1, proposal_id="P-0001",
            vote_result="Approved (80%)", status="applied",
            applied_character_id="CH-0002",
        )
        timeline = CharacterTimeline(
            character_name="Atlas",
            version_chain=["CH-0001", "CH-0002"],
            snapshots=[snap1, snap2],
            events=[evt],
            latest_version="CH-0002",
        )

        renderer.render_evolution_timeline(timeline)
        output = buf.getvalue()
        assert "Atlas" in output
        assert "CH-0001" in output
        assert "CH-0002" in output
        assert "EV-0001" in output

    def test_render_evolution_timeline_empty(self):
        from core.dashboard import DashboardRenderer

        console, buf = self._make_console()
        renderer = DashboardRenderer(console=console)

        timeline = CharacterTimeline(
            character_name="Atlas",
            version_chain=["CH-0001"],
            snapshots=[],
            events=[],
            latest_version="CH-0001",
        )

        renderer.render_evolution_timeline(timeline)
        output = buf.getvalue()
        assert "Atlas" in output

    def test_render_version_diff(self):
        from core.dashboard import DashboardRenderer

        console, buf = self._make_console()
        renderer = DashboardRenderer(console=console)

        diffs = [
            "+ Trait: Brave (personality, 0.7)",
            "- Trait: Timid (personality, 0.3)",
            "~ Name: 'Atlas' → 'Atlas Prime'",
        ]

        renderer.render_version_diff("CH-0001", "CH-0002", diffs)
        output = buf.getvalue()
        assert "Brave" in output
        assert "Timid" in output
        assert "CH-0001" in output

    def test_render_version_diff_no_changes(self):
        from core.dashboard import DashboardRenderer

        console, buf = self._make_console()
        renderer = DashboardRenderer(console=console)

        renderer.render_version_diff("CH-0001", "CH-0001", ["(no differences)"])
        output = buf.getvalue()
        assert "no differences" in output

    def test_render_timeline_list(self):
        from core.dashboard import DashboardRenderer

        console, buf = self._make_console()
        renderer = DashboardRenderer(console=console)

        timelines = [
            CharacterTimeline(
                character_name="Atlas",
                version_chain=["CH-0001", "CH-0002"],
                latest_version="CH-0002",
            ),
            CharacterTimeline(
                character_name="Nova",
                version_chain=["CH-0003"],
                latest_version="CH-0003",
            ),
        ]

        renderer.render_timeline_list(timelines)
        output = buf.getvalue()
        assert "Atlas" in output
        assert "Nova" in output
        assert "CH-0002" in output

    def test_render_timeline_list_empty(self):
        from core.dashboard import DashboardRenderer

        console, buf = self._make_console()
        renderer = DashboardRenderer(console=console)

        renderer.render_timeline_list([])
        output = buf.getvalue()
        assert "No" in output


# ═══════════════════════════════════════════════════════════════
# CLI Command Tests
# ═══════════════════════════════════════════════════════════════


class TestCLICommands:
    """Tests for the history CLI subcommands."""

    def test_history_timeline(self):
        from click.testing import CliRunner
        from core.cli import cli

        ch = _make_character("CH-0001")
        mock_chars = _mock_char_manager([ch])

        runner = CliRunner()
        with patch("core.cli.CharacterManager", return_value=mock_chars):
            result = runner.invoke(cli, ["history", "timeline", "CH-0001"])
        assert result.exit_code == 0

    def test_history_timeline_not_found(self):
        from click.testing import CliRunner
        from core.cli import cli

        mock_chars = _mock_char_manager([])

        runner = CliRunner()
        with patch("core.cli.CharacterManager", return_value=mock_chars):
            result = runner.invoke(cli, ["history", "timeline", "CH-9999"])
        assert result.exit_code != 0

    def test_history_diff(self):
        from click.testing import CliRunner
        from core.cli import cli

        ch1 = _make_character("CH-0001")
        ch2 = _make_character("CH-0002", name="Atlas Prime")
        mock_chars = _mock_char_manager([ch1, ch2])

        runner = CliRunner()
        with patch("core.cli.CharacterManager", return_value=mock_chars):
            result = runner.invoke(cli, ["history", "diff", "CH-0001", "CH-0002"])
        assert result.exit_code == 0

    def test_history_list(self):
        from click.testing import CliRunner
        from core.cli import cli

        ch = _make_character("CH-0001")
        mock_chars = _mock_char_manager([ch])

        runner = CliRunner()
        with patch("core.cli.CharacterManager", return_value=mock_chars):
            result = runner.invoke(cli, ["history", "list"])
        assert result.exit_code == 0

    def test_history_help(self):
        from click.testing import CliRunner
        from core.cli import cli

        runner = CliRunner()
        result = runner.invoke(cli, ["history", "--help"])
        assert result.exit_code == 0
        assert "history" in result.output.lower()
