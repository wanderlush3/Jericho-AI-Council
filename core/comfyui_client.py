"""
Jericho — ComfyUI Client & Connection Manager (F-037a)

HTTP client for ComfyUI's REST API with workflow template management.

ComfyUI exposes a local HTTP API (default ``127.0.0.1:8188``) that accepts
workflow JSON via ``POST /prompt``, reports status via ``GET /history/{id}``,
and serves generated images via ``GET /view``.

This module provides:

- **ComfyUIClient** — async HTTP client for queueing workflows, polling
  status, downloading images, and testing the connection.

- **WorkflowTemplateManager** — filesystem-backed CRUD for user-uploaded
  ComfyUI workflow templates (``TPL-XXXX.json``).  Detects ``%placeholder%``
  tokens and fills them before submission.

Storage: one JSON file per template in ``data/comfyui/templates/``.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    COMFYUI_DEFAULT_HOST,
    COMFYUI_DEFAULT_PORT,
    COMFYUI_TEMPLATES_DIR,
    COMFYUI_MAX_QUEUE_SIZE,
)
from core.utils import atomic_write


# ─── Exceptions ────────────────────────────────────────────────


class ComfyUIError(Exception):
    """Base exception for ComfyUI integration errors."""


class ComfyUIConnectionError(ComfyUIError):
    """Raised when the ComfyUI server cannot be reached."""

    def __init__(self, message: str, host: str = "", port: int = 0) -> None:
        self.host = host
        self.port = port
        super().__init__(message)


class ComfyUIWorkflowError(ComfyUIError):
    """Raised when a workflow fails to execute."""

    def __init__(self, message: str, prompt_id: str = "") -> None:
        self.prompt_id = prompt_id
        super().__init__(message)


class TemplateError(ComfyUIError):
    """Base exception for template-related errors."""


class TemplateNotFoundError(TemplateError):
    """Raised when a template ID is not found on disk."""

    def __init__(self, template_id: str) -> None:
        self.template_id = template_id
        super().__init__(f"Template not found: '{template_id}'")


class TemplateValidationError(TemplateError):
    """Raised when template data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


# ─── Placeholder Tokens ──────────────────────────────────────

# Tokens that can appear in workflow JSON as %token_name%
PLACEHOLDER_PATTERN = re.compile(r"%([a-z_]+)%")

KNOWN_PLACEHOLDERS = frozenset({
    "prompt",
    "negative",
    "seed",
    "width",
    "height",
    "entity_name",
    "entity_type",
    "steps",
    "cfg",
    "sampler",
    "scheduler",
    "batch_size",
})


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class ComfyUIConfig:
    """Connection configuration for a ComfyUI server."""

    host: str = COMFYUI_DEFAULT_HOST
    port: int = COMFYUI_DEFAULT_PORT

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComfyUIConfig:
        return cls(
            host=data.get("host", COMFYUI_DEFAULT_HOST),
            port=int(data.get("port", COMFYUI_DEFAULT_PORT)),
        )

    @classmethod
    def create(
        cls,
        host: str = COMFYUI_DEFAULT_HOST,
        port: int = COMFYUI_DEFAULT_PORT,
    ) -> ComfyUIConfig:
        """Factory with validation."""
        errors: list[str] = []
        if not host.strip():
            errors.append("Host is required.")
        if port < 1 or port > 65535:
            errors.append(f"Port must be between 1 and 65535, got {port}.")
        if errors:
            raise TemplateValidationError(errors)
        return cls(host=host.strip(), port=port)


