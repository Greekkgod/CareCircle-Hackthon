"""Appointment management service."""

from datetime import datetime, timezone
import uuid
from typing import List, Optional
from app.core.database import db
from app.models.appointment import Appointment, AppointmentCreate, AppointmentStatus


def list_appointments(elder_id: str) -> List[Appointment]:
    """Retrieve all appointments for a given elder."""
    records = db.list(
        "appointments",
        filters=[("elder_id", "==", elder_id)],
        order_by="scheduled_time",
        descending=False,
    )
    return [Appointment(**rec) for rec in records]


def get_appointment(appointment_id: str) -> Optional[Appointment]:
    """Retrieve an appointment by ID."""
    rec = db.get("appointments", appointment_id)
    return Appointment(**rec) if rec else None


def create_appointment(elder_id: str, payload: AppointmentCreate) -> Appointment:
    """Create a new confirmed appointment for an elder."""
    appt_id = f"appt_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data.update({
        "id": appt_id,
        "elder_id": elder_id,
        "status": AppointmentStatus.CONFIRMED.value,
        "created_at": now_iso,
    })
    saved = db.set("appointments", appt_id, data)
    return Appointment(**saved)


def update_status(appointment_id: str, new_status: AppointmentStatus) -> Optional[Appointment]:
    """Update appointment status (CONFIRMED, COMPLETED, CANCELLED)."""
    updated = db.update("appointments", appointment_id, {"status": new_status.value})
    return Appointment(**updated) if updated else None


def delete_appointment(appointment_id: str) -> bool:
    """Delete an appointment."""
    return db.delete("appointments", appointment_id)
