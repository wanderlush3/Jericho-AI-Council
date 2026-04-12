"""
Jericho — Treasury Routes
"""

from __future__ import annotations


from typing import Any

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()

@router.get("/api/treasury")
def api_treasury_list(
    type: str | None = Query(None, alias="type"),
) -> list[dict[str, Any]]:
    """List all treasury accounts, optionally filtered by type."""
    from core.treasury import TreasuryManager
    tmgr = TreasuryManager()
    accounts = tmgr.list_accounts(account_type=type)
    return [a.to_dict() for a in accounts]

@router.get("/api/treasury/{account_id}")
def api_treasury_detail(account_id: str) -> dict[str, Any]:
    """Get a single treasury account."""
    from core.treasury import TreasuryManager, AccountNotFoundError
    tmgr = TreasuryManager()
    try:
        acct = tmgr.get(account_id)
    except AccountNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Treasury account '{account_id}' not found.",
        )
    return acct.to_dict()

@router.post("/api/treasury/initialize")
def api_treasury_initialize() -> dict[str, Any]:
    """Create default accounts for all known entities."""
    from core.treasury import TreasuryManager
    from core.manager_cache import get_registry, get_character_manager

    tmgr = TreasuryManager()
    registry = get_registry()
    cmgr = get_character_manager()
    created = tmgr.initialize_defaults(
        registry=registry, character_manager=cmgr
    )
    return {
        "status": "ok",
        "created_count": len(created),
        "accounts": [a.to_dict() for a in created],
    }

@router.post("/api/treasury/{account_id}/credit")
def api_treasury_credit(
    account_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Add funds to an account.  Body: {gold, silver, bronze}."""
    from core.treasury import (
        TreasuryManager, AccountNotFoundError, TreasuryValidationError,
    )
    tmgr = TreasuryManager()
    try:
        acct = tmgr.credit(
            account_id,
            gold=int(body.get("gold", 0)),
            silver=int(body.get("silver", 0)),
            bronze=int(body.get("bronze", 0)),
        )
    except AccountNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Treasury account '{account_id}' not found.",
        )
    except TreasuryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return acct.to_dict()

@router.post("/api/treasury/{account_id}/debit")
def api_treasury_debit(
    account_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    """Remove funds from an account.  Body: {gold, silver, bronze}."""
    from core.treasury import (
        TreasuryManager, AccountNotFoundError,
        InsufficientFundsError, TreasuryValidationError,
    )
    tmgr = TreasuryManager()
    try:
        acct = tmgr.debit(
            account_id,
            gold=int(body.get("gold", 0)),
            silver=int(body.get("silver", 0)),
            bronze=int(body.get("bronze", 0)),
        )
    except AccountNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"Treasury account '{account_id}' not found.",
        )
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TreasuryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return acct.to_dict()

@router.post("/api/treasury/transfer")
def api_treasury_transfer(body: dict[str, Any]) -> dict[str, Any]:
    """Transfer funds between accounts.

    Body: {from: account_id, to: account_id, gold, silver, bronze}

    Tax is automatically collected on eligible transfers.
    """
    from core.treasury import (
        TreasuryManager, AccountNotFoundError,
        InsufficientFundsError, TreasuryValidationError,
    )
    from core.taxation import TaxationManager
    from_id = body.get("from", "").strip()
    to_id = body.get("to", "").strip()
    if not from_id or not to_id:
        raise HTTPException(
            status_code=400,
            detail="'from' and 'to' account IDs are required.",
        )
    tax_mgr = TaxationManager()
    tmgr = TreasuryManager(taxation_manager=tax_mgr)
    try:
        from_acct, to_acct = tmgr.transfer(
            from_id, to_id,
            gold=int(body.get("gold", 0)),
            silver=int(body.get("silver", 0)),
            bronze=int(body.get("bronze", 0)),
        )
    except AccountNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InsufficientFundsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except TreasuryValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "from": from_acct.to_dict(),
        "to": to_acct.to_dict(),
    }

# ── Taxation ──────────────────────────────────────────────

@router.get("/api/tax/policy")
def api_tax_policy_get() -> dict[str, Any]:
    """Get the current tax policy."""
    from core.taxation import TaxationManager
    mgr = TaxationManager()
    return mgr.get_policy().to_dict()

@router.put("/api/tax/policy")
def api_tax_policy_update(body: dict[str, Any]) -> dict[str, Any]:
    """Update the tax policy.

    Body: {rate?: float, enabled?: bool, exempt_account_types?: list}
    """
    from core.taxation import TaxationManager, TaxationValidationError
    mgr = TaxationManager()
    kwargs: dict[str, Any] = {}
    if "rate" in body:
        kwargs["rate"] = float(body["rate"])
    if "enabled" in body:
        kwargs["enabled"] = bool(body["enabled"])
    if "exempt_account_types" in body:
        kwargs["exempt_account_types"] = list(body["exempt_account_types"])
    try:
        policy = mgr.update_policy(**kwargs)
    except TaxationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return policy.to_dict()

@router.get("/api/tax/events")
def api_tax_events(
    limit: int | None = Query(None),
    from_account: str | None = Query(None),
    to_account: str | None = Query(None),
) -> list[dict[str, Any]]:
    """List tax collection events."""
    from core.taxation import TaxationManager
    mgr = TaxationManager()
    events = mgr.list_events(
        limit=limit, from_account=from_account, to_account=to_account,
    )
    return [e.to_dict() for e in events]

@router.get("/api/tax/summary")
def api_tax_summary() -> dict[str, Any]:
    """Total tax collected across all time."""
    from core.taxation import TaxationManager
    mgr = TaxationManager()
    total = mgr.get_total_collected()
    policy = mgr.get_policy()
    return {
        "total_collected": total,
        "policy": policy.to_dict(),
        "event_count": len(mgr.list_events()),
    }

# ── Salary Payroll (hidden, runs at startup) ──────────────

try:
    from core.salary import SalaryManager
    SalaryManager().check_and_pay()
except Exception:
    import logging
    logging.getLogger(__name__).exception("Salary: startup payroll check failed")

# ── Entity Image Gallery (F-037e) ────────────────────────

# NOTE: Specific routes (file, set-primary, info) MUST be registered
# before the generic {entity_type}/{entity_id} catch-all routes.

