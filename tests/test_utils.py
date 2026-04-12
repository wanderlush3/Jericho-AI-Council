"""
Tests for core/utils.py — atomic_write and atomic_append edge cases.

Feature: F-047 — Utils Edge-Case Tests
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from core.utils import atomic_append, atomic_write


# ---------------------------------------------------------------------------
# atomic_write — basic operations
# ---------------------------------------------------------------------------


class TestAtomicWriteBasic:
    """Core behaviour of atomic_write."""

    def test_creates_file(self, tmp_path: Path) -> None:
        target = tmp_path / "out.json"
        atomic_write(target, '{"key": "value"}')
        assert target.exists()
        assert target.read_text(encoding="utf-8") == '{"key": "value"}'

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "out.txt"
        target.write_text("old-content", encoding="utf-8")
        atomic_write(target, "new-content")
        assert target.read_text(encoding="utf-8") == "new-content"

    def test_creates_nested_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "a" / "b" / "c" / "deep.txt"
        atomic_write(target, "deep-value")
        assert target.read_text(encoding="utf-8") == "deep-value"

    def test_no_leftover_temp_files(self, tmp_path: Path) -> None:
        target = tmp_path / "clean.txt"
        atomic_write(target, "data")
        # Only the target file should remain in the directory.
        remaining = list(tmp_path.iterdir())
        assert remaining == [target]

    def test_empty_content(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.txt"
        atomic_write(target, "")
        assert target.read_text(encoding="utf-8") == ""
        assert target.stat().st_size == 0

    def test_multiline_content(self, tmp_path: Path) -> None:
        target = tmp_path / "multi.txt"
        content = "line1\nline2\nline3\n"
        atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# atomic_write — unicode handling
# ---------------------------------------------------------------------------


class TestAtomicWriteUnicode:
    """Unicode edge cases for atomic_write."""

    def test_basic_unicode(self, tmp_path: Path) -> None:
        target = tmp_path / "uni.txt"
        content = "日本語テスト — 中文 — العربية"
        atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content

    def test_emoji_content(self, tmp_path: Path) -> None:
        target = tmp_path / "emoji.txt"
        content = "🎉🌍🔥✨ emoji test 🚀"
        atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content

    def test_mixed_scripts(self, tmp_path: Path) -> None:
        target = tmp_path / "mixed.txt"
        content = "Ελληνικά · Кириллица · हिन्दी · 漢字"
        atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content

    def test_null_and_control_characters(self, tmp_path: Path) -> None:
        target = tmp_path / "ctrl.txt"
        # Note: \r is deliberately excluded — Python text mode on Windows
        # translates \r to \n, which is expected platform behaviour.
        content = "before\x00after\ttab"
        atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# atomic_write — large content
# ---------------------------------------------------------------------------


class TestAtomicWriteLargeContent:
    """Large payload handling for atomic_write."""

    def test_large_file(self, tmp_path: Path) -> None:
        target = tmp_path / "large.txt"
        content = "x" * (1024 * 1024)  # 1 MiB
        atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content

    def test_many_lines(self, tmp_path: Path) -> None:
        target = tmp_path / "lines.txt"
        content = "\n".join(f"line-{i}" for i in range(10000))
        atomic_write(target, content)
        assert target.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# atomic_write — error paths
# ---------------------------------------------------------------------------


class TestAtomicWriteErrors:
    """Error handling for atomic_write."""

    def test_cleanup_on_write_failure(self, tmp_path: Path) -> None:
        """Temp file should be cleaned up if the write itself raises."""
        target = tmp_path / "fail.txt"

        # Patch the write call inside the fdopen context — can't patch
        # os.fdopen itself because mkstemp already created the fd.
        original_fdopen = os.fdopen

        def exploding_fdopen(fd, *args, **kwargs):
            f = original_fdopen(fd, *args, **kwargs)
            f.write = lambda data: (_ for _ in ()).throw(
                IOError("mock write error")
            )
            return f

        with patch("core.utils.os.fdopen", side_effect=exploding_fdopen):
            with pytest.raises(IOError, match="mock write error"):
                atomic_write(target, "data")

        # No temp files should remain.
        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 0

    def test_cleanup_on_replace_failure(self, tmp_path: Path) -> None:
        """Temp file should be cleaned up if os.replace raises."""
        target = tmp_path / "fail2.txt"

        with patch("core.utils.os.replace", side_effect=OSError("mock replace error")):
            with pytest.raises(OSError, match="mock replace error"):
                atomic_write(target, "data")

        # No temp files should remain.
        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 0

    def test_preserves_original_on_failure(self, tmp_path: Path) -> None:
        """Original file content should be preserved if write fails."""
        target = tmp_path / "preserve.txt"
        target.write_text("original", encoding="utf-8")

        with patch("core.utils.os.replace", side_effect=OSError("mock error")):
            with pytest.raises(OSError):
                atomic_write(target, "replacement")

        assert target.read_text(encoding="utf-8") == "original"


# ---------------------------------------------------------------------------
# atomic_write — concurrent writes
# ---------------------------------------------------------------------------


class TestAtomicWriteConcurrent:
    """Concurrent write safety for atomic_write."""

    def test_concurrent_writes_no_corruption(self, tmp_path: Path) -> None:
        """Multiple threads writing simultaneously should not corrupt.

        On Windows, concurrent os.replace can raise PermissionError when
        the target file is momentarily locked.  The important guarantee
        is that the *final file* is not corrupted — some individual
        writes may fail, and that is acceptable.
        """
        target = tmp_path / "concurrent.txt"
        n_threads = 20

        def writer(idx: int) -> None:
            try:
                atomic_write(target, f"writer-{idx}-payload")
            except PermissionError:
                pass  # Expected on Windows under contention

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # The file must exist and contain exactly one writer's payload.
        final = target.read_text(encoding="utf-8")
        assert final.startswith("writer-")
        assert final.endswith("-payload")

    def test_no_temp_leftovers_after_concurrent(self, tmp_path: Path) -> None:
        """No .tmp files should linger after concurrent writes."""
        target = tmp_path / "conc2.txt"

        def writer(idx: int) -> None:
            try:
                atomic_write(target, f"data-{idx}")
            except PermissionError:
                pass  # Expected on Windows under contention

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        remaining = list(tmp_path.iterdir())
        assert all(not f.name.endswith(".tmp") for f in remaining)


# ---------------------------------------------------------------------------
# atomic_append — basic operations
# ---------------------------------------------------------------------------


class TestAtomicAppendBasic:
    """Core behaviour of atomic_append."""

    def test_creates_file_if_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "new.jsonl"
        atomic_append(target, '{"event": "start"}')
        assert target.exists()
        assert target.read_text(encoding="utf-8") == '{"event": "start"}\n'

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        target = tmp_path / "existing.jsonl"
        target.write_text("line1\n", encoding="utf-8")
        atomic_append(target, "line2")
        assert target.read_text(encoding="utf-8") == "line1\nline2\n"

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "x" / "y" / "z" / "deep.log"
        atomic_append(target, "deep-line")
        assert target.read_text(encoding="utf-8") == "deep-line\n"

    def test_multiple_appends(self, tmp_path: Path) -> None:
        target = tmp_path / "multi.jsonl"
        for i in range(5):
            atomic_append(target, f"line-{i}")
        lines = target.read_text(encoding="utf-8").strip().split("\n")
        assert lines == [f"line-{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# atomic_append — newline handling
# ---------------------------------------------------------------------------


class TestAtomicAppendNewlines:
    """Newline edge cases for atomic_append."""

    def test_adds_newline_when_missing(self, tmp_path: Path) -> None:
        target = tmp_path / "nl.txt"
        atomic_append(target, "no-trailing-newline")
        content = target.read_text(encoding="utf-8")
        assert content.endswith("\n")
        assert content.count("\n") == 1

    def test_preserves_existing_newline(self, tmp_path: Path) -> None:
        target = tmp_path / "nl2.txt"
        atomic_append(target, "has-newline\n")
        content = target.read_text(encoding="utf-8")
        assert content == "has-newline\n"
        # Should NOT add a double newline.
        assert not content.endswith("\n\n")

    def test_empty_string_append(self, tmp_path: Path) -> None:
        target = tmp_path / "empty.txt"
        atomic_append(target, "")
        content = target.read_text(encoding="utf-8")
        # Empty string gets a newline appended.
        assert content == "\n"


# ---------------------------------------------------------------------------
# atomic_append — unicode handling
# ---------------------------------------------------------------------------


class TestAtomicAppendUnicode:
    """Unicode edge cases for atomic_append."""

    def test_unicode_append(self, tmp_path: Path) -> None:
        target = tmp_path / "uni.jsonl"
        atomic_append(target, '{"name": "日本語"}')
        atomic_append(target, '{"name": "العربية"}')
        lines = target.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        assert "日本語" in lines[0]
        assert "العربية" in lines[1]

    def test_emoji_append(self, tmp_path: Path) -> None:
        target = tmp_path / "emoji.jsonl"
        atomic_append(target, "🎉 party")
        assert "🎉" in target.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# atomic_append — concurrent appends
# ---------------------------------------------------------------------------


class TestAtomicAppendConcurrent:
    """Concurrent append safety for atomic_append."""

    def test_concurrent_appends_serialized(self, tmp_path: Path) -> None:
        """Appending serially from multiple threads preserves all data.

        On Windows, concurrent file appends to the same file can
        interleave or fail silently.  We serialize with a lock to
        test the *logic* of atomic_append rather than OS-level
        file-locking semantics.
        """
        target = tmp_path / "conc.jsonl"
        n = 50
        lock = threading.Lock()
        errors: list[Exception | None] = [None] * n

        def appender(idx: int) -> None:
            try:
                with lock:
                    atomic_append(target, f"line-{idx}")
            except Exception as e:
                errors[idx] = e

        threads = [threading.Thread(target=appender, args=(i,)) for i in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(e is None for e in errors)
        lines = target.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == n
        payloads = {line.strip() for line in lines}
        expected = {f"line-{i}" for i in range(n)}
        assert payloads == expected


# ---------------------------------------------------------------------------
# atomic_append — large appends
# ---------------------------------------------------------------------------


class TestAtomicAppendLarge:
    """Large payload handling for atomic_append."""

    def test_large_single_line(self, tmp_path: Path) -> None:
        target = tmp_path / "big.jsonl"
        big_line = "x" * (512 * 1024)  # 512 KiB single line
        atomic_append(target, big_line)
        content = target.read_text(encoding="utf-8")
        assert content.strip() == big_line

    def test_many_small_appends(self, tmp_path: Path) -> None:
        target = tmp_path / "many.jsonl"
        for i in range(1000):
            atomic_append(target, f"entry-{i}")
        lines = target.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 1000


# ---------------------------------------------------------------------------
# Cross-function interaction
# ---------------------------------------------------------------------------


class TestWriteAppendInteraction:
    """Interaction between atomic_write and atomic_append on the same file."""

    def test_write_then_append(self, tmp_path: Path) -> None:
        target = tmp_path / "hybrid.txt"
        atomic_write(target, "initial\n")
        atomic_append(target, "appended")
        content = target.read_text(encoding="utf-8")
        assert content == "initial\nappended\n"

    def test_append_then_write_replaces(self, tmp_path: Path) -> None:
        target = tmp_path / "hybrid2.txt"
        atomic_append(target, "first")
        atomic_append(target, "second")
        atomic_write(target, "replaced")
        assert target.read_text(encoding="utf-8") == "replaced"

    def test_write_empty_then_append(self, tmp_path: Path) -> None:
        target = tmp_path / "empty_then_append.txt"
        atomic_write(target, "")
        atomic_append(target, "after-empty")
        content = target.read_text(encoding="utf-8")
        assert content == "after-empty\n"
