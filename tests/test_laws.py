"""
Jericho — Law System Tests

Comprehensive tests for core/laws.py and core/memory.LawSharedMemory.
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from core.laws import (
    Law,
    LawError,
    LawLifecycleError,
    LawManager,
    LawNotFoundError,
    LawValidationError,
)
from core.memory import LawSharedMemory
from config.settings import LAW_STATUSES


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def laws_dir(tmp_path: Path) -> Path:
    d = tmp_path / "laws"
    d.mkdir()
    return d


@pytest.fixture
def mgr(laws_dir: Path) -> LawManager:
    return LawManager(laws_dir)


@pytest.fixture
def law_shared_dir(tmp_path: Path) -> Path:
    d = tmp_path / "law_shared"
    d.mkdir()
    return d


@pytest.fixture
def lsm(law_shared_dir: Path) -> LawSharedMemory:
    return LawSharedMemory(law_shared_dir)


def _make_law(mgr: LawManager, **overrides) -> Law:
    """Helper to create a law with sensible defaults."""
    defaults = dict(
        title="Test Law",
        description="A test law description",
        author="Council",
    )
    defaults.update(overrides)
    return mgr.create(**defaults)


# ─── TestLaw ──────────────────────────────────────────────────


class TestLaw:
    """Tests for the Law data class."""

    def test_fields(self):
        law = Law(
            id="LAW-0001", title="Trade Act", description="Regulates trade",
            author="Council",
        )
        assert law.id == "LAW-0001"
        assert law.title == "Trade Act"
        assert law.status == "draft"
        assert law.tags == []
        assert law.metadata == {}
        assert law.source_proposal_id == ""

    def test_frozen(self):
        law = Law(id="LAW-0001", title="T", description="D", author="A")
        with pytest.raises(AttributeError):
            law.title = "Changed"

    def test_to_dict_from_dict_roundtrip(self):
        law = Law(
            id="LAW-0042", title="Tax Policy", description="Establish taxes",
            author="Council", status="active",
            created_at="C", updated_at="U", body="# Full Text",
            tags=["economy", "tax"], source_proposal_id="P-0005",
            metadata={"priority": "high"},
        )
        d = law.to_dict()
        restored = Law.from_dict(d)
        assert restored.id == law.id
        assert restored.title == law.title
        assert restored.status == law.status
        assert restored.tags == ["economy", "tax"]
        assert restored.source_proposal_id == "P-0005"
        assert restored.metadata == {"priority": "high"}

    def test_create_factory(self):
        law = Law.create(
            id="LAW-0001", title="New", description="Brand new",
            author="Council", body="Full text",
        )
        assert law.status == "draft"
        assert law.created_at != ""
        assert law.updated_at != ""
        assert law.body == "Full text"
        assert law.tags == []

    def test_defaults(self):
        law = Law(id="LAW-0001", title="T", description="D", author="A")
        assert law.body == ""
        assert law.created_at == ""
        assert law.updated_at == ""
        assert law.source_proposal_id == ""


# ─── TestLawManagerInit ──────────────────────────────────────


class TestLawManagerInit:
    """Tests for LawManager initialization."""

    def test_creates_directory(self, tmp_path: Path):
        new_dir = tmp_path / "new_laws"
        mgr = LawManager(new_dir)
        assert new_dir.exists()
        assert mgr.directory == new_dir

    def test_uses_existing_directory(self, laws_dir: Path):
        mgr = LawManager(laws_dir)
        assert mgr.directory == laws_dir

    def test_repr(self, mgr: LawManager):
        assert "LawManager" in repr(mgr)
        assert "laws=0" in repr(mgr)


# ─── TestLawCreation ─────────────────────────────────────────


class TestLawCreation:
    """Tests for creating laws."""

    def test_create_basic(self, mgr: LawManager):
        law = mgr.create("Trade Act", "Regulates inter-city trade",
                          author="Council")
        assert law.id == "LAW-0001"
        assert law.title == "Trade Act"
        assert law.description == "Regulates inter-city trade"
        assert law.author == "Council"
        assert law.status == "draft"
        assert law.created_at != ""

    def test_sequential_ids(self, mgr: LawManager):
        l1 = _make_law(mgr, title="First")
        l2 = _make_law(mgr, title="Second")
        l3 = _make_law(mgr, title="Third")
        assert l1.id == "LAW-0001"
        assert l2.id == "LAW-0002"
        assert l3.id == "LAW-0003"

    def test_persistence(self, mgr: LawManager):
        law = _make_law(mgr)
        filepath = mgr.directory / f"{law.id}.json"
        assert filepath.exists()
        data = json.loads(filepath.read_text(encoding="utf-8"))
        assert data["id"] == law.id
        assert data["title"] == law.title

    def test_with_body_and_tags(self, mgr: LawManager):
        law = mgr.create(
            "Tax Policy", "Establish trade taxes",
            author="Council", body="# Tax Code\n\nFull text.",
            tags=["economy", "tax"],
        )
        assert law.body == "# Tax Code\n\nFull text."
        assert law.tags == ["economy", "tax"]

    def test_empty_title_rejected(self, mgr: LawManager):
        with pytest.raises(LawValidationError, match="Title must not be empty"):
            mgr.create("", "Desc", author="Council")

    def test_empty_description_rejected(self, mgr: LawManager):
        with pytest.raises(LawValidationError, match="Description must not be empty"):
            mgr.create("Title", "", author="Council")

    def test_empty_author_rejected(self, mgr: LawManager):
        with pytest.raises(LawValidationError, match="Author must not be empty"):
            mgr.create("Title", "Desc", author="  ")

    def test_whitespace_stripped(self, mgr: LawManager):
        law = mgr.create("  Trimmed Title  ", "  Trimmed Desc  ",
                          author="  Council  ")
        assert law.title == "Trimmed Title"
        assert law.description == "Trimmed Desc"
        assert law.author == "Council"

    def test_with_source_proposal(self, mgr: LawManager):
        law = mgr.create(
            "Proposal Law", "From a proposal",
            author="Council", source_proposal_id="P-0042",
        )
        assert law.source_proposal_id == "P-0042"


# ─── TestLawRetrieval ────────────────────────────────────────


class TestLawRetrieval:
    """Tests for getting and listing laws."""

    def test_get_by_id(self, mgr: LawManager):
        created = _make_law(mgr)
        loaded = mgr.get(created.id)
        assert loaded.id == created.id
        assert loaded.title == created.title

    def test_get_not_found(self, mgr: LawManager):
        with pytest.raises(LawNotFoundError, match="LAW-9999"):
            mgr.get("LAW-9999")

    def test_list_all(self, mgr: LawManager):
        _make_law(mgr, title="First")
        _make_law(mgr, title="Second")
        _make_law(mgr, title="Third")
        laws = mgr.list_laws()
        assert len(laws) == 3
        assert laws[0].title == "First"

    def test_filter_by_status(self, mgr: LawManager):
        l1 = _make_law(mgr, title="Draft One")
        l2 = _make_law(mgr, title="Draft Two")
        mgr.update_status(l1.id, "active")
        drafts = mgr.list_laws(status="draft")
        assert len(drafts) == 1
        assert drafts[0].id == l2.id

    def test_filter_by_author(self, mgr: LawManager):
        _make_law(mgr, title="A", author="Council")
        _make_law(mgr, title="B", author="Sage")
        council_laws = mgr.list_laws(author="council")  # case-insensitive
        assert len(council_laws) == 1
        assert council_laws[0].author == "Council"

    def test_filter_by_tag(self, mgr: LawManager):
        mgr.create("Tax Act", "Taxes", author="Council", tags=["economy", "tax"])
        mgr.create("Defense Act", "Defense", author="Council", tags=["military"])
        economy_laws = mgr.list_laws(tag="economy")
        assert len(economy_laws) == 1
        assert economy_laws[0].title == "Tax Act"

    def test_empty_list(self, mgr: LawManager):
        assert mgr.list_laws() == []


# ─── TestStatusLifecycle ──────────────────────────────────────


class TestStatusLifecycle:
    """Tests for law lifecycle transitions."""

    def test_draft_to_active(self, mgr: LawManager):
        law = _make_law(mgr)
        updated = mgr.update_status(law.id, "active")
        assert updated.status == "active"
        assert updated.updated_at != law.updated_at

    def test_active_to_archived(self, mgr: LawManager):
        law = _make_law(mgr)
        mgr.update_status(law.id, "active")
        updated = mgr.update_status(law.id, "archived")
        assert updated.status == "archived"

    def test_archived_to_active_reactivation(self, mgr: LawManager):
        """Laws can be reactivated from archived state."""
        law = _make_law(mgr)
        mgr.update_status(law.id, "active")
        mgr.update_status(law.id, "archived")
        reactivated = mgr.update_status(law.id, "active")
        assert reactivated.status == "active"

    def test_full_lifecycle(self, mgr: LawManager):
        """draft → active → archived → active (reactivation)."""
        law = _make_law(mgr)
        mgr.update_status(law.id, "active")
        mgr.update_status(law.id, "archived")
        final = mgr.update_status(law.id, "active")
        assert final.status == "active"

    def test_invalid_draft_to_archived(self, mgr: LawManager):
        law = _make_law(mgr)
        with pytest.raises(LawLifecycleError, match="draft.*archived"):
            mgr.update_status(law.id, "archived")

    def test_invalid_active_to_draft(self, mgr: LawManager):
        law = _make_law(mgr)
        mgr.update_status(law.id, "active")
        with pytest.raises(LawLifecycleError):
            mgr.update_status(law.id, "draft")

    def test_invalid_archived_to_draft(self, mgr: LawManager):
        law = _make_law(mgr)
        mgr.update_status(law.id, "active")
        mgr.update_status(law.id, "archived")
        with pytest.raises(LawLifecycleError):
            mgr.update_status(law.id, "draft")

    def test_unknown_status(self, mgr: LawManager):
        law = _make_law(mgr)
        with pytest.raises(LawValidationError, match="Unknown status"):
            mgr.update_status(law.id, "approved")


# ─── TestLawUpdate ────────────────────────────────────────────


class TestLawUpdate:
    """Tests for updating mutable fields."""

    def test_update_title(self, mgr: LawManager):
        law = _make_law(mgr, title="Old Title")
        updated = mgr.update(law.id, title="New Title")
        assert updated.title == "New Title"
        assert updated.updated_at != law.updated_at

    def test_update_body(self, mgr: LawManager):
        law = _make_law(mgr)
        updated = mgr.update(law.id, body="# Updated\n\nNew content.")
        assert updated.body == "# Updated\n\nNew content."

    def test_update_tags(self, mgr: LawManager):
        law = _make_law(mgr)
        updated = mgr.update(law.id, tags=["trade", "economy"])
        assert updated.tags == ["trade", "economy"]

    def test_immutable_id_rejected(self, mgr: LawManager):
        law = _make_law(mgr)
        with pytest.raises(LawValidationError, match="immutable"):
            mgr.update(law.id, id="LAW-9999")

    def test_immutable_author_rejected(self, mgr: LawManager):
        law = _make_law(mgr)
        with pytest.raises(LawValidationError, match="immutable"):
            mgr.update(law.id, author="Different")

    def test_update_not_found(self, mgr: LawManager):
        with pytest.raises(LawNotFoundError):
            mgr.update("LAW-9999", title="Ghost")


# ─── TestLawSharedMemory ─────────────────────────────────────


class TestLawSharedMemory:
    """Tests for the LawSharedMemory class."""

    def test_empty_initial(self, lsm: LawSharedMemory):
        assert lsm.read_active_laws() == []

    def test_sync_and_read(self, lsm: LawSharedMemory):
        laws = [
            {"id": "LAW-0001", "title": "Trade Act", "description": "Regulates trade"},
            {"id": "LAW-0002", "title": "Defense Act", "description": "National defense"},
        ]
        lsm.sync_active_laws(laws)
        result = lsm.read_active_laws()
        assert len(result) == 2
        assert result[0]["title"] == "Trade Act"
        assert result[1]["title"] == "Defense Act"

    def test_sync_overwrites(self, lsm: LawSharedMemory):
        lsm.sync_active_laws([{"title": "Old"}])
        lsm.sync_active_laws([{"title": "New"}])
        result = lsm.read_active_laws()
        assert len(result) == 1
        assert result[0]["title"] == "New"

    def test_sync_empty_clears(self, lsm: LawSharedMemory):
        lsm.sync_active_laws([{"title": "Something"}])
        lsm.sync_active_laws([])
        result = lsm.read_active_laws()
        assert result == []

    def test_get_law_context_empty(self, lsm: LawSharedMemory):
        assert lsm.get_law_context() == ""

    def test_get_law_context_with_laws(self, lsm: LawSharedMemory):
        lsm.sync_active_laws([
            {"title": "Trade Act", "description": "Regulates trade", "body": "Full text here"},
        ])
        context = lsm.get_law_context()
        assert "Active Laws" in context
        assert "Trade Act" in context
        assert "Regulates trade" in context
        assert "Full text here" in context

    def test_directory_created(self, tmp_path: Path):
        new_dir = tmp_path / "new_law_shared"
        lsm = LawSharedMemory(new_dir)
        assert new_dir.exists()


# ─── TestExceptions ───────────────────────────────────────────


class TestExceptions:
    """Tests for exception classes."""

    def test_law_error_hierarchy(self):
        assert issubclass(LawNotFoundError, LawError)
        assert issubclass(LawValidationError, LawError)
        assert issubclass(LawLifecycleError, LawError)

    def test_not_found_fields(self):
        err = LawNotFoundError("LAW-0042")
        assert err.law_id == "LAW-0042"
        assert "LAW-0042" in str(err)

    def test_validation_fields(self):
        err = LawValidationError(["error1", "error2"])
        assert err.errors == ["error1", "error2"]
        assert "error1" in str(err)

    def test_lifecycle_fields(self):
        err = LawLifecycleError("LAW-0001", "draft", "archived")
        assert err.law_id == "LAW-0001"
        assert err.current_status == "draft"
        assert err.requested_status == "archived"
        assert "draft" in str(err)
        assert "archived" in str(err)


# ─── TestEdgeCases ────────────────────────────────────────────


class TestEdgeCases:
    """Edge case and robustness tests."""

    def test_unicode_content(self, mgr: LawManager):
        law = mgr.create(
            "日本語タイトル", "Ünïcödé description — ⚖️",
            author="Council", body="Law body with emojis: 🌟✨📜",
        )
        loaded = mgr.get(law.id)
        assert loaded.title == "日本語タイトル"
        assert "⚖️" in loaded.description

    def test_corrupt_json_skipped_in_list(self, mgr: LawManager):
        _make_law(mgr, title="Good")
        corrupt_path = mgr.directory / "LAW-0099.json"
        corrupt_path.write_text("not valid json{{{", encoding="utf-8")
        laws = mgr.list_laws()
        assert len(laws) == 1
        assert laws[0].title == "Good"

    def test_id_sequencing_with_gaps(self, mgr: LawManager):
        """If LAW-0003 exists but LAW-0002 doesn't, next ID should be LAW-0004."""
        _make_law(mgr)  # LAW-0001
        _make_law(mgr)  # LAW-0002
        _make_law(mgr)  # LAW-0003
        (mgr.directory / "LAW-0002.json").unlink()
        law = _make_law(mgr)
        assert law.id == "LAW-0004"
