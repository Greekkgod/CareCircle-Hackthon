"""Daily check-in and emergency SOS service."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from app.core.database import db
from app.models.checkin import CheckIn, CheckInCreate, EmergencyAlert


def record_checkin(elder_id: str, elder_name: str, payload: CheckInCreate) -> CheckIn:
    """Record an elder's daily wellness check-in."""
    checkin_id = f"chk_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data.update({
        "id": checkin_id,
        "elder_id": elder_id,
        "elder_name": elder_name,
        "created_at": now_iso,
    })
    saved = db.set("checkins", checkin_id, data)
    return CheckIn(**saved)


def list_checkins(elder_id: str, limit: int = 15) -> List[CheckIn]:
    """Retrieve recent check-ins for an elder."""
    records = db.list(
        "checkins",
        filters=[("elder_id", "==", elder_id)],
        order_by="created_at",
        descending=True,
        limit=limit,
    )
    return [CheckIn(**rec) for rec in records]


def trigger_emergency_sos(elder_id: str, elder_name: str, note: str) -> EmergencyAlert:
    """Trigger an urgent emergency SOS panic alert."""
    alert_id = f"sos_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    data = {
        "id": alert_id,
        "elder_id": elder_id,
        "elder_name": elder_name,
        "trigger_type": "PANIC_BUTTON",
        "status": "ACTIVE",
        "note": note,
        "created_at": now_iso,
    }
    saved = db.set("emergency_alerts", alert_id, data)
    return EmergencyAlert(**saved)


def list_emergencies(elder_id: str, only_active: bool = False) -> List[EmergencyAlert]:
    """Retrieve emergency alerts for an elder."""
    filters = [("elder_id", "==", elder_id)]
    if only_active:
        filters.append(("status", "==", "ACTIVE"))
    records = db.list("emergency_alerts", filters=filters, order_by="created_at", descending=True)
    return [EmergencyAlert(**rec) for rec in records]


def resolve_emergency(alert_id: str, resolved_by: str) -> Optional[EmergencyAlert]:
    """Resolve an emergency alert."""
    now_iso = datetime.now(timezone.utc).isoformat()
    updated = db.update("emergency_alerts", alert_id, {
        "status": "RESOLVED",
        "resolved_at": now_iso,
        "resolved_by": resolved_by,
    })
    return EmergencyAlert(**updated) if updated else None
