"""Tests for medication adherence, dose logging, refills, and checkins."""

from starlette.testclient import TestClient

from app.core.database import db


def test_log_dose_decrements_refills(client: TestClient, elder_token: str):
    """Verify taking a medication decrements the remaining refills."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # Inspect initial refills
    initial_med = db.get("medications", "med_sample_1")
    initial_refills = initial_med["remaining_refills"]

    # Log taken dose
    resp = client.post(
        "/api/medications/log",
        json={
            "medication_id": "med_sample_1",
            "medication_name": "Lisinopril",
            "scheduled_time": "08:00",
            "status": "TAKEN",
        },
        headers=headers,
    )
    assert resp.status_code == 200

    updated_med = db.get("medications", "med_sample_1")
    assert updated_med["remaining_refills"] == initial_refills - 1


def test_adherence_calculation(client: TestClient, elder_token: str):
    """Verify adherence rate computes accurately across logged doses."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # Log 1 taken dose
    client.post(
        "/api/medications/log",
        json={
            "medication_id": "med_sample_1",
            "medication_name": "Lisinopril",
            "scheduled_time": "08:00",
            "status": "TAKEN",
        },
        headers=headers,
    )

    # Log 1 missed dose
    client.post(
        "/api/medications/log",
        json={
            "medication_id": "med_sample_1",
            "medication_name": "Lisinopril",
            "scheduled_time": "20:00",
            "status": "MISSED",
        },
        headers=headers,
    )

    resp = client.get("/api/medications/adherence", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_logged"] == 2
    assert data["taken_count"] == 1
    assert data["missed_count"] == 1
    assert data["adherence_percentage"] == 50.0


def test_daily_mood_checkin(client: TestClient, elder_token: str):
    """Verify elder can record daily mood check-in."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    resp = client.post("/api/checkins/", json={"mood": "GREAT", "note": "Feeling energetic"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["mood"] == "GREAT"


def test_emergency_sos_trigger_and_resolve(
    client: TestClient, elder_token: str, caretaker_token: str
):
    """Verify elder can trigger SOS and caretaker can resolve it."""
    elder_headers = {"Authorization": f"Bearer {elder_token}"}
    caretaker_headers = {"Authorization": f"Bearer {caretaker_token}"}

    # Trigger SOS
    resp_sos = client.post(
        "/api/checkins/sos",
        json={"note": "Assistance needed in kitchen"},
        headers=elder_headers,
    )
    assert resp_sos.status_code == 200
    alert_id = resp_sos.json()["id"]
    assert resp_sos.json()["status"] == "ACTIVE"

    # Caretaker views and resolves
    resp_resolve = client.post(
        f"/api/checkins/emergencies/{alert_id}/resolve",
        headers=caretaker_headers,
    )
    assert resp_resolve.status_code == 200
    assert resp_resolve.json()["status"] == "RESOLVED"
