"""Authentication and User Pydantic models."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """Supported roles in the CareCircle platform."""

    ELDER = "elder"
    CARETAKER = "caretaker"
    FAMILY = "family"


class PasscodeLogin(BaseModel):
    """User passcode authentication request."""

    identifier: str = Field(..., min_length=1, max_length=100, description="Username or user ID")
    passcode: str = Field(..., min_length=4, max_length=64, description="Numeric PIN or secret passcode")


class TokenResponse(BaseModel):
    """JWT response payload returned on successful authentication."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    name: str
    role: UserRole
    elder_id: str


class RateLimitStatus(BaseModel):
    """Passcode rate limiting status report."""

    identifier: str
    is_locked: bool
    remaining_attempts: int
    lockout_seconds_remaining: int


class UserProfile(BaseModel):
    """Public user profile model."""

    id: str
    name: str
    role: UserRole
    elder_id: Optional[str] = None
    phone: Optional[str] = None
    created_at: str
