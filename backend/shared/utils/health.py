"""
Health Check Utilities.

ARCH-OPP-03: Provides decorators and utilities for health checks with
consistent timeout handling and response formatting.

Usage:
    from shared.utils.health import health_check_with_timeout, HealthStatus

    @health_check_with_timeout(timeout=3.0)
    async def check_redis():
        await redis.ping()
        return {"latency_ms": 5}

    # Returns: {"status": "healthy", "latency_ms": 5}
    # On timeout: {"status": "unhealthy", "error": "timeout after 3.0s"}
"""

from __future__ import annotations

import asyncio
import functools
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar

from shared.config.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class HealthStatus(str, Enum):
    """Health check status values."""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"


@dataclass
class HealthCheckResult:
    """
    Result of a health check operation.

    Provides consistent structure for all health check responses.
    """
    status: HealthStatus
    component: str
    latency_ms: float | None = None
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result = {
            "status": self.status.value,
            "component": self.component,
        }
        if self.latency_ms is not None:
            result["latency_ms"] = round(self.latency_ms, 2)
        if self.error:
            result["error"] = self.error
        if self.details:
            result["details"] = self.details
        return result


def health_check_with_timeout(
    timeout: float = 5.0,
    component: str | None = None,
):
    """
    Decorator for health check functions with timeout protection.

    ARCH-OPP-03: Ensures consistent timeout handling across all health checks.

    Args:
        timeout: Maximum time to wait for health check (seconds).
        component: Component name for logging (defaults to function name).

    Returns:
        Decorated function that returns HealthCheckResult.

    Usage:
        @health_check_with_timeout(timeout=3.0, component="redis")
        async def check_redis_health():
            await redis.ping()
            return {"pool_size": 10}  # Optional details

        result = await check_redis_health()
        # Returns: HealthCheckResult(status=HEALTHY, component="redis", latency_ms=5.2, details={"pool_size": 10})
    """
    def decorator(
        func: Callable[..., Coroutine[Any, Any, dict[str, Any] | None]]
    ) -> Callable[..., Coroutine[Any, Any, HealthCheckResult]]:
        comp_name = component or func.__name__.replace("check_", "").replace("_health", "")

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> HealthCheckResult:
            start_time = time.perf_counter()
            try:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout,
                )
                latency_ms = (time.perf_counter() - start_time) * 1000
                details = result if isinstance(result, dict) else {}

                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    component=comp_name,
                    latency_ms=latency_ms,
                    details=details,
                )
            except asyncio.TimeoutError:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "Health check timeout",
                    component=comp_name,
                    timeout=timeout,
                    latency_ms=latency_ms,
                )
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    component=comp_name,
                    latency_ms=latency_ms,
                    error=f"timeout after {timeout}s",
                )
            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "Health check failed",
                    component=comp_name,
                    error=str(e),
                    latency_ms=latency_ms,
                )
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    component=comp_name,
                    latency_ms=latency_ms,
                    error=str(e),
                )

        return wrapper
    return decorator


def sync_health_check_with_timeout(
    timeout: float = 5.0,
    component: str | None = None,
):
    """
    Decorator for synchronous health check functions with timeout protection.

    Similar to health_check_with_timeout but for sync functions.
    Uses threading for timeout (sync functions can't use asyncio.wait_for).

    Args:
        timeout: Maximum time to wait for health check (seconds).
        component: Component name for logging.

    Returns:
        Decorated function that returns HealthCheckResult.
    """
    import concurrent.futures

    def decorator(
        func: Callable[..., dict[str, Any] | None]
    ) -> Callable[..., HealthCheckResult]:
        comp_name = component or func.__name__.replace("check_", "").replace("_health", "")

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> HealthCheckResult:
            start_time = time.perf_counter()
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(func, *args, **kwargs)
                    result = future.result(timeout=timeout)

                latency_ms = (time.perf_counter() - start_time) * 1000
                details = result if isinstance(result, dict) else {}

                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    component=comp_name,
                    latency_ms=latency_ms,
                    details=details,
                )
            except concurrent.futures.TimeoutError:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "Sync health check timeout",
                    component=comp_name,
                    timeout=timeout,
                )
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    component=comp_name,
                    latency_ms=latency_ms,
                    error=f"timeout after {timeout}s",
                )
            except Exception as e:
                latency_ms = (time.perf_counter() - start_time) * 1000
                logger.warning(
                    "Sync health check failed",
                    component=comp_name,
                    error=str(e),
                )
                return HealthCheckResult(
                    status=HealthStatus.UNHEALTHY,
                    component=comp_name,
                    latency_ms=latency_ms,
                    error=str(e),
                )

        return wrapper
    return decorator


async def aggregate_health_checks(
    checks: list[Coroutine[Any, Any, HealthCheckResult]],
) -> dict[str, Any]:
    """
    Run multiple health checks concurrently and aggregate results.

    Args:
        checks: List of health check coroutines to run.

    Returns:
        Aggregated health status with individual component results.

    Usage:
        result = await aggregate_health_checks([
            check_redis_health(),
            check_database_health(),
        ])
        # Returns: {
        #     "status": "healthy",  # or "degraded" if any unhealthy
        #     "components": {
        #         "redis": {"status": "healthy", "latency_ms": 5.2},
        #         "database": {"status": "healthy", "latency_ms": 12.1},
        #     }
        # }
    """
    results = await asyncio.gather(*checks, return_exceptions=True)

    components: dict[str, dict] = {}
    all_healthy = True

    for result in results:
        if isinstance(result, HealthCheckResult):
            components[result.component] = result.to_dict()
            if result.status != HealthStatus.HEALTHY:
                all_healthy = False
        elif isinstance(result, Exception):
            # Handle unexpected exceptions
            components["unknown"] = {
                "status": HealthStatus.UNHEALTHY.value,
                "error": str(result),
            }
            all_healthy = False

    return {
        "status": HealthStatus.HEALTHY.value if all_healthy else HealthStatus.DEGRADED.value,
        "components": components,
    }
