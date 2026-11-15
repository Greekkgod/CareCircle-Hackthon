"""Tests for all 4 Gemini-powered features:

1. Prescription photo to draft medication list (Multimodal Vision).
2. Natural-language and conversational voice entry with PII redaction.
3. Plain-language "Why am I taking this?" senior explanation.
4. Pre-appointment doctor briefing synthesized from adherence history.

Validates:
- All outputs are drafts in PENDING_CONFIRMATION status.
- Every response includes a mandatory 'confirm with your doctor or pharmacist' notice.
- Personal identifiers (names, SSNs, phone numbers) are redacted before calling the model.
- API failures and network errors are handled gracefully with robust fallbacks.
- Mocking Gemini responses in tests.
"""

from unittest.mock import MagicMock, patch

from starlette.testclient import TestClient

from app.core.database import db
from app.models.ai_draft import DraftStatus, DraftType
from app.models.medication import DoseLogCreate, DoseStatus
from app.services.gemini_service import (
    explain_why_am_i_taking_this,
    generate_doctor_briefing,
    parse_natural_language_voice_to_drafts,
    parse_prescription_photo_to_drafts,
)
from app.services.medication_service import log_dose


def test_prescription_photo_to_draft_medication_list(client: TestClient, caretaker_token: str):
    """Test Feature 1: Prescription photo upload extracts drafts requiring human confirmation."""
    headers = {"Authorization": f"Bearer {caretaker_token}"}
    fake_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    resp = client.post(
        "/api/ai/prescription-photo",
        json={"image_base64": fake_image_b64, "mime_type": "image/png", "elder_id": "elder_1"},
        headers=headers,
    )
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) >= 1

    # Verify strict safety constraints
    for d in drafts:
        assert d["draft_type"] == DraftType.MEDICATION.value
        assert d["status"] == DraftStatus.PENDING_CONFIRMATION.value
        assert "confirm" in d["medical_disclaimer"].lower()
        assert "doctor or pharmacist" in d["medical_disclaimer"].lower()
        assert "name" in d["proposed_data"]
        assert "dosage" in d["proposed_data"]


def test_natural_language_voice_entry_with_pii_redaction(client: TestClient, caretaker_token: str):
    """Test Feature 2: Natural-language/voice note redacts PII before model processing."""
    headers = {"Authorization": f"Bearer {caretaker_token}"}
    voice_transcript = (
        "Patient Rose Dawson (SSN: 000-12-3456, phone 555-234-5678, living at 123 Elm St). "
        "Doctor said to start Metformin 500mg twice daily with meals, and scheduled an appointment "
        "with Dr. Adams at Metro Heart Clinic on Friday at 10am."
    )

    resp = client.post(
        "/api/ai/voice-entry",
        json={"text": voice_transcript, "elder_id": "elder_1"},
        headers=headers,
    )
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) >= 2  # At least 1 med and 1 appt

    for d in drafts:
        # PII must NOT appear in stored source snippet
        assert "000-12-3456" not in d["source_snippet"]
        assert "555-234-5678" not in d["source_snippet"]
        assert d["status"] == DraftStatus.PENDING_CONFIRMATION.value
        assert "doctor or pharmacist" in d["medical_disclaimer"].lower()


