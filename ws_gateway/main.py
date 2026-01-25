"""
WebSocket Gateway main application.

Handles real-time connections for waiters, kitchen staff, admins, and diners.
Refactored to use extracted components for maintainability.

HIGH-03 FIX: Migrated endpoint logic to reusable WebSocketEndpointBase classes.
Eliminated ~300 lines of duplicated code across waiter, kitchen, admin, diner endpoints.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, Query
from fastapi.middleware.cors import CORSMiddleware

from shared.config.settings import settings
from shared.config.logging import setup_logging, ws_gateway_logger as logger
from shared.infrastructure.events import close_redis_pool
from ws_gateway.connection_manager import ConnectionManager
from ws_gateway.redis_subscriber import run_subscriber, get_subscriber_metrics
from ws_gateway.components.core.constants import WSConstants, DEFAULT_ALLOWED_ORIGINS
from ws_gateway.components.endpoints.handlers import (
    WaiterEndpoint,
    KitchenEndpoint,
    AdminEndpoint,
    DinerEndpoint,
)
from ws_gateway.components.data.sector_repository import cleanup_sector_repository
from ws_gateway.components.events.router import EventRouter


# Global connection manager
manager = ConnectionManager()


# =============================================================================
# Lifespan and background tasks
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Starts:
    - Redis subscriber task for event dispatching
    - Heartbeat cleanup task for stale connections
    """
    setup_logging()
    logger.info(
        "Starting WebSocket Gateway",
        port=settings.ws_gateway_port,
        env=settings.environment,
    )

    # MED-NEW-02 FIX: Added task names for easier debugging
    subscriber_task = asyncio.create_task(start_redis_subscriber(), name="redis_subscriber")
    cleanup_task = asyncio.create_task(start_heartbeat_cleanup(), name="heartbeat_cleanup")

    yield

    logger.info("Shutting down WebSocket Gateway")
    subscriber_task.cancel()
    cleanup_task.cancel()

    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    # HIGH-WS-09 FIX: Wait for pending lock cleanup tasks to complete
    try:
        await manager._lock_manager.await_pending_cleanup()
        logger.debug("Lock manager cleanup completed")
    except Exception as e:
        logger.warning("Error awaiting lock manager cleanup", error=str(e))

    # HIGH-WS-10 FIX: Clean up sector repository singleton and cache
    try:
        cleanup_sector_repository()
        logger.debug("Sector repository cleaned up")
    except Exception as e:
        logger.warning("Error cleaning up sector repository", error=str(e))

    await close_redis_pool()
    logger.info("Redis connection pool closed")


async def start_heartbeat_cleanup():
    """
    Periodically clean up stale connections and resources.

    Runs every 30 seconds to check for:
    - Connections without recent heartbeats
    - Dead connections marked during send operations
    - Stale locks for inactive branches/users
    - Rate limiter entries for disconnected connections (HIGH-04 FIX)
    """
    cleanup_cycle = 0
    while True:
        try:
            await asyncio.sleep(WSConstants.HEARTBEAT_CLEANUP_INTERVAL)
            cleanup_cycle += 1

            # Clean up stale connections (no heartbeat)
            stale_cleaned = await manager.cleanup_stale_connections()
            if stale_cleaned > 0:
                logger.info("Cleaned up stale connections", count=stale_cleaned)

            # Clean up dead connections marked during send operations
            dead_cleaned = await manager.cleanup_dead_connections()
            if dead_cleaned > 0:
                logger.info("Cleaned up dead connections", count=dead_cleaned)

            # HIGH-04 FIX: Clean up rate limiter entries for disconnected connections
            # CRIT-WS-06 FIX: Wrap with error handling to prevent cleanup loop crash
            try:
                rate_limiter_cleaned = await manager._rate_limiter.cleanup_stale()
                if rate_limiter_cleaned > 0:
                    logger.debug("Cleaned up rate limiter entries", count=rate_limiter_cleaned)
            except Exception as e:
                logger.warning("Error during rate limiter cleanup", error=str(e))

            # Clean up stale locks periodically
            if cleanup_cycle % WSConstants.LOCK_CLEANUP_CYCLE == 0:
                locks_cleaned = await manager.cleanup_locks()
                if locks_cleaned > 0:
                    logger.info("Cleaned up stale locks", count=locks_cleaned)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in heartbeat cleanup", error=str(e))


async def start_redis_subscriber():
    """
    Start the Redis subscriber that dispatches events to WebSocket clients.

    ARCH-AUDIT-03 FIX: Now uses EventRouter for explicit dependency injection
    instead of capturing 'manager' via closure.
    """
    # ARCH-AUDIT-03 FIX: Explicit dependency - EventRouter receives manager
    router = EventRouter(manager)

    async def on_event(event: dict):
        """
        Handle incoming Redis events.

        ARCH-AUDIT-03 FIX: Delegates routing to EventRouter which handles:
        - tenant_id: Filter by tenant for multi-tenant isolation
        - branch_id: Send to admins and waiters in branch
        - sector_id: Target specific sector's waiters (if present)
        - session_id: Send to diners at the table
        - Event-type based routing (kitchen events, session events, admin-only)
        """
        result = await router.route_event(event)

        if result.errors:
            logger.error(
                "Errors routing event",
                event_type=event.get("type"),
                errors=result.errors,
            )
        elif result.total_sent == 0:
            logger.debug(
                "Event routed but no recipients",
                event_type=event.get("type"),
            )

    channels = [
        "branch:*:waiters",
        "branch:*:kitchen",
        "branch:*:admin",
        "sector:*:waiters",
        "session:*",
    ]

    try:
        await run_subscriber(channels, on_event)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Redis subscriber error", error=str(e), exc_info=True)


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Integrador WebSocket Gateway",
    description="Real-time notifications for restaurant staff",
    version="0.2.0",
    lifespan=lifespan,
)

