"""
Jericho — Web Dashboard API (F-021)

FastAPI application serving JSON endpoints that wrap existing managers,
plus static files for the single-page dashboard frontend.

Launch via CLI: ``jericho web``
Or directly:  ``uvicorn core.web_api:app --port 8080``
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config.settings import (
    CHARACTERS_DIR,
    COUNCIL_MEMBERS_DIR,
    PROPOSALS_DIR,
    VOTES_DIR,
    WEB_STATIC_DIR,
)

# ─── App Factory ──────────────────────────────────────────────


def create_app() -> FastAPI:
    """Build and return the FastAPI application."""

    application = FastAPI(
        title="Jericho AI Council",
        description="Web dashboard for the Jericho AI Council governance system.",
        version="0.1.0",
    )

    # ── Status ────────────────────────────────────────────────

    @application.get("/api/status")
    def api_status() -> dict[str, Any]:
        """Project overview — counts of members, proposals, votes, characters."""
        data: dict[str, Any] = {}

        try:
            from core.registry import CouncilRegistry
            registry = CouncilRegistry().load()
            members = registry.list_members()
            providers: dict[str, int] = {}
            for m in members:
                providers[m.api_provider] = providers.get(m.api_provider, 0) + 1
            data["members"] = {
                "count": len(members),
                "providers": providers,
            }
        except Exception:
            data["members"] = {"count": 0, "providers": {}}

        try:
            from core.proposals import ProposalManager
            pmgr = ProposalManager()
            proposals = pmgr.list_proposals()
            by_status: dict[str, int] = {}
            by_category: dict[str, int] = {}
            for p in proposals:
                by_status[p.status] = by_status.get(p.status, 0) + 1
                by_category[p.category] = by_category.get(p.category, 0) + 1
            data["proposals"] = {
                "count": len(proposals),
                "by_status": by_status,
                "by_category": by_category,
            }
        except Exception:
            data["proposals"] = {"count": 0, "by_status": {}, "by_category": {}}

        try:
            from core.voting import VotingEngine
            engine = VotingEngine()
            records = engine.list_records()
            vote_statuses: dict[str, int] = {}
            for r in records:
                vote_statuses[r.status] = vote_statuses.get(r.status, 0) + 1
            data["votes"] = {
                "count": len(records),
                "by_status": vote_statuses,
            }
        except Exception:
            data["votes"] = {"count": 0, "by_status": {}}

        try:
            from core.characters import CharacterManager
            cmgr = CharacterManager()
            chars = cmgr.list_characters()
            char_statuses: dict[str, int] = {}
            for c in chars:
                char_statuses[c.status] = char_statuses.get(c.status, 0) + 1
            data["characters"] = {
                "count": len(chars),
                "by_status": char_statuses,
            }
        except Exception:
            data["characters"] = {"count": 0, "by_status": {}}

        return data

    # ── Council ───────────────────────────────────────────────

    @application.get("/api/council")
    def api_council_list() -> list[dict[str, Any]]:
        """List all council members."""
        from core.registry import CouncilRegistry
        registry = CouncilRegistry().load()
        members = registry.list_members()
        return [
            {
                "name": m.name,
                "role": m.role,
                "description": m.description,
                "personality": m.personality,
                "api_provider": m.api_provider,
                "model": m.model,
                "vote_weight": m.vote_weight,
                "specialties": m.specialties,
                "system_prompt": m.system_prompt,
            }
            for m in members
        ]

    @application.get("/api/council/{name}")
    def api_council_detail(name: str) -> dict[str, Any]:
        """Get a single council member by name."""
        from core.registry import CouncilRegistry, MemberNotFoundError
        registry = CouncilRegistry().load()
        try:
            m = registry.get(name)
        except MemberNotFoundError:
            raise HTTPException(status_code=404, detail=f"Council member '{name}' not found.")
        return {
            "name": m.name,
            "role": m.role,
            "description": m.description,
            "personality": m.personality,
            "api_provider": m.api_provider,
            "model": m.model,
            "vote_weight": m.vote_weight,
            "specialties": m.specialties,
            "system_prompt": m.system_prompt,
        }

    # ── Proposals ─────────────────────────────────────────────

    @application.get("/api/proposals")
    def api_proposals_list(
        status: str | None = Query(None),
        category: str | None = Query(None),
        author: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List proposals with optional filters."""
        from core.proposals import ProposalManager
        mgr = ProposalManager()
        items = mgr.list_proposals(status=status, category=category, author=author)
        return [p.to_dict() for p in items]

    @application.get("/api/proposals/{proposal_id}")
    def api_proposal_detail(proposal_id: str) -> dict[str, Any]:
        """Get a single proposal."""
        from core.proposals import ProposalManager, ProposalNotFoundError
        mgr = ProposalManager()
        try:
            p = mgr.get(proposal_id)
        except ProposalNotFoundError:
            raise HTTPException(status_code=404, detail=f"Proposal '{proposal_id}' not found.")
        return p.to_dict()

    # ── Votes ─────────────────────────────────────────────────

    @application.get("/api/votes")
    def api_votes_list(
        status: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List vote records with optional status filter."""
        from core.voting import VotingEngine
        engine = VotingEngine()
        records = engine.list_records(status=status)
        result = []
        for r in records:
            rec_dict = r.to_dict()
            try:
                tally = engine.tally(r.proposal_id)
                rec_dict["tally"] = tally.to_dict()
            except Exception:
                rec_dict["tally"] = None
            result.append(rec_dict)
        return result

    @application.get("/api/votes/{proposal_id}")
    def api_vote_detail(proposal_id: str) -> dict[str, Any]:
        """Get vote record and tally for a proposal."""
        from core.voting import VotingEngine, VoteNotFoundError
        engine = VotingEngine()
        try:
            record = engine.get(proposal_id)
            tally = engine.tally(proposal_id)
        except VoteNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"No vote record for proposal '{proposal_id}'.",
            )
        result = record.to_dict()
        result["tally"] = tally.to_dict()
        return result

    # ── Characters ────────────────────────────────────────────

    @application.get("/api/characters")
    def api_characters_list(
        status: str | None = Query(None),
        author: str | None = Query(None),
        tag: str | None = Query(None),
    ) -> list[dict[str, Any]]:
        """List characters with optional filters."""
        from core.characters import CharacterManager
        mgr = CharacterManager()
        items = mgr.list_characters(status=status, author=author, tag=tag)
        return [c.to_dict() for c in items]

    @application.get("/api/characters/{character_id}")
    def api_character_detail(character_id: str) -> dict[str, Any]:
        """Get a single character template."""
        from core.characters import CharacterManager, CharacterNotFoundError
        mgr = CharacterManager()
        try:
            c = mgr.get(character_id)
        except CharacterNotFoundError:
            raise HTTPException(
                status_code=404,
                detail=f"Character '{character_id}' not found.",
            )
        return c.to_dict()

    # ── Analytics ─────────────────────────────────────────────

    @application.get("/api/analytics")
    def api_analytics() -> dict[str, Any]:
        """Full analytics report."""
        from core.analytics import SessionAnalytics
        from core.proposals import ProposalManager
        from core.voting import VotingEngine

        pmgr = ProposalManager()
        engine = VotingEngine()
        sa = SessionAnalytics(proposal_manager=pmgr, voting_engine=engine)
        report = sa.full_report()
        return report.to_dict()

    # ── Static Files ──────────────────────────────────────────

    static_dir = WEB_STATIC_DIR
    if static_dir.exists():
        application.mount(
            "/static",
            StaticFiles(directory=str(static_dir)),
            name="static",
        )

    @application.get("/")
    def serve_index() -> FileResponse:
        """Serve the SPA index.html."""
        index = static_dir / "index.html"
        if not index.exists():
            raise HTTPException(status_code=404, detail="Dashboard not found.")
        return FileResponse(str(index))

    return application


# Module-level app instance for ``uvicorn core.web_api:app``
app = create_app()
