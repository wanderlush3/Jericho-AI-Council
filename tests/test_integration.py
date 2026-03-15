"""
Jericho — Cross-Module Integration Tests (F-017)

Tests that exercise real workflows spanning multiple managers.
API calls are mocked at the transport layer; everything else
uses real filesystem-backed managers via tmp_path.

~65 tests across 5 integration suites.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Core imports ─────────────────────────────────────────────
from core.api_client import ChatMessage, ChatResponse
from core.characters import (
    CharacterManager,
    CharacterNotFoundError,
    CharacterTemplate,
    Trait,
)
from core.character_evolution import (
    CharacterChange,
    CharacterEvolution,
    EvolutionRecord,
    EvolutionStateError,
    EvolutionValidationError,
)
from core.discussion import DiscussionManager
from core.memory import AgentMemory, MemoryEntry, SharedMemory
from core.proposals import Proposal, ProposalManager
from core.session import SessionOrchestrator, SessionRecord
from core.voting import Vote, VotingEngine
from core.analytics import SessionAnalytics

# Shared helpers from conftest
from tests.conftest import make_member, mock_api_client, mock_registry


# ═══════════════════════════════════════════════════════════════
# 1. Governance Workflow: proposal → discussion → vote → decide
# ═══════════════════════════════════════════════════════════════


class TestGovernanceWorkflow:
    """End-to-end governance: create proposal, discuss, vote, close."""

    # ── helpers ────────────────────────────────────────────────

    @pytest.fixture
    def govn(self, tmp_dirs):
        """Set up all governance components."""
        pm = ProposalManager(proposals_dir=tmp_dirs["proposals"])
        ve = VotingEngine(
            votes_dir=tmp_dirs["votes"], quorum=2, threshold=0.6,
        )
        api = mock_api_client("I support this proposal.")
        sage = make_member("Sage", "Ethics")
        logic = make_member("Logic", "Systems")
        spark = make_member("Spark", "Creative", api_provider="mancer")
        reg = mock_registry(sage, logic, spark)
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        dm = DiscussionManager(
            registry=reg,
            api_client=api,
            proposal_manager=pm,
            discussions_dir=tmp_dirs["discussions"],
            shared_memory=shared,
        )
        return {
            "pm": pm, "ve": ve, "dm": dm, "shared": shared,
            "api": api, "reg": reg,
        }

    # ── tests ─────────────────────────────────────────────────

    def test_proposal_created_and_retrievable(self, govn):
        pm = govn["pm"]
        p = pm.create("Ethics Reform", "Reform ethics guidelines",
                       author="Sage", category="ethics")
        assert p.id == "P-0001"
        assert pm.get(p.id).title == "Ethics Reform"

    def test_proposal_status_lifecycle(self, govn):
        pm = govn["pm"]
        p = pm.create("Test", "Desc", author="Logic", category="governance")
        assert p.status == "draft"
        pm.update_status(p.id, "open")
        assert pm.get(p.id).status == "open"
        pm.update_status(p.id, "under_review")
        assert pm.get(p.id).status == "under_review"

    def test_discussion_on_proposal(self, govn):
        pm, dm = govn["pm"], govn["dm"]
        p = pm.create("Discuss Me", "Desc", author="Sage", category="ethics")
        pm.update_status(p.id, "open")
        rec = dm.create_discussion(
            "D-001", p.id, "Ethics Discussion",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(dm.run_round("D-001"))
        assert rec.current_round == 1
        assert len(rec.contributions) == 2

    def test_discussion_close_records_shared_memory(self, govn):
        pm, dm, shared = govn["pm"], govn["dm"], govn["shared"]
        p = pm.create("MemTest", "Desc", author="Sage", category="ethics")
        pm.update_status(p.id, "open")
        dm.create_discussion(
            "D-001", p.id, "Close Test",
            participants=["Sage", "Logic"],
        )
        dm.close_discussion("D-001", summary="Reached consensus.")
        decisions = shared.read_decisions()
        assert any(d["type"] == "discussion_closed" for d in decisions)

    def test_vote_after_discussion(self, govn):
        pm, dm, ve = govn["pm"], govn["dm"], govn["ve"]
        p = pm.create("VoteTest", "Desc", author="Sage", category="ethics")
        pm.update_status(p.id, "open")
        dm.create_discussion(
            "D-001", p.id, "Pre-vote discussion",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(dm.run_all_rounds("D-001"))
        dm.close_discussion("D-001")

        # Open voting and cast votes
        ve.open_voting(p.id)
        ve.cast_vote(p.id, Vote.create("Sage", "for"))
        ve.cast_vote(p.id, Vote.create("Logic", "for"))
        ve.cast_vote(p.id, Vote.create("Spark", "against"))
        ve.close_voting(p.id)

        record = ve.get(p.id)
        assert record.status == "closed"
        tally = ve.tally(p.id)
        assert tally.approved is True

    def test_full_governance_pipeline(self, govn):
        """Proposal → discuss → vote → decide (end-to-end)."""
        pm, dm, ve, shared = (
            govn["pm"], govn["dm"], govn["ve"], govn["shared"],
        )
        # 1. Create proposal
        p = pm.create("Full Pipeline", "Full test",
                       author="Sage", category="governance")
        pm.update_status(p.id, "open")

        # 2. Discuss
        dm.create_discussion(
            "D-001", p.id, "Pipeline Discussion",
            participants=["Sage", "Logic", "Spark"],
            round_count=1,
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(dm.run_all_rounds("D-001"))
        disc = dm.close_discussion("D-001")
        assert disc.status == "closed"

        # 3. Vote
        ve.open_voting(p.id)
        ve.cast_vote(p.id, Vote.create("Sage", "for"))
        ve.cast_vote(p.id, Vote.create("Logic", "for"))
        ve.cast_vote(p.id, Vote.create("Spark", "for"))
        ve.close_voting(p.id)
        tally = ve.tally(p.id)
        assert tally.approved is True

        # 4. Finalize proposal
        pm.update_status(p.id, "under_review")
        pm.update_status(p.id, "decided")
        assert pm.get(p.id).status == "decided"

        # 5. Shared memory has decision record
        decisions = shared.read_decisions()
        assert len(decisions) >= 1

    def test_vetoed_proposal(self, govn):
        pm, ve = govn["pm"], govn["ve"]
        p = pm.create("Vetoed", "Desc", author="Logic", category="ethics")
        pm.update_status(p.id, "open")
        ve.open_voting(p.id)
        ve.cast_vote(p.id, Vote.create("Sage", "for"))
        ve.cast_vote(p.id, Vote.create("Logic", "for"))
        ve.veto(p.id, "Overruled by council chair")
        record = ve.get(p.id)
        assert record.vetoed is True

    def test_no_quorum_rejects(self, govn):
        pm, ve = govn["pm"], govn["ve"]
        p = pm.create("NoQuorum", "Desc", author="Sage", category="general")
        pm.update_status(p.id, "open")
        ve.open_voting(p.id)
        ve.cast_vote(p.id, Vote.create("Sage", "for"))  # only 1, quorum=2
        ve.close_voting(p.id)
        tally = ve.tally(p.id)
        assert tally.approved is False

    def test_multiple_proposals_independent(self, govn):
        pm, ve = govn["pm"], govn["ve"]
        p1 = pm.create("First", "D1", author="Sage", category="ethics")
        p2 = pm.create("Second", "D2", author="Logic", category="governance")
        pm.update_status(p1.id, "open")
        pm.update_status(p2.id, "open")

        ve.open_voting(p1.id)
        ve.open_voting(p2.id)
        ve.cast_vote(p1.id, Vote.create("Sage", "for"))
        ve.cast_vote(p1.id, Vote.create("Logic", "for"))
        ve.cast_vote(p2.id, Vote.create("Sage", "against"))
        ve.cast_vote(p2.id, Vote.create("Logic", "against"))
        ve.close_voting(p1.id)
        ve.close_voting(p2.id)

        assert ve.tally(p1.id).approved is True
        assert ve.tally(p2.id).approved is False


# ═══════════════════════════════════════════════════════════════
# 2. Character Lifecycle: create → activate → evolve → version
# ═══════════════════════════════════════════════════════════════


class TestCharacterLifecycle:
    """End-to-end character creation, evolution, and versioning."""

    @pytest.fixture
    def char_env(self, tmp_dirs):
        """Character lifecycle environment."""
        cm = CharacterManager(characters_dir=tmp_dirs["characters"])
        pm = ProposalManager(proposals_dir=tmp_dirs["proposals"])
        ve = VotingEngine(
            votes_dir=tmp_dirs["votes"], quorum=2, threshold=0.6,
        )
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        evo = CharacterEvolution(
            character_manager=cm,
            proposal_manager=pm,
            voting_engine=ve,
            evolutions_dir=tmp_dirs["evolutions"],
            shared_memory=shared,
        )
        return {"cm": cm, "pm": pm, "ve": ve, "evo": evo, "shared": shared}

    def _create_active_char(self, cm: CharacterManager) -> CharacterTemplate:
        trait = Trait.create("personality", "Curious", "Questions everything", intensity=0.7)
        char = cm.create(
            "Atlas", "An explorer AI", author="Forge",
            traits=[trait],
            backstory="Born from curiosity.",
            system_prompt="You are Atlas, an explorer.",
        )
        return cm.update_status(char.id, "active")

    def _make_change(self, **kw) -> CharacterChange:
        defaults = {
            "change_type": "trait_add",
            "field_name": "bravery",
            "new_value": {
                "trait_type": "personality", "name": "bravery",
                "description": "Fearless", "intensity": 0.8,
            },
            "rationale": "Needs courage",
        }
        defaults.update(kw)
        return CharacterChange.create(**defaults)

    # ── tests ─────────────────────────────────────────────────

    def test_create_and_activate(self, char_env):
        cm = char_env["cm"]
        char = self._create_active_char(cm)
        assert char.status == "active"
        assert char.version == 1

    def test_evolution_creates_proposal(self, char_env):
        cm, pm, evo = char_env["cm"], char_env["pm"], char_env["evo"]
        char = self._create_active_char(cm)
        change = self._make_change()
        rec = evo.create_evolution(char.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        assert rec.status == "proposed"
        assert rec.proposal_id.startswith("P-")
        # Verify the proposal was actually created in ProposalManager
        proposal = pm.get(rec.proposal_id)
        assert proposal.category == "character"

    def test_evolution_voting_approved(self, char_env):
        cm, ve, evo = char_env["cm"], char_env["ve"], char_env["evo"]
        char = self._create_active_char(cm)
        change = self._make_change()
        rec = evo.create_evolution(char.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        assert rec.status == "voting"
        ve.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        ve.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "decided"
        assert "Approved" in rec.summary

    def test_evolution_apply_creates_new_version(self, char_env):
        cm, ve, evo = char_env["cm"], char_env["ve"], char_env["evo"]
        char = self._create_active_char(cm)
        change = self._make_change()
        rec = evo.create_evolution(char.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        ve.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        ve.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        new_char = evo.apply_evolution(rec.evolution_id)
        assert new_char.version == 2
        assert new_char.status == "active"
        # Original should be superseded
        original = cm.get(char.id)
        assert original.status == "superseded"
        # New char has the added trait
        assert any(t.name == "bravery" for t in new_char.traits)

    def test_full_character_lifecycle(self, char_env):
        """Create → activate → evolve → approve → apply → verify."""
        cm, pm, ve, evo = (
            char_env["cm"], char_env["pm"],
            char_env["ve"], char_env["evo"],
        )
        # 1. Create and activate
        char = self._create_active_char(cm)
        assert char.version == 1

        # 2. Propose evolution
        change = CharacterChange.create(
            "field_update", "backstory",
            old_value=char.backstory,
            new_value="A brave explorer forged in the fires of discovery.",
            rationale="Richer narrative",
        )
        rec = evo.create_evolution(char.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)

        # 3. Vote on evolution
        rec = evo.open_voting(rec.evolution_id)
        ve.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        ve.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "decided"

        # 4. Apply evolution
        new_char = evo.apply_evolution(rec.evolution_id)
        assert new_char.version == 2
        assert new_char.backstory == "A brave explorer forged in the fires of discovery."

        # 5. Verify original superseded
        old = cm.get(char.id)
        assert old.status == "superseded"

    def test_rejected_evolution_not_applied(self, char_env):
        cm, ve, evo = char_env["cm"], char_env["ve"], char_env["evo"]
        char = self._create_active_char(cm)
        change = self._make_change()
        rec = evo.create_evolution(char.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        # Vote against
        ve.cast_vote(rec.proposal_id, Vote.create("Sage", "against"))
        ve.cast_vote(rec.proposal_id, Vote.create("Logic", "against"))
        rec = evo.resolve(rec.evolution_id)
        assert rec.status == "rejected"
        # Cannot apply rejected evolution
        with pytest.raises(EvolutionStateError):
            evo.apply_evolution(rec.evolution_id)
        # Original stays active
        assert cm.get(char.id).status == "active"

    def test_multiple_evolutions_sequential(self, char_env):
        cm, ve, evo = char_env["cm"], char_env["ve"], char_env["evo"]
        char = self._create_active_char(cm)

        # First evolution
        c1 = self._make_change(field_name="bravery")
        r1 = evo.create_evolution(char.id, author="Sage", changes=[c1])
        r1 = evo.submit_for_review(r1.evolution_id)
        r1 = evo.open_voting(r1.evolution_id)
        ve.cast_vote(r1.proposal_id, Vote.create("Sage", "for"))
        ve.cast_vote(r1.proposal_id, Vote.create("Logic", "for"))
        r1 = evo.resolve(r1.evolution_id)
        char_v2 = evo.apply_evolution(r1.evolution_id)
        assert char_v2.version == 2

        # Second evolution on new version
        c2 = CharacterChange.create(
            "field_update", "backstory",
            new_value="Updated by second evolution.",
            rationale="Further development",
        )
        r2 = evo.create_evolution(char_v2.id, author="Logic", changes=[c2])
        r2 = evo.submit_for_review(r2.evolution_id)
        r2 = evo.open_voting(r2.evolution_id)
        ve.cast_vote(r2.proposal_id, Vote.create("Sage", "for"))
        ve.cast_vote(r2.proposal_id, Vote.create("Logic", "for"))
        r2 = evo.resolve(r2.evolution_id)
        char_v3 = evo.apply_evolution(r2.evolution_id)
        assert char_v3.version == 3
        assert char_v3.backstory == "Updated by second evolution."

    def test_evolution_on_inactive_character_fails(self, char_env):
        cm, evo = char_env["cm"], char_env["evo"]
        trait = Trait.create("personality", "Test", "test", intensity=0.5)
        char = cm.create("Draft", "A draft", author="Forge", traits=[trait])
        change = self._make_change()
        with pytest.raises(EvolutionValidationError, match="must be in 'active'"):
            evo.create_evolution(char.id, author="Sage", changes=[change])

    def test_trait_removal_via_evolution(self, char_env):
        cm, ve, evo = char_env["cm"], char_env["ve"], char_env["evo"]
        char = self._create_active_char(cm)
        # Add extra trait so removal is valid
        extra = Trait.create("values", "Honesty", "Truthful", intensity=0.6)
        cm.add_trait(char.id, extra)
        change = CharacterChange.create(
            "trait_remove", "Curious",
            rationale="Evolved beyond curiosity",
        )
        rec = evo.create_evolution(char.id, author="Sage", changes=[change])
        rec = evo.submit_for_review(rec.evolution_id)
        rec = evo.open_voting(rec.evolution_id)
        ve.cast_vote(rec.proposal_id, Vote.create("Sage", "for"))
        ve.cast_vote(rec.proposal_id, Vote.create("Logic", "for"))
        rec = evo.resolve(rec.evolution_id)
        new_char = evo.apply_evolution(rec.evolution_id)
        assert not any(t.name == "Curious" for t in new_char.traits)
        assert any(t.name == "Honesty" for t in new_char.traits)


# ═══════════════════════════════════════════════════════════════
# 3. Session Lifecycle: create → brief → discuss → close
# ═══════════════════════════════════════════════════════════════


class TestSessionLifecycle:
    """Full session lifecycle with real shared memory."""

    @pytest.fixture
    def sess_env(self, tmp_dirs):
        sage = make_member("Sage", "Ethics")
        logic = make_member("Logic", "Systems")
        reg = mock_registry(sage, logic)
        api = mock_api_client("I understand the agenda.")
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        orch = SessionOrchestrator(
            registry=reg,
            api_client=api,
            conversations_dir=tmp_dirs["conversations"],
            shared_memory=shared,
        )
        return {"orch": orch, "shared": shared, "api": api}

    def test_create_session(self, sess_env):
        orch = sess_env["orch"]
        rec = orch.create_session("S-001", "Test Session", participants=["Sage"])
        assert rec.session_id == "S-001"
        assert rec.phase == "created"

    def test_session_phase_progression(self, sess_env):
        orch = sess_env["orch"]
        orch.create_session("S-001", "Phases", participants=["Sage"])
        loop = asyncio.get_event_loop()
        rec = loop.run_until_complete(orch.start_session("S-001"))
        assert rec.phase == "briefing"
        rec = loop.run_until_complete(orch.activate_session("S-001"))
        assert rec.phase == "active"
        rec = loop.run_until_complete(orch.begin_summary("S-001"))
        assert rec.phase == "summary"
        rec = loop.run_until_complete(
            orch.close_session("S-001", summary="Done.")
        )
        assert rec.phase == "closed"

    def test_brief_member_records_messages(self, sess_env):
        orch = sess_env["orch"]
        orch.create_session("S-001", "Brief Test", participants=["Sage"])
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orch.start_session("S-001"))
        rec = loop.run_until_complete(orch.brief_member("S-001", "Sage"))
        # orchestrator prompt + member response
        assert len(rec.messages) == 2
        assert rec.messages[0].speaker == "orchestrator"
        assert rec.messages[1].speaker == "Sage"

    def test_discussion_records_messages(self, sess_env):
        orch = sess_env["orch"]
        orch.create_session(
            "S-001", "Discussion", participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orch.start_session("S-001"))
        loop.run_until_complete(orch.activate_session("S-001"))
        rec = loop.run_until_complete(
            orch.discuss("S-001", "AI Ethics", ["Sage", "Logic"])
        )
        # topic announcement + 2 responses
        assert len(rec.messages) == 3

    def test_close_records_shared_memory(self, sess_env):
        orch, shared = sess_env["orch"], sess_env["shared"]
        orch.create_session("S-001", "SharedMem", participants=["Sage"])
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orch.start_session("S-001"))
        loop.run_until_complete(orch.activate_session("S-001"))
        loop.run_until_complete(orch.begin_summary("S-001"))
        loop.run_until_complete(
            orch.close_session("S-001", summary="Session complete.")
        )
        decisions = shared.read_decisions()
        assert any(
            d.get("type") == "session_closed" and d.get("session_id") == "S-001"
            for d in decisions
        )

    def test_close_records_history(self, sess_env):
        orch, shared = sess_env["orch"], sess_env["shared"]
        orch.create_session("S-001", "HistTest", participants=["Sage"])
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orch.start_session("S-001"))
        loop.run_until_complete(orch.activate_session("S-001"))
        loop.run_until_complete(orch.begin_summary("S-001"))
        loop.run_until_complete(
            orch.close_session("S-001", summary="Completed.")
        )
        history = shared.read_history()
        assert "HistTest" in history

    def test_full_session_lifecycle(self, sess_env):
        """Create → brief → discuss → summarize → close."""
        orch, shared = sess_env["orch"], sess_env["shared"]
        orch.create_session(
            "S-001", "Full Lifecycle",
            activity_type="discussion",
            participants=["Sage", "Logic"],
        )
        loop = asyncio.get_event_loop()

        # Start & brief
        loop.run_until_complete(orch.start_session("S-001"))
        loop.run_until_complete(orch.brief_member("S-001", "Sage"))
        loop.run_until_complete(orch.brief_member("S-001", "Logic"))

        # Activate & discuss
        loop.run_until_complete(orch.activate_session("S-001"))
        loop.run_until_complete(
            orch.discuss("S-001", "AI autonomy", ["Sage", "Logic"])
        )

        # Summary & close
        loop.run_until_complete(orch.begin_summary("S-001"))
        rec = loop.run_until_complete(
            orch.close_session("S-001", summary="Ethics reviewed.")
        )
        assert rec.phase == "closed"
        assert rec.summary == "Ethics reviewed."
        assert len(rec.messages) >= 5  # briefs + discussion + topic

    def test_human_message_in_session(self, sess_env):
        orch = sess_env["orch"]
        orch.create_session("S-001", "HumanMsg", participants=["Sage"])
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orch.start_session("S-001"))
        rec = orch.add_human_message("S-001", "I have a question")
        assert rec.messages[0].speaker == "human"

    def test_multiple_sessions_isolated(self, sess_env):
        orch = sess_env["orch"]
        orch.create_session("S-001", "First", participants=["Sage"])
        orch.create_session("S-002", "Second", participants=["Logic"])
        assert orch.has_session("S-001")
        assert orch.has_session("S-002")
        sessions = orch.list_sessions()
        assert len(sessions) == 2


# ═══════════════════════════════════════════════════════════════
# 4. Memory Integration: cross-module memory verification
# ═══════════════════════════════════════════════════════════════


class TestMemoryIntegration:
    """Verify that module actions produce retrievable memory entries."""

    def test_agent_memory_write_and_read(self, tmp_dirs):
        mem = AgentMemory("sage", memories_dir=tmp_dirs["memories"])
        entry = MemoryEntry.create(
            "S-001", "briefing", "Agent was briefed on AI ethics topic",
            source="session",
        )
        mem.append_session_event(entry)
        log = mem.read_session_log()
        assert len(log) == 1
        assert log[0].session_id == "S-001"
        assert log[0].event_type == "briefing"

    def test_shared_memory_decisions_persist(self, tmp_dirs):
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        shared.record_decision({
            "type": "session_closed",
            "session_id": "S-001",
            "summary": "Test decision",
        })
        shared.record_decision({
            "type": "vote_completed",
            "proposal_id": "P-0001",
        })
        decisions = shared.read_decisions()
        assert len(decisions) == 2
        assert decisions[0]["type"] == "session_closed"
        assert decisions[1]["type"] == "vote_completed"

    def test_shared_memory_history_append(self, tmp_dirs):
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        shared.append_history("## Session 1\nEthics discussed.\n")
        shared.append_history("## Session 2\nGovernance reviewed.\n")
        history = shared.read_history()
        assert "Session 1" in history
        assert "Session 2" in history

    def test_multiple_agents_independent_memory(self, tmp_dirs):
        sage_mem = AgentMemory("sage", memories_dir=tmp_dirs["memories"])
        logic_mem = AgentMemory("logic", memories_dir=tmp_dirs["memories"])
        sage_mem.append_session_event(
            MemoryEntry.create("S-001", "chat", "Sage spoke")
        )
        logic_mem.append_session_event(
            MemoryEntry.create("S-001", "chat", "Logic spoke")
        )
        assert len(sage_mem.read_session_log()) == 1
        assert len(logic_mem.read_session_log()) == 1
        assert sage_mem.read_session_log()[0].content == "Sage spoke"

    def test_session_close_populates_shared_memory(self, tmp_dirs):
        """Session close → shared memory decision record."""
        sage = make_member("Sage")
        reg = mock_registry(sage)
        api = mock_api_client()
        shared = SharedMemory(shared_dir=tmp_dirs["shared"])
        orch = SessionOrchestrator(
            registry=reg,
            api_client=api,
            conversations_dir=tmp_dirs["conversations"],
            shared_memory=shared,
        )
        orch.create_session("S-001", "MemIntegration", participants=["Sage"])
        loop = asyncio.get_event_loop()
        loop.run_until_complete(orch.start_session("S-001"))
        loop.run_until_complete(orch.activate_session("S-001"))
        loop.run_until_complete(orch.begin_summary("S-001"))
        loop.run_until_complete(
            orch.close_session("S-001", summary="Memory integration test.")
        )
        decisions = shared.read_decisions()
        assert len(decisions) >= 1
        assert decisions[0]["type"] == "session_closed"

    def test_core_beliefs_roundtrip(self, tmp_dirs):
        from core.memory import CoreBelief
        mem = AgentMemory("sage", memories_dir=tmp_dirs["memories"])
        belief = CoreBelief.create("safety", "Safety is paramount", source="session-1")
        mem.write_core_belief(belief)
        beliefs = mem.read_core_beliefs()
        assert len(beliefs) == 1
        assert beliefs[0].topic == "safety"
        assert beliefs[0].content == "Safety is paramount"

    def test_session_log_filter_by_session(self, tmp_dirs):
        mem = AgentMemory("sage", memories_dir=tmp_dirs["memories"])
        mem.append_session_event(
            MemoryEntry.create("S-001", "chat", "Message 1")
        )
        mem.append_session_event(
            MemoryEntry.create("S-002", "chat", "Message 2")
        )
        s1 = mem.read_session_log(session_id="S-001")
        assert len(s1) == 1
        assert s1[0].content == "Message 1"

    def test_recent_memories_ordered(self, tmp_dirs):
        mem = AgentMemory("sage", memories_dir=tmp_dirs["memories"])
        for i in range(5):
            mem.append_session_event(
                MemoryEntry.create("S-001", "chat", f"Message {i}")
            )
        recent = mem.get_recent_memories(limit=3)
        assert len(recent) == 3
        assert recent[0].content == "Message 4"  # newest first
        assert recent[2].content == "Message 2"


# ═══════════════════════════════════════════════════════════════
# 5. Analytics Integration: stats computed from real manager data
# ═══════════════════════════════════════════════════════════════


class TestAnalyticsIntegration:
    """Analytics engine producing correct stats from populated managers."""

    @pytest.fixture
    def analytics_env(self, tmp_dirs):
        pm = ProposalManager(proposals_dir=tmp_dirs["proposals"])
        ve = VotingEngine(
            votes_dir=tmp_dirs["votes"], quorum=2, threshold=0.6,
        )
        return {"pm": pm, "ve": ve}

    def test_proposal_stats_match_manager(self, analytics_env):
        pm = analytics_env["pm"]
        pm.create("P1", "D1", author="Sage", category="ethics")
        pm.create("P2", "D2", author="Logic", category="governance")
        pm.create("P3", "D3", author="Sage", category="ethics")

        sa = SessionAnalytics(proposal_manager=pm)
        stats = sa.proposal_stats()
        assert stats.total == 3
        assert stats.by_category["ethics"] == 2
        assert stats.by_category["governance"] == 1

    def test_voting_stats_match_engine(self, analytics_env):
        ve = analytics_env["ve"]
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))
        ve.open_voting("P-0002")
        ve.cast_vote("P-0002", Vote.create("Sage", "against"))

        sa = SessionAnalytics(voting_engine=ve)
        stats = sa.voting_stats()
        assert stats.total_records == 2
        assert stats.total_votes_cast == 3

    def test_member_stats_aggregate(self, analytics_env):
        pm, ve = analytics_env["pm"], analytics_env["ve"]
        pm.create("P1", "D", author="Sage", category="ethics")
        pm.create("P2", "D", author="Logic", category="governance")

        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "against"))

        sa = SessionAnalytics(proposal_manager=pm, voting_engine=ve)
        sage_stats = sa.member_stats("Sage")
        assert sage_stats.proposals_authored == 1
        assert sage_stats.votes_cast == 1
        assert sage_stats.votes_for == 1

    def test_all_member_stats(self, analytics_env):
        pm = analytics_env["pm"]
        pm.create("P1", "D", author="Sage", category="ethics")
        pm.create("P2", "D", author="Logic", category="governance")

        sa = SessionAnalytics(proposal_manager=pm)
        all_stats = sa.all_member_stats()
        assert "Sage" in all_stats
        assert "Logic" in all_stats

    def test_approval_rate_calculation(self, analytics_env):
        pm, ve = analytics_env["pm"], analytics_env["ve"]
        p1 = pm.create("P1", "D", author="Sage", category="ethics")
        p2 = pm.create("P2", "D", author="Sage", category="ethics")

        # Move both to decided
        for pid in [p1.id, p2.id]:
            pm.update_status(pid, "open")
            pm.update_status(pid, "under_review")
            pm.update_status(pid, "decided")

        # Approve p1, reject p2
        ve.open_voting(p1.id)
        ve.cast_vote(p1.id, Vote.create("A", "for"))
        ve.cast_vote(p1.id, Vote.create("B", "for"))
        ve.open_voting(p2.id)
        ve.cast_vote(p2.id, Vote.create("A", "against"))
        ve.cast_vote(p2.id, Vote.create("B", "against"))

        sa = SessionAnalytics(proposal_manager=pm, voting_engine=ve)
        stats = sa.proposal_stats()
        assert stats.approval_rate == 0.5

    def test_empty_analytics(self):
        sa = SessionAnalytics()
        assert sa.proposal_stats().total == 0
        assert sa.voting_stats().total_records == 0
        stats = sa.member_stats("Nobody")
        assert stats.total_activity == 0

    def test_session_stats_from_fake_orchestrator(self):
        from core.session import SessionMessage, SessionRecord

        sessions = [
            SessionRecord(
                session_id="S-001", title="Test",
                phase="closed", activity_type="discussion",
                participants=["Sage", "Logic"],
                messages=[
                    SessionMessage.create("Sage", "Hello"),
                    SessionMessage.create("Logic", "Hi"),
                ],
            ),
        ]

        class FakeOrch:
            def list_sessions(self, **kw):
                return sessions

        sa = SessionAnalytics(session_orchestrator=FakeOrch())
        stats = sa.session_stats()
        assert stats.total_sessions == 1
        assert stats.by_phase == {"closed": 1}
        assert stats.avg_participants == 2.0

    def test_full_analytics_report(self, analytics_env):
        pm, ve = analytics_env["pm"], analytics_env["ve"]
        pm.create("P1", "D", author="Sage", category="ethics")
        ve.open_voting("P-0001")
        ve.cast_vote("P-0001", Vote.create("Sage", "for"))
        ve.cast_vote("P-0001", Vote.create("Logic", "for"))

        sa = SessionAnalytics(proposal_manager=pm, voting_engine=ve)
        report = sa.full_report(member_names=["Sage", "Logic"])
        assert report.proposal_stats.total == 1
        assert report.voting_stats.total_records == 1
        assert "Sage" in report.member_stats
        assert "Logic" in report.member_stats
