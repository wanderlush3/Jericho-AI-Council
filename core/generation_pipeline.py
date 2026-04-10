"""
Jericho — Generation Pipeline & Progress UI (F-037f)

End-to-end image generation flow that connects:

- **PromptBuilder** (F-037c) — generates image prompts via LLM
- **ComfyUIClient** (F-037a) — queues workflows and polls for results
- **WorkflowTemplateManager** (F-037a) — fills workflow templates
- **ImageManager** (F-037b) — stores downloaded images

The pipeline is orchestrated by :class:`GenerationPipeline`, which
manages an in-memory job queue capped at
:data:`config.settings.COMFYUI_MAX_QUEUE_SIZE` concurrent jobs.

Each job progresses through stages::

    prompt_generating → template_filling → queued → running
        → downloading → saving → completed

Jobs can also transition to ``failed`` or ``cancelled`` at any point.

Usage::

    pipeline = GenerationPipeline(
        comfyui_client=client,
        template_manager=tmgr,
        image_manager=img_mgr,
        prompt_builder=builder,
    )
    job_id = pipeline.start_generation(request)
    async for progress in pipeline.run_job(job_id):
        print(progress.stage, progress.message)
"""

from __future__ import annotations

import random
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from config.settings import COMFYUI_MAX_QUEUE_SIZE


# ─── Exceptions ────────────────────────────────────────────────


class GenerationError(Exception):
    """Base exception for generation pipeline errors."""


class GenerationNotFoundError(GenerationError):
    """Raised when a job ID is not found."""

    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(f"Generation job not found: '{job_id}'")


