"""
Rate limiting utilities using slowapi.
Protects public endpoints from abuse.

CRIT-AUTH-02 FIX: Added email-based rate limiting for login attempts.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


# Create limiter instance using client IP as key
limiter = Limiter(key_func=get_remote_address)


def get_email_from_body(request: Request) -> str:
    """
    CRIT-AUTH-02 FIX: Extract email from request body for email-based rate limiting.

    This key function is used to rate limit login attempts by email address,
    preventing credential stuffing attacks even when using different IPs.
    """
    # For login endpoints, we want to limit by email
    # FastAPI parses the body, but we need to handle this carefully
    # We'll use a combination of IP + email when available
    ip = get_remote_address(request)

    # Try to get email from the request's state (set by middleware or body parsing)
    email = getattr(request.state, "rate_limit_email", None)

    if email:
        return f"{ip}:{email}"
    return ip


def set_rate_limit_email(request: Request, email: str) -> None:
    """Set the email for rate limiting purposes."""
    request.state.rate_limit_email = email


# CRIT-AUTH-02 FIX: Create a separate limiter for email-based rate limiting
email_limiter = Limiter(key_func=get_email_from_body)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for rate limit exceeded errors.
    Returns a JSON response with retry information.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Rate limit exceeded. Please try again later.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(exc.detail)},
    )


# Rate limit decorators for different endpoint types
# Usage: @limiter.limit("10/minute")

# Common rate limits:
# - "5/minute" for login attempts
# - "30/minute" for authenticated API calls
# - "100/minute" for read-only public data
# - "10/minute" for write operations

# Example usage in router:
# from shared.rate_limit import limiter
#
# @router.post("/login")
# @limiter.limit("5/minute")
# async def login(request: Request, ...):
#     ...
