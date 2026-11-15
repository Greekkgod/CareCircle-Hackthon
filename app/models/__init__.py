"""Pydantic Firestore data models for CareCircle platform."""

from app.models.ai_draft import (
    AIDraft,
    ConfirmDraftRequest,
    DoctorBriefingRequest,
    DraftStatus,
    DraftType,
    ParseNoteRequest,
    PrescriptionPhotoRequest,
    VoiceOrNaturalLanguageRequest,
    WhyAmITakingThisRequest,
)
from app.models.appointment import Appointment, AppointmentCreate, AppointmentStatus
from app.models.audit import AuditEntry, AuditEntryCreate
from app.models.auth import PasscodeLogin, RateLimitStatus, TokenResponse, UserProfile, UserRole
from app.models.change_request import (
    ChangeRequest,
    ChangeRequestCreate,
    ChangeRequestStatus,
    EntityType,
)
from app.models.checkin import CheckIn, CheckInCreate, EmergencyAlert, EmergencySOSCreate, MoodLevel
from app.models.medication import (
    AdherenceStats,
    DoseLog,
    DoseLogCreate,
    DoseStatus,
    Medication,
    MedicationCreate,
    MedicationLog,
    MedicationLogCreate,
)
from app.models.member import (
    ElderProfile,
    ElderProfileCreate,
    Member,
    MemberCreate,
    MemberRole,
)
from app.models.notification import (
    AlertPriority,
    DigestQueueItem,
    EscalationConfig,
    EscalationLevel,
    NotificationLog,
    NotificationStatus,
    PendingNotification,
    QuietHoursConfig,
    SimulationTimeRequest,
    SimulationTimeResponse,
)

__all__ = [
    # Core Firestore Entities required by platform specification
    "ElderProfile",
    "ElderProfileCreate",
    "Member",
    "MemberCreate",
    "MemberRole",
    "Medication",
    "MedicationCreate",
    "DoseLog",
    "DoseLogCreate",
    "DoseStatus",
    "Appointment",
    "AppointmentCreate",
    "AppointmentStatus",
    "ChangeRequest",
    "ChangeRequestCreate",
    "ChangeRequestStatus",
    "EntityType",
    "AuditEntry",
    "AuditEntryCreate",
    # Additional helpers
    "AdherenceStats",
    "MedicationLog",
    "MedicationLogCreate",
    "AIDraft",
    "ConfirmDraftRequest",
    "DraftStatus",
    "DraftType",
    "ParseNoteRequest",
    "PrescriptionPhotoRequest",
    "VoiceOrNaturalLanguageRequest",
    "WhyAmITakingThisRequest",
    "DoctorBriefingRequest",
    "PasscodeLogin",
    "RateLimitStatus",
    "TokenResponse",
    "UserProfile",
    "UserRole",
    "CheckIn",
    "CheckInCreate",
    "EmergencyAlert",
    "EmergencySOSCreate",
    "MoodLevel",
    # Notification & Escalation Entities
    "AlertPriority",
    "EscalationLevel",
    "NotificationStatus",
    "NotificationLog",
    "QuietHoursConfig",
    "EscalationConfig",
    "PendingNotification",
    "DigestQueueItem",
    "SimulationTimeRequest",
    "SimulationTimeResponse",
]
