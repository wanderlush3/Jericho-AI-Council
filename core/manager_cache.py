"""
Jericho — Manager Cache

Lazy-init singleton store for frequently-used managers.  Each manager
is created once on first access and reused across all API requests.
Mutation endpoints call the corresponding ``invalidate_*()`` function
so the next read sees fresh data.

This eliminates the per-request overhead of re-reading YAML/JSON data
directories for every API call.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.api_client import APIClient
    from core.characters import CharacterManager
    from core.items import ItemManager
    from core.laws import LawManager
    from core.locations import LocationManager
    from core.memory_influence import MemoryInfluence
    from core.proposals import ProposalManager
    from core.registry import CouncilRegistry
    from core.reputation import ReputationManager
    from core.stores import StoreManager
    from core.story import StoryManager
    from core.treasury import TreasuryManager
    from core.voting import VotingEngine

_lock = threading.Lock()

# ── Internal state ────────────────────────────────────────────

_registry: CouncilRegistry | None = None
_api_client: APIClient | None = None
_character_manager: CharacterManager | None = None
_location_manager: LocationManager | None = None
_item_manager: ItemManager | None = None
_law_manager: LawManager | None = None
_story_manager: StoryManager | None = None
_proposal_manager: ProposalManager | None = None
_voting_engine: VotingEngine | None = None
_treasury_manager: TreasuryManager | None = None
_store_manager: StoreManager | None = None
_memory_influence: MemoryInfluence | None = None
_reputation_manager: ReputationManager | None = None


# ── Accessors ─────────────────────────────────────────────────


def get_registry() -> CouncilRegistry:
    """Return the cached CouncilRegistry, loading if needed."""
    global _registry
    if _registry is None:
        with _lock:
            if _registry is None:
                from core.registry import CouncilRegistry
                _registry = CouncilRegistry().load()
    return _registry


def get_api_client() -> APIClient:
    """Return the cached APIClient."""
    global _api_client
    if _api_client is None:
        with _lock:
            if _api_client is None:
                from core.api_client import APIClient
                _api_client = APIClient()
    return _api_client


def get_character_manager() -> CharacterManager:
    """Return the cached CharacterManager."""
    global _character_manager
    if _character_manager is None:
        with _lock:
            if _character_manager is None:
                from core.characters import CharacterManager
                _character_manager = CharacterManager()
    return _character_manager


def get_location_manager() -> LocationManager:
    """Return the cached LocationManager."""
    global _location_manager
    if _location_manager is None:
        with _lock:
            if _location_manager is None:
                from core.locations import LocationManager
                _location_manager = LocationManager()
    return _location_manager


def get_item_manager() -> ItemManager:
    """Return the cached ItemManager."""
    global _item_manager
    if _item_manager is None:
        with _lock:
            if _item_manager is None:
                from core.items import ItemManager
                _item_manager = ItemManager()
    return _item_manager


def get_law_manager() -> LawManager:
    """Return the cached LawManager."""
    global _law_manager
    if _law_manager is None:
        with _lock:
            if _law_manager is None:
                from core.laws import LawManager
                _law_manager = LawManager()
    return _law_manager


def get_story_manager() -> StoryManager:
    """Return the cached StoryManager."""
    global _story_manager
    if _story_manager is None:
        with _lock:
            if _story_manager is None:
                from core.story import StoryManager
                _story_manager = StoryManager()
    return _story_manager


def get_proposal_manager() -> ProposalManager:
    """Return the cached ProposalManager."""
    global _proposal_manager
    if _proposal_manager is None:
        with _lock:
            if _proposal_manager is None:
                from core.proposals import ProposalManager
                _proposal_manager = ProposalManager()
    return _proposal_manager


def get_voting_engine() -> VotingEngine:
    """Return the cached VotingEngine."""
    global _voting_engine
    if _voting_engine is None:
        with _lock:
            if _voting_engine is None:
                from core.voting import VotingEngine
                _voting_engine = VotingEngine()
    return _voting_engine


def get_treasury_manager() -> TreasuryManager:
    """Return the cached TreasuryManager."""
    global _treasury_manager
    if _treasury_manager is None:
        with _lock:
            if _treasury_manager is None:
                from core.treasury import TreasuryManager
                _treasury_manager = TreasuryManager()
    return _treasury_manager


def get_store_manager() -> StoreManager:
    """Return the cached StoreManager."""
    global _store_manager
    if _store_manager is None:
        with _lock:
            if _store_manager is None:
                from core.stores import StoreManager
                _store_manager = StoreManager()
    return _store_manager


def get_memory_influence() -> MemoryInfluence:
    """Return the cached MemoryInfluence engine."""
    global _memory_influence
    if _memory_influence is None:
        with _lock:
            if _memory_influence is None:
                from core.memory_influence import MemoryInfluence
                _memory_influence = MemoryInfluence()
    return _memory_influence


def get_reputation_manager() -> ReputationManager:
    """Return the cached ReputationManager."""
    global _reputation_manager
    if _reputation_manager is None:
        with _lock:
            if _reputation_manager is None:
                from core.reputation import ReputationManager
                _reputation_manager = ReputationManager()
    return _reputation_manager


# ── Invalidation ──────────────────────────────────────────────
# Call these from mutation endpoints (POST/PUT/DELETE) so the
# next read picks up fresh data.


def invalidate_registry() -> None:
    """Clear the cached CouncilRegistry."""
    global _registry
    with _lock:
        _registry = None


def invalidate_character_manager() -> None:
    """Clear the cached CharacterManager."""
    global _character_manager
    with _lock:
        _character_manager = None


def invalidate_location_manager() -> None:
    """Clear the cached LocationManager."""
    global _location_manager
    with _lock:
        _location_manager = None


def invalidate_item_manager() -> None:
    """Clear the cached ItemManager."""
    global _item_manager
    with _lock:
        _item_manager = None


def invalidate_law_manager() -> None:
    """Clear the cached LawManager."""
    global _law_manager
    with _lock:
        _law_manager = None


def invalidate_story_manager() -> None:
    """Clear the cached StoryManager."""
    global _story_manager
    with _lock:
        _story_manager = None


def invalidate_proposal_manager() -> None:
    """Clear the cached ProposalManager."""
    global _proposal_manager
    with _lock:
        _proposal_manager = None


def invalidate_voting_engine() -> None:
    """Clear the cached VotingEngine."""
    global _voting_engine
    with _lock:
        _voting_engine = None


def invalidate_treasury_manager() -> None:
    """Clear the cached TreasuryManager."""
    global _treasury_manager
    with _lock:
        _treasury_manager = None


def invalidate_store_manager() -> None:
    """Clear the cached StoreManager."""
    global _store_manager
    with _lock:
        _store_manager = None


def invalidate_memory_influence() -> None:
    """Clear the cached MemoryInfluence."""
    global _memory_influence
    with _lock:
        _memory_influence = None


def invalidate_reputation_manager() -> None:
    """Clear the cached ReputationManager."""
    global _reputation_manager
    with _lock:
        _reputation_manager = None


def invalidate_all() -> None:
    """Clear all cached managers (useful for testing)."""
    invalidate_registry()
    invalidate_character_manager()
    invalidate_location_manager()
    invalidate_item_manager()
    invalidate_law_manager()
    invalidate_story_manager()
    invalidate_proposal_manager()
    invalidate_voting_engine()
    invalidate_treasury_manager()
    invalidate_store_manager()
    invalidate_memory_influence()
    invalidate_reputation_manager()
    global _api_client
    with _lock:
        _api_client = None
