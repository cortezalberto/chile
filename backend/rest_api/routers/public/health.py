"""
Health check endpoints for the REST API.
Provides basic and detailed health status of the service and its dependencies.

ARCH-OPP-03 FIX: Uses standardized health check utilities for consistent response format.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from shared.config.settings import settings
from shared.infrastructure.db import SessionLocal
from shared.infrastructure.events import (
    check_redis_async_health,
    check_redis_sync_health,
)
from shared.utils.health import (
    HealthStatus,
    HealthCheckResult,
    health_check_with_timeout,
    aggregate_health_checks,
)
from rest_api.services.payments.webhook_retry import webhook_retry_queue
from rest_api.services.payments.circuit_breaker import get_all_breaker_stats


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check():
    """
    Basic health check endpoint.
    Returns service status without checking dependencies.
    """
    return {
        "status": "healthy",
        "service": "rest-api",
        "environment": settings.environment,
    }


@health_check_with_timeout(timeout=3.0, component="postgresql")
async def check_postgresql_health() -> dict:
    """Check PostgreSQL connectivity."""
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"type": "postgresql"}


@router.get("/health/detailed")
async def detailed_health_check():
    """
    Detailed health check that verifies connectivity to dependencies.
    Returns status of PostgreSQL and Redis connections.

    ARCH-OPP-03 FIX: Uses standardized health check utilities for consistent
    response format and timeout handling.

    Returns 503 Service Unavailable if any dependency is down.
    """
    # Run health checks concurrently using standardized utilities
    health_results = await aggregate_health_checks([
        check_postgresql_health(),
        check_redis_async_health(),
    ])

    # Also get sync Redis health (run in thread pool)
    sync_redis_result = check_redis_sync_health()

    # Build response
    checks = {
        "service": "rest-api",
        "environment": settings.environment,
        "status": health_results["status"],
        "dependencies": health_results["components"],
    }

    # Add sync Redis result to components
    checks["dependencies"]["redis_sync"] = sync_redis_result.to_dict()

    # Include circuit breaker and webhook retry stats
    checks["circuit_breakers"] = get_all_breaker_stats()
    checks["webhook_retry"] = await webhook_retry_queue.get_stats()

    # Determine overall health status
    all_healthy = all(
        comp.get("status") == HealthStatus.HEALTHY.value
        for comp in checks["dependencies"].values()
    )
    checks["status"] = HealthStatus.HEALTHY.value if all_healthy else HealthStatus.DEGRADED.value

    # Return 503 if any dependency is down
    if not all_healthy:
        return JSONResponse(content=checks, status_code=503)

    return checks
