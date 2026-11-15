"""Medication domain service handling CRUD, dose logs, adherence metrics, and streaks."""

from datetime import date, datetime, timezone
import uuid
from typing import Any, Dict, List, Optional, Tuple
from app.core.database import db
from app.models.medication import (
    AdherenceStats,
    DoseStatus,
    Medication,
    MedicationCreate,
    MedicationLog,
    MedicationLogCreate,
)
from app.services.change_request_service import log_audit


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
        "updated_at": now_iso,
    })
    saved = db.set("medications", med_id, data)
    return Medication(**saved)


def update_medication(medication_id: str, updates: Dict[str, Any]) -> Optional[Medication]:
    """Update an existing medication."""
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    updated = db.update("medications", medication_id, updates)
    return Medication(**updated) if updated else None


def delete_medication(medication_id: str) -> bool:
    """Delete a medication."""
    return db.delete("medications", medication_id)


def log_dose(
    elder_id: str,
    payload: MedicationLogCreate,
    confirmed_by: str,
    actor_role: str = "elder",
) -> MedicationLog:
    """Record a medication dose (TAKEN, MISSED, or SNOOZED).

    Decrements refills when TAKEN. Writes an immutable AuditEntry.

    Args:
        elder_id: Target elder ID.
        payload: Dose log details.
        confirmed_by: Name or role of the person recording.
        actor_role: Role of the actor (elder or caretaker).

    Returns:
        Persisted MedicationLog model.
    """
    log_id = f"log_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now(timezone.utc).isoformat()
    data = payload.model_dump()
    data.update({
        "id": log_id,
        "elder_id": elder_id,
        "logged_at": now_iso,
        "logged_by": confirmed_by,
        "taken_at": now_iso,
        "confirmed_by": confirmed_by,
    })
    saved = db.set("medication_logs", log_id, data)

    # Decrement remaining refills if TAKEN
    if payload.status == DoseStatus.TAKEN:
        med = db.get("medications", payload.medication_id)
        if med and med.get("remaining_refills", 0) > 0:
            db.update("medications", payload.medication_id, {
                "remaining_refills": med["remaining_refills"] - 1,
            })

    # Record immutable audit entry
    log_audit(
        elder_id=elder_id,
        action=f"DOSE_{payload.status.value}",
        actor_id=confirmed_by,
        actor_role=actor_role,
        details={
            "dose_log_id": log_id,
            "medication_id": payload.medication_id,
            "medication_name": payload.medication_name,
            "status": payload.status.value,
            "snooze_until": payload.snooze_until,
        },
    )

    return MedicationLog(**saved)


def list_recent_logs(elder_id: str, limit: int = 20) -> List[MedicationLog]:
    """Retrieve recent dose logs for an elder."""
    records = db.list(
        "medication_logs",
        filters=[("elder_id", "==", elder_id)],
        order_by="logged_at",
        descending=True,
        limit=limit,
    )
    return [MedicationLog(**rec) for rec in records]


def calculate_streaks(logs: List[Dict[str, Any]]) -> Tuple[int, int]:
    """Compute current streak and longest streak of consecutive adherent days.

    Args:
        logs: List of dose log dictionaries.

    Returns:
        Tuple of (current_streak_days, longest_streak_days).
    """
    if not logs:
        return 0, 0

    # Group log statuses by calendar date (YYYY-MM-DD)
    day_status: Dict[str, List[str]] = {}
    for log in logs:
        ts = log.get("logged_at") or log.get("taken_at") or ""
        date_str = ts[:10] if len(ts) >= 10 else date.today().isoformat()
        if date_str not in day_status:
            day_status[date_str] = []
        day_status[date_str].append(log.get("status", ""))

    sorted_dates = sorted(day_status.keys())
    longest = 0
    current = 0

    for d in sorted_dates:
        statuses = day_status[d]
        has_taken = DoseStatus.TAKEN.value in statuses
        has_missed = DoseStatus.MISSED.value in statuses

        # A day counts toward a streak if it has taken doses and no missed doses
        if has_taken and not has_missed:
            current += 1
            if current > longest:
                longest = current
        elif has_missed:
            current = 0

    return current, longest


def compute_adherence(elder_id: str) -> AdherenceStats:
    """Calculate adherence percentage, streaks, and refill alert counts.

    Returns:
        AdherenceStats model with metrics.
    """
    logs = db.list("medication_logs", filters=[("elder_id", "==", elder_id)])
    meds = db.list("medications", filters=[("elder_id", "==", elder_id), ("is_active", "==", True)])

    total = len(logs)
    taken = sum(1 for log in logs if log.get("status") == DoseStatus.TAKEN.value)
    missed = sum(1 for log in logs if log.get("status") == DoseStatus.MISSED.value)
    snoozed = sum(1 for log in logs if log.get("status") == DoseStatus.SNOOZED.value)

    # Effective rate considers taken vs missed
    denom = taken + missed
    percentage = round((taken / denom * 100.0), 1) if denom > 0 else (100.0 if taken > 0 else 100.0)

    current_streak, longest_streak = calculate_streaks(logs)

    needs_refill = sum(
        1 for m in meds
        if m.get("remaining_refills", 0) <= m.get("refill_threshold", 7)
    )

    return AdherenceStats(
        elder_id=elder_id,
        total_logged=total,
        taken_count=taken,
        missed_count=missed,
        snoozed_count=snoozed,
        adherence_percentage=percentage,
        current_streak_days=current_streak,
        longest_streak_days=longest_streak,
        needs_refill_count=needs_refill,
    )
