"""Application configuration module.

Loads environment variables and validates configuration settings using Pydantic.
"""

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration settings for the CareCircle platform."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core application
    app_name: str = "CareCircle"
    environment: str = "development"
    debug: bool = False
    secret_key: str = "carecircle-hackathon-change-this-in-production-use-a-strong-secret-key-32chars"
    host: str = "0.0.0.0"
    port: int = 8000

    # Google Cloud Firestore
    firestore_project_id: str = ""
    use_mock_firestore: bool = True
    google_application_credentials: str = ""

    # Gemini API
    gemini_api_key: str = "mock"
    gemini_model: str = "gemini-1.5-flash"

    # Security & Passcode
    passcode_salt_rounds: int = 12
    max_passcode_attempts: int = 5
    passcode_lockout_seconds: int = 300
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # Cloud Scheduler & Internal API Protection
    cron_secret: str = "carecircle-internal-scheduler-secret-2026"

    # Email & Notifications
    use_mock_email: bool = True
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "notifications@carecircle.app"
    smtp_use_tls: bool = True

    # Escalation Ladder & Timing Defaults (in minutes)
    escalation_elder_grace_minutes: int = 0
    escalation_caretaker_delay_minutes: int = 15
    escalation_family_delay_minutes: int = 30

    # Quiet Hours (24-hour format)
    quiet_hours_start: int = 22
    quiet_hours_end: int = 7

    # Allowed CORS origins
    allowed_origins: List[str] = ["*"]


settings = Settings()
