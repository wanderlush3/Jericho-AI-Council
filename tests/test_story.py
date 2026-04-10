"""
Tests for ``core.story`` — F-041 Story Illustration System.
"""

import json
import os
import tempfile
from pathlib import Path

import pytest

from core.story import (
    ChapterNotFoundError,
    SceneNotFoundError,
    StoryChapter,
    StoryError,
    StoryLifecycleError,
    StoryManager,
    StoryNotFoundError,
    StoryRecord,
    StoryScene,
    StoryValidationError,
)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def stories_dir(tmp_path, monkeypatch):
    d = tmp_path / "stories"
    d.mkdir()
    monkeypatch.setattr("config.settings.STORIES_DIR", d)
    return d


@pytest.fixture
def mgr(stories_dir):
    return StoryManager(stories_dir=stories_dir)


# ─── TestStoryScene ──────────────────────────────────────────


class TestStoryScene:
    def test_fields(self):
        sc = StoryScene(scene_id="SCE-0001", chapter_id="CHP-0001")
        assert sc.scene_id == "SCE-0001"
        assert sc.chapter_id == "CHP-0001"
        assert sc.scene_number == 1
        assert sc.narrative_text == ""
        assert sc.image_id == ""
        assert sc.characters == []
        assert sc.mood == ""

    def test_frozen(self):
        sc = StoryScene(scene_id="SCE-0001", chapter_id="CHP-0001")
        with pytest.raises(AttributeError):
            sc.scene_id = "other"

    def test_roundtrip(self):
        sc = StoryScene(
            scene_id="SCE-0001", chapter_id="CHP-0001",
            scene_number=2, narrative_text="It was dark.",
            image_id="IMG-0001", characters=["CH-0001"],
            location_id="LOC-0001", mood="tense",
        )
        d = sc.to_dict()
        restored = StoryScene.from_dict(d)
        assert restored == sc

    def test_create_factory(self):
        sc = StoryScene.create(
            scene_id="SCE-0001", chapter_id="CHP-0001",
            scene_number=3, mood="joyful",
            characters=["CH-0001", "CH-0002"],
            location_id="LOC-0001",
        )
        assert sc.scene_id == "SCE-0001"
        assert sc.scene_number == 3
        assert sc.mood == "joyful"
        assert sc.created_at != ""   # auto-timestamped

    def test_create_validation_empty_ids(self):
        with pytest.raises(StoryValidationError) as exc_info:
            StoryScene.create(scene_id="", chapter_id="")
        assert "scene_id" in str(exc_info.value)
        assert "chapter_id" in str(exc_info.value)

    def test_create_validation_bad_scene_number(self):
        with pytest.raises(StoryValidationError):
            StoryScene.create(
                scene_id="SCE-0001", chapter_id="CHP-0001", scene_number=0,
            )


# ─── TestStoryChapter ────────────────────────────────────────


class TestStoryChapter:
    def test_fields(self):
        ch = StoryChapter(chapter_id="CHP-0001", story_id="ST-0001")
        assert ch.chapter_id == "CHP-0001"
        assert ch.story_id == "ST-0001"
        assert ch.scenes == []

    def test_frozen(self):
        ch = StoryChapter(chapter_id="CHP-0001", story_id="ST-0001")
        with pytest.raises(AttributeError):
            ch.title = "New"

    def test_roundtrip(self):
        scene = StoryScene(scene_id="SCE-0001", chapter_id="CHP-0001",
                           narrative_text="Hello")
        ch = StoryChapter(
            chapter_id="CHP-0001", story_id="ST-0001",
            chapter_number=1, title="Chapter One",
            synopsis="Introduction", scenes=[scene],
        )
        d = ch.to_dict()
        restored = StoryChapter.from_dict(d)
        assert restored.chapter_id == ch.chapter_id
        assert len(restored.scenes) == 1
        assert restored.scenes[0].narrative_text == "Hello"

    def test_create_factory(self):
        ch = StoryChapter.create(
            chapter_id="CHP-0001", story_id="ST-0001",
            title="The Beginning", synopsis="It starts here.",
        )
        assert ch.chapter_id == "CHP-0001"
        assert ch.title == "The Beginning"
        assert ch.created_at != ""

    def test_create_validation(self):
        with pytest.raises(StoryValidationError):
            StoryChapter.create(chapter_id="", story_id="")


