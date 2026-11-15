"""Security utilities module for authentication, hashing, and rate limiting.

Implements bcrypt passcode hashing, JWT token handling, rate limiting
for passcode attempts, and role-based access control.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
import threading
import bcrypt
import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security_bearer = HTTPBearer(auto_error=False)


class PasscodeRateLimiter:
    """Thread-safe in-memory rate limiter for passcode verification attempts."""

    def __init__(self, max_attempts: int, lockout_seconds: int) -> None:
        """Initialize the rate limiter with limits and lockout duration.

        Args:
            max_attempts: Maximum allowed consecutive failed attempts.
            lockout_seconds: Lockout duration in seconds after max attempts.
        """
        self.max_attempts: int = max_attempts
        self.lockout_seconds: int = lockout_seconds
        self._lock: threading.Lock = threading.Lock()
        # key -> (failed_count, lockout_until_timestamp)
        self._attempts: Dict[str, Tuple[int, Optional[datetime]]] = {}

    def is_locked(self, key: str) -> Tuple[bool, int]:
        """Check if an identifier is currently locked out.

        Args:
            key: Unique key such as user ID or IP address.

        Returns:
            Tuple of (is_locked_bool, remaining_lockout_seconds).
        """
        with self._lock:
            record = self._attempts.get(key)
            if not record:
                return False, 0

            failed_count, lockout_until = record
            if lockout_until:
                now = datetime.now(timezone.utc)
                if now < lockout_until:
                    remaining = int((lockout_until - now).total_seconds())
                    return True, max(remaining, 1)
                # Lockout expired, reset failed attempts
                del self._attempts[key]
                return False, 0

            return False, 0

    def record_failure(self, key: str) -> Tuple[int, bool]:
        """Record a failed passcode attempt for a key.

        Args:
            key: Unique key such as user ID or IP address.

        Returns:
            Tuple of (current_failed_count, is_now_locked).
        """
        with self._lock:
            now = datetime.now(timezone.utc)
            record = self._attempts.get(key, (0, None))
            failed_count = record[0] + 1

            if failed_count >= self.max_attempts:
                lockout_until = now + timedelta(seconds=self.lockout_seconds)
                self._attempts[key] = (failed_count, lockout_until)
                return failed_count, True

            self._attempts[key] = (failed_count, None)
            return failed_count, False

    def record_success(self, key: str) -> None:
        """Reset failed passcode attempts upon successful authentication.

        Args:
            key: Unique key such as user ID or IP address.
        """
        with self._lock:
            self._attempts.pop(key, None)

    def remaining_attempts(self, key: str) -> int:
        """Get the number of remaining attempts before lockout.

        Args:
            key: Unique key such as user ID or IP address.

        Returns:
            Number of attempts left before lockout.
        """
        with self._lock:
            record = self._attempts.get(key)
            if not record:
                return self.max_attempts
            failed_count, _ = record
            return max(0, self.max_attempts - failed_count)


rate_limiter = PasscodeRateLimiter(
    max_attempts=settings.max_passcode_attempts,
    lockout_seconds=settings.passcode_lockout_seconds,
)


def hash_passcode(passcode: str) -> str:
    """Hash a plaintext passcode using bcrypt.

    Args:
        passcode: Plaintext passcode string.

    Returns:
        Salted and hashed passcode string.
    """
    salt = bcrypt.gensalt(rounds=settings.passcode_salt_rounds)
    hashed_bytes = bcrypt.hashpw(passcode.encode("utf-8"), salt)
    return hashed_bytes.decode("utf-8")


def verify_passcode(passcode: str, hashed_passcode: str) -> bool:
    """Verify a plaintext passcode against its bcrypt hash.

    Args:
        passcode: Plaintext passcode string.
        hashed_passcode: Hashed passcode string.

    Returns:
        True if the passcode matches the hash, False otherwise.
    """
    try:
        return bcrypt.checkpw(
            passcode.encode("utf-8"),
            hashed_passcode.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    user_id: str,
    role: str,
    name: str,
    elder_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        user_id: Unique identifier of the user.
        role: User role (elder, caretaker, family).
        name: User display name.
        elder_id: Associated elder ID if applicable.
        expires_delta: Optional custom token expiration delta.

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(timezone.utc)
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    expire = now + delta

    payload = {
        "sub": user_id,
        "role": role,
        "name": name,
        "elder_id": elder_id or user_id,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(
        payload,
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_access_token(token: str) -> Dict[str, str]:
    """Decode and validate a JWT access token.

    Args:
        token: JWT string.

    Returns:
        Dictionary of token payload claims.

    Raises:
        HTTPException: If token is expired or invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please enter passcode again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    auth: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Dict[str, str]:
    """FastAPI dependency to retrieve the authenticated user payload.

    Args:
        auth: Bearer token from the Authorization header.

    Returns:
        Dictionary containing authenticated user claims.

    Raises:
        HTTPException: If credentials are missing or invalid.
    """
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please sign in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_access_token(auth.credentials)


def require_roles(allowed_roles: List[str]):
    """FastAPI dependency factory enforcing role-based permissions.

    Args:
        allowed_roles: List of allowed role names (elder, caretaker, family).

    Returns:
        Dependency callable verifying current user's role.
    """

    async def role_checker(
        current_user: Dict[str, str] = Security(get_current_user),
    ) -> Dict[str, str]:
        user_role = current_user.get("role", "")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires one of roles: {', '.join(allowed_roles)}.",
            )
        return current_user

    return role_checker
