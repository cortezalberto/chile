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


def get_waiter_sector_ids(user_id: int, tenant_id: int) -> list[int]:
    """
    Get the sector IDs assigned to a waiter for today.

    Args:
        user_id: The waiter's user ID.
        tenant_id: The tenant ID.

    Returns:
        List of sector IDs the waiter is assigned to.
    """
    db: Session = SessionLocal()
    try:
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
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.
    Starts Redis subscriber on startup.
    """
    # Initialize logging
    setup_logging()

    logger.info("Starting WebSocket Gateway", port=settings.ws_gateway_port, env=settings.environment)

    # Start Redis subscriber task
    subscriber_task = asyncio.create_task(start_redis_subscriber())

    yield

    # Shutdown
    logger.info("Shutting down WebSocket Gateway")
    subscriber_task.cancel()
    try:
        await subscriber_task
    except asyncio.CancelledError:
        pass

    # BACK-HIGH-04: Close Redis connection pool on shutdown
    await close_redis_pool()
    logger.info("Redis connection pool closed")


async def start_redis_subscriber():
    """
    Start the Redis subscriber that dispatches events to WebSocket clients.
    """

    async def on_event(event: dict):
        """Handle incoming Redis events."""
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
            # Also send to branch for managers/admins who may not be assigned to sectors
            if branch_id is not None:
                # But exclude those who already received via sector
                # For simplicity, send to branch anyway - clients can dedupe
                pass

        # Dispatch to branch (waiters/kitchen) - fallback when no sector specified
        if branch_id is not None and sector_id is None:
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
    import redis.asyncio as aioredis

    checks = {
        "service": "ws-gateway",
        "environment": settings.environment,
        "connections": manager.get_stats(),
        "dependencies": {},
    }
    all_healthy = True

    # Check Redis
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        await redis_client.close()
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

    # Extract user info
    user_id = int(claims["sub"])
    tenant_id = int(claims.get("tenant_id", 0))
    branch_ids = list(claims.get("branch_ids", []))
    roles = claims.get("roles", [])

    # Verify user has waiter or higher role
    if not any(role in roles for role in ["WAITER", "MANAGER", "ADMIN"]):
        await websocket.close(code=4003, reason="Insufficient role")
        return

    # Get today's sector assignments for the waiter
    sector_ids = []
    if "WAITER" in roles:
        sector_ids = get_waiter_sector_ids(user_id, tenant_id)

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
            # Handle heartbeats
            if data == "ping":
                await websocket.send_text("pong")
            # Handle sector refresh request (when assignments change during shift)
            elif data == "refresh_sectors":
                new_sector_ids = get_waiter_sector_ids(user_id, tenant_id)
                manager.update_sectors(websocket, new_sector_ids)
                await websocket.send_text(f"sectors_updated:{','.join(map(str, new_sector_ids))}")
                logger.info(
                    "Waiter sectors refreshed",
                    user_id=user_id,
                    sectors=new_sector_ids,
                )

    except WebSocketDisconnect:
        logger.info("Waiter disconnected", user_id=user_id)
    finally:
        manager.disconnect(websocket)


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
            # Handle heartbeat in both plain text and JSON format
            if data == "ping":
                await websocket.send_text("pong")
            elif data == '{"type":"ping"}':
                await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:
        logger.info("Kitchen disconnected", user_id=user_id)
    finally:
        manager.disconnect(websocket)


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
            # Handle heartbeat in both plain text and JSON format
            if data == "ping":
                await websocket.send_text("pong")
            elif data == '{"type":"ping"}':
                await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:
        logger.info("Admin disconnected", user_id=user_id)
    finally:
        manager.disconnect(websocket)


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
    manager.register_session(websocket, session_id)

    logger.info("Diner connected", session_id=session_id, table_id=table_id, branch_id=branch_id)

    try:
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Phase 5: Handle JSON heartbeat from frontend
            if data == "ping" or data == '{"type":"ping"}':
                await websocket.send_text('{"type":"pong"}')

    except WebSocketDisconnect:
        logger.info("Diner disconnected", session_id=session_id)
    finally:
        manager.disconnect(websocket)
        manager.unregister_session(websocket, session_id)


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
