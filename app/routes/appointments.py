"""Appointment endpoints for scheduling and tracking care visits."""

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_roles
from app.models.appointment import Appointment, AppointmentCreate, AppointmentStatus
from app.services import appointment_service

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


@router.get("/", response_model=List[Appointment])
async def get_appointments(
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[Appointment]:
    """Retrieve scheduled appointments."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return appointment_service.list_appointments(target_elder)


@router.post("/", response_model=Appointment)
async def add_appointment(
    payload: AppointmentCreate,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker"])),
) -> Appointment:
    """Create a new appointment (Caretaker permission required)."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return appointment_service.create_appointment(target_elder, payload)


@router.patch("/{appointment_id}/status", response_model=Appointment)
async def change_status(
    appointment_id: str,
    status_value: AppointmentStatus,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> Appointment:
    """Update appointment status (e.g. COMPLETED or CANCELLED)."""
    updated = appointment_service.update_status(appointment_id, status_value)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment '{appointment_id}' not found.",
        )
    return updated
