"""
Jericho — Story Illustration System (F-041)

LLM-narrated story segments with inline generated illustrations.

Stories are hierarchical:  Story → Chapters → Scenes.
Each scene has LLM-generated narrative text and an optional inline
illustration (referenced by ``image_id`` from ImageManager).

Storage: one JSON file per story in ``data/stories/`` (``ST-XXXX.json``).

Usage::

    mgr = StoryManager()
    story = mgr.create("The Fall of Ironhaven", "A tale of betrayal...", author="User")
    chapter = mgr.add_chapter(story.story_id, title="Chapter I: The Arrival")
    scene = mgr.add_scene(story.story_id, chapter.chapter_id,
                          location_id="LOC-0001", characters=["CH-0001"])
    # After LLM narration:
    mgr.update_scene(story.story_id, chapter.chapter_id, scene.scene_id,
                     narrative_text="The gates of Ironhaven loomed...")
    # After image generation:
    mgr.attach_illustration(story.story_id, chapter.chapter_id,
                            scene.scene_id, image_id="IMG-0042")
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    STORIES_DIR,
    STORY_MAX_CHAPTERS,
    STORY_MAX_SCENES_PER_CHAPTER,
    STORY_STATUSES,
)
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class StoryError(Exception):
    """Base exception for story system errors."""


class StoryNotFoundError(StoryError):
    """Raised when a story ID is not found."""

    def __init__(self, story_id: str) -> None:
        self.story_id = story_id
        super().__init__(f"Story not found: '{story_id}'")


class ChapterNotFoundError(StoryError):
    """Raised when a chapter ID is not found within a story."""

    def __init__(self, chapter_id: str, story_id: str = "") -> None:
        self.chapter_id = chapter_id
        self.story_id = story_id
        msg = f"Chapter not found: '{chapter_id}'"
        if story_id:
            msg += f" in story '{story_id}'"
        super().__init__(msg)


class SceneNotFoundError(StoryError):
    """Raised when a scene ID is not found within a chapter."""

    def __init__(self, scene_id: str, chapter_id: str = "") -> None:
        self.scene_id = scene_id
        self.chapter_id = chapter_id
        msg = f"Scene not found: '{scene_id}'"
        if chapter_id:
            msg += f" in chapter '{chapter_id}'"
        super().__init__(msg)


class StoryValidationError(StoryError):
    """Raised when story data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


class StoryLifecycleError(StoryError):
    """Raised when a status transition is invalid."""

    def __init__(
        self, story_id: str, current_status: str, requested_status: str,
    ) -> None:
        self.story_id = story_id
        self.current_status = current_status
        self.requested_status = requested_status
        super().__init__(
            f"Cannot transition story '{story_id}' from "
            f"'{current_status}' to '{requested_status}'"
        )


# ─── Constants ─────────────────────────────────────────────────


