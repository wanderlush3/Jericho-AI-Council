"""
Jericho — Exploration Image Galleries (F-040 / F-079)

Visual location exploration with generated scene images.

Users can "look around" at a location to generate contextual scene images
using the existing ComfyUI generation pipeline. Scenes are stored as
metadata referencing existing EntityImage objects via their image IDs.

F-079 adds feature-centric movement: scenes can focus on specific areas
(features) of a location, with progressive exploration and imaginative
discovery beyond the defined map.

Navigation between connected locations (parent, children, siblings)
enables an immersive exploration experience.

Storage: scenes metadata in ``data/exploration/scenes.json``
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    EXPLORATION_DIR,
    EXPLORATION_SCENES_FILE,
)
from core.utils import atomic_write

log = logging.getLogger(__name__)


# ─── Exceptions ────────────────────────────────────────────────


class ExplorationError(Exception):
    """Base exception for exploration-system errors."""


class SceneNotFoundError(ExplorationError):
    """Raised when a scene ID is not found."""

    def __init__(self, scene_id: str) -> None:
        self.scene_id = scene_id
        super().__init__(f"Exploration scene not found: '{scene_id}'")


class ExplorationValidationError(ExplorationError):
    """Raised when exploration data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


# ─── Constants ─────────────────────────────────────────────────


