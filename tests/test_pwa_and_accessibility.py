"""Tests for PWA capabilities and accessibility requirements."""

from pathlib import Path

from starlette.testclient import TestClient


def test_pwa_manifest_endpoint(client: TestClient):
    """Verify web app manifest is served with standalone display and theme color."""
    resp = client.get("/manifest.webmanifest")
    assert resp.status_code == 200
    manifest = resp.json()
    assert manifest["display"] == "standalone"
    assert manifest["short_name"] == "CareCircle"
    assert len(manifest["icons"]) > 0


def test_pwa_service_worker_endpoint(client: TestClient):
    """Verify service worker file is served with correct headers."""
    resp = client.get("/sw.js")
    assert resp.status_code == 200
    assert resp.headers.get("Service-Worker-Allowed") == "/"
    assert "caches.open" in resp.text


def test_accessibility_html_semantics_and_aria():
    """Verify semantic HTML, skip-link, labels, ARIA live regions, hero next dose, bottom nav, and dashboard in index.html."""
    html_path = Path(__file__).resolve().parent.parent / "static" / "index.html"
    assert html_path.exists()
    content = html_path.read_text(encoding="utf-8")

    # Semantic tags
    assert "<main" in content
    assert "<header" in content
    assert "<nav" in content
    assert "<article" in content
    assert "<section" in content
    assert "<footer" in content

    # Skip to main content link
    assert 'class="skip-link"' in content
    assert 'href="#main-content"' in content

    # ARIA live region for screen readers
    assert 'role="status"' in content
    assert 'aria-live="polite"' in content

    # Accessible labels
    assert 'aria-label=' in content
    assert '<label for=' in content

    # Elder Hero Next Dose and Actions
    assert 'id="hero-next-dose-card"' in content
    assert 'id="btn-huge-take"' in content
    assert 'id="btn-snooze-hero"' in content
    assert 'id="btn-readout-hero"' in content

    # 4-item Elder Bottom Navigation (Today, Medicines, Appointments, Family)
    assert 'id="elder-bottom-nav"' in content
    assert 'id="bottom-tab-today"' in content
    assert 'id="bottom-tab-meds"' in content
    assert 'id="bottom-tab-appts"' in content
    assert 'id="bottom-tab-family"' in content

    # Caretaker Dashboard Status Banner & Weekly Adherence Strip
    assert 'id="caretaker-status-banner"' in content
    assert 'id="caretaker-weekly-adherence"' in content

    # Senior Text Scaling & High Contrast Controls
    assert 'id="btn-text-normal"' in content
    assert 'id="btn-text-large"' in content
    assert 'id="btn-text-xlarge"' in content
    assert 'id="btn-contrast-toggle"' in content


def test_accessibility_css_tokens():
    """Verify 20px+ base font, 56px+ touch target, high contrast theme, and reduced motion in app.css."""
    css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
    assert css_path.exists()
    content = css_path.read_text(encoding="utf-8")

    # Base font size >= 20px
    assert "--font-base: 22px;" in content or "font-size: 2" in content

    # 56px+ touch targets
    assert "--min-touch-target: 56px;" in content
    assert "min-height: var(--min-touch-target)" in content

    # High contrast theme and text scaling
    assert 'html[data-text-size="large"]' in content
    assert 'html[data-theme="high-contrast"]' in content

    # Huge 'I took it' button styling
    assert ".btn-huge-take" in content
    assert ".elder-bottom-nav" in content

    # Reduced motion preference support
    assert "@media (prefers-reduced-motion: reduce)" in content


def test_service_worker_offline_schedule_caching():
    """Verify service worker handles caching for offline today schedule."""
    sw_path = Path(__file__).resolve().parent.parent / "static" / "sw.js"
    assert sw_path.exists()
    content = sw_path.read_text(encoding="utf-8")

    assert "API_CACHE" in content
    assert "STATIC_CACHE" in content
    assert "Offline mode" in content
    assert "caches.open" in content
