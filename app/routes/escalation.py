"""Escalation, Cloud Scheduler, and Simulation routes for CareCircle.

Provides:
- Protected /internal/run-reminders for Google Cloud Scheduler cron triggers.
- /api/simulation/simulate-time for demo time stepping and previewing the escalation ladder.
- Read endpoints for notification logs and digest batch inspections.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from app.core.config import settings
from app.core.database import db
from app.core.security import require_roles
from app.models.notification import SimulationTimeRequest, SimulationTimeResponse
from app.services.escalation_service import (
    flush_digest_queue,
    get_current_escalation_time,
    run_reminders_all_elders,
    set_simulated_clock,
    simulate_time_advance,
)

router = APIRouter(tags=["Escalation & Cloud Scheduler"])


def verify_scheduler_secret(
    x_cloudscheduler_token: Optional[str] = Header(None, alias="X-CloudScheduler-Token"),
    authorization: Optional[str] = Header(None),
) -> bool:
    """Verify secret token provided by Google Cloud Scheduler or internal cron callers."""
    expected = settings.cron_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Scheduler secret not configured on server",
        )

    # 1. Check custom X-CloudScheduler-Token header
    if x_cloudscheduler_token and x_cloudscheduler_token == expected:
        return True

    # 2. Check Authorization: Bearer <secret>
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1] == expected:
            return True

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unauthorized: Valid Cloud Scheduler token required",
        headers={"WWW-Authenticate": "Bearer"},
    )


# -------------------------------------------------------------------------
# Protected Cloud Scheduler Endpoint
# -------------------------------------------------------------------------
@router.post(
    "/internal/run-reminders",
    summary="Trigger reminder & escalation cycle (Protected for Cloud Scheduler)",
)
async def trigger_run_reminders(
    dry_run: bool = Query(default=False, description="Preview actions without writing sent logs"),
    _: bool = Depends(verify_scheduler_secret),
) -> Dict[str, Any]:
    """Execute scheduled reminder evaluation loop across all elders.

    Protected by Cloud Scheduler token in `X-CloudScheduler-Token` or `Authorization: Bearer <secret>`.
    """
    results = run_reminders_all_elders(dry_run=dry_run)
    return results


# -------------------------------------------------------------------------
# Simulation Endpoints (Interactive Demo & Evaluation)
# -------------------------------------------------------------------------
@router.post(
    "/api/simulation/simulate-time",
    response_model=SimulationTimeResponse,
    summary="Simulate time advancement and evaluate escalation ladder",
)
async def simulate_time(payload: SimulationTimeRequest) -> SimulationTimeResponse:
    """Set simulated clock or advance time by N minutes to test the escalation ladder.

    Accessible to test the multi-tier escalation (Elder -> Caretaker -> Family)
    and quiet hours digest batching without waiting for real wall-clock time.
    """
    response = simulate_time_advance(
        simulated_now=payload.simulated_now,
        advance_minutes=payload.advance_minutes,
        elder_id=payload.elder_id,
        dry_run=payload.dry_run,
    )
    return response


@router.post(
    "/api/simulation/reset-clock",
    summary="Reset simulated clock back to real system time",
)
async def reset_simulation_clock() -> Dict[str, str]:
    """Clear any active simulated clock offset."""
    set_simulated_clock(None)
    now = datetime.now(timezone.utc).isoformat()
    return {"message": "Simulation clock reset to live wall time", "current_time": now}


# -------------------------------------------------------------------------
# Notification Logs & Digest Inspection Endpoints
# -------------------------------------------------------------------------
@router.get(
    "/api/escalation/logs",
    summary="List notification sent-logs for an elder",
)
async def get_escalation_logs(
    elder_id: str = Query(default="elder_1"),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[Dict[str, Any]]:
    """Retrieve immutable notification logs for auditing and idempotency inspection."""
    logs = db.list(
        "notification_logs",
        filters=[("elder_id", "==", elder_id)],
        order_by="created_at",
        descending=True,
        limit=limit,
    )
    return logs


@router.get(
    "/api/escalation/digest",
    summary="List items queued for quiet-hours digest batching",
)
async def get_queued_digests(
    elder_id: str = Query(default="elder_1"),
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[Dict[str, Any]]:
    """Inspect low-priority alerts currently queued during quiet hours."""
    items = db.list("digest_queue", filters=[("elder_id", "==", elder_id)])
    return items


@router.post(
    "/api/escalation/flush-digest",
    summary="Deliver queued digest items",
)
async def trigger_flush_digest(
    elder_id: str = Query(default="elder_1"),
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> List[Dict[str, Any]]:
    """Force flush and deliver queued digest items to members."""
    results = flush_digest_queue(elder_id=elder_id)
    return results
