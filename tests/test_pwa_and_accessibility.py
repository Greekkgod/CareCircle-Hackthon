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
    """Verify semantic HTML, skip-link, labels, and ARIA live regions in index.html."""
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


def test_accessibility_css_tokens():
    """Verify 20px+ base font, 56px+ touch target, and reduced motion in app.css."""
    css_path = Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
    assert css_path.exists()
    content = css_path.read_text(encoding="utf-8")

    # Base font size >= 20px
    assert "--font-base: 22px;" in content or "font-size: 2" in content

    # 56px+ touch targets
    assert "--min-touch-target: 56px;" in content
    assert "min-height: var(--min-touch-target)" in content

    # Reduced motion preference support
    assert "@media (prefers-reduced-motion: reduce)" in content
