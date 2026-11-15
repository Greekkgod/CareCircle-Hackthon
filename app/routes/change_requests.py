"""ChangeRequest API routes implementing the plain-language elder-consent workflow."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from app.core.security import require_roles
from app.models.change_request import ChangeRequest, ChangeRequestCreate, ChangeRequestStatus
from app.services import change_request_service

router = APIRouter(prefix="/api/change-requests", tags=["Change Requests & Consent"])


class RejectPayload(BaseModel):
    """Optional rejection rationale."""

    reason: Optional[str] = Field(default=None, max_length=300)


@router.get("/", response_model=List[ChangeRequest])
async def list_change_requests(
    elder_id: Optional[str] = None,
    status_filter: Optional[ChangeRequestStatus] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> List[ChangeRequest]:
    """List change requests for an elder. Accessible by elder and caretaker."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return change_request_service.list_change_requests(target_elder, status_filter=status_filter)


@router.post("/", response_model=ChangeRequest, status_code=status.HTTP_201_CREATED)
async def create_change_request_endpoint(
    payload: ChangeRequestCreate,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker"])),
) -> ChangeRequest:
    """Submit a proposed change request for elder confirmation with duplicate protection."""
    return change_request_service.create_change_request(
        elder_id=payload.elder_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        proposed_changes=payload.proposed_changes,
        reason=payload.reason,
        created_by=current_user.get("name", current_user["sub"]),
        plain_language_summary=payload.plain_language_summary,
        ai_generated=payload.ai_generated,
        expires_in_hours=payload.expires_in_hours,
    )


@router.post("/{change_request_id}/approve", response_model=Dict[str, Any])
async def approve_change_request_endpoint(
    change_request_id: str,
    current_user: Dict[str, str] = Depends(require_roles(["elder"])),
) -> Dict[str, Any]:
    """Approve a change request and apply mutations to the underlying entity.

    Strict Permission Matrix: Only the 'elder' role can approve change requests.
    Validates against expiration.
    """
    cr, entity = change_request_service.approve_change_request(
        change_request_id=change_request_id,
        reviewer_id=current_user["sub"],
        reviewer_role=current_user["role"],
    )
    return {
        "status": "success",
        "action": "approved",
        "change_request": cr.model_dump(),
        "applied_entity": entity.model_dump() if entity else None,
    }


@router.post("/{change_request_id}/reject", response_model=ChangeRequest)
async def reject_change_request_endpoint(
    change_request_id: str,
    payload: Optional[RejectPayload] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder"])),
) -> ChangeRequest:
    """Reject a change request without applying changes.

    Strict Permission Matrix: Only the 'elder' role can reject change requests.
    """
    reason = payload.reason if payload else None
    return change_request_service.reject_change_request(
        change_request_id=change_request_id,
        reviewer_id=current_user["sub"],
        reviewer_role=current_user["role"],
        reason=reason,
    )
