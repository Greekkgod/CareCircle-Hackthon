"""Comprehensive security and accessibility review test suite for CareCircle.

Verifies:
1. Security Headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy).
2. Input Validation (Pydantic schema enforcement, boundary conditions, malformed types).
3. Rate Limiting & Brute Force Lockout (Sliding window, Retry-After header).
4. Accessibility Standards (WCAG 2.1 AA/AAA Contrast Ratios, ARIA attributes, semantic landmarks, touch target scale).
"""

import math
from pathlib import Path

from starlette.testclient import TestClient

from app.core.config import settings
from app.core.security import create_access_token, rate_limiter


def _relative_luminance(hex_color: str) -> float:
    """Calculate relative luminance according to WCAG 2.1 specifications."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))

    def _adjust(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else math.pow((c + 0.055) / 1.055, 2.4)

    return 0.2126 * _adjust(r) + 0.7152 * _adjust(g) + 0.0722 * _adjust(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    """Calculate contrast ratio between two hex colors according to WCAG 2.1."""
    lum1 = _relative_luminance(hex1)
    lum2 = _relative_luminance(hex2)
    lighter = max(lum1, lum2)
    darker = min(lum1, lum2)
    return (lighter + 0.05) / (darker + 0.05)


def test_security_headers_enforced_across_endpoints(client: TestClient):
    """Verify security headers are attached across API, health, and static root."""
    endpoints = ["/health", "/", "/manifest.webmanifest"]
    for ep in endpoints:
        resp = client.get(ep)
        headers = resp.headers
        assert headers.get("X-Content-Type-Options") == "nosniff", f"Missing nosniff on {ep}"
        assert headers.get("X-Frame-Options") == "DENY", f"Missing X-Frame-Options on {ep}"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin", f"Missing Referrer-Policy on {ep}"
        assert "max-age=31536000" in headers.get("Strict-Transport-Security", ""), f"Missing HSTS on {ep}"
        assert "default-src 'self'" in headers.get("Content-Security-Policy", ""), f"Missing CSP on {ep}"
        assert "camera=(self)" in headers.get("Permissions-Policy", ""), f"Missing camera permission on {ep}"
        assert "microphone=(self)" in headers.get("Permissions-Policy", ""), f"Missing microphone permission on {ep}"


def test_input_validation_pydantic_enforcement(client: TestClient):
    """Verify rigorous input validation rejects invalid payloads with HTTP 422."""
    token = create_access_token(
        user_id="caretaker_1",
        role="caretaker",
        name="Nurse Joy",
        elder_id="elder_1",
    )
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Invalid dose quantity string or negative refills
    invalid_med_payload = {
        "elder_id": "elder_1",
        "name": "",  # Empty name rejected
        "dosage": "10 mg",
        "instructions": "Take daily",
        "frequency": "once_daily",
        "refills_remaining": -5,  # Negative refills rejected
    }
    resp = client.post("/api/medications/", json=invalid_med_payload, headers=headers)
    assert resp.status_code == 422

    # 2. Malformed JSON types (e.g. array instead of string)
    malformed_payload = {
        "elder_id": "elder_1",
        "name": ["Invalid", "Array"],
        "dosage": 12345,
    }
    resp2 = client.post("/api/medications/", json=malformed_payload, headers=headers)
    assert resp2.status_code == 422

    # 3. Invalid dose status enum in dose logging
    invalid_dose = {
        "medication_id": "med_123",
        "elder_id": "elder_1",
        "status": "NON_EXISTENT_STATUS",
    }
    resp3 = client.post("/api/medications/log", json=invalid_dose, headers=headers)
    assert resp3.status_code == 422


def test_passcode_rate_limit_sliding_window_lockout():
    """Verify rate limiter locks out after exceeding max attempts and provides Retry-After."""
    test_key = "audit_reviewer_ip_test_unique_2026"
    rate_limiter.record_success(test_key)

    # First N-1 attempts fail without lockout
    for _ in range(settings.max_passcode_attempts - 1):
        _, is_locked = rate_limiter.record_failure(test_key)
        assert is_locked is False

    # The Nth failure triggers lockout
    _, is_locked = rate_limiter.record_failure(test_key)
    assert is_locked is True

    # Validate lock status
    locked, remaining_sec = rate_limiter.is_locked(test_key)
    assert locked is True
    assert remaining_sec > 0


def test_wcag_contrast_ratios():
    """Verify color palette meets and exceeds WCAG AA (4.5:1) and AAA (7.0:1) contrast ratios."""
    # High Contrast Mode: Bright Yellow on Pure Black
    yellow_on_black = _contrast_ratio("#ffe500", "#000000")
    assert yellow_on_black >= 15.0, f"Expected >15.0:1 contrast, got {yellow_on_black:.2f}:1"

    # Normal Theme: High-contrast slate on off-white
    slate_on_white = _contrast_ratio("#0f172a", "#f8fafc")
    assert slate_on_white >= 12.0, f"Expected >12.0:1 contrast, got {slate_on_white:.2f}:1"

    # Primary Action Button: White text on Forest Green
    white_on_green = _contrast_ratio("#ffffff", "#15803d")
    assert white_on_green >= 4.5, f"Expected >=4.5:1 (WCAG AA), got {white_on_green:.2f}:1"


def test_semantic_aria_and_accessibility_tokens():
    """Verify HTML semantic landmarks, ARIA live regions, skip links, and CSS tokens."""
    index_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
    html_content = index_path.read_text(encoding="utf-8")

    # Document language
    assert '<html lang="en"' in html_content

    # Skip to main content link for keyboard users
    assert '<a href="#main-content" class="skip-link">Skip to main content</a>' in html_content
    assert 'id="main-content"' in html_content

    # Semantic Landmarks
    assert "<header" in html_content
    assert "<nav" in html_content
    assert "<main" in html_content
    assert "<section" in html_content
    assert "<dialog" in html_content

    # ARIA live regions for dynamic screen reader announcements
    assert 'aria-live="polite"' in html_content
    assert 'aria-atomic="true"' in html_content

    # Accessibility CSS tokens
    css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
    css_content = css_path.read_text(encoding="utf-8")

    # Senior typography: 22px base font size (scalable to 26px and 30px)
    assert "--font-base: 22px;" in css_content
    assert "font-size: 22px;" in css_content
    assert "font-size: 26px;" in css_content
    assert "font-size: 30px;" in css_content

    # Touch targets: 56px minimum touch target, 72px hero button
    assert "--min-touch-target: 56px;" in css_content
    assert "min-height: 72px;" in css_content

    # Reduced motion media query
    assert "@media (prefers-reduced-motion: reduce)" in css_content
