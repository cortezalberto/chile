"""
Rate limiting utilities using slowapi + Redis for email-based limiting.
Protects public endpoints from abuse.

CRIT-AUTH-02 FIX: Added email-based rate limiting for login attempts.
QA-HIGH-01 FIX: Uses Redis for email-based rate limiting (slowapi only supports IP).
REDIS-CRIT-01 FIX: Changed to fail-closed policy on Redis errors.
REDIS-HIGH-06 FIX: Made INCR+EXPIRE atomic using Lua script.
"""

import asyncio
import concurrent.futures
import threading
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

from shared.config.settings import settings
from shared.config.logging import get_logger

logger = get_logger(__name__)

# Create limiter instance using client IP as key
limiter = Limiter(key_func=get_remote_address)


def set_rate_limit_email(request: Request, email: str) -> None:
    """Set the email for rate limiting purposes (for logging)."""
    request.state.rate_limit_email = email


# =============================================================================
# QA-HIGH-01 FIX: Redis-based email rate limiting for login attempts
# =============================================================================

# SHARED-LOW-01 FIX: Use configurable values from settings
LOGIN_RATE_LIMIT = settings.login_rate_limit  # Max attempts per window
LOGIN_RATE_WINDOW = settings.login_rate_window  # Window in seconds

# SHARED-MED-01 FIX: Module-level executor to avoid creating on each call
_rate_limit_executor: concurrent.futures.ThreadPoolExecutor | None = None
# REDIS-CRIT-01 FIX: Lock to protect executor initialization (prevents race condition)
_executor_lock = threading.Lock()

# REDIS-HIGH-06 FIX: Lua script for atomic INCR + EXPIRE
# This prevents race condition where key could be left without TTL
RATE_LIMIT_LUA_SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])

local count = redis.call('INCR', key)
if count == 1 then
    redis.call('EXPIRE', key, window)
end

local ttl = redis.call('TTL', key)
if ttl == -1 then
    redis.call('EXPIRE', key, window)
    ttl = window
end

