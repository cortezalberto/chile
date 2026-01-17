"""
WebSocket Gateway main application.
Handles real-time connections for waiters and kitchen staff.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.auth import verify_jwt, verify_table_token
from shared.settings import settings
from shared.logging import setup_logging, ws_gateway_logger as logger
from shared.events import close_redis_pool
from ws_gateway.connection_manager import ConnectionManager
from ws_gateway.redis_subscriber import run_subscriber
from rest_api.db import SessionLocal
from rest_api.models import WaiterSectorAssignment


# Global connection manager
manager = ConnectionManager()

# WS-CRIT-05 FIX: Maximum message size to prevent DoS attacks
# 64KB should be enough for any valid message (heartbeats, acks, etc.)
MAX_MESSAGE_SIZE = 64 * 1024  # 64KB


def _get_waiter_sector_ids_sync(user_id: int, tenant_id: int) -> list[int]:
    """
    Synchronous helper to get sector IDs assigned to a waiter.
    Used internally by get_waiter_sector_ids_async.
    """
    from rest_api.db import get_db_context

    with get_db_context() as db:
        today = date.today()
        assignments = db.execute(
            select(WaiterSectorAssignment.sector_id)
            .where(
                WaiterSectorAssignment.waiter_id == user_id,
                WaiterSectorAssignment.tenant_id == tenant_id,
                WaiterSectorAssignment.assignment_date == today,
                WaiterSectorAssignment.is_active == True,
            )
        ).scalars().all()
        return list(set(assignments))  # Unique sector IDs


# WS-CRIT-04 FIX: Timeout for DB lookup to prevent blocking event loop
DB_LOOKUP_TIMEOUT = 2.0  # seconds


async def get_waiter_sector_ids_async(user_id: int, tenant_id: int) -> list[int]:
    """
    Get the sector IDs assigned to a waiter for today (async with timeout).

    WS-CRIT-04 FIX: Uses asyncio.to_thread with timeout to prevent blocking.

    Args:
        user_id: The waiter's user ID.
        tenant_id: The tenant ID.

    Returns:
        List of sector IDs the waiter is assigned to.
    """
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_get_waiter_sector_ids_sync, user_id, tenant_id),
            timeout=DB_LOOKUP_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.error(
            "DB lookup timeout for waiter sectors",
            user_id=user_id,
            tenant_id=tenant_id,
            timeout=DB_LOOKUP_TIMEOUT
        )
        return []  # Return empty list on timeout - waiter will receive all branch events


def get_waiter_sector_ids(user_id: int, tenant_id: int) -> list[int]:
    """
    Get the sector IDs assigned to a waiter for today (sync version).

    CRIT-13 FIX: Uses context manager for proper connection handling.

    Note: Prefer get_waiter_sector_ids_async() in async context.
    """
    return _get_waiter_sector_ids_sync(user_id, tenant_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Starts Redis subscriber on startup.
    CRIT-06 FIX: Also starts heartbeat cleanup task.
    """
    # Initialize logging
    setup_logging()

    logger.info("Starting WebSocket Gateway", port=settings.ws_gateway_port, env=settings.environment)

    # Start Redis subscriber task
    subscriber_task = asyncio.create_task(start_redis_subscriber())

    # CRIT-06 FIX: Start heartbeat cleanup task
    cleanup_task = asyncio.create_task(start_heartbeat_cleanup())

    yield

    # Shutdown
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

    # BACK-HIGH-04: Close Redis connection pool on shutdown
    await close_redis_pool()
    logger.info("Redis connection pool closed")


async def start_heartbeat_cleanup():
    """
    CRIT-06 FIX: Periodically clean up stale connections.
    Runs every 30 seconds to check for connections without recent heartbeats.
    """
    while True:
        try:
            await asyncio.sleep(30)  # Check every 30 seconds
            cleaned = await manager.cleanup_stale_connections()
            if cleaned > 0:
                logger.info("Cleaned up stale connections", count=cleaned)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("Error in heartbeat cleanup", error=str(e))


