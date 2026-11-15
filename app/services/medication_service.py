"""Medication domain service handling CRUD, dose logs, and adherence metrics."""

from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional
from app.core.database import db
from app.models.medication import (
    AdherenceStats,
    DoseStatus,
    Medication,
    MedicationCreate,
    MedicationLog,
    MedicationLogCreate,
)


def list_medications(elder_id: str, only_active: bool = True) -> List[Medication]:
    """Retrieve all medications for a specific elder.

    Args:
        elder_id: The unique elder identifier.
        only_active: If True, only returns active medications.

    Returns:
        List of Medication models.
    """
    filters = [("elder_id", "==", elder_id)]
    if only_active:
        filters.append(("is_active", "==", True))

    records = db.list("medications", filters=filters, order_by="created_at", descending=True)
    return [Medication(**rec) for rec in records]


def get_medication(medication_id: str) -> Optional[Medication]:
    """Retrieve a single medication by ID."""
    rec = db.get("medications", medication_id)
    return Medication(**rec) if rec else None


def create_medication(elder_id: str, payload: MedicationCreate) -> Medication:
    """Create and persist a new medication for an elder.

    Args:
        elder_id: Target elder ID.
        payload: Medication details.

    Returns:
        Saved Medication model.
    """
    med_id = f"med_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data.update({
        "id": med_id,
        "elder_id": elder_id,
        "is_active": True,
        "created_at": now_iso,
    })
    saved = db.set("medications", med_id, data)
    return Medication(**saved)


def log_dose(
    elder_id: str,
    payload: MedicationLogCreate,
    confirmed_by: str,
) -> MedicationLog:
    """Record a medication dose taken or missed by an elder.

    Decrements remaining refills if status is TAKEN.

    Args:
        elder_id: Target elder ID.
        payload: Dose log details.
        confirmed_by: Name or role of the person recording (e.g. elder self-report).

    Returns:
        Persisted MedicationLog model.
    """
    log_id = f"log_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data.update({
        "id": log_id,
        "elder_id": elder_id,
        "taken_at": now_iso,
        "confirmed_by": confirmed_by,
    })
    saved = db.set("medication_logs", log_id, data)

    # If taken, decrement remaining refills for that medication
    if payload.status == DoseStatus.TAKEN:
        med = db.get("medications", payload.medication_id)
        if med and med.get("remaining_refills", 0) > 0:
            db.update("medications", payload.medication_id, {
                "remaining_refills": med["remaining_refills"] - 1,
            })

    return MedicationLog(**saved)


def list_recent_logs(elder_id: str, limit: int = 20) -> List[MedicationLog]:
    """Retrieve recent dose logs for an elder."""
    records = db.list(
        "medication_logs",
        filters=[("elder_id", "==", elder_id)],
        order_by="taken_at",
        descending=True,
        limit=limit,
    )
    return [MedicationLog(**rec) for rec in records]


def compute_adherence(elder_id: str) -> AdherenceStats:
    """Calculate adherence percentage and refill alert counts for an elder.

    Returns:
        AdherenceStats model with metrics.
    """
    logs = db.list("medication_logs", filters=[("elder_id", "==", elder_id)])
    meds = db.list("medications", filters=[("elder_id", "==", elder_id), ("is_active", "==", True)])

    total = len(logs)
    taken = sum(1 for log in logs if log.get("status") == DoseStatus.TAKEN.value)
    missed = sum(1 for log in logs if log.get("status") in [DoseStatus.MISSED.value, DoseStatus.SKIPPED.value])

    percentage = round((taken / total * 100.0), 1) if total > 0 else 100.0

    needs_refill = sum(
        1 for m in meds
        if m.get("remaining_refills", 0) <= m.get("refill_threshold", 7)
    )

    return AdherenceStats(
        elder_id=elder_id,
        total_logged=total,
        taken_count=taken,
        missed_count=missed,
        adherence_percentage=percentage,
        needs_refill_count=needs_refill,
    )
