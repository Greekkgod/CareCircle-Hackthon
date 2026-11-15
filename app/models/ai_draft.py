"""AI generated draft models enforcing human-in-the-loop confirmation."""

from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DraftType(str, Enum):
    """Type of draft extracted by the AI."""

    MEDICATION = "MEDICATION"
    APPOINTMENT = "APPOINTMENT"


class DraftStatus(str, Enum):
    """Lifecycle status of an AI-generated draft."""

    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"


class ParseNoteRequest(BaseModel):
    """Input request containing doctor notes or caregiver instructions for AI parsing."""

    raw_text: str = Field(
        ...,
        min_length=5,
        max_length=5000,
        description="Prescription note or doctor discharge summary",
    )


class AIDraft(BaseModel):
    """AI-suggested draft waiting for mandatory human confirmation before saving."""

    id: str
    elder_id: str
    draft_type: DraftType
    status: DraftStatus = DraftStatus.PENDING_CONFIRMATION
    source_snippet: str
    proposed_data: Dict[str, Any]
    reasoning: str
    created_at: str
    confirmed_at: Optional[str] = None
    confirmed_by: Optional[str] = None


class ConfirmDraftRequest(BaseModel):
    """Human confirmation or rejection decision on an AI draft."""

    approved: bool = Field(
        ...,
        description="True to confirm and commit to database, False to reject",
    )
    modifications: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional human edits applied prior to final confirmation",
    )
