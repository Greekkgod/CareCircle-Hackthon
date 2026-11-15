"""Vercel serverless entry point for CareCircle FastAPI application.

Loads the initialized ASGI `app` callable for the @vercel/python runtime.
"""

from app.main import app

# Vercel serverless functions automatically detect and execute `app`
__all__ = ["app"]
