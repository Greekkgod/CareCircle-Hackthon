"""Escalation orchestration service for CareCircle.

Coordinates the pure escalation engine, database persistence, idempotency sent-logs,
email interface dispatch with retries, and quiet-hours digest batching.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, List, Optional
import uuid

from app.core.config import settings
from app.core.database import db
from app.models.audit import AuditEntry
from app.models.notification import (
    AlertPriority,
    DigestQueueItem,
    EscalationConfig,
    NotificationLog,
    NotificationStatus,
    PendingNotification,
    QuietHoursConfig,
    SimulationTimeResponse,
)
from app.services.email_service import EmailSender, get_email_sender
from app.services.escalation_engine import (
    build_digest_summary_email,
    evaluate_escalation_cycle,
    parse_iso_datetime,
)

logger = logging.getLogger(__name__)

# Track simulated clock offset for testing and interactive demo
_simulated_clock: Optional[datetime] = None


def get_current_escalation_time() -> datetime:
    """Retrieve current evaluation time, respecting simulated demo clock if set."""
    global _simulated_clock
    if _simulated_clock is not None:
        return _simulated_clock
    return datetime.now(timezone.utc)


def set_simulated_clock(dt: Optional[datetime]) -> None:
    """Set or reset the simulated demo clock."""
    global _simulated_clock
    if dt is not None and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    _simulated_clock = dt


def log_escalation_audit(
    elder_id: str,
    action: str,
    details: Dict[str, Any],
) -> None:
    """Record an immutable audit entry for notification and escalation events."""
    audit_id = str(uuid.uuid4())
    entry = AuditEntry(
        id=audit_id,
        elder_id=elder_id,
        actor_id="system_escalation_engine",
        actor_role="system",
        action=action,
        details=details,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    db.set("audit_entries", audit_id, entry.model_dump())


def dispatch_with_retries(
    sender: EmailSender,
    to: str,
    subject: str,
    body: str,
    max_retries: int = 3,
) -> tuple[bool, int, Optional[str]]:
    """Attempt email transmission with automatic retries on transient errors."""
    attempts = 0
    last_error: Optional[str] = None

    while attempts < max_retries:
        attempts += 1
        try:
            success = sender.send(to=to, subject=subject, body=body)
            if success:
                return True, attempts, None
            last_error = f"Sender returned failure on attempt {attempts}"
        except Exception as exc:
            last_error = f"Exception on attempt {attempts}: {str(exc)}"

    return False, attempts, last_error


def run_escalation_for_elder(
    elder_id: str,
    current_time: Optional[datetime] = None,
    dry_run: bool = False,
    sender: Optional[EmailSender] = None,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Execute escalation cycle for a single elder.

    Args:
        elder_id: Target elder ID.
        current_time: Datetime to evaluate at. Defaults to active clock.
        dry_run: If True, do not deliver emails or persist sent-logs.
        sender: Email sender provider.
        max_retries: Number of retries on email failure.

    Returns:
        Summary dictionary of actions taken.
    """
    eval_time = current_time or get_current_escalation_time()
    if eval_time.tzinfo is None:
        eval_time = eval_time.replace(tzinfo=timezone.utc)

    elder_record = db.get("elder_profiles", elder_id) or {
        "id": elder_id,
        "name": "Rose Dawson",
        "email": "rose@carecircle.demo",
    }

    medications = db.list(
        "medications",
        filters=[("elder_id", "==", elder_id), ("is_active", "==", True)],
    )
    dose_logs = db.list("dose_logs", filters=[("elder_id", "==", elder_id)])
    members = db.list("users", filters=[("elder_id", "==", elder_id)])
    sent_logs = db.list("notification_logs", filters=[("elder_id", "==", elder_id)])

    # Gather idempotency keys that are already completed or batched
    sent_idempotency_keys = {
        log["idempotency_key"]
        for log in sent_logs
        if log.get("status") in (NotificationStatus.SENT.value, NotificationStatus.BATCHED.value, "SENT", "BATCHED")
    }

    # Build config from elder preferences and application defaults
    quiet_start = elder_record.get("quiet_hours_start", settings.quiet_hours_start)
    quiet_end = elder_record.get("quiet_hours_end", settings.quiet_hours_end)
    config = EscalationConfig(
        elder_grace_minutes=settings.escalation_elder_grace_minutes,
        caretaker_delay_minutes=settings.escalation_caretaker_delay_minutes,
        family_delay_minutes=settings.escalation_family_delay_minutes,
        quiet_hours=QuietHoursConfig(start_hour=quiet_start, end_hour=quiet_end),
    )

    immediate_actions, batched_items, stats = evaluate_escalation_cycle(
        current_time=eval_time,
        elder=elder_record,
        medications=medications,
        dose_logs=dose_logs,
        members=members,
        sent_idempotency_keys=sent_idempotency_keys,
        config=config,
    )

    sent_records: List[Dict[str, Any]] = []
    batched_records: List[Dict[str, Any]] = []
    failed_records: List[Dict[str, Any]] = []
    email_sender = sender or get_email_sender()

    # 1. Process Immediate Notifications
    for action in immediate_actions:
        # Strict idempotency check against persistent store
        existing = db.list(
            "notification_logs",
            filters=[("idempotency_key", "==", action.idempotency_key)],
        )
        if any(e.get("status") == NotificationStatus.SENT.value for e in existing):
            continue

        if dry_run:
            sent_records.append({
                "idempotency_key": action.idempotency_key,
                "recipient": action.recipient_email,
                "role": action.recipient_role,
                "subject": action.subject,
                "status": "DRY_RUN_PREVIEW",
            })
            continue

        # Dispatch with retries
        success, attempts, last_err = dispatch_with_retries(
            sender=email_sender,
            to=action.recipient_email,
            subject=action.subject,
            body=action.body,
            max_retries=max_retries,
        )

        status_val = NotificationStatus.SENT if success else NotificationStatus.FAILED
        log_id = str(uuid.uuid4())
        notif_log = NotificationLog(
            id=log_id,
            elder_id=elder_id,
            recipient_role=action.recipient_role,
            recipient_email=action.recipient_email,
            escalation_level=action.escalation_level,
            idempotency_key=action.idempotency_key,
            subject=action.subject,
            body=action.body,
            priority=action.priority,
            status=status_val,
            attempt_count=attempts,
            error_message=last_err,
        )
        db.set("notification_logs", log_id, notif_log.model_dump())

        if success:
            sent_records.append(notif_log.model_dump())
            log_escalation_audit(
                elder_id=elder_id,
                action=f"ESCALATION_{action.escalation_level.value.upper()}_SENT",
                details={
                    "recipient": action.recipient_email,
                    "subject": action.subject,
                    "attempts": attempts,
                },
            )
        else:
            failed_records.append(notif_log.model_dump())
            log_escalation_audit(
                elder_id=elder_id,
                action=f"ESCALATION_{action.escalation_level.value.upper()}_FAILED",
                details={
                    "recipient": action.recipient_email,
                    "error": last_err,
                    "attempts": attempts,
                },
            )

    # 2. Process Batched Digests (during Quiet Hours)
    for item in batched_items:
        if dry_run:
            batched_records.append(item.model_dump())
            continue

        existing_queue = db.list("digest_queue", filters=[("id", "==", item.id)])
        if not existing_queue:
            db.set("digest_queue", item.id, item.model_dump())

            # Also log as BATCHED in sent-log for idempotency tracking
            log_id = str(uuid.uuid4())
            notif_log = NotificationLog(
                id=log_id,
                elder_id=elder_id,
                recipient_role=item.recipient_role,
                recipient_email=item.recipient_email,
                escalation_level=item.recipient_role,  # type: ignore
                idempotency_key=item.id,
                subject=f"Batched for Digest: {item.medication_name}",
                body=item.reason,
                priority=AlertPriority.LOW,
                status=NotificationStatus.BATCHED,
                attempt_count=1,
            )
            db.set("notification_logs", log_id, notif_log.model_dump())
            batched_records.append(item.model_dump())

    return {
        "elder_id": elder_id,
        "evaluated_at": eval_time.isoformat(),
        "is_quiet_hours": stats["is_quiet_hours"],
        "sent_count": len(sent_records),
        "batched_count": len(batched_records),
        "failed_count": len(failed_records),
        "skipped_count": stats["skipped_count"],
        "sent": sent_records,
        "batched": batched_records,
        "failed": failed_records,
    }


