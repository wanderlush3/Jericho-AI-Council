"""
Tests for core.generation_pipeline — F-037f Generation Pipeline.

Covers:
- GenerationRequest / GenerationProgress data classes
- GenerationPipeline job lifecycle (create, run, cancel)
- Queue limit enforcement
- Prompt mode routing (all 5 modes)
- Template filling
- Image saving after download
- Error handling (ComfyUI failures, template not found, etc.)
"""

from __future__ import annotations

import asyncio
import json
import pytest
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from core.generation_pipeline import (
    GenerationError,
    GenerationNotFoundError,
    GenerationValidationError,
    GenerationQueueFullError,
    GenerationRequest,
    GenerationProgress,
    GenerationPipeline,
    GENERATION_STAGES,
    _ACTIVE_STATUSES,
    _TERMINAL_STATUSES,
    _JobState,
)


# ─── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def mock_comfyui_client():
    """Mock ComfyUI client with async methods."""
    client = MagicMock()
    client.queue_workflow = AsyncMock(return_value="comfyui-prompt-001")
    client.get_history = AsyncMock(return_value={
        "status": {"completed": True, "status_str": "success"},
        "outputs": {
            "9": {
                "images": [
                    {"filename": "output_001.png", "subfolder": "", "type": "output"}
                ]
            }
        },
    })
    client.download_image = AsyncMock(return_value=b"\x89PNG\r\n\x1a\nfakedata")
    client._poll_interval = 0.01
    client._max_poll_attempts = 5
    return client


@pytest.fixture
def mock_template_manager():
    """Mock workflow template manager."""
    mgr = MagicMock()
    mgr.get = MagicMock(return_value=MagicMock(
        id="TPL-0001",
        name="Test Template",
        placeholders=["prompt", "negative", "seed", "width", "height"],
    ))
    mgr.fill_template = MagicMock(return_value={"workflow": "filled"})
    return mgr


@pytest.fixture
def mock_image_manager(tmp_path):
    """Mock image manager."""
    mgr = MagicMock()
    saved_image = MagicMock()
    saved_image.id = "IMG-0001"
    saved_image.filename = "img_0001.png"
    mgr.save_image = MagicMock(return_value=saved_image)
    return mgr


@pytest.fixture
def mock_prompt_builder():
    """Mock prompt builder."""
    builder = MagicMock()
    result = MagicMock()
    result.positive = "a beautiful landscape"
    result.negative = "blurry, low quality"
    builder.generate = AsyncMock(return_value=result)
    return builder


@pytest.fixture
def pipeline(mock_comfyui_client, mock_template_manager, mock_image_manager, mock_prompt_builder):
    """Fully wired pipeline with mocks."""
    return GenerationPipeline(
        comfyui_client=mock_comfyui_client,
        template_manager=mock_template_manager,
        image_manager=mock_image_manager,
        prompt_builder=mock_prompt_builder,
    )


@pytest.fixture
def valid_request():
    """A basic valid GenerationRequest."""
    return GenerationRequest.create(
        entity_type="character",
        entity_id="CH-0001",
        template_id="TPL-0001",
        prompt_mode="system",
        width=512,
        height=512,
    )


# ─── Test GenerationRequest ───────────────────────────────────


