"""Tests for the consent flow:
- Caretaker edits create pending ChangeRequests with plain-language summaries
- Elder approves / declines with immediate database application and immutable audit logging
- Expiry handling: expired requests cannot be approved or declined
- Duplicate request prevention: concurrent pending requests for the same entity are rejected with 409
"""

from datetime import datetime, timedelta, timezone

from starlette.testclient import TestClient

from app.core.database import db
from app.models.change_request import ChangeRequestStatus, EntityType
from app.services.change_request_service import (
    create_change_request,
    generate_plain_language_summary,
)


def test_plain_language_summary_generation():
    """Verify summaries are easy to understand for seniors."""
    # Medication edit
    summary_edit = generate_plain_language_summary(
        entity_type=EntityType.MEDICATION,
        proposed_changes={"id": "med_sample_1", "name": "Lisinopril", "dosage": "20 mg"},
        reason="Blood pressure elevated",
        created_by="Nurse Sarah",
    )
    assert "Nurse Sarah suggests to change dose to 20 mg" in summary_edit
    assert "Reason: Blood pressure elevated" in summary_edit

    # Appointment rescheduling
    summary_appt = generate_plain_language_summary(
        entity_type=EntityType.APPOINTMENT,
        proposed_changes={
            "title": "Cardiology Follow-up",
            "doctor_name": "Dr. Adams",
            "location": "Room 402",
            "scheduled_time": "Friday 10:00 AM",
        },
        reason="Doctor rescheduled clinics",
        created_by="Nurse Sarah",
    )
    assert "Nurse Sarah suggests scheduling 'Cardiology Follow-up' with Dr. Adams" in summary_appt
    assert "Room 402" in summary_appt


def test_consent_flow_caretaker_edit_and_elder_approval(
    client: TestClient, caretaker_token: str, elder_token: str
):
    """Verify caretaker edit creates a plain-language request that elder approves."""
    h_care = {"Authorization": f"Bearer {caretaker_token}"}
    h_elder = {"Authorization": f"Bearer {elder_token}"}

    # Initial dosage
    assert db.get("medications", "med_sample_1")["dosage"] == "10 mg"

    # Caretaker submits dosage change
    resp_edit = client.patch(
        "/api/medications/med_sample_1",
        json={"dosage": "25 mg", "reason": "Adjusting for morning blood pressure"},
        headers=h_care,
    )
    assert resp_edit.status_code == 202
    cr = resp_edit.json()["change_request"]
    cr_id = cr["id"]
    assert "plain_language_summary" in cr
    assert "25 mg" in cr["plain_language_summary"]

    # Verify Lisinopril is still 10 mg before elder approval
    assert db.get("medications", "med_sample_1")["dosage"] == "10 mg"

    # Elder approves the change request
    resp_approve = client.post(f"/api/change-requests/{cr_id}/approve", headers=h_elder)
    assert resp_approve.status_code == 200
    assert resp_approve.json()["action"] == "approved"

    # Verify Lisinopril dosage is now applied in database
    assert db.get("medications", "med_sample_1")["dosage"] == "25 mg"

    # Verify immutable audit log
    audits = db.list("audit_logs", filters=[("action", "==", "CHANGE_REQUEST_APPROVED")])
    assert any(a["details"].get("change_request_id") == cr_id for a in audits)


def test_consent_flow_elder_decline(
    client: TestClient, caretaker_token: str, elder_token: str
):
    """Verify elder decline rejects the request without mutating the care plan."""
    h_care = {"Authorization": f"Bearer {caretaker_token}"}
    h_elder = {"Authorization": f"Bearer {elder_token}"}

    # Caretaker submits another change
    resp_edit = client.patch(
        "/api/medications/med_sample_1",
        json={"dosage": "100 mg", "reason": "Experimental dosage"},
        headers=h_care,
    )
    assert resp_edit.status_code == 202
    cr_id = resp_edit.json()["change_request"]["id"]

    # Elder declines/rejects
    resp_decline = client.post(
        f"/api/change-requests/{cr_id}/reject",
        json={"reason": "Dose is too high, prefer current regimen"},
        headers=h_elder,
    )
    assert resp_decline.status_code == 200
    assert resp_decline.json()["status"] == "REJECTED"

    # Verify medication was NOT changed to 100 mg
    assert db.get("medications", "med_sample_1")["dosage"] != "100 mg"

    # Verify immutable audit log
    audits = db.list("audit_logs", filters=[("action", "==", "CHANGE_REQUEST_REJECTED")])
    assert any(a["details"].get("change_request_id") == cr_id for a in audits)


def test_duplicate_change_requests_prevented(
    client: TestClient, caretaker_token: str
):
    """Verify submitting a second change request for an entity with a pending request is rejected with 409."""
    h_care = {"Authorization": f"Bearer {caretaker_token}"}

    # 1. First edit: succeeds with 202 Accepted
    resp_1 = client.patch(
        "/api/medications/med_sample_1",
        json={"dosage": "30 mg", "reason": "First adjustment"},
        headers=h_care,
    )
    assert resp_1.status_code == 202

    # 2. Second edit while first is still pending: rejected with 409 Conflict!
    resp_2 = client.patch(
        "/api/medications/med_sample_1",
        json={"dosage": "35 mg", "reason": "Second adjustment"},
        headers=h_care,
    )
    assert resp_2.status_code == 409
    assert "pending change request for this medication already exists" in resp_2.json()["detail"].lower()


def test_expired_change_requests_cannot_be_approved(
    client: TestClient, elder_token: str
):
    """Verify that a change request past its expiration date is marked EXPIRED and cannot be approved."""
    h_elder = {"Authorization": f"Bearer {elder_token}"}

    # Create a change request directly with past expires_at
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    cr = create_change_request(
        elder_id="elder_1",
        entity_type=EntityType.MEDICATION,
        entity_id="med_sample_2",
        proposed_changes={"id": "med_sample_2", "dosage": "1000 mg"},
        reason="Old proposal",
        created_by="Nurse Sarah",
        expires_in_hours=72,
    )

    # Backdate expires_at in repository to simulate expiration
    db.update("change_requests", cr.id, {"expires_at": past_iso})

    # Elder attempts to approve the expired request
    resp_approve = client.post(f"/api/change-requests/{cr.id}/approve", headers=h_elder)
    assert resp_approve.status_code == 400
    assert "expired" in resp_approve.json()["detail"].lower()

    # Elder attempts to decline the expired request
    resp_decline = client.post(f"/api/change-requests/{cr.id}/reject", headers=h_elder)
    assert resp_decline.status_code == 400
    assert "expired" in resp_decline.json()["detail"].lower()

    # Verify status in database is now EXPIRED
    updated_cr = db.get("change_requests", cr.id)
    assert updated_cr["status"] == ChangeRequestStatus.EXPIRED.value
