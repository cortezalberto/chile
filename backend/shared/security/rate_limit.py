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
# CRIT-LOCK-02 FIX: Use threading.Lock instead of asyncio.Lock to avoid event loop issues
# asyncio.Lock gets attached to one event loop and fails when used from another
# (e.g., when asyncio.run() creates a new loop in check_email_rate_limit_sync)
_script_sha_lock = threading.Lock()  # Module-level threading lock for script SHA


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
        from shared.infrastructure.redis.constants import PREFIX_RATELIMIT_LOGIN

        redis = await get_redis_pool()
        key = f"{PREFIX_RATELIMIT_LOGIN}{email}"  # REDIS-HIGH-01: Standardized prefix


        # REDIS-HIGH-06 FIX: Use Lua script for atomic operation
        # FAIL-CRIT-01 FIX: Proper double-check pattern to prevent race condition
        # This ensures only one thread loads the script even under concurrent access
        with _script_sha_lock:
            current_sha = _rate_limit_script_sha

        try:
            if current_sha:
                result = await redis.evalsha(
                    current_sha,
                    1,  # Number of keys
                    key,
                    LOGIN_RATE_LIMIT,
                    LOGIN_RATE_WINDOW,
                )
            else:
                # First call - load script and cache SHA with double-check
                new_sha = await redis.script_load(RATE_LIMIT_LUA_SCRIPT)
                with _script_sha_lock:
                    # FAIL-CRIT-01 FIX: Double-check - another thread may have set it
                    if _rate_limit_script_sha is None:
                        _rate_limit_script_sha = new_sha
                    current_sha = _rate_limit_script_sha
                result = await redis.evalsha(
                    current_sha,
                    1,
                    key,
                    LOGIN_RATE_LIMIT,
                    LOGIN_RATE_WINDOW,
                )
        except Exception as script_error:
            # Script may have been flushed from Redis, re-register
            if "NOSCRIPT" in str(script_error):
                logger.debug("Lua script cache miss, re-registering")
                new_sha = await redis.script_load(RATE_LIMIT_LUA_SCRIPT)
                with _script_sha_lock:
                    _rate_limit_script_sha = new_sha
                result = await redis.evalsha(
                    new_sha,
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
    Synchronous rate limit check using sync Redis client.
    Safe to call from sync endpoints without event loop issues.

    CRIT-LOCK-03 FIX: Completely rewritten to use sync Redis client directly,
    avoiding asyncio event loop conflicts that occur when using asyncio.run()
    with a Redis pool created in a different event loop.

    Args:
        email: The email address to check.
        fail_closed: If True, deny access on Redis errors.
    """
    global _rate_limit_script_sha

    try:
        from shared.infrastructure.events import get_redis_sync_client
        from shared.infrastructure.redis.constants import PREFIX_RATELIMIT_LOGIN

        redis_client = get_redis_sync_client()
        key = f"{PREFIX_RATELIMIT_LOGIN}{email}"


        # Use Lua script for atomic INCR + EXPIRE
        with _script_sha_lock:
            current_sha = _rate_limit_script_sha

        try:
            if current_sha:
                result = redis_client.evalsha(
                    current_sha,
                    1,
                    key,
                    LOGIN_RATE_LIMIT,
                    LOGIN_RATE_WINDOW,
                )
            else:
                # First call - load script and cache SHA
                new_sha = redis_client.script_load(RATE_LIMIT_LUA_SCRIPT)
                with _script_sha_lock:
                    _rate_limit_script_sha = new_sha
                result = redis_client.evalsha(
                    new_sha,
                    1,
                    key,
                    LOGIN_RATE_LIMIT,
                    LOGIN_RATE_WINDOW,
                )
        except Exception as script_error:
            if "NOSCRIPT" in str(script_error):
                logger.debug("Lua script cache miss (sync), re-registering")
                new_sha = redis_client.script_load(RATE_LIMIT_LUA_SCRIPT)
                with _script_sha_lock:
                    _rate_limit_script_sha = new_sha
                result = redis_client.evalsha(
                    new_sha,
                    1,
                    key,
                    LOGIN_RATE_LIMIT,
                    LOGIN_RATE_WINDOW,
                )
            else:
                raise

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

    except HTTPException:
        raise  # Re-raise rate limit exceptions

    except Exception as e:
        logger.error(
            "Rate limit check failed (sync) - applying fail-closed policy",
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
