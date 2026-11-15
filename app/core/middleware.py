"""Security headers and audit middleware.

Applies modern HTTP security headers and prevents clickjacking, MIME-sniffing,
and unauthorized feature access.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing secure response headers across all HTTP endpoints."""

    async def dispatch(self, request: Request, call_next) -> Response:
        """Process incoming request and attach standard security headers to response.

        Args:
            request: The incoming Starlette/FastAPI request.
            call_next: Next request handler in the middleware chain.

        Returns:
            HTTP response enhanced with security headers.
        """
        response: Response = await call_next(request)

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent framing / clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"

        # Referrer privacy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser APIs not needed by platform
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )

        # Enforce HTTPS transport policy
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # Content Security Policy (allows local PWA scripts, styles, manifests, web workers)
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "font-src 'self' https://fonts.gstatic.com data:",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "manifest-src 'self'",
            "worker-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        return response