# ─── TestStoryRecord ────────────────────────────────────────


class TestStoryRecord:
    def test_fields(self):
        st = StoryRecord(story_id="ST-0001", title="My Story")
        assert st.story_id == "ST-0001"
        assert st.title == "My Story"
        assert st.status == "draft"
        assert st.chapters == []
        assert st.entity_refs == {}

    def test_frozen(self):
        st = StoryRecord(story_id="ST-0001", title="My Story")
        with pytest.raises(AttributeError):
            st.title = "Other"

    def test_roundtrip(self):
        scene = StoryScene(scene_id="SCE-0001", chapter_id="CHP-0001")
        chapter = StoryChapter(
            chapter_id="CHP-0001", story_id="ST-0001",
            scenes=[scene],
        )
        st = StoryRecord(
            story_id="ST-0001", title="Epic Tale",
            synopsis="A grand story", author="User",
            chapters=[chapter],
            entity_refs={"characters": ["CH-0001"]},
        )
        d = st.to_dict()
        restored = StoryRecord.from_dict(d)
        assert restored.story_id == st.story_id
        assert len(restored.chapters) == 1
        assert len(restored.chapters[0].scenes) == 1

    def test_create_factory(self):
        st = StoryRecord.create(
            story_id="ST-0001", title="Tale of Kings",
            synopsis="A tale", author="Admin",
        )
        assert st.story_id == "ST-0001"
        assert st.status == "draft"
        assert st.created_at != ""
        assert st.updated_at != ""

    def test_create_validation(self):
        with pytest.raises(StoryValidationError):
            StoryRecord.create(story_id="ST-0001", title="")
        with pytest.raises(StoryValidationError):
            StoryRecord.create(story_id="", title="Valid")


# ─── TestStoryManagerInit ────────────────────────────────────


class TestStoryManagerInit:
    def test_dir_creation(self, tmp_path):
        d = tmp_path / "new_dir"
        mgr = StoryManager(stories_dir=d)
        assert d.exists()
        assert mgr.directory == d

    def test_repr(self, mgr):
        assert "StoryManager" in repr(mgr)


# ─── TestStoryCreation ──────────────────────────────────────


class TestStoryCreation:
    def test_basic(self, mgr):
        story = mgr.create("My Story", "Synopsis")
        assert story.story_id == "ST-0001"
        assert story.title == "My Story"
        assert story.synopsis == "Synopsis"
        assert story.status == "draft"

    def test_sequential_ids(self, mgr):
        s1 = mgr.create("Story 1")
        s2 = mgr.create("Story 2")
        assert s1.story_id == "ST-0001"
        assert s2.story_id == "ST-0002"

    def test_persistence(self, mgr, stories_dir):
        mgr.create("Persistent Story")
        path = stories_dir / "ST-0001.json"
        assert path.exists()
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["title"] == "Persistent Story"

    def test_with_options(self, mgr):
        story = mgr.create(
            "Styled Story", author="Writer",
            style_preset_key="fantasy_art",
            template_id="TPL-0001",
            metadata={"genre": "fantasy"},
        )
        assert story.author == "Writer"
        assert story.style_preset_key == "fantasy_art"
        assert story.template_id == "TPL-0001"
        assert story.metadata == {"genre": "fantasy"}

    def test_empty_title_raises(self, mgr):
        with pytest.raises(StoryValidationError):
            mgr.create("")

    def test_whitespace_stripping(self, mgr):
        story = mgr.create("  Spaced Title  ", "  Synopsis  ")
        assert story.title == "Spaced Title"
        assert story.synopsis == "Synopsis"


# ─── TestStoryRetrieval ──────────────────────────────────────


