"""Appointment endpoints with role-based permissions and caretaker ChangeRequest flow."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.core.database import db
from app.core.security import require_roles
from app.models.appointment import Appointment, AppointmentCreate, AppointmentStatus
from app.models.change_request import EntityType
from app.services import appointment_service
from app.services.change_request_service import create_change_request, log_audit

router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


class AppointmentUpdate(BaseModel):
    """Payload to update an appointment."""

    title: Optional[str] = Field(default=None, max_length=150)
    doctor_name: Optional[str] = Field(default=None, max_length=120)
    location: Optional[str] = Field(default=None, max_length=250)
    scheduled_time: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=500)
    transport_needed: Optional[bool] = None
    status: Optional[AppointmentStatus] = None
    reason: Optional[str] = Field(default="Appointment rescheduling", max_length=300)


@router.get("/", response_model=List[Appointment])
async def get_appointments(
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[Appointment]:
    """Retrieve scheduled appointments for the elder."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return appointment_service.list_appointments(target_elder)


@router.get("/{appointment_id}", response_model=Appointment)
async def get_single_appointment(
    appointment_id: str,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> Appointment:
    """Retrieve a single appointment by ID (Read CRUD)."""
    appt = appointment_service.get_appointment(appointment_id)
    if not appt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment '{appointment_id}' not found.",
        )
    return appt


@router.post("/", response_model=Appointment, status_code=status.HTTP_201_CREATED)
async def add_appointment(
    payload: AppointmentCreate,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> Appointment:
    """Create a new appointment. Elder and Caretaker allowed; Family denied (403)."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    created = appointment_service.create_appointment(target_elder, payload)
    log_audit(
        elder_id=target_elder,
        action="APPOINTMENT_CREATED",
        actor_id=current_user["sub"],
        actor_role=current_user["role"],
        details={"appointment_id": created.id, "title": created.title},
    )
    return created


@router.patch("/{appointment_id}", response_model=Dict[str, Any])
async def edit_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    response: Response,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> Dict[str, Any]:
    """Edit an appointment.

    Permission Rule:
    - Elder = Full control: applies edit immediately.
    - Caretaker: creates a ChangeRequest that the elder must approve!
    - Family: Denied (HTTP 403).
    """
    existing = db.get("appointments", appointment_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Appointment '{appointment_id}' not found.",
        )

    target_elder = existing["elder_id"]
    user_role = current_user["role"]

    update_data = {k: v for k, v in payload.model_dump().items() if v is not None and k != "reason"}
    if "status" in update_data and isinstance(update_data["status"], AppointmentStatus):
        update_data["status"] = update_data["status"].value

    if user_role == "elder":
        # Elder applies edit directly
        updated = db.update("appointments", appointment_id, update_data)
        log_audit(
            elder_id=target_elder,
            action="APPOINTMENT_UPDATED_BY_ELDER",
            actor_id=current_user["sub"],
            actor_role=user_role,
            details={"appointment_id": appointment_id, "changes": update_data},
        )
        return {
            "status": "applied",
            "message": "Appointment updated directly by elder.",
            "appointment": updated,
        }

    # Caretaker edit creates a ChangeRequest
    changes_with_id = dict(update_data)
    changes_with_id["id"] = appointment_id
    changes_with_id["title"] = update_data.get("title", existing["title"])

    cr = create_change_request(
        elder_id=target_elder,
        entity_type=EntityType.APPOINTMENT,
        proposed_changes=changes_with_id,
        reason=payload.reason or "Caretaker updated appointment details",
        created_by=current_user.get("name", current_user["sub"]),
        ai_generated=False,
    )

    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "status": "pending_approval",
        "message": "Caretaker edit submitted as a ChangeRequest. Elder approval required.",
        "change_request": cr.model_dump(),
    }


@router.delete("/{appointment_id}", response_model=Dict[str, str])
async def delete_appointment(
    appointment_id: str,
    current_user: Dict[str, str] = Depends(require_roles(["elder"])),
) -> Dict[str, str]:
    """Delete an appointment (Elder full control only)."""
    existing = db.get("appointments", appointment_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Appointment not found.")

    db.delete("appointments", appointment_id)
    log_audit(
        elder_id=existing["elder_id"],
        action="APPOINTMENT_DELETED",
        actor_id=current_user["sub"],
        actor_role="elder",
        details={"appointment_id": appointment_id},
    )
    return {"status": "deleted", "appointment_id": appointment_id}
