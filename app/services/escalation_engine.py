"""Pure, functional escalation ladder engine for CareCircle.

Decoupled from database, network, and clock I/O to guarantee 100% deterministic testability.
Computes:
1. Elder reminder at scheduled dose time.
2. Caretaker alert after N minutes if still untaken.
3. Family alert after M minutes if still untaken.
4. Halts escalation on TAKEN / SKIPPED doses.
5. Pauses escalation during active SNOOZE periods.
6. Enforces quiet hours and routes low-priority alerts to digest queues.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.medication import DoseStatus
from app.models.member import MemberRole
from app.models.notification import (
    AlertPriority,
    DigestQueueItem,
    EscalationConfig,
    EscalationLevel,
    PendingNotification,
)


def parse_iso_datetime(dt_str: str) -> Optional[datetime]:
    """Safely parse an ISO datetime string into an aware UTC datetime."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def get_scheduled_datetime_today(current_time: datetime, time_slot: str) -> Optional[datetime]:
    """Combine current date with a time slot string like '08:00' or '20:30'."""
    try:
        parts = time_slot.strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        return current_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    except Exception:
        return None


def find_active_member(members: List[Dict[str, Any]], role: MemberRole) -> Optional[Dict[str, Any]]:
    """Locate the first member matching the specified role."""
    target_role = role.value if isinstance(role, MemberRole) else str(role)
    for m in members:
        if m.get("role") == target_role:
            return m
    return None


def is_dose_resolved_or_snoozed(
    medication_id: str,
    scheduled_slot: str,
    dose_logs: List[Dict[str, Any]],
    current_time: datetime,
) -> Tuple[bool, bool, Optional[str]]:
    """Determine if a scheduled dose is already taken, skipped, or currently snoozed.

    Returns:
        Tuple[is_resolved, is_snoozed, reason]
    """
    for log in dose_logs:
        if log.get("medication_id") != medication_id:
            continue
        log_slot = log.get("scheduled_time", "")
        # Match time slot directly
        if scheduled_slot in log_slot or log_slot == scheduled_slot:
            status = log.get("status")
            if status in (DoseStatus.TAKEN.value, DoseStatus.SKIPPED.value, "TAKEN", "SKIPPED"):
                return True, False, f"Dose marked as {status}"
            if status in (DoseStatus.SNOOZED.value, "SNOOZED"):
                snooze_until_str = log.get("snooze_until")
                if snooze_until_str:
                    snooze_dt = parse_iso_datetime(snooze_until_str)
                    if snooze_dt and current_time < snooze_dt:
                        return True, True, f"Dose snoozed until {snooze_until_str}"
    return False, False, None


