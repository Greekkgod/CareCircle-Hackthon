"""Tests for the complete permission matrix across elder, caretaker, and family roles.

Matrix rules:
- elder: Full control. Adds/edits meds and appointments directly. Approves/rejects ChangeRequests.
- caretaker: Can add meds and appointments. Edits create a ChangeRequest that elder must approve.
- family: Read-only summary. All mutations (add, edit, delete, approve) are rejected with 403 Forbidden.
"""

from starlette.testclient import TestClient
from app.core.database import db


def test_passcode_login_for_all_three_roles_tied_to_same_elder(client: TestClient):
    """Verify elder, caretaker, and family can authenticate with passcodes for elder_1."""
    # 1. Elder login
    resp_elder = client.post("/api/auth/login", json={"identifier": "elder_1", "passcode": "1234"})
    assert resp_elder.status_code == 200
    assert resp_elder.json()["role"] == "elder"
    assert resp_elder.json()["elder_id"] == "elder_1"

    # 2. Caretaker login
    resp_care = client.post("/api/auth/login", json={"identifier": "caretaker_1", "passcode": "care2026"})
    assert resp_care.status_code == 200
    assert resp_care.json()["role"] == "caretaker"
    assert resp_care.json()["elder_id"] == "elder_1"

    # 3. Family login
    resp_fam = client.post("/api/auth/login", json={"identifier": "family_1", "passcode": "fam1234"})
    assert resp_fam.status_code == 200
    assert resp_fam.json()["role"] == "family"
    assert resp_fam.json()["elder_id"] == "elder_1"


def test_medication_permission_matrix(
    client: TestClient,
    elder_token: str,
    caretaker_token: str,
    family_token: str,
):
    """Test every role against medication actions (read, add, edit, delete, log)."""
    h_elder = {"Authorization": f"Bearer {elder_token}"}
    h_care = {"Authorization": f"Bearer {caretaker_token}"}
    h_fam = {"Authorization": f"Bearer {family_token}"}

    # 1. READ MEDS: All 3 roles can read
    assert client.get("/api/medications/", headers=h_elder).status_code == 200
    assert client.get("/api/medications/", headers=h_care).status_code == 200
    assert client.get("/api/medications/", headers=h_fam).status_code == 200

    # 2. ADD MED: Elder & Caretaker allowed; Family denied (403)
    new_med = {
        "name": "Simvastatin",
        "dosage": "20 mg",
        "instructions": "Take at bedtime",
        "schedule_times": ["21:00"],
    }
    assert client.post("/api/medications/", json=new_med, headers=h_fam).status_code == 403

    resp_add_elder = client.post("/api/medications/", json=new_med, headers=h_elder)
    assert resp_add_elder.status_code == 201
    created_id = resp_add_elder.json()["id"]

    resp_add_care = client.post(
        "/api/medications/",
        json={**new_med, "name": "Aspirin"},
        headers=h_care,
    )
    assert resp_add_care.status_code == 201

    # 3. EDIT MED:
    # - Elder: applied immediately (200)
    resp_edit_elder = client.patch(
        f"/api/medications/{created_id}",
        json={"dosage": "40 mg"},
        headers=h_elder,
    )
    assert resp_edit_elder.status_code == 200
    assert resp_edit_elder.json()["status"] == "applied"
    assert db.get("medications", created_id)["dosage"] == "40 mg"

    # - Caretaker: creates a ChangeRequest (202 Accepted), does NOT mutate immediately
    resp_edit_care = client.patch(
        f"/api/medications/{created_id}",
        json={"dosage": "80 mg", "reason": "Increased dosage per cardiology review"},
        headers=h_care,
    )
    assert resp_edit_care.status_code == 202
    assert resp_edit_care.json()["status"] == "pending_approval"
    cr_id = resp_edit_care.json()["change_request"]["id"]
    # Verify medication in DB still has 40 mg (NOT 80 mg!)
    assert db.get("medications", created_id)["dosage"] == "40 mg"

    # - Family: Denied (403)
    assert client.patch(f"/api/medications/{created_id}", json={"dosage": "10 mg"}, headers=h_fam).status_code == 403

    # 4. DELETE MED: Elder only (200); Caretaker and Family denied (403)
    assert client.delete(f"/api/medications/{created_id}", headers=h_care).status_code == 403
    assert client.delete(f"/api/medications/{created_id}", headers=h_fam).status_code == 403
    assert client.delete(f"/api/medications/{created_id}", headers=h_elder).status_code == 200

    # 5. LOG DOSE: Elder & Caretaker allowed; Family denied (403)
    log_data = {
        "medication_id": "med_sample_1",
        "medication_name": "Lisinopril",
        "scheduled_time": "08:00",
        "status": "TAKEN",
    }
    assert client.post("/api/medications/log", json=log_data, headers=h_fam).status_code == 403
    assert client.post("/api/medications/log", json=log_data, headers=h_care).status_code == 200
    assert client.post("/api/medications/log", json=log_data, headers=h_elder).status_code == 200