class TestGenerationRequest:
    """Tests for the GenerationRequest data class."""

    def test_create_basic(self):
        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
        )
        assert req.entity_type == "character"
        assert req.entity_id == "CH-0001"
        assert req.template_id == "TPL-0001"
        assert req.prompt_mode == "system"
        assert req.width == 512
        assert req.height == 512
        assert req.seed > 0  # auto-generated

    def test_create_with_all_fields(self):
        req = GenerationRequest.create(
            entity_type="location",
            entity_id="LOC-0001",
            template_id="TPL-0002",
            prompt_mode="character",
            member_name="Spark",
            style_preset_key="fantasy_art",
            width=1024,
            height=768,
            seed=42,
        )
        assert req.prompt_mode == "character"
        assert req.member_name == "Spark"
        assert req.style_preset_key == "fantasy_art"
        assert req.width == 1024
        assert req.height == 768
        assert req.seed == 42

    def test_create_raw_user_mode(self):
        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
            prompt_mode="raw_user",
            user_prompt="a knight in shining armor",
        )
        assert req.prompt_mode == "raw_user"
        assert req.user_prompt == "a knight in shining armor"

    def test_create_council_vote_mode(self):
        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
            prompt_mode="council_vote",
            participants=["Spark", "Sage", "Forge"],
            selected_prompt_index=1,
        )
        assert req.participants == ["Spark", "Sage", "Forge"]
        assert req.selected_prompt_index == 1

    def test_create_empty_entity_type_raises(self):
        with pytest.raises(GenerationValidationError) as exc_info:
            GenerationRequest.create(
                entity_type="",
                entity_id="CH-0001",
                template_id="TPL-0001",
            )
        assert "entity_type" in str(exc_info.value)

    def test_create_empty_entity_id_raises(self):
        with pytest.raises(GenerationValidationError) as exc_info:
            GenerationRequest.create(
                entity_type="character",
                entity_id="",
                template_id="TPL-0001",
            )
        assert "entity_id" in str(exc_info.value)

    def test_create_empty_template_id_raises(self):
        with pytest.raises(GenerationValidationError) as exc_info:
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="",
            )
        assert "template_id" in str(exc_info.value)

    def test_create_invalid_mode_raises(self):
        with pytest.raises(GenerationValidationError) as exc_info:
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                prompt_mode="invalid_mode",
            )
        assert "Invalid prompt_mode" in str(exc_info.value)

    def test_create_character_mode_no_member_raises(self):
        with pytest.raises(GenerationValidationError):
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                prompt_mode="character",
            )

    def test_create_raw_user_no_prompt_raises(self):
        with pytest.raises(GenerationValidationError):
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                prompt_mode="raw_user",
            )

    def test_create_user_refined_no_prompt_raises(self):
        with pytest.raises(GenerationValidationError):
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                prompt_mode="user_refined",
                member_name="Spark",
            )

    def test_create_user_refined_no_member_raises(self):
        with pytest.raises(GenerationValidationError):
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                prompt_mode="user_refined",
                user_prompt="a castle",
            )

    def test_create_council_vote_too_few_participants_raises(self):
        with pytest.raises(GenerationValidationError):
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                prompt_mode="council_vote",
                participants=["Spark"],
            )

    def test_create_invalid_width_raises(self):
        with pytest.raises(GenerationValidationError):
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                width=10,
            )

    def test_create_invalid_height_raises(self):
        with pytest.raises(GenerationValidationError):
            GenerationRequest.create(
                entity_type="character",
                entity_id="CH-0001",
                template_id="TPL-0001",
                height=5000,
            )

    def test_frozen(self):
        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
        )
        with pytest.raises(FrozenInstanceError):
            req.entity_type = "location"

    def test_to_dict_roundtrip(self):
        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
            prompt_mode="raw_user",
            user_prompt="test prompt",
            seed=42,
        )
        d = req.to_dict()
        restored = GenerationRequest.from_dict(d)
        assert restored.entity_type == req.entity_type
        assert restored.entity_id == req.entity_id
        assert restored.template_id == req.template_id
        assert restored.prompt_mode == req.prompt_mode
        assert restored.user_prompt == req.user_prompt
        assert restored.seed == req.seed

    def test_whitespace_stripping(self):
        req = GenerationRequest.create(
            entity_type="  character  ",
            entity_id="  CH-0001  ",
            template_id="  TPL-0001  ",
        )
        assert req.entity_type == "character"
        assert req.entity_id == "CH-0001"
        assert req.template_id == "TPL-0001"


# ─── Test GenerationProgress ─────────────────────────────────


class TestGenerationProgress:
    """Tests for the GenerationProgress data class."""

    def test_create_basic(self):
        p = GenerationProgress(job_id="GEN-0001")
        assert p.job_id == "GEN-0001"
        assert p.stage == "queued"
        assert p.progress_pct == 0
        assert p.message == ""
        assert p.error == ""
        assert p.image_id == ""

    def test_with_all_fields(self):
        p = GenerationProgress(
            job_id="GEN-0001",
            stage="completed",
            progress_pct=100,
            message="Done!",
            image_id="IMG-0001",
            prompt_positive="a castle",
            prompt_negative="blurry",
        )
        assert p.stage == "completed"
        assert p.progress_pct == 100
        assert p.image_id == "IMG-0001"
        assert p.prompt_positive == "a castle"

    def test_frozen(self):
        p = GenerationProgress(job_id="GEN-0001")
        with pytest.raises(FrozenInstanceError):
            p.stage = "completed"

    def test_to_dict(self):
        p = GenerationProgress(
            job_id="GEN-0001",
            stage="running",
            progress_pct=50,
            message="Working...",
        )
        d = p.to_dict()
        assert d["job_id"] == "GEN-0001"
        assert d["stage"] == "running"
        assert d["progress_pct"] == 50

    def test_from_dict(self):
        d = {"job_id": "GEN-0001", "stage": "failed", "error": "timeout"}
        p = GenerationProgress.from_dict(d)
        assert p.job_id == "GEN-0001"
        assert p.stage == "failed"
        assert p.error == "timeout"


