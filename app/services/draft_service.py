"""Service managing AI draft confirmation and rejection.

Enforces human-in-the-loop validation: AI proposals become real records
only upon explicit human approval.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from app.core.database import db
from app.models.ai_draft import AIDraft, DraftStatus, DraftType
from app.models.appointment import AppointmentCreate
from app.models.medication import MedicationCreate
from app.services.appointment_service import create_appointment
from app.services.medication_service import create_medication


def list_drafts(elder_id: str, status_filter: Optional[DraftStatus] = None) -> List[AIDraft]:
    """Retrieve drafts for an elder, optionally filtered by status."""
    filters = [("elder_id", "==", elder_id)]
    if status_filter:
        filters.append(("status", "==", status_filter.value))

    records = db.list("ai_drafts", filters=filters, order_by="created_at", descending=True)
    return [AIDraft(**rec) for rec in records]


def get_draft(draft_id: str) -> Optional[AIDraft]:
    """Fetch draft by ID."""
    rec = db.get("ai_drafts", draft_id)
    return AIDraft(**rec) if rec else None


def process_draft_confirmation(
    draft_id: str,
    approved: bool,
    modifications: Optional[Dict[str, Any]],
    confirmed_by: str,
) -> Tuple[AIDraft, Optional[Any]]:
    """Process human decision to approve or reject an AI-generated draft.

    Args:
        draft_id: ID of the draft to process.
        approved: True if human approves, False if rejected.
        modifications: Optional field overrides entered by human.
        confirmed_by: Identifier of the approving user.

    Returns:
        Tuple of (updated_draft, created_entity_or_none).

    Raises:
        ValueError: If draft does not exist or was already confirmed/rejected.
    """
    draft_dict = db.get("ai_drafts", draft_id)
    if not draft_dict:
        raise ValueError(f"Draft '{draft_id}' not found.")

    draft = AIDraft(**draft_dict)
    if draft.status != DraftStatus.PENDING_CONFIRMATION:
        raise ValueError(f"Draft '{draft_id}' already has status '{draft.status}'.")

    now_iso = datetime.now(timezone.utc).isoformat()

    if not approved:
        # User rejected the draft - do NOT save to medications or appointments
        updated = db.update("ai_drafts", draft_id, {
            "status": DraftStatus.REJECTED.value,
            "confirmed_at": now_iso,
            "confirmed_by": confirmed_by,
        })
        return AIDraft(**updated), None

    # User approved - merge modifications if any
    final_data = dict(draft.proposed_data)
    if modifications:
        final_data.update(modifications)

    created_entity = None
    if draft.draft_type == DraftType.MEDICATION:
        med_create = MedicationCreate(
            name=final_data["name"],
            dosage=final_data["dosage"],
            instructions=final_data.get("instructions", "Take as directed"),
            schedule_times=final_data.get("schedule_times", ["08:00"]),
            frequency=final_data.get("frequency", "Daily"),
            pill_color=final_data.get("pill_color", "#3B82F6"),
            remaining_refills=int(final_data.get("remaining_refills", 30)),
            refill_threshold=int(final_data.get("refill_threshold", 7)),
        )
        created_entity = create_medication(draft.elder_id, med_create)

    elif draft.draft_type == DraftType.APPOINTMENT:
        appt_create = AppointmentCreate(
            title=final_data["title"],
            doctor_name=final_data["doctor_name"],
            location=final_data["location"],
            scheduled_time=final_data["scheduled_time"],
            notes=final_data.get("notes"),
            transport_needed=bool(final_data.get("transport_needed", False)),
        )
        created_entity = create_appointment(draft.elder_id, appt_create)

    updated = db.update("ai_drafts", draft_id, {
        "status": DraftStatus.CONFIRMED.value,
        "proposed_data": final_data,
        "confirmed_at": now_iso,
        "confirmed_by": confirmed_by,
    })

    return AIDraft(**updated), created_entity
