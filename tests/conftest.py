"""Pytest fixtures and test configuration for CareCircle."""

import pytest
from starlette.testclient import TestClient
from app.core.database import db
from app.core.security import create_access_token, rate_limiter
from app.main import app
from app.services.auth_service import seed_default_users


@pytest.fixture(autouse=True)
def setup_test_db():
    """Reset the mock database and rate limiter before each test."""
    db.reset_mock()
    seed_default_users()
    with rate_limiter._lock:
        rate_limiter._attempts.clear()
    yield
    db.reset_mock()
    with rate_limiter._lock:
        rate_limiter._attempts.clear()


@pytest.fixture
def client():
    """Synchronous test client."""
    return TestClient(app)


@pytest.fixture
def elder_token():
    """Token for authenticated elder user."""
    return create_access_token(
        user_id="elder_1",
        role="elder",
        name="Rose Dawson",
        elder_id="elder_1",
    )


@pytest.fixture
def caretaker_token():
    """Token for authenticated caretaker user."""
    return create_access_token(
        user_id="caretaker_1",
        role="caretaker",
        name="Sarah Jenkins, RN",
        elder_id="elder_1",
    )


@pytest.fixture
def family_token():
    """Token for authenticated family user."""
    return create_access_token(
        user_id="family_1",
        role="family",
        name="David Dawson",
        elder_id="elder_1",
    )