# ─── Test Constants ──────────────────────────────────────────


class TestConstants:
    """Tests for module-level constants."""

    def test_generation_stages(self):
        assert "prompt_generating" in GENERATION_STAGES
        assert "completed" in GENERATION_STAGES
        assert "failed" in GENERATION_STAGES
        assert "cancelled" in GENERATION_STAGES

    def test_active_statuses(self):
        assert "running" in _ACTIVE_STATUSES
        assert "completed" not in _ACTIVE_STATUSES

    def test_terminal_statuses(self):
        assert "completed" in _TERMINAL_STATUSES
        assert "failed" in _TERMINAL_STATUSES
        assert "cancelled" in _TERMINAL_STATUSES
        assert "running" not in _TERMINAL_STATUSES


# ─── Test Exceptions ─────────────────────────────────────────


class TestExceptions:
    """Tests for exception hierarchy."""

    def test_hierarchy(self):
        assert issubclass(GenerationNotFoundError, GenerationError)
        assert issubclass(GenerationValidationError, GenerationError)
        assert issubclass(GenerationQueueFullError, GenerationError)

    def test_not_found_fields(self):
        exc = GenerationNotFoundError("GEN-0001")
        assert exc.job_id == "GEN-0001"
        assert "GEN-0001" in str(exc)

    def test_validation_error_string(self):
        exc = GenerationValidationError("single error")
        assert exc.errors == ["single error"]

    def test_validation_error_list(self):
        exc = GenerationValidationError(["error1", "error2"])
        assert len(exc.errors) == 2

    def test_queue_full_error(self):
        exc = GenerationQueueFullError(10)
        assert exc.max_size == 10
        assert "10" in str(exc)


# ─── Test Pipeline Init ─────────────────────────────────────


class TestPipelineInit:
    """Tests for pipeline initialization."""

    def test_create(self, pipeline):
        assert pipeline.active_job_count == 0
        assert pipeline.max_queue_size == 10

    def test_custom_queue_size(self):
        p = GenerationPipeline(max_queue_size=5)
        assert p.max_queue_size == 5

    def test_repr(self, pipeline):
        r = repr(pipeline)
        assert "active=0" in r
        assert "total=0" in r


# ─── Test Start Generation ───────────────────────────────────


class TestStartGeneration:
    """Tests for starting generation jobs."""

    def test_start_basic(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        assert job_id == "GEN-0001"
        assert pipeline.active_job_count == 1

    def test_start_sequential_ids(self, pipeline, valid_request):
        id1 = pipeline.start_generation(valid_request)
        id2 = pipeline.start_generation(valid_request)
        assert id1 == "GEN-0001"
        assert id2 == "GEN-0002"

    def test_start_template_not_found(self, pipeline, mock_template_manager):
        from core.comfyui_client import TemplateNotFoundError
        mock_template_manager.get.side_effect = TemplateNotFoundError("TPL-9999")

        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-9999",
        )
        with pytest.raises(GenerationValidationError) as exc_info:
            pipeline.start_generation(req)
        assert "TPL-9999" in str(exc_info.value)

    def test_start_queue_full(self, pipeline, valid_request):
        # Fill the queue
        pipeline._max_queue_size = 2
        pipeline.start_generation(valid_request)
        pipeline.start_generation(valid_request)

        with pytest.raises(GenerationQueueFullError) as exc_info:
            pipeline.start_generation(valid_request)
        assert exc_info.value.max_size == 2

    def test_start_queue_allows_after_completion(self, pipeline, valid_request):
        pipeline._max_queue_size = 1
        job_id = pipeline.start_generation(valid_request)

        # Simulate completion
        pipeline._jobs[job_id].stage = "completed"

        # Should now allow a new job
        job_id2 = pipeline.start_generation(valid_request)
        assert job_id2 is not None


# ─── Test Run Job ────────────────────────────────────────────


