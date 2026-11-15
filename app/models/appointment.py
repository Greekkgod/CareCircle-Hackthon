"""Appointment models for elderly care."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class AppointmentStatus(str, Enum):
    """Status of an elderly medical appointment."""

    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    COMPLETED = "COMPLETED"


class AppointmentCreate(BaseModel):
    """Payload to schedule an appointment."""

    title: str = Field(..., min_length=2, max_length=150)
    doctor_name: str = Field(..., min_length=2, max_length=120)
    location: str = Field(..., min_length=2, max_length=250)
    scheduled_time: str = Field(..., description="ISO 8601 string or readable date/time")
    notes: Optional[str] = Field(default=None, max_length=500)
    transport_needed: bool = Field(default=False)


class Appointment(AppointmentCreate):
    """Full appointment entity stored in database."""

    id: str
    elder_id: str
    status: AppointmentStatus = AppointmentStatus.CONFIRMED
    created_at: str
