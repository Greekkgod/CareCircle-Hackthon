"""ChangeRequest model for human-in-the-loop validation of AI suggestions."""

from datetime import datetime, timezone
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


class ChangeRequestCreate(BaseModel):
    """Payload to create a new change request or draft."""

    elder_id: str
    entity_type: EntityType
    proposed_changes: Dict[str, Any]
    reason: str = Field(..., max_length=500)
    ai_generated: bool = Field(default=True)
    created_by: str = Field(default="system")


class ChangeRequest(ChangeRequestCreate):
    """Change request document stored in Firestore."""

    id: str
    status: ChangeRequestStatus = ChangeRequestStatus.PENDING
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
