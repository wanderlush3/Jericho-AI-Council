"""
Thread-Safety Tests for Sequential ID Generation (F-066).

Verifies that concurrent calls to ``create()`` on each manager produce
unique, sequential IDs without collisions or overwrites.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from core.characters import CharacterManager, Trait
from core.proposals import ProposalManager
from core.locations import LocationManager
from core.stores import StoreManager
from core.story import StoryManager
from core.tasks import TaskManager
from core.laws import LawManager
from core.items import ItemManager
from core.council_session import CouncilSessionManager


# ─── Helpers ───────────────────────────────────────────────────


def _run_concurrent(target, args_list: list[tuple], workers: int = 10):
    """Run *target* concurrently with different args and collect results."""
    results: list[Any] = [None] * workers
    errors: list[Exception | None] = [None] * workers
    barrier = threading.Barrier(workers)

    def _wrapped(idx, *args):
        try:
            barrier.wait(timeout=5)
            results[idx] = target(*args)
        except Exception as exc:
            errors[idx] = exc

    threads = []
    for i in range(workers):
        args = args_list[i] if i < len(args_list) else args_list[0]
        t = threading.Thread(target=_wrapped, args=(i, *args))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10)

    for i, err in enumerate(errors):
        if err is not None:
            raise AssertionError(f"Worker {i} raised: {err}") from err

    return [r for r in results if r is not None]


# ─── CharacterManager ─────────────────────────────────────────


class TestConcurrentCharacterCreate:
    """Verify CharacterManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = CharacterManager(characters_dir=tmp_path / "chars")
        trait = Trait.create("personality", "Brave", "Always bold")

        results = _run_concurrent(
            lambda: mgr.create(
                name="Hero",
                description="A brave hero",
                author="Test",
                traits=[trait],
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.id for r in results]
        assert len(ids) == 10, f"Expected 10 results, got {len(ids)}"
        assert len(set(ids)) == 10, f"Duplicate IDs found: {ids}"

        # Verify files exist
        files = sorted(tmp_path.joinpath("chars").glob("CH-*.json"))
        assert len(files) == 10


# ─── ProposalManager ──────────────────────────────────────────


class TestConcurrentProposalCreate:
    """Verify ProposalManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = ProposalManager(proposals_dir=tmp_path / "proposals")

        results = _run_concurrent(
            lambda: mgr.create(
                title="Test Proposal",
                description="A test proposal",
                author="Tester",
                category="governance",
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"
        files = sorted(tmp_path.joinpath("proposals").glob("P-*.json"))
        assert len(files) == 10


# ─── LocationManager ──────────────────────────────────────────


class TestConcurrentLocationCreate:
    """Verify LocationManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = LocationManager(locations_dir=tmp_path / "locations")

        results = _run_concurrent(
            lambda: mgr.create(
                name="Test Location",
                description="A test location",
                author="Tester",
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"


# ─── StoreManager ─────────────────────────────────────────────


class TestConcurrentStoreCreate:
    """Verify StoreManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = StoreManager(stores_dir=tmp_path / "stores")

        results = _run_concurrent(
            lambda: mgr.create(
                name="Test Store",
                description="A test store",
                author="Tester",
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"


# ─── StoryManager ─────────────────────────────────────────────


class TestConcurrentStoryCreate:
    """Verify StoryManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = StoryManager(stories_dir=tmp_path / "stories")

        results = _run_concurrent(
            lambda: mgr.create(
                title="Test Story",
                synopsis="A test story",
                author="Tester",
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.story_id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"


# ─── TaskManager ──────────────────────────────────────────────


class TestConcurrentTaskCreate:
    """Verify TaskManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = TaskManager(tasks_dir=tmp_path / "tasks")

        results = _run_concurrent(
            lambda: mgr.create(
                name="Test Task",
                description="A test task",
                reason="Testing",
                assignees=["Worker"],
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"


# ─── LawManager ───────────────────────────────────────────────


class TestConcurrentLawCreate:
    """Verify LawManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = LawManager(laws_dir=tmp_path / "laws")

        results = _run_concurrent(
            lambda: mgr.create(
                title="Test Law",
                description="A test law",
                author="Tester",
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"


# ─── ItemManager ──────────────────────────────────────────────


class TestConcurrentItemCreate:
    """Verify ItemManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = ItemManager(items_dir=tmp_path / "items")

        results = _run_concurrent(
            lambda: mgr.create(
                name="Test Item",
                description="A test item",
                author="Tester",
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"


# ─── CouncilSessionManager ────────────────────────────────────


class TestConcurrentCouncilSessionCreate:
    """Verify CouncilSessionManager.create() is thread-safe."""

    def test_concurrent_create_unique_ids(self, tmp_path: Path):
        mgr = CouncilSessionManager(sessions_dir=tmp_path / "sessions")

        results = _run_concurrent(
            lambda: mgr.create_session(
                title="Test Session",
                topic="Testing thread safety",
            ),
            args_list=[()],
            workers=10,
        )

        ids = [r.session_id for r in results]
        assert len(set(ids)) == 10, f"Duplicate IDs: {ids}"
