"""
Security middlewares for the FastAPI application.
Implements security headers and content-type validation.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add security headers to all responses.

    HIGH-MID-01 FIX: Added CSP and HSTS headers for production security.

    Headers added:
    - X-Content-Type-Options: nosniff (prevent MIME sniffing)
    - X-Frame-Options: DENY (prevent clickjacking)
    - X-XSS-Protection: 1; mode=block (legacy XSS protection)
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: disable dangerous browser features
    - Content-Security-Policy: strict CSP (HIGH-MID-01)
    - Strict-Transport-Security: HSTS for production (HIGH-MID-01)
    """

    async def dispatch(self, request: Request, call_next):
        from shared.config.settings import settings

        response = await call_next(request)
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        # XSS protection (legacy, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Control referrer information
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Disable dangerous browser features
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Remove server header if present
        response.headers.pop("server", None)

        # HIGH-MID-01 FIX: Add Content-Security-Policy header
        # Allow self and configured origins for scripts/styles/connect
        csp_directives = [
            "default-src 'self'",
            "script-src 'self'",
            "style-src 'self' 'unsafe-inline'",  # unsafe-inline needed for some UI frameworks
            "img-src 'self' data: https:",  # Allow data URIs and HTTPS images
            "font-src 'self'",
            "connect-src 'self'",  # API connections from same origin
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # HIGH-MID-01 FIX: Add HSTS header in production
        if settings.environment == "production":
            # max-age=31536000 (1 year), includeSubDomains for comprehensive coverage
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )

        return response


class ContentTypeValidationMiddleware(BaseHTTPMiddleware):
    """
    Validate Content-Type for requests with body.

    Ensures POST/PUT/PATCH requests use application/json or form-urlencoded.
    Returns 415 Unsupported Media Type if invalid.
    """

    METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}
    # Endpoints that don't require JSON (webhooks, file uploads, etc.)
    EXEMPT_PATHS = {"/api/billing/webhook", "/api/health"}

    async def dispatch(self, request: Request, call_next):
        if request.method in self.METHODS_WITH_BODY:
            # Skip validation for exempt paths
            if not any(request.url.path.startswith(p) for p in self.EXEMPT_PATHS):
                content_type = request.headers.get("content-type", "")
                # Allow application/json and form-urlencoded (for OAuth flows)
                if content_type and not (
                    content_type.startswith("application/json")
                    or content_type.startswith("application/x-www-form-urlencoded")
                ):
                    return JSONResponse(
                        status_code=415,
                        content={"detail": "Unsupported Media Type. Use application/json"},
                    )
        return await call_next(request)


def register_middlewares(app: FastAPI) -> None:
    """
    Register all security middlewares on the FastAPI application.

    Order matters: middlewares are executed in reverse order of registration.
    ContentTypeValidation runs first, then SecurityHeaders.
    """
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(ContentTypeValidationMiddleware)
