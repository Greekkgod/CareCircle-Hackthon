"""Daily check-in and emergency SOS endpoints."""

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_roles
from app.models.checkin import (
    CheckIn,
    CheckInCreate,
    EmergencyAlert,
    EmergencySOSCreate,
)
from app.services import checkin_service

router = APIRouter(prefix="/api/checkins", tags=["Check-ins & Emergency"])


@router.post("/", response_model=CheckIn)
async def post_checkin(
    payload: CheckInCreate,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> CheckIn:
    """Record a daily mood & wellness check-in for the elder."""
    elder_id = current_user.get("elder_id", current_user["sub"])
    elder_name = current_user.get("name", "Elder")
    return checkin_service.record_checkin(elder_id, elder_name, payload)


@router.get("/", response_model=List[CheckIn])
async def get_checkins(
    elder_id: Optional[str] = None,
    limit: int = 15,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[CheckIn]:
    """Retrieve recent wellness check-ins."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return checkin_service.list_checkins(target_elder, limit=limit)


@router.post("/sos", response_model=EmergencyAlert)
async def trigger_emergency(
    payload: EmergencySOSCreate,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> EmergencyAlert:
    """Trigger an emergency panic alert dispatched to caretakers and family."""
    elder_id = current_user.get("elder_id", current_user["sub"])
    elder_name = current_user.get("name", "Elder")
    return checkin_service.trigger_emergency_sos(
        elder_id=elder_id,
        elder_name=elder_name,
        note=payload.note or "Emergency alert triggered",
    )


@router.get("/emergencies", response_model=List[EmergencyAlert])
async def get_emergencies(
    elder_id: Optional[str] = None,
    only_active: bool = False,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[EmergencyAlert]:
    """Retrieve active or historical emergency alerts."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return checkin_service.list_emergencies(target_elder, only_active=only_active)


@router.post("/emergencies/{alert_id}/resolve", response_model=EmergencyAlert)
async def resolve_emergency_alert(
    alert_id: str,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker"])),
) -> EmergencyAlert:
    """Mark an emergency alert as resolved (Caretaker permission required)."""
    resolved_by = current_user.get("name", current_user["sub"])
    resolved = checkin_service.resolve_emergency(alert_id, resolved_by=resolved_by)
    if not resolved:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Emergency alert '{alert_id}' not found.",
        )
    return resolved
