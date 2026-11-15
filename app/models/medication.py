"""Medication and DoseLog models for scheduling and tracking adherence."""

from datetime import datetime, timezone
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
        description="List of times or slots (e.g. ['08:00', '20:00'])",
    )
    frequency: str = Field(default="Daily", max_length=100)
    pill_color: str = Field(default="#3B82F6", max_length=50)
    remaining_refills: int = Field(default=30, ge=0)
    refill_threshold: int = Field(default=7, ge=0)


class Medication(MedicationCreate):
    """Full medication document stored in Firestore."""

    id: str
    elder_id: str
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DoseLogCreate(BaseModel):
    """Payload when recording a taken or missed dose."""

    medication_id: str
    medication_name: str
    scheduled_time: str
    status: DoseStatus = DoseStatus.TAKEN
    notes: Optional[str] = Field(default=None, max_length=300)


class DoseLog(DoseLogCreate):
    """Dose log document stored in Firestore."""

    id: str
    elder_id: str
    logged_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    logged_by: str = Field(default="system", description="Name or role of person recording")
    taken_at: Optional[str] = None
    confirmed_by: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if not self.taken_at:
            self.taken_at = self.logged_at
        if not self.confirmed_by:
            self.confirmed_by = self.logged_by


# Compatibility alias
MedicationLog = DoseLog
MedicationLogCreate = DoseLogCreate


class AdherenceStats(BaseModel):
    """Adherence analytics for an elder."""

    elder_id: str
    total_logged: int
    taken_count: int
    missed_count: int
    adherence_percentage: float
    needs_refill_count: int
