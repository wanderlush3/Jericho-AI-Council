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


# ─── Web → API Format Conversion ─────────────────────────────


def is_web_format(workflow_json: dict[str, Any]) -> bool:
    """Detect whether a workflow dict is in ComfyUI's *web/graph* format.

    Web format has a ``nodes`` array and ``links`` array.  API format is
    a flat dict keyed by string node IDs, each with ``class_type``.
    """
    return isinstance(workflow_json.get("nodes"), list)


def convert_web_to_api_format(
    workflow_json: dict[str, Any],
) -> dict[str, Any]:
    """Convert a ComfyUI **web-format** workflow to **API format**.

    The web format stores a ``nodes`` list and a ``links`` list.
    The API format ComfyUI's ``POST /prompt`` expects is a flat dict::

        {
          "3": {"class_type": "KSampler", "inputs": {...}},
          "4": {"class_type": "EmptyLatentImage", "inputs": {...}},
          ...
        }

    This conversion resolves links into direct ``[node_id_str, slot]``
    input references and maps widget values to their named inputs.

    If the workflow contains **subgraph / component nodes** (identified
    by UUID-style ``type`` fields), those are expanded into top-level
    nodes with namespaced IDs.

    Raises:
        ComfyUIWorkflowError: If the workflow structure is malformed.
    """
    nodes = workflow_json.get("nodes", [])
    links = workflow_json.get("links", [])
    definitions = workflow_json.get("definitions", {})

    if not nodes:
        raise ComfyUIWorkflowError("Web-format workflow has no nodes.")

    # ── Build link lookup: link_id → (source_node_id, source_slot) ──
    link_map: dict[int, tuple[int, int]] = {}
    for link in links:
        # link format: [link_id, source_node, source_slot,
        #               target_node, target_slot, type_name]
        if isinstance(link, list) and len(link) >= 6:
            link_id, src_node, src_slot = int(link[0]), int(link[1]), int(link[2])
            link_map[link_id] = (src_node, src_slot)

    # ── Resolve subgraph definitions ──
    subgraph_defs: dict[str, dict[str, Any]] = {}
    for sg in definitions.get("subgraphs", []):
        sg_id = sg.get("id", "")
        if sg_id:
            subgraph_defs[sg_id] = sg

    # ── Convert each node ──
    api_format: dict[str, Any] = {}
    # Track subgraph nodes that need expansion
    subgraph_nodes: list[dict[str, Any]] = []

    for node in nodes:
        node_id = str(node.get("id", ""))
        node_type = node.get("type", "")

        if not node_id or not node_type:
            continue

        # Check if this is a subgraph/component node (UUID-style type)
        if node_type in subgraph_defs:
            subgraph_nodes.append(node)
            continue

        api_node = _convert_single_node(node, link_map)
        api_format[node_id] = api_node

    # ── Expand subgraph nodes ──
    for sg_node in subgraph_nodes:
        sg_type = sg_node["type"]
        sg_def = subgraph_defs[sg_type]
        expanded = _expand_subgraph(sg_node, sg_def, link_map)
        api_format.update(expanded)

    return api_format


_CONTROL_AFTER_GENERATE_VALUES = frozenset({
    "fixed", "increment", "decrement", "randomize", "last",
})
"""Values used by the hidden ``control_after_generate`` widget.

ComfyUI's frontend inserts a control widget after every ``INT`` seed
input (and similar RNG inputs).  This widget appears in
``widgets_values`` but is **not** listed in the node's ``inputs``
array, so we must skip it during conversion to avoid misaligning the
rest of the widget values.
"""