class TestStoryRetrieval:
    def test_get(self, mgr):
        created = mgr.create("Test Story")
        fetched = mgr.get(created.story_id)
        assert fetched.title == "Test Story"

    def test_get_not_found(self, mgr):
        with pytest.raises(StoryNotFoundError):
            mgr.get("ST-9999")

    def test_list_all(self, mgr):
        mgr.create("Story A")
        mgr.create("Story B")
        stories = mgr.list_stories()
        assert len(stories) == 2

    def test_list_filter_status(self, mgr):
        mgr.create("Draft Story")
        s2 = mgr.create("Active Story")
        mgr.update_status(s2.story_id, "active")
        drafts = mgr.list_stories(status="draft")
        assert len(drafts) == 1
        assert drafts[0].title == "Draft Story"

    def test_list_filter_author(self, mgr):
        mgr.create("S1", author="Alice")
        mgr.create("S2", author="Bob")
        alice_stories = mgr.list_stories(author="alice")
        assert len(alice_stories) == 1
        assert alice_stories[0].author == "Alice"

    def test_has_story(self, mgr):
        story = mgr.create("Exists")
        assert mgr.has_story(story.story_id)
        assert not mgr.has_story("ST-9999")


# ─── TestStoryUpdates ────────────────────────────────────────


class TestStoryUpdates:
    def test_update_title(self, mgr):
        story = mgr.create("Original")
        updated = mgr.update(story.story_id, title="Renamed")
        assert updated.title == "Renamed"
        fetched = mgr.get(story.story_id)
        assert fetched.title == "Renamed"

    def test_update_synopsis(self, mgr):
        story = mgr.create("Story", "Old synopsis")
        updated = mgr.update(story.story_id, synopsis="New synopsis")
        assert updated.synopsis == "New synopsis"

    def test_update_empty_title_raises(self, mgr):
        story = mgr.create("Story")
        with pytest.raises(StoryValidationError):
            mgr.update(story.story_id, title="")

    def test_update_not_found(self, mgr):
        with pytest.raises(StoryNotFoundError):
            mgr.update("ST-9999", title="X")

    def test_update_bumps_updated_at(self, mgr):
        story = mgr.create("Story")
        old_updated = story.updated_at
        updated = mgr.update(story.story_id, synopsis="New")
        assert updated.updated_at > old_updated

    def test_status_lifecycle(self, mgr):
        story = mgr.create("Story")
        assert story.status == "draft"

        s = mgr.update_status(story.story_id, "active")
        assert s.status == "active"

        s = mgr.update_status(story.story_id, "completed")
        assert s.status == "completed"

        s = mgr.update_status(story.story_id, "archived")
        assert s.status == "archived"

        s = mgr.update_status(story.story_id, "draft")
        assert s.status == "draft"

    def test_invalid_transition(self, mgr):
        story = mgr.create("Story")
        with pytest.raises(StoryLifecycleError):
            mgr.update_status(story.story_id, "completed")  # draft → completed invalid

    def test_unknown_status(self, mgr):
        story = mgr.create("Story")
        with pytest.raises(StoryValidationError):
            mgr.update_status(story.story_id, "unknown")

    def test_delete(self, mgr):
        story = mgr.create("Deletable")
        mgr.delete(story.story_id)
        assert not mgr.has_story(story.story_id)

    def test_delete_not_found(self, mgr):
        with pytest.raises(StoryNotFoundError):
            mgr.delete("ST-9999")


# ─── TestChapterManagement ───────────────────────────────────


