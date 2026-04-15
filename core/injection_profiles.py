"""
Jericho — Tiered Injection Profiles (F-061)

Named injection profiles that control which context layers are included
in LLM prompts for different call types.  Each route chooses the
appropriate profile, eliminating unnecessary context and saving
~1000–2000 tokens for lightweight call types.

Profiles:
    CHAT_FULL    — All layers (chat with full world/memory context)
    CHAT_LIGHT   — System prompt + history + identity only
    IMAGE_GEN    — Entity context + style (no memories/laws/world)
    NARRATION    — Story context + participant identity + world subset
    DISCUSSION   — Proposal + prior contributions + beliefs only

Usage::

    from core.injection_profiles import InjectionProfile, get_profile

    cfg = get_profile(InjectionProfile.IMAGE_GEN)
    if cfg.include_world_context:
        # inject world entities …
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any


# ─── Profile Enum ─────────────────────────────────────────────


class InjectionProfile(enum.Enum):
    """Named injection profiles for different LLM call types."""

    CHAT_FULL = "chat_full"
    CHAT_LIGHT = "chat_light"
    IMAGE_GEN = "image_gen"
    NARRATION = "narration"
    DISCUSSION = "discussion"


# ─── Profile Configuration ───────────────────────────────────


@dataclass(frozen=True)
class ProfileConfig:
    """Boolean flags controlling which context layers to include.

    Each flag maps to a section of the LLM prompt that can be
    independently enabled or disabled.

    Attributes:
        name: Human-readable profile name.
        include_system_prompt: Include the agent's system prompt.
        include_history: Include conversation history.
        include_memories: Include session log memories.
        include_beliefs: Include core beliefs.
        include_world_context: Include world entities (locations,
            items, stores).
        include_laws: Include active laws.
        include_injections: Include user-authored LLM injections.
        include_participant_context: Include other-participant
            identity previews (persona, backstory, traits).
    """

    name: str
    include_system_prompt: bool = True
    include_history: bool = True
    include_memories: bool = True
    include_beliefs: bool = True
    include_world_context: bool = True
    include_laws: bool = True
    include_injections: bool = True
    include_participant_context: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for API/debug output."""
        return {
            "name": self.name,
            "include_system_prompt": self.include_system_prompt,
            "include_history": self.include_history,
            "include_memories": self.include_memories,
            "include_beliefs": self.include_beliefs,
            "include_world_context": self.include_world_context,
            "include_laws": self.include_laws,
            "include_injections": self.include_injections,
            "include_participant_context": self.include_participant_context,
        }

    @property
    def enabled_layers(self) -> list[str]:
        """List of layer names that are enabled in this profile."""
        layers = []
        for field_name in (
            "include_system_prompt",
            "include_history",
            "include_memories",
            "include_beliefs",
            "include_world_context",
            "include_laws",
            "include_injections",
            "include_participant_context",
        ):
            if getattr(self, field_name):
                # Strip "include_" prefix for readability
                layers.append(field_name[8:])
        return layers


# ─── Profile Registry ────────────────────────────────────────

PROFILE_CONFIGS: dict[InjectionProfile, ProfileConfig] = {
    # Full context — used by explore chat, story chat, human-to-agent chat
    InjectionProfile.CHAT_FULL: ProfileConfig(
        name="chat_full",
        include_system_prompt=True,
        include_history=True,
        include_memories=True,
        include_beliefs=True,
        include_world_context=True,
        include_laws=True,
        include_injections=True,
        include_participant_context=True,
    ),

    # Lightweight chat — system prompt + history + identity only
    InjectionProfile.CHAT_LIGHT: ProfileConfig(
        name="chat_light",
        include_system_prompt=True,
        include_history=True,
        include_memories=False,
        include_beliefs=False,
        include_world_context=False,
        include_laws=False,
        include_injections=False,
        include_participant_context=True,
    ),

    # Image generation — entity context + style only
    InjectionProfile.IMAGE_GEN: ProfileConfig(
        name="image_gen",
        include_system_prompt=False,
        include_history=False,
        include_memories=False,
        include_beliefs=False,
        include_world_context=False,
        include_laws=False,
        include_injections=False,
        include_participant_context=True,
    ),

    # Narration — story context + participant identity + world subset
    InjectionProfile.NARRATION: ProfileConfig(
        name="narration",
        include_system_prompt=True,
        include_history=False,
        include_memories=False,
        include_beliefs=False,
        include_world_context=True,
        include_laws=True,
        include_injections=True,
        include_participant_context=True,
    ),

    # Discussion — proposal + prior contributions + beliefs only
    InjectionProfile.DISCUSSION: ProfileConfig(
        name="discussion",
        include_system_prompt=True,
        include_history=True,
        include_memories=False,
        include_beliefs=True,
        include_world_context=False,
        include_laws=False,
        include_injections=False,
        include_participant_context=False,
    ),
}


# ─── Public API ───────────────────────────────────────────────


def get_profile(profile: InjectionProfile) -> ProfileConfig:
    """Look up the configuration for an injection profile.

    Args:
        profile: The profile enum value to look up.

    Returns:
        The ``ProfileConfig`` for the given profile.

    Raises:
        ValueError: If the profile is not registered.
    """
    cfg = PROFILE_CONFIGS.get(profile)
    if cfg is None:
        raise ValueError(
            f"Unknown injection profile: {profile!r}. "
            f"Valid profiles: {[p.value for p in InjectionProfile]}"
        )
    return cfg


def should_include(profile: InjectionProfile, layer: str) -> bool:
    """Check whether a specific layer should be included for a profile.

    Args:
        profile: The injection profile.
        layer: The layer name (e.g. ``"world_context"``, ``"memories"``).
            This should match the suffix after ``include_`` in the
            ``ProfileConfig`` fields.

    Returns:
        ``True`` if the layer should be included, ``False`` otherwise.

    Raises:
        ValueError: If the profile is not registered.
        AttributeError: If the layer name is invalid.
    """
    cfg = get_profile(profile)
    attr = f"include_{layer}"
    if not hasattr(cfg, attr):
        raise AttributeError(
            f"Unknown layer '{layer}'. Valid layers: "
            f"{[f[8:] for f in cfg.__dataclass_fields__ if f.startswith('include_')]}"
        )
    return getattr(cfg, attr)