class GenerationValidationError(GenerationError):
    """Raised when a generation request fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


class GenerationQueueFullError(GenerationError):
    """Raised when the job queue is at capacity."""

    def __init__(self, max_size: int) -> None:
        self.max_size = max_size
        super().__init__(
            f"Generation queue is full ({max_size} active jobs). "
            f"Wait for a job to complete or cancel one."
        )


# ─── Constants ─────────────────────────────────────────────────


GENERATION_STAGES = (
    "prompt_generating",
    "template_filling",
    "queued",
    "running",
    "downloading",
    "saving",
    "completed",
    "failed",
    "cancelled",
)

_ACTIVE_STATUSES = frozenset({"prompt_generating", "template_filling",
                               "queued", "running", "downloading", "saving"})

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})

# Max completed jobs to keep in memory before pruning
_MAX_COMPLETED_JOBS = 100


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class GenerationRequest:
    """Input for starting a generation job.

    Attributes:
        entity_type: Type of entity to generate for (character, location, etc.).
        entity_id: ID of the entity (e.g. ``CH-0001``).
        template_id: ComfyUI workflow template ID (``TPL-XXXX``).
        prompt_mode: One of the 5 prompt modes from PromptBuilder.
        member_name: Council member for character/user_refined modes.
        user_prompt: User-supplied prompt text (raw_user/user_refined modes).
        style_preset_key: Key into DEFAULT_STYLE_PRESETS (e.g. ``"fantasy_art"``).
        participants: Member names for council_vote mode.
        selected_prompt_index: For council_vote mode — which prompt to use (0-based).
        width: Image width in pixels.
        height: Image height in pixels.
        seed: Random seed (0 = auto-generate).
        metadata: Arbitrary pass-through metadata.
    """

    entity_type: str
    entity_id: str
    template_id: str
    prompt_mode: str = "system"
    member_name: str = ""
    user_prompt: str = ""
    style_preset_key: str = ""
    participants: list[str] = field(default_factory=list)
    selected_prompt_index: int = 0
    width: int = 512
    height: int = 512
    seed: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GenerationRequest:
        return cls(
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id", ""),
            template_id=data.get("template_id", ""),
            prompt_mode=data.get("prompt_mode", "system"),
            member_name=data.get("member_name", ""),
            user_prompt=data.get("user_prompt", ""),
            style_preset_key=data.get("style_preset_key", ""),
            participants=data.get("participants", []),
            selected_prompt_index=data.get("selected_prompt_index", 0),
            width=data.get("width", 512),
            height=data.get("height", 512),
            seed=data.get("seed", 0),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        entity_type: str,
        entity_id: str,
        template_id: str,
        prompt_mode: str = "system",
        member_name: str = "",
        user_prompt: str = "",
        style_preset_key: str = "",
        participants: list[str] | None = None,
        selected_prompt_index: int = 0,
        width: int = 512,
        height: int = 512,
        seed: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationRequest:
        """Factory with validation."""
        from core.prompt_builder import PROMPT_MODES

        errors: list[str] = []
        if not entity_type.strip():
            errors.append("entity_type is required.")
        if not entity_id.strip():
            errors.append("entity_id is required.")
        if not template_id.strip():
            errors.append("template_id is required.")
        if prompt_mode not in PROMPT_MODES:
            errors.append(
                f"Invalid prompt_mode '{prompt_mode}' — "
                f"must be one of {sorted(PROMPT_MODES)}"
            )
        if prompt_mode == "character" and not member_name.strip():
            errors.append("member_name is required for 'character' mode.")
        if prompt_mode == "user_refined" and not user_prompt.strip():
            errors.append("user_prompt is required for 'user_refined' mode.")
        if prompt_mode == "user_refined" and not member_name.strip():
            errors.append("member_name is required for 'user_refined' mode.")
        if prompt_mode == "raw_user" and not user_prompt.strip():
            errors.append("user_prompt is required for 'raw_user' mode.")
        if prompt_mode == "council_vote":
            effective = participants or []
            if len(effective) < 2:
                errors.append(
                    "At least 2 participants required for 'council_vote' mode."
                )
        if width < 64 or width > 4096:
            errors.append(f"width must be 64–4096, got {width}.")
        if height < 64 or height > 4096:
            errors.append(f"height must be 64–4096, got {height}.")
        if errors:
            raise GenerationValidationError(errors)

        return cls(
            entity_type=entity_type.strip(),
            entity_id=entity_id.strip(),
            template_id=template_id.strip(),
            prompt_mode=prompt_mode,
            member_name=member_name.strip(),
            user_prompt=user_prompt.strip() if user_prompt else "",
            style_preset_key=style_preset_key.strip() if style_preset_key else "",
            participants=participants or [],
            selected_prompt_index=selected_prompt_index,
            width=width,
            height=height,
            seed=seed if seed else random.randint(1, 2**31),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class GenerationProgress:
    """Progress update for a generation job.

    Attributes:
        job_id: The generation job ID (``GEN-XXXX``).
        stage: Current stage of the generation pipeline.
        progress_pct: Estimated progress percentage (0–100).
        message: Human-readable status message.
        error: Error message if stage is ``failed``.
        image_id: The resulting image ID (set on ``completed``).
        prompt_positive: The positive prompt used (set after prompt gen).
        prompt_negative: The negative prompt used (set after prompt gen).
    """

    job_id: str
    stage: str = "queued"
    progress_pct: int = 0
    message: str = ""
    error: str = ""
    image_id: str = ""
    prompt_positive: str = ""
    prompt_negative: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GenerationProgress:
        return cls(
            job_id=data["job_id"],
            stage=data.get("stage", "queued"),
            progress_pct=data.get("progress_pct", 0),
            message=data.get("message", ""),
            error=data.get("error", ""),
            image_id=data.get("image_id", ""),
            prompt_positive=data.get("prompt_positive", ""),
            prompt_negative=data.get("prompt_negative", ""),
        )


# ─── Job State (Mutable Internal Tracker) ────────────────────


class _JobState:
    """Mutable tracking for an active generation job."""

    def __init__(
        self,
        job_id: str,
        request: GenerationRequest,
    ) -> None:
        self.job_id = job_id
        self.request = request
        self.stage: str = "queued"
        self.progress_pct: int = 0
        self.message: str = "Waiting to start..."
        self.error: str = ""
        self.image_id: str = ""
        self.prompt_positive: str = ""
        self.prompt_negative: str = ""
        self.prompt_id: str = ""  # ComfyUI prompt_id
        self.cancelled: bool = False
        self.created_at: str = datetime.now(timezone.utc).isoformat()
        self.completed_at: str = ""

    def to_progress(self) -> GenerationProgress:
        """Snapshot the current state as an immutable GenerationProgress."""
        return GenerationProgress(
            job_id=self.job_id,
            stage=self.stage,
            progress_pct=self.progress_pct,
            message=self.message,
            error=self.error,
            image_id=self.image_id,
            prompt_positive=self.prompt_positive,
            prompt_negative=self.prompt_negative,
        )

    def to_dict(self) -> dict[str, Any]:
        """Full state for API responses."""
        return {
            "job_id": self.job_id,
            "stage": self.stage,
            "progress_pct": self.progress_pct,
            "message": self.message,
            "error": self.error,
            "image_id": self.image_id,
            "prompt_positive": self.prompt_positive,
            "prompt_negative": self.prompt_negative,
            "entity_type": self.request.entity_type,
            "entity_id": self.request.entity_id,
            "template_id": self.request.template_id,
            "prompt_mode": self.request.prompt_mode,
            "cancelled": self.cancelled,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


# ─── Generation Pipeline ─────────────────────────────────────


class GenerationPipeline:
    """Orchestrates end-to-end image generation.

    Connects the PromptBuilder, ComfyUI Client, WorkflowTemplateManager,
    and ImageManager into a single pipeline with SSE-compatible progress
    streaming.

    Usage::

        pipeline = GenerationPipeline(
            comfyui_client=client,
            template_manager=tmgr,
            image_manager=img_mgr,
            prompt_builder=builder,
        )
        job_id = pipeline.start_generation(request)
        async for progress in pipeline.run_job(job_id):
            print(progress.stage, progress.message)
    """

    def __init__(
        self,
        *,
        comfyui_client: Any = None,
        template_manager: Any = None,
        image_manager: Any = None,
        prompt_builder: Any = None,
        max_queue_size: int = COMFYUI_MAX_QUEUE_SIZE,
    ) -> None:
        self._comfyui_client = comfyui_client
        self._template_manager = template_manager
        self._image_manager = image_manager
        self._prompt_builder = prompt_builder
        self._max_queue_size = max_queue_size
        self._jobs: dict[str, _JobState] = {}
        self._job_counter: int = 0

    # ── Properties ───────────────────────────────────────────

    @property
    def active_job_count(self) -> int:
        """Number of currently active (non-terminal) jobs."""
        return sum(
            1 for j in self._jobs.values()
            if j.stage in _ACTIVE_STATUSES
        )

    @property
    def max_queue_size(self) -> int:
        return self._max_queue_size

    # ── Start Generation ─────────────────────────────────────

    def start_generation(self, request: GenerationRequest) -> str:
        """Create a new generation job and return its ID.

        Raises:
            GenerationQueueFullError: If the queue is at capacity.
            GenerationValidationError: If the request is invalid.
        """
        # Enforce queue limit
        if self.active_job_count >= self._max_queue_size:
            raise GenerationQueueFullError(self._max_queue_size)

        # Validate template exists
        if self._template_manager is not None:
            from core.comfyui_client import TemplateNotFoundError
            try:
                self._template_manager.get(request.template_id)
            except TemplateNotFoundError:
                raise GenerationValidationError(
                    f"Template '{request.template_id}' not found."
                )

        # Generate job ID
        self._job_counter += 1
        job_id = f"GEN-{self._job_counter:04d}"

        # Create job state
        job = _JobState(job_id=job_id, request=request)
        self._jobs[job_id] = job

        # Prune old completed jobs
        self._prune_completed()

        return job_id

    def start_batch_generation(
        self,
        requests: list[GenerationRequest],
    ) -> list[str]:
        """Create multiple generation jobs from a batch of requests.

        All-or-nothing validation: if any request would push past the
        queue limit, no jobs are created.

        Args:
            requests: Up to 10 ``GenerationRequest`` objects.

        Returns:
            List of job IDs in the same order as the requests.

        Raises:
            GenerationQueueFullError: If there isn't room for the batch.
            GenerationValidationError: If batch is empty or too large.
        """
        if not requests:
            raise GenerationValidationError(
                "Batch generation requires at least one request."
            )
        if len(requests) > 10:
            raise GenerationValidationError(
                f"Batch size {len(requests)} exceeds maximum of 10."
            )

        # Check capacity for the entire batch
        available = self._max_queue_size - self.active_job_count
        if len(requests) > available:
            raise GenerationQueueFullError(self._max_queue_size)

        # Queue all jobs
        job_ids: list[str] = []
        for request in requests:
            job_id = self.start_generation(request)
            job_ids.append(job_id)

        return job_ids

    # ── Run Job ──────────────────────────────────────────────

    async def run_job(
        self,
        job_id: str,
    ) -> AsyncGenerator[GenerationProgress, None]:
        """Execute a generation job, yielding progress updates.

        This is the main pipeline coroutine. It:

        1. Generates a prompt via PromptBuilder
        2. Fills the workflow template with prompt + settings
        3. Queues the workflow to ComfyUI
        4. Polls for completion
        5. Downloads the result image
        6. Saves via ImageManager

        Yields:
            :class:`GenerationProgress` at each stage transition.

        Raises:
            GenerationNotFoundError: If the job ID does not exist.
        """
        job = self._get_job(job_id)

        try:
            # ── Stage 1: Generate Prompt ─────────────────────
            job.stage = "prompt_generating"
            job.progress_pct = 10
            job.message = "Generating image prompt..."
            yield job.to_progress()

            if job.cancelled:
                yield self._cancel(job)
                return

            positive, negative = await self._generate_prompt(job)
            job.prompt_positive = positive
            job.prompt_negative = negative

            # ── Stage 2: Fill Template ───────────────────────
            job.stage = "template_filling"
            job.progress_pct = 25
            job.message = "Preparing ComfyUI workflow..."
            yield job.to_progress()

            if job.cancelled:
                yield self._cancel(job)
                return

            filled_workflow = self._fill_template(job)

            # ── Stage 3: Queue to ComfyUI ────────────────────
            job.stage = "queued"
            job.progress_pct = 35
            job.message = "Submitting to ComfyUI..."
            yield job.to_progress()

            if job.cancelled:
                yield self._cancel(job)
                return

            prompt_id = await self._comfyui_client.queue_workflow(filled_workflow)
            job.prompt_id = prompt_id

            # ── Stage 4: Poll for completion ─────────────────
            job.stage = "running"
            job.progress_pct = 45
            job.message = "ComfyUI is generating the image..."
            yield job.to_progress()

            history = await self._poll_comfyui(job, prompt_id)

            if job.cancelled:
                yield self._cancel(job)
                return

            # ── Stage 5: Download image ──────────────────────
            job.stage = "downloading"
            job.progress_pct = 80
            job.message = "Downloading generated image..."
            yield job.to_progress()

            if job.cancelled:
                yield self._cancel(job)
                return

            image_data, output_filename = await self._download_image(
                history,
            )

            # ── Stage 6: Save to ImageManager ────────────────
            job.stage = "saving"
            job.progress_pct = 90
            job.message = "Saving image..."
            yield job.to_progress()

            image = self._save_image(job, image_data, output_filename)
            job.image_id = image.id

            # ── Stage 7: Complete ────────────────────────────
            job.stage = "completed"
            job.progress_pct = 100
            job.message = "Image generated successfully!"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            yield job.to_progress()

        except Exception as exc:
            job.stage = "failed"
            job.progress_pct = 0
            job.error = str(exc)
            job.message = f"Generation failed: {exc}"
            job.completed_at = datetime.now(timezone.utc).isoformat()
            yield job.to_progress()

    # ── Cancel Job ───────────────────────────────────────────

    def cancel_job(self, job_id: str) -> GenerationProgress:
        """Mark a job for cancellation.

        The job will be cancelled at the next stage transition.

        Raises:
            GenerationNotFoundError: If the job does not exist.
        """
        job = self._get_job(job_id)

        if job.stage in _TERMINAL_STATUSES:
            # Already finished — nothing to cancel
            return job.to_progress()

        job.cancelled = True
        return self._cancel(job)

    # ── Query Jobs ───────────────────────────────────────────

    def get_job(self, job_id: str) -> dict[str, Any]:
        """Get the current state of a generation job.

        Raises:
            GenerationNotFoundError: If the job does not exist.
        """
        return self._get_job(job_id).to_dict()

    def list_jobs(
        self,
        *,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        """List all tracked generation jobs.

        Args:
            active_only: If True, return only non-terminal jobs.
        """
        jobs = list(self._jobs.values())
        if active_only:
            jobs = [j for j in jobs if j.stage in _ACTIVE_STATUSES]
        # Sort by creation time (newest first)
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return [j.to_dict() for j in jobs]

    # ── Internal: Prompt Generation ──────────────────────────

    async def _generate_prompt(
        self,
        job: _JobState,
    ) -> tuple[str, str]:
        """Generate positive/negative prompts via PromptBuilder."""
        from core.prompt_builder import PromptRequest, get_style_preset

        req = job.request

        # Build the PromptBuilder request
        style_preset = None
        if req.style_preset_key:
            style_preset = get_style_preset(req.style_preset_key)

        prompt_request = PromptRequest.create(
            req.prompt_mode,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            member_name=req.member_name,
            user_prompt=req.user_prompt,
            style_preset=style_preset,
            participants=req.participants if req.participants else None,
        )

        result = await self._prompt_builder.generate(prompt_request)

        # For council_vote, result is a list — pick the selected one
        if isinstance(result, list):
            idx = req.selected_prompt_index
            if idx < 0 or idx >= len(result):
                idx = 0
            chosen = result[idx]
            return chosen.positive, chosen.negative
        else:
            return result.positive, result.negative

    # ── Internal: Template Filling ───────────────────────────

    def _fill_template(self, job: _JobState) -> dict[str, Any]:
        """Fill the workflow template with prompt + settings."""
        req = job.request

        values = {
            "prompt": job.prompt_positive,
            "negative": job.prompt_negative,
            "seed": str(req.seed),
            "width": str(req.width),
            "height": str(req.height),
            "entity_name": req.entity_id,
            "entity_type": req.entity_type,
        }

        return self._template_manager.fill_template(
            req.template_id, values,
        )

    # ── Internal: ComfyUI Polling ────────────────────────────

    async def _poll_comfyui(
        self,
        job: _JobState,
        prompt_id: str,
    ) -> dict[str, Any]:
        """Poll ComfyUI until the workflow completes."""
        import asyncio

        poll_interval = getattr(
            self._comfyui_client, '_poll_interval', 1.0,
        )
        max_attempts = getattr(
            self._comfyui_client, '_max_poll_attempts', 300,
        )

        for attempt in range(max_attempts):
            if job.cancelled:
                return {}

            history = await self._comfyui_client.get_history(prompt_id)

            if not history:
                # Update progress estimate during polling
                pct = min(45 + int((attempt / max_attempts) * 30), 75)
                job.progress_pct = pct
                await asyncio.sleep(poll_interval)
                continue

            # Check for error
            status = history.get("status", {})
            status_str = status.get("status_str", "")
            if status_str == "error":
                messages = status.get("messages", [])
                error_text = str(messages) if messages else "Unknown error"
                from core.comfyui_client import ComfyUIWorkflowError
                raise ComfyUIWorkflowError(
                    f"ComfyUI workflow failed: {error_text}",
                    prompt_id=prompt_id,
                )

            completed = status.get("completed", False)
            if completed:
                return history

            await asyncio.sleep(poll_interval)

        from core.comfyui_client import ComfyUIWorkflowError
        raise ComfyUIWorkflowError(
            f"Polling timed out for prompt_id '{prompt_id}'.",
            prompt_id=prompt_id,
        )

    # ── Internal: Image Download ─────────────────────────────

    async def _download_image(
        self,
        history: dict[str, Any],
    ) -> tuple[bytes, str]:
        """Download the first output image from ComfyUI history."""
        from core.comfyui_client import ComfyUIClient

        output_images = ComfyUIClient.extract_output_images(history)
        if not output_images:
            raise GenerationError(
                "No output images found in ComfyUI history."
            )

        # Download the first image
        first = output_images[0]
        image_data = await self._comfyui_client.download_image(
            first["filename"],
            subfolder=first.get("subfolder", ""),
            image_type=first.get("type", "output"),
        )

        return image_data, first["filename"]

    # ── Internal: Image Saving ───────────────────────────────

    def _save_image(
        self,
        job: _JobState,
        image_data: bytes,
        output_filename: str,
    ) -> Any:
        """Save the downloaded image via ImageManager."""
        req = job.request

        image = self._image_manager.save_image(
            image_data,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            original_filename=output_filename,
            prompt=job.prompt_positive,
            negative_prompt=job.prompt_negative,
            template_id=req.template_id,
            generation_job_id=job.job_id,
            width=req.width,
            height=req.height,
            metadata={
                "prompt_mode": req.prompt_mode,
                "style_preset": req.style_preset_key,
                "seed": req.seed,
                "member_name": req.member_name,
            },
        )
        return image

    # ── Internal: Helpers ────────────────────────────────────

    def _get_job(self, job_id: str) -> _JobState:
        """Look up a job by ID, raise if not found."""
        job = self._jobs.get(job_id)
        if job is None:
            raise GenerationNotFoundError(job_id)
        return job

    def _cancel(self, job: _JobState) -> GenerationProgress:
        """Mark a job as cancelled and return final progress."""
        job.stage = "cancelled"
        job.progress_pct = 0
        job.message = "Generation cancelled."
        job.cancelled = True
        job.completed_at = datetime.now(timezone.utc).isoformat()
        return job.to_progress()

    def _prune_completed(self) -> None:
        """Remove old completed jobs if we exceed the retention limit."""
        completed = [
            j for j in self._jobs.values()
            if j.stage in _TERMINAL_STATUSES
        ]
        if len(completed) <= _MAX_COMPLETED_JOBS:
            return
        # Sort by completion time, remove oldest
        completed.sort(key=lambda j: j.completed_at or "")
        to_remove = completed[: len(completed) - _MAX_COMPLETED_JOBS]
        for j in to_remove:
            del self._jobs[j.job_id]

    # ── Repr ─────────────────────────────────────────────────

    def __repr__(self) -> str:
        active = self.active_job_count
        total = len(self._jobs)
        return f"GenerationPipeline(active={active}, total={total})"
