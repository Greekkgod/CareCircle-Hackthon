"""AI Clinical Assistant routes enforcing human confirmation for drafts.

Features:
1. Prescription photo to draft medication list (Multimodal Vision).
2. Natural-language and conversational voice note extraction.
3. Plain-language "Why am I taking this?" senior explanations.
4. Pre-appointment doctor briefing synthesized from adherence trends.

Strict Rules:
- All generated outputs are drafts with PENDING_CONFIRMATION status.
- Every response includes a mandatory 'confirm with your doctor or pharmacist' note.
- Redacts personal identifiers before calling the model.
- Handles API failures gracefully with built-in fallbacks.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import require_roles
from app.models.ai_draft import (
    AIDraft,
    ConfirmDraftRequest,
    DoctorBriefingRequest,
    DraftStatus,
    ParseNoteRequest,
    PrescriptionPhotoRequest,
    VoiceOrNaturalLanguageRequest,
    WhyAmITakingThisRequest,
)
from app.services.draft_service import list_drafts, process_draft_confirmation
from app.services.gemini_service import (
    explain_why_am_i_taking_this,
    generate_doctor_briefing,
    parse_and_create_drafts,
    parse_natural_language_voice_to_drafts,
    parse_prescription_photo_to_drafts,
)

router = APIRouter(prefix="/api/ai", tags=["AI Clinical Assistant"])


# -------------------------------------------------------------------------
# Feature 1: Prescription Photo to Draft Medication List
# -------------------------------------------------------------------------
@router.post("/prescription-photo", response_model=List[AIDraft])
async def upload_prescription_photo(
    payload: PrescriptionPhotoRequest,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker", "elder"])),
) -> List[AIDraft]:
    """Extract medication drafts from an uploaded prescription image.

    - Strips/omits personal identifiers before model processing.
    - Output items are drafts requiring human confirmation.
    - Includes mandatory doctor/pharmacist confirmation disclaimer.
    """
    target_elder = elder_id or payload.elder_id or current_user.get("elder_id", current_user["sub"])
    drafts = parse_prescription_photo_to_drafts(
        image_base64=payload.image_base64,
        mime_type=payload.mime_type,
        elder_id=target_elder,
    )
    return drafts


# -------------------------------------------------------------------------
# Feature 2: Natural-Language / Voice Entry
# -------------------------------------------------------------------------
@router.post("/voice-entry", response_model=List[AIDraft])
async def parse_voice_or_natural_language(
    payload: VoiceOrNaturalLanguageRequest,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> List[AIDraft]:
    """Parse transcribed conversational voice notes or freeform text into drafts.

    - Redacts patient identifiers (names, SSNs, phone numbers, addresses).
    - AI outputs structured drafts with PENDING_CONFIRMATION status.
    - Includes mandatory doctor/pharmacist confirmation disclaimer.
    """
    target_elder = elder_id or payload.elder_id or current_user.get("elder_id", current_user["sub"])
    drafts = parse_natural_language_voice_to_drafts(
        raw_text=payload.text,
        elder_id=target_elder,
    )
    return drafts


# Legacy route for clinical note text
@router.post("/parse-draft", response_model=List[AIDraft])
async def parse_notes_into_drafts(
    payload: ParseNoteRequest,
    elder_id: Optional[str] = None,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker", "elder"])),
) -> List[AIDraft]:
    """Parse medical notes or discharge instructions into AI suggested drafts."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    drafts = parse_and_create_drafts(payload.raw_text, elder_id=target_elder)
    return drafts


# -------------------------------------------------------------------------
# Feature 3: Plain-Language "Why Am I Taking This?"
# -------------------------------------------------------------------------
@router.post("/why-am-i-taking-this", response_model=AIDraft)
async def explain_medication_purpose(
    payload: WhyAmITakingThisRequest,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> AIDraft:
    """Generate a senior-friendly 5th-grade explanation of a medication's clinical purpose.

    - Warm, plain-language breakdown of what the pill does and 1 practical tip.
    - Draft includes mandatory doctor/pharmacist confirmation disclaimer.
    """
    target_elder = payload.elder_id or current_user.get("elder_id", current_user["sub"])
    draft = explain_why_am_i_taking_this(
        medication_name=payload.medication_name,
        dosage=payload.dosage,
        elder_id=target_elder,
    )
    return draft


# -------------------------------------------------------------------------
# Feature 4: Pre-Appointment Doctor Briefing
# -------------------------------------------------------------------------
@router.post("/doctor-briefing", response_model=AIDraft)
async def create_doctor_briefing(
    payload: DoctorBriefingRequest,
    current_user: Dict[str, str] = Depends(require_roles(["elder", "caretaker", "family"])),
) -> AIDraft:
    """Generate a concise pre-appointment clinical briefing synthesized from adherence history.

    - Highlights adherence rate, streaks, missed/snoozed doses, and mood logs.
    - Draft includes mandatory doctor/pharmacist confirmation disclaimer.
    """
    target_elder = payload.elder_id or current_user.get("elder_id", current_user["sub"])
    draft = generate_doctor_briefing(
        elder_id=target_elder,
        appointment_id=payload.appointment_id,
        timeframe_days=payload.timeframe_days,
    )
    return draft


# -------------------------------------------------------------------------
# Draft Management & Human-In-The-Loop Confirmation
# -------------------------------------------------------------------------
@router.get("/drafts", response_model=List[AIDraft])
async def get_drafts(
    elder_id: Optional[str] = None,
    status_filter: Optional[DraftStatus] = None,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker", "elder", "family"])),
) -> List[AIDraft]:
    """List AI drafts pending human review and confirmation."""
    target_elder = elder_id or current_user.get("elder_id", current_user["sub"])
    return list_drafts(target_elder, status_filter=status_filter)


@router.post("/drafts/{draft_id}/confirm", response_model=Dict[str, Any])
async def confirm_draft(
    draft_id: str,
    payload: ConfirmDraftRequest,
    current_user: Dict[str, str] = Depends(require_roles(["caretaker", "elder"])),
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
        "created_record": (
            created_entity.model_dump()
            if hasattr(created_entity, "model_dump")
            else created_entity
        ),
    }
