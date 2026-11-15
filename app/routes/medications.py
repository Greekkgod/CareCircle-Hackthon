"""Medication endpoints enforcing role permissions and caretaker change requests."""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.core.database import db
from app.core.security import require_roles
from app.models.change_request import EntityType
from app.models.medication import (
    AdherenceStats,
    Medication,
    MedicationCreate,
    MedicationLog,
    MedicationLogCreate,
)
from app.services import medication_service
from app.services.change_request_service import create_change_request, log_audit

router = APIRouter(prefix="/api/medications", tags=["Medications"])


class MedicationUpdate(BaseModel):
    """Payload to update an existing medication."""

    name: Optional[str] = Field(default=None, max_length=120)
    dosage: Optional[str] = Field(default=None, max_length=100)
    instructions: Optional[str] = Field(default=None, max_length=300)
    schedule_times: Optional[List[str]] = None
    frequency: Optional[str] = Field(default=None, max_length=100)
    pill_color: Optional[str] = Field(default=None, max_length=50)
    remaining_refills: Optional[int] = Field(default=None, ge=0)
    refill_threshold: Optional[int] = Field(default=None, ge=0)
    reason: Optional[str] = Field(default="Clinical dosage adjustment", max_length=300)


@router.get("/", response_model=List[Medication])
async def get_medications(
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[Medication]:
    """Retrieve medications for the elder (all roles can view summary)."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return medication_service.list_medications(target_elder)





@router.get("/adherence", response_model=AdherenceStats)
async def get_adherence(
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> AdherenceStats:
    """Retrieve adherence score and refill alert counts (Family read-only access)."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return medication_service.compute_adherence(target_elder)


@router.get("/logs", response_model=List[MedicationLog])
async def get_medication_logs(
    elder_id: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=100),
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[MedicationLog]:
    """Retrieve dose history logs (Family read-only access)."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return medication_service.list_recent_logs(target_elder, limit=limit)


@router.get("/{medication_id}", response_model=Medication)
async def get_single_medication(
    medication_id: str,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> Medication:
    """Retrieve a single medication by ID (Read CRUD)."""
    med = medication_service.get_medication(medication_id)
    if not med:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Medication '{medication_id}' not found.",
        )
    return med


@router.post("/", response_model=Medication, status_code=status.HTTP_201_CREATED)
async def add_medication(
    payload: MedicationCreate,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> Medication:
    """Create a new medication. Elder and Caretaker permitted; Family denied."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    created = medication_service.create_medication(target_elder, payload)
    log_audit(
        elder_id=target_elder,
        action="MEDICATION_CREATED",
        actor_id=current_user["sub"],
        actor_role=current_user["role"],
        details={"medication_id": created.id, "name": created.name},
    )
    return created


@router.patch("/{medication_id}", response_model=Dict[str, Any])
async def edit_medication(
    medication_id: str,
    payload: MedicationUpdate,
    response: Response,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> Dict[str, Any]:
    """Edit an existing medication.

    Permission Rule:
    - Elder = Full control: applies edit immediately.
    - Caretaker: creates a ChangeRequest that the elder must approve!
    - Family: Denied (HTTP 403).
    """
    existing = db.get("medications", medication_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Medication '{medication_id}' not found.",
        )

    target_elder = existing["elder_id"]
    user_role = current_user["role"]

    # Filter out None values
    update_data = {k: v for k, v in payload.model_dump().items() if v is not None and k != "reason"}

    if user_role == "elder":
        # Elder has full control - apply changes directly
        updated = db.update("medications", medication_id, update_data)
        log_audit(
            elder_id=target_elder,
            action="MEDICATION_UPDATED_BY_ELDER",
            actor_id=current_user["sub"],
            actor_role=user_role,
            details={"medication_id": medication_id, "changes": update_data},
        )
        return {
            "status": "applied",
            "message": "Medication updated directly by elder.",
            "medication": updated,
        }

    # Caretaker edit: Must create a ChangeRequest requiring elder approval!
    changes_with_id = dict(update_data)
    changes_with_id["id"] = medication_id
    changes_with_id["name"] = update_data.get("name", existing["name"])

    cr = create_change_request(
        elder_id=target_elder,
        entity_type=EntityType.MEDICATION,
        proposed_changes=changes_with_id,
        reason=payload.reason or "Caretaker adjusted medication",
        created_by=current_user.get("name", current_user["sub"]),
        ai_generated=False,
    )

    response.status_code = status.HTTP_202_ACCEPTED
    return {
        "status": "pending_approval",
        "message": "Caretaker edit submitted as a ChangeRequest. Elder approval required.",
        "change_request": cr.model_dump(),
    }


@router.delete("/{medication_id}", response_model=Dict[str, str])
async def delete_medication(
    medication_id: str,
    current_user: Dict[str, str] = Depends(require_roles(["elder"])),
) -> Dict[str, str]:
    """Delete a medication (Elder full control only)."""
    existing = db.get("medications", medication_id)
    if not existing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Medication not found.")

    db.delete("medications", medication_id)
    log_audit(
        elder_id=existing["elder_id"],
        action="MEDICATION_DELETED",
        actor_id=current_user["sub"],
        actor_role="elder",
        details={"medication_id": medication_id},
    )
    return {"status": "deleted", "medication_id": medication_id}


@router.post("/log", response_model=MedicationLog)
async def log_medication_dose(
    payload: MedicationLogCreate,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> MedicationLog:
    """Record a medication dose taken, missed, or snoozed."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    confirmed_by = current_user.get("name", current_user["sub"])
    return medication_service.log_dose(
        target_elder,
        payload,
        confirmed_by=confirmed_by,
        actor_role=current_user["role"],
    )



