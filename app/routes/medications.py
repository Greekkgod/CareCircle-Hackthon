"""Medication endpoints for scheduling, dosage logging, and adherence tracking."""

from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, Query
from app.core.security import require_roles
from app.models.medication import (
    AdherenceStats,
    Medication,
    MedicationCreate,
    MedicationLog,
    MedicationLogCreate,
)
from app.services import medication_service

router = APIRouter(prefix="/api/medications", tags=["Medications"])


@router.get("/", response_model=List[Medication])
async def get_medications(
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[Medication]:
    """Retrieve medications for the elder."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return medication_service.list_medications(target_elder)


@router.post("/", response_model=Medication)
async def add_medication(
    payload: MedicationCreate,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker"])),
) -> Medication:
    """Create a new medication (Caretaker permission required)."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return medication_service.create_medication(target_elder, payload)


@router.post("/log", response_model=MedicationLog)
async def log_medication_dose(
    payload: MedicationLogCreate,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> MedicationLog:
    """Record a medication dose taken or missed."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    confirmed_by = current_user.get("name", current_user["sub"])
    return medication_service.log_dose(target_elder, payload, confirmed_by=confirmed_by)


@router.get("/adherence", response_model=AdherenceStats)
async def get_adherence(
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> AdherenceStats:
    """Retrieve adherence score and refill alert counts."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return medication_service.compute_adherence(target_elder)


@router.get("/logs", response_model=List[MedicationLog])
async def get_medication_logs(
    elder_id: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[MedicationLog]:
    """Retrieve dose history logs."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return medication_service.list_recent_logs(target_elder, limit=limit)
