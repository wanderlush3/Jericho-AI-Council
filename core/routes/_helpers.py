"""
Jericho — Shared Route Helpers

Re-exports helper functions that are used across multiple route modules.
Each function is defined in its primary route module and re-exported here
for convenient cross-module importing.
"""

from __future__ import annotations

# These will be populated after all route modules are loaded.
# Using lazy imports to avoid circular dependency issues.


def _get_pipeline():
    """Lazily create the GenerationPipeline singleton. (Defined in generation.py)"""
    from core.routes.generation import _get_pipeline as _impl
    return _impl()


def _explore_primary_image(imgr, entity_type: str, entity_id: str) -> str:
    """Get primary image URL for an entity. (Defined in generation.py)"""
    from core.routes.generation import _explore_primary_image as _impl
    return _impl(imgr, entity_type, entity_id)


def _make_discussion_manager(proposal_manager=None):
    """Create a DiscussionManager. (Defined in chat.py)"""
    from core.routes.chat import _make_discussion_manager as _impl
    return _impl(proposal_manager)


def _build_participant_context(
    participants,
    *,
    skip_world_context: bool = False,
    current_speaker: str | None = None,
    context_keywords: list[str] | None = None,
    profile=None,
):
    """Build participant context for prompts. (Defined in context_builder.py)"""
    from core.context_builder import build_participant_context as _impl
    return _impl(
        participants,
        skip_world_context=skip_world_context,
        current_speaker=current_speaker,
        context_keywords=context_keywords,
        profile=profile,
    )
