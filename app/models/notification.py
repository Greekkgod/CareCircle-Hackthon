"""Notification, escalation, and audit logging models for CareCircle.

Provides data structures for escalation levels, priorities, quiet hours,
notification logs with idempotency tracking, and scheduler payloads.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertPriority(str, Enum):
    """Priority level for alert dispatching."""

    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    LOW = "LOW"


class EscalationLevel(str, Enum):
    """The hierarchical notification ladder step."""

    ELDER = "elder"
    CARETAKER = "caretaker"
    FAMILY = "family"


class NotificationChannel(str, Enum):
    """Communication channel for dispatch."""

    EMAIL = "email"
    IN_APP = "in_app"


class NotificationStatus(str, Enum):
    """Execution status of a notification attempt."""

    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    BATCHED = "BATCHED"
    SKIPPED = "SKIPPED"


class QuietHoursConfig(BaseModel):
    """Quiet hours window definition (24-hour time)."""

    enabled: bool = True
    start_hour: int = Field(default=22, ge=0, le=23, description="Quiet hours start (e.g. 22 for 10 PM)")
    end_hour: int = Field(default=7, ge=0, le=23, description="Quiet hours end (e.g. 7 for 7 AM)")

    def is_quiet_hour(self, dt: datetime) -> bool:
        """Return True if given datetime falls into the quiet hours window."""
        if not self.enabled:
            return False
        hour = dt.hour
        if self.start_hour > self.end_hour:
            # Over-midnight quiet hours, e.g. 22:00 to 07:00
            return hour >= self.start_hour or hour < self.end_hour
        if self.start_hour < self.end_hour:
            # Same-day quiet hours, e.g. 13:00 to 15:00
            return self.start_hour <= hour < self.end_hour
        # Equal start and end means disabled
        return False


class EscalationConfig(BaseModel):
    """Configuration timing thresholds and quiet hours for the escalation ladder."""

    elder_grace_minutes: int = Field(
        default=0,
        ge=0,
        description="Minutes past due time to send first reminder to elder",
    )
    caretaker_delay_minutes: int = Field(
        default=15,
        ge=1,
        description="Minutes past due time to escalate alert to caretaker",
    )
    family_delay_minutes: int = Field(
        default=30,
        ge=2,
        description="Minutes past due time to escalate alert to family",
    )
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)


class PendingNotification(BaseModel):
    """An alert action determined by the pure escalation engine."""

    idempotency_key: str
    elder_id: str
    medication_id: Optional[str] = None
    medication_name: Optional[str] = None
    scheduled_time: str
    escalation_level: EscalationLevel
    recipient_role: str
    recipient_name: str
    recipient_email: str
    subject: str
    body: str
    priority: AlertPriority = AlertPriority.HIGH


class DigestQueueItem(BaseModel):
    """Low-priority or quiet-hours alert deferred into a digest batch."""

    id: str
    elder_id: str
    recipient_role: str
    recipient_email: str
    medication_name: str
    scheduled_time: str
    reason: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class NotificationLog(BaseModel):
    """Immutable sent-log entry recording each dispatched or batched notification."""

    id: str
    elder_id: str
    recipient_role: str
    recipient_email: str
    escalation_level: EscalationLevel
    idempotency_key: str
    subject: str
    body: str
    priority: AlertPriority = AlertPriority.HIGH
    status: NotificationStatus = NotificationStatus.SENT
    attempt_count: int = 1
    last_attempt_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    error_message: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SimulationTimeRequest(BaseModel):
    """Payload for simulating time advancement and triggering escalation cycles."""

    simulated_now: Optional[str] = Field(default=None, description="ISO datetime string for simulation")
    advance_minutes: int = Field(default=0, ge=0, description="Advance simulated clock by minutes")
    elder_id: str = Field(default="elder_1", description="Target elder profile")
    dry_run: bool = Field(default=False, description="Preview actions without writing sent logs")


class SimulationTimeResponse(BaseModel):
    """Response payload detailing actions triggered by the simulated tick."""

    simulated_time: str
    elder_id: str
    is_quiet_hours: bool
    notifications_sent: List[Dict[str, Any]] = []
    notifications_batched: List[Dict[str, Any]] = []
    notifications_skipped: List[Dict[str, Any]] = []
    summary: str
