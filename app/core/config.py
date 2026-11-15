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

    # Allowed CORS origins
    allowed_origins: List[str] = ["*"]


settings = Settings()