return {count, ttl}
"""

# Cached script SHA for performance
_rate_limit_script_sha: str | None = None
# CRIT-LOCK-01 FIX: Lock to prevent race condition on script SHA initialization
# Threading lock at module level (NOT inside function) to ensure single instance
import threading
_script_lock_init = threading.Lock()  # Module-level threading lock
_rate_limit_script_lock: asyncio.Lock | None = None


def _get_script_lock() -> asyncio.Lock:
    """
    CRIT-LOCK-01 FIX: Get or create the script lock (lazy initialization for event loop safety).
    Uses double-check pattern with module-level threading.Lock to prevent multiple asyncio.Lock instances.
    """
    global _rate_limit_script_lock
    if _rate_limit_script_lock is None:
        with _script_lock_init:  # Use module-level lock
            if _rate_limit_script_lock is None:
                _rate_limit_script_lock = asyncio.Lock()
    return _rate_limit_script_lock


def _get_rate_limit_executor() -> concurrent.futures.ThreadPoolExecutor:
    """
    Get or create the module-level ThreadPoolExecutor.

    REDIS-CRIT-01 FIX: Uses double-check locking pattern to prevent
    race condition where multiple threads create separate executors.
    """
    global _rate_limit_executor
    if _rate_limit_executor is None:
        with _executor_lock:
            if _rate_limit_executor is None:  # Double-check inside lock
                _rate_limit_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=2, thread_name_prefix="rate_limit"
                )
    return _rate_limit_executor


def _format_retry_time(seconds: int) -> str:
    """SHARED-LOW-03 FIX: Format retry time in human-readable format."""
    if seconds < 60:
        return f"{seconds} segundos"
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    if remaining_seconds == 0:
        return f"{minutes} minuto{'s' if minutes > 1 else ''}"
    return f"{minutes}m {remaining_seconds}s"


async def check_email_rate_limit(email: str, fail_closed: bool = True) -> None:
    """
    QA-HIGH-01 FIX: Check if email has exceeded rate limit using Redis.
    Raises HTTPException 429 if rate limit exceeded.

    REDIS-HIGH-06 FIX: Uses Lua script for atomic INCR + EXPIRE.
    REDIS-CRIT-01 FIX: Fail-closed on Redis errors (deny access by default).

    Args:
        email: The email address to check.
        fail_closed: If True, deny access on Redis errors. If False, allow access.
                     Default is True for security (fail-closed pattern).
    """
    global _rate_limit_script_sha

    try:
        from shared.infrastructure.events import get_redis_pool

        redis = await get_redis_pool()
        key = f"ratelimit:login:{email}"  # REDIS-HIGH-01: Standardized prefix

        # REDIS-HIGH-06 FIX: Use Lua script for atomic operation
        # SHARED-RATELIMIT-01 FIX: Protected with asyncio.Lock to prevent race condition
        async with _get_script_lock():
            try:
                # Try to use cached script SHA first (faster)
                if _rate_limit_script_sha:
                    result = await redis.evalsha(
                        _rate_limit_script_sha,
                        1,  # Number of keys
                        key,
                        LOGIN_RATE_LIMIT,
                        LOGIN_RATE_WINDOW,
                    )
                else:
                    # First call - load script and cache SHA
                    _rate_limit_script_sha = await redis.script_load(RATE_LIMIT_LUA_SCRIPT)
                    result = await redis.evalsha(
                        _rate_limit_script_sha,
                        1,
                        key,
                        LOGIN_RATE_LIMIT,
                        LOGIN_RATE_WINDOW,
                    )
            except Exception as script_error:
                # Script may have been flushed from Redis, re-register
                if "NOSCRIPT" in str(script_error):
                    logger.debug("Lua script cache miss, re-registering")
                    _rate_limit_script_sha = await redis.script_load(RATE_LIMIT_LUA_SCRIPT)
                    result = await redis.evalsha(
                        _rate_limit_script_sha,
                        1,
                        key,
                        LOGIN_RATE_LIMIT,
                        LOGIN_RATE_WINDOW,
                    )
                else:
                    raise  # Re-raise other exceptions

        count, ttl = result

        if count > LOGIN_RATE_LIMIT:
            retry_time = _format_retry_time(ttl)
            logger.warning(
                "Rate limit exceeded for email",
                email=email,
                count=count,
                limit=LOGIN_RATE_LIMIT,
                ttl=ttl,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Demasiados intentos de login. Intente nuevamente en {retry_time}.",
                headers={"Retry-After": str(ttl)},
            )

    except ImportError:
        # Redis module not available
        if fail_closed:
            logger.error("Redis not available - failing closed for rate limit")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Servicio temporalmente no disponible. Intente más tarde.",
            )
        else:
            logger.warning("Redis not available, skipping rate limit check", email=email)

    except HTTPException:
        raise  # Re-raise rate limit/service unavailable exceptions

    except Exception as e:
        # REDIS-CRIT-01 FIX: Fail-closed on Redis errors
        logger.error(
            "Rate limit check failed - applying fail-closed policy",
            email=email,
            error=str(e),
            fail_closed=fail_closed,
        )
        if fail_closed:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Error de verificación. Intente nuevamente en unos segundos.",
                headers={"Retry-After": "5"},
            )
        # If fail_closed=False, allow the request through (legacy behavior)


def check_email_rate_limit_sync(email: str, fail_closed: bool = True) -> None:
    """
    Synchronous wrapper for check_email_rate_limit.
    Safe to call from sync endpoints.

    CRIT-01 FIX: Use thread pool to properly block when in async context,
    instead of asyncio.ensure_future which returns immediately.
    SHARED-MED-01 FIX: Reuse module-level executor instead of creating per-call.
    REDIS-CRIT-01 FIX: Fail-closed by default on errors.

    Args:
        email: The email address to check.
        fail_closed: If True, deny access on Redis errors.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # CRIT-01 FIX: Use thread pool to run async check synchronously
            # SHARED-MED-01 FIX: Reuse module-level executor
            executor = _get_rate_limit_executor()
            future = executor.submit(
                asyncio.run, check_email_rate_limit(email, fail_closed)
            )
            try:
                future.result(timeout=5.0)  # 5 second timeout
            except concurrent.futures.TimeoutError:
                logger.error("Rate limit check timed out", email=email)
                if fail_closed:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail="Verificación de seguridad expiró. Intente nuevamente.",
                        headers={"Retry-After": "5"},
                    )
        else:
            loop.run_until_complete(check_email_rate_limit(email, fail_closed))
    except HTTPException:
        raise  # Re-raise rate limit/service unavailable exceptions
    except RuntimeError:
        # No event loop, try creating one
        try:
            asyncio.run(check_email_rate_limit(email, fail_closed))
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Rate limit check failed in sync wrapper", error=str(e))
            if fail_closed:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Error de verificación. Intente nuevamente.",
                    headers={"Retry-After": "5"},
                )


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Custom handler for rate limit exceeded errors.
    Returns a JSON response with retry information.
    """
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Límite de solicitudes excedido. Intente más tarde.",
            "retry_after": exc.detail,
        },
        headers={"Retry-After": str(exc.detail)},
    )


def close_rate_limit_executor() -> None:
    """
    SHARED-RATELIMIT-02 FIX: Clean up the module-level ThreadPoolExecutor.
    Should be called on application shutdown.
    """
    global _rate_limit_executor
    if _rate_limit_executor is not None:
        try:
            _rate_limit_executor.shutdown(wait=False)
            logger.info("Rate limit executor closed")
        except Exception as e:
            logger.warning("Error closing rate limit executor", error=str(e))
        _rate_limit_executor = None


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
