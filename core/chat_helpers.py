"""
Jericho — Chat Helper Utilities (F-063)

Pure functions shared across chat modules.  Extracted from
``core/human_chat.py`` so they can be imported independently.

Includes:
- character_to_member — convert a ``CharacterTemplate`` to a ``CouncilMember``
- character_memory_name — derive a memory directory name from a character name
- build_human_chat_prompt — assemble the LLM prompt for human-to-agent chat
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.characters import CharacterTemplate
from core.conversation_summary import RollingSummaryResult
from core.registry import CouncilMember

if TYPE_CHECKING:
    pass  # No additional type-only imports needed


# ─── Character ↔ Member Conversion ────────────────────────────


def character_to_member(char: CharacterTemplate) -> CouncilMember:
    """Convert a CharacterTemplate to a CouncilMember for API calls.

    Uses the character's own api_provider/model (model defaults to
    'Default' which makes APIClient fall back to the Settings default).
    The character's traits, backstory, and personality fields are woven
    into the system prompt so the LLM receives the full character context.
    """
    # Build a rich system prompt from all character fields
    prompt_parts: list[str] = []
    if char.system_prompt:
        prompt_parts.append(char.system_prompt)

    if char.backstory:
        prompt_parts.append(f"\n## Backstory\n{char.backstory}")

    if char.traits:
        traits_text = "\n".join(
            f"- **{t.name}** ({t.trait_type}, intensity {t.intensity}): {t.description}"
            for t in char.traits
        )
        prompt_parts.append(f"\n## Character Traits\n{traits_text}")

    if char.greeting:
        prompt_parts.append(
            f"\n## Greeting\nWhen starting a conversation, greet with: {char.greeting}"
        )

    if char.example_messages:
        examples = "\n".join(f"- {ex}" for ex in char.example_messages)
        prompt_parts.append(f"\n## Example Messages\n{examples}")

    full_prompt = "\n".join(prompt_parts) if prompt_parts else f"You are {char.name}."

    return CouncilMember(
        name=char.name,
        role=char.description,
        description=char.description,
        personality={},
        api_provider=char.api_provider,
        model=char.model,
        vote_weight=1.0,
        specialties=list(char.tags),
        system_prompt=full_prompt,
    )


def character_memory_name(char_name: str) -> str:
    """Return the memory directory name for a character."""
    return f"{char_name.strip().lower().replace(' ', '_')}_memory"


# ─── Prompt Builder ────────────────────────────────────────────


def build_human_chat_prompt(
    member: CouncilMember,
    messages: list[Any],
    topic: str,
    memory_context_text: str = "",
    council_members: list[str] | None = None,
    user_description: str = "",
    character_names: list[str] | None = None,
    user_name: str = "",
    summary_result: RollingSummaryResult | None = None,
) -> str:
    """Build a prompt for the council member to respond to the human.

    *messages* is ``list[HumanChatMessage]`` but typed as ``Any`` to
    avoid a circular import with ``core.human_chat``.

    When *summary_result* is provided (F-058), the prompt includes a
    compressed summary of earlier messages followed by the most recent
    raw messages, instead of the raw last-10 window.
    """
    parts = ["## Direct Conversation with Human Operator"]

    if user_description or user_name:
        label = "About the Human Operator"
        if user_name:
            label += f" ({user_name})"
        desc = user_description or "No further details provided."
        parts.append(f"\n**{label}:** {desc}")

    if topic:
        parts.append(f"**Topic:** {topic}")

    if messages:
        parts.append("\n### Conversation So Far")
        if summary_result is not None:
            # F-058: inject rolling summary + recent messages
            parts.append(
                f"[Summary of prior conversation: "
                f"{summary_result.summary_text}]"
            )
            for msg in summary_result.recent_messages:
                label = "Human" if msg.role == "human" else msg.speaker
                parts.append(f"**{label}:** {msg.content}")
        else:
            for msg in messages[-10:]:  # limit context window
                label = "Human" if msg.role == "human" else msg.speaker
                parts.append(f"**{label}:** {msg.content}")

    if memory_context_text:
        parts.append(f"\n{memory_context_text}")

    # Multi-member context — combine council members and characters
    all_participants = list(council_members or []) + list(character_names or [])
    other_members = [
        m for m in all_participants
        if m.lower() != member.name.lower()
    ]

    parts.append(f"\n---\n")
    if other_members:
        others_str = ", ".join(f"**{m}**" for m in other_members)
        parts.append(
            f"You are **{member.name}** ({member.role}). You are in a "
            f"group conversation with the human operator and {others_str}. "
            f"Read everyone's messages carefully and respond to the latest "
            f"points raised. Be concise but substantive."
        )
    else:
        parts.append(
            f"You are **{member.name}** ({member.role}). You are speaking "
            f"directly with the human operator of the Jericho AI Council. "
            f"Respond to their latest message. Be concise but substantive."
        )
    return "\n".join(parts)