def evaluate_escalation_cycle(
    current_time: datetime,
    elder: Dict[str, Any],
    medications: List[Dict[str, Any]],
    dose_logs: List[Dict[str, Any]],
    members: List[Dict[str, Any]],
    sent_idempotency_keys: Set[str],
    config: Optional[EscalationConfig] = None,
    additional_alerts: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[List[PendingNotification], List[DigestQueueItem], Dict[str, Any]]:
    """Pure evaluation function that computes all required notification and digest actions.

    Args:
        current_time: Evaluated current wall clock time (aware UTC).
        elder: Elder profile dictionary.
        medications: Active medications for the elder.
        dose_logs: Dose logs recorded for the elder today.
        members: Circle members (elder, caretaker, family).
        sent_idempotency_keys: Set of keys already sent or processed.
        config: Escalation timing and quiet hours rules.
        additional_alerts: Optional custom low/high priority alerts.

    Returns:
        Tuple of:
            - Immediate PendingNotification list.
            - Batched DigestQueueItem list.
            - Metrics and summary dictionary.
    """
    if config is None:
        config = EscalationConfig()

    # Ensure current_time is aware UTC
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    else:
        current_time = current_time.astimezone(timezone.utc)

    elder_id = elder.get("id", "elder_1")
    elder_name = elder.get("name", "Elder")
    date_str = current_time.strftime("%Y-%m-%d")

    # Resolve member contacts
    elder_member = find_active_member(members, MemberRole.ELDER) or {
        "name": elder_name,
        "email": elder.get("email") or f"{elder_name.lower().replace(' ', '')}@example.com",
        "role": MemberRole.ELDER.value,
    }
    caretaker_member = find_active_member(members, MemberRole.CARETAKER) or {
        "name": "Primary Caretaker",
        "email": "caretaker@example.com",
        "role": MemberRole.CARETAKER.value,
    }
    family_member = find_active_member(members, MemberRole.FAMILY) or {
        "name": "Family Contact",
        "email": "family@example.com",
        "role": MemberRole.FAMILY.value,
    }

    in_quiet_hours = config.quiet_hours.is_quiet_hour(current_time)

    immediate_notifications: List[PendingNotification] = []
    batched_digests: List[DigestQueueItem] = []
    skipped_count = 0

    # 1. Process Medication Escalation Ladder
    for med in medications:
        if not med.get("is_active", True):
            continue

        med_id = med.get("id", "med")
        med_name = med.get("name", "Medication")
        dosage = med.get("dosage", "")
        instructions = med.get("instructions", "Take as prescribed")
        schedule_times = med.get("schedule_times", ["08:00"])

        for slot in schedule_times:
            scheduled_dt = get_scheduled_datetime_today(current_time, slot)
            if not scheduled_dt:
                continue

            # Only evaluate doses whose scheduled time has arrived or passed
            if current_time < scheduled_dt:
                continue

            elapsed_minutes = (current_time - scheduled_dt).total_seconds() / 60.0

            # Check if resolved (taken/skipped) or snoozed
            is_resolved, is_snoozed, _ = is_dose_resolved_or_snoozed(
                med_id, slot, dose_logs, current_time
            )
            if is_resolved:
                skipped_count += 1
                continue

            # --- Escalation Level 1: Elder Reminder ---
            elder_key = f"escalation:{elder_id}:{med_id}:{date_str}:{slot}:elder"
            if elapsed_minutes >= config.elder_grace_minutes and elder_key not in sent_idempotency_keys:
                subject = f"Friendly Reminder: Time for your {med_name} ({dosage})"
                body = (
                    f"Hello {elder_name},\n\n"
                    f"It is time to take your {med_name} ({dosage}) scheduled for {slot}.\n"
                    f"Instructions: {instructions}.\n\n"
                    f"Please confirm in your CareCircle dashboard once taken."
                )

                if in_quiet_hours:
                    # During quiet hours, routine elder reminder is deferred into morning digest
                    batched_digests.append(
                        DigestQueueItem(
                            id=elder_key,
                            elder_id=elder_id,
                            recipient_role=MemberRole.ELDER.value,
                            recipient_email=elder_member.get("email", ""),
                            medication_name=med_name,
                            scheduled_time=slot,
                            reason=f"Quiet hours scheduled reminder for {med_name}",
                        )
                    )
                else:
                    immediate_notifications.append(
                        PendingNotification(
                            idempotency_key=elder_key,
                            elder_id=elder_id,
                            medication_id=med_id,
                            medication_name=med_name,
                            scheduled_time=slot,
                            escalation_level=EscalationLevel.ELDER,
                            recipient_role=MemberRole.ELDER.value,
                            recipient_name=elder_member.get("name", elder_name),
                            recipient_email=elder_member.get("email", ""),
                            subject=subject,
                            body=body,
                            priority=AlertPriority.LOW,
                        )
                    )

            # --- Escalation Level 2: Caretaker Alert ---
            caretaker_key = f"escalation:{elder_id}:{med_id}:{date_str}:{slot}:caretaker"
            if (
                elapsed_minutes >= config.caretaker_delay_minutes
                and caretaker_key not in sent_idempotency_keys
            ):
                subject = f"Alert: {elder_name} has not confirmed {med_name} ({int(elapsed_minutes)}m overdue)"
                body = (
                    f"Caregiver Alert:\n\n"
                    f"{elder_name} was scheduled to take {med_name} ({dosage}) at {slot} today.\n"
                    f"It is now {int(elapsed_minutes)} minutes past due and no confirmation has been recorded.\n\n"
                    f"Please check in with {elder_name} or update their CareCircle log."
                )
                immediate_notifications.append(
                    PendingNotification(
                        idempotency_key=caretaker_key,
                        elder_id=elder_id,
                        medication_id=med_id,
                        medication_name=med_name,
                        scheduled_time=slot,
                        escalation_level=EscalationLevel.CARETAKER,
                        recipient_role=MemberRole.CARETAKER.value,
                        recipient_name=caretaker_member.get("name", "Caretaker"),
                        recipient_email=caretaker_member.get("email", ""),
                        subject=subject,
                        body=body,
                        priority=AlertPriority.HIGH,
                    )
                )

            # --- Escalation Level 3: Family Escalation ---
            family_key = f"escalation:{elder_id}:{med_id}:{date_str}:{slot}:family"
            if (
                elapsed_minutes >= config.family_delay_minutes
                and family_key not in sent_idempotency_keys
            ):
                subject = f"CareCircle Notice: Overdue medication for {elder_name}"
                body = (
                    f"Hello {family_member.get('name', 'Family')},\n\n"
                    f"{elder_name}'s scheduled dose of {med_name} ({dosage}) at {slot} is "
                    f"{int(elapsed_minutes)} minutes overdue.\n"
                    f"The care team has been notified. This notice is sent to keep the family informed."
                )
                immediate_notifications.append(
                    PendingNotification(
                        idempotency_key=family_key,
                        elder_id=elder_id,
                        medication_id=med_id,
                        medication_name=med_name,
                        scheduled_time=slot,
                        escalation_level=EscalationLevel.FAMILY,
                        recipient_role=MemberRole.FAMILY.value,
                        recipient_name=family_member.get("name", "Family"),
                        recipient_email=family_member.get("email", ""),
                        subject=subject,
                        body=body,
                        priority=AlertPriority.HIGH,
                    )
                )

    # 2. Process Additional Low-Priority Alerts (Refills / Check-ins)
    if additional_alerts:
        for alert in additional_alerts:
            alert_key = alert.get("idempotency_key", "")
            if alert_key in sent_idempotency_keys:
                skipped_count += 1
                continue

            priority = alert.get("priority", AlertPriority.LOW)
            if priority == AlertPriority.LOW and in_quiet_hours:
                batched_digests.append(
                    DigestQueueItem(
                        id=alert_key,
                        elder_id=elder_id,
                        recipient_role=alert.get("recipient_role", MemberRole.FAMILY.value),
                        recipient_email=alert.get("recipient_email", family_member.get("email", "")),
                        medication_name=alert.get("medication_name", "General Update"),
                        scheduled_time=alert.get("scheduled_time", "N/A"),
                        reason=alert.get("reason", "Low-priority alert queued during quiet hours"),
                    )
                )
            else:
                immediate_notifications.append(
                    PendingNotification(
                        idempotency_key=alert_key,
                        elder_id=elder_id,
                        medication_id=alert.get("medication_id"),
                        medication_name=alert.get("medication_name"),
                        scheduled_time=alert.get("scheduled_time", ""),
                        escalation_level=EscalationLevel(alert.get("escalation_level", "elder")),
                        recipient_role=alert.get("recipient_role", MemberRole.ELDER.value),
                        recipient_name=alert.get("recipient_name", elder_name),
                        recipient_email=alert.get("recipient_email", elder_member.get("email", "")),
                        subject=alert.get("subject", "CareCircle Notification"),
                        body=alert.get("body", ""),
                        priority=priority,
                    )
                )

    stats = {
        "evaluated_at": current_time.isoformat(),
        "is_quiet_hours": in_quiet_hours,
        "immediate_count": len(immediate_notifications),
        "batched_count": len(batched_digests),
        "skipped_count": skipped_count,
    }

    return immediate_notifications, batched_digests, stats


def build_digest_summary_email(
    elder_name: str,
    recipient_role: str,
    items: List[DigestQueueItem],
) -> Tuple[str, str]:
    """Assemble a consolidated digest email for batched low-priority alerts."""
    subject = f"CareCircle Summary Digest for {elder_name} ({len(items)} updates)"
    item_lines = [
        f"• {item.medication_name} ({item.scheduled_time}): {item.reason}"
        for item in items
    ]
    body = (
        f"Hello,\n\n"
        f"Here is your compiled CareCircle digest for {elder_name}.\n"
        f"The following {len(items)} low-priority updates were gathered during quiet hours:\n\n"
        + "\n".join(item_lines)
        + f"\n\nLog in to your CareCircle dashboard for full adherence logs."
    )
    return subject, body
