"""
Jericho — Shared Utilities

Common filesystem helpers used across all core modules.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


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
