"""
Jericho — Shared Utilities

Common filesystem helpers used across all core modules.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path


def make_id_lock() -> threading.Lock:
    """Create a new threading.Lock for guarding sequential ID generation.

    Each manager that generates sequential IDs (e.g. ``CH-0001``,
    ``P-0002``) should hold **one** lock instance and acquire it around
    the ``_next_id()`` → ``_save()`` pair inside its ``create()``
    method.  This prevents two concurrent requests from scanning the
    same max-id and producing a duplicate.

    Usage inside a manager ``__init__``::

        self._id_lock = make_id_lock()

    And inside the ``create`` method::

        with self._id_lock:
            new_id = self._next_id()
            ...
            self._save(record)
    """
    return threading.Lock()


def atomic_write(filepath: Path, content: str) -> None:
    """Write *content* to *filepath* atomically via temp-file + rename."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=filepath.parent, suffix=".tmp", prefix=filepath.stem
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        # On Windows, os.replace handles cross-device atomicity.
        os.replace(tmp_path, filepath)
    except BaseException:
        # Clean up the temp file on failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def atomic_append(filepath: Path, line: str) -> None:
    """Append a single line to *filepath* (creates file if missing)."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(line if line.endswith("\n") else line + "\n")
