"""
Jericho — Prompt Generation Engine (F-037c)

Multi-mode LLM-driven prompt construction for image generation.

Supports five generation modes:

- **council_vote** — Multiple council members each generate a prompt;
  the operator picks (or the council votes on) the best one.
- **character** — A specific character or council member generates
  the prompt in their style and voice.
- **system** — A generic "image prompt expert" system prompt with no
  personality injection.
- **user_refined** — The operator writes a base prompt and a character
  enhances / refines it.
- **raw_user** — The operator provides the exact prompt text — no LLM
  involvement at all.

Each mode produces a :class:`PromptResult` containing positive and
(optionally) negative prompt strings, plus metadata about the generation.

Usage::

    builder = PromptBuilder(api_client=client, registry=registry)
    result = await builder.generate(request)
    print(result.positive)
    print(result.negative)
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.settings import (
    COMFYUI_TEMPLATES_DIR,
)


# ─── Exceptions ────────────────────────────────────────────────


class PromptError(Exception):
    """Base exception for prompt generation errors."""


class PromptValidationError(PromptError):
    """Raised when a prompt request or preset fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


# ─── Constants ─────────────────────────────────────────────────


PROMPT_MODES = frozenset({
    "council_vote",
    "character",
    "system",
    "user_refined",
    "raw_user",
})

VALID_ENTITY_TYPES = frozenset({
    "character",
    "location",
    "item",
    "store",
    "council_member",
})


# ─── Data Models ───────────────────────────────────────────────