# CORS configuration
# MED-NEW-04 FIX: Use shared DEFAULT_ALLOWED_ORIGINS from constants
# Add HTTPS variants for production
DEFAULT_WS_ORIGINS = list(DEFAULT_ALLOWED_ORIGINS) + [
    origin.replace("http://", "https://") for origin in DEFAULT_ALLOWED_ORIGINS
]

ws_allowed_origins = (
    [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    if settings.allowed_origins
    else DEFAULT_WS_ORIGINS
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ws_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Table-Token"],
)


# =============================================================================
# Health Check
# =============================================================================


@app.get("/ws/health")
def health_check():
    """Basic health check endpoint."""
    # LOW-NEW-03 FIX: Include version in health response
    # CRIT-WS-06 FIX: Wrap sync method call with error handling
    try:
        stats = manager.get_stats_sync()
    except Exception as e:
        logger.warning("Failed to get stats in health check", error=str(e))
        stats = {"error": "stats_unavailable"}
    return {
        "status": "healthy",
        "service": "ws-gateway",
        "version": app.version,
        "environment": settings.environment,
        **stats,
    }


@app.get("/ws/health/detailed")
async def detailed_health_check():
    """Detailed health check with Redis and component status."""
    from shared.infrastructure.events import check_redis_async_health, check_redis_sync_health

    stats = await manager.get_stats()
    checks = {
        "service": "ws-gateway",
        "environment": settings.environment,
        "connections": stats,
        "dependencies": {},
        "subscriber_metrics": get_subscriber_metrics(),
    }
    all_healthy = True

    # Check async Redis pool
    async_health = await check_redis_async_health()
    checks["dependencies"]["redis_async"] = async_health
    if async_health["status"] != "healthy":
        all_healthy = False

    # Check sync Redis client
    sync_health = check_redis_sync_health()
    checks["dependencies"]["redis_sync"] = sync_health
    if sync_health["status"] != "healthy":
        all_healthy = False

    checks["status"] = "healthy" if all_healthy else "degraded"

    if not all_healthy:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=checks, status_code=503)

    return checks


# =============================================================================
# Prometheus Metrics Endpoint
# =============================================================================


@app.get("/ws/metrics")
async def prometheus_metrics():
    """
    Prometheus-compatible metrics endpoint.

    ARCH-OPP-07 FIX: Exposes metrics in Prometheus exposition format.

    Usage:
        curl http://localhost:8001/ws/metrics

    Configure Prometheus scrape:
        scrape_configs:
          - job_name: 'ws-gateway'
            static_configs:
              - targets: ['localhost:8001']
            metrics_path: '/ws/metrics'
    """
    from fastapi.responses import PlainTextResponse
    from ws_gateway.components.metrics.prometheus import generate_prometheus_metrics

    metrics_output = await generate_prometheus_metrics(manager)
    return PlainTextResponse(
        content=metrics_output,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


# =============================================================================
# WebSocket Endpoints
# =============================================================================


@app.websocket("/ws/waiter")
async def waiter_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token"),
):
    """
    WebSocket endpoint for waiters.

    HIGH-03 FIX: Migrated to WaiterEndpoint class.
    """
    endpoint = WaiterEndpoint(websocket, manager, token)
    await endpoint.run()


@app.websocket("/ws/kitchen")
async def kitchen_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token"),
):
    """
    WebSocket endpoint for kitchen staff.

    HIGH-03 FIX: Migrated to KitchenEndpoint class.
    """
    endpoint = KitchenEndpoint(websocket, manager, token)
    await endpoint.run()


@app.websocket("/ws/admin")
async def admin_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token"),
):
    """
    WebSocket endpoint for Dashboard/admin monitoring.

    HIGH-03 FIX: Migrated to AdminEndpoint class.
    """
    endpoint = AdminEndpoint(websocket, manager, token)
    await endpoint.run()


@app.websocket("/ws/diner")
async def diner_websocket(
    websocket: WebSocket,
    table_token: str = Query(..., description="Table session token"),
):
    """
    WebSocket endpoint for diners at a table.

    HIGH-03 FIX: Migrated to DinerEndpoint class.
    """
    endpoint = DinerEndpoint(websocket, manager, table_token)
    await endpoint.run()


# =============================================================================
# Development entry point
# =============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "ws_gateway.main:app",
        host="0.0.0.0",
        port=settings.ws_gateway_port,
        reload=True,
    )