class TestChapterManagement:
    def test_add_chapter(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Chapter 1")
        assert ch.chapter_id == "CHP-0001"
        assert ch.chapter_number == 1
        assert ch.title == "Chapter 1"

    def test_multiple_chapters(self, mgr):
        story = mgr.create("Story")
        ch1 = mgr.add_chapter(story.story_id, title="One")
        ch2 = mgr.add_chapter(story.story_id, title="Two")
        assert ch2.chapter_id == "CHP-0002"
        assert ch2.chapter_number == 2
        fetched = mgr.get(story.story_id)
        assert len(fetched.chapters) == 2

    def test_update_chapter(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Old Title")
        updated = mgr.update_chapter(
            story.story_id, ch.chapter_id, title="New Title",
        )
        assert updated.title == "New Title"

    def test_delete_chapter(self, mgr):
        story = mgr.create("Story")
        ch1 = mgr.add_chapter(story.story_id, title="One")
        ch2 = mgr.add_chapter(story.story_id, title="Two")
        mgr.delete_chapter(story.story_id, ch1.chapter_id)
        fetched = mgr.get(story.story_id)
        assert len(fetched.chapters) == 1
        # Renumbered
        assert fetched.chapters[0].chapter_number == 1

    def test_delete_chapter_not_found(self, mgr):
        story = mgr.create("Story")
        with pytest.raises(ChapterNotFoundError):
            mgr.delete_chapter(story.story_id, "CHP-9999")

    def test_chapter_on_missing_story(self, mgr):
        with pytest.raises(StoryNotFoundError):
            mgr.add_chapter("ST-9999", title="X")


# ─── TestSceneManagement ────────────────────────────────────


class TestSceneManagement:
    def test_add_scene(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        sc = mgr.add_scene(
            story.story_id, ch.chapter_id,
            mood="tense", location_id="LOC-0001",
            characters=["CH-0001"],
        )
        assert sc.scene_id == "SCE-0001"
        assert sc.scene_number == 1
        assert sc.mood == "tense"
        assert sc.characters == ["CH-0001"]
        assert sc.location_id == "LOC-0001"

    def test_multiple_scenes(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        mgr.add_scene(story.story_id, ch.chapter_id)
        sc2 = mgr.add_scene(story.story_id, ch.chapter_id)
        assert sc2.scene_id == "SCE-0002"
        assert sc2.scene_number == 2

    def test_update_scene_narrative(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        sc = mgr.add_scene(story.story_id, ch.chapter_id)
        updated = mgr.update_scene(
            story.story_id, ch.chapter_id, sc.scene_id,
            narrative_text="The tower crumbled...",
        )
        assert updated.narrative_text == "The tower crumbled..."

    def test_attach_illustration(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        sc = mgr.add_scene(story.story_id, ch.chapter_id)
        updated = mgr.attach_illustration(
            story.story_id, ch.chapter_id, sc.scene_id,
            image_id="IMG-0001", prompt_used="a dark tower",
        )
        assert updated.image_id == "IMG-0001"
        assert updated.prompt_used == "a dark tower"

    def test_delete_scene(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        sc1 = mgr.add_scene(story.story_id, ch.chapter_id)
        sc2 = mgr.add_scene(story.story_id, ch.chapter_id)
        mgr.delete_scene(story.story_id, ch.chapter_id, sc1.scene_id)
        fetched = mgr.get(story.story_id)
        scenes = fetched.chapters[0].scenes
        assert len(scenes) == 1
        assert scenes[0].scene_number == 1  # Renumbered

    def test_scene_not_found(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        with pytest.raises(SceneNotFoundError):
            mgr.delete_scene(story.story_id, ch.chapter_id, "SCE-9999")

    def test_scene_on_missing_chapter(self, mgr):
        story = mgr.create("Story")
        with pytest.raises(ChapterNotFoundError):
            mgr.add_scene(story.story_id, "CHP-9999")

    def test_entity_refs_updated(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        mgr.add_scene(
            story.story_id, ch.chapter_id,
            characters=["CH-0001", "CH-0002"],
            location_id="LOC-0001",
        )
        fetched = mgr.get(story.story_id)
        assert "CH-0001" in fetched.entity_refs.get("characters", [])
        assert "LOC-0001" in fetched.entity_refs.get("locations", [])


# ─── TestNarrationPrompt ─────────────────────────────────────


class TestNarrationPrompt:
    def test_basic_prompt(self, mgr):
        story = mgr.create("My Story", "A tale of adventure")
        ch = mgr.add_chapter(story.story_id, title="The Start")
        sc = mgr.add_scene(
            story.story_id, ch.chapter_id, mood="excited",
        )
        story = mgr.get(story.story_id)
        chapter = story.chapters[0]
        scene = chapter.scenes[0]

        prompt = StoryManager.build_scene_narration_prompt(
            story, chapter, scene,
        )
        assert "My Story" in prompt
        assert "A tale of adventure" in prompt
        assert "The Start" in prompt
        assert "excited" in prompt
        assert "Write the next scene" in prompt

    def test_preceding_scenes(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        mgr.add_scene(story.story_id, ch.chapter_id)
        mgr.update_scene(
            story.story_id, ch.chapter_id, "SCE-0001",
            narrative_text="The hero arrived at the gates.",
        )
        sc2 = mgr.add_scene(story.story_id, ch.chapter_id)

        story = mgr.get(story.story_id)
        chapter = story.chapters[0]
        scene2 = chapter.scenes[1]

        prompt = StoryManager.build_scene_narration_prompt(
            story, chapter, scene2,
        )
        assert "The hero arrived at the gates." in prompt

    def test_prompt_with_mood(self, mgr):
        story = mgr.create("Story")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        mgr.add_scene(story.story_id, ch.chapter_id, mood="melancholic")

        story = mgr.get(story.story_id)
        chapter = story.chapters[0]
        scene = chapter.scenes[0]

        prompt = StoryManager.build_scene_narration_prompt(
            story, chapter, scene,
        )
        assert "melancholic" in prompt


# ─── TestEdgeCases ───────────────────────────────────────────


class TestEdgeCases:
    def test_unicode(self, mgr):
        story = mgr.create("Ëlara's Ödyssey", "A tale of ñobles and ᚦing")
        fetched = mgr.get(story.story_id)
        assert fetched.title == "Ëlara's Ödyssey"

    def test_full_lifecycle(self, mgr):
        story = mgr.create("Epic", "Full flow", author="Admin")
        ch = mgr.add_chapter(story.story_id, title="Ch1", synopsis="Start")
        sc = mgr.add_scene(
            story.story_id, ch.chapter_id,
            characters=["CH-0001"], mood="tense",
        )
        mgr.update_scene(
            story.story_id, ch.chapter_id, sc.scene_id,
            narrative_text="The battle raged on.",
        )
        mgr.attach_illustration(
            story.story_id, ch.chapter_id, sc.scene_id,
            image_id="IMG-0001",
        )
        mgr.update_status(story.story_id, "active")
        mgr.update_status(story.story_id, "completed")

        final = mgr.get(story.story_id)
        assert final.status == "completed"
        assert len(final.chapters) == 1
        assert len(final.chapters[0].scenes) == 1
        assert final.chapters[0].scenes[0].image_id == "IMG-0001"

    def test_persistence_roundtrip(self, mgr):
        story = mgr.create("Roundtrip")
        ch = mgr.add_chapter(story.story_id, title="Ch1")
        mgr.add_scene(story.story_id, ch.chapter_id, mood="happy")

        # Recreate manager (simulates restart)
        mgr2 = StoryManager(stories_dir=mgr.directory)
        fetched = mgr2.get(story.story_id)
        assert fetched.title == "Roundtrip"
        assert len(fetched.chapters) == 1
        assert len(fetched.chapters[0].scenes) == 1

    def test_corrupt_json_skipped(self, mgr, stories_dir):
        # Create a valid story
        mgr.create("Valid")
        # Write a corrupt file
        corrupt = stories_dir / "ST-0002.json"
        corrupt.write_text("not json", encoding="utf-8")
        stories = mgr.list_stories()
        assert len(stories) == 1


# ─── TestExceptions ──────────────────────────────────────────


class TestExceptions:
    def test_hierarchy(self):
        assert issubclass(StoryNotFoundError, StoryError)
        assert issubclass(ChapterNotFoundError, StoryError)
        assert issubclass(SceneNotFoundError, StoryError)
        assert issubclass(StoryValidationError, StoryError)
        assert issubclass(StoryLifecycleError, StoryError)

    def test_story_not_found_fields(self):
        exc = StoryNotFoundError("ST-0001")
        assert exc.story_id == "ST-0001"

    def test_chapter_not_found_fields(self):
        exc = ChapterNotFoundError("CHP-0001", "ST-0001")
        assert exc.chapter_id == "CHP-0001"
        assert exc.story_id == "ST-0001"

    def test_scene_not_found_fields(self):
        exc = SceneNotFoundError("SCE-0001", "CHP-0001")
        assert exc.scene_id == "SCE-0001"

    def test_lifecycle_error_fields(self):
        exc = StoryLifecycleError("ST-0001", "draft", "completed")
        assert exc.story_id == "ST-0001"
        assert exc.current_status == "draft"
        assert exc.requested_status == "completed"

    def test_validation_error_multi(self):
        exc = StoryValidationError(["Error 1", "Error 2"])
        assert len(exc.errors) == 2
