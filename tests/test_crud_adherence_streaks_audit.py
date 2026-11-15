"""Comprehensive tests for Medication and Appointment CRUD, Dose Logging (taken/missed/snoozed),
Adherence & Streaks calculation, and immutable AuditEntry logging on every change.
"""

from starlette.testclient import TestClient

from app.core.database import db
from app.services.medication_service import calculate_streaks


def test_medication_crud_operations(client: TestClient, elder_token: str):
    """Test full CRUD operations on medications by elder."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # 1. CREATE
    create_payload = {
        "name": "Levothyroxine",
        "dosage": "50 mcg",
        "instructions": "Take in morning on an empty stomach",
        "schedule_times": ["07:00"],
        "frequency": "Daily",
        "pill_color": "#F59E0B",
        "remaining_refills": 60,
        "refill_threshold": 10,
    }
    resp_create = client.post("/api/medications/", json=create_payload, headers=headers)
    assert resp_create.status_code == 201
    med_id = resp_create.json()["id"]

    # Verify immutable AuditEntry for creation
    audits = db.list("audit_logs", filters=[("action", "==", "MEDICATION_CREATED")])
    assert any(a["details"].get("medication_id") == med_id for a in audits)

    # 2. READ SINGLE
    resp_get = client.get(f"/api/medications/{med_id}", headers=headers)
    assert resp_get.status_code == 200
    assert resp_get.json()["name"] == "Levothyroxine"
    assert resp_get.json()["dosage"] == "50 mcg"

    # 3. READ LIST
    resp_list = client.get("/api/medications/", headers=headers)
    assert resp_list.status_code == 200
    assert any(m["id"] == med_id for m in resp_list.json())

    # 4. UPDATE DIRECTLY BY ELDER
    resp_update = client.patch(
        f"/api/medications/{med_id}",
        json={"dosage": "75 mcg", "instructions": "Take with water only"},
        headers=headers,
    )
    assert resp_update.status_code == 200
    assert resp_update.json()["status"] == "applied"

    # Verify update in DB
    updated_med = db.get("medications", med_id)
    assert updated_med["dosage"] == "75 mcg"

    # Verify immutable AuditEntry for update
    audits_update = db.list("audit_logs", filters=[("action", "==", "MEDICATION_UPDATED_BY_ELDER")])
    assert any(a["details"].get("medication_id") == med_id for a in audits_update)

    # 5. DELETE
    resp_delete = client.delete(f"/api/medications/{med_id}", headers=headers)
    assert resp_delete.status_code == 200

    # Verify deleted from DB
    assert db.get("medications", med_id) is None

    # Verify immutable AuditEntry for deletion
    audits_del = db.list("audit_logs", filters=[("action", "==", "MEDICATION_DELETED")])
    assert any(a["details"].get("medication_id") == med_id for a in audits_del)


def test_appointment_crud_operations(client: TestClient, elder_token: str):
    """Test full CRUD operations on appointments by elder."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # 1. CREATE
    appt_payload = {
        "title": "Cardiology Stress Test",
        "doctor_name": "Dr. Angela Vance",
        "location": "Metro Hospital, Cardiac Wing 3",
        "scheduled_time": "2026-12-05 09:30",
        "notes": "Wear comfortable running shoes",
        "transport_needed": True,
    }
    resp_create = client.post("/api/appointments/", json=appt_payload, headers=headers)
    assert resp_create.status_code == 201
    appt_id = resp_create.json()["id"]

    # Verify AuditEntry for appointment creation
    audits_create = db.list("audit_logs", filters=[("action", "==", "APPOINTMENT_CREATED")])
    assert any(a["details"].get("appointment_id") == appt_id for a in audits_create)

    # 2. READ SINGLE
    resp_get = client.get(f"/api/appointments/{appt_id}", headers=headers)
    assert resp_get.status_code == 200
    assert resp_get.json()["title"] == "Cardiology Stress Test"

    # 3. READ LIST
    resp_list = client.get("/api/appointments/", headers=headers)
    assert resp_list.status_code == 200
    assert any(a["id"] == appt_id for a in resp_list.json())

    # 4. UPDATE DIRECTLY BY ELDER
    resp_update = client.patch(
        f"/api/appointments/{appt_id}",
        json={"location": "Metro Hospital, Cardiac Wing 4B"},
        headers=headers,
    )
    assert resp_update.status_code == 200
    assert resp_update.json()["status"] == "applied"
    assert db.get("appointments", appt_id)["location"] == "Metro Hospital, Cardiac Wing 4B"

    # Verify AuditEntry for appointment update
    audits_update = db.list("audit_logs", filters=[("action", "==", "APPOINTMENT_UPDATED_BY_ELDER")])
    assert any(a["details"].get("appointment_id") == appt_id for a in audits_update)

    # 5. DELETE
    resp_del = client.delete(f"/api/appointments/{appt_id}", headers=headers)
    assert resp_del.status_code == 200
    assert db.get("appointments", appt_id) is None

    # Verify AuditEntry for appointment deletion
    audits_del = db.list("audit_logs", filters=[("action", "==", "APPOINTMENT_DELETED")])
    assert any(a["details"].get("appointment_id") == appt_id for a in audits_del)


