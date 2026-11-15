"""ElderProfile and Member models for authentication and access control."""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MemberRole(str, Enum):
    """Role-based access levels."""

    ELDER = "elder"
    CARETAKER = "caretaker"
    FAMILY = "family"


class ElderProfileCreate(BaseModel):
    """Payload to create or update an elder profile."""

    name: str = Field(..., min_length=1, max_length=120)
    date_of_birth: Optional[str] = Field(default=None, description="YYYY-MM-DD format")
    emergency_contact: str = Field(..., min_length=3, max_length=150)
    medical_notes: Optional[str] = Field(default=None, max_length=1000)
    timezone: str = Field(default="UTC", max_length=50)
    email: Optional[str] = Field(default=None, max_length=120)
    quiet_hours_start: int = Field(default=22, ge=0, le=23, description="Quiet hours start hour (0-23)")
    quiet_hours_end: int = Field(default=7, ge=0, le=23, description="Quiet hours end hour (0-23)")


class ElderProfile(ElderProfileCreate):
    """Elder profile stored in Firestore."""

    id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class MemberCreate(BaseModel):
    """Payload to register a new circle member."""

    elder_id: str
    name: str = Field(..., min_length=1, max_length=120)
    role: MemberRole
    passcode: str = Field(..., min_length=4, max_length=64, description="Plaintext passcode to be hashed")
    phone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=120)


class Member(BaseModel):
    """Circle member stored in Firestore with bcrypt hashed passcode."""

    id: str
    elder_id: str
    name: str
    role: MemberRole
    passcode_hash: str
    phone: Optional[str] = None
    email: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