async def start_redis_subscriber():
    """
    Start the Redis subscriber that dispatches events to WebSocket clients.
    """

    async def on_event(event: dict):
        """Handle incoming Redis events.

        CRIT-WS-11 FIX: Wrapped in try-except to prevent one bad event
        from breaking the subscriber loop.
        """
        try:
            branch_id = event.get("branch_id")
            session_id = event.get("session_id")
            sector_id = event.get("sector_id")
            event_type = event.get("type")

            # Dispatch to sector (waiter assignments) - takes priority over branch
            if sector_id is not None:
                sent = await manager.send_to_sector(int(sector_id), event)
                if sent > 0:
                    logger.debug(
                        "Dispatched event to sector",
                        event_type=event_type,
                        sector_id=sector_id,
                        clients=sent,
                    )

            # CRIT-WS-10 FIX: Always send to branch when branch_id present
            # Managers/admins monitoring the branch should always receive events
            if branch_id is not None:
                sent = await manager.send_to_branch(int(branch_id), event)
                if sent > 0:
                    logger.debug(
                        "Dispatched event to branch",
                        event_type=event_type,
                        branch_id=branch_id,
                        clients=sent,
                    )

            # Dispatch to session (diners)
            if session_id is not None:
                sent = await manager.send_to_session(int(session_id), event)
                if sent > 0:
                    logger.debug(
                        "Dispatched event to session",
                        event_type=event_type,
                        session_id=session_id,
                        diners=sent,
                    )
        except Exception as e:
            # CRIT-WS-11 FIX: Log but don't crash - continue processing other events
            logger.error(
                "Error processing event in on_event callback",
                event_type=event.get("type"),
                error=str(e),
                exc_info=True,
            )

    # Subscribe to all channels
    channels = [
        "branch:*:waiters",
        "branch:*:kitchen",
        "branch:*:admin",  # Dashboard/manager monitoring
        "sector:*:waiters",  # Sector-specific waiter notifications
        "session:*",
    ]

    try:
        await run_subscriber(channels, on_event)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Redis subscriber error", error=str(e), exc_info=True)


# Create FastAPI application
app = FastAPI(
    title="Integrador WebSocket Gateway",
    description="Real-time notifications for restaurant staff",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5176",
        "http://localhost:5177",
        "http://localhost:5178",  # pwaWaiter
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5176",
        "http://127.0.0.1:5177",
        "http://127.0.0.1:5178",  # pwaWaiter
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# Health Check
# =============================================================================


@app.get("/ws/health")
def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "ws-gateway",
        "environment": settings.environment,
        **manager.get_stats(),
    }