def run_reminders_all_elders(
    current_time: Optional[datetime] = None,
    dry_run: bool = False,
    sender: Optional[EmailSender] = None,
) -> Dict[str, Any]:
    """Execute reminder and escalation cycles across all registered elders."""
    eval_time = current_time or get_current_escalation_time()
    elder_profiles = db.list("elder_profiles")
    if not elder_profiles:
        # Fallback to default elder if empty
        elder_profiles = [{"id": "elder_1", "name": "Rose Dawson"}]

    total_sent = 0
    total_batched = 0
    total_failed = 0
    details = []

    for profile in elder_profiles:
        elder_id = profile.get("id", "elder_1")
        summary = run_escalation_for_elder(
            elder_id=elder_id,
            current_time=eval_time,
            dry_run=dry_run,
            sender=sender,
        )
        total_sent += summary["sent_count"]
        total_batched += summary["batched_count"]
        total_failed += summary["failed_count"]
        details.append(summary)

    return {
        "status": "success",
        "timestamp": eval_time.isoformat(),
        "processed_elders": len(elder_profiles),
        "total_sent": total_sent,
        "total_batched": total_batched,
        "total_failed": total_failed,
        "details": details,
    }


def flush_digest_queue(
    elder_id: str,
    sender: Optional[EmailSender] = None,
) -> List[Dict[str, Any]]:
    """Deliver queued digest notifications when quiet hours end."""
    queued_items = db.list("digest_queue", filters=[("elder_id", "==", elder_id)])
    if not queued_items:
        return []

    elder_record = db.get("elder_profiles", elder_id) or {"name": "Elder"}
    elder_name = elder_record.get("name", "Elder")
    email_sender = sender or get_email_sender()

    # Group by recipient email
    by_recipient: Dict[str, List[DigestQueueItem]] = {}
    for raw in queued_items:
        item = DigestQueueItem(**raw)
        by_recipient.setdefault(item.recipient_email, []).append(item)

    flushed_results = []
    for recipient, items in by_recipient.items():
        subject, body = build_digest_summary_email(
            elder_name=elder_name,
            recipient_role=items[0].recipient_role,
            items=items,
        )
        success, attempts, err = dispatch_with_retries(
            sender=email_sender,
            to=recipient,
            subject=subject,
            body=body,
        )

        if success:
            for item in items:
                db.delete("digest_queue", item.id)
            flushed_results.append({
                "recipient": recipient,
                "items_count": len(items),
                "subject": subject,
                "status": "DELIVERED",
            })
            log_escalation_audit(
                elder_id=elder_id,
                action="DIGEST_DELIVERED",
                details={"recipient": recipient, "count": len(items)},
            )
        else:
            flushed_results.append({
                "recipient": recipient,
                "items_count": len(items),
                "error": err,
                "status": "FAILED",
            })

    return flushed_results


