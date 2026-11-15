"""Authentication service with bcrypt passcode verification and rate limiting."""

from datetime import datetime, timezone
from typing import Optional, Tuple
from fastapi import HTTPException, status
from app.core.database import db
from app.core.security import (
    create_access_token,
    hash_passcode,
    rate_limiter,
    verify_passcode,
)
from app.models.auth import PasscodeLogin, RateLimitStatus, TokenResponse, UserRole


def seed_default_users() -> None:
    """Seed initial demo accounts for elder, caretaker, and family if not present."""
    default_users = [
        {
            "id": "elder_1",
            "name": "Rose Dawson",
            "role": UserRole.ELDER.value,
            "elder_id": "elder_1",
            "phone": "+1-555-0199",
            "email": "rose@carecircle.demo",
            "passcode_plain": "1234",
        },
        {
            "id": "caretaker_1",
            "name": "Sarah Jenkins, RN",
            "role": UserRole.CARETAKER.value,
            "elder_id": "elder_1",
            "phone": "+1-555-0144",
            "email": "sarah.rn@carecircle.demo",
            "passcode_plain": "care2026",
        },
        {
            "id": "family_1",
            "name": "David Dawson",
            "role": UserRole.FAMILY.value,
            "elder_id": "elder_1",
            "phone": "+1-555-0188",
            "email": "david.family@carecircle.demo",
            "passcode_plain": "fam1234",
        },
    ]

    # Seed primary elder profile tied to all 3 demo accounts
    if not db.get("elder_profiles", "elder_1"):
        db.set("elder_profiles", "elder_1", {
            "id": "elder_1",
            "name": "Rose Dawson",
            "date_of_birth": "1944-04-12",
            "emergency_contact": "+1-555-0199",
            "medical_notes": "Hypertension, Type 2 Diabetes",
            "timezone": "America/New_York",
            "email": "rose@carecircle.demo",
            "quiet_hours_start": 22,
            "quiet_hours_end": 7,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    for user in default_users:
        existing = db.get("users", user["id"])
        if not existing:
            hashed = hash_passcode(user["passcode_plain"])
            record = {
                "id": user["id"],
                "name": user["name"],
                "role": user["role"],
                "elder_id": user["elder_id"],
                "phone": user["phone"],
                "email": user["email"],
                "passcode_hash": hashed,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            db.set("users", user["id"], record)
            db.set("members", user["id"], record)

    # Seed sample medications if none exist
    existing_meds = db.list("medications", filters=[("elder_id", "==", "elder_1")])
    if not existing_meds:
        sample_meds = [
            {
                "id": "med_sample_1",
                "elder_id": "elder_1",
                "name": "Lisinopril",
                "dosage": "10 mg",
                "instructions": "Take 1 tablet every morning with a glass of water",
                "schedule_times": ["08:00"],
                "frequency": "Daily - Morning",
                "pill_color": "#3B82F6",
                "remaining_refills": 24,
                "refill_threshold": 7,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": "med_sample_2",
                "elder_id": "elder_1",
                "name": "Metformin",
                "dosage": "500 mg",
                "instructions": "Take with evening dinner",
                "schedule_times": ["19:00"],
                "frequency": "Daily - Evening",
                "pill_color": "#10B981",
                "remaining_refills": 5,  # Trigger refill notice!
                "refill_threshold": 7,
                "is_active": True,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        ]
        for m in sample_meds:
            db.set("medications", m["id"], m)


def authenticate_with_passcode(login_data: PasscodeLogin, client_ip: str = "unknown") -> TokenResponse:
    """Authenticate a user using their passcode with brute-force rate limiting.

    Args:
        login_data: PasscodeLogin request payload.
        client_ip: IP address for multi-factor rate limit tracking.

    Returns:
        TokenResponse on success.

    Raises:
        HTTPException 429: If account/IP is locked out.
        HTTPException 401: If passcode or user is invalid.
    """
    key = f"{login_data.identifier}:{client_ip}"

    # 1. Check if identifier/IP is currently locked out
    is_locked, remaining_seconds = rate_limiter.is_locked(key)
    if is_locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many incorrect passcode attempts. Locked for {remaining_seconds} seconds.",
            headers={"Retry-After": str(remaining_seconds)},
        )

    # 2. Look up user by identifier (ID or case-insensitive match on ID/role)
    user_doc = db.get("users", login_data.identifier)
    if not user_doc:
        # Search by role name or name
        all_users = db.list("users")
        for u in all_users:
            if (
                u.get("role") == login_data.identifier.lower()
                or u.get("name", "").lower() == login_data.identifier.lower()
            ):
                user_doc = u
                break

    if not user_doc:
        failed_count, now_locked = rate_limiter.record_failure(key)
        remaining = rate_limiter.remaining_attempts(key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid user or passcode. {remaining} attempt(s) remaining.",
        )

    # 3. Verify bcrypt hash
    passcode_hash = user_doc.get("passcode_hash", "")
    is_valid = verify_passcode(login_data.passcode, passcode_hash)

    if not is_valid:
        failed_count, now_locked = rate_limiter.record_failure(key)
        remaining = rate_limiter.remaining_attempts(key)
        if now_locked:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many incorrect passcode attempts. Account locked for 5 minutes.",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Incorrect passcode. {remaining} attempt(s) remaining.",
        )

    # 4. Success - clear failed attempts and return token
    rate_limiter.record_success(key)
    token = create_access_token(
        user_id=user_doc["id"],
        role=user_doc["role"],
        name=user_doc["name"],
        elder_id=user_doc.get("elder_id", user_doc["id"]),
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_doc["id"],
        name=user_doc["name"],
        role=UserRole(user_doc["role"]),
        elder_id=user_doc.get("elder_id", user_doc["id"]),
    )


def get_rate_limit_status(identifier: str, client_ip: str = "unknown") -> RateLimitStatus:
    """Check current rate limit status for an identifier/IP."""
    key = f"{identifier}:{client_ip}"
    is_locked, remaining_seconds = rate_limiter.is_locked(key)
    remaining_attempts = rate_limiter.remaining_attempts(key)
    return RateLimitStatus(
        identifier=identifier,
        is_locked=is_locked,
        remaining_attempts=remaining_attempts,
        lockout_seconds_remaining=remaining_seconds,
    )