def _convert_single_node(
    node: dict[str, Any],
    link_map: dict[int, tuple[int, int]],
) -> dict[str, Any]:
    """Convert a single web-format node to API format.

    Resolves linked inputs to ``[source_node_str, source_slot]`` and
    maps ``widgets_values`` to their corresponding named widget inputs.

    **Hidden control widgets** — The ComfyUI frontend inserts invisible
    control widgets (e.g. ``control_after_generate`` with values like
    ``"randomize"``, ``"fixed"``, ``"increment"``, ``"decrement"``) into
    the ``widgets_values`` array after seed-type INT inputs.  These
    entries do NOT have a corresponding item in the ``inputs`` list.
    This function detects and skips them so that subsequent widget values
    are correctly aligned with their named inputs.

    **Connected widget inputs** — When a widget input is connected via a
    link, its value in ``widgets_values`` still occupies a slot (the
    default/last-used value), but the API format should use the link
    reference instead.  We must consume the slot to keep alignment but
    not set it in the output.
    """
    node_type = node.get("type", "")
    inputs_list = node.get("inputs", [])
    widget_values = list(node.get("widgets_values", []))

    api_inputs: dict[str, Any] = {}

    # ── Pass 1: Resolve connection inputs and collect widget inputs ──
    # ALL widget-type inputs are tracked in order (even those connected
    # via links) because they each consume a slot in widgets_values.
    all_widget_input_names: list[str] = []
    connected_via_link: set[str] = set()

    for inp in inputs_list:
        name = inp.get("name", "")
        if not name:
            continue

        link_id = inp.get("link")
        is_widget = "widget" in inp

        if link_id is not None and link_id in link_map:
            # Connected via a link — resolve to [node_id_str, slot]
            src_node, src_slot = link_map[link_id]
            api_inputs[name] = [str(src_node), src_slot]
            connected_via_link.add(name)
            # If this is also a widget input, it still occupies a
            # slot in widgets_values that we must consume.
            if is_widget:
                all_widget_input_names.append(name)
        elif is_widget:
            all_widget_input_names.append(name)
        # Else: unconnected non-widget input — skip (ComfyUI default)

    # ── Pass 2: Map widgets_values → widget input names ──
    # Walk through widgets_values, assigning each value to the next
    # expected widget input.  When we see a control_after_generate
    # string where we expected the next named widget input, skip it.
    widget_name_idx = 0
    for wv_idx in range(len(widget_values)):
        if widget_name_idx >= len(all_widget_input_names):
            break  # All widget inputs satisfied

        value = widget_values[wv_idx]

        # Check if this value is a control_after_generate entry.
        # These are string values like "randomize", "fixed", etc.
        # that appear after seed/INT widgets but have no corresponding
        # named input in the inputs list.
        if (
            isinstance(value, str)
            and value.lower() in _CONTROL_AFTER_GENERATE_VALUES
        ):
            # Peek at the expected input name — if it doesn't match
            # a seed-control name, this is a hidden control widget.
            expected_name = all_widget_input_names[widget_name_idx]
            # Only skip if the expected widget is NOT one that would
            # legitimately accept control values.
            if expected_name not in (
                "control_after_generate", "control_mode",
            ):
                continue  # Skip this hidden control widget value

        input_name = all_widget_input_names[widget_name_idx]
        widget_name_idx += 1

        # Only set the value if this input is NOT connected via a link
        # (connected inputs already have a [node_id, slot] reference).
        if input_name not in connected_via_link:
            api_inputs[input_name] = value

    return {
        "class_type": node_type,
        "inputs": api_inputs,
        "_meta": {"title": node.get("title", node_type)},
    }


def _expand_subgraph(
    sg_node: dict[str, Any],
    sg_def: dict[str, Any],
    parent_link_map: dict[int, tuple[int, int]],
) -> dict[str, Any]:
    """Expand a subgraph/component node into top-level API-format nodes.

    Internal nodes get IDs namespaced as ``{parent_id}:{internal_id}``.
    The input/output boundary nodes (``-10`` / ``-20``) are NOT emitted;
    instead their connections are threaded through to the internal nodes.
    """
    parent_id = str(sg_node.get("id", ""))
    parent_inputs = sg_node.get("inputs", [])
    sg_inputs_def = sg_def.get("inputs", [])
    sg_nodes = sg_def.get("nodes", [])
    sg_links = sg_def.get("links", [])

    if not sg_nodes:
        return {}

    # ── Map parent input slot index → source from parent links ──
    # Parent inputs are connected via the parent link map
    parent_input_sources: dict[int, tuple[str, int]] = {}
    for slot_idx, inp in enumerate(parent_inputs):
        link_id = inp.get("link")
        if link_id is not None and link_id in parent_link_map:
            src_node, src_slot = parent_link_map[link_id]
            parent_input_sources[slot_idx] = (str(src_node), src_slot)

    # ── Map subgraph input definitions to their slot on -10 ──
    # sg_inputs_def maps positional index to subgraph boundary
    input_node_outputs: dict[int, tuple[str, int]] = {}
    for slot_idx, sg_inp in enumerate(sg_inputs_def):
        if slot_idx in parent_input_sources:
            input_node_outputs[slot_idx] = parent_input_sources[slot_idx]

    # ── Build internal link map ──
    # Internal links use object format: {id, origin_id, origin_slot,
    #                                     target_id, target_slot, type}
    internal_link_map: dict[int, tuple[str, int]] = {}
    for link in sg_links:
        if isinstance(link, dict):
            link_id = link.get("id", 0)
            origin_id = link.get("origin_id", 0)
            origin_slot = link.get("origin_slot", 0)

            if origin_id == -10:
                # This comes from the subgraph input node — resolve
                # to the parent's source
                if origin_slot in input_node_outputs:
                    src = input_node_outputs[origin_slot]
                    internal_link_map[link_id] = src
                # else: drop — unconnected subgraph input
            else:
                # Regular internal link — namespace the origin ID
                namespaced = f"{parent_id}:{origin_id}"
                internal_link_map[link_id] = (namespaced, origin_slot)

    # ── Convert internal nodes ──
    result: dict[str, Any] = {}
    for node in sg_nodes:
        node_id = node.get("id")
        if node_id is None or node_id < 0:
            continue  # Skip boundary nodes

        namespaced_id = f"{parent_id}:{node_id}"
        api_node = _convert_single_node(node, internal_link_map)
        result[namespaced_id] = api_node

    return result


