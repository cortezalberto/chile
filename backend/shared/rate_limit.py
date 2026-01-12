"""
Rate limiting utilities using slowapi.
Protects public endpoints from abuse.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


# Create limiter instance using client IP as key
limiter = Limiter(key_func=get_remote_address)


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
