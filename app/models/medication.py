"""Medication management and adherence tracking models."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class DoseStatus(str, Enum):
    """Status of a scheduled medication dose."""

    TAKEN = "TAKEN"
    MISSED = "MISSED"
    SKIPPED = "SKIPPED"


class MedicationCreate(BaseModel):
    """Payload for creating a new medication."""

    name: str = Field(..., min_length=1, max_length=120)
    dosage: str = Field(..., min_length=1, max_length=100, description="e.g. 10mg, 1 tablet")
    instructions: str = Field(..., min_length=1, max_length=300, description="e.g. Take with food")
    schedule_times: List[str] = Field(
        default=["08:00"],
        description="List of times or meal slots (e.g. ['08:00', '20:00'])",
    )
    frequency: str = Field(default="Daily", max_length=100)
    pill_color: str = Field(default="#3B82F6", max_length=50, description="Color code or visual cue")
    remaining_refills: int = Field(default=30, ge=0)
    refill_threshold: int = Field(default=7, ge=0)


class Medication(MedicationCreate):
    """Full medication entity stored in database."""

    id: str
    elder_id: str
    is_active: bool = True
    created_at: str


class MedicationLogCreate(BaseModel):
    """Payload when recording a taken or missed dose."""

    medication_id: str
    medication_name: str
    scheduled_time: str
    status: DoseStatus = DoseStatus.TAKEN
    notes: Optional[str] = Field(default=None, max_length=300)


class MedicationLog(MedicationLogCreate):
    """Full medication dose log stored in database."""

    id: str
    elder_id: str
    taken_at: str
    confirmed_by: str


class AdherenceStats(BaseModel):
    """Adherence analytics for an elder."""

    elder_id: str
    total_logged: int
    taken_count: int
    missed_count: int
    adherence_percentage: float
    needs_refill_count: int
