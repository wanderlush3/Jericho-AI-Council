"""
Jericho — Exploration State Engine (F-079)

Tracks where the user is within a location and what they've already
seen during exploration.  Supports feature-centric movement, guided
exploration of known features, and imaginative discovery beyond the
known map.

Storage: one JSON file per location state in ``data/exploration/states/``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    DYNAMIC_LOCATION_TAGS,
    EXPLORATION_STATES_DIR,
    IMAGINATIVE_MODE_ENABLED,
    STATIC_LOCATION_TAGS,
)
from core.utils import atomic_write

log = logging.getLogger(__name__)


# ─── Exceptions ────────────────────────────────────────────────


class ExplorationStateError(Exception):
    """Base exception for exploration state errors."""


class InvalidMoveError(ExplorationStateError):
    """Raised when a movement target is invalid."""

    def __init__(self, target: str, reason: str = "") -> None:
        self.target = target
        msg = f"Invalid move to '{target}'"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


# ─── Constants ─────────────────────────────────────────────────


EXPLORATION_MODES = ("guided", "imaginative")

# Focus constants
FOCUS_INITIAL = "initial"
FOCUS_EXTERIOR = "exterior"
FOCUS_IMAGINATIVE = "imaginative"


# ─── Data Models ───────────────────────────────────────────────


@dataclass
class ExplorationState:
    """Tracks exploration progress within a single location.

    Attributes:
        location_id: The location being explored.
        current_focus: What the user is currently looking at.
            ``"initial"`` before first look-around,
            ``"exterior"`` for the approach/overview,
            a feature name for focused exploration,
            or ``"imaginative"`` for beyond-map discovery.
        explored_areas: List of features/areas already visited.
        exploration_depth: How many moves deep (0 = not started).
        mode: ``"guided"`` while exploring known features,
            ``"imaginative"`` once all features have been explored.
        imaginative_history: LLM-generated area descriptions
            (prevents repeating the same discoveries).
        scene_setting: ``"outdoor"`` or ``"indoor"`` — inferred from
            the location's ComfyUI prompt output or feature context.
        metadata: Arbitrary pass-through metadata.
    """

    location_id: str
    current_focus: str = FOCUS_INITIAL
    explored_areas: list[str] = field(default_factory=list)
    exploration_depth: int = 0
    mode: str = "guided"
    imaginative_history: list[str] = field(default_factory=list)
    scene_setting: str = "outdoor"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExplorationState:
        return cls(
            location_id=data["location_id"],
            current_focus=data.get("current_focus", FOCUS_INITIAL),
            explored_areas=data.get("explored_areas", []),
            exploration_depth=data.get("exploration_depth", 0),
            mode=data.get("mode", "guided"),
            imaginative_history=data.get("imaginative_history", []),
            scene_setting=data.get("scene_setting", "outdoor"),
            metadata=data.get("metadata", {}),
        )

    # ── State transitions ────────────────────────────────────

    def move_to(self, target: str) -> None:
        """Move focus to a new area.

        - ``"exterior"`` — return to the exterior/overview
        - A feature name — focus on that specific feature
        - ``"explore_further"`` — enter imaginative mode (if enabled)

        Args:
            target: The target to move to.

        Raises:
            InvalidMoveError: If the target is not valid.
        """
        if target == "explore_further":
            if not IMAGINATIVE_MODE_ENABLED:
                raise InvalidMoveError(
                    target, "Imaginative exploration is disabled"
                )
            self.mode = "imaginative"
            self.current_focus = FOCUS_IMAGINATIVE
            self.exploration_depth += 1
            return

        if target == FOCUS_EXTERIOR:
            self.current_focus = FOCUS_EXTERIOR
            if FOCUS_EXTERIOR not in self.explored_areas:
                self.explored_areas.append(FOCUS_EXTERIOR)
            self.exploration_depth += 1
            return

        # Feature-specific move
        self.current_focus = target
        if target not in self.explored_areas:
            self.explored_areas.append(target)
        self.exploration_depth += 1

    def add_imaginative_discovery(self, description: str) -> None:
        """Record an LLM-generated discovery to prevent repetition."""
        if description and description not in self.imaginative_history:
            self.imaginative_history.append(description)

    def get_exploration_progress(
        self, total_features: int,
    ) -> dict[str, Any]:
        """Calculate exploration progress.

        Args:
            total_features: Total number of known features in the location.

        Returns:
            Dict with ``explored``, ``total``, ``percentage``,
            and ``all_explored`` keys.
        """
        # Explored = feature-areas that have been visited
        # (exclude "exterior" and "imaginative" from the feature count)
        feature_explored = [
            a for a in self.explored_areas
            if a not in (FOCUS_EXTERIOR, FOCUS_INITIAL, FOCUS_IMAGINATIVE)
        ]
        explored = len(feature_explored)
        total = max(total_features, 1)
        pct = min(100, int((explored / total) * 100))
        return {
            "explored": explored,
            "total": total_features,
            "percentage": pct,
            "all_explored": explored >= total_features and total_features > 0,
        }

    def get_available_moves(
        self, feature_names: list[str],
    ) -> list[dict[str, Any]]:
        """Compute available movement targets.

        Args:
            feature_names: Names of the location's defined features.

        Returns:
            List of move target dicts with ``target``, ``label``,
            ``explored`` (bool), and ``type`` keys.
        """
        moves: list[dict[str, Any]] = []

        # Exterior / overview (always available)
        moves.append({
            "target": FOCUS_EXTERIOR,
            "label": "Exterior Overview",
            "explored": FOCUS_EXTERIOR in self.explored_areas,
            "type": "exterior",
        })

        # Known features
        for name in feature_names:
            moves.append({
                "target": name,
                "label": name,
                "explored": name in self.explored_areas,
                "type": "feature",
            })

        # Imaginative — only available when all features explored
        progress = self.get_exploration_progress(len(feature_names))
        if progress["all_explored"] and IMAGINATIVE_MODE_ENABLED:
            moves.append({
                "target": "explore_further",
                "label": "Explore Further…",
                "explored": False,
                "type": "imaginative",
            })

        return moves

    def reset(self) -> None:
        """Reset the exploration state to initial."""
        self.current_focus = FOCUS_INITIAL
        self.explored_areas = []
        self.exploration_depth = 0
        self.mode = "guided"
        self.imaginative_history = []


# ─── Location Dynamism ────────────────────────────────────────


def infer_location_dynamism(
    location: Any,
) -> str:
    """Infer whether a location is static or dynamic.

    Uses tags and feature count as heuristic signals.

    Returns:
        ``"static"``, ``"dynamic"``, or ``"moderate"``.
    """
    tags_lower = {t.lower() for t in (location.tags or [])}
    name_lower = location.name.lower()

    # Check tags
    has_static = bool(tags_lower & STATIC_LOCATION_TAGS)
    has_dynamic = bool(tags_lower & DYNAMIC_LOCATION_TAGS)

    # Also check name words
    name_words = set(name_lower.split())
    has_static = has_static or bool(name_words & STATIC_LOCATION_TAGS)
    has_dynamic = has_dynamic or bool(name_words & DYNAMIC_LOCATION_TAGS)

    if has_static and not has_dynamic:
        return "static"
    if has_dynamic and not has_static:
        return "dynamic"

    # Feature-count heuristic
    feature_count = len(location.features) if hasattr(location, "features") else 0
    if feature_count <= 3:
        return "static"
    if feature_count > 5:
        return "dynamic"

    return "moderate"


# ─── Exploration State Manager ────────────────────────────────


class ExplorationStateManager:
    """Filesystem-backed manager for per-location exploration states.

    Each location gets at most one state file (``{location_id}.json``).

    Usage::

        mgr = ExplorationStateManager()
        state = mgr.get_or_create("LOC-0001")
        state.move_to("Great Hall")
        mgr.save(state)
    """

    def __init__(
        self,
        states_dir: Path | None = None,
    ) -> None:
        self._dir = states_dir or EXPLORATION_STATES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Read ──────────────────────────────────────────────────

    def get(self, location_id: str) -> ExplorationState | None:
        """Load state for a location, or None if not started."""
        path = self._filepath(location_id)
        if not path.exists():
            return None
        try:
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            return ExplorationState.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            log.debug("Corrupt exploration state for %s", location_id)
            return None

    def get_or_create(self, location_id: str) -> ExplorationState:
        """Load existing state or create a fresh one."""
        state = self.get(location_id)
        if state is not None:
            return state
        state = ExplorationState(location_id=location_id)
        self.save(state)
        return state

    # ── Write ─────────────────────────────────────────────────

    def save(self, state: ExplorationState) -> None:
        """Persist exploration state to disk."""
        payload = json.dumps(
            state.to_dict(), indent=2, ensure_ascii=False,
        )
        atomic_write(self._filepath(state.location_id), payload + "\n")

    # ── Delete / Reset ────────────────────────────────────────

    def reset(self, location_id: str) -> ExplorationState:
        """Reset exploration state to initial for a location."""
        state = self.get_or_create(location_id)
        state.reset()
        self.save(state)
        return state

    def delete(self, location_id: str) -> bool:
        """Delete exploration state for a location.

        Returns True if a state existed and was deleted.
        """
        path = self._filepath(location_id)
        if path.exists():
            path.unlink()
            return True
        return False

    # ── Internal ──────────────────────────────────────────────

    def _filepath(self, location_id: str) -> Path:
        return self._dir / f"{location_id}.json"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("LOC-*.json")))
        return (
            f"ExplorationStateManager(states={count}, dir={self._dir})"
        )
