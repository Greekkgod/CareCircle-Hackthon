"""Tests for security headers, bcrypt hashing, and passcode rate limiting."""

from starlette.testclient import TestClient
from app.core.config import settings
from app.core.security import hash_passcode, rate_limiter, verify_passcode


def test_passcode_bcrypt_hashing():
    """Verify passcodes are hashed with bcrypt and verifiable."""
    plain = "elderSecret123"
    hashed = hash_passcode(plain)

    assert hashed != plain
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_passcode(plain, hashed) is True
    assert verify_passcode("wrongSecret", hashed) is False


def test_rate_limiter_lockout_mechanism():
    """Verify rate limiter locks out after exceeding max attempts."""
    key = "test_user_key"
    max_att = settings.max_passcode_attempts

    for i in range(max_att - 1):
        failed_count, is_locked = rate_limiter.record_failure(key)
        assert is_locked is False

    # The Nth failure triggers lockout
    failed_count, is_locked = rate_limiter.record_failure(key)
    assert is_locked is True

    locked_check, remaining = rate_limiter.is_locked(key)
    assert locked_check is True
    assert remaining > 0


def test_auth_login_rate_limiting_endpoint(client: TestClient):
    """Verify endpoint returns HTTP 429 after repeated wrong passcode attempts."""
    max_att = settings.max_passcode_attempts

    # Attempt wrong passcodes up to limit
    for _ in range(max_att):
        resp = client.post(
            "/api/auth/login",
            json={"identifier": "elder_1", "passcode": "0000"},
        )
        assert resp.status_code in [401, 429]

    # Subsequent attempt must be 429 Too Many Requests
    resp = client.post(
        "/api/auth/login",
        json={"identifier": "elder_1", "passcode": "0000"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_security_headers_present(client: TestClient):
    """Verify required HTTP security headers are attached to responses."""
    resp = client.get("/health")
    assert resp.status_code == 200

    headers = resp.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Strict-Transport-Security" in headers
    assert "Content-Security-Policy" in headers
    assert "Permissions-Policy" in headers


def test_unauthenticated_request_rejected(client: TestClient):
    """Verify protected routes reject unauthenticated requests with 401."""
    resp = client.get("/api/medications/")
    assert resp.status_code == 401
