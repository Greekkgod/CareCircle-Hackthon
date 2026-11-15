"""Main FastAPI application entry point for CareCircle.

Configures routes, security middleware, static asset serving, and startup seeding.
"""

from contextlib import asynccontextmanager
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.middleware import SecurityHeadersMiddleware
from app.routes import ai_assistant, appointments, auth, checkins, medications
from app.services.auth_service import seed_default_users

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle event handler: seeds initial demo users into Firestore."""
    seed_default_users()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Elderly care & medication management platform for hackathons.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

# Attach security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Attach CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(auth.router)
app.include_router(medications.router)
app.include_router(appointments.router)
app.include_router(ai_assistant.router)
app.include_router(checkins.router)


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for container probes."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "environment": settings.environment,
    }


# Ensure static directory exists before mounting
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serve the single page PWA index application."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(index_path, media_type="text/html")
    return {"message": "Welcome to CareCircle API. Visit /docs for OpenAPI specifications."}


@app.get("/manifest.webmanifest")
async def serve_manifest():
    """Serve the PWA web app manifest."""
    manifest_path = STATIC_DIR / "manifest.webmanifest"
    return FileResponse(manifest_path, media_type="application/manifest+json")


@app.get("/sw.js")
async def serve_service_worker():
    """Serve the PWA service worker with appropriate Service-Worker-Allowed header."""
    sw_path = STATIC_DIR / "sw.js"
    response = FileResponse(sw_path, media_type="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    return response
