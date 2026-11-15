"""AuditEntry model for tracking all security, clinical, and data actions."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class AuditEntryCreate(BaseModel):
    """Payload to create an audit record."""

    elder_id: str
    action: str = Field(..., max_length=100, description="e.g. DOSE_LOGGED, PASSCODE_FAILED, DRAFT_CONFIRMED")
    actor_id: str = Field(..., max_length=100)
    actor_role: str = Field(..., max_length=50)
    details: Dict[str, Any] = Field(default_factory=dict)
    ip_address: Optional[str] = Field(default=None, max_length=50)


class AuditEntry(AuditEntryCreate):
    """Audit document stored in Firestore."""

    id: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
