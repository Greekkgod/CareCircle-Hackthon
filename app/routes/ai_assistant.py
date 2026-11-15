"""AI Clinical Assistant routes enforcing human confirmation for drafts."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.core.security import require_roles
from app.models.ai_draft import AIDraft, ConfirmDraftRequest, DraftStatus, ParseNoteRequest
from app.services.draft_service import get_draft, list_drafts, process_draft_confirmation
from app.services.gemini_service import parse_and_create_drafts

router = APIRouter(prefix="/api/ai", tags=["AI Clinical Assistant"])


@router.post("/parse-draft", response_model=List[AIDraft])
async def parse_notes_into_drafts(
    payload: ParseNoteRequest,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker"])),
) -> List[AIDraft]:
    """Parse medical notes or prescription into AI suggested drafts.

    Security & Privacy:
    - Redacts personal identifiers (names, SSNs, phone numbers, addresses) before AI processing.
    - AI only suggests: creates drafts with PENDING_CONFIRMATION status.
    """
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    drafts = parse_and_create_drafts(payload.raw_text, elder_id=target_elder)
    return drafts


@router.get("/drafts", response_model=List[AIDraft])
async def get_drafts(
    elder_id: Optional[str] = None,
    status_filter: Optional[DraftStatus] = None,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker"])),
) -> List[AIDraft]:
    """List AI drafts pending human review and confirmation."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return list_drafts(target_elder, status_filter=status_filter)


@router.post("/drafts/{draft_id}/confirm", response_model=Dict[str, Any])
async def confirm_draft(
    draft_id: str,
    payload: ConfirmDraftRequest,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker"])),
) -> Dict[str, Any]:
    """Human-in-the-loop confirmation or rejection of an AI draft.

    AI rule: An AI draft ONLY becomes an active medication or appointment
    when approved by a human through this endpoint.
    """
    confirmed_by = current_user.get("name", current_user["sub"])
    try:
        updated_draft, created_entity = process_draft_confirmation(
            draft_id=draft_id,
            approved=payload.approved,
            modifications=payload.modifications,
            confirmed_by=confirmed_by,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    return {
        "status": "success",
        "decision": "approved" if payload.approved else "rejected",
        "draft": updated_draft.model_dump(),
        "created_record": created_entity.model_dump() if created_entity else None,
    }
