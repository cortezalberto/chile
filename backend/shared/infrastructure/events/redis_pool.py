"""
Redis Connection Pool Management.

REDIS-CRIT-02/HIGH-02 FIX: Unified configuration from settings.
LOAD-LEVEL2: Supports high concurrency with separate sync pool.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING

import redis.asyncio as redis

from shared.config.settings import settings, REDIS_URL
from shared.config.logging import get_logger

if TYPE_CHECKING:
    import redis as redis_sync

logger = get_logger(__name__)


# =============================================================================
# Async Redis Pool
# =============================================================================

# Global Redis connection pool singleton (async)
_redis_pool: redis.Redis | None = None
_redis_pool_lock: asyncio.Lock | None = None
_pool_lock_init = threading.Lock()


def _get_pool_lock() -> asyncio.Lock:
    """
    Get or create the pool lock (lazy initialization for event loop safety).

    Uses threading.Lock with double-check pattern to prevent race condition
    where multiple coroutines could create different asyncio.Lock instances.
    """
    global _redis_pool_lock
    if _redis_pool_lock is None:
        with _pool_lock_init:
            if _redis_pool_lock is None:
                _redis_pool_lock = asyncio.Lock()
    return _redis_pool_lock


async def get_redis_pool() -> redis.Redis:
    """
    Get or create the Redis connection pool singleton.

    REDIS-MED-03/HIGH-02 FIX: Uses configurable values from settings.
    """
    global _redis_pool

    # Fast path: pool already initialized
    if _redis_pool is not None:
        return _redis_pool

    # Slow path: acquire lock and initialize if needed
    async with _get_pool_lock():
        # Double-check after acquiring lock (another coroutine may have initialized)
        if _redis_pool is None:
            _redis_pool = redis.from_url(
                REDIS_URL,
                max_connections=settings.redis_pool_max_connections,
                decode_responses=True,
                socket_connect_timeout=settings.redis_socket_timeout,
                socket_timeout=settings.redis_socket_timeout,
                health_check_interval=30,  # PERF-MED-02 FIX: Auto-detect dead connections
            )
            logger.info(
                "Redis async pool initialized",
                max_connections=settings.redis_pool_max_connections,
                timeout=settings.redis_socket_timeout,
            )
    return _redis_pool


async def get_redis_client() -> redis.Redis:
    """
    Get an async Redis client.

    REDIS-MED-01 FIX: Deprecated - use get_redis_pool() instead.
    This function now returns the pooled connection for backward compatibility.
    Callers should migrate to get_redis_pool() directly.
    """
    return await get_redis_pool()


# =============================================================================
# Sync Redis Pool (LOAD-LEVEL2)
# =============================================================================

# LOAD-LEVEL2: Sync Redis connection POOL (not singleton) for high concurrency
_redis_sync_pool = None
_sync_pool_lock = threading.Lock()


def _get_redis_sync_pool() -> "redis_sync.ConnectionPool":
    """
    LOAD-LEVEL2: Get or create synchronous Redis connection POOL.

    Uses a connection pool instead of a single client to support
    high concurrency in sync operations (token blacklist, rate limiting).

    LOW-WS-03 FIX: Added return type hint.
    """
    import redis as redis_sync  # LOW-WS-02 FIX: Import at top of function body
    global _redis_sync_pool
    if _redis_sync_pool is None:
        with _sync_pool_lock:
            if _redis_sync_pool is None:
                _redis_sync_pool = redis_sync.ConnectionPool.from_url(
                    REDIS_URL,
                    max_connections=settings.redis_sync_pool_max_connections,
                    decode_responses=True,
                    socket_connect_timeout=settings.redis_socket_timeout,
                    socket_timeout=settings.redis_socket_timeout,
                    health_check_interval=30,  # PERF-MED-02 FIX: Auto-detect dead connections
                )
                logger.info(
                    "Redis sync pool initialized",
                    max_connections=settings.redis_sync_pool_max_connections,
                    timeout=settings.redis_socket_timeout,
                )
    return _redis_sync_pool


def get_redis_sync_client() -> "redis_sync.Redis":
    """
    LOAD-LEVEL2: Get a Redis client from the sync connection pool.

    Each call returns a client backed by the shared pool, allowing
    multiple concurrent sync operations without blocking each other.

    LOW-WS-03 FIX: Added return type hint.
    """
    import redis as redis_sync  # Import here for type hint resolution
    pool = _get_redis_sync_pool()
    return redis_sync.Redis(connection_pool=pool)


# =============================================================================
# Cleanup functions
# =============================================================================


def close_redis_sync_client() -> None:
    """
    LOAD-LEVEL2: Close sync Redis connection pool on application shutdown.

    CRIT-04 FIX: Thread-safe close operation.
    Uses _sync_pool_lock to prevent race condition when multiple threads
    call close simultaneously or during concurrent get_redis_sync_client() calls.
    """
    global _redis_sync_pool
    with _sync_pool_lock:
        if _redis_sync_pool is not None:
            try:
                _redis_sync_pool.disconnect()
                logger.info("Redis sync pool closed")
            except Exception as e:
                logger.warning("Error closing Redis sync pool", error=str(e))
            finally:
                # CRIT-04 FIX: Always set to None in finally block
                _redis_sync_pool = None


async def close_redis_pool() -> None:
    """
    Close all Redis connections on application shutdown.

    REDIS-CRIT-03 FIX: Now also closes the sync client for proper cleanup.
    """
    global _redis_pool, _redis_pool_lock

    # Close async pool
    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None
        logger.info("Redis async pool closed")
    _redis_pool_lock = None

    # REDIS-CRIT-03 FIX: Also close sync client
    close_redis_sync_client()
