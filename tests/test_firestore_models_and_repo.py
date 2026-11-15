"""Tests for Firestore models and fake in-memory repository operations.

Covers:
- ElderProfile
- Member (role, hashed passcode)
- Medication
- DoseLog
- Appointment
- ChangeRequest
- AuditEntry
- /health endpoint
"""

from starlette.testclient import TestClient
from app.core.database import FakeInMemoryRepository
from app.core.security import hash_passcode, verify_passcode
from app.models import (
    Appointment,
    AppointmentStatus,
    AuditEntry,
    ChangeRequest,
    ChangeRequestStatus,
    DoseLog,
    DoseStatus,
    ElderProfile,
    EntityType,
    Medication,
    Member,
    MemberRole,
)


def test_health_endpoint(client: TestClient):
    """Verify /health endpoint returns status, app name, and version."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["app"] == "CareCircle"
    assert "version" in data
    assert "environment" in data


def test_elder_profile_model_and_repo(fake_repo: FakeInMemoryRepository):
    """Verify ElderProfile model creation, serialization, and repo operations."""
    elder = ElderProfile(
        id="elder_101",
        name="Eleanor Vance",
        date_of_birth="1942-08-15",
        emergency_contact="Daughter Jane: +1-555-0199",
        medical_notes="Penicillin allergy. Hypertension.",
        timezone="America/New_York",
    )
    saved = fake_repo.set("elder_profiles", elder.id, elder.model_dump())
    assert saved["id"] == "elder_101"

    fetched = fake_repo.get("elder_profiles", "elder_101")
    assert fetched is not None
    assert fetched["name"] == "Eleanor Vance"
    assert fetched["date_of_birth"] == "1942-08-15"

    loaded = ElderProfile(**fetched)
    assert loaded.name == elder.name
    assert loaded.emergency_contact == elder.emergency_contact


def test_member_model_with_hashed_passcode(fake_repo: FakeInMemoryRepository):
    """Verify Member model with role and bcrypt hashed passcode."""
    raw_passcode = "carePass99"
    hashed = hash_passcode(raw_passcode)

    member = Member(
        id="member_202",
        elder_id="elder_101",
        name="Nurse Jackie",
        role=MemberRole.CARETAKER,
        passcode_hash=hashed,
        phone="+1-555-4422",
    )
    fake_repo.set("members", member.id, member.model_dump())

    fetched = fake_repo.get("members", member.id)
    assert fetched is not None
    assert fetched["role"] == "caretaker"
    assert verify_passcode(raw_passcode, fetched["passcode_hash"]) is True
    assert verify_passcode("wrongPass", fetched["passcode_hash"]) is False


def test_medication_model_and_refills(fake_repo: FakeInMemoryRepository):
    """Verify Medication model with schedule times, refills, and queries."""
    med = Medication(
        id="med_303",
        elder_id="elder_101",
        name="Metoprolol",
        dosage="25 mg",
        instructions="Take 1 tablet twice daily with water",
        schedule_times=["08:00", "20:00"],
        frequency="Twice Daily",
        pill_color="#10B981",
        remaining_refills=14,
        refill_threshold=5,
        is_active=True,
    )
    fake_repo.set("medications", med.id, med.model_dump())

    results = fake_repo.list("medications", filters=[("elder_id", "==", "elder_101")])
    assert len(results) == 1
    assert results[0]["name"] == "Metoprolol"
    assert results[0]["schedule_times"] == ["08:00", "20:00"]


def test_doselog_model(fake_repo: FakeInMemoryRepository):
    """Verify DoseLog model records taken/missed statuses."""
    log = DoseLog(
        id="log_404",
        elder_id="elder_101",
        medication_id="med_303",
        medication_name="Metoprolol",
        scheduled_time="08:00",
        status=DoseStatus.TAKEN,
        logged_by="Self (Rose)",
        notes="Taken after oatmeal",
    )
    fake_repo.set("dose_logs", log.id, log.model_dump())

    fetched = fake_repo.get("dose_logs", log.id)
    assert fetched is not None
    assert fetched["status"] == DoseStatus.TAKEN.value
    assert fetched["logged_by"] == "Self (Rose)"


def test_appointment_model(fake_repo: FakeInMemoryRepository):
    """Verify Appointment model attributes and status updates."""
    appt = Appointment(
        id="appt_505",
        elder_id="elder_101",
        title="Ophthalmologist Routine Check",
        doctor_name="Dr. Lisa Chen",
        location="Vision Center, 4th Floor",
        scheduled_time="2026-11-20T14:30:00Z",
        notes="Bring current reading glasses",
        transport_needed=True,
        status=AppointmentStatus.CONFIRMED,
        created_at="2026-11-15T10:00:00Z",
    )
    fake_repo.set("appointments", appt.id, appt.model_dump())

    fake_repo.update("appointments", appt.id, {"status": AppointmentStatus.COMPLETED.value})
    updated = fake_repo.get("appointments", appt.id)
    assert updated["status"] == "COMPLETED"


def test_change_request_model_human_in_the_loop(fake_repo: FakeInMemoryRepository):
    """Verify ChangeRequest model for AI suggestions awaiting human review."""
    change_req = ChangeRequest(
        id="cr_606",
        elder_id="elder_101",
        entity_type=EntityType.MEDICATION,
        proposed_changes={
            "name": "Gabapentin",
            "dosage": "100 mg",
            "instructions": "Take at night for nerve discomfort",
        },
        reason="Prescription draft parsed from Dr. Notes",
        ai_generated=True,
        status=ChangeRequestStatus.PENDING,
        created_by="gemini_assistant",
    )
    fake_repo.set("change_requests", change_req.id, change_req.model_dump())

    pending_list = fake_repo.list(
        "change_requests",
        filters=[("status", "==", ChangeRequestStatus.PENDING.value)],
    )
    assert len(pending_list) == 1
    assert pending_list[0]["ai_generated"] is True

    # Human reviews and approves
    fake_repo.update("change_requests", change_req.id, {
        "status": ChangeRequestStatus.APPROVED.value,
        "reviewed_by": "Nurse Jackie",
        "reviewed_at": "2026-11-15T10:15:00Z",
    })
    approved = fake_repo.get("change_requests", change_req.id)
    assert approved["status"] == "APPROVED"
    assert approved["reviewed_by"] == "Nurse Jackie"


def test_audit_entry_model(fake_repo: FakeInMemoryRepository):
    """Verify AuditEntry model captures actions and actor roles."""
    audit = AuditEntry(
        id="audit_707",
        elder_id="elder_101",
        action="CHANGE_REQUEST_APPROVED",
        actor_id="member_202",
        actor_role="caretaker",
        details={"change_request_id": "cr_606", "approved": True},
        ip_address="192.168.1.100",
    )
    fake_repo.set("audit_logs", audit.id, audit.model_dump())

    logs = fake_repo.list("audit_logs", filters=[("elder_id", "==", "elder_101")])
    assert len(logs) == 1
    assert logs[0]["action"] == "CHANGE_REQUEST_APPROVED"
    assert logs[0]["actor_role"] == "caretaker"