@dataclass(frozen=True)
class WorkflowTemplate:
    """A stored ComfyUI workflow template with placeholder metadata."""

    id: str
    name: str
    description: str
    workflow_json: dict[str, Any]
    placeholders: list[str] = field(default_factory=list)
    entity_type: str = ""        # e.g. "character", "location", or "" for general
    author: str = ""
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkflowTemplate:
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            workflow_json=data.get("workflow_json", {}),
            placeholders=data.get("placeholders", []),
            entity_type=data.get("entity_type", ""),
            author=data.get("author", ""),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        id: str,
        name: str,
        description: str = "",
        workflow_json: dict[str, Any],
        entity_type: str = "",
        author: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowTemplate:
        """Factory that auto-detects placeholders and sets timestamps."""
        now = datetime.now(timezone.utc).isoformat()
        placeholders = detect_placeholders(workflow_json)
        return cls(
            id=id,
            name=name,
            description=description,
            workflow_json=workflow_json,
            placeholders=sorted(placeholders),
            entity_type=entity_type,
            author=author,
            created_at=now,
            updated_at=now,
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class GenerationJob:
    """Tracks a single image generation request submitted to ComfyUI."""

    job_id: str               # Jericho job ID (GEN-XXXX)
    prompt_id: str             # ComfyUI prompt_id from POST /prompt
    template_id: str
    entity_type: str = ""
    entity_id: str = ""
    status: str = "queued"     # queued | running | completed | failed
    output_filename: str = ""  # filename from ComfyUI /history
    error: str = ""
    created_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GenerationJob:
        return cls(
            job_id=data["job_id"],
            prompt_id=data["prompt_id"],
            template_id=data.get("template_id", ""),
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id", ""),
            status=data.get("status", "queued"),
            output_filename=data.get("output_filename", ""),
            error=data.get("error", ""),
            created_at=data.get("created_at", ""),
            completed_at=data.get("completed_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        *,
        job_id: str,
        prompt_id: str,
        template_id: str,
        entity_type: str = "",
        entity_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> GenerationJob:
        """Factory with timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            job_id=job_id,
            prompt_id=prompt_id,
            template_id=template_id,
            entity_type=entity_type,
            entity_id=entity_id,
            status="queued",
            created_at=now,
            metadata=metadata or {},
        )


# ─── Placeholder Utilities ───────────────────────────────────


def detect_placeholders(workflow_json: dict[str, Any]) -> list[str]:
    """Scan a workflow JSON structure for ``%placeholder%`` tokens.

    Returns a sorted, deduplicated list of placeholder names found.
    """
    found: set[str] = set()
    _scan_value(workflow_json, found)
    return sorted(found)


def _scan_value(value: Any, found: set[str]) -> None:
    """Recursively scan any JSON-compatible value for placeholder tokens."""
    if isinstance(value, str):
        for match in PLACEHOLDER_PATTERN.finditer(value):
            found.add(match.group(1))
    elif isinstance(value, dict):
        for v in value.values():
            _scan_value(v, found)
    elif isinstance(value, list):
        for item in value:
            _scan_value(item, found)


def fill_placeholders(
    workflow_json: dict[str, Any],
    values: dict[str, str],
) -> dict[str, Any]:
    """Return a deep copy of *workflow_json* with placeholders replaced.

    Only string values are touched.  ``%placeholder%`` tokens in *values*
    are replaced with the corresponding value string.  Tokens not present
    in *values* are left as-is.
    """
    return _fill_value(workflow_json, values)


def _fill_value(value: Any, values: dict[str, str]) -> Any:
    """Recursively replace placeholder tokens in a JSON-compatible value."""
    if isinstance(value, str):
        result = value
        for token, replacement in values.items():
            result = result.replace(f"%{token}%", str(replacement))
        return result
    elif isinstance(value, dict):
        return {k: _fill_value(v, values) for k, v in value.items()}
    elif isinstance(value, list):
        return [_fill_value(item, values) for item in value]
    else:
        return value


# ─── ComfyUI Client ──────────────────────────────────────────


class ComfyUIClient:
    """Async HTTP client for the ComfyUI REST API.

    Usage::

        config = ComfyUIConfig.create(host="127.0.0.1", port=8188)
        async with ComfyUIClient(config) as client:
            ok = await client.test_connection()
            prompt_id = await client.queue_workflow(filled_json)
            result = await client.poll_status(prompt_id)
            image_bytes = await client.download_image(result["filename"])
    """

    def __init__(
        self,
        config: ComfyUIConfig | None = None,
        *,
        timeout: float = 30.0,
        poll_interval: float = 1.0,
        max_poll_attempts: int = 300,
    ) -> None:
        self._config = config or ComfyUIConfig()
        self._timeout = timeout
        self._poll_interval = poll_interval
        self._max_poll_attempts = max_poll_attempts
        self._client: Any = None  # httpx.AsyncClient, lazily created

    # ── Context Manager ──────────────────────────────────────

    async def __aenter__(self) -> ComfyUIClient:
        import httpx
        self._client = httpx.AsyncClient(
            base_url=self._config.base_url,
            timeout=self._timeout,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Properties ───────────────────────────────────────────

    @property
    def config(self) -> ComfyUIConfig:
        return self._config

    @property
    def base_url(self) -> str:
        return self._config.base_url

    # ── Connection Test ──────────────────────────────────────

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection to ComfyUI via ``GET /system_stats``.

        Returns:
            System stats dict from ComfyUI on success.

        Raises:
            ComfyUIConnectionError: If the server is unreachable.
        """
        self._ensure_client()
        try:
            response = await self._client.get("/system_stats")
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise ComfyUIConnectionError(
                f"Cannot connect to ComfyUI at {self._config.base_url}: {exc}",
                host=self._config.host,
                port=self._config.port,
            )

    # ── Queue Workflow ───────────────────────────────────────

    async def queue_workflow(
        self,
        workflow_json: dict[str, Any],
        *,
        client_id: str | None = None,
    ) -> str:
        """Submit a workflow to ComfyUI for execution.

        Args:
            workflow_json: The filled workflow JSON (API format).
            client_id: Optional client identifier for WebSocket routing.

        Returns:
            The ``prompt_id`` assigned by ComfyUI.

        Raises:
            ComfyUIConnectionError: If the server is unreachable.
            ComfyUIWorkflowError: If the server rejects the workflow.
        """
        self._ensure_client()
        payload: dict[str, Any] = {"prompt": workflow_json}
        if client_id:
            payload["client_id"] = client_id

        try:
            response = await self._client.post("/prompt", json=payload)
        except Exception as exc:
            raise ComfyUIConnectionError(
                f"Failed to queue workflow: {exc}",
                host=self._config.host,
                port=self._config.port,
            )

        if response.status_code != 200:
            body = response.text
            raise ComfyUIWorkflowError(
                f"ComfyUI rejected workflow (HTTP {response.status_code}): {body}"
            )

        data = response.json()
        prompt_id = data.get("prompt_id", "")
        if not prompt_id:
            raise ComfyUIWorkflowError(
                "ComfyUI response missing 'prompt_id'."
            )
        return prompt_id

    # ── Poll Status ──────────────────────────────────────────

    async def get_history(self, prompt_id: str) -> dict[str, Any]:
        """Fetch the execution history for a single prompt.

        Returns:
            The history entry dict for this prompt_id, or empty dict
            if the prompt hasn't completed yet.

        Raises:
            ComfyUIConnectionError: If the server is unreachable.
        """
        self._ensure_client()
        try:
            response = await self._client.get(f"/history/{prompt_id}")
            response.raise_for_status()
        except Exception as exc:
            raise ComfyUIConnectionError(
                f"Failed to get history for {prompt_id}: {exc}",
                host=self._config.host,
                port=self._config.port,
            )
        data = response.json()
        return data.get(prompt_id, {})

    async def poll_until_complete(
        self,
        prompt_id: str,
    ) -> dict[str, Any]:
        """Poll ``GET /history/{prompt_id}`` until execution completes.

        Returns:
            The completed history entry with output information.

        Raises:
            ComfyUIConnectionError: If the server is unreachable.
            ComfyUIWorkflowError: If the workflow fails on the server or
                polling times out.
        """
        import asyncio

        for attempt in range(self._max_poll_attempts):
            history = await self.get_history(prompt_id)

            if not history:
                # Not yet in history — still executing
                await asyncio.sleep(self._poll_interval)
                continue

            # Check for execution status
            status = history.get("status", {})
            completed = status.get("completed", False)
            status_str = status.get("status_str", "")

            if status_str == "error":
                messages = status.get("messages", [])
                error_text = str(messages) if messages else "Unknown error"
                raise ComfyUIWorkflowError(
                    f"Workflow execution failed: {error_text}",
                    prompt_id=prompt_id,
                )

            if completed:
                return history

            await asyncio.sleep(self._poll_interval)

        raise ComfyUIWorkflowError(
            f"Polling timed out after {self._max_poll_attempts} attempts "
            f"for prompt_id '{prompt_id}'.",
            prompt_id=prompt_id,
        )

    # ── Extract Output Filenames ─────────────────────────────

    @staticmethod
    def extract_output_images(history: dict[str, Any]) -> list[dict[str, str]]:
        """Extract output image metadata from a completed history entry.

        Returns:
            List of dicts with ``filename``, ``subfolder``, and ``type`` keys.
        """
        outputs = history.get("outputs", {})
        images: list[dict[str, str]] = []
        for _node_id, node_output in outputs.items():
            for img in node_output.get("images", []):
                images.append({
                    "filename": img.get("filename", ""),
                    "subfolder": img.get("subfolder", ""),
                    "type": img.get("type", "output"),
                })
        return images

    # ── Download Image ───────────────────────────────────────

    async def download_image(
        self,
        filename: str,
        *,
        subfolder: str = "",
        image_type: str = "output",
    ) -> bytes:
        """Download a generated image from ComfyUI via ``GET /view``.

        Args:
            filename: The image filename from the history output.
            subfolder: Subfolder within ComfyUI's output directory.
            image_type: Image type (usually ``"output"``).

        Returns:
            Raw image bytes.

        Raises:
            ComfyUIConnectionError: If the download fails.
        """
        self._ensure_client()
        params = {
            "filename": filename,
            "subfolder": subfolder,
            "type": image_type,
        }
        try:
            response = await self._client.get("/view", params=params)
            response.raise_for_status()
            return response.content
        except Exception as exc:
            raise ComfyUIConnectionError(
                f"Failed to download image '{filename}': {exc}",
                host=self._config.host,
                port=self._config.port,
            )

    # ── Upload Image ─────────────────────────────────────────

    async def upload_image(
        self,
        image_data: bytes,
        filename: str,
        *,
        image_type: str = "input",
        overwrite: bool = True,
    ) -> dict[str, Any]:
        """Upload an image to ComfyUI for use as input.

        Returns:
            The response dict from ComfyUI.

        Raises:
            ComfyUIConnectionError: If the upload fails.
        """
        self._ensure_client()
        try:
            files = {"image": (filename, image_data, "image/png")}
            data = {"type": image_type, "overwrite": str(overwrite).lower()}
            response = await self._client.post(
                "/upload/image", files=files, data=data,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            raise ComfyUIConnectionError(
                f"Failed to upload image '{filename}': {exc}",
                host=self._config.host,
                port=self._config.port,
            )

    # ── Internal ─────────────────────────────────────────────

    def _ensure_client(self) -> None:
        """Raise if the client was not entered as a context manager."""
        if self._client is None:
            raise ComfyUIError(
                "ComfyUIClient must be used as an async context manager: "
                "async with ComfyUIClient() as client: ..."
            )

    def __repr__(self) -> str:
        return f"ComfyUIClient(url={self._config.base_url!r})"


# ─── Workflow Template Manager ────────────────────────────────


class WorkflowTemplateManager:
    """Filesystem-backed CRUD manager for ComfyUI workflow templates.

    Each template is stored as ``TPL-XXXX.json`` in the templates directory.

    Usage::

        mgr = WorkflowTemplateManager()
        tpl = mgr.create("My Workflow", workflow_json=raw_json)
        filled = mgr.fill_template(tpl.id, {"prompt": "a cat", "seed": "42"})
        print(tpl.placeholders)   # ['prompt', 'seed', ...]
    """

    _ID_PATTERN = re.compile(r"^TPL-(\d{4})\.json$")

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._dir = templates_dir or COMFYUI_TEMPLATES_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Properties ───────────────────────────────────────────

    @property
    def directory(self) -> Path:
        return self._dir

    # ── Create ───────────────────────────────────────────────

    def create(
        self,
        name: str,
        *,
        description: str = "",
        workflow_json: dict[str, Any],
        entity_type: str = "",
        author: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowTemplate:
        """Create a new workflow template.

        Raises:
            TemplateValidationError: If required fields are missing
                or workflow_json is empty.
        """
        errors: list[str] = []
        if not name.strip():
            errors.append("Template name is required.")
        if not workflow_json:
            errors.append("Workflow JSON is required.")
        if errors:
            raise TemplateValidationError(errors)

        template_id = self._next_id()
        template = WorkflowTemplate.create(
            id=template_id,
            name=name.strip(),
            description=description.strip() if description else "",
            workflow_json=workflow_json,
            entity_type=entity_type.strip() if entity_type else "",
            author=author.strip() if author else "",
            metadata=metadata,
        )
        self._save(template)
        return template

    # ── Read ─────────────────────────────────────────────────

    def get(self, template_id: str) -> WorkflowTemplate:
        """Load a single template by ID."""
        filepath = self._filepath(template_id)
        if not filepath.exists():
            raise TemplateNotFoundError(template_id)
        return self._load(filepath)

    def list_templates(
        self,
        *,
        entity_type: str | None = None,
        author: str | None = None,
    ) -> list[WorkflowTemplate]:
        """List templates with optional filters."""
        templates: list[WorkflowTemplate] = []
        for filepath in sorted(self._dir.glob("TPL-*.json")):
            try:
                tpl = self._load(filepath)
            except (json.JSONDecodeError, KeyError):
                continue  # skip corrupt files
            if entity_type is not None and tpl.entity_type != entity_type:
                continue
            if author is not None and tpl.author.lower() != author.lower():
                continue
            templates.append(tpl)
        return templates

    def has_template(self, template_id: str) -> bool:
        """Check if a template exists."""
        return self._filepath(template_id).exists()

    # ── Update ───────────────────────────────────────────────

    _MUTABLE_FIELDS = {
        "name", "description", "workflow_json",
        "entity_type", "author", "metadata",
    }

    def update(self, template_id: str, **fields: Any) -> WorkflowTemplate:
        """Update mutable fields on a template.

        If ``workflow_json`` is updated, placeholders are re-detected.
        """
        immutable = {"id", "created_at", "placeholders"}
        bad = set(fields.keys()) & immutable
        if bad:
            raise TemplateValidationError(
                f"Cannot update immutable field(s): {', '.join(sorted(bad))}"
            )

        unknown = set(fields.keys()) - self._MUTABLE_FIELDS
        if unknown:
            raise TemplateValidationError(
                f"Unknown field(s): {', '.join(sorted(unknown))}"
            )

        template = self.get(template_id)
        now = datetime.now(timezone.utc).isoformat()
        data = template.to_dict()
        data.update(fields)
        data["updated_at"] = now

        # Re-detect placeholders if workflow changed
        if "workflow_json" in fields:
            data["placeholders"] = detect_placeholders(data["workflow_json"])

        updated = WorkflowTemplate.from_dict(data)
        self._save(updated)
        return updated

    # ── Delete ───────────────────────────────────────────────

    def delete(self, template_id: str) -> None:
        """Delete a template from disk."""
        filepath = self._filepath(template_id)
        if not filepath.exists():
            raise TemplateNotFoundError(template_id)
        filepath.unlink()

    # ── Fill Template ────────────────────────────────────────

    def fill_template(
        self,
        template_id: str,
        values: dict[str, str],
    ) -> dict[str, Any]:
        """Load a template, fill its placeholders, and return the result.

        Args:
            template_id: The template to fill.
            values: Dict mapping placeholder names to replacement values.

        Returns:
            The filled workflow JSON ready for submission to ComfyUI.
        """
        template = self.get(template_id)
        return fill_placeholders(template.workflow_json, values)

    def get_unfilled_placeholders(
        self,
        template_id: str,
        values: dict[str, str],
    ) -> list[str]:
        """Return placeholders that are NOT satisfied by *values*.

        Useful for UI validation before submission.
        """
        template = self.get(template_id)
        return [p for p in template.placeholders if p not in values]

    # ── Internal ─────────────────────────────────────────────

    def _filepath(self, template_id: str) -> Path:
        return self._dir / f"{template_id}.json"

    def _save(self, template: WorkflowTemplate) -> None:
        payload = json.dumps(template.to_dict(), indent=2, ensure_ascii=False)
        atomic_write(self._filepath(template.id), payload + "\n")

    def _load(self, filepath: Path) -> WorkflowTemplate:
        text = filepath.read_text(encoding="utf-8")
        data = json.loads(text)
        return WorkflowTemplate.from_dict(data)

    def _next_id(self) -> str:
        """Scan existing files and return the next sequential TPL-XXXX id."""
        max_num = 0
        for filepath in self._dir.glob("TPL-*.json"):
            match = self._ID_PATTERN.match(filepath.name)
            if match:
                max_num = max(max_num, int(match.group(1)))
        return f"TPL-{max_num + 1:04d}"

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("TPL-*.json")))
        return f"WorkflowTemplateManager(templates={count}, dir={self._dir})"