class TestRunJob:
    """Tests for the job execution pipeline."""

    @pytest.mark.asyncio
    async def test_run_full_pipeline(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        stages = []
        async for progress in pipeline.run_job(job_id):
            stages.append(progress.stage)

        assert stages == [
            "prompt_generating",
            "template_filling",
            "queued",
            "running",
            "downloading",
            "saving",
            "completed",
        ]

    @pytest.mark.asyncio
    async def test_run_sets_image_id(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        last_progress = None
        async for progress in pipeline.run_job(job_id):
            last_progress = progress

        assert last_progress is not None
        assert last_progress.stage == "completed"
        assert last_progress.image_id == "IMG-0001"

    @pytest.mark.asyncio
    async def test_run_sets_prompts(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        prompts_seen = False
        async for progress in pipeline.run_job(job_id):
            if progress.stage == "template_filling":
                assert progress.prompt_positive == "a beautiful landscape"
                assert progress.prompt_negative == "blurry, low quality"
                prompts_seen = True

        assert prompts_seen

    @pytest.mark.asyncio
    async def test_run_calls_prompt_builder(self, pipeline, valid_request, mock_prompt_builder):
        job_id = pipeline.start_generation(valid_request)
        async for _ in pipeline.run_job(job_id):
            pass

        mock_prompt_builder.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_calls_template_fill(self, pipeline, valid_request, mock_template_manager):
        job_id = pipeline.start_generation(valid_request)
        async for _ in pipeline.run_job(job_id):
            pass

        mock_template_manager.fill_template.assert_called_once()
        args = mock_template_manager.fill_template.call_args
        assert args[0][0] == "TPL-0001"  # template_id
        values = args[0][1]
        assert "prompt" in values
        assert "negative" in values
        assert "seed" in values

    @pytest.mark.asyncio
    async def test_run_calls_queue_workflow(self, pipeline, valid_request, mock_comfyui_client):
        job_id = pipeline.start_generation(valid_request)
        async for _ in pipeline.run_job(job_id):
            pass

        mock_comfyui_client.queue_workflow.assert_called_once_with(
            {"workflow": "filled"},
        )

    @pytest.mark.asyncio
    async def test_run_calls_download_image(self, pipeline, valid_request, mock_comfyui_client):
        job_id = pipeline.start_generation(valid_request)
        async for _ in pipeline.run_job(job_id):
            pass

        mock_comfyui_client.download_image.assert_called_once_with(
            "output_001.png",
            subfolder="",
            image_type="output",
        )

    @pytest.mark.asyncio
    async def test_run_calls_save_image(self, pipeline, valid_request, mock_image_manager):
        job_id = pipeline.start_generation(valid_request)
        async for _ in pipeline.run_job(job_id):
            pass

        mock_image_manager.save_image.assert_called_once()
        kwargs = mock_image_manager.save_image.call_args[1]
        assert kwargs["entity_type"] == "character"
        assert kwargs["entity_id"] == "CH-0001"
        assert kwargs["prompt"] == "a beautiful landscape"
        assert kwargs["negative_prompt"] == "blurry, low quality"
        assert kwargs["generation_job_id"] == "GEN-0001"

    @pytest.mark.asyncio
    async def test_run_not_found_raises(self, pipeline):
        with pytest.raises(GenerationNotFoundError):
            async for _ in pipeline.run_job("GEN-9999"):
                pass

    @pytest.mark.asyncio
    async def test_run_comfyui_error_yields_failed(
        self, pipeline, valid_request, mock_comfyui_client,
    ):
        mock_comfyui_client.queue_workflow.side_effect = Exception("Connection refused")

        job_id = pipeline.start_generation(valid_request)
        stages = []
        async for progress in pipeline.run_job(job_id):
            stages.append(progress.stage)

        assert "failed" in stages

    @pytest.mark.asyncio
    async def test_run_no_output_images_fails(
        self, pipeline, valid_request, mock_comfyui_client,
    ):
        # Return history with no output images
        mock_comfyui_client.get_history.return_value = {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {},
        }

        job_id = pipeline.start_generation(valid_request)
        stages = []
        async for progress in pipeline.run_job(job_id):
            stages.append(progress.stage)

        assert "failed" in stages

    @pytest.mark.asyncio
    async def test_run_progress_percentages_increase(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        percentages = []
        async for progress in pipeline.run_job(job_id):
            percentages.append(progress.progress_pct)

        # Percentages should generally increase
        for i in range(1, len(percentages)):
            assert percentages[i] >= percentages[i - 1] or percentages[i] == 0


# ─── Test Council Vote Mode ─────────────────────────────────


class TestCouncilVoteMode:
    """Tests for council_vote prompt mode handling."""

    @pytest.mark.asyncio
    async def test_council_vote_selects_prompt(self, pipeline, mock_prompt_builder):
        # Return list of results for council_vote
        result1 = MagicMock()
        result1.positive = "prompt one"
        result1.negative = "neg one"
        result2 = MagicMock()
        result2.positive = "prompt two"
        result2.negative = "neg two"
        result3 = MagicMock()
        result3.positive = "prompt three"
        result3.negative = "neg three"
        mock_prompt_builder.generate.return_value = [result1, result2, result3]

        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
            prompt_mode="council_vote",
            participants=["Spark", "Sage", "Forge"],
            selected_prompt_index=1,  # pick the second prompt
        )

        job_id = pipeline.start_generation(req)
        last = None
        async for progress in pipeline.run_job(job_id):
            last = progress

        assert last.prompt_positive == "prompt two"
        assert last.prompt_negative == "neg two"

    @pytest.mark.asyncio
    async def test_council_vote_defaults_to_first(self, pipeline, mock_prompt_builder):
        result1 = MagicMock()
        result1.positive = "first prompt"
        result1.negative = "first neg"
        result2 = MagicMock()
        result2.positive = "second"
        result2.negative = "second neg"
        mock_prompt_builder.generate.return_value = [result1, result2]

        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
            prompt_mode="council_vote",
            participants=["Spark", "Sage"],
            selected_prompt_index=99,  # out of range
        )

        job_id = pipeline.start_generation(req)
        last = None
        async for progress in pipeline.run_job(job_id):
            last = progress

        assert last.prompt_positive == "first prompt"


# ─── Test Cancel Job ─────────────────────────────────────────


class TestCancelJob:
    """Tests for job cancellation."""

    def test_cancel_active_job(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        result = pipeline.cancel_job(job_id)
        assert result.stage == "cancelled"
        assert result.message == "Generation cancelled."

    def test_cancel_not_found(self, pipeline):
        with pytest.raises(GenerationNotFoundError):
            pipeline.cancel_job("GEN-9999")

    def test_cancel_completed_job_noop(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        # Simulate completion
        pipeline._jobs[job_id].stage = "completed"

        result = pipeline.cancel_job(job_id)
        assert result.stage == "completed"  # not changed

    @pytest.mark.asyncio
    async def test_cancel_during_run(self, pipeline, valid_request, mock_prompt_builder):
        """Cancel is checked between stages."""
        # Slow down the prompt builder to give us time to cancel
        original_generate = mock_prompt_builder.generate

        async def slow_generate(*args, **kwargs):
            result = MagicMock()
            result.positive = "test"
            result.negative = ""
            return result

        mock_prompt_builder.generate = AsyncMock(side_effect=slow_generate)

        job_id = pipeline.start_generation(valid_request)

        # Pre-cancel the job
        pipeline._jobs[job_id].cancelled = True

        stages = []
        async for progress in pipeline.run_job(job_id):
            stages.append(progress.stage)

        assert "cancelled" in stages


# ─── Test Query Jobs ─────────────────────────────────────────


class TestQueryJobs:
    """Tests for job query methods."""

    def test_get_job(self, pipeline, valid_request):
        job_id = pipeline.start_generation(valid_request)
        job = pipeline.get_job(job_id)
        assert job["job_id"] == job_id
        assert job["entity_type"] == "character"

    def test_get_job_not_found(self, pipeline):
        with pytest.raises(GenerationNotFoundError):
            pipeline.get_job("GEN-9999")

    def test_list_jobs_empty(self, pipeline):
        assert pipeline.list_jobs() == []

    def test_list_jobs_all(self, pipeline, valid_request):
        pipeline.start_generation(valid_request)
        pipeline.start_generation(valid_request)
        jobs = pipeline.list_jobs()
        assert len(jobs) == 2

    def test_list_jobs_active_only(self, pipeline, valid_request):
        id1 = pipeline.start_generation(valid_request)
        id2 = pipeline.start_generation(valid_request)
        # Mark one as completed
        pipeline._jobs[id1].stage = "completed"

        active = pipeline.list_jobs(active_only=True)
        assert len(active) == 1
        assert active[0]["job_id"] == id2

    def test_list_jobs_sorted_newest_first(self, pipeline, valid_request):
        id1 = pipeline.start_generation(valid_request)
        id2 = pipeline.start_generation(valid_request)
        # Ensure distinct timestamps for deterministic sort
        pipeline._jobs[id1].created_at = "2026-01-01T00:00:00+00:00"
        pipeline._jobs[id2].created_at = "2026-01-01T00:01:00+00:00"
        jobs = pipeline.list_jobs()
        assert jobs[0]["job_id"] == id2  # newest first


# ─── Test Prune Completed ───────────────────────────────────


class TestPruneCompleted:
    """Tests for completed job pruning."""

    def test_prune_old_completed(self, pipeline, valid_request):
        from core.generation_pipeline import _MAX_COMPLETED_JOBS

        pipeline._max_queue_size = 200

        # Create many completed jobs
        for i in range(120):
            jid = pipeline.start_generation(valid_request)
            pipeline._jobs[jid].stage = "completed"
            pipeline._jobs[jid].completed_at = f"2026-01-01T00:{i:02d}:00+00:00"

        # Creating another job should trigger pruning
        pipeline.start_generation(valid_request)

        completed = [
            j for j in pipeline._jobs.values()
            if j.stage == "completed"
        ]
        assert len(completed) <= _MAX_COMPLETED_JOBS


# ─── Test JobState ───────────────────────────────────────────


class TestJobState:
    """Tests for internal _JobState class."""

    def test_to_progress(self, valid_request):
        job = _JobState(job_id="GEN-0001", request=valid_request)
        p = job.to_progress()
        assert p.job_id == "GEN-0001"
        assert p.stage == "queued"

    def test_to_dict(self, valid_request):
        job = _JobState(job_id="GEN-0001", request=valid_request)
        d = job.to_dict()
        assert d["job_id"] == "GEN-0001"
        assert d["entity_type"] == "character"
        assert d["template_id"] == "TPL-0001"
        assert d["created_at"] != ""


# ─── Test Edge Cases ────────────────────────────────────────


class TestEdgeCases:
    """Edge case tests."""

    def test_unicode_prompt(self):
        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
            prompt_mode="raw_user",
            user_prompt="日本語のテスト 🎨",
        )
        assert req.user_prompt == "日本語のテスト 🎨"

    @pytest.mark.asyncio
    async def test_comfyui_workflow_error_in_history(
        self, pipeline, valid_request, mock_comfyui_client,
    ):
        mock_comfyui_client.get_history.return_value = {
            "status": {
                "completed": False,
                "status_str": "error",
                "messages": [["execution_error", {"message": "Node failed"}]],
            },
        }

        job_id = pipeline.start_generation(valid_request)
        stages = []
        async for progress in pipeline.run_job(job_id):
            stages.append(progress.stage)

        assert "failed" in stages

    @pytest.mark.asyncio
    async def test_multiple_output_images_uses_first(
        self, pipeline, valid_request, mock_comfyui_client,
    ):
        mock_comfyui_client.get_history.return_value = {
            "status": {"completed": True, "status_str": "success"},
            "outputs": {
                "9": {
                    "images": [
                        {"filename": "first.png", "subfolder": "", "type": "output"},
                        {"filename": "second.png", "subfolder": "", "type": "output"},
                    ]
                }
            },
        }

        job_id = pipeline.start_generation(valid_request)
        async for _ in pipeline.run_job(job_id):
            pass

        mock_comfyui_client.download_image.assert_called_once_with(
            "first.png", subfolder="", image_type="output",
        )

    def test_active_job_count(self, pipeline, valid_request):
        pipeline.start_generation(valid_request)
        pipeline.start_generation(valid_request)
        assert pipeline.active_job_count == 2

        # Complete one
        pipeline._jobs["GEN-0001"].stage = "completed"
        assert pipeline.active_job_count == 1

    @pytest.mark.asyncio
    async def test_style_preset_passed_through(
        self, pipeline, mock_prompt_builder,
    ):
        req = GenerationRequest.create(
            entity_type="character",
            entity_id="CH-0001",
            template_id="TPL-0001",
            prompt_mode="system",
            style_preset_key="fantasy_art",
        )

        job_id = pipeline.start_generation(req)
        async for _ in pipeline.run_job(job_id):
            pass

        # Verify prompt builder got the right request
        call_args = mock_prompt_builder.generate.call_args
        prompt_request = call_args[0][0]
        assert prompt_request.style_preset is not None