@dataclass(frozen=True)
class StylePreset:
    """A named style preset with positive/negative prompt fragments.

    Style presets are injected into the LLM prompt as guidance for the
    visual style.  The ``positive_suffix`` is appended to the generated
    positive prompt; ``negative_prefix`` is prepended to the generated
    negative prompt.
    """

    name: str
    description: str = ""
    positive_suffix: str = ""
    negative_prefix: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StylePreset:
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            positive_suffix=data.get("positive_suffix", ""),
            negative_prefix=data.get("negative_prefix", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        name: str,
        *,
        description: str = "",
        positive_suffix: str = "",
        negative_prefix: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> StylePreset:
        """Factory with validation."""
        if not name.strip():
            raise PromptValidationError("Style preset name is required.")
        return cls(
            name=name.strip(),
            description=description.strip(),
            positive_suffix=positive_suffix.strip(),
            negative_prefix=negative_prefix.strip(),
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class PromptRequest:
    """Input for a prompt generation call.

    Attributes:
        mode: One of the five generation modes.
        entity_type: The type of entity to generate for (character, location, etc.).
        entity_id: The ID of the entity (e.g. ``CH-0001``).
        member_name: Council member or character name (for ``character`` mode).
        user_prompt: User-supplied prompt text (for ``user_refined`` and ``raw_user``).
        style_preset: Optional style preset to apply.
        participants: List of member names (for ``council_vote`` mode).
        context_hint: Optional extra context to inject into the LLM prompt.
        metadata: Arbitrary metadata to pass through.
    """

    mode: str
    entity_type: str = ""
    entity_id: str = ""
    member_name: str = ""
    user_prompt: str = ""
    style_preset: StylePreset | None = None
    participants: list[str] = field(default_factory=list)
    context_hint: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.style_preset is not None:
            d["style_preset"] = self.style_preset.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptRequest:
        preset = None
        if data.get("style_preset"):
            preset = StylePreset.from_dict(data["style_preset"])
        return cls(
            mode=data["mode"],
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id", ""),
            member_name=data.get("member_name", ""),
            user_prompt=data.get("user_prompt", ""),
            style_preset=preset,
            participants=data.get("participants", []),
            context_hint=data.get("context_hint", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        mode: str,
        *,
        entity_type: str = "",
        entity_id: str = "",
        member_name: str = "",
        user_prompt: str = "",
        style_preset: StylePreset | None = None,
        participants: list[str] | None = None,
        context_hint: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PromptRequest:
        """Factory with validation."""
        errors: list[str] = []
        if mode not in PROMPT_MODES:
            errors.append(
                f"Invalid mode '{mode}' — must be one of {sorted(PROMPT_MODES)}"
            )
        if mode == "character" and not member_name.strip():
            errors.append("member_name is required for 'character' mode.")
        if mode == "user_refined" and not user_prompt.strip():
            errors.append("user_prompt is required for 'user_refined' mode.")
        if mode == "user_refined" and not member_name.strip():
            errors.append("member_name is required for 'user_refined' mode.")
        if mode == "raw_user" and not user_prompt.strip():
            errors.append("user_prompt is required for 'raw_user' mode.")
        if mode == "council_vote":
            effective_participants = participants or []
            if len(effective_participants) < 2:
                errors.append(
                    "At least 2 participants required for 'council_vote' mode."
                )
        if errors:
            raise PromptValidationError(errors)
        return cls(
            mode=mode,
            entity_type=entity_type.strip(),
            entity_id=entity_id.strip(),
            member_name=member_name.strip(),
            user_prompt=user_prompt.strip() if user_prompt else "",
            style_preset=style_preset,
            participants=participants or [],
            context_hint=context_hint.strip() if context_hint else "",
            metadata=metadata or {},
        )


@dataclass(frozen=True)
class PromptResult:
    """Output of a prompt generation call.

    Attributes:
        positive: The positive prompt for image generation.
        negative: The negative prompt (things to avoid).
        mode: The generation mode used.
        member_name: Which member/character generated it (empty for system/raw).
        style_preset_name: Name of the style preset applied (if any).
        entity_type: The entity type context was built from.
        entity_id: The entity ID context was built from.
        raw_llm_response: The full LLM response text (empty for raw_user).
        created_at: ISO timestamp of generation.
        metadata: Pass-through metadata from request plus generation info.
    """

    positive: str
    negative: str = ""
    mode: str = ""
    member_name: str = ""
    style_preset_name: str = ""
    entity_type: str = ""
    entity_id: str = ""
    raw_llm_response: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PromptResult:
        return cls(
            positive=data["positive"],
            negative=data.get("negative", ""),
            mode=data.get("mode", ""),
            member_name=data.get("member_name", ""),
            style_preset_name=data.get("style_preset_name", ""),
            entity_type=data.get("entity_type", ""),
            entity_id=data.get("entity_id", ""),
            raw_llm_response=data.get("raw_llm_response", ""),
            created_at=data.get("created_at", ""),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def create(
        cls,
        positive: str,
        *,
        negative: str = "",
        mode: str = "",
        member_name: str = "",
        style_preset_name: str = "",
        entity_type: str = "",
        entity_id: str = "",
        raw_llm_response: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> PromptResult:
        """Factory with timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            positive=positive,
            negative=negative,
            mode=mode,
            member_name=member_name,
            style_preset_name=style_preset_name,
            entity_type=entity_type,
            entity_id=entity_id,
            raw_llm_response=raw_llm_response,
            created_at=now,
            metadata=metadata or {},
        )


# ─── Built-in Style Presets ───────────────────────────────────


DEFAULT_STYLE_PRESETS: dict[str, StylePreset] = {
    "fantasy_art": StylePreset(
        name="Fantasy Art",
        description="High-fantasy illustration with rich detail and magical atmosphere",
        positive_suffix="fantasy art, highly detailed, intricate, magical, epic lighting, painterly style",
        negative_prefix="photo, photograph, realistic, selfie, blurry, low quality, bad anatomy",
    ),
    "anime": StylePreset(
        name="Anime",
        description="Japanese anime / manga visual style",
        positive_suffix="anime style, manga, cel shading, clean lines, vibrant colors",
        negative_prefix="realistic, photo, western cartoon, 3d render, blurry, low quality",
    ),
    "realistic": StylePreset(
        name="Realistic",
        description="Photorealistic rendering with natural lighting",
        positive_suffix="photorealistic, 8k, highly detailed, natural lighting, sharp focus, professional photography",
        negative_prefix="cartoon, anime, drawing, painting, illustration, blurry, low quality, bad anatomy",
    ),
    "oil_painting": StylePreset(
        name="Oil Painting",
        description="Classical oil painting with rich textures and warm tones",
        positive_suffix="oil painting, classical art, rich textures, warm tones, masterwork, fine art",
        negative_prefix="photo, digital art, anime, cartoon, low quality, blurry",
    ),
    "watercolor": StylePreset(
        name="Watercolor",
        description="Soft watercolor painting with gentle washes and organic edges",
        positive_suffix="watercolor painting, soft washes, organic edges, gentle colors, artistic, delicate",
        negative_prefix="photo, digital art, sharp lines, anime, 3d render, low quality",
    ),
    "pixel_art": StylePreset(
        name="Pixel Art",
        description="Retro pixel art style with limited color palette",
        positive_suffix="pixel art, retro game style, limited palette, 16-bit, clean pixels",
        negative_prefix="realistic, photo, smooth gradients, high resolution, blurry",
    ),
    "concept_art": StylePreset(
        name="Concept Art",
        description="Professional concept art with dynamic composition",
        positive_suffix="concept art, professional illustration, dynamic composition, dramatic lighting, artstation",
        negative_prefix="photo, amateur, blurry, low quality, bad anatomy, deformed",
    ),
    "dark_fantasy": StylePreset(
        name="Dark Fantasy",
        description="Grim, moody dark fantasy with horror undertones",
        positive_suffix="dark fantasy, grim, moody atmosphere, gothic, ominous lighting, dramatic shadows",
        negative_prefix="bright, cheerful, cartoon, anime, cute, low quality, blurry",
    ),
}


def get_style_preset(name: str) -> StylePreset | None:
    """Look up a style preset by key or display name.

    Checks custom presets first (so users can override builtins),
    then falls back to built-in presets.

    Returns ``None`` if not found.
    """
    # Check custom presets first (override builtins)
    try:
        mgr = CustomStylePresetManager()
        for preset_data in mgr.list_presets():
            preset = preset_data["preset"]
            if preset_data["key"] == name:
                return preset
            if preset.name.lower() == name.lower():
                return preset
    except Exception:
        pass  # Fall through to builtins

    # Try builtin key
    if name in DEFAULT_STYLE_PRESETS:
        return DEFAULT_STYLE_PRESETS[name]
    # Try builtin display name (case-insensitive)
    for preset in DEFAULT_STYLE_PRESETS.values():
        if preset.name.lower() == name.lower():
            return preset
    return None


def list_style_presets() -> list[StylePreset]:
    """Return all style presets (builtins + custom), sorted by name."""
    presets: dict[str, StylePreset] = {}

    # Start with builtins
    for k in sorted(DEFAULT_STYLE_PRESETS):
        presets[k] = DEFAULT_STYLE_PRESETS[k]

    # Overlay custom presets (custom keys override builtins)
    try:
        mgr = CustomStylePresetManager()
        for preset_data in mgr.list_presets():
            presets[preset_data["key"]] = preset_data["preset"]
    except Exception:
        pass

    return sorted(presets.values(), key=lambda p: p.name.lower())


# ─── Custom Style Preset Manager ─────────────────────────────


class CustomStylePresetManager:
    """Filesystem-backed CRUD for user-defined style presets.

    Stores presets as JSON files in ``data/comfyui/presets/``.
    Each preset gets a sequential ID ``PST-XXXX`` and a user-defined key.

    Usage::

        mgr = CustomStylePresetManager()
        preset_id = mgr.create(
            key="cyberpunk",
            name="Cyberpunk",
            description="Neon-lit futuristic cityscapes",
            positive_suffix="cyberpunk, neon lights, rain, futuristic",
            negative_prefix="nature, medieval, fantasy, bright daylight",
        )
        data = mgr.get(preset_id)  # {'id': 'PST-0001', 'key': '...', ...}
    """

    def __init__(self, *, presets_dir: Any = None) -> None:
        from config.settings import COMFYUI_PRESETS_DIR
        self._dir = Path(presets_dir) if presets_dir else COMFYUI_PRESETS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Create ───────────────────────────────────────────────

    def create(
        self,
        *,
        key: str,
        name: str,
        description: str = "",
        positive_suffix: str = "",
        negative_prefix: str = "",
    ) -> dict[str, Any]:
        """Create a new custom style preset.

        Args:
            key: Unique lookup key (e.g. ``"cyberpunk"``).
            name: Display name (e.g. ``"Cyberpunk"``).
            description: Short description.
            positive_suffix: Text appended to positive prompts.
            negative_prefix: Text prepended to negative prompts.

        Returns:
            The full preset record dict.

        Raises:
            PromptValidationError: If key or name is empty, or key already exists.
        """
        errors: list[str] = []
        if not key.strip():
            errors.append("Preset key is required.")
        if not name.strip():
            errors.append("Preset name is required.")
        key = key.strip().lower().replace(" ", "_")

        # Check for duplicate key
        if not errors:
            for existing in self._load_all():
                if existing.get("key") == key:
                    errors.append(f"Preset key '{key}' already exists.")
                    break

        if errors:
            raise PromptValidationError(errors)

        # Auto-sequential ID
        preset_id = self._next_id()

        record = {
            "id": preset_id,
            "key": key,
            "name": name.strip(),
            "description": description.strip(),
            "positive_suffix": positive_suffix.strip(),
            "negative_prefix": negative_prefix.strip(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        path = self._dir / f"{preset_id}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record

    # ── Read ─────────────────────────────────────────────────

    def get(self, preset_id: str) -> dict[str, Any]:
        """Get a preset by ID.

        Raises:
            PromptValidationError: If not found.
        """
        path = self._dir / f"{preset_id}.json"
        if not path.exists():
            raise PromptValidationError(f"Preset '{preset_id}' not found.")
        return json.loads(path.read_text(encoding="utf-8"))

    def list_presets(self) -> list[dict[str, Any]]:
        """List all custom presets, each enriched with a ``preset`` StylePreset.

        Returns a list of dicts with keys:
        ``id``, ``key``, ``name``, ``description``, ``positive_suffix``,
        ``negative_prefix``, ``created_at``, ``preset``.
        """
        records = self._load_all()
        records.sort(key=lambda r: r.get("name", "").lower())

        results = []
        for r in records:
            r["preset"] = StylePreset(
                name=r.get("name", ""),
                description=r.get("description", ""),
                positive_suffix=r.get("positive_suffix", ""),
                negative_prefix=r.get("negative_prefix", ""),
            )
            results.append(r)
        return results

    # ── Update ───────────────────────────────────────────────

    def update(
        self,
        preset_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        positive_suffix: str | None = None,
        negative_prefix: str | None = None,
    ) -> dict[str, Any]:
        """Update a custom preset.

        Raises:
            PromptValidationError: If preset not found.
        """
        record = self.get(preset_id)
        if name is not None:
            name = name.strip()
            if not name:
                raise PromptValidationError("Preset name cannot be empty.")
            record["name"] = name
        if description is not None:
            record["description"] = description.strip()
        if positive_suffix is not None:
            record["positive_suffix"] = positive_suffix.strip()
        if negative_prefix is not None:
            record["negative_prefix"] = negative_prefix.strip()

        path = self._dir / f"{preset_id}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return record

    # ── Delete ───────────────────────────────────────────────

    def delete(self, preset_id: str) -> bool:
        """Delete a custom preset.

        Raises:
            PromptValidationError: If preset not found.
        """
        path = self._dir / f"{preset_id}.json"
        if not path.exists():
            raise PromptValidationError(f"Preset '{preset_id}' not found.")
        path.unlink()
        return True

    # ── Import / Export ──────────────────────────────────────

    def export_json(self) -> list[dict[str, Any]]:
        """Export all custom presets as a JSON-serializable list.

        The ``preset`` key (StylePreset object) is excluded from export.
        """
        records = self._load_all()
        records.sort(key=lambda r: r.get("name", "").lower())
        return records

    def import_json(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Import presets from a JSON list.

        Skips presets whose key already exists (no overwrite).

        Returns:
            List of newly created preset records.
        """
        existing_keys = {r.get("key") for r in self._load_all()}
        created = []

        for item in data:
            key = (item.get("key") or "").strip().lower().replace(" ", "_")
            name = (item.get("name") or "").strip()
            if not key or not name:
                continue
            if key in existing_keys:
                continue  # Skip duplicates

            record = self.create(
                key=key,
                name=name,
                description=(item.get("description") or "").strip(),
                positive_suffix=(item.get("positive_suffix") or "").strip(),
                negative_prefix=(item.get("negative_prefix") or "").strip(),
            )
            created.append(record)
            existing_keys.add(key)

        return created

    # ── Internal ─────────────────────────────────────────────

    def _load_all(self) -> list[dict[str, Any]]:
        """Load all preset JSON files from the directory."""
        records = []
        for path in sorted(self._dir.glob("PST-*.json")):
            try:
                records.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue  # Skip corrupt files
        return records

    def _next_id(self) -> str:
        """Generate the next sequential preset ID."""
        existing_ids = []
        for path in self._dir.glob("PST-*.json"):
            stem = path.stem
            try:
                num = int(stem.split("-")[1])
                existing_ids.append(num)
            except (IndexError, ValueError):
                continue
        next_num = max(existing_ids, default=0) + 1
        return f"PST-{next_num:04d}"


def build_entity_context(
    entity_type: str,
    entity_id: str,
    *,
    character_manager: Any = None,
    location_manager: Any = None,
    item_manager: Any = None,
    store_manager: Any = None,
    registry: Any = None,
) -> str:
    """Build a descriptive context string for an entity.

    This reads the entity data from the appropriate manager and formats
    it as a structured text block suitable for injecting into an LLM
    prompt.

    Returns an empty string if the entity type is unknown or the entity
    is not found.
    """
    try:
        if entity_type == "character" and character_manager is not None:
            char = character_manager.get(entity_id)
            lines = [
                f"Entity: Character — {char.name}",
                f"Description: {char.description}",
            ]
            if char.backstory:
                lines.append(f"Backstory: {char.backstory}")
            if char.traits:
                trait_strs = [
                    f"  - {t.name} ({t.trait_type}): {t.description}"
                    for t in char.traits
                ]
                lines.append("Traits:")
                lines.extend(trait_strs)
            if char.tags:
                lines.append(f"Tags: {', '.join(char.tags)}")
            return "\n".join(lines)

        elif entity_type == "location" and location_manager is not None:
            loc = location_manager.get(entity_id)
            # Priority order: name → description → lore
            # Name and description define the place; lore adds atmosphere
            lines = [
                f"Entity: Location — {loc.name}",
                f"Description: {loc.description}",
            ]
            if hasattr(loc, "lore") and loc.lore:
                lines.append(f"Lore: {loc.lore}")
            if hasattr(loc, "tags") and loc.tags:
                lines.append(f"Tags: {', '.join(loc.tags)}")
            if hasattr(loc, "location_type") and loc.location_type:
                lines.append(f"Type: {loc.location_type}")
            if hasattr(loc, "coordinates") and loc.coordinates:
                lines.append(f"Coordinates: {loc.coordinates}")
            if hasattr(loc, "features") and loc.features:
                feat_list = loc.features if isinstance(loc.features, list) else []
                feat_strs = []
                for f in feat_list:
                    if isinstance(f, dict):
                        fname = f.get('name', f.get('feature_type', 'unknown'))
                        fdesc = f.get('description', '')
                        ftype = f.get('feature_type', '')
                        if fdesc and ftype:
                            feat_strs.append(f"  - {fname} ({ftype}): {fdesc}")
                        elif fdesc:
                            feat_strs.append(f"  - {fname}: {fdesc}")
                        else:
                            feat_strs.append(f"  - {fname}")
                    else:
                        # LocationFeature dataclass
                        fname = getattr(f, 'name', str(f))
                        fdesc = getattr(f, 'description', '')
                        ftype = getattr(f, 'feature_type', '')
                        if fdesc and ftype:
                            feat_strs.append(f"  - {fname} ({ftype}): {fdesc}")
                        elif fdesc:
                            feat_strs.append(f"  - {fname}: {fdesc}")
                        else:
                            feat_strs.append(f"  - {fname}")
                if feat_strs:
                    lines.append("Features:")
                    lines.extend(feat_strs)
            return "\n".join(lines)

        elif entity_type == "item" and item_manager is not None:
            item = item_manager.get(entity_id)
            # Priority order: tags → name → description → lore
            # Tags come first as the strongest visual/categorical signal
            lines = []
            if hasattr(item, "tags") and item.tags:
                lines.append(f"Tags: {', '.join(item.tags)}")
            lines.append(f"Entity: Item — {item.name}")
            lines.append(f"Description: {item.description}")
            if hasattr(item, "lore") and item.lore:
                lines.append(f"Lore: {item.lore}")
            if hasattr(item, "rarity") and item.rarity:
                lines.append(f"Rarity: {item.rarity}")
            if hasattr(item, "tier") and item.tier:
                lines.append(f"Tier: {item.tier}")
            if hasattr(item, "properties") and item.properties:
                prop_strs = [
                    f"  - {p.name} ({p.property_type}): {p.description}"
                    for p in item.properties
                ]
                lines.append("Properties:")
                lines.extend(prop_strs)
            return "\n".join(lines)

        elif entity_type == "store" and store_manager is not None:
            store = store_manager.get(entity_id)
            lines = [
                f"Entity: Store — {store.name}",
                f"Description: {store.description}",
            ]
            if hasattr(store, "store_type") and store.store_type:
                lines.append(f"Type: {store.store_type}")
            return "\n".join(lines)

        elif entity_type == "council_member" and registry is not None:
            member = registry.get(entity_id)
            lines = [
                f"Entity: Council Member — {member.name}",
                f"Role: {member.role}",
                f"Description: {member.description}",
            ]
            if member.specialties:
                lines.append(f"Specialties: {', '.join(member.specialties)}")
            return "\n".join(lines)

    except Exception:
        pass  # Entity not found or manager error — return empty

    return ""


# ─── System Prompt Templates ─────────────────────────────────


_SYSTEM_PROMPT_IMAGE_EXPERT = """\
You are an expert image prompt engineer. Your job is to generate \
high-quality prompts for AI image generation (Stable Diffusion, SDXL, Flux).

When given an entity description, produce a vivid, detailed image prompt \
that captures the essence of the subject. Focus on visual details: \
appearance, lighting, mood, composition, medium, and style.

Respond with EXACTLY two lines:
POSITIVE: <your positive prompt here>
NEGATIVE: <your negative prompt here>

Do NOT include any other text, explanation, or preamble. \
Just the two lines starting with POSITIVE: and NEGATIVE:"""

_CHARACTER_PROMPT_TEMPLATE = """\
You are {member_name}, and you have been asked to describe an image \
of the following entity. Use your unique perspective, personality, and \
artistic sensibility to create a vivid image generation prompt.

{entity_context}

{style_guidance}

{context_hint}

Respond with EXACTLY two lines:
POSITIVE: <your positive prompt here>
NEGATIVE: <your negative prompt here>

Do NOT include any other text, explanation, or preamble. \
Just the two lines starting with POSITIVE: and NEGATIVE:"""

_USER_REFINED_TEMPLATE = """\
You are {member_name}. The operator has drafted a rough image prompt \
and wants you to enhance it using your artistic sensibility and \
knowledge of the subject.

Operator's draft prompt: "{user_prompt}"

{entity_context}

{style_guidance}

Enhance and refine the prompt. Keep the operator's core intent but add \
visual detail, composition notes, lighting, and atmosphere.

Respond with EXACTLY two lines:
POSITIVE: <your refined positive prompt here>
NEGATIVE: <your negative prompt here>

Do NOT include any other text, explanation, or preamble. \
Just the two lines starting with POSITIVE: and NEGATIVE:"""

_SYSTEM_MODE_TEMPLATE = """\
{entity_context}

{style_guidance}

{context_hint}

Generate a detailed, vivid image prompt for the entity described above. \
Focus on visual details: appearance, lighting, mood, composition, and style.

Respond with EXACTLY two lines:
POSITIVE: <your positive prompt here>
NEGATIVE: <your negative prompt here>

Do NOT include any other text, explanation, or preamble. \
Just the two lines starting with POSITIVE: and NEGATIVE:"""


# ─── Response Parsing ─────────────────────────────────────────


def parse_prompt_response(raw_text: str) -> tuple[str, str]:
    """Parse POSITIVE: / NEGATIVE: lines from LLM output.

    Returns a ``(positive, negative)`` tuple.  If the response does not
    follow the expected format, the entire text is treated as the
    positive prompt and negative is empty.
    """
    positive = ""
    negative = ""

    for line in raw_text.strip().splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("POSITIVE:"):
            positive = stripped[len("POSITIVE:"):].strip()
        elif upper.startswith("NEGATIVE:"):
            negative = stripped[len("NEGATIVE:"):].strip()

    # Fallback: if no POSITIVE: line found, use the whole text
    if not positive:
        positive = raw_text.strip()

    return positive, negative


def apply_style_preset(
    positive: str,
    negative: str,
    preset: StylePreset | None,
) -> tuple[str, str]:
    """Append/prepend style preset fragments to prompt strings."""
    if preset is None:
        return positive, negative

    if preset.positive_suffix:
        if positive:
            positive = f"{positive}, {preset.positive_suffix}"
        else:
            positive = preset.positive_suffix

    if preset.negative_prefix:
        if negative:
            negative = f"{preset.negative_prefix}, {negative}"
        else:
            negative = preset.negative_prefix

    return positive, negative


# ─── Prompt Builder ───────────────────────────────────────────


class PromptBuilder:
    """Multi-mode prompt generator for image generation.

    Integrates with the Jericho :class:`APIClient` and
    :class:`CouncilRegistry` to produce image generation prompts
    using council members' personalities.

    Usage::

        builder = PromptBuilder(api_client=client, registry=registry)
        request = PromptRequest.create("character",
                                        member_name="Spark",
                                        entity_type="character",
                                        entity_id="CH-0001")
        result = await builder.generate(request)
        print(result.positive)

    For ``raw_user`` mode, no API client is needed::

        builder = PromptBuilder()
        request = PromptRequest.create("raw_user",
                                        user_prompt="a majestic castle")
        result = await builder.generate(request)
    """

    def __init__(
        self,
        *,
        api_client: Any = None,
        registry: Any = None,
        character_manager: Any = None,
        location_manager: Any = None,
        item_manager: Any = None,
        store_manager: Any = None,
    ) -> None:
        self._api_client = api_client
        self._registry = registry
        self._character_manager = character_manager
        self._location_manager = location_manager
        self._item_manager = item_manager
        self._store_manager = store_manager

    # ── Properties ───────────────────────────────────────────

    @property
    def api_client(self) -> Any:
        return self._api_client

    @property
    def registry(self) -> Any:
        return self._registry

    # ── Generate ─────────────────────────────────────────────

    async def generate(self, request: PromptRequest) -> PromptResult | list[PromptResult]:
        """Generate image prompt(s) using the specified mode.

        Args:
            request: A validated :class:`PromptRequest`.

        Returns:
            A single :class:`PromptResult` for most modes, or a
            ``list[PromptResult]`` for ``council_vote`` mode (one per
            participant).

        Raises:
            PromptError: If the API client is not available when needed.
            PromptValidationError: If the request is invalid.
        """
        if request.mode == "raw_user":
            return self._generate_raw_user(request)
        elif request.mode == "system":
            return await self._generate_system(request)
        elif request.mode == "character":
            return await self._generate_character(request)
        elif request.mode == "user_refined":
            return await self._generate_user_refined(request)
        elif request.mode == "council_vote":
            return await self._generate_council_vote(request)
        else:
            raise PromptValidationError(
                f"Unknown mode '{request.mode}'"
            )

    # ── Raw User Mode ────────────────────────────────────────

    def _generate_raw_user(self, request: PromptRequest) -> PromptResult:
        """Directly use the user's prompt with no LLM involvement."""
        positive = request.user_prompt
        negative = ""

        positive, negative = apply_style_preset(
            positive, negative, request.style_preset,
        )

        return PromptResult.create(
            positive=positive,
            negative=negative,
            mode="raw_user",
            style_preset_name=request.style_preset.name if request.style_preset else "",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            raw_llm_response="",
            metadata=dict(request.metadata),
        )

    # ── System Mode ──────────────────────────────────────────

    async def _generate_system(self, request: PromptRequest) -> PromptResult:
        """Use a generic image-expert system prompt."""
        self._ensure_api_client()

        entity_context = self._build_entity_context(request)
        style_guidance = self._build_style_guidance(request.style_preset)
        context_hint = request.context_hint if request.context_hint else ""

        user_message = _SYSTEM_MODE_TEMPLATE.format(
            entity_context=entity_context,
            style_guidance=style_guidance,
            context_hint=context_hint,
        )

        raw_text = await self._call_llm_with_system_prompt(
            _SYSTEM_PROMPT_IMAGE_EXPERT,
            user_message,
        )

        positive, negative = parse_prompt_response(raw_text)
        positive, negative = apply_style_preset(
            positive, negative, request.style_preset,
        )

        return PromptResult.create(
            positive=positive,
            negative=negative,
            mode="system",
            style_preset_name=request.style_preset.name if request.style_preset else "",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            raw_llm_response=raw_text,
            metadata=dict(request.metadata),
        )

    # ── Character Mode ───────────────────────────────────────

    async def _generate_character(self, request: PromptRequest) -> PromptResult:
        """Use a specific member's personality to generate the prompt."""
        self._ensure_api_client()
        self._ensure_registry()

        member = self._registry.get(request.member_name)
        entity_context = self._build_entity_context(request)
        style_guidance = self._build_style_guidance(request.style_preset)
        context_hint = request.context_hint if request.context_hint else ""

        user_message = _CHARACTER_PROMPT_TEMPLATE.format(
            member_name=member.name,
            entity_context=entity_context,
            style_guidance=style_guidance,
            context_hint=context_hint,
        )

        raw_text = await self._call_llm_with_member(member, user_message)

        positive, negative = parse_prompt_response(raw_text)
        positive, negative = apply_style_preset(
            positive, negative, request.style_preset,
        )

        return PromptResult.create(
            positive=positive,
            negative=negative,
            mode="character",
            member_name=member.name,
            style_preset_name=request.style_preset.name if request.style_preset else "",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            raw_llm_response=raw_text,
            metadata=dict(request.metadata),
        )

    # ── User-Refined Mode ────────────────────────────────────

    async def _generate_user_refined(self, request: PromptRequest) -> PromptResult:
        """User provides a base prompt; a member enhances it."""
        self._ensure_api_client()
        self._ensure_registry()

        member = self._registry.get(request.member_name)
        entity_context = self._build_entity_context(request)
        style_guidance = self._build_style_guidance(request.style_preset)

        user_message = _USER_REFINED_TEMPLATE.format(
            member_name=member.name,
            user_prompt=request.user_prompt,
            entity_context=entity_context,
            style_guidance=style_guidance,
        )

        raw_text = await self._call_llm_with_member(member, user_message)

        positive, negative = parse_prompt_response(raw_text)
        positive, negative = apply_style_preset(
            positive, negative, request.style_preset,
        )

        return PromptResult.create(
            positive=positive,
            negative=negative,
            mode="user_refined",
            member_name=member.name,
            style_preset_name=request.style_preset.name if request.style_preset else "",
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            raw_llm_response=raw_text,
            metadata={**request.metadata, "original_user_prompt": request.user_prompt},
        )

    # ── Council Vote Mode ────────────────────────────────────

    async def _generate_council_vote(self, request: PromptRequest) -> list[PromptResult]:
        """Each participant generates a prompt; return all for comparison."""
        self._ensure_api_client()
        self._ensure_registry()

        results: list[PromptResult] = []
        entity_context = self._build_entity_context(request)
        style_guidance = self._build_style_guidance(request.style_preset)
        context_hint = request.context_hint if request.context_hint else ""

        for participant_name in request.participants:
            member = self._registry.get(participant_name)

            user_message = _CHARACTER_PROMPT_TEMPLATE.format(
                member_name=member.name,
                entity_context=entity_context,
                style_guidance=style_guidance,
                context_hint=context_hint,
            )

            raw_text = await self._call_llm_with_member(member, user_message)

            positive, negative = parse_prompt_response(raw_text)
            positive, negative = apply_style_preset(
                positive, negative, request.style_preset,
            )

            result = PromptResult.create(
                positive=positive,
                negative=negative,
                mode="council_vote",
                member_name=member.name,
                style_preset_name=request.style_preset.name if request.style_preset else "",
                entity_type=request.entity_type,
                entity_id=request.entity_id,
                raw_llm_response=raw_text,
                metadata=dict(request.metadata),
            )
            results.append(result)

        return results

    # ── LLM Call Helpers ─────────────────────────────────────

    async def _call_llm_with_system_prompt(
        self,
        system_prompt: str,
        user_message: str,
    ) -> str:
        """Send a chat request using a custom system prompt (no member).

        Creates a temporary CouncilMember-like object with the system prompt
        for compatibility with the APIClient's chat() interface.
        """
        from core.api_client import ChatMessage
        from core.registry import CouncilMember

        # Use a generic member with an openrouter provider and the
        # image-expert system prompt
        temporary_member = CouncilMember(
            name="ImagePromptExpert",
            role="Image Prompt Expert",
            description="Generates image prompts for AI image generation",
            api_provider="openrouter",
            model="Default",
            system_prompt=system_prompt,
        )

        messages = [ChatMessage(role="user", content=user_message)]
        response = await self._api_client.chat(temporary_member, messages)
        return response.content

    async def _call_llm_with_member(
        self,
        member: Any,
        user_message: str,
    ) -> str:
        """Send a chat request using a real council member."""
        from core.api_client import ChatMessage

        messages = [ChatMessage(role="user", content=user_message)]
        response = await self._api_client.chat(member, messages)
        return response.content

    # ── Context Helpers ──────────────────────────────────────

    def _build_entity_context(self, request: PromptRequest) -> str:
        """Build entity context from the request."""
        if not request.entity_type or not request.entity_id:
            return ""
        return build_entity_context(
            request.entity_type,
            request.entity_id,
            character_manager=self._character_manager,
            location_manager=self._location_manager,
            item_manager=self._item_manager,
            store_manager=self._store_manager,
            registry=self._registry,
        )

    @staticmethod
    def _build_style_guidance(preset: StylePreset | None) -> str:
        """Build style guidance text from a preset."""
        if preset is None:
            return ""
        parts = [f"Style: {preset.name}"]
        if preset.description:
            parts.append(f"Style Description: {preset.description}")
        if preset.positive_suffix:
            parts.append(f"Style Keywords: {preset.positive_suffix}")
        return "\n".join(parts)

    # ── Validation Helpers ───────────────────────────────────

    def _ensure_api_client(self) -> None:
        """Raise if no API client is available."""
        if self._api_client is None:
            raise PromptError(
                "An API client is required for this prompt mode. "
                "Pass api_client= to PromptBuilder()."
            )

    def _ensure_registry(self) -> None:
        """Raise if no registry is available."""
        if self._registry is None:
            raise PromptError(
                "A council registry is required for this prompt mode. "
                "Pass registry= to PromptBuilder()."
            )

    # ── Dunder ───────────────────────────────────────────────

    def __repr__(self) -> str:
        has_api = self._api_client is not None
        has_reg = self._registry is not None
        return f"PromptBuilder(api_client={has_api}, registry={has_reg})"