def simulate_time_advance(
    simulated_now: Optional[str] = None,
    advance_minutes: int = 0,
    elder_id: str = "elder_1",
    dry_run: bool = False,
) -> SimulationTimeResponse:
    """Advance or set the simulation clock and execute an escalation evaluation cycle."""
    if simulated_now:
        parsed = parse_iso_datetime(simulated_now)
        if parsed:
            target_time = parsed
        else:
            target_time = datetime.now(timezone.utc)
    else:
        current = get_current_escalation_time()
        target_time = current + timedelta(minutes=advance_minutes)

    # Update active simulated clock
    set_simulated_clock(target_time)

    # Run cycle
    summary = run_escalation_for_elder(
        elder_id=elder_id,
        current_time=target_time,
        dry_run=dry_run,
    )

    summary_text = (
        f"Simulated time set to {target_time.strftime('%Y-%m-%d %H:%M:%S UTC')}. "
        f"Evaluated {elder_id}: {summary['sent_count']} sent, "
        f"{summary['batched_count']} batched, {summary['skipped_count']} skipped."
    )

    return SimulationTimeResponse(
        simulated_time=target_time.isoformat(),
        elder_id=elder_id,
        is_quiet_hours=summary["is_quiet_hours"],
        notifications_sent=summary["sent"],
        notifications_batched=summary["batched"],
        notifications_skipped=[],
        summary=summary_text,
    )
