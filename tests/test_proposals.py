"""
Jericho — Proposal System Tests (F-005)

Comprehensive tests for core/proposals.py.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from core.proposals import (
    Proposal,
    ProposalError,
    ProposalLifecycleError,
    ProposalManager,
    ProposalNotFoundError,
    ProposalValidationError,
    Review,
)
from config.settings import PROPOSAL_CATEGORIES, PROPOSAL_STATUSES, REVIEW_STANCES


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def proposals_dir(tmp_path: Path) -> Path:
    d = tmp_path / "proposals"
    d.mkdir()
    return d


@pytest.fixture
def mgr(proposals_dir: Path) -> ProposalManager:
    return ProposalManager(proposals_dir)


def _make_proposal(mgr: ProposalManager, **overrides) -> Proposal:
    """Helper to create a proposal with sensible defaults."""
    defaults = dict(
        title="Test Proposal",
        description="A test proposal description",
        author="Sage",
        category="ethics",
    )
    defaults.update(overrides)
    return mgr.create(**defaults)


# ─── TestReview ────────────────────────────────────────────────


class TestReview:
    """Tests for the Review data class."""

    def test_fields(self):
        r = Review(reviewer="Sage", stance="support", comment="Good", timestamp="T1")
        assert r.reviewer == "Sage"
        assert r.stance == "support"
        assert r.comment == "Good"
        assert r.timestamp == "T1"

    def test_frozen(self):
        r = Review(reviewer="Sage", stance="support", comment="Good")
        with pytest.raises(AttributeError):
            r.reviewer = "Logic"

    def test_to_dict_from_dict_roundtrip(self):
        r = Review(reviewer="Spark", stance="oppose", comment="Needs work", timestamp="T2")
        d = r.to_dict()
        restored = Review.from_dict(d)
        assert restored == r

    def test_create_factory(self):
        r = Review.create("Logic", "neutral", "Interesting")
        assert r.reviewer == "Logic"
        assert r.stance == "neutral"
        assert r.comment == "Interesting"
        assert r.timestamp != ""

    def test_create_invalid_stance(self):
        with pytest.raises(ProposalValidationError, match="Invalid stance"):
            Review.create("Sage", "maybe", "Not sure")


# ─── TestProposal ─────────────────────────────────────────────


class TestProposal:
    """Tests for the Proposal data class."""

    def test_fields(self):
        p = Proposal(
            id="P-0001", title="Test", description="Desc",
            author="Sage", category="ethics",
        )
        assert p.id == "P-0001"
        assert p.title == "Test"
        assert p.status == "draft"
        assert p.reviews == []
        assert p.metadata == {}

    def test_frozen(self):
        p = Proposal(id="P-0001", title="T", description="D", author="A", category="ethics")
        with pytest.raises(AttributeError):
            p.title = "Changed"

    def test_to_dict_from_dict_roundtrip(self):
        review = Review(reviewer="Logic", stance="support", comment="Yes", timestamp="T")
        p = Proposal(
            id="P-0042", title="Ethics Update", description="Expand constraints",
            author="Sage", category="ethics", status="open",
            created_at="C", updated_at="U", body="# Details",
            reviews=[review], metadata={"priority": "high"},
        )
        d = p.to_dict()
        restored = Proposal.from_dict(d)
        assert restored.id == p.id
        assert restored.title == p.title
        assert restored.status == p.status
        assert len(restored.reviews) == 1
        assert restored.reviews[0].reviewer == "Logic"
        assert restored.metadata == {"priority": "high"}

    def test_create_factory(self):
        p = Proposal.create(
            id="P-0001", title="New", description="Brand new",
            author="Spark", category="character", body="Full text",
        )
        assert p.status == "draft"
        assert p.created_at != ""
        assert p.updated_at != ""
        assert p.body == "Full text"
        assert p.reviews == []

    def test_create_invalid_category(self):
        with pytest.raises(ProposalValidationError, match="Invalid category"):
            Proposal.create(
                id="P-0001", title="Bad", description="Bad cat",
                author="Sage", category="invalid_cat",
            )

    def test_defaults(self):
        p = Proposal(id="P-0001", title="T", description="D", author="A", category="ethics")
        assert p.body == ""
        assert p.created_at == ""
        assert p.updated_at == ""


# ─── TestProposalManagerInit ──────────────────────────────────


class TestProposalManagerInit:
    """Tests for ProposalManager initialization."""

    def test_creates_directory(self, tmp_path: Path):
        new_dir = tmp_path / "new_proposals"
        mgr = ProposalManager(new_dir)
        assert new_dir.exists()
        assert mgr.directory == new_dir

    def test_uses_existing_directory(self, proposals_dir: Path):
        mgr = ProposalManager(proposals_dir)
        assert mgr.directory == proposals_dir

    def test_repr(self, mgr: ProposalManager):
        assert "ProposalManager" in repr(mgr)
        assert "proposals=0" in repr(mgr)


# ─── TestProposalCreation ─────────────────────────────────────


class TestProposalCreation:
    """Tests for creating proposals."""

    def test_create_basic(self, mgr: ProposalManager):
        p = mgr.create("Ethics Update", "Expand ethical constraints",
                        author="Sage", category="ethics")
        assert p.id == "P-0001"
        assert p.title == "Ethics Update"
        assert p.description == "Expand ethical constraints"
        assert p.author == "Sage"
        assert p.category == "ethics"
        assert p.status == "draft"
        assert p.created_at != ""

    def test_sequential_ids(self, mgr: ProposalManager):
        p1 = _make_proposal(mgr, title="First")
        p2 = _make_proposal(mgr, title="Second")
        p3 = _make_proposal(mgr, title="Third")
        assert p1.id == "P-0001"
        assert p2.id == "P-0002"
        assert p3.id == "P-0003"

    def test_persistence(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        filepath = mgr.directory / f"{p.id}.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["id"] == p.id
        assert data["title"] == p.title

    def test_with_body_and_metadata(self, mgr: ProposalManager):
        p = mgr.create(
            "Rich Proposal", "Full details",
            author="Forge", category="character",
            body="# Character Design\n\nFull proposal text.",
            metadata={"urgency": "high", "related": ["P-0000"]},
        )
        assert p.body == "# Character Design\n\nFull proposal text."
        assert p.metadata["urgency"] == "high"

    def test_invalid_category(self, mgr: ProposalManager):
        with pytest.raises(ProposalValidationError, match="Invalid category"):
            mgr.create("Bad", "Bad", author="Sage", category="nonexistent")

    def test_empty_title_rejected(self, mgr: ProposalManager):
        with pytest.raises(ProposalValidationError, match="Title must not be empty"):
            mgr.create("", "Desc", author="Sage", category="ethics")

    def test_empty_author_rejected(self, mgr: ProposalManager):
        with pytest.raises(ProposalValidationError, match="Author must not be empty"):
            mgr.create("Title", "Desc", author="  ", category="ethics")

    def test_whitespace_stripped(self, mgr: ProposalManager):
        p = mgr.create("  Trimmed Title  ", "  Trimmed Desc  ",
                        author="  Sage  ", category="ethics")
        assert p.title == "Trimmed Title"
        assert p.description == "Trimmed Desc"
        assert p.author == "Sage"


# ─── TestProposalRetrieval ────────────────────────────────────


class TestProposalRetrieval:
    """Tests for getting and listing proposals."""

    def test_get_by_id(self, mgr: ProposalManager):
        created = _make_proposal(mgr)
        loaded = mgr.get(created.id)
        assert loaded.id == created.id
        assert loaded.title == created.title

    def test_get_not_found(self, mgr: ProposalManager):
        with pytest.raises(ProposalNotFoundError, match="P-9999"):
            mgr.get("P-9999")

    def test_list_all(self, mgr: ProposalManager):
        _make_proposal(mgr, title="First")
        _make_proposal(mgr, title="Second")
        _make_proposal(mgr, title="Third")
        proposals = mgr.list_proposals()
        assert len(proposals) == 3
        assert proposals[0].title == "First"  # sorted by ID

    def test_filter_by_status(self, mgr: ProposalManager):
        p1 = _make_proposal(mgr, title="Draft One")
        p2 = _make_proposal(mgr, title="Draft Two")
        mgr.update_status(p1.id, "open")
        drafts = mgr.list_proposals(status="draft")
        assert len(drafts) == 1
        assert drafts[0].id == p2.id

    def test_filter_by_category(self, mgr: ProposalManager):
        _make_proposal(mgr, title="Ethics", category="ethics")
        _make_proposal(mgr, title="Char", category="character")
        _make_proposal(mgr, title="Gov", category="governance")
        ethics = mgr.list_proposals(category="ethics")
        assert len(ethics) == 1
        assert ethics[0].title == "Ethics"

    def test_filter_by_author(self, mgr: ProposalManager):
        _make_proposal(mgr, title="By Sage", author="Sage")
        _make_proposal(mgr, title="By Spark", author="Spark")
        sage_proposals = mgr.list_proposals(author="sage")  # case-insensitive
        assert len(sage_proposals) == 1
        assert sage_proposals[0].author == "Sage"

    def test_empty_list(self, mgr: ProposalManager):
        assert mgr.list_proposals() == []

    def test_combined_filters(self, mgr: ProposalManager):
        p1 = _make_proposal(mgr, title="A", author="Sage", category="ethics")
        _make_proposal(mgr, title="B", author="Sage", category="character")
        _make_proposal(mgr, title="C", author="Spark", category="ethics")
        result = mgr.list_proposals(author="Sage", category="ethics")
        assert len(result) == 1
        assert result[0].id == p1.id


# ─── TestStatusLifecycle ──────────────────────────────────────


class TestStatusLifecycle:
    """Tests for proposal lifecycle transitions."""

    def test_draft_to_open(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        updated = mgr.update_status(p.id, "open")
        assert updated.status == "open"
        assert updated.updated_at != p.updated_at

    def test_open_to_under_review(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        updated = mgr.update_status(p.id, "under_review")
        assert updated.status == "under_review"

    def test_under_review_to_decided(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        updated = mgr.update_status(p.id, "decided")
        assert updated.status == "decided"

    def test_full_lifecycle(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        final = mgr.update_status(p.id, "decided")
        assert final.status == "decided"

    def test_invalid_skip_draft_to_decided(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        with pytest.raises(ProposalLifecycleError, match="draft.*decided"):
            mgr.update_status(p.id, "decided")

    def test_invalid_decided_to_open(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        mgr.update_status(p.id, "decided")
        with pytest.raises(ProposalLifecycleError):
            mgr.update_status(p.id, "open")

    def test_withdraw_from_draft(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        updated = mgr.update_status(p.id, "withdrawn")
        assert updated.status == "withdrawn"

    def test_withdraw_from_open(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        updated = mgr.update_status(p.id, "withdrawn")
        assert updated.status == "withdrawn"

    def test_withdraw_from_under_review(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        updated = mgr.update_status(p.id, "withdrawn")
        assert updated.status == "withdrawn"

    def test_cannot_withdraw_from_decided(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        mgr.update_status(p.id, "decided")
        with pytest.raises(ProposalLifecycleError):
            mgr.update_status(p.id, "withdrawn")

    def test_cannot_unwithdraw(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "withdrawn")
        with pytest.raises(ProposalLifecycleError):
            mgr.update_status(p.id, "open")

    # ── open_to_review transitions ────────────────────────────

    def test_open_to_open_to_review(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        updated = mgr.update_status(p.id, "open_to_review")
        assert updated.status == "open_to_review"

    def test_open_to_review_to_decided(self, mgr: ProposalManager):
        """Call Vote directly from review skips under_review."""
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "open_to_review")
        updated = mgr.update_status(p.id, "decided")
        assert updated.status == "decided"

    def test_open_to_review_to_under_review(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "open_to_review")
        updated = mgr.update_status(p.id, "under_review")
        assert updated.status == "under_review"

    def test_withdraw_from_open_to_review(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "open_to_review")
        updated = mgr.update_status(p.id, "withdrawn")
        assert updated.status == "withdrawn"

    def test_full_lifecycle_through_review(self, mgr: ProposalManager):
        """draft → open → open_to_review → decided."""
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "open_to_review")
        final = mgr.update_status(p.id, "decided")
        assert final.status == "decided"

    def test_cannot_skip_open_to_open_to_review(self, mgr: ProposalManager):
        """draft → open_to_review should be invalid."""
        p = _make_proposal(mgr)
        with pytest.raises(ProposalLifecycleError):
            mgr.update_status(p.id, "open_to_review")

    def test_unknown_status(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        with pytest.raises(ProposalValidationError, match="Unknown status"):
            mgr.update_status(p.id, "approved")


# ─── TestReviews ──────────────────────────────────────────────


class TestReviews:
    """Tests for adding reviews to proposals."""

    def _open_proposal(self, mgr: ProposalManager) -> Proposal:
        p = _make_proposal(mgr)
        return mgr.update_status(p.id, "open")

    def test_add_review(self, mgr: ProposalManager):
        p = self._open_proposal(mgr)
        review = Review.create("Logic", "support", "Well reasoned")
        updated = mgr.add_review(p.id, review)
        assert len(updated.reviews) == 1
        assert updated.reviews[0].reviewer == "Logic"
        assert updated.reviews[0].stance == "support"

    def test_multiple_reviewers(self, mgr: ProposalManager):
        p = self._open_proposal(mgr)
        mgr.add_review(p.id, Review.create("Logic", "support", "Good"))
        mgr.add_review(p.id, Review.create("Spark", "oppose", "Too rigid"))
        updated = mgr.add_review(p.id, Review.create("Drift", "neutral", "Hmm"))
        assert len(updated.reviews) == 3

    def test_duplicate_reviewer_rejected(self, mgr: ProposalManager):
        p = self._open_proposal(mgr)
        mgr.add_review(p.id, Review.create("Logic", "support", "Good"))
        with pytest.raises(ProposalValidationError, match="already reviewed"):
            mgr.add_review(p.id, Review.create("Logic", "oppose", "Changed mind"))

    def test_duplicate_reviewer_case_insensitive(self, mgr: ProposalManager):
        p = self._open_proposal(mgr)
        mgr.add_review(p.id, Review.create("Logic", "support", "Good"))
        with pytest.raises(ProposalValidationError, match="already reviewed"):
            mgr.add_review(p.id, Review.create("LOGIC", "oppose", "Changed mind"))

    def test_review_on_draft_rejected(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        with pytest.raises(ProposalLifecycleError, match="draft"):
            mgr.add_review(p.id, Review.create("Logic", "support", "Early"))

    def test_review_on_decided_rejected(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        mgr.update_status(p.id, "decided")
        with pytest.raises(ProposalLifecycleError):
            mgr.add_review(p.id, Review.create("Logic", "support", "Too late"))

    def test_review_on_under_review_allowed(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        updated = mgr.add_review(p.id, Review.create("Sage", "support", "Approved"))
        assert len(updated.reviews) == 1

    def test_reviews_persisted(self, mgr: ProposalManager):
        p = self._open_proposal(mgr)
        mgr.add_review(p.id, Review.create("Logic", "support", "Good"))
        mgr.add_review(p.id, Review.create("Spark", "oppose", "Bad"))
        # Re-load from disk
        loaded = mgr.get(p.id)
        assert len(loaded.reviews) == 2
        assert loaded.reviews[0].reviewer == "Logic"
        assert loaded.reviews[1].reviewer == "Spark"


# ─── TestProposalUpdate ───────────────────────────────────────


class TestProposalUpdate:
    """Tests for updating mutable fields."""

    def test_update_title(self, mgr: ProposalManager):
        p = _make_proposal(mgr, title="Old Title")
        updated = mgr.update(p.id, title="New Title")
        assert updated.title == "New Title"
        assert updated.updated_at != p.updated_at

    def test_update_body(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        updated = mgr.update(p.id, body="# New Body\n\nUpdated content.")
        assert updated.body == "# New Body\n\nUpdated content."

    def test_update_category(self, mgr: ProposalManager):
        p = _make_proposal(mgr, category="ethics")
        updated = mgr.update(p.id, category="governance")
        assert updated.category == "governance"

    def test_update_invalid_category(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        with pytest.raises(ProposalValidationError, match="Invalid category"):
            mgr.update(p.id, category="bad_category")

    def test_immutable_field_rejected(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        with pytest.raises(ProposalValidationError, match="immutable"):
            mgr.update(p.id, id="P-9999")

    def test_immutable_author_rejected(self, mgr: ProposalManager):
        p = _make_proposal(mgr)
        with pytest.raises(ProposalValidationError, match="immutable"):
            mgr.update(p.id, author="Forge")

    def test_update_not_found(self, mgr: ProposalManager):
        with pytest.raises(ProposalNotFoundError):
            mgr.update("P-9999", title="Ghost")

    def test_update_multiple_fields(self, mgr: ProposalManager):
        p = _make_proposal(mgr, title="Old", description="Old desc")
        updated = mgr.update(p.id, title="New", description="New desc")
        assert updated.title == "New"
        assert updated.description == "New desc"


# ─── TestWithdraw ─────────────────────────────────────────────


class TestWithdraw:
    """Tests for proposal withdrawal."""

    def test_author_can_withdraw(self, mgr: ProposalManager):
        p = _make_proposal(mgr, author="Sage")
        withdrawn = mgr.withdraw(p.id, "Sage")
        assert withdrawn.status == "withdrawn"

    def test_author_case_insensitive(self, mgr: ProposalManager):
        p = _make_proposal(mgr, author="Sage")
        withdrawn = mgr.withdraw(p.id, "SAGE")
        assert withdrawn.status == "withdrawn"

    def test_non_author_cannot_withdraw(self, mgr: ProposalManager):
        p = _make_proposal(mgr, author="Sage")
        with pytest.raises(ProposalValidationError, match="Only the author"):
            mgr.withdraw(p.id, "Spark")

    def test_cannot_withdraw_decided(self, mgr: ProposalManager):
        p = _make_proposal(mgr, author="Sage")
        mgr.update_status(p.id, "open")
        mgr.update_status(p.id, "under_review")
        mgr.update_status(p.id, "decided")
        with pytest.raises(ProposalLifecycleError):
            mgr.withdraw(p.id, "Sage")


# ─── TestEdgeCases ────────────────────────────────────────────


class TestEdgeCases:
    """Edge case and robustness tests."""

    def test_unicode_content(self, mgr: ProposalManager):
        p = mgr.create(
            "日本語タイトル", "Ünïcödé description — 🎭",
            author="Echo", category="character",
            body="Proposal body with emojis: 🌟✨🎪",
        )
        loaded = mgr.get(p.id)
        assert loaded.title == "日本語タイトル"
        assert "🎭" in loaded.description
        assert "🌟" in loaded.body

    def test_very_long_body(self, mgr: ProposalManager):
        long_body = "A" * 100_000
        p = mgr.create("Long", "Very long body", author="Forge", category="general",
                        body=long_body)
        loaded = mgr.get(p.id)
        assert len(loaded.body) == 100_000

    def test_corrupt_json_skipped_in_list(self, mgr: ProposalManager):
        _make_proposal(mgr, title="Good")
        corrupt_path = mgr.directory / "P-0099.json"
        corrupt_path.write_text("not valid json{{{", encoding="utf-8")
        proposals = mgr.list_proposals()
        assert len(proposals) == 1
        assert proposals[0].title == "Good"

    def test_legacy_md_files_ignored(self, mgr: ProposalManager):
        _make_proposal(mgr, title="New Format")
        # Simulate legacy markdown proposal
        (mgr.directory / "2023-10-15_ethical_constraints.md").write_text("# Old", encoding="utf-8")
        proposals = mgr.list_proposals()
        assert len(proposals) == 1  # only JSON proposals

    def test_id_sequencing_with_gaps(self, mgr: ProposalManager):
        """If P-0003 exists but P-0002 doesn't, next ID should be P-0004."""
        _make_proposal(mgr)  # P-0001
        _make_proposal(mgr)  # P-0002
        _make_proposal(mgr)  # P-0003
        # Delete P-0002
        (mgr.directory / "P-0002.json").unlink()
        p = _make_proposal(mgr)
        assert p.id == "P-0004"  # based on max existing, not gap-filling


# ─── TestExceptions ───────────────────────────────────────────


class TestExceptions:
    """Tests for exception classes."""

    def test_proposal_error_hierarchy(self):
        assert issubclass(ProposalNotFoundError, ProposalError)
        assert issubclass(ProposalValidationError, ProposalError)
        assert issubclass(ProposalLifecycleError, ProposalError)

    def test_not_found_fields(self):
        err = ProposalNotFoundError("P-0042")
        assert err.proposal_id == "P-0042"
        assert "P-0042" in str(err)

    def test_validation_fields(self):
        err = ProposalValidationError(["error1", "error2"])
        assert err.errors == ["error1", "error2"]
        assert "error1" in str(err)
        assert "error2" in str(err)

    def test_lifecycle_fields(self):
        err = ProposalLifecycleError("P-0001", "draft", "decided")
        assert err.proposal_id == "P-0001"
        assert err.current_status == "draft"
        assert err.requested_status == "decided"
        assert "draft" in str(err)
        assert "decided" in str(err)
