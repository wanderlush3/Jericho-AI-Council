"""
Jericho — Context Builder

Builds rich markdown context for LLM prompt injection.
Extracted from core/routes/explore.py (F-064) to keep route modules
as thin HTTP adapters.
"""

from __future__ import annotations

import logging
from typing import Any

from core.manager_cache import (
    get_character_manager,
    get_item_manager,
    get_law_manager,
    get_location_manager,
    get_registry,
    get_store_manager,
)
from config.settings import (
    CHARACTER_BACKSTORY_PREVIEW_LENGTH,
    CHARACTER_PERSONA_PREVIEW_LENGTH,
    CONTEXT_MAX_WORLD_ITEMS,
    CONTEXT_MAX_WORLD_LAWS,
    CONTEXT_MAX_WORLD_LOCATIONS,
    CONTEXT_MAX_WORLD_STORES,
    COUNCIL_PERSONA_PREVIEW_LENGTH,
    ITEM_INJECTION_MAX_LENGTH,
    LOCATION_INJECTION_MAX_LENGTH,
    STORE_INJECTION_MAX_LENGTH,
)
from core.injection_profiles import InjectionProfile, get_profile

log = logging.getLogger(__name__)

PARTICIPANT_MAX = 10


def build_participant_context(
    participants: list[dict[str, Any]],
    *,
    skip_world_context: bool = False,
    current_speaker: str | None = None,
    context_keywords: list[str] | None = None,
    profile: InjectionProfile | None = None,
) -> str:
    """Build rich markdown context for selected participants.

    Injects:
    - Council members: persona, core beliefs, relevant memories
    - Characters: full description, backstory, traits, system prompt
    - Shared world context: active laws, locations, items
      (unless ``skip_world_context`` is True)

    Args:
        participants: List of {"id": "...", "type": "council"|"character"}
        skip_world_context: When True, omit the World Context section
            (laws, locations, items, stores).  Use this when the caller
            already injects world context via MemoryInfluence to avoid
            double-injection.
        current_speaker: When provided, skip the persona preview for
            the participant whose name matches (case-insensitive).
            The current speaker already has their full system_prompt
            as the LLM system message, so repeating the preview is
            redundant (F-056).
        context_keywords: Optional list of words/phrases describing the
            current conversational context.  When provided, laws are
            scored against these keywords and only relevant laws are
            injected (F-060).  When ``None``, all active laws are
            injected (backward-compatible behaviour).
        profile: Optional injection profile (F-061) that controls
            which context layers are included.  When ``None``, all
            layers are included (backward-compatible behaviour).
            When provided, boolean flags on the profile config
            determine whether memories, beliefs, world context,
            laws, and injections are included.

    Returns:
        Markdown text suitable for prompt injection.
    """
    if not participants:
        return ""

    # Resolve profile config (None → include everything)
    pcfg = get_profile(profile) if profile is not None else None

    parts: list[str] = []
    parts.append("\n## Present Participants\n")

    # Separate by type
    council_ids = [
        p["id"] for p in participants if p.get("type") == "council"
    ]
    character_ids = [
        p["id"] for p in participants if p.get("type") == "character"
    ]

    # ── Council Members ──
    if council_ids:
        try:
            registry = get_registry()
            members_map = {
                m.name.lower(): m for m in registry.list_members()
            }
        except Exception:
            log.debug("context_builder: failed registry", exc_info=True)
            members_map = {}

        # Memory influence engine (may not be available)
        # F-061: Skip memory/belief injection when profile disables them
        _want_memories = pcfg is None or pcfg.include_memories
        _want_beliefs = pcfg is None or pcfg.include_beliefs
        mi = None
        if _want_memories or _want_beliefs:
            try:
                from core.memory_influence import MemoryInfluence
                mi = MemoryInfluence(embedding_provider=None)
            except Exception:
                log.debug("Failed to load character data for LLM context", exc_info=True)
        for cid in council_ids:
            member = members_map.get(cid.lower())
            if not member:
                parts.append(f"### 🏛️ Council Member: {cid}")
                parts.append("*(Member data unavailable)*\n")
                continue

            parts.append(f"### 🏛️ Council Member: {member.name}")
            parts.append(f"**Role:** {member.role}")
            if member.description:
                parts.append(f"**Description:** {member.description}")
            # F-056: Skip persona preview when this member IS the
            # current speaker — their full system_prompt is already
            # the LLM system message.
            is_self = (
                current_speaker is not None
                and member.name.lower() == current_speaker.lower()
            )
            if member.system_prompt and not is_self:
                _lim = COUNCIL_PERSONA_PREVIEW_LENGTH
                prompt_preview = member.system_prompt[:_lim]
                parts.append(
                    f"**Persona:** {prompt_preview}"
                    + ("…" if len(member.system_prompt) > _lim else "")
                )
            if member.specialties:
                parts.append(
                    f"**Specialties:** {', '.join(member.specialties)}"
                )

            # Inject core beliefs and memories via MemoryInfluence
            if mi:
                try:
                    ctx = mi.build_context(
                        member.name,
                        ["exploration", "location", "scene"],
                    )
                    # F-061: Only inject beliefs/memories when profile allows
                    if ctx.beliefs and _want_beliefs:
                        parts.append("\n**Core Beliefs:**")
                        for sb in ctx.beliefs[:5]:
                            parts.append(
                                f"- **{sb.belief.topic}**: "
                                f"{sb.belief.content}"
                            )
                    if ctx.memories and _want_memories:
                        parts.append("\n**Relevant Memories:**")
                        for sm in ctx.memories[:5]:
                            parts.append(
                                f"- [{sm.entry.event_type}] "
                                f"{sm.entry.content}"
                            )
                except Exception:
                    log.debug("Failed to score and select relevant law for context", exc_info=True)

            # F-069: Inject reputation tier
            try:
                from core.manager_cache import get_reputation_manager
                from config.settings import DEFAULT_REPUTATION_STANCES
                rep_mgr = get_reputation_manager()
                entity_id = f"member:{member.name.lower()}"
                score = rep_mgr.get_score(entity_id)
                if score.event_count > 0:
                    parts.append(
                        f"**Reputation:** {score.tier_emoji} "
                        f"{score.tier.title()} (score: {score.decayed_score:.0f})"
                    )
                else:
                    # No events yet — show default stance perception note
                    stance = DEFAULT_REPUTATION_STANCES.get(member.name.lower(), "neutral")
                    from core.reputation import tier_emoji as _te
                    parts.append(
                        f"**Reputation:** {_te(stance)} {stance.title()} (default)"
                    )
            except Exception:
                log.debug("core.context_builder: reputation injection error", exc_info=True)
            parts.append("")  # blank separator

    # ── Characters ──
    if character_ids:
        try:
            cmgr = get_character_manager()
        except Exception:
            log.debug("context_builder: failed cmgr", exc_info=True)
            cmgr = None

        for char_id in character_ids:
            if cmgr is None:
                parts.append(f"### 🎭 Character: {char_id}")
                parts.append("*(Character data unavailable)*\n")
                continue

            try:
                char = cmgr.get(char_id)
            except Exception:
                log.debug("context_builder: failed char", exc_info=True)
                parts.append(f"### 🎭 Character: {char_id}")
                parts.append("*(Character not found)*\n")
                continue

            parts.append(f"### 🎭 Character: {char.name}")
            if char.description:
                parts.append(f"**Description:** {char.description}")
            # F-056: Skip backstory + persona preview when this
            # character IS the current speaker.
            is_self = (
                current_speaker is not None
                and char.name.lower() == current_speaker.lower()
            )
            if char.backstory and not is_self:
                _blim = CHARACTER_BACKSTORY_PREVIEW_LENGTH
                backstory_preview = char.backstory[:_blim]
                parts.append(
                    f"**Backstory:** {backstory_preview}"
                    + ("…" if len(char.backstory) > _blim else "")
                )
            if char.traits:
                trait_strs = [
                    f"{t.name} ({t.trait_type}, "
                    f"{int(t.intensity * 100)}%)"
                    for t in char.traits[:8]
                ]
                parts.append(f"**Traits:** {', '.join(trait_strs)}")
            if char.system_prompt and not is_self:
                _plim = CHARACTER_PERSONA_PREVIEW_LENGTH
                prompt_preview = char.system_prompt[:_plim]
                parts.append(
                    f"**Persona:** {prompt_preview}"
                    + ("…" if len(char.system_prompt) > _plim else "")
                )
            parts.append("")

    # ── Shared World Context ──
    # When skip_world_context is True, the caller's MemoryInfluence
    # engine already injects world locations/items with relevance
    # scoring, so we skip them here to avoid duplication (F-055).
    # F-061: Also skip when profile disables world context.
    if skip_world_context:
        return "\n".join(parts)
    if pcfg is not None and not pcfg.include_world_context:
        return "\n".join(parts)

    parts.append("\n## World Context\n")

    # Active Laws (F-060: conditional injection based on context keywords)
    # F-061: Skip laws when profile disables them
    _want_laws = pcfg is None or pcfg.include_laws
    if _want_laws:
        try:
            active_laws = get_law_manager().list_laws(status="active")
            if active_laws:
                if context_keywords:
                    # Score laws against context and inject only relevant ones
                    from core.law_filter import LawFilter
                    lf = LawFilter()
                    scored = lf.filter_laws(
                        active_laws, context_keywords,
                        limit=CONTEXT_MAX_WORLD_LAWS,
                    )
                    if scored:
                        parts.append("### Active Laws")
                        for sl in scored:
                            parts.append(
                                f"- **{sl.law.title}**: {sl.law.description[:200]}"
                            )
                        parts.append("")
                else:
                    # No context keywords — inject all (backward-compatible)
                    parts.append("### Active Laws")
                    for law in active_laws[:CONTEXT_MAX_WORLD_LAWS]:
                        parts.append(
                            f"- **{law.title}**: {law.description[:200]}"
                        )
                    parts.append("")
        except Exception:
            log.debug("Failed to load active location for world context", exc_info=True)
    try:
        active_locs = get_location_manager().list_locations(status="active")
        if active_locs:
            parts.append("### Known Locations")
            for loc in active_locs[:CONTEXT_MAX_WORLD_LOCATIONS]:
                line = f"- **{loc.name}**: {loc.description[:150]}"
                if loc.lore:
                    line += f" — {loc.lore[:100]}"
                parts.append(line)
                # F-053: Inject location LLM injection text
                # F-061: Only inject when profile allows injections
                _want_inj = pcfg is None or pcfg.include_injections
                if loc.llm_injection and _want_inj:
                    parts.append(
                        f"  💉 *{loc.llm_injection[:LOCATION_INJECTION_MAX_LENGTH]}*"
                    )
            parts.append("")
    except Exception:
        log.debug("Failed to load active item for world context", exc_info=True)
    try:
        from core.items import is_injection_active
        active_items = get_item_manager().list_items(status="active")
        if active_items:
            parts.append("### Known Items")
            for item in active_items[:CONTEXT_MAX_WORLD_ITEMS]:
                line = f"- **{item.name}**: {item.description[:150]}"
                if item.rarity:
                    line += f" [{item.rarity}]"
                parts.append(line)
                # F-053: Inject item LLM injection text (respects consumable TTL)
                # F-061: Only inject when profile allows injections
                _want_inj = pcfg is None or pcfg.include_injections
                if is_injection_active(item) and _want_inj:
                    parts.append(
                        f"  💉 *{item.llm_injection[:ITEM_INJECTION_MAX_LENGTH]}*"
                    )
            parts.append("")
    except Exception:
        log.debug("Failed to load active store for world context", exc_info=True)
    try:
        active_stores = get_store_manager().list_stores(status="active")
        if active_stores:
            parts.append("### Known Stores")
            for store in active_stores[:CONTEXT_MAX_WORLD_STORES]:
                line = f"- **{store.name}**: {store.description[:150]}"
                if store.store_type:
                    line += f" ({store.store_type})"
                parts.append(line)
                # F-053: Inject store LLM injection text
                # F-061: Only inject when profile allows injections
                _want_inj = pcfg is None or pcfg.include_injections
                if store.llm_injection and _want_inj:
                    parts.append(
                        f"  💉 *{store.llm_injection[:STORE_INJECTION_MAX_LENGTH]}*"
                    )
            parts.append("")
    except Exception:
        log.debug("Failed to load reputation tier for council context", exc_info=True)
    return "\n".join(parts)


# Backward-compatible alias (underscore-prefixed name used by existing code)
_build_participant_context = build_participant_context