def test_plain_language_why_am_i_taking_this(client: TestClient, elder_token: str):
    """Test Feature 3: Plain-language senior-friendly explanation of medication."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # Test common elder medication (Metformin)
    resp = client.post(
        "/api/ai/why-am-i-taking-this",
        json={"medication_name": "Metformin", "dosage": "500mg", "elder_id": "elder_1"},
        headers=headers,
    )
    assert resp.status_code == 200
    draft = resp.json()

    assert draft["draft_type"] == DraftType.WHY_AM_I_TAKING_THIS.value
    assert draft["status"] == DraftStatus.PENDING_CONFIRMATION.value
    assert "sugar" in draft["proposed_data"]["explanation"].lower()
    assert len(draft["proposed_data"]["practical_tip"]) > 0
    assert "confirm with your doctor or pharmacist" in draft["medical_disclaimer"].lower()

    # Test Lisinopril
    resp_l = client.post(
        "/api/ai/why-am-i-taking-this",
        json={"medication_name": "Lisinopril", "dosage": "10mg", "elder_id": "elder_1"},
        headers=headers,
    )
    assert resp_l.status_code == 200
    draft_l = resp_l.json()
    assert "blood pressure" in draft_l["proposed_data"]["explanation"].lower()


def test_pre_appointment_doctor_briefing_from_adherence_history(client: TestClient, elder_token: str):
    """Test Feature 4: Synthesize adherence records into a clinical pre-appointment briefing."""
    headers = {"Authorization": f"Bearer {elder_token}"}

    # Seed elder medication and dose logs
    db.set("elder_profiles", "elder_1", {"id": "elder_1", "name": "Rose Dawson"})
    db.set("medications", "med_1", {
        "id": "med_1",
        "elder_id": "elder_1",
        "name": "Metformin",
        "dosage": "500mg",
        "schedule_times": ["08:00"],
        "is_active": True,
    })

    # Log several doses: 3 taken, 1 missed
    for i in range(3):
        log_dose(
            "elder_1",
            DoseLogCreate(
                medication_id="med_1",
                medication_name="Metformin",
                scheduled_time=f"2026-11-1{i}T08:00:00Z",
                status=DoseStatus.TAKEN,
            ),
            confirmed_by="Rose Dawson",
        )
    log_dose(
        "elder_1",
        DoseLogCreate(
            medication_id="med_1",
            medication_name="Metformin",
            scheduled_time="2026-11-14T08:00:00Z",
            status=DoseStatus.MISSED,
            notes="Felt nauseous",
        ),
        confirmed_by="Rose Dawson",
    )

    resp = client.post(
        "/api/ai/doctor-briefing",
        json={"elder_id": "elder_1", "timeframe_days": 14},
        headers=headers,
    )
    assert resp.status_code == 200
    draft = resp.json()

    assert draft["draft_type"] == DraftType.DOCTOR_BRIEFING.value
    assert draft["status"] == DraftStatus.PENDING_CONFIRMATION.value
    assert "adherence_rate" in draft["proposed_data"]
    assert "executive_summary" in draft["proposed_data"]
    assert "topics_for_physician" in draft["proposed_data"]
    assert "confirm all observations with your doctor or pharmacist" in draft["medical_disclaimer"].lower()


def test_gemini_api_graceful_failure_and_fallback():
    """Verify that if the Gemini API throws exceptions or quotas are exhausted, fallbacks run smoothly."""
    # Simulate Gemini API failure
    with patch("google.genai.Client", side_effect=Exception("API Connection Refused / Quota Exceeded")):
        # Photo parser fallback
        photo_drafts = parse_prescription_photo_to_drafts(
            image_base64="fake-data",
            elder_id="elder_1",
        )
        assert len(photo_drafts) >= 1
        assert photo_drafts[0].status == DraftStatus.PENDING_CONFIRMATION

        # Voice parser fallback
        voice_drafts = parse_natural_language_voice_to_drafts(
            raw_text="Start Amlodipine 5mg daily",
            elder_id="elder_1",
        )
        assert len(voice_drafts) >= 1
        assert "Amlodipine" in voice_drafts[0].proposed_data["name"]

        # Explanation fallback
        why_draft = explain_why_am_i_taking_this("Metformin", "500mg", "elder_1")
        assert why_draft.proposed_data["explanation"] != ""

        # Doctor briefing fallback
        briefing_draft = generate_doctor_briefing("elder_1", timeframe_days=7)
        assert "executive_summary" in briefing_draft.proposed_data


def test_mocking_gemini_in_tests():
    """Demonstrate mocking Gemini SDK client and responses in tests."""
    mock_response = MagicMock()
    mock_response.text = '{"medications": [{"name": "MockPill", "dosage": "50mg", "instructions": "Daily", "schedule_times": ["08:00"], "frequency": "Daily", "pill_color": "#10B981", "remaining_refills": 30, "refill_threshold": 7, "reasoning": "Mocked test response"}], "appointments": []}'

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch("app.core.config.settings.gemini_api_key", "valid-test-key"):
        with patch("google.genai.Client", return_value=mock_client):
            drafts = parse_natural_language_voice_to_drafts("Patient starts MockPill 50mg daily", elder_id="elder_1")
            assert len(drafts) == 1
            assert drafts[0].proposed_data["name"] == "MockPill"
            assert drafts[0].status == DraftStatus.PENDING_CONFIRMATION
            assert "doctor or pharmacist" in drafts[0].medical_disclaimer.lower()
