"""Tests for the pure escalation ladder, quiet hours, email interface, retries, and scheduler.

Covers:
- Pure escalation ladder progression: Elder (0m) -> Caretaker (15m) -> Family (30m).
- Halting ladder when dose is TAKEN or SKIPPED.
- Pausing ladder when dose is SNOOZED.
- Quiet hours logic (midnight wrapping) and low-priority digest batching.
- Email interface, mock fault injection, and retry handling.
- Idempotent execution preventing duplicate notification dispatches.
- Cloud Scheduler protected /internal/run-reminders endpoint security.
- Interactive simulate-time endpoint.
"""

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import db
from app.main import app
from app.models.medication import DoseStatus
from app.models.member import MemberRole
from app.models.notification import (
    AlertPriority,
    DigestQueueItem,
    EscalationConfig,
    EscalationLevel,
    QuietHoursConfig,
)
from app.services.email_service import MockEmailSender, set_email_sender
from app.services.escalation_engine import (
    build_digest_summary_email,
    evaluate_escalation_cycle,
    is_dose_resolved_or_snoozed,
)
from app.services.escalation_service import (
    dispatch_with_retries,
    flush_digest_queue,
    run_escalation_for_elder,
    set_simulated_clock,
    simulate_time_advance,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_test_state():
    """Reset repository collections, simulated clock, and mock email sender before each test."""
    db.reset_mock()
    set_simulated_clock(None)
    mock_sender = MockEmailSender()
    set_email_sender(mock_sender)
    yield
    db.reset_mock()
    set_simulated_clock(None)


# -------------------------------------------------------------------------
# 1. Pure Escalation Engine Unit Tests
# -------------------------------------------------------------------------

def test_pure_escalation_ladder_step_by_step():
    """Test the complete 3-tier escalation ladder: Elder -> Caretaker -> Family."""
    elder = {"id": "elder_1", "name": "Rose Dawson", "email": "rose@carecircle.demo"}
    medications = [
        {
            "id": "med_1",
            "name": "Metformin",
            "dosage": "500mg",
            "instructions": "With breakfast",
            "schedule_times": ["08:00"],
            "is_active": True,
        }
    ]
    members = [
        {"role": MemberRole.ELDER.value, "name": "Rose Dawson", "email": "rose@carecircle.demo"},
        {"role": MemberRole.CARETAKER.value, "name": "Nurse Sarah", "email": "sarah@carecircle.demo"},
        {"role": MemberRole.FAMILY.value, "name": "David Dawson", "email": "david@carecircle.demo"},
    ]
    dose_logs = []
    sent_keys = set()
    config = EscalationConfig(
        elder_grace_minutes=0,
        caretaker_delay_minutes=15,
        family_delay_minutes=30,
        quiet_hours=QuietHoursConfig(enabled=False),
    )

    # Step 1: At 08:00 (Due Time) -> Elder reminder only
    time_0800 = datetime(2026, 11, 15, 8, 0, 0, tzinfo=timezone.utc)
    immediates, batched, stats = evaluate_escalation_cycle(
        current_time=time_0800,
        elder=elder,
        medications=medications,
        dose_logs=dose_logs,
        members=members,
        sent_idempotency_keys=sent_keys,
        config=config,
    )
    assert len(immediates) == 1
    assert immediates[0].escalation_level == EscalationLevel.ELDER
    assert immediates[0].recipient_email == "rose@carecircle.demo"
    assert "Friendly Reminder" in immediates[0].subject
    sent_keys.add(immediates[0].idempotency_key)

    # Step 2: At 08:10 (10 mins elapsed) -> No new escalation yet (before 15m)
    time_0810 = datetime(2026, 11, 15, 8, 10, 0, tzinfo=timezone.utc)
    immediates_10, _, _ = evaluate_escalation_cycle(
        current_time=time_0810,
        elder=elder,
        medications=medications,
        dose_logs=dose_logs,
        members=members,
        sent_idempotency_keys=sent_keys,
        config=config,
    )
    assert len(immediates_10) == 0

    # Step 3: At 08:15 (15 mins elapsed) -> Caretaker alert
    time_0815 = datetime(2026, 11, 15, 8, 15, 0, tzinfo=timezone.utc)
    immediates_15, _, _ = evaluate_escalation_cycle(
        current_time=time_0815,
        elder=elder,
        medications=medications,
        dose_logs=dose_logs,
        members=members,
        sent_idempotency_keys=sent_keys,
        config=config,
    )
    assert len(immediates_15) == 1
    assert immediates_15[0].escalation_level == EscalationLevel.CARETAKER
    assert immediates_15[0].recipient_email == "sarah@carecircle.demo"
    assert "15m overdue" in immediates_15[0].subject
    sent_keys.add(immediates_15[0].idempotency_key)

    # Step 4: At 08:30 (30 mins elapsed) -> Family escalation
    time_0830 = datetime(2026, 11, 15, 8, 30, 0, tzinfo=timezone.utc)
    immediates_30, _, _ = evaluate_escalation_cycle(
        current_time=time_0830,
        elder=elder,
        medications=medications,
        dose_logs=dose_logs,
        members=members,
        sent_idempotency_keys=sent_keys,
        config=config,
    )
    assert len(immediates_30) == 1
    assert immediates_30[0].escalation_level == EscalationLevel.FAMILY
    assert immediates_30[0].recipient_email == "david@carecircle.demo"
    assert "Overdue medication" in immediates_30[0].subject


def test_escalation_halts_when_dose_is_taken():
    """Verify that logging a dose as TAKEN halts all further escalation tiers."""
    elder = {"id": "elder_1", "name": "Rose Dawson"}
    medications = [{"id": "med_1", "name": "Lisinopril", "schedule_times": ["08:00"], "is_active": True}]
    members = [
        {"role": "elder", "name": "Rose", "email": "rose@example.com"},
        {"role": "caretaker", "name": "Sarah", "email": "sarah@example.com"},
    ]
    # Elder took dose at 08:05
    dose_logs = [
        {"medication_id": "med_1", "scheduled_time": "08:00", "status": DoseStatus.TAKEN.value}
    ]
    sent_keys = {"escalation:elder_1:med_1:2026-11-15:08:00:elder"}

    # Evaluate at 08:20 (when Caretaker would normally be alerted)
    time_0820 = datetime(2026, 11, 15, 8, 20, 0, tzinfo=timezone.utc)
    immediates, _, stats = evaluate_escalation_cycle(
        current_time=time_0820,
        elder=elder,
        medications=medications,
        dose_logs=dose_logs,
        members=members,
        sent_idempotency_keys=sent_keys,
    )
    assert len(immediates) == 0
    assert stats["skipped_count"] >= 1


def test_escalation_pauses_when_dose_is_snoozed():
    """Verify that snoozing a dose suppresses escalation alerts until snooze time passes."""
    elder = {"id": "elder_1", "name": "Rose"}
    medications = [{"id": "med_1", "name": "Aspirin", "schedule_times": ["08:00"], "is_active": True}]
    members = [
        {"role": "elder", "name": "Rose", "email": "rose@example.com"},
        {"role": "caretaker", "name": "Sarah", "email": "sarah@example.com"},
    ]
    # Snoozed until 08:45
    dose_logs = [
        {
            "medication_id": "med_1",
            "scheduled_time": "08:00",
            "status": DoseStatus.SNOOZED.value,
            "snooze_until": "2026-11-15T08:45:00Z",
        }
    ]
    sent_keys = set()

    # At 08:20, current_time (08:20) < snooze_until (08:45)
    time_0820 = datetime(2026, 11, 15, 8, 20, 0, tzinfo=timezone.utc)
    is_res, is_snz, reason = is_dose_resolved_or_snoozed("med_1", "08:00", dose_logs, time_0820)
    assert is_res is True
    assert is_snz is True

    immediates, _, _ = evaluate_escalation_cycle(
        current_time=time_0820,
        elder=elder,
        medications=medications,
        dose_logs=dose_logs,
        members=members,
        sent_idempotency_keys=sent_keys,
    )
    assert len(immediates) == 0


def test_quiet_hours_midnight_wrapping_and_logic():
    """Test quiet hours detection across midnight boundaries (e.g. 22:00 to 07:00)."""
    qh = QuietHoursConfig(enabled=True, start_hour=22, end_hour=7)

    # 11 PM (23:00) -> Quiet
    assert qh.is_quiet_hour(datetime(2026, 11, 15, 23, 0, 0)) is True
    # 2 AM (02:00) -> Quiet
    assert qh.is_quiet_hour(datetime(2026, 11, 16, 2, 0, 0)) is True
    # 7 AM (07:00) -> End of quiet hours (Daytime)
    assert qh.is_quiet_hour(datetime(2026, 11, 16, 7, 0, 0)) is False
    # 10 AM (10:00) -> Daytime
    assert qh.is_quiet_hour(datetime(2026, 11, 16, 10, 0, 0)) is False

    # Disabled
    qh_disabled = QuietHoursConfig(enabled=False, start_hour=22, end_hour=7)
    assert qh_disabled.is_quiet_hour(datetime(2026, 11, 15, 23, 0, 0)) is False


def test_quiet_hours_batches_low_priority_alerts_into_digest():
    """Verify that during quiet hours, low-priority reminders are batched into a digest."""
    elder = {"id": "elder_1", "name": "Rose Dawson", "email": "rose@carecircle.demo"}
    medications = [
        {"id": "med_night", "name": "Melatonin", "dosage": "3mg", "schedule_times": ["22:30"], "is_active": True}
    ]
    members = [
        {"role": "elder", "name": "Rose Dawson", "email": "rose@carecircle.demo"},
        {"role": "caretaker", "name": "Sarah", "email": "sarah@carecircle.demo"},
    ]
    config = EscalationConfig(
        elder_grace_minutes=0,
        quiet_hours=QuietHoursConfig(enabled=True, start_hour=22, end_hour=7),
    )

    # Evaluate at 22:30 (Quiet Hours)
    night_time = datetime(2026, 11, 15, 22, 30, 0, tzinfo=timezone.utc)
    immediates, batched, stats = evaluate_escalation_cycle(
        current_time=night_time,
        elder=elder,
        medications=medications,
        dose_logs=[],
        members=members,
        sent_idempotency_keys=set(),
        config=config,
    )
    assert stats["is_quiet_hours"] is True
    # Immediate notification to elder is suppressed
    assert len(immediates) == 0
    # Placed in batched digest instead
    assert len(batched) == 1
    assert batched[0].medication_name == "Melatonin"
    assert "Quiet hours" in batched[0].reason


def test_digest_summary_assembly_and_flush():
    """Test consolidating batched quiet hours items into a single digest email."""
    items = [
        DigestQueueItem(
            id="q1",
            elder_id="elder_1",
            recipient_role="elder",
            recipient_email="rose@carecircle.demo",
            medication_name="Vitamin D",
            scheduled_time="22:00",
            reason="Nighttime scheduled dose",
        ),
        DigestQueueItem(
            id="q2",
            elder_id="elder_1",
            recipient_role="elder",
            recipient_email="rose@carecircle.demo",
            medication_name="Eye Drops",
            scheduled_time="22:30",
            reason="Bedtime routine",
        ),
    ]
    subject, body = build_digest_summary_email("Rose Dawson", "elder", items)
    assert "Rose Dawson (2 updates)" in subject
    assert "Vitamin D" in body
    assert "Eye Drops" in body


# -------------------------------------------------------------------------
# 2. Email Interface, Fault Injection & Retries
# -------------------------------------------------------------------------

def test_mock_email_sender_and_retries():
    """Test MockEmailSender with transient failure simulation and retry recovery."""
    sender = MockEmailSender()
    # Configure 2 transient failures before succeeding
    sender.failures_remaining = 2

    success, attempts, err = dispatch_with_retries(
        sender=sender,
        to="test@example.com",
        subject="Test Alert",
        body="Body content",
        max_retries=3,
    )
    assert success is True
    assert attempts == 3
    assert err is None
    assert len(sender.get_messages()) == 1
    assert sender.get_messages()[0]["to"] == "test@example.com"


def test_mock_email_sender_permanent_failure():
    """Test retry exhaustion when provider permanently fails."""
    sender = MockEmailSender()
    sender.failure_mode = True

    success, attempts, err = dispatch_with_retries(
        sender=sender,
        to="fail@example.com",
        subject="Alert",
        body="Body",
        max_retries=3,
    )
    assert success is False
    assert attempts == 3
    assert "failure" in str(err)
    assert len(sender.get_messages()) == 0


# -------------------------------------------------------------------------
# 3. Idempotency & Sent-Log Integration
# -------------------------------------------------------------------------

def test_idempotent_escalation_execution():
    """Verify that multiple consecutive runs do not send duplicate emails."""
    mock_sender = MockEmailSender()
    set_email_sender(mock_sender)

    # Seed elder and medication
    db.set("elder_profiles", "elder_1", {"id": "elder_1", "name": "Rose Dawson", "email": "rose@carecircle.demo"})
    db.set("medications", "med_1", {
        "id": "med_1",
        "elder_id": "elder_1",
        "name": "Metformin",
        "dosage": "500mg",
        "schedule_times": ["08:00"],
        "is_active": True,
    })
    db.set("users", "elder_1", {
        "id": "elder_1",
        "elder_id": "elder_1",
        "name": "Rose Dawson",
        "role": "elder",
        "email": "rose@carecircle.demo",
    })

    eval_time = datetime(2026, 11, 15, 8, 0, 0, tzinfo=timezone.utc)

    # Run 1: Should send 1 notification
    run1 = run_escalation_for_elder("elder_1", current_time=eval_time, sender=mock_sender)
    assert run1["sent_count"] == 1
    assert len(mock_sender.get_messages()) == 1

    # Run 2: Exact same time and state -> Should send 0 (idempotent!)
    run2 = run_escalation_for_elder("elder_1", current_time=eval_time, sender=mock_sender)
    assert run2["sent_count"] == 0
    assert len(mock_sender.get_messages()) == 1  # Still 1, no duplicate


# -------------------------------------------------------------------------
# 4. Protected Cloud Scheduler Endpoint Tests
# -------------------------------------------------------------------------

def test_cloud_scheduler_endpoint_unauthorized():
    """Verify /internal/run-reminders rejects calls without valid scheduler token."""
    # Missing headers
    resp = client.post("/internal/run-reminders")
    assert resp.status_code == 401

    # Invalid token
    resp_bad = client.post(
        "/internal/run-reminders",
        headers={"X-CloudScheduler-Token": "wrong-secret-token"},
    )
    assert resp_bad.status_code == 401


def test_cloud_scheduler_endpoint_authorized():
    """Verify /internal/run-reminders succeeds with valid X-CloudScheduler-Token or Bearer token."""
    # Custom Header
    resp_hdr = client.post(
        "/internal/run-reminders?dry_run=true",
        headers={"X-CloudScheduler-Token": settings.cron_secret},
    )
    assert resp_hdr.status_code == 200
    data = resp_hdr.json()
    assert data["status"] == "success"
    assert "processed_elders" in data

    # Bearer Authorization Header
    resp_bearer = client.post(
        "/internal/run-reminders?dry_run=true",
        headers={"Authorization": f"Bearer {settings.cron_secret}"},
    )
    assert resp_bearer.status_code == 200


# -------------------------------------------------------------------------
# 5. Interactive Simulation Endpoint Tests
# -------------------------------------------------------------------------

def test_simulation_simulate_time_endpoint():
    """Test /api/simulation/simulate-time endpoint advances clock and evaluates ladder."""
    db.set("elder_profiles", "elder_1", {
        "id": "elder_1",
        "name": "Rose Dawson",
        "email": "rose@carecircle.demo",
        "quiet_hours_start": 22,
        "quiet_hours_end": 7,
    })
    db.set("medications", "med_1", {
        "id": "med_1",
        "elder_id": "elder_1",
        "name": "Coreg",
        "dosage": "12.5mg",
        "schedule_times": ["08:00"],
        "is_active": True,
    })

    # Simulate 08:00 (Due time)
    resp = client.post(
        "/api/simulation/simulate-time",
        json={"simulated_now": "2026-11-15T08:00:00Z", "elder_id": "elder_1"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["simulated_time"] == "2026-11-15T08:00:00+00:00"
    assert res_data["is_quiet_hours"] is False
    assert len(res_data["notifications_sent"]) == 1
    assert "elder" in res_data["notifications_sent"][0]["escalation_level"]

    # Reset clock
    reset_resp = client.post("/api/simulation/reset-clock")
    assert reset_resp.status_code == 200