def test_appointment_permission_matrix(
    client: TestClient,
    elder_token: str,
    caretaker_token: str,
    family_token: str,
):
    """Test every role against appointment actions (read, add, edit, delete)."""
    h_elder = {"Authorization": f"Bearer {elder_token}"}
    h_care = {"Authorization": f"Bearer {caretaker_token}"}
    h_fam = {"Authorization": f"Bearer {family_token}"}

    # 1. READ: All allowed
    assert client.get("/api/appointments/", headers=h_elder).status_code == 200
    assert client.get("/api/appointments/", headers=h_care).status_code == 200
    assert client.get("/api/appointments/", headers=h_fam).status_code == 200

    # 2. ADD: Elder and Caretaker allowed (201); Family denied (403)
    appt_data = {
        "title": "Dental Cleaning",
        "doctor_name": "Dr. Miller",
        "location": "Suite 101",
        "scheduled_time": "2026-11-25 10:00",
    }
    assert client.post("/api/appointments/", json=appt_data, headers=h_fam).status_code == 403

    resp_add = client.post("/api/appointments/", json=appt_data, headers=h_elder)
    assert resp_add.status_code == 201
    appt_id = resp_add.json()["id"]

    # 3. EDIT:
    # - Elder applies directly (200)
    resp_elder_edit = client.patch(
        f"/api/appointments/{appt_id}",
        json={"location": "Suite 102"},
        headers=h_elder,
    )
    assert resp_elder_edit.status_code == 200
    assert db.get("appointments", appt_id)["location"] == "Suite 102"

    # - Caretaker creates ChangeRequest (202), does NOT mutate directly
    resp_care_edit = client.patch(
        f"/api/appointments/{appt_id}",
        json={"location": "Hospital Main Wing"},
        headers=h_care,
    )
    assert resp_care_edit.status_code == 202
    assert resp_care_edit.json()["status"] == "pending_approval"
    assert db.get("appointments", appt_id)["location"] == "Suite 102"

    # - Family denied (403)
    assert client.patch(f"/api/appointments/{appt_id}", json={"location": "Denied"}, headers=h_fam).status_code == 403

    # 4. DELETE: Elder only (200)
    assert client.delete(f"/api/appointments/{appt_id}", headers=h_care).status_code == 403
    assert client.delete(f"/api/appointments/{appt_id}", headers=h_fam).status_code == 403
    assert client.delete(f"/api/appointments/{appt_id}", headers=h_elder).status_code == 200


def test_changerequest_approval_workflow(
    client: TestClient,
    elder_token: str,
    caretaker_token: str,
    family_token: str,
):
    """End-to-end test of caretaker edit -> change request -> elder approval/rejection."""
    h_elder = {"Authorization": f"Bearer {elder_token}"}
    h_care = {"Authorization": f"Bearer {caretaker_token}"}
    h_fam = {"Authorization": f"Bearer {family_token}"}

    # Caretaker proposes dosage increase on Lisinopril
    resp_edit = client.patch(
        "/api/medications/med_sample_1",
        json={"dosage": "20 mg", "reason": "Physician recommendation"},
        headers=h_care,
    )
    assert resp_edit.status_code == 202
    cr_id = resp_edit.json()["change_request"]["id"]

    # Verify Lisinopril is still 10 mg
    assert db.get("medications", "med_sample_1")["dosage"] == "10 mg"

    # Family attempts to approve -> 403
    assert client.post(f"/api/change-requests/{cr_id}/approve", headers=h_fam).status_code == 403

    # Caretaker attempts to approve their own request -> 403 (Elder approval required!)
    assert client.post(f"/api/change-requests/{cr_id}/approve", headers=h_care).status_code == 403

    # Elder approves the change request -> 200
    resp_approve = client.post(f"/api/change-requests/{cr_id}/approve", headers=h_elder)
    assert resp_approve.status_code == 200
    assert resp_approve.json()["action"] == "approved"

    # Verify Lisinopril dosage in database is NOW updated to 20 mg!
    assert db.get("medications", "med_sample_1")["dosage"] == "20 mg"

    # Now test rejection flow: Caretaker submits another change request
    resp_edit2 = client.patch(
        "/api/medications/med_sample_1",
        json={"dosage": "50 mg", "reason": "Experimental dose"},
        headers=h_care,
    )
    cr_id_2 = resp_edit2.json()["change_request"]["id"]

    # Elder rejects the change request
    resp_reject = client.post(
        f"/api/change-requests/{cr_id_2}/reject",
        json={"reason": "Too high dosage"},
        headers=h_elder,
    )
    assert resp_reject.status_code == 200
    assert resp_reject.json()["status"] == "REJECTED"

    # Verify medication dosage remained 20 mg, NOT 50 mg
    assert db.get("medications", "med_sample_1")["dosage"] == "20 mg"
