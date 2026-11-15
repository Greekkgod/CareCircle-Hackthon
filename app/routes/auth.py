"""Authentication endpoints with passcode verification and rate limiting."""

from typing import Dict
from fastapi import APIRouter, Depends, Request
from app.core.security import get_current_user
from app.models.auth import PasscodeLogin, RateLimitStatus, TokenResponse, UserProfile
from app.services.auth_service import authenticate_with_passcode, get_rate_limit_status

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: PasscodeLogin, request: Request) -> TokenResponse:
    """Authenticate with user identifier and hashed passcode.

    Rate-limited: Locks out after configured failed attempts.
    """
    client_ip = request.client.host if request.client else "127.0.0.1"
    return authenticate_with_passcode(payload, client_ip=client_ip)


@router.get("/rate-limit-status", response_model=RateLimitStatus)
async def check_rate_limit(identifier: str, request: Request) -> RateLimitStatus:
    """Check remaining passcode attempts and lockout status."""
    client_ip = request.client.host if request.client else "127.0.0.1"
    return get_rate_limit_status(identifier, client_ip=client_ip)


@router.get("/me", response_model=Dict[str, str])
async def get_current_user_profile(
    current_user: Dict[str, str] = Depends(get_current_user),
) -> Dict[str, str]:
    """Retrieve authenticated user token claims."""
    return current_user
