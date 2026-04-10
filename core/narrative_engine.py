"""
Jericho -- Emergent Narrative Engine

Template-driven narrative layer that aggregates recent in-world events
(proposals, votes, council sessions, treasury activity, items, etc.)
and produces flavourful "news bulletins" for the Dashboard.

No LLM calls -- all narrative is generated from templates with
randomised selection for variety.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any


# --- Data Models -----------------------------------------------------------


@dataclass(frozen=True)
class NarrativeBulletin:
    """A single news bulletin for the dashboard ticker."""

    headline: str
    body: str
    source_type: str        # "proposal", "vote", "session", "character", "item", "treasury", "location"
    source_id: str          # e.g. "P-0001", "CH-0001"
    timestamp: str          # ISO 8601
    icon: str               # emoji icon

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NarrativeBulletin":
        return cls(
            headline=data["headline"],
            body=data["body"],
            source_type=data["source_type"],
            source_id=data["source_id"],
            timestamp=data["timestamp"],
            icon=data["icon"],
        )


# --- Template Banks -------------------------------------------------------

_PROPOSAL_CREATED_TEMPLATES = [
    '{author} tabled a new {category} proposal: "{title}".',
    'A fresh {category} proposal from {author} has appeared on the docket: "{title}".',
    'Breaking: {author} submits "{title}" for council deliberation.',
    'The halls of governance stir -- {author} introduces "{title}".',
    'New motion on the floor: {author} proposes "{title}" under {category}.',
]

_PROPOSAL_DECIDED_TEMPLATES = [
    'The Council has rendered its verdict on "{title}".',
    '"{title}" has been decided -- the gavel has fallen.',
    'After deliberation, the Council has ruled on "{title}".',
    'The fate of "{title}" is sealed -- decision rendered.',
]

_VOTE_APPROVED_TEMPLATES = [
    'The Council voted {for_count}-{against_count} to approve "{title}". {dissent_line}',
    '"{title}" passes with {approval_pct}% approval. {dissent_line}',
    'Motion carried: "{title}" garners {for_count} ayes against {against_count} nays. {dissent_line}',
    'Victory for proponents -- "{title}" clears the threshold at {approval_pct}%. {dissent_line}',
]

_VOTE_REJECTED_TEMPLATES = [
    'The Council struck down "{title}" with {against_count} votes against. {dissent_line}',
    '"{title}" fails to pass -- {approval_pct}% fell short of the threshold. {dissent_line}',
    'Motion denied: "{title}" rejected by the Council. {dissent_line}',
    'The nays prevail -- "{title}" is voted down {against_count}-{for_count}. {dissent_line}',
]

_VOTE_VETOED_TEMPLATES = [
    'VETO: "{title}" has been overridden by executive veto. {reason_line}',
    'The Human Veto falls on "{title}". {reason_line}',
    'Despite council deliberation, "{title}" is struck down by veto power. {reason_line}',
]

_CHARACTER_CREATED_TEMPLATES = [
    "A new character emerges from the creative forge: {name}.",
    "Meet {name} -- the latest creation from the council's imagination.",
    "The roster grows: {name} steps into the world. {desc_line}",
    "From draft to existence -- {name} is born. {desc_line}",
]

_CHARACTER_ACTIVATED_TEMPLATES = [
    "{name} has been activated and is now live in the world.",
    "Status update: {name} transitions to active duty.",
    "{name} steps out of the workshop and into the spotlight.",
]

_ITEM_CREATED_TEMPLATES = [
    "A new item has been forged: {name}. {desc_line}",
    "The craftsmen present: {name}. {desc_line}",
    "Fresh from the workshop -- {name} enters the inventory. {desc_line}",
    "New acquisition catalogued: {name}. {desc_line}",
]

_LOCATION_CREATED_TEMPLATES = [
    "A new location has been charted: {name}. {desc_line}",
    "Cartographers report: {name} added to the map. {desc_line}",
    "Explorers have discovered {name}. {desc_line}",
    "The world expands -- {name} is now on the map. {desc_line}",
]

_TREASURY_TEMPLATES = [
    "The Government Treasury holds {gold}G {silver}S {bronze}B in Obelisk reserves.",
    "Treasury Report: {total_accounts} accounts active, Government coffers at {gold} Gold.",
    "Obelisk Update: The realm's finances stand at {gold}G across {total_accounts} accounts.",
]

_DISSENT_TEMPLATES = [
    "{voter}'s dissent was sharp: 'This is not what the council should pursue.'",
    "{voter} voted against, remarking: 'I have reservations about this direction.'",
    "{voter} stood in opposition, citing concerns about the approach.",
    "{voter} cast a dissenting vote, urging caution.",
    "Notable opposition came from {voter}.",
]

_FLAVOR_SUFFIXES = [
    "Meanwhile, the corridors of power hum with whispered debates...",
    "The council chambers echo with the weight of governance.",
    "Scribes record the proceedings for the annals of Jericho.",
    "The Obelisk markets stir in response to the news.",
    "Council watchers await the next session with bated breath.",
    "The archives grow thicker by the day.",
    "",  # sometimes no suffix
    "",
    "",
]


# --- Narrative Engine ------------------------------------------------------


class NarrativeEngine:
    """
    Aggregates recent events from Jericho's data managers and produces
    template-driven news bulletins for the Dashboard.

    All methods are read-only -- no data is written to disk.

    Usage::

        engine = NarrativeEngine(max_bulletins=10, max_age_days=30)
        bulletins = engine.generate_bulletins()  # list[NarrativeBulletin]
    """

    def __init__(
        self,
        *,
        max_bulletins: int = 10,
        max_age_days: int = 30,
    ) -> None:
        self._max_bulletins = max_bulletins
        self._max_age_days = max_age_days

    # -- Public API --------------------------------------------------------

    def generate_bulletins(self) -> list[NarrativeBulletin]:
        """
        Scan all data sources and produce narrative bulletins,
        sorted newest-first, capped at max_bulletins.
        """
        bulletins: list[NarrativeBulletin] = []

        bulletins.extend(self._proposal_bulletins())
        bulletins.extend(self._vote_bulletins())
        bulletins.extend(self._character_bulletins())
        bulletins.extend(self._item_bulletins())
        bulletins.extend(self._location_bulletins())
        bulletins.extend(self._treasury_bulletins())

        # Sort newest-first by timestamp
        bulletins.sort(key=lambda b: b.timestamp, reverse=True)

        # Cap at max
        return bulletins[: self._max_bulletins]

    # -- Proposal Bulletins ------------------------------------------------

    def _proposal_bulletins(self) -> list[NarrativeBulletin]:
        bulletins: list[NarrativeBulletin] = []
        try:
            from core.proposals import ProposalManager
            pmgr = ProposalManager()
            proposals = pmgr.list_proposals()

            cutoff = self._cutoff_time()

            for p in proposals:
                ts = p.created_at or p.updated_at or ""
                if not self._is_within_window(ts, cutoff):
                    continue

                if p.status == "decided":
                    template = random.choice(_PROPOSAL_DECIDED_TEMPLATES)
                    headline = template.format(
                        title=p.title, author=p.author, category=p.category,
                    )
                    suffix = random.choice(_FLAVOR_SUFFIXES)
                    body = p.description + (" " + suffix if suffix else "")
                    bulletins.append(NarrativeBulletin(
                        headline=headline, body=body,
                        source_type="proposal", source_id=p.id,
                        timestamp=ts, icon="📜",
                    ))
                elif p.status in ("open", "under_review"):
                    template = random.choice(_PROPOSAL_CREATED_TEMPLATES)
                    headline = template.format(
                        title=p.title, author=p.author, category=p.category,
                    )
                    suffix = random.choice(_FLAVOR_SUFFIXES)
                    body = p.description + (" " + suffix if suffix else "")
                    bulletins.append(NarrativeBulletin(
                        headline=headline, body=body,
                        source_type="proposal", source_id=p.id,
                        timestamp=ts, icon="📜",
                    ))
        except Exception:
            pass  # graceful degradation
        return bulletins

    # -- Vote Bulletins ----------------------------------------------------

    def _vote_bulletins(self) -> list[NarrativeBulletin]:
        bulletins: list[NarrativeBulletin] = []
        try:
            from core.voting import VotingEngine
            from core.proposals import ProposalManager
            engine = VotingEngine()
            pmgr = ProposalManager()
            records = engine.list_records()
            cutoff = self._cutoff_time()

            for rec in records:
                if rec.status != "closed":
                    continue

                ts = rec.closed_at or rec.opened_at or ""
                if not self._is_within_window(ts, cutoff):
                    continue

                # Get proposal title
                title = rec.proposal_id
                try:
                    proposal = pmgr.get(rec.proposal_id)
                    title = proposal.title
                except Exception:
                    pass

                # Compute tally
                tally = engine._compute_tally(rec)
                for_count = tally.votes_for
                against_count = tally.votes_against
                approval_pct = round((tally.approval_rate or 0) * 100)

                # Build dissent line
                dissent_line = ""
                against_voters = [
                    v.voter for v in rec.votes if v.choice == "against"
                ]
                if against_voters:
                    dissenter = random.choice(against_voters)
                    dissent_line = random.choice(
                        _DISSENT_TEMPLATES
                    ).format(voter=dissenter)

                if rec.vetoed:
                    template = random.choice(_VOTE_VETOED_TEMPLATES)
                    reason_line = ""
                    if rec.veto_reason:
                        reason_line = 'Reason: "' + rec.veto_reason + '"'
                    headline = template.format(
                        title=title, reason_line=reason_line,
                    )
                    body = (
                        "The veto overrides the council's vote on "
                        + rec.proposal_id + "."
                    )
                    icon = "🚫"
                elif tally.approved:
                    template = random.choice(_VOTE_APPROVED_TEMPLATES)
                    headline = template.format(
                        title=title, for_count=for_count,
                        against_count=against_count,
                        approval_pct=approval_pct,
                        dissent_line=dissent_line,
                    )
                    body = (
                        "Proposal " + rec.proposal_id
                        + " passes with " + str(approval_pct) + "% approval."
                    )
                    icon = "✅"
                else:
                    template = random.choice(_VOTE_REJECTED_TEMPLATES)
                    headline = template.format(
                        title=title, for_count=for_count,
                        against_count=against_count,
                        approval_pct=approval_pct,
                        dissent_line=dissent_line,
                    )
                    body = (
                        "Proposal " + rec.proposal_id
                        + " fails with only " + str(approval_pct)
                        + "% approval."
                    )
                    icon = "❌"

                bulletins.append(NarrativeBulletin(
                    headline=headline, body=body,
                    source_type="vote", source_id=rec.proposal_id,
                    timestamp=ts, icon=icon,
                ))
        except Exception:
            pass
        return bulletins

    # -- Character Bulletins -----------------------------------------------

    def _character_bulletins(self) -> list[NarrativeBulletin]:
        bulletins: list[NarrativeBulletin] = []
        try:
            from core.characters import CharacterManager
            cmgr = CharacterManager()
            chars = cmgr.list_characters()
            cutoff = self._cutoff_time()

            for c in chars:
                ts = c.created_at or ""
                if not self._is_within_window(ts, cutoff):
                    continue

                desc_line = ""
                if c.description:
                    desc_line = "'" + c.description + "'"

                if c.status == "active":
                    template = random.choice(_CHARACTER_ACTIVATED_TEMPLATES)
                    headline = template.format(name=c.name, desc_line=desc_line)
                    body = desc_line or (c.name + " is now active.")
                elif c.status == "draft":
                    template = random.choice(_CHARACTER_CREATED_TEMPLATES)
                    headline = template.format(name=c.name, desc_line=desc_line)
                    body = desc_line or (c.name + " awaits activation.")
                else:
                    continue  # skip archived/superseded

                bulletins.append(NarrativeBulletin(
                    headline=headline, body=body,
                    source_type="character", source_id=c.id,
                    timestamp=ts, icon="🎭",
                ))
        except Exception:
            pass
        return bulletins

    # -- Item Bulletins ----------------------------------------------------

    def _item_bulletins(self) -> list[NarrativeBulletin]:
        bulletins: list[NarrativeBulletin] = []
        try:
            from core.items import ItemManager
            imgr = ItemManager()
            items = imgr.list_items()
            cutoff = self._cutoff_time()

            for item in items:
                ts = item.created_at or ""
                if not self._is_within_window(ts, cutoff):
                    continue
                if item.status not in ("draft", "active"):
                    continue

                desc_line = ""
                if item.description:
                    desc_line = "'" + item.description + "'"

                template = random.choice(_ITEM_CREATED_TEMPLATES)
                headline = template.format(name=item.name, desc_line=desc_line)
                body = desc_line or (item.name + " has been catalogued.")

                bulletins.append(NarrativeBulletin(
                    headline=headline, body=body,
                    source_type="item", source_id=item.id,
                    timestamp=ts, icon="📦",
                ))
        except Exception:
            pass
        return bulletins

    # -- Location Bulletins ------------------------------------------------

    def _location_bulletins(self) -> list[NarrativeBulletin]:
        bulletins: list[NarrativeBulletin] = []
        try:
            from core.locations import LocationManager
            lmgr = LocationManager()
            locs = lmgr.list_locations()
            cutoff = self._cutoff_time()

            for loc in locs:
                ts = loc.created_at or ""
                if not self._is_within_window(ts, cutoff):
                    continue
                if loc.status not in ("draft", "active"):
                    continue

                desc_line = ""
                if loc.description:
                    desc_line = "'" + loc.description + "'"

                template = random.choice(_LOCATION_CREATED_TEMPLATES)
                headline = template.format(name=loc.name, desc_line=desc_line)
                body = desc_line or (loc.name + " awaits exploration.")

                bulletins.append(NarrativeBulletin(
                    headline=headline, body=body,
                    source_type="location", source_id=loc.id,
                    timestamp=ts, icon="🗺️",
                ))
        except Exception:
            pass
        return bulletins

    # -- Treasury Bulletins ------------------------------------------------

    def _treasury_bulletins(self) -> list[NarrativeBulletin]:
        bulletins: list[NarrativeBulletin] = []
        try:
            from core.treasury import TreasuryManager
            tmgr = TreasuryManager()
            accounts = tmgr.list_accounts()

            if not accounts:
                return bulletins

            gov_accounts = [
                a for a in accounts if a.account_type == "government"
            ]
            if gov_accounts:
                gov = gov_accounts[0]
                bal = gov.balance
                template = random.choice(_TREASURY_TEMPLATES)
                headline = template.format(
                    gold=bal.gold, silver=bal.silver, bronze=bal.bronze,
                    total_accounts=len(accounts),
                )
                body = (
                    "The Obelisk Treasury manages "
                    + str(len(accounts)) + " active accounts."
                )
                now = datetime.now(timezone.utc).isoformat()

                bulletins.append(NarrativeBulletin(
                    headline=headline, body=body,
                    source_type="treasury", source_id="government",
                    timestamp=now, icon="🪙",
                ))
        except Exception:
            pass
        return bulletins

    # -- Helpers -----------------------------------------------------------

    def _cutoff_time(self) -> datetime:
        """Return the earliest timestamp we care about."""
        return datetime.now(timezone.utc) - timedelta(days=self._max_age_days)

    @staticmethod
    def _is_within_window(ts: str, cutoff: datetime) -> bool:
        """Check if a timestamp string falls within the window."""
        if not ts:
            return True  # no timestamp -> include it
        try:
            dt = datetime.fromisoformat(ts)
            # Ensure timezone-aware comparison
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt >= cutoff
        except (ValueError, TypeError):
            return True  # can't parse -> include it

    def __repr__(self) -> str:
        return (
            "NarrativeEngine(max_bulletins="
            + str(self._max_bulletins)
            + ", max_age_days="
            + str(self._max_age_days)
            + ")"
        )