# ─── Standard Output Node Detection ──────────────────────────


# Node class_types whose return values populate the ``outputs`` dict
# in ComfyUI's ``/history`` response via the standard ``ui`` mechanism.
_STANDARD_OUTPUT_NODE_TYPES = frozenset({
    "SaveImage",
    "PreviewImage",
    "SaveAnimatedWEBP",
    "SaveAnimatedPNG",
    "SaveImageWebsocket",
})

# Node class_types that save images but do NOT populate ``outputs``.
# We look for an ``images`` input on these to find the image source.
_CUSTOM_SAVE_KEYWORDS = ("save", "preview")


def ensure_preview_output(workflow_json: dict[str, Any]) -> dict[str, Any]:
    """Ensure the workflow has a standard output node for image retrieval.

    Many custom ComfyUI save nodes (e.g. ``Save Image (LoraManager)``) do
    not populate the ``outputs`` dict in ComfyUI's ``/history`` response.
    When Jericho's pipeline polls history, it finds an empty ``outputs``
    and can't download the image.

    This function detects whether the workflow lacks a standard output
    node (``SaveImage`` or ``PreviewImage``).  If so, it finds the image
    source from whatever custom save node is present and injects a
    ``PreviewImage`` node connected to the same source.

    The injected node uses a high numeric ID (``_jericho_preview``) to
    avoid collisions with existing nodes.

    Args:
        workflow_json: API-format workflow dict (node-id → node).

    Returns:
        The workflow dict, potentially with an added ``PreviewImage`` node.
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    # Check if any standard output node already exists
    for node_id, node in workflow_json.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        if class_type in _STANDARD_OUTPUT_NODE_TYPES:
            _log.debug(
                "Workflow already has standard output node %s (%s)",
                node_id, class_type,
            )
            return workflow_json

    # No standard output node — find a custom save/preview node with
    # an ``images`` input to discover the image source.
    image_source: list[str | int] | None = None
    save_node_class = ""

    for node_id, node in workflow_json.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type", "")
        ct_lower = class_type.lower()
        if not any(kw in ct_lower for kw in _CUSTOM_SAVE_KEYWORDS):
            continue

        inputs = node.get("inputs", {})
        images_input = inputs.get("images")
        if isinstance(images_input, list) and len(images_input) == 2:
            image_source = images_input
            save_node_class = class_type
            break

    if image_source is None:
        # No image-producing save node found anywhere — look for any
        # node that outputs IMAGE and has no downstream consumer.
        # As a last resort we can't do anything.
        _log.warning(
            "Workflow has no standard output node and no custom save "
            "node with an 'images' input.  Image retrieval may fail.",
        )
        return workflow_json

    # Generate a unique high node ID to avoid collisions
    existing_numeric_ids = []
    for nid in workflow_json:
        # Handle namespaced IDs like "13:59"
        parts = nid.split(":")
        for part in parts:
            try:
                existing_numeric_ids.append(int(part))
            except ValueError:
                pass
    preview_id = str(max(existing_numeric_ids, default=0) + 9000)

    # Inject PreviewImage node
    workflow_json[preview_id] = {
        "class_type": "PreviewImage",
        "inputs": {
            "images": image_source,
        },
        "_meta": {"title": "Jericho Preview (auto-injected)"},
    }

    _log.info(
        "Injected PreviewImage node %s (source from %s node, "
        "images input=%s) for reliable history output retrieval.",
        preview_id, save_node_class, image_source,
    )

    return workflow_json


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

        # Auto-convert web-format workflows to API format
        if is_web_format(workflow_json):
            workflow_json = convert_web_to_api_format(workflow_json)

        # Ensure we have a standard output node for reliable image retrieval
        workflow_json = ensure_preview_output(workflow_json)

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

        Searches for ``images``, ``gifs``, and ``videos`` keys in each
        node's output — different ComfyUI nodes use different keys.

        Returns:
            List of dicts with ``filename``, ``subfolder``, and ``type`` keys.
        """
        import logging as _logging
        _log = _logging.getLogger(__name__)

        outputs = history.get("outputs", {})
        images: list[dict[str, str]] = []

        _log.debug(
            "extract_output_images: %d output nodes, node IDs: %s",
            len(outputs), list(outputs.keys()),
        )

        # ComfyUI nodes may output under different keys
        _IMAGE_OUTPUT_KEYS = ("images", "gifs", "videos")

        for node_id, node_output in outputs.items():
            _log.debug(
                "  node %s output keys: %s",
                node_id, list(node_output.keys()),
            )
            for output_key in _IMAGE_OUTPUT_KEYS:
                for img in node_output.get(output_key, []):
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
