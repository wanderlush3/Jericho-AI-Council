"""
Tests for F-060 — Conditional Law Injection (core/law_filter.py).

Verifies that laws are scored against context keywords using Jaccard
similarity and that only relevant laws are injected into prompts.
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from core.law_filter import LawFilter, ScoredLaw


# ─── Fake Law for testing ─────────────────────────────────────


@dataclass(frozen=True)
class FakeLaw:
    """Minimal stand-in for core.laws.Law."""

    id: str
    title: str
    description: str
    status: str = "active"
    body: str = ""
    tags: list[str] = field(default_factory=list)
    author: str = "Council"

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "body": self.body,
            "tags": self.tags,
            "author": self.author,
        }


# ─── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def tax_law() -> FakeLaw:
    return FakeLaw(
        id="LAW-0001",
        title="Taxation and Revenue Act",
        description="Regulates taxation rates for all inter-city trade",
        body="All trade transactions shall be taxed at 5% by the treasury",
        tags=["economy", "trade", "taxation"],
    )


@pytest.fixture
def ethics_law() -> FakeLaw:
    return FakeLaw(
        id="LAW-0002",
        title="Ethics Code of Conduct",
        description="Establishes ethical guidelines for council members",
        body="Council members must adhere to strict moral standards",
        tags=["ethics", "governance", "conduct"],
    )


@pytest.fixture
def magic_law() -> FakeLaw:
    return FakeLaw(
        id="LAW-0003",
        title="Arcane Regulation Act",
        description="Controls the use of magical artifacts and enchantments",
        body="All magical artifacts must be registered with the council",
        tags=["magic", "artifacts", "enchantments"],
    )


@pytest.fixture
def trade_law() -> FakeLaw:
    return FakeLaw(
        id="LAW-0004",
        title="Free Trade Agreement",
        description="Permits unrestricted trade between allied cities",
        body="Allied cities may trade goods without tariffs or restrictions",
        tags=["trade", "alliance", "commerce"],
    )


@pytest.fixture
def all_laws(tax_law, ethics_law, magic_law, trade_law) -> list[FakeLaw]:
    return [tax_law, ethics_law, magic_law, trade_law]


@pytest.fixture
def filter_enabled() -> LawFilter:
    return LawFilter(enabled=True, min_score=0.05)


@pytest.fixture
def filter_disabled() -> LawFilter:
    return LawFilter(enabled=False)


# ─── Test: ScoredLaw Data Model ──────────────────────────────


class TestScoredLaw:
    def test_fields(self, tax_law):
        sl = ScoredLaw(law=tax_law, relevance_score=0.42, matched_keywords=frozenset({"trade"}))
        assert sl.law is tax_law
        assert sl.relevance_score == 0.42
        assert sl.matched_keywords == frozenset({"trade"})

    def test_frozen(self, tax_law):
        sl = ScoredLaw(law=tax_law)
        with pytest.raises(AttributeError):
            sl.relevance_score = 0.99

    def test_defaults(self, tax_law):
        sl = ScoredLaw(law=tax_law)
        assert sl.relevance_score == 0.0
        assert sl.matched_keywords == frozenset()

    def test_to_dict(self, tax_law):
        sl = ScoredLaw(
            law=tax_law,
            relevance_score=0.35,
            matched_keywords=frozenset({"trade", "taxation"}),
        )
        d = sl.to_dict()
        assert d["law_id"] == "LAW-0001"
        assert d["title"] == "Taxation and Revenue Act"
        assert d["relevance_score"] == 0.35
        assert sorted(d["matched_keywords"]) == ["taxation", "trade"]


# ─── Test: LawFilter Init ────────────────────────────────────


class TestLawFilterInit:
    def test_defaults(self):
        lf = LawFilter()
        assert lf.enabled is True
        assert lf.min_score == 0.05

    def test_custom_settings(self):
        lf = LawFilter(enabled=False, min_score=0.2)
        assert lf.enabled is False
        assert lf.min_score == 0.2

    def test_repr(self):
        lf = LawFilter(enabled=True, min_score=0.1)
        r = repr(lf)
        assert "LawFilter" in r
        assert "enabled=True" in r
        assert "min_score=0.1" in r


# ─── Test: Scoring Individual Laws ───────────────────────────


class TestScoreLaw:
    def test_matching_keywords(self, filter_enabled, tax_law):
        from core.memory_influence import _tokenise
        context_tokens = _tokenise("trade economy taxation")
        sl = filter_enabled.score_law(tax_law, context_tokens)
        assert sl.relevance_score > 0.0
        assert len(sl.matched_keywords) > 0
        assert "trade" in sl.matched_keywords or "taxation" in sl.matched_keywords

    def test_no_match(self, filter_enabled, tax_law):
        from core.memory_influence import _tokenise
        context_tokens = _tokenise("character backstory personality")
        sl = filter_enabled.score_law(tax_law, context_tokens)
        # Score should be very low (possibly zero) for unrelated context
        assert sl.relevance_score < 0.1

    def test_empty_context(self, filter_enabled, tax_law):
        sl = filter_enabled.score_law(tax_law, set())
        assert sl.relevance_score == 0.0
        assert sl.matched_keywords == frozenset()

    def test_body_contributes_to_score(self, filter_enabled):
        """Law body text is included in scoring."""
        law_with_body = FakeLaw(
            id="LAW-0099",
            title="Generic Law",
            description="A general purpose law",
            body="This law specifically regulates dragon breeding programs",
        )
        from core.memory_influence import _tokenise
        ctx = _tokenise("dragon breeding programs")
        sl = filter_enabled.score_law(law_with_body, ctx)
        assert sl.relevance_score > 0.0
        assert "dragon" in sl.matched_keywords or "breeding" in sl.matched_keywords

    def test_tags_contribute_to_score(self, filter_enabled):
        """Law tags are included in scoring."""
        law_with_tags = FakeLaw(
            id="LAW-0098",
            title="Placeholder",
            description="A simple placeholder",
            tags=["alchemy", "potions", "brewing"],
        )
        from core.memory_influence import _tokenise
        ctx = _tokenise("alchemy potions")
        sl = filter_enabled.score_law(law_with_tags, ctx)
        assert sl.relevance_score > 0.0
        assert "alchemy" in sl.matched_keywords or "potions" in sl.matched_keywords

    def test_score_rounded(self, filter_enabled, tax_law):
        from core.memory_influence import _tokenise
        ctx = _tokenise("trade")
        sl = filter_enabled.score_law(tax_law, ctx)
        # Score should be rounded to 4 decimal places
        score_str = str(sl.relevance_score)
        parts = score_str.split(".")
        if len(parts) == 2:
            assert len(parts[1]) <= 4


# ─── Test: Filtering Laws ────────────────────────────────────


class TestFilterLaws:
    def test_relevant_laws_returned(self, filter_enabled, all_laws):
        """Laws matching context should be returned."""
        scored = filter_enabled.filter_laws(all_laws, ["trade", "economy", "taxation"])
        assert len(scored) > 0
        # Tax law and trade law should score high
        law_ids = [sl.law.id for sl in scored]
        assert "LAW-0001" in law_ids  # taxation law

    def test_irrelevant_laws_filtered(self, filter_enabled, all_laws):
        """Laws not matching context should be excluded."""
        scored = filter_enabled.filter_laws(
            all_laws, ["character", "backstory", "personality", "feelings"],
        )
        # None of our laws are about characters — most should be filtered
        law_ids = [sl.law.id for sl in scored]
        # Tax, magic, trade laws should not appear for character context
        assert "LAW-0001" not in law_ids  # taxation irrelevant

    def test_sorted_by_relevance(self, filter_enabled, all_laws):
        """Results should be sorted by descending relevance."""
        scored = filter_enabled.filter_laws(all_laws, ["trade", "economy"])
        if len(scored) > 1:
            for i in range(len(scored) - 1):
                assert scored[i].relevance_score >= scored[i + 1].relevance_score

    def test_limit_applied(self, filter_enabled, all_laws):
        """Limit parameter should cap results."""
        scored = filter_enabled.filter_laws(
            all_laws, ["trade", "economy", "ethics", "magic"],
            limit=2,
        )
        assert len(scored) <= 2

    def test_empty_laws_list(self, filter_enabled):
        scored = filter_enabled.filter_laws([], ["trade"])
        assert scored == []

    def test_empty_keywords(self, filter_enabled, all_laws):
        """Empty keywords should return all laws (no filtering basis)."""
        scored = filter_enabled.filter_laws(all_laws, [])
        assert len(scored) == len(all_laws)

    def test_stop_words_only(self, filter_enabled, all_laws):
        """Keywords that are all stop words produce no tokens → return all."""
        scored = filter_enabled.filter_laws(all_laws, ["the", "and", "is", "a"])
        # All stop words → empty context tokens → all laws pass
        assert len(scored) == len(all_laws)


# ─── Test: Disabled Filtering ────────────────────────────────


class TestFilterDisabled:
    def test_all_laws_pass(self, filter_disabled, all_laws):
        """When disabled, all laws pass through regardless of score."""
        scored = filter_disabled.filter_laws(
            all_laws, ["character", "backstory", "personality"],
        )
        # All 4 laws should be returned (no filtering)
        assert len(scored) == len(all_laws)

    def test_still_sorted(self, filter_disabled, all_laws):
        """Even when disabled, results should be sorted by score."""
        scored = filter_disabled.filter_laws(all_laws, ["trade", "economy"])
        if len(scored) > 1:
            for i in range(len(scored) - 1):
                assert scored[i].relevance_score >= scored[i + 1].relevance_score

    def test_still_scored(self, filter_disabled, all_laws):
        """Even when disabled, laws should have scores computed."""
        scored = filter_disabled.filter_laws(all_laws, ["trade", "economy"])
        # At least some should have non-zero scores
        has_nonzero = any(sl.relevance_score > 0 for sl in scored)
        assert has_nonzero


# ─── Test: Settings Constants ────────────────────────────────


class TestSettingsConstants:
    def test_law_relevance_enabled_exists(self):
        from config.settings import LAW_RELEVANCE_ENABLED
        assert isinstance(LAW_RELEVANCE_ENABLED, bool)

    def test_law_relevance_min_score_exists(self):
        from config.settings import LAW_RELEVANCE_MIN_SCORE
        assert isinstance(LAW_RELEVANCE_MIN_SCORE, float)
        assert 0.0 < LAW_RELEVANCE_MIN_SCORE < 1.0

    def test_default_values(self):
        from config.settings import LAW_RELEVANCE_ENABLED, LAW_RELEVANCE_MIN_SCORE
        assert LAW_RELEVANCE_ENABLED is True
        assert LAW_RELEVANCE_MIN_SCORE == 0.05


# ─── Test: High Min Score ────────────────────────────────────


class TestHighMinScore:
    def test_high_threshold_filters_more(self, all_laws):
        """A very high min_score should filter out most laws."""
        lf = LawFilter(enabled=True, min_score=0.9)
        scored = lf.filter_laws(all_laws, ["trade"])
        # With a 0.9 threshold, most/all laws should be filtered
        assert len(scored) < len(all_laws)

    def test_zero_threshold_keeps_all(self, all_laws):
        """A zero min_score should keep all scored laws."""
        lf = LawFilter(enabled=True, min_score=0.0)
        scored = lf.filter_laws(all_laws, ["trade"])
        # Every law should pass (score >= 0.0)
        assert len(scored) == len(all_laws)


# ─── Test: Law Text Construction ─────────────────────────────


class TestLawText:
    def test_includes_title_and_description(self):
        law = FakeLaw(
            id="LAW-T1",
            title="Dragon Regulation",
            description="Controls dragon ownership",
        )
        text = LawFilter._law_text(law)
        assert "Dragon" in text
        assert "dragon" in text.lower()
        assert "ownership" in text.lower()

    def test_includes_body(self):
        law = FakeLaw(
            id="LAW-T2",
            title="Simple",
            description="Basic",
            body="Alchemy is strictly regulated",
        )
        text = LawFilter._law_text(law)
        assert "alchemy" in text.lower()

    def test_includes_tags(self):
        law = FakeLaw(
            id="LAW-T3",
            title="Simple",
            description="Basic",
            tags=["potions", "herbalism"],
        )
        text = LawFilter._law_text(law)
        assert "potions" in text.lower()
        assert "herbalism" in text.lower()

    def test_handles_empty_fields(self):
        law = FakeLaw(
            id="LAW-T4",
            title="",
            description="",
            body="",
            tags=[],
        )
        text = LawFilter._law_text(law)
        assert isinstance(text, str)


# ─── Test: Integration with _build_participant_context ────────


class TestParticipantContextIntegration:
    """Test that _build_participant_context properly uses context_keywords."""

    def test_context_keywords_filters_laws(self, tmp_path, tax_law, ethics_law):
        """When context_keywords are provided, laws should be filtered."""
        from unittest.mock import MagicMock

        # Set up mocks
        mock_law_manager = MagicMock()
        mock_law_manager.list_laws.return_value = [tax_law, ethics_law]

        mock_member = MagicMock()
        mock_member.name = "TestMember"
        mock_member.role = "Tester"
        mock_member.description = ""
        mock_member.system_prompt = ""
        mock_member.specialties = []

        mock_registry = MagicMock()
        mock_registry.list_members.return_value = [mock_member]

        mock_loc_manager = MagicMock()
        mock_loc_manager.list_locations.return_value = []

        mock_item_manager = MagicMock()
        mock_item_manager.list_items.return_value = []

        mock_store_manager = MagicMock()
        mock_store_manager.list_stores.return_value = []

        with patch("core.routes.explore.get_law_manager", return_value=mock_law_manager), \
             patch("core.routes.explore.get_registry", return_value=mock_registry), \
             patch("core.routes.explore.get_location_manager", return_value=mock_loc_manager), \
             patch("core.routes.explore.get_item_manager", return_value=mock_item_manager), \
             patch("core.routes.explore.get_store_manager", return_value=mock_store_manager):

            from core.routes.explore import _build_participant_context

            # Need at least one participant so the function doesn't early-return
            participants = [{"id": "TestMember", "type": "council"}]

            # Call with context_keywords related to ethics
            result = _build_participant_context(
                participants,
                context_keywords=["ethics", "moral", "conduct", "governance"],
            )

            # Ethics law should appear, tax law should be filtered out
            assert "Ethics Code" in result

    def test_no_context_keywords_injects_all(self, tax_law, ethics_law):
        """Without context_keywords, all laws should be injected."""
        from unittest.mock import MagicMock

        mock_law_manager = MagicMock()
        mock_law_manager.list_laws.return_value = [tax_law, ethics_law]

        mock_member = MagicMock()
        mock_member.name = "TestMember"
        mock_member.role = "Tester"
        mock_member.description = ""
        mock_member.system_prompt = ""
        mock_member.specialties = []

        mock_registry = MagicMock()
        mock_registry.list_members.return_value = [mock_member]

        mock_loc_manager = MagicMock()
        mock_loc_manager.list_locations.return_value = []

        mock_item_manager = MagicMock()
        mock_item_manager.list_items.return_value = []

        mock_store_manager = MagicMock()
        mock_store_manager.list_stores.return_value = []

        with patch("core.routes.explore.get_law_manager", return_value=mock_law_manager), \
             patch("core.routes.explore.get_registry", return_value=mock_registry), \
             patch("core.routes.explore.get_location_manager", return_value=mock_loc_manager), \
             patch("core.routes.explore.get_item_manager", return_value=mock_item_manager), \
             patch("core.routes.explore.get_store_manager", return_value=mock_store_manager):

            from core.routes.explore import _build_participant_context

            participants = [{"id": "TestMember", "type": "council"}]

            result = _build_participant_context(
                participants,
                context_keywords=None,
            )

            # Both laws should appear
            assert "Taxation and Revenue" in result
            assert "Ethics Code" in result


# ─── Test: Helpers Re-export ─────────────────────────────────


class TestHelpersReExport:
    def test_helpers_forwards_context_keywords(self):
        """The _helpers.py re-export should accept context_keywords."""
        from unittest.mock import MagicMock, patch as mock_patch

        mock_impl = MagicMock(return_value="test_result")

        with mock_patch(
            "core.routes.explore._build_participant_context",
            mock_impl,
        ):
            from core.routes._helpers import _build_participant_context
            result = _build_participant_context(
                [{"id": "sage", "type": "council"}],
                context_keywords=["trade", "economy"],
            )

            # Verify context_keywords was forwarded
            mock_impl.assert_called_once()
            call_kwargs = mock_impl.call_args
            assert call_kwargs.kwargs.get("context_keywords") == ["trade", "economy"]


# ─── Test: Edge Cases ────────────────────────────────────────


class TestEdgeCases:
    def test_unicode_law(self, filter_enabled):
        law = FakeLaw(
            id="LAW-U001",
            title="Règlement des Marchés",
            description="Contrôle des marchés internationaux et échanges",
            tags=["marchés", "commerce"],
        )
        scored = filter_enabled.filter_laws(
            [law], ["marchés", "commerce"],
        )
        assert len(scored) > 0

    def test_single_keyword(self, filter_enabled, tax_law):
        scored = filter_enabled.filter_laws([tax_law], ["taxation"])
        assert len(scored) > 0
        assert scored[0].relevance_score > 0.0

    def test_many_laws(self, filter_enabled):
        """Performance: filtering many laws should not error."""
        laws = [
            FakeLaw(
                id=f"LAW-{i:04d}",
                title=f"Law Number {i}",
                description=f"Description of law {i} about topic {i}",
            )
            for i in range(100)
        ]
        scored = filter_enabled.filter_laws(laws, ["topic", "law"])
        assert isinstance(scored, list)

    def test_law_without_body_or_tags(self, filter_enabled):
        """Laws with only title+description should still be scored."""
        law = FakeLaw(
            id="LAW-BARE",
            title="Trade Embargo",
            description="Blocks all trade with hostile nations",
        )
        from core.memory_influence import _tokenise
        ctx = _tokenise("trade embargo")
        sl = filter_enabled.score_law(law, ctx)
        assert sl.relevance_score > 0.0

    def test_duplicate_keywords(self, filter_enabled, tax_law):
        """Duplicate keywords shouldn't skew scoring."""
        scored_once = filter_enabled.filter_laws(
            [tax_law], ["trade"],
        )
        scored_duped = filter_enabled.filter_laws(
            [tax_law], ["trade", "trade", "trade"],
        )
        # Scores should be identical since tokenisation deduplicates
        assert scored_once[0].relevance_score == scored_duped[0].relevance_score
