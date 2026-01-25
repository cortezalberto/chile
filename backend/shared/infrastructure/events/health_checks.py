"""
Redis Health Check Functions.

REDIS-CRIT-04 FIX: Health check support for monitoring.
ARCH-OPP-03 FIX: Uses standardized health check decorators.
"""

from __future__ import annotations

from typing import Any

from shared.config.settings import settings
from shared.utils.health import (
    health_check_with_timeout,
    sync_health_check_with_timeout,
    HealthCheckResult,
)
from .redis_pool import get_redis_pool, get_redis_sync_client, _get_redis_sync_pool


@health_check_with_timeout(timeout=3.0, component="redis_async")
async def check_redis_async_health() -> dict[str, Any]:
    """
    Check health of async Redis pool.

    ARCH-OPP-03 FIX: Now uses health_check_with_timeout decorator for consistent
    timeout handling and response formatting.

    Returns dict with pool details (wrapped in HealthCheckResult by decorator).
    """
    pool = await get_redis_pool()
    await pool.ping()
    return {"type": "async", "max_connections": settings.redis_pool_max_connections}


@sync_health_check_with_timeout(timeout=3.0, component="redis_sync")
def check_redis_sync_health() -> dict[str, Any]:
    """
    LOAD-LEVEL2: Check health of sync Redis pool.

    ARCH-OPP-03 FIX: Now uses sync_health_check_with_timeout decorator for
    consistent timeout handling and response formatting.

    Returns dict with pool info (wrapped in HealthCheckResult by decorator).
    """
    client = get_redis_sync_client()
    client.ping()
    # Get pool stats if available
    pool = _get_redis_sync_pool()
    return {
        "type": "sync_pool",
        "max_connections": pool.max_connections,
    }


# =============================================================================
# Legacy functions for backward compatibility
# =============================================================================


async def check_redis_async_health_legacy() -> dict[str, Any]:
    """Legacy health check - use check_redis_async_health() instead."""
    result = await check_redis_async_health()
    return result.to_dict() if isinstance(result, HealthCheckResult) else result


def check_redis_sync_health_legacy() -> dict[str, Any]:
    """Legacy health check - use check_redis_sync_health() instead."""
    result = check_redis_sync_health()
    return result.to_dict() if isinstance(result, HealthCheckResult) else result