SCENE_TYPES = ("overview", "feature", "transition")


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ExplorationScene:
    """Immutable snapshot of an exploration scene.

    Attributes:
        scene_id: Unique identifier (``SCN-XXXX-XXXX``).
        location_id: The location this scene belongs to.
        image_id: Reference to an existing EntityImage ID.
        scene_type: One of ``overview``, ``feature``, ``transition``.
        description: Human-readable description of this scene.
        focus_area: Which area/feature this scene depicts (F-079).
            Empty string for legacy scenes without focus tracking.
        generated_at: ISO timestamp of when the scene was generated.
        metadata: Arbitrary pass-through metadata.
    """

    scene_id: str
    location_id: str
    image_id: str
    scene_type: str = "overview"
    description: str = ""
    focus_area: str = ""
    generated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExplorationScene:
        return cls(
            scene_id=data["scene_id"],
            location_id=data["location_id"],
            image_id=data["image_id"],
            scene_type=data.get("scene_type", "overview"),
            description=data.get("description", ""),
            focus_area=data.get("focus_area", ""),
            generated_at=data.get("generated_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        location_id: str,
        image_id: str,
        scene_type: str = "overview",
        description: str = "",
        focus_area: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ExplorationScene:
        """Factory with validation and auto-generated ID."""
        errors: list[str] = []
        if not location_id.strip():
            errors.append("location_id is required.")
        if not image_id.strip():
            errors.append("image_id is required.")
        if scene_type not in SCENE_TYPES:
            errors.append(
                f"Invalid scene_type '{scene_type}' — "
                f"must be one of {SCENE_TYPES}"
            )
        if errors:
            raise ExplorationValidationError(errors)

        short_uuid = uuid.uuid4().hex[:8]
        scene_id = f"SCN-{short_uuid}"

        return cls(
            scene_id=scene_id,
            location_id=location_id.strip(),
            image_id=image_id.strip(),
            scene_type=scene_type,
            description=description.strip() if description else "",
            focus_area=focus_area.strip() if focus_area else "",
            generated_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


# ─── Exploration Manager ─────────────────────────────────────


class ExplorationManager:
    """Manages exploration scenes for locations.

    Scenes are stored as a JSON list in a single file. Each scene
    references an existing EntityImage via ``image_id``.

    Usage::

        mgr = ExplorationManager()
        scene = mgr.add_scene(
            location_id="LOC-0001",
            image_id="IMG-0042",
            scene_type="overview",
            description="The bustling marketplace of Ironhaven",
        )
        scenes = mgr.list_scenes("LOC-0001")
    """

    def __init__(
        self,
        scenes_file: Path | None = None,
        exploration_dir: Path | None = None,
    ) -> None:
        self._dir = exploration_dir or EXPLORATION_DIR
        self._scenes_file = scenes_file or EXPLORATION_SCENES_FILE
        self._dir.mkdir(parents=True, exist_ok=True)
        self._scenes: list[ExplorationScene] = self._load_all()

    # ── Create ────────────────────────────────────────────────

    def add_scene(
        self,
        *,
        location_id: str,
        image_id: str,
        scene_type: str = "overview",
        description: str = "",
        focus_area: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ExplorationScene:
        """Create and persist a new exploration scene.

        Args:
            location_id: ID of the location (e.g. ``LOC-0001``).
            image_id: ID of the existing EntityImage.
            scene_type: Type of scene (overview/feature/transition).
            description: Human-readable description.
            focus_area: Which area/feature this scene depicts (F-079).
            metadata: Arbitrary metadata.

        Returns:
            The created ExplorationScene.

        Raises:
            ExplorationValidationError: If required fields are missing.
        """
        scene = ExplorationScene.create(
            location_id=location_id,
            image_id=image_id,
            scene_type=scene_type,
            description=description,
            focus_area=focus_area,
            metadata=metadata,
        )
        self._scenes.append(scene)
        self._save_all()
        return scene

    # ── Read ──────────────────────────────────────────────────

    def get_scene(self, scene_id: str) -> ExplorationScene:
        """Get a scene by ID.

        Raises:
            SceneNotFoundError: If scene_id is not found.
        """
        for scene in self._scenes:
            if scene.scene_id == scene_id:
                return scene
        raise SceneNotFoundError(scene_id)

    def list_scenes(
        self,
        location_id: str | None = None,
        *,
        scene_type: str | None = None,
    ) -> list[ExplorationScene]:
        """List scenes, optionally filtered by location and/or type.

        Returns scenes sorted by generated_at (newest first).
        """
        result = list(self._scenes)
        if location_id is not None:
            result = [s for s in result if s.location_id == location_id]
        if scene_type is not None:
            result = [s for s in result if s.scene_type == scene_type]
        result.sort(key=lambda s: s.generated_at, reverse=True)
        return result

    def count_scenes(self, location_id: str) -> int:
        """Count scenes for a location."""
        return sum(1 for s in self._scenes if s.location_id == location_id)

    # ── Delete ────────────────────────────────────────────────

    def delete_scene(self, scene_id: str) -> None:
        """Delete a scene by ID.

        Raises:
            SceneNotFoundError: If scene_id is not found.
        """
        original_len = len(self._scenes)
        self._scenes = [s for s in self._scenes if s.scene_id != scene_id]
        if len(self._scenes) == original_len:
            raise SceneNotFoundError(scene_id)
        self._save_all()

    def delete_scenes_for_location(self, location_id: str) -> int:
        """Delete all scenes for a location.

        Returns:
            Number of scenes deleted.
        """
        original_len = len(self._scenes)
        self._scenes = [
            s for s in self._scenes if s.location_id != location_id
        ]
        deleted = original_len - len(self._scenes)
        if deleted > 0:
            self._save_all()
        return deleted

    # ── Navigation ────────────────────────────────────────────

    @staticmethod
    def get_navigation_targets(
        location_id: str,
        location_manager: Any,
    ) -> dict[str, Any]:
        """Get navigation targets for a location.

        Returns a dict with:
        - ``parent``: Parent location (or None)
        - ``children``: List of child locations
        - ``siblings``: List of sibling locations (same parent, excluding self)

        Args:
            location_id: The current location ID.
            location_manager: A LocationManager instance.
        """
        from core.locations import LocationNotFoundError

        try:
            current = location_manager.get(location_id)
        except LocationNotFoundError:
            return {"parent": None, "children": [], "siblings": []}

        # Parent
        parent = None
        if current.parent_location_id:
            try:
                parent = location_manager.get(current.parent_location_id)
            except LocationNotFoundError:
                pass

        # Children
        children = location_manager.get_children(location_id)

        # Siblings (same parent, excluding self)
        siblings = []
        if current.parent_location_id:
            all_siblings = location_manager.get_children(
                current.parent_location_id,
            )
            siblings = [s for s in all_siblings if s.id != location_id]

        return {
            "parent": parent,
            "children": children,
            "siblings": siblings,
        }

    # ── Look Around ──────────────────────────────────────────

    @staticmethod
    def build_look_around_description(location: Any) -> str:
        """Build a contextual description for scene generation.

        Creates a rich text description from the location's fields
        to use as context for the image generation prompt.

        Args:
            location: A Location instance.

        Returns:
            A descriptive string for prompt generation.
        """
        parts = [f"Location: {location.name}"]

        if location.description:
            parts.append(f"Description: {location.description}")

        if location.lore:
            parts.append(f"Lore: {location.lore}")

        if location.features:
            feature_strs = [
                f"- {f.name}: {f.description}" for f in location.features
            ]
            parts.append("Notable features:\n" + "\n".join(feature_strs))

        if location.tags:
            parts.append(f"Tags: {', '.join(location.tags)}")

        return "\n\n".join(parts)

    # ── Focused Prompt Builder (F-079) ───────────────────────

    @staticmethod
    def build_focused_prompt(
        location: Any,
        state: Any,
        previous_scenes: list[ExplorationScene] | None = None,
    ) -> str:
        """Build a context-aware prompt based on exploration state.

        Three strategies depending on exploration depth and mode:

        1. **Initial / Exterior** — Establishing shot of the location
           from outside, showing approach, entrance, atmosphere.
        2. **Guided** — Focused view of a specific feature/area
           with continuity from previously explored areas.
        3. **Imaginative** — LLM-driven discovery beyond the known
           map, constrained by the location's dynamism.

        Args:
            location: A Location instance.
            state: An ExplorationState instance.
            previous_scenes: Already-generated scenes for continuity.

        Returns:
            A descriptive string for prompt generation.
        """
        from core.exploration_state import (
            FOCUS_EXTERIOR,
            FOCUS_IMAGINATIVE,
            FOCUS_INITIAL,
            infer_location_dynamism,
        )

        parts: list[str] = []
        scenes = previous_scenes or []

        # Determine scene setting keyword
        setting = state.scene_setting or "outdoor"

        # Strategy 1: Initial / exterior overview
        if state.current_focus in (FOCUS_INITIAL, FOCUS_EXTERIOR):
            parts.append(f"Location: {location.name}")
            parts.append(f"Setting: {setting}")
            if location.description:
                parts.append(f"Description: {location.description}")
            if location.lore:
                parts.append(f"Atmosphere: {location.lore}")
            parts.append(
                "\nDirective: Generate an establishing exterior view "
                "of this location. Show the approach, the entrance, "
                "and the overall atmosphere as seen from outside."
            )
            if location.features:
                names = [f.name for f in location.features]
                parts.append(
                    f"Notable features visible: {', '.join(names)}"
                )
            return "\n".join(parts)

        # Strategy 2: Guided — focused on a specific feature
        if state.mode == "guided":
            focus_name = state.current_focus
            target_feature = None
            for f in (location.features or []):
                if f.name == focus_name:
                    target_feature = f
                    break

            parts.append(f"Location: {location.name}")

            # Infer indoor setting when exploring building-like features
            feature_type = ""
            if target_feature:
                feature_type = getattr(
                    target_feature, "feature_type", "custom",
                )
                if feature_type in ("building", "infrastructure"):
                    setting = "indoor"
                parts.append(f"Setting: {setting}")
                parts.append(
                    f"\nFocus Area: {target_feature.name}"
                )
                parts.append(
                    f"Description: {target_feature.description}"
                )
                if feature_type:
                    parts.append(f"Area Type: {feature_type}")
            else:
                parts.append(f"Setting: {setting}")
                parts.append(f"\nFocus Area: {focus_name}")

            # Continuity — what was seen before
            if state.explored_areas:
                prior = [
                    a for a in state.explored_areas
                    if a != focus_name
                ]
                if prior:
                    parts.append(
                        f"\nPreviously explored: {', '.join(prior)}"
                    )

            parts.append(
                "\nDirective: Generate a detailed view of this "
                "specific area. Focus on the textures, objects, "
                "lighting, and atmosphere unique to this space."
            )
            return "\n".join(parts)

        # Strategy 3: Imaginative exploration
        if state.mode == "imaginative":
            dynamism = infer_location_dynamism(location)
            parts.append(f"Location: {location.name}")
            parts.append(f"Setting: {setting}")
            if location.description:
                parts.append(
                    f"Known description: {location.description}"
                )

            # Summarize what's already been explored
            if state.explored_areas:
                parts.append(
                    f"\nAlready explored: {', '.join(state.explored_areas)}"
                )

            # Prevent repetition with imaginative history
            if state.imaginative_history:
                parts.append(
                    "\nPrevious discoveries (do NOT repeat these): "
                    + "; ".join(state.imaginative_history[-5:])
                )

            if dynamism == "static":
                parts.append(
                    "\nDirective: You have explored all known areas "
                    "of this location. Discover hidden details — a "
                    "forgotten alcove, a worn inscription, a subtle "
                    "atmospheric detail, or an overlooked corner. "
                    "Stay grounded in the location's established "
                    "character. Do not invent new buildings or major "
                    "structures."
                )
            elif dynamism == "dynamic":
                parts.append(
                    "\nDirective: Beyond the known areas of this "
                    "location, discover what lies further — a hidden "
                    "path, an unexpected vista, a mysterious feature, "
                    "or an undiscovered area that fits the location's "
                    "atmosphere. Be creative but consistent with the "
                    "established world."
                )
            else:  # moderate
                parts.append(
                    "\nDirective: Explore a previously overlooked "
                    "area of this location. It could be a quiet "
                    "corner, a view from a different angle, or a "
                    "subtle detail that adds depth to this place."
                )
            return "\n".join(parts)

        # Fallback: generic description
        return ExplorationManager.build_look_around_description(location)

    # ── Internal ─────────────────────────────────────────────

    def _load_all(self) -> list[ExplorationScene]:
        """Load all scenes from the JSON file."""
        if not self._scenes_file.exists():
            return []
        try:
            text = self._scenes_file.read_text(encoding="utf-8")
            data = json.loads(text)
            if not isinstance(data, list):
                return []
            return [ExplorationScene.from_dict(d) for d in data]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save_all(self) -> None:
        """Persist all scenes to the JSON file."""
        payload = json.dumps(
            [s.to_dict() for s in self._scenes],
            indent=2,
            ensure_ascii=False,
        )
        atomic_write(self._scenes_file, payload + "\n")

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"ExplorationManager(scenes={len(self._scenes)}, "
            f"file={self._scenes_file})"
        )

    def __len__(self) -> int:
        return len(self._scenes)