_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"active", "archived"},
    "active": {"completed", "archived", "draft"},
    "completed": {"archived", "active"},
    "archived": {"draft"},
}


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class StoryScene:
    """A single scene within a chapter.

    Attributes:
        scene_id: Unique identifier (``SC-XXXX``).
        chapter_id: Parent chapter ID.
        scene_number: Ordinal position within the chapter.
        narrative_text: LLM-generated prose narrative.
        image_id: Optional reference to an EntityImage ID.
        prompt_used: The prompt used for illustration generation.
        characters: List of character entity IDs involved.
        location_id: Location where the scene takes place.
        mood: Mood descriptor (e.g. "tense", "joyful", "melancholic").
        created_at: ISO 8601 timestamp.
        metadata: Arbitrary pass-through metadata.
    """

    scene_id: str
    chapter_id: str
    scene_number: int = 1
    narrative_text: str = ""
    image_id: str = ""
    prompt_used: str = ""
    characters: list[str] = field(default_factory=list)
    location_id: str = ""
    mood: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryScene:
        return cls(
            scene_id=data["scene_id"],
            chapter_id=data["chapter_id"],
            scene_number=data.get("scene_number", 1),
            narrative_text=data.get("narrative_text", ""),
            image_id=data.get("image_id", ""),
            prompt_used=data.get("prompt_used", ""),
            characters=data.get("characters", []),
            location_id=data.get("location_id", ""),
            mood=data.get("mood", ""),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        scene_id: str,
        chapter_id: str,
        scene_number: int = 1,
        narrative_text: str = "",
        characters: list[str] | None = None,
        location_id: str = "",
        mood: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StoryScene:
        """Factory with validation and auto-timestamp."""
        errors: list[str] = []
        if not scene_id.strip():
            errors.append("scene_id is required.")
        if not chapter_id.strip():
            errors.append("chapter_id is required.")
        if scene_number < 1:
            errors.append("scene_number must be >= 1.")
        if errors:
            raise StoryValidationError(errors)

        return cls(
            scene_id=scene_id.strip(),
            chapter_id=chapter_id.strip(),
            scene_number=scene_number,
            narrative_text=narrative_text,
            characters=characters or [],
            location_id=location_id.strip() if location_id else "",
            mood=mood.strip() if mood else "",
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class StoryChapter:
    """A chapter within a story, containing ordered scenes.

    Attributes:
        chapter_id: Unique identifier (``CH-XXXX`` scoped to the story).
        story_id: Parent story ID.
        chapter_number: Ordinal position within the story.
        title: Chapter title.
        synopsis: Brief chapter synopsis.
        scenes: Ordered list of StoryScene.
        created_at: ISO 8601 timestamp.
        metadata: Arbitrary pass-through metadata.
    """

    chapter_id: str
    story_id: str
    chapter_number: int = 1
    title: str = ""
    synopsis: str = ""
    scenes: list[StoryScene] = field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["scenes"] = [s.to_dict() for s in self.scenes]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryChapter:
        scenes_data = data.get("scenes", [])
        scenes = [StoryScene.from_dict(s) for s in scenes_data]
        return cls(
            chapter_id=data["chapter_id"],
            story_id=data["story_id"],
            chapter_number=data.get("chapter_number", 1),
            title=data.get("title", ""),
            synopsis=data.get("synopsis", ""),
            scenes=scenes,
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        chapter_id: str,
        story_id: str,
        chapter_number: int = 1,
        title: str = "",
        synopsis: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StoryChapter:
        """Factory with validation and auto-timestamp."""
        errors: list[str] = []
        if not chapter_id.strip():
            errors.append("chapter_id is required.")
        if not story_id.strip():
            errors.append("story_id is required.")
        if chapter_number < 1:
            errors.append("chapter_number must be >= 1.")
        if errors:
            raise StoryValidationError(errors)

        return cls(
            chapter_id=chapter_id.strip(),
            story_id=story_id.strip(),
            chapter_number=chapter_number,
            title=title.strip() if title else "",
            synopsis=synopsis.strip() if synopsis else "",
            scenes=[],
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class StoryRecord:
    """A complete story with chapters and scenes.

    Attributes:
        story_id: Unique identifier (``ST-XXXX``).
        title: Story title.
        synopsis: Brief story synopsis.
        author: Creator of the story.
        status: Lifecycle status (draft/active/completed/archived).
        chapters: Ordered list of StoryChapter.
        entity_refs: Entity IDs referenced (characters, locations, items).
        style_preset_key: Default style preset for illustration generation.
        template_id: Default ComfyUI workflow template ID.
        created_at: ISO 8601 timestamp.
        updated_at: ISO 8601 timestamp of last modification.
        metadata: Arbitrary pass-through metadata.
    """

    story_id: str
    title: str
    synopsis: str = ""
    author: str = ""
    status: str = "draft"
    chapters: list[StoryChapter] = field(default_factory=list)
    entity_refs: dict[str, list[str]] = field(default_factory=dict)
    style_preset_key: str = ""
    template_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["chapters"] = [c.to_dict() for c in self.chapters]
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoryRecord:
        chapters_data = data.get("chapters", [])
        chapters = [StoryChapter.from_dict(c) for c in chapters_data]
        return cls(
            story_id=data["story_id"],
            title=data["title"],
            synopsis=data.get("synopsis", ""),
            author=data.get("author", ""),
            status=data.get("status", "draft"),
            chapters=chapters,
            entity_refs=data.get("entity_refs", {}),
            style_preset_key=data.get("style_preset_key", ""),
            template_id=data.get("template_id", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        story_id: str,
        title: str,
        synopsis: str = "",
        author: str = "",
        style_preset_key: str = "",
        template_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StoryRecord:
        """Factory with validation and auto-timestamp."""
        errors: list[str] = []
        if not story_id.strip():
            errors.append("story_id is required.")
        if not title.strip():
            errors.append("Story title is required.")
        if errors:
            raise StoryValidationError(errors)

        now = datetime.now(timezone.utc).isoformat()
        return cls(
            story_id=story_id.strip(),
            title=title.strip(),
            synopsis=synopsis.strip() if synopsis else "",
            author=author.strip() if author else "",
            status="draft",
            chapters=[],
            entity_refs={},
            style_preset_key=style_preset_key.strip() if style_preset_key else "",
            template_id=template_id.strip() if template_id else "",
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


# ─── Story Manager ───────────────────────────────────────────


class StoryManager:
    """Filesystem-backed story management.

    Each story is stored as a single JSON file ``ST-XXXX.json`` containing
    the full hierarchy of chapters and scenes.

    Usage::

        mgr = StoryManager()
        story = mgr.create("My Story", "An epic tale", author="User")
        ch = mgr.add_chapter(story.story_id, title="Chapter 1")
        sc = mgr.add_scene(story.story_id, ch.chapter_id)
    """

    _ID_PREFIX = "ST"

    def __init__(self, stories_dir: Path | None = None) -> None:
        self._dir = stories_dir or STORIES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Properties ───────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    # ── Create Story ─────────────────────────────────────────

    def create(
        self,
        title: str,
        synopsis: str = "",
        *,
        author: str = "",
        style_preset_key: str = "",
        template_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StoryRecord:
        """Create a new story.

        Args:
            title: Story title.
            synopsis: Brief synopsis.
            author: Creator name.
            style_preset_key: Default style preset key.
            template_id: Default ComfyUI template ID.
            metadata: Arbitrary metadata.

        Returns:
            The created StoryRecord.

        Raises:
            StoryValidationError: If title is empty.
        """
        story_id = self._next_id()
        story = StoryRecord.create(
            story_id=story_id,
            title=title,
            synopsis=synopsis,
            author=author,
            style_preset_key=style_preset_key,
            template_id=template_id,
            metadata=metadata,
        )
        self._save(story)
        return story

    # ── Get / List Stories ───────────────────────────────────

    def get(self, story_id: str) -> StoryRecord:
        """Get a story by ID.

        Raises:
            StoryNotFoundError: If the story ID does not exist.
        """
        path = self._path(story_id)
        if not path.exists():
            raise StoryNotFoundError(story_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return StoryRecord.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            raise StoryNotFoundError(story_id) from exc

    def list_stories(
        self,
        *,
        status: str | None = None,
        author: str | None = None,
    ) -> list[StoryRecord]:
        """List all stories, optionally filtered.

        Returns stories sorted by updated_at (newest first).
        """
        stories: list[StoryRecord] = []
        for path in sorted(self._dir.glob(f"{self._ID_PREFIX}-*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                story = StoryRecord.from_dict(data)
                if status and story.status != status:
                    continue
                if author and story.author.lower() != author.lower():
                    continue
                stories.append(story)
            except (json.JSONDecodeError, KeyError):
                continue
        stories.sort(key=lambda s: s.updated_at or s.created_at, reverse=True)
        return stories

    def has_story(self, story_id: str) -> bool:
        """Check if a story exists."""
        return self._path(story_id).exists()

    # ── Update Story ─────────────────────────────────────────

    def update(
        self,
        story_id: str,
        *,
        title: str | None = None,
        synopsis: str | None = None,
        style_preset_key: str | None = None,
        template_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> StoryRecord:
        """Update mutable story fields.

        Raises:
            StoryNotFoundError: If the story ID does not exist.
            StoryValidationError: If new title is empty.
        """
        story = self.get(story_id)
        d = story.to_dict()

        if title is not None:
            if not title.strip():
                raise StoryValidationError("Story title cannot be empty.")
            d["title"] = title.strip()
        if synopsis is not None:
            d["synopsis"] = synopsis.strip()
        if style_preset_key is not None:
            d["style_preset_key"] = style_preset_key.strip()
        if template_id is not None:
            d["template_id"] = template_id.strip()
        if metadata is not None:
            d["metadata"] = metadata

        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = StoryRecord.from_dict(d)
        self._save(updated)
        return updated

    def update_status(self, story_id: str, new_status: str) -> StoryRecord:
        """Transition a story's lifecycle status.

        Valid transitions::

            draft → active, archived
            active → completed, archived, draft
            completed → archived, active
            archived → draft

        Raises:
            StoryNotFoundError: If the story does not exist.
            StoryLifecycleError: If the transition is invalid.
            StoryValidationError: If the status is unknown.
        """
        if new_status not in STORY_STATUSES:
            raise StoryValidationError(
                f"Unknown status '{new_status}' — "
                f"must be one of {STORY_STATUSES}"
            )

        story = self.get(story_id)
        allowed = _VALID_TRANSITIONS.get(story.status, set())
        if new_status not in allowed:
            raise StoryLifecycleError(story_id, story.status, new_status)

        d = story.to_dict()
        d["status"] = new_status
        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = StoryRecord.from_dict(d)
        self._save(updated)
        return updated

    def delete(self, story_id: str) -> None:
        """Delete a story.

        Raises:
            StoryNotFoundError: If the story does not exist.
        """
        path = self._path(story_id)
        if not path.exists():
            raise StoryNotFoundError(story_id)
        path.unlink()

    # ── Chapter Management ───────────────────────────────────

    def add_chapter(
        self,
        story_id: str,
        *,
        title: str = "",
        synopsis: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StoryChapter:
        """Add a new chapter to a story.

        Raises:
            StoryNotFoundError: If the story does not exist.
            StoryValidationError: If chapter limit is exceeded.
        """
        story = self.get(story_id)

        if len(story.chapters) >= STORY_MAX_CHAPTERS:
            raise StoryValidationError(
                f"Story has reached the maximum of {STORY_MAX_CHAPTERS} chapters."
            )

        # Auto-sequential chapter ID
        chapter_number = len(story.chapters) + 1
        chapter_id = f"CHP-{chapter_number:04d}"

        chapter = StoryChapter.create(
            chapter_id=chapter_id,
            story_id=story_id,
            chapter_number=chapter_number,
            title=title,
            synopsis=synopsis,
            metadata=metadata,
        )

        d = story.to_dict()
        d["chapters"].append(chapter.to_dict())
        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = StoryRecord.from_dict(d)
        self._save(updated)
        return chapter

    def update_chapter(
        self,
        story_id: str,
        chapter_id: str,
        *,
        title: str | None = None,
        synopsis: str | None = None,
    ) -> StoryChapter:
        """Update a chapter's title or synopsis.

        Raises:
            StoryNotFoundError: If the story does not exist.
            ChapterNotFoundError: If the chapter is not found.
        """
        story = self.get(story_id)
        d = story.to_dict()

        for ch_data in d["chapters"]:
            if ch_data["chapter_id"] == chapter_id:
                if title is not None:
                    ch_data["title"] = title.strip()
                if synopsis is not None:
                    ch_data["synopsis"] = synopsis.strip()
                d["updated_at"] = datetime.now(timezone.utc).isoformat()
                updated = StoryRecord.from_dict(d)
                self._save(updated)
                return StoryChapter.from_dict(ch_data)

        raise ChapterNotFoundError(chapter_id, story_id)

    def delete_chapter(self, story_id: str, chapter_id: str) -> None:
        """Delete a chapter and all its scenes.

        Raises:
            StoryNotFoundError: If the story does not exist.
            ChapterNotFoundError: If the chapter is not found.
        """
        story = self.get(story_id)
        d = story.to_dict()

        original_len = len(d["chapters"])
        d["chapters"] = [
            c for c in d["chapters"] if c["chapter_id"] != chapter_id
        ]

        if len(d["chapters"]) == original_len:
            raise ChapterNotFoundError(chapter_id, story_id)

        # Renumber chapters
        for i, ch_data in enumerate(d["chapters"]):
            ch_data["chapter_number"] = i + 1

        d["updated_at"] = datetime.now(timezone.utc).isoformat()
        updated = StoryRecord.from_dict(d)
        self._save(updated)

    # ── Scene Management ─────────────────────────────────────

    def add_scene(
        self,
        story_id: str,
        chapter_id: str,
        *,
        narrative_text: str = "",
        characters: list[str] | None = None,
        location_id: str = "",
        mood: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StoryScene:
        """Add a scene to a chapter.

        Raises:
            StoryNotFoundError: If the story does not exist.
            ChapterNotFoundError: If the chapter is not found.
            StoryValidationError: If scene limit is exceeded.
        """
        story = self.get(story_id)
        d = story.to_dict()

        for ch_data in d["chapters"]:
            if ch_data["chapter_id"] == chapter_id:
                scenes = ch_data.get("scenes", [])
                if len(scenes) >= STORY_MAX_SCENES_PER_CHAPTER:
                    raise StoryValidationError(
                        f"Chapter has reached the maximum of "
                        f"{STORY_MAX_SCENES_PER_CHAPTER} scenes."
                    )

                scene_number = len(scenes) + 1
                scene_id = f"SCE-{scene_number:04d}"

                scene = StoryScene.create(
                    scene_id=scene_id,
                    chapter_id=chapter_id,
                    scene_number=scene_number,
                    narrative_text=narrative_text,
                    characters=characters,
                    location_id=location_id,
                    mood=mood,
                    metadata=metadata,
                )

                scenes.append(scene.to_dict())
                ch_data["scenes"] = scenes

                # Update entity_refs
                self._update_entity_refs(d, characters, location_id)

                d["updated_at"] = datetime.now(timezone.utc).isoformat()
                updated = StoryRecord.from_dict(d)
                self._save(updated)
                return scene

        raise ChapterNotFoundError(chapter_id, story_id)

    def update_scene(
        self,
        story_id: str,
        chapter_id: str,
        scene_id: str,
        *,
        narrative_text: str | None = None,
        characters: list[str] | None = None,
        location_id: str | None = None,
        mood: str | None = None,
        image_id: str | None = None,
        prompt_used: str | None = None,
    ) -> StoryScene:
        """Update a scene's fields.

        Raises:
            StoryNotFoundError: If the story does not exist.
            ChapterNotFoundError: If the chapter is not found.
            SceneNotFoundError: If the scene is not found.
        """
        story = self.get(story_id)
        d = story.to_dict()

        for ch_data in d["chapters"]:
            if ch_data["chapter_id"] == chapter_id:
                for sc_data in ch_data.get("scenes", []):
                    if sc_data["scene_id"] == scene_id:
                        if narrative_text is not None:
                            sc_data["narrative_text"] = narrative_text
                        if characters is not None:
                            sc_data["characters"] = characters
                        if location_id is not None:
                            sc_data["location_id"] = location_id.strip()
                        if mood is not None:
                            sc_data["mood"] = mood.strip()
                        if image_id is not None:
                            sc_data["image_id"] = image_id.strip()
                        if prompt_used is not None:
                            sc_data["prompt_used"] = prompt_used

                        d["updated_at"] = datetime.now(timezone.utc).isoformat()
                        updated = StoryRecord.from_dict(d)
                        self._save(updated)
                        return StoryScene.from_dict(sc_data)

                raise SceneNotFoundError(scene_id, chapter_id)

        raise ChapterNotFoundError(chapter_id, story_id)

    def attach_illustration(
        self,
        story_id: str,
        chapter_id: str,
        scene_id: str,
        *,
        image_id: str,
        prompt_used: str = "",
    ) -> StoryScene:
        """Attach an image to a scene after generation.

        Shorthand for ``update_scene(..., image_id=..., prompt_used=...)``.
        """
        return self.update_scene(
            story_id, chapter_id, scene_id,
            image_id=image_id, prompt_used=prompt_used,
        )

    def delete_scene(
        self,
        story_id: str,
        chapter_id: str,
        scene_id: str,
    ) -> None:
        """Delete a scene.

        Raises:
            StoryNotFoundError: If the story does not exist.
            ChapterNotFoundError: If the chapter is not found.
            SceneNotFoundError: If the scene is not found.
        """
        story = self.get(story_id)
        d = story.to_dict()

        for ch_data in d["chapters"]:
            if ch_data["chapter_id"] == chapter_id:
                scenes = ch_data.get("scenes", [])
                original_len = len(scenes)
                scenes = [
                    s for s in scenes if s["scene_id"] != scene_id
                ]
                if len(scenes) == original_len:
                    raise SceneNotFoundError(scene_id, chapter_id)

                # Renumber scenes
                for i, sc_data in enumerate(scenes):
                    sc_data["scene_number"] = i + 1

                ch_data["scenes"] = scenes
                d["updated_at"] = datetime.now(timezone.utc).isoformat()
                updated = StoryRecord.from_dict(d)
                self._save(updated)
                return

        raise ChapterNotFoundError(chapter_id, story_id)

    # ── Narration Prompt Building ────────────────────────────

    @staticmethod
    def build_scene_narration_prompt(
        story: StoryRecord,
        chapter: StoryChapter,
        scene: StoryScene,
        *,
        character_manager: Any = None,
        location_manager: Any = None,
        preceding_count: int = 3,
    ) -> str:
        """Build a rich LLM prompt for scene narration.

        Gathers context from:
        - Story synopsis
        - Chapter synopsis and position
        - Preceding scene narratives (for continuity)
        - Character descriptions (if character_manager provided)
        - Location description (if location_manager provided)
        - Scene mood directive

        Args:
            story: The parent StoryRecord.
            chapter: The parent StoryChapter.
            scene: The scene to generate narration for.
            character_manager: Optional CharacterManager for entity context.
            location_manager: Optional LocationManager for entity context.
            preceding_count: Number of preceding scenes to include.

        Returns:
            A structured prompt string for the LLM.
        """
        parts: list[str] = []

        # Story context
        parts.append(f"# Story: {story.title}")
        if story.synopsis:
            parts.append(f"Synopsis: {story.synopsis}")

        # Chapter context
        parts.append(
            f"\n## Chapter {chapter.chapter_number}: "
            f"{chapter.title or 'Untitled'}"
        )
        if chapter.synopsis:
            parts.append(f"Chapter synopsis: {chapter.synopsis}")

        # Preceding scenes for continuity
        preceding_scenes = [
            s for s in chapter.scenes
            if s.scene_number < scene.scene_number and s.narrative_text
        ]
        if preceding_scenes:
            # Take the last N
            recent = preceding_scenes[-preceding_count:]
            parts.append("\n### What has happened so far in this chapter:")
            for ps in recent:
                parts.append(f"Scene {ps.scene_number}: {ps.narrative_text}")

        # Character context
        if scene.characters and character_manager is not None:
            char_descs: list[str] = []
            for char_id in scene.characters:
                try:
                    char = character_manager.get(char_id)
                    desc = f"- {char.name}: {char.description}"
                    if char.backstory:
                        desc += f" ({char.backstory[:100]}...)"
                    char_descs.append(desc)
                except Exception:
                    char_descs.append(f"- {char_id} (unknown)")
            if char_descs:
                parts.append("\n### Characters in this scene:")
                parts.extend(char_descs)

        # Location context
        if scene.location_id and location_manager is not None:
            try:
                loc = location_manager.get(scene.location_id)
                parts.append(f"\n### Setting: {loc.name}")
                if loc.description:
                    parts.append(loc.description)
            except Exception:
                pass

        # Mood directive
        if scene.mood:
            parts.append(f"\n### Mood: {scene.mood}")
            parts.append(
                f"The narration should evoke a {scene.mood} atmosphere."
            )

        # Instruction
        parts.append(
            "\n### Task:\n"
            "Write the next scene of this story. "
            "Write in third person, present tense. "
            "Be vivid and atmospheric. "
            "Aim for 2-4 paragraphs. "
            "Do not include any meta-commentary — just the story."
        )

        return "\n".join(parts)

    # ── Internal: Entity References ──────────────────────────

    @staticmethod
    def _update_entity_refs(
        story_data: dict[str, Any],
        characters: list[str] | None,
        location_id: str,
    ) -> None:
        """Update the entity_refs dict on a story data dict."""
        refs = story_data.setdefault("entity_refs", {})

        if characters:
            existing_chars = set(refs.get("characters", []))
            existing_chars.update(characters)
            refs["characters"] = sorted(existing_chars)

        if location_id:
            existing_locs = set(refs.get("locations", []))
            existing_locs.add(location_id)
            refs["locations"] = sorted(existing_locs)

    # ── Internal: File I/O ───────────────────────────────────

    def _path(self, story_id: str) -> Path:
        """Build the file path for a story."""
        return self._dir / f"{story_id}.json"

    def _save(self, story: StoryRecord) -> None:
        """Persist a story to disk."""
        content = json.dumps(
            story.to_dict(),
            indent=2,
            ensure_ascii=False,
        )
        atomic_write(self._path(story.story_id), content + "\n")

    def _next_id(self) -> str:
        """Generate the next sequential ``ST-XXXX`` ID."""
        existing_nums: list[int] = []
        for path in self._dir.glob(f"{self._ID_PREFIX}-*.json"):
            stem = path.stem
            try:
                num = int(stem.split("-")[1])
                existing_nums.append(num)
            except (IndexError, ValueError):
                continue
        next_num = max(existing_nums, default=0) + 1
        return f"{self._ID_PREFIX}-{next_num:04d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        return f"StoryManager(dir={str(self._dir)!r})"
