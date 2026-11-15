"""Elderly daily wellness check-in and emergency SOS models."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MoodLevel(str, Enum):
    """Daily mood rating for seniors."""

    GREAT = "GREAT"
    OKAY = "OKAY"
    NEED_HELP = "NEED_HELP"


class CheckInCreate(BaseModel):
    """Payload when an elder records a daily wellness check-in."""

    mood: MoodLevel
    note: Optional[str] = Field(default=None, max_length=200)


class CheckIn(CheckInCreate):
    """Full check-in record stored in database."""

    id: str
    elder_id: str
    elder_name: str
    created_at: str


class EmergencySOSCreate(BaseModel):
    """Payload to trigger an urgent SOS emergency alert."""

    note: Optional[str] = Field(default="Elder triggered emergency SOS button", max_length=300)


class EmergencyAlert(BaseModel):
    """Emergency alert dispatched to caretakers and family."""

    id: str
    elder_id: str
    elder_name: str
    trigger_type: str = "PANIC_BUTTON"
    status: str = "ACTIVE"
    note: str
    created_at: str
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