@app.get("/ws/health/detailed")
async def detailed_health_check():
    """
    Detailed health check that verifies Redis connectivity.
    """
    from shared.events import get_redis_pool

    checks = {
        "service": "ws-gateway",
        "environment": settings.environment,
        "connections": manager.get_stats(),
        "dependencies": {},
    }
    all_healthy = True

    # Check Redis
    # REDIS-01 FIX: Use pooled connection instead of creating temporary one
    try:
        redis = await get_redis_pool()
        await redis.ping()
        # Note: Don't close pooled connection - pool manages lifecycle
        checks["dependencies"]["redis"] = {"status": "healthy"}
    except Exception as e:
        checks["dependencies"]["redis"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    checks["status"] = "healthy" if all_healthy else "degraded"

    # Return 503 if Redis is down
    if not all_healthy:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=checks, status_code=503)

    return checks


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

    Waiters receive notifications about:
    - New rounds submitted
    - Rounds ready from kitchen
    - Service calls from diners
    - Check requests
    - Payment approvals

    Notifications are filtered by sector assignment when available.
    """
    # Verify JWT token
    try:
        claims = verify_jwt(token)
    except HTTPException as e:
        await websocket.close(code=4001, reason=str(e.detail))
        return

    # WS-CRIT-03 FIX: Verify token type is "access" (reject refresh tokens)
    if claims.get("type") == "refresh":
        await websocket.close(code=4001, reason="Refresh tokens cannot be used for WebSocket authentication")
        return

    # Extract user info
    user_id = int(claims["sub"])
    tenant_id = int(claims.get("tenant_id", 0))
    branch_ids = list(claims.get("branch_ids", []))
    roles = claims.get("roles", [])

    # Verify user has waiter or higher role
    if not any(role in roles for role in ["WAITER", "MANAGER", "ADMIN"]):
        await websocket.close(code=4003, reason="Insufficient role")
        return

    # WS-CRIT-04 FIX: Get today's sector assignments with timeout
    sector_ids = []
    if "WAITER" in roles:
        sector_ids = await get_waiter_sector_ids_async(user_id, tenant_id)

    # Accept and register connection with sector assignments
    await manager.connect(websocket, user_id, branch_ids, sector_ids)
    logger.info(
        "Waiter connected",
        user_id=user_id,
        branches=branch_ids,
        sectors=sector_ids,
    )

    try:
        # Keep connection alive
        while True:
            # Wait for messages from client (heartbeat, acks, etc.)
            data = await websocket.receive_text()

            # WS-CRIT-05 FIX: Validate message size to prevent DoS
            if len(data) > MAX_MESSAGE_SIZE:
                logger.warning(
                    "Message size exceeded limit from waiter",
                    user_id=user_id,
                    size=len(data),
                    max_size=MAX_MESSAGE_SIZE,
                )
                await websocket.close(code=1009, reason="Message too large")
                break

            # CRIT-06 FIX: Record heartbeat on any message
            manager.record_heartbeat(websocket)
            # Handle heartbeats
            if data == "ping" or data == '{"type":"ping"}':
                await websocket.send_text("pong")
            # Handle sector refresh request (when assignments change during shift)
            elif data == "refresh_sectors":
                # WS-HIGH-05 FIX: Re-validate token before refreshing sectors
                # This prevents abuse if token was revoked during the session
                try:
                    revalidated_claims = verify_jwt(token)
                    if revalidated_claims.get("type") == "refresh":
                        await websocket.close(code=4001, reason="Token revoked")
                        break
                except HTTPException:
                    logger.warning(
                        "Token validation failed on refresh_sectors",
                        user_id=user_id,
                    )
                    await websocket.close(code=4001, reason="Token expired or revoked")
                    break

                # WS-CRIT-04 FIX: Use async version with timeout
                new_sector_ids = await get_waiter_sector_ids_async(user_id, tenant_id)
                await manager.update_sectors(websocket, new_sector_ids)
                await websocket.send_text(f"sectors_updated:{','.join(map(str, new_sector_ids))}")
                # WS-HIGH-06 FIX: Enhanced logging for forensics
                logger.info(
                    "Waiter sectors refreshed",
                    user_id=user_id,
                    tenant_id=tenant_id,
                    sectors=new_sector_ids,
                    branches=branch_ids,
                    roles=roles,
                )
            else:
                # WS-31-MED-04 FIX: Log unknown messages for debugging
                logger.debug(
                    "Unknown message from waiter",
                    user_id=user_id,
                    message=data[:100] if len(data) > 100 else data,
                )

    except WebSocketDisconnect:
        # WS-HIGH-06 FIX: Enhanced logging for forensics
        logger.info(
            "Waiter disconnected",
            user_id=user_id,
            tenant_id=tenant_id,
            branches=branch_ids,
            sectors=sector_ids,
        )
    finally:
        await manager.disconnect(websocket)


@app.websocket("/ws/kitchen")
async def kitchen_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token"),
):
    """
    WebSocket endpoint for kitchen staff.

    Kitchen receives notifications about:
    - New rounds submitted (orders to prepare)
    """
    # Verify JWT token
    try:
        claims = verify_jwt(token)
    except HTTPException as e:
        await websocket.close(code=4001, reason=str(e.detail))
        return

    # WS-CRIT-03 FIX: Verify token type is "access" (reject refresh tokens)
    if claims.get("type") == "refresh":
        await websocket.close(code=4001, reason="Refresh tokens cannot be used for WebSocket authentication")
        return

    # Extract user info
    user_id = int(claims["sub"])
    branch_ids = list(claims.get("branch_ids", []))
    roles = claims.get("roles", [])

    # Verify user has kitchen or higher role
    if not any(role in roles for role in ["KITCHEN", "MANAGER", "ADMIN"]):
        await websocket.close(code=4003, reason="Insufficient role")
        return

    # Accept and register connection
    await manager.connect(websocket, user_id, branch_ids)
    logger.info("Kitchen connected", user_id=user_id, branches=branch_ids)

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()

            # WS-CRIT-05 FIX: Validate message size to prevent DoS
            if len(data) > MAX_MESSAGE_SIZE:
                logger.warning(
                    "Message size exceeded limit from kitchen",
                    user_id=user_id,
                    size=len(data),
                    max_size=MAX_MESSAGE_SIZE,
                )
                await websocket.close(code=1009, reason="Message too large")
                break

            # CRIT-06 FIX: Record heartbeat on any message
            manager.record_heartbeat(websocket)
            # Handle heartbeat in both plain text and JSON format
            if data == "ping":
                await websocket.send_text("pong")
            elif data == '{"type":"ping"}':
                await websocket.send_text('{"type":"pong"}')
            else:
                # WS-31-MED-04 FIX: Log unknown messages for debugging
                logger.debug(
                    "Unknown message from kitchen",
                    user_id=user_id,
                    message=data[:100] if len(data) > 100 else data,
                )

    except WebSocketDisconnect:
        # WS-HIGH-06 FIX: Enhanced logging for forensics
        logger.info(
            "Kitchen disconnected",
            user_id=user_id,
            branches=branch_ids,
            roles=roles,
        )
    finally:
        await manager.disconnect(websocket)


@app.websocket("/ws/admin")
async def admin_websocket(
    websocket: WebSocket,
    token: str = Query(..., description="JWT token"),
):
    """
    WebSocket endpoint for Dashboard/admin monitoring.

    Admins and managers receive notifications about:
    - All round events (SUBMITTED, IN_KITCHEN, READY, SERVED)
    - Service calls
    - Check requests and payments
    - Table status changes

    This allows managers to monitor the entire restaurant operation.
    """
    # Verify JWT token
    try:
        claims = verify_jwt(token)
    except HTTPException as e:
        await websocket.close(code=4001, reason=str(e.detail))
        return

    # WS-CRIT-03 FIX: Verify token type is "access" (reject refresh tokens)
    if claims.get("type") == "refresh":
        await websocket.close(code=4001, reason="Refresh tokens cannot be used for WebSocket authentication")
        return

    # Extract user info
    user_id = int(claims["sub"])
    branch_ids = list(claims.get("branch_ids", []))
    roles = claims.get("roles", [])

    # Verify user has manager or admin role
    if not any(role in roles for role in ["MANAGER", "ADMIN"]):
        await websocket.close(code=4003, reason="Insufficient role")
        return

    # Accept and register connection
    await manager.connect(websocket, user_id, branch_ids)
    logger.info("Admin connected", user_id=user_id, branches=branch_ids, roles=roles)

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()

            # WS-CRIT-05 FIX: Validate message size to prevent DoS
            if len(data) > MAX_MESSAGE_SIZE:
                logger.warning(
                    "Message size exceeded limit from admin",
                    user_id=user_id,
                    size=len(data),
                    max_size=MAX_MESSAGE_SIZE,
                )
                await websocket.close(code=1009, reason="Message too large")
                break

            # CRIT-06 FIX: Record heartbeat on any message
            manager.record_heartbeat(websocket)
            # Handle heartbeat in both plain text and JSON format
            if data == "ping":
                await websocket.send_text("pong")
            elif data == '{"type":"ping"}':
                await websocket.send_text('{"type":"pong"}')
            else:
                # WS-31-MED-04 FIX: Log unknown messages for debugging
                logger.debug(
                    "Unknown message from admin",
                    user_id=user_id,
                    message=data[:100] if len(data) > 100 else data,
                )

    except WebSocketDisconnect:
        # WS-HIGH-06 FIX: Enhanced logging for forensics
        logger.info(
            "Admin disconnected",
            user_id=user_id,
            branches=branch_ids,
            roles=roles,
        )
    finally:
        await manager.disconnect(websocket)


@app.websocket("/ws/diner")
async def diner_websocket(
    websocket: WebSocket,
    table_token: str = Query(..., description="Table session token"),
):
    """
    WebSocket endpoint for diners at a table.

    Diners receive notifications about:
    - Round status changes (IN_KITCHEN, READY, SERVED)
    - Service call acknowledgments
    - Check status updates
    """
    # Verify table token
    try:
        token_data = verify_table_token(table_token)
    except HTTPException as e:
        await websocket.close(code=4001, reason=str(e.detail))
        return

    session_id = token_data["session_id"]
    table_id = token_data["table_id"]
    branch_id = token_data["branch_id"]

    # Accept and register connection (use negative session_id as pseudo user_id)
    # This allows us to use the same ConnectionManager
    pseudo_user_id = -session_id
    await manager.connect(websocket, pseudo_user_id, [branch_id])

    # Also register by session for targeted notifications
    await manager.register_session(websocket, session_id)

    logger.info("Diner connected", session_id=session_id, table_id=table_id, branch_id=branch_id)

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()

            # WS-CRIT-05 FIX: Validate message size to prevent DoS
            if len(data) > MAX_MESSAGE_SIZE:
                logger.warning(
                    "Message size exceeded limit from diner",
                    session_id=session_id,
                    size=len(data),
                    max_size=MAX_MESSAGE_SIZE,
                )
                await websocket.close(code=1009, reason="Message too large")
                break

            # CRIT-06 FIX: Record heartbeat on any message
            manager.record_heartbeat(websocket)
            # Phase 5: Handle JSON heartbeat from frontend
            if data == "ping" or data == '{"type":"ping"}':
                await websocket.send_text('{"type":"pong"}')
            else:
                # WS-31-MED-04 FIX: Log unknown messages for debugging
                logger.debug(
                    "Unknown message from diner",
                    session_id=session_id,
                    message=data[:100] if len(data) > 100 else data,
                )

    except WebSocketDisconnect:
        # WS-HIGH-06 FIX: Enhanced logging for forensics
        logger.info(
            "Diner disconnected",
            session_id=session_id,
            table_id=table_id,
            branch_id=branch_id,
        )
    finally:
        await manager.disconnect(websocket)
        await manager.unregister_session(websocket, session_id)


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
