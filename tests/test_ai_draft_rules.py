"""Tests verifying the strict rule: AI only suggests, humans must confirm."""

from starlette.testclient import TestClient

from app.core.database import db
from app.models.ai_draft import DraftStatus


def test_ai_draft_requires_human_confirmation(client: TestClient, caretaker_token: str):
    """Verify that parsing creates unconfirmed drafts without mutating active records."""
    headers = {"Authorization": f"Bearer {caretaker_token}"}

    # Record initial counts
    meds_before = len(db.list("medications", filters=[("elder_id", "==", "elder_1")]))
    appts_before = len(db.list("appointments", filters=[("elder_id", "==", "elder_1")]))

    # Submit clinical note to AI parse endpoint
    raw_text = (
        "Patient: Rose Dawson, Phone: 555-123-4567. "
        "Prescription: Atorvastatin 20mg once daily at bedtime. "
        "Schedule follow-up visit with Dr. Miller at Cardiology Suite on Dec 12."
    )
    resp = client.post("/api/ai/parse-draft", json={"raw_text": raw_text}, headers=headers)
    assert resp.status_code == 200
    drafts = resp.json()
    assert len(drafts) >= 1

    # STRICT RULE CHECK 1: Every draft MUST be in PENDING_CONFIRMATION status
    for draft in drafts:
        assert draft["status"] == DraftStatus.PENDING_CONFIRMATION.value

    # STRICT RULE CHECK 2: No active records should have been created yet
    meds_after = len(db.list("medications", filters=[("elder_id", "==", "elder_1")]))
    appts_after = len(db.list("appointments", filters=[("elder_id", "==", "elder_1")]))
    assert meds_after == meds_before
    assert appts_after == appts_before

    # Now test Human Rejection of first draft
    draft_1 = drafts[0]
    resp_reject = client.post(
        f"/api/ai/drafts/{draft_1['id']}/confirm",
        json={"approved": False},
        headers=headers,
    )
    assert resp_reject.status_code == 200
    assert resp_reject.json()["decision"] == "rejected"
    assert resp_reject.json()["created_record"] is None

    # Verify rejected draft did not create active entity
    meds_after_reject = len(db.list("medications", filters=[("elder_id", "==", "elder_1")]))
    assert meds_after_reject == meds_before

    # Now test Human Approval of second draft if exists, or re-parse
    if len(drafts) > 1:
        draft_2 = drafts[1]
        resp_confirm = client.post(
            f"/api/ai/drafts/{draft_2['id']}/confirm",
            json={"approved": True, "modifications": {"instructions": "Verified by Dr. Sarah"}},
            headers=headers,
        )
        assert resp_confirm.status_code == 200
        assert resp_confirm.json()["decision"] == "approved"
        assert resp_confirm.json()["created_record"] is not None