def test_dose_logging_taken_missed_snoozed_and_audits(client: TestClient, elder_token: str):
    """Test dose logging with taken, missed, and snoozed statuses with immutable audit entries."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # 1. Log TAKEN
    resp_taken = client.post(
        "/api/medications/log",
        json={
            "medication_id": "med_sample_1",
            "medication_name": "Lisinopril",
            "scheduled_time": "08:00",
            "status": "TAKEN",
            "notes": "Taken with breakfast",
        },
        headers=headers,
    )
    assert resp_taken.status_code == 200
    assert resp_taken.json()["status"] == "TAKEN"

    # Verify DOSE_TAKEN AuditEntry
    audits_taken = db.list("audit_logs", filters=[("action", "==", "DOSE_TAKEN")])
    assert len(audits_taken) >= 1
    assert audits_taken[-1]["details"]["medication_id"] == "med_sample_1"

    # 2. Log MISSED
    resp_missed = client.post(
        "/api/medications/log",
        json={
            "medication_id": "med_sample_1",
            "medication_name": "Lisinopril",
            "scheduled_time": "08:00",
            "status": "MISSED",
            "notes": "Elder was away on a morning walk",
        },
        headers=headers,
    )
    assert resp_missed.status_code == 200
    assert resp_missed.json()["status"] == "MISSED"

    # Verify DOSE_MISSED AuditEntry
    audits_missed = db.list("audit_logs", filters=[("action", "==", "DOSE_MISSED")])
    assert len(audits_missed) >= 1

    # 3. Log SNOOZED
    resp_snooze = client.post(
        "/api/medications/log",
        json={
            "medication_id": "med_sample_1",
            "medication_name": "Lisinopril",
            "scheduled_time": "08:00",
            "status": "SNOOZED",
            "notes": "Remind in 30 minutes",
            "snooze_until": "2026-11-15T08:30:00Z",
        },
        headers=headers,
    )
    assert resp_snooze.status_code == 200
    assert resp_snooze.json()["status"] == "SNOOZED"
    assert resp_snooze.json()["snooze_until"] == "2026-11-15T08:30:00Z"

    # Verify DOSE_SNOOZED AuditEntry
    audits_snooze = db.list("audit_logs", filters=[("action", "==", "DOSE_SNOOZED")])
    assert len(audits_snooze) >= 1
    assert audits_snooze[-1]["details"]["snooze_until"] == "2026-11-15T08:30:00Z"


def test_adherence_rate_and_streak_calculation(client: TestClient, elder_token: str):
    """Test adherence rate metrics and consecutive days streak algorithm."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # Test unit calculation helper across multiple consecutive days
    synthetic_logs = [
        {"logged_at": "2026-11-10T08:00:00Z", "status": "TAKEN"},
        {"logged_at": "2026-11-11T08:00:00Z", "status": "TAKEN"},
        {"logged_at": "2026-11-12T08:00:00Z", "status": "TAKEN"},
        {"logged_at": "2026-11-13T08:00:00Z", "status": "MISSED"},  # Streak breaks here
        {"logged_at": "2026-11-14T08:00:00Z", "status": "TAKEN"},
        {"logged_at": "2026-11-15T08:00:00Z", "status": "TAKEN"},
    ]
    current_streak, longest_streak = calculate_streaks(synthetic_logs)
    assert longest_streak == 3   # Days 10, 11, 12
    assert current_streak == 2   # Days 14, 15

    # Test API endpoint returns streaks and counts
    # Log 2 taken doses and 1 snoozed dose
    client.post(
        "/api/medications/log",
        json={"medication_id": "med_sample_1", "medication_name": "Lisinopril", "scheduled_time": "08:00", "status": "TAKEN"},
        headers=headers,
    )
    client.post(
        "/api/medications/log",
        json={"medication_id": "med_sample_1", "medication_name": "Lisinopril", "scheduled_time": "08:00", "status": "SNOOZED", "snooze_until": "10:00"},
        headers=headers,
    )

    resp = client.get("/api/medications/adherence", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["taken_count"] >= 1
    assert data["snoozed_count"] >= 1
    assert "current_streak_days" in data
    assert "longest_streak_days" in data
    assert data["adherence_percentage"] == 100.0
