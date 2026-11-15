"""Tests for role-based access control (elder, caretaker, family)."""

from starlette.testclient import TestClient


def test_elder_permissions(client: TestClient, elder_token: str):
    """Verify elder can view meds and log dose, but cannot add meds."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # Elder can read medications
    resp = client.get("/api/medications/", headers=headers)
    assert resp.status_code == 200

    # Elder can log dose
    log_payload = {
        "medication_id": "med_sample_1",
        "medication_name": "Lisinopril",
        "scheduled_time": "08:00",
        "status": "TAKEN",
    }
    resp = client.post("/api/medications/log", json=log_payload, headers=headers)
    assert resp.status_code == 200

    # Elder CANNOT add new medication (403 Forbidden)
    new_med = {
        "name": "New Pill",
        "dosage": "5mg",
        "instructions": "Take daily",
        "schedule_times": ["09:00"],
    }
    resp = client.post("/api/medications/", json=new_med, headers=headers)
    assert resp.status_code == 403

    # Elder CANNOT confirm AI drafts (403 Forbidden)
    resp = client.post("/api/ai/drafts/draft_123/confirm", json={"approved": True}, headers=headers)
    assert resp.status_code == 403


def test_caretaker_permissions(client: TestClient, caretaker_token: str):
    """Verify caretaker has administrative access to add meds and parse notes."""
    headers = {"Authorization": f"Bearer {caretaker_token}"}

    # Caretaker can add medication
    new_med = {
        "name": "Amlodipine",
        "dosage": "5mg",
        "instructions": "Take every morning",
        "schedule_times": ["08:00"],
        "frequency": "Daily",
        "remaining_refills": 30,
        "refill_threshold": 7,
    }
    resp = client.post("/api/medications/", json=new_med, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Amlodipine"

    # Caretaker can parse notes
    parse_payload = {"raw_text": "Start Amlodipine 5mg once daily in morning."}
    resp = client.post("/api/ai/parse-draft", json=parse_payload, headers=headers)
    assert resp.status_code == 200


def test_family_permissions(client: TestClient, family_token: str):
    """Verify family role can view reassurance metrics but not mutate clinical plans."""
    headers = {"Authorization": f"Bearer {family_token}"}

    # Family can view adherence and medication list
    resp = client.get("/api/medications/adherence", headers=headers)
    assert resp.status_code == 200
    assert "adherence_percentage" in resp.json()

    resp = client.get("/api/medications/", headers=headers)
    assert resp.status_code == 200

    # Family CANNOT add new medication (403 Forbidden)
    new_med = {"name": "Test", "dosage": "1mg", "instructions": "None"}
    resp = client.post("/api/medications/", json=new_med, headers=headers)
    assert resp.status_code == 403

    # Family CANNOT parse AI prescription drafts (403 Forbidden)
    resp = client.post("/api/ai/parse-draft", json={"raw_text": "Take test 5mg"}, headers=headers)
    assert resp.status_code == 403
