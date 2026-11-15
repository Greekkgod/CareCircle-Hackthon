"""ChangeRequest model for human-in-the-loop consent and plain-language elder review."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Entity target of the change request."""

    MEDICATION = "MEDICATION"
    APPOINTMENT = "APPOINTMENT"


class ChangeRequestStatus(str, Enum):
    """Status of change request."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class ChangeRequestCreate(BaseModel):
    """Payload to create a new change request or draft."""

    elder_id: str
    entity_type: EntityType
    entity_id: Optional[str] = Field(default=None, description="Target medication or appointment ID")
    proposed_changes: Dict[str, Any]
    reason: str = Field(..., max_length=500)
    ai_generated: bool = Field(default=False)
    created_by: str = Field(default="system")
    plain_language_summary: Optional[str] = Field(
        default=None,
        description="Plain-language explanation for elderly review",
    )
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class ChangeRequest(BaseModel):
    """Change request document stored in Firestore."""

    id: str
    elder_id: str
    entity_type: EntityType
    entity_id: Optional[str] = None
    proposed_changes: Dict[str, Any]
    reason: str
    plain_language_summary: str = Field(
        default="",
        description="Plain-language explanation for elderly review",
    )
    ai_generated: bool = False
    created_by: str = "system"
    status: ChangeRequestStatus = ChangeRequestStatus.PENDING
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    expires_at: str = Field(
        default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=72)).isoformat()
    )

    def model_post_init(self, __context) -> None:
        if not self.plain_language_summary:
            self.plain_language_summary = (
                f"Proposed {self.entity_type.value.lower()} change: {self.reason}"
            )
