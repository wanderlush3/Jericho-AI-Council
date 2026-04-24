"""
Jericho — Reputation System (F-069)

Event-sourced reputation tracking for council members and characters.
Each entity's reputation is computed from a stream of immutable events
stored as JSONL files in ``data/reputation/``.

Key concepts:
- **ReputationEvent**: Immutable record of a reputation-relevant action
- **ReputationScore**: Computed snapshot (raw + decayed score, tier)
- **Default reputation stance**: Each entity can have a default tier
  they assign to unknown entities (e.g., Araushnee → "dubious")
- **ReputationManager**: CRUD + scoring engine, JSONL-backed
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from math import log as mathlog
from pathlib import Path
from typing import Any

from config.settings import (
    REPUTATION_DECAY_ENABLED,
    REPUTATION_DECAY_HALF_LIFE_DAYS,
    REPUTATION_DECAY_MIN_FACTOR,
    REPUTATION_DIR,
)
from core.utils import make_id_lock

log = logging.getLogger(__name__)

# ─── Event Types & Default Points ─────────────────────────────

REPUTATION_EVENT_TYPES = {
    "proposal_authored",
    "proposal_approved",
    "proposal_rejected",
    "vote_cast",
    "vote_aligned",
    "review_written",
    "gift_given",
    "gift_received",
    "discussion_participated",
    "session_participated",
    "custom",
}

REPUTATION_DEFAULT_POINTS: dict[str, int] = {
    "proposal_authored": 10,
    "proposal_approved": 5,
    "proposal_rejected": -2,
    "vote_cast": 2,
    "vote_aligned": 1,
    "review_written": 3,
    "gift_given": 5,
    "gift_received": 1,
    "discussion_participated": 2,
    "session_participated": 3,
    "custom": 0,
}

# ─── Tier Definitions ─────────────────────────────────────────

REPUTATION_TIERS: list[tuple[str, int, str]] = [
    # (tier_name, min_score, emoji)
    ("legendary",     200,  "⭐"),
    ("distinguished", 100,  "🏆"),
    ("respected",      50,  "✨"),
    ("neutral",         0,  "👤"),
    ("dubious",       -25,  "⚠️"),
    ("disgraced",  -999999,  "🚫"),
]

# Valid tiers for default_reputation_stance
VALID_DEFAULT_STANCES = {"disgraced", "dubious", "neutral", "respected"}


def tier_for_score(score: float) -> tuple[str, str]:
    """Return (tier_name, emoji) for a given decayed score."""
    for name, min_score, emoji in REPUTATION_TIERS:
        if score >= min_score:
            return name, emoji
    return "disgraced", "🚫"


def tier_emoji(tier_name: str) -> str:
    """Return emoji for a tier name."""
    for name, _, emoji in REPUTATION_TIERS:
        if name == tier_name:
            return emoji
    return "👤"


# ─── Data Models ──────────────────────────────────────────────


@dataclass(frozen=True)
class ReputationEvent:
    """An immutable record of a reputation-relevant action."""

    id: str
    entity_id: str          # "member:Sage" or "character:CH-0001"
    event_type: str         # from REPUTATION_EVENT_TYPES
    points: int             # positive or negative
    reason: str             # human-readable
    source_id: str = ""     # reference to originating object
    timestamp: str = ""     # ISO 8601 UTC

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReputationEvent:
        return cls(
            id=data["id"],
            entity_id=data["entity_id"],
            event_type=data["event_type"],
            points=data["points"],
            reason=data.get("reason", ""),
            source_id=data.get("source_id", ""),
            timestamp=data.get("timestamp", ""),
        )

    @classmethod
    def create(
        cls,
        *,
        id: str,
        entity_id: str,
        event_type: str,
        points: int,
        reason: str = "",
        source_id: str = "",
    ) -> ReputationEvent:
        """Factory with timestamp auto-fill."""
        now = datetime.now(timezone.utc).isoformat()
        return cls(
            id=id,
            entity_id=entity_id,
            event_type=event_type,
            points=points,
            reason=reason,
            source_id=source_id,
            timestamp=now,
        )


@dataclass(frozen=True)
class ReputationScore:
    """Computed reputation snapshot for an entity."""

    entity_id: str
    raw_score: int
    decayed_score: float
    tier: str
    tier_emoji: str
    event_count: int
    last_event_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ─── Reputation Manager ──────────────────────────────────────


class ReputationError(Exception):
    """Base exception for reputation errors."""


class ReputationValidationError(ReputationError):
    """Raised when reputation data fails validation."""

    def __init__(self, errors: list[str] | str) -> None:
        if isinstance(errors, str):
            errors = [errors]
        self.errors = errors
        super().__init__("; ".join(errors))


class ReputationManager:
    """Event-sourced reputation tracker with JSONL storage.

    Each entity gets one JSONL file in the reputation directory.
    Events are append-only; scores are computed on demand.

    Usage::

        mgr = ReputationManager()
        event = mgr.record_event("member:Sage", "vote_cast", reason="Voted on P-0001")
        score = mgr.get_score("member:Sage")
        board = mgr.get_leaderboard()
    """

    _ID_PATTERN = re.compile(r"^REP-(\d{6})$")

    def __init__(
        self,
        reputation_dir: Path | None = None,
        *,
        decay_enabled: bool | None = None,
        decay_half_life_days: float | None = None,
        decay_min_factor: float | None = None,
    ) -> None:
        self._dir = reputation_dir or REPUTATION_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._id_lock = make_id_lock()
        self._decay_enabled = decay_enabled if decay_enabled is not None else REPUTATION_DECAY_ENABLED
        self._decay_half_life_days = decay_half_life_days if decay_half_life_days is not None else REPUTATION_DECAY_HALF_LIFE_DAYS
        self._decay_min_factor = decay_min_factor if decay_min_factor is not None else REPUTATION_DECAY_MIN_FACTOR

    @property
    def directory(self) -> Path:
        return self._dir

    @property
    def decay_enabled(self) -> bool:
        return self._decay_enabled

    @property
    def decay_half_life_days(self) -> float:
        return self._decay_half_life_days

    # ── Record Event ──────────────────────────────────────────

    def record_event(
        self,
        entity_id: str,
        event_type: str,
        *,
        points: int | None = None,
        reason: str = "",
        source_id: str = "",
    ) -> ReputationEvent:
        """Record a reputation event for an entity.

        Args:
            entity_id: e.g. "member:Sage" or "character:CH-0001"
            event_type: from REPUTATION_EVENT_TYPES
            points: override default points (if None, uses REPUTATION_DEFAULT_POINTS)
            reason: human-readable explanation
            source_id: optional reference to originating object

        Returns:
            The created ReputationEvent.

        Raises:
            ReputationValidationError: if entity_id or event_type is invalid.
        """
        errors: list[str] = []
        if not entity_id or not entity_id.strip():
            errors.append("entity_id must not be empty.")
        if event_type not in REPUTATION_EVENT_TYPES:
            errors.append(
                f"Unknown event_type '{event_type}'. "
                f"Must be one of: {', '.join(sorted(REPUTATION_EVENT_TYPES))}"
            )
        if errors:
            raise ReputationValidationError(errors)

        if points is None:
            points = REPUTATION_DEFAULT_POINTS.get(event_type, 0)

        with self._id_lock:
            event_id = self._next_id()
            event = ReputationEvent.create(
                id=event_id,
                entity_id=entity_id.strip(),
                event_type=event_type,
                points=points,
                reason=reason,
                source_id=source_id,
            )
            self._append_event(event)
        return event

    # ── Score Retrieval ───────────────────────────────────────

    def get_score(self, entity_id: str) -> ReputationScore:
        """Compute the current reputation score for an entity."""
        events = self._load_events(entity_id)
        return self._compute_score(entity_id, events)

    def get_events(
        self, entity_id: str, *, limit: int = 50,
    ) -> list[ReputationEvent]:
        """Return events for an entity, most recent first."""
        events = self._load_events(entity_id)
        events.reverse()
        return events[:limit]

    def get_leaderboard(self, *, limit: int = 50) -> list[ReputationScore]:
        """Return all entities sorted by decayed score, descending."""
        scores: list[ReputationScore] = []
        for filepath in sorted(self._dir.glob("*.jsonl")):
            entity_id = self._entity_id_from_filename(filepath.stem)
            if not entity_id:
                continue
            events = self._load_events_from_file(filepath)
            score = self._compute_score(entity_id, events)
            scores.append(score)
        scores.sort(key=lambda s: s.decayed_score, reverse=True)
        return scores[:limit]

    def get_perceived_tier(
        self,
        perceiver_name: str,
        target_entity_id: str,
        *,
        default_stances: dict[str, str] | None = None,
    ) -> tuple[str, str]:
        """Return the tier a perceiver would assign to a target.

        If the target has recorded events, returns their actual tier.
        If not, returns the perceiver's default stance (from default_stances
        dict, keyed by lowercased perceiver name).

        Args:
            perceiver_name: The entity doing the perceiving (e.g. "Sage")
            target_entity_id: The entity being perceived (e.g. "member:Logic")
            default_stances: Optional dict of {perceiver_name_lower: tier_name}

        Returns:
            Tuple of (tier_name, emoji)
        """
        events = self._load_events(target_entity_id)
        if events:
            score = self._compute_score(target_entity_id, events)
            return score.tier, score.tier_emoji

        # No events — use perceiver's default stance
        if default_stances:
            stance = default_stances.get(perceiver_name.strip().lower(), "neutral")
            if stance in VALID_DEFAULT_STANCES:
                return stance, tier_emoji(stance)

        return "neutral", "👤"

    # ── Internal: Score Computation ───────────────────────────

    def _compute_score(
        self, entity_id: str, events: list[ReputationEvent],
    ) -> ReputationScore:
        """Compute raw and decayed score from a list of events."""
        if not events:
            return ReputationScore(
                entity_id=entity_id,
                raw_score=0,
                decayed_score=0.0,
                tier="neutral",
                tier_emoji="👤",
                event_count=0,
                last_event_at="",
            )

        raw_score = sum(e.points for e in events)
        decayed_score = sum(
            e.points * self._decay_factor(e.timestamp) for e in events
        )
        decayed_score = round(decayed_score, 2)

        tier_name, emoji = tier_for_score(decayed_score)
        last_event = max(events, key=lambda e: e.timestamp or "")

        return ReputationScore(
            entity_id=entity_id,
            raw_score=raw_score,
            decayed_score=decayed_score,
            tier=tier_name,
            tier_emoji=emoji,
            event_count=len(events),
            last_event_at=last_event.timestamp,
        )

    def _decay_factor(self, timestamp: str) -> float:
        """Compute time-based decay factor for an event timestamp."""
        if not self._decay_enabled:
            return 1.0
        if not timestamp:
            return 1.0
        try:
            event_time = datetime.fromisoformat(timestamp)
            now = datetime.now(timezone.utc)
            age_days = (now - event_time).total_seconds() / 86400
            if age_days <= 0:
                return 1.0
            # Half-life decay: factor = 0.5 ^ (age / half_life)
            factor = 0.5 ** (age_days / self._decay_half_life_days)
            return max(self._decay_min_factor, factor)
        except (ValueError, TypeError):
            return 1.0

    # ── Internal: Storage ─────────────────────────────────────

    def _entity_filename(self, entity_id: str) -> str:
        """Convert entity_id to a safe filename stem."""
        # "member:Sage" → "member_sage"
        # "character:CH-0001" → "character_ch-0001"
        safe = entity_id.lower().replace(":", "_").replace(" ", "_")
        # Remove any remaining unsafe chars
        safe = re.sub(r"[^\w\-]", "", safe)
        return safe

    def _entity_id_from_filename(self, stem: str) -> str | None:
        """Reverse the filename back to an entity_id (best-effort)."""
        # "member_sage" → "member:sage"
        if "_" not in stem:
            return None
        parts = stem.split("_", 1)
        if len(parts) != 2:
            return None
        return f"{parts[0]}:{parts[1]}"

    def _entity_filepath(self, entity_id: str) -> Path:
        """Return the JSONL file path for an entity."""
        return self._dir / f"{self._entity_filename(entity_id)}.jsonl"

    def _append_event(self, event: ReputationEvent) -> None:
        """Append a single event as a JSON line."""
        filepath = self._entity_filepath(event.entity_id)
        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(line)

    def _load_events(self, entity_id: str) -> list[ReputationEvent]:
        """Load all events for an entity from its JSONL file."""
        filepath = self._entity_filepath(entity_id)
        return self._load_events_from_file(filepath)

    def _load_events_from_file(self, filepath: Path) -> list[ReputationEvent]:
        """Load all events from a JSONL file."""
        if not filepath.exists():
            return []
        events: list[ReputationEvent] = []
        try:
            text = filepath.read_text(encoding="utf-8")
            for line in text.strip().split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    events.append(ReputationEvent.from_dict(data))
                except (json.JSONDecodeError, KeyError):
                    log.debug("Skipping corrupt reputation event line", exc_info=True)
        except Exception:
            log.debug("Error reading reputation file %s", filepath, exc_info=True)
        return events

    def _next_id(self) -> str:
        """Generate next sequential REP-XXXXXX id."""
        max_num = 0
        for filepath in self._dir.glob("*.jsonl"):
            try:
                text = filepath.read_text(encoding="utf-8")
                for line in text.strip().split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        eid = data.get("id", "")
                        m = self._ID_PATTERN.match(eid)
                        if m:
                            max_num = max(max_num, int(m.group(1)))
                    except (json.JSONDecodeError, KeyError):
                        continue
            except Exception:
                log.debug("reputation._next_id: failed data", exc_info=True)
                continue
        return f"REP-{max_num + 1:06d}"

    # ── Dunder ────────────────────────────────────────────────

    def __repr__(self) -> str:
        count = len(list(self._dir.glob("*.jsonl")))
        return (
            f"ReputationManager(entities={count}, "
            f"decay={'on' if self._decay_enabled else 'off'}, "
            f"half_life={self._decay_half_life_days}d, "
            f"dir={self._dir})"
        )
