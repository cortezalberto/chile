"""
WebSocket Connection Manager.

Thin orchestrator that composes modular components for connection management.

ARCH-MODULAR-08: Refactored to use composition pattern.
Original monolithic class split into:
- ConnectionLifecycle: Connect/disconnect logic
- ConnectionBroadcaster: Message broadcasting
- ConnectionCleanup: Stale/dead connection cleanup
- ConnectionStats: Statistics aggregation

This file maintains backward compatibility while delegating to modules.
"""

from __future__ import annotations

import asyncio
import logging
from types import MappingProxyType
from typing import Any, TYPE_CHECKING

from shared.config.settings import settings
from ws_gateway.components.core.constants import (
    WSCloseCode,
    WSConstants,
)
from ws_gateway.components.connection.locks import LockManager
from ws_gateway.components.metrics.collector import MetricsCollector
from ws_gateway.components.connection.heartbeat import HeartbeatTracker, handle_heartbeat
from ws_gateway.components.connection.rate_limiter import WebSocketRateLimiter
from ws_gateway.components.core.context import sanitize_log_data
from ws_gateway.components.connection.index import ConnectionIndex

# Import modular components
from ws_gateway.core.connection import (
    ConnectionLifecycle,
    ConnectionBroadcaster,
    ConnectionCleanup,
    ConnectionStats,
    is_ws_connected,
)

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Legacy re-exports for backward compatibility
# DEPRECATED: Import directly from ws_gateway.components.core.constants instead
WS_CLOSE_NORMAL = WSCloseCode.NORMAL
WS_CLOSE_GOING_AWAY = WSCloseCode.GOING_AWAY
WS_CLOSE_MESSAGE_TOO_BIG = WSCloseCode.MESSAGE_TOO_BIG
WS_CLOSE_POLICY_VIOLATION = WSCloseCode.POLICY_VIOLATION
WS_CLOSE_SERVER_OVERLOADED = WSCloseCode.SERVER_OVERLOADED
WS_CLOSE_AUTH_FAILED = WSCloseCode.AUTH_FAILED
WS_CLOSE_FORBIDDEN = WSCloseCode.FORBIDDEN
WS_CLOSE_RATE_LIMITED = WSCloseCode.RATE_LIMITED

__all__ = [
    "ConnectionManager",
    "WSCloseCode",
    "handle_heartbeat",
    "sanitize_log_data",
    "is_ws_connected",
    # DEPRECATED legacy exports
    "WS_CLOSE_NORMAL",
    "WS_CLOSE_GOING_AWAY",
    "WS_CLOSE_MESSAGE_TOO_BIG",
    "WS_CLOSE_POLICY_VIOLATION",
    "WS_CLOSE_SERVER_OVERLOADED",
    "WS_CLOSE_AUTH_FAILED",
    "WS_CLOSE_FORBIDDEN",
    "WS_CLOSE_RATE_LIMITED",
]


class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.

    Composes modular components for specific responsibilities:
    - ConnectionLifecycle: Connect/disconnect operations
    - ConnectionBroadcaster: Message broadcasting
    - ConnectionCleanup: Stale/dead connection cleanup
    - ConnectionStats: Statistics aggregation

    Configuration from settings:
    - ws_max_connections_per_user: Max connections per user (default: 3)
    - ws_max_total_connections: Global connection limit (default: 1000)
    - ws_broadcast_batch_size: Parallel broadcast batch size (default: 50)
    - ws_heartbeat_timeout: Seconds before connection is stale (default: 60)
    - ws_message_rate_limit: Max messages per second (default: 20)

    Lock Ordering (to prevent deadlocks):
    1. connection_counter_lock (global)
    2. user_lock (per-user, ascending user_id)
    3. branch_locks (per-branch, ascending branch_id)
    4. sector_lock (global)
    5. session_lock (global)
    6. dead_connections_lock (global)
    """

    # Configuration from settings
    HEARTBEAT_TIMEOUT = settings.ws_heartbeat_timeout
    MAX_CONNECTIONS_PER_USER = settings.ws_max_connections_per_user
    MAX_TOTAL_CONNECTIONS = settings.ws_max_total_connections
    BROADCAST_BATCH_SIZE = settings.ws_broadcast_batch_size
    MAX_MESSAGE_SIZE = settings.ws_max_message_size

    def __init__(self) -> None:
        """Initialize the connection manager with composed components."""
        # Core components
        self._lock_manager = LockManager()
        self._metrics = MetricsCollector()
        self._heartbeat_tracker = HeartbeatTracker(timeout_seconds=self.HEARTBEAT_TIMEOUT)
        self._rate_limiter = WebSocketRateLimiter(
            max_messages=settings.ws_message_rate_limit,
            window_seconds=settings.ws_message_rate_window,
        )
        self._index = ConnectionIndex()

        # Lifecycle component
        self._lifecycle = ConnectionLifecycle(
            lock_manager=self._lock_manager,
            metrics=self._metrics,
            heartbeat_tracker=self._heartbeat_tracker,
            rate_limiter=self._rate_limiter,
            index=self._index,
            max_connections_per_user=self.MAX_CONNECTIONS_PER_USER,
            max_total_connections=self.MAX_TOTAL_CONNECTIONS,
        )

        # Cleanup component (needs disconnect callback)
        self._cleanup = ConnectionCleanup(
            lock_manager=self._lock_manager,
            metrics=self._metrics,
            heartbeat_tracker=self._heartbeat_tracker,
            index=self._index,
            disconnect_callback=self._lifecycle.disconnect,
        )

        # Broadcaster component (needs mark_dead callback)
        self._broadcaster = ConnectionBroadcaster(
            lock_manager=self._lock_manager,
            index=self._index,
            metrics=self._metrics,
            mark_dead_callback=self._cleanup.mark_dead_connection,
            batch_size=self.BROADCAST_BATCH_SIZE,
        )

        # Stats component
        self._stats = ConnectionStats(
            lock_manager=self._lock_manager,
            metrics=self._metrics,
            heartbeat_tracker=self._heartbeat_tracker,
            rate_limiter=self._rate_limiter,
            index=self._index,
            get_total_connections=lambda: self._lifecycle.total_connections,
            get_dead_connections_count=lambda: self._cleanup.dead_connections_count,
            max_total_connections=self.MAX_TOTAL_CONNECTIONS,
        )

    # =========================================================================
    # Public properties (delegate to index)
    # =========================================================================

    @property
    def by_user(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by user ID."""
        return self._index.by_user

    @property
    def by_branch(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by branch ID."""
        return self._index.by_branch

    @property
    def by_session(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by session ID."""
        return self._index.by_session

    @property
    def by_sector(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by sector ID."""
        return self._index.by_sector

    @property
    def admins_by_branch(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Admin connections indexed by branch ID."""
        return self._index.admins_by_branch

    @property
    def total_connections(self) -> int:
        """Total number of active connections."""
        return self._lifecycle.total_connections

    # =========================================================================
    # SCALE-HIGH-01: Broadcast Worker Pool
    # =========================================================================

    async def start_broadcast_workers(self) -> None:
        """
        SCALE-HIGH-01 FIX: Start broadcast worker pool.
        
        Call this during application startup (lifespan) to enable
        parallel broadcast processing for high-throughput scenarios.
        """
        await self._broadcaster.start_workers()

    async def stop_broadcast_workers(self, timeout: float = 5.0) -> None:
        """
        SCALE-HIGH-01 FIX: Stop broadcast worker pool.
        
        Call this during application shutdown. Waits for pending
        broadcasts to complete or timeout.
        """
        await self._broadcaster.stop_workers(timeout=timeout)

    # =========================================================================
    # Rate limiting (delegate to rate_limiter)
    # =========================================================================

    async def check_rate_limit(self, ws: "WebSocket") -> bool:
        """Check if a message from this connection is allowed."""
        return await self._rate_limiter.is_allowed(ws)

    def record_rate_limit_rejection(self) -> None:
        """Record a rate limit rejection metric."""
        self._metrics.increment_connection_rejected_rate_limit_sync()

    # =========================================================================
    # Connection management (delegate to lifecycle)
    # =========================================================================

    async def connect(
        self,
        websocket: "WebSocket",
        user_id: int,
        branch_ids: list[int],
        sector_ids: list[int] | None = None,
        is_admin: bool = False,
        is_kitchen: bool = False,
        timeout: float = WSConstants.WS_ACCEPT_TIMEOUT,
        tenant_id: int | None = None,
    ) -> None:
        """Accept and register a new WebSocket connection."""
        await self._lifecycle.connect(
            websocket=websocket,
            user_id=user_id,
            branch_ids=branch_ids,
            sector_ids=sector_ids,
            is_admin=is_admin,
            is_kitchen=is_kitchen,
            timeout=timeout,
            tenant_id=tenant_id,
        )

    async def disconnect(self, websocket: "WebSocket") -> None:
        """Remove a WebSocket connection from all registrations."""
        await self._lifecycle.disconnect(websocket)

    # =========================================================================
    # Session management (delegate to index with locking)
    # =========================================================================

    async def register_session(self, websocket: "WebSocket", session_id: int) -> None:
        """Register a WebSocket connection to a table session."""
        async with self._lock_manager.session_lock:
            self._index.register_session(websocket, session_id)

    async def unregister_session(self, websocket: "WebSocket", session_id: int) -> None:
        """Unregister a WebSocket connection from a table session."""
        async with self._lock_manager.session_lock:
            self._index.unregister_session(websocket, session_id)

    # =========================================================================
    # Sector management (delegate to index with locking)
    # =========================================================================

    async def update_sectors(self, websocket: "WebSocket", sector_ids: list[int]) -> None:
        """Update sector assignments for a WebSocket connection."""
        if not isinstance(sector_ids, list):
            raise ValueError("sector_ids must be a list")
        for sector_id in sector_ids:
            if not isinstance(sector_id, int) or sector_id <= 0:
                raise ValueError(f"Invalid sector_id: {sector_id}")

        # Log warning when clearing all sectors
        if not sector_ids:
            user_id = self._index.get_user_id(websocket) or "unknown"
            old_sectors = self._index.get_sector_ids(websocket)
            if old_sectors:
                logger.warning(
                    "Clearing all sector assignments for connection",
                    user_id=user_id,
                    old_sectors=old_sectors,
                )

        async with self._lock_manager.sector_lock:
            self._index.update_sectors(websocket, sector_ids)

    def get_sectors(self, websocket: "WebSocket") -> list[int]:
        """Get the sector IDs assigned to a WebSocket connection."""
        return self._index.get_sector_ids(websocket)

    def get_tenant_id(self, websocket: "WebSocket") -> int | None:
        """Get the tenant ID for a WebSocket connection."""
        return self._index.get_tenant_id(websocket)

    def _filter_by_tenant(
        self,
        connections: list["WebSocket"],
        tenant_id: int | None,
    ) -> list["WebSocket"]:
        """Filter connections to only those belonging to the specified tenant."""
        return self._index.filter_by_tenant(connections, tenant_id)

    # =========================================================================
    # Heartbeat tracking (delegate to cleanup)
    # =========================================================================

    async def record_heartbeat(self, websocket: "WebSocket") -> None:
        """Record a heartbeat from a connection."""
        await self._cleanup.record_heartbeat(websocket)

    async def get_stale_connections(self) -> list["WebSocket"]:
        """Get connections that haven't sent a heartbeat within timeout."""
        return await self._cleanup.get_stale_connections()

    async def cleanup_stale_connections(self) -> int:
        """Close and remove stale connections."""
        return await self._cleanup.cleanup_stale_connections()

    # =========================================================================
    # Dead connection management (delegate to cleanup)
    # =========================================================================

    async def _mark_dead_connection(self, ws: "WebSocket") -> None:
        """Mark a connection as dead for async cleanup."""
        await self._cleanup.mark_dead_connection(ws)

    async def cleanup_dead_connections(self) -> int:
        """Clean up connections marked as dead during send operations."""
        return await self._cleanup.cleanup_dead_connections()

    # =========================================================================
    # Lock cleanup (delegate to cleanup)
    # =========================================================================

    async def cleanup_locks(self) -> int:
        """Clean up stale locks for inactive branches/users."""
        return await self._cleanup.cleanup_locks()

    # =========================================================================
    # Broadcast methods (delegate to broadcaster)
    # =========================================================================

    async def _send_to_connection(self, ws: "WebSocket", payload: dict[str, Any]) -> bool:
        """Send to a single connection, returning success status."""
        return await self._broadcaster._send_to_connection(ws, payload)

    async def _broadcast_to_connections(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str = "broadcast",
    ) -> int:
        """Send to multiple connections in parallel batches."""
        return await self._broadcaster._broadcast_to_connections(connections, payload, context)

    async def send_to_user(
        self,
        user_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to all connections of a specific user."""
        return await self._broadcaster.send_to_user(user_id, payload, tenant_id)

    async def send_to_branch(
        self,
        branch_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to all connections in a branch."""
        return await self._broadcaster.send_to_branch(branch_id, payload, tenant_id)

    async def send_to_session(
        self,
        session_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to all connections in a table session."""
        return await self._broadcaster.send_to_session(session_id, payload, tenant_id)

    async def send_to_sector(
        self,
        sector_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to all connections assigned to a sector."""
        return await self._broadcaster.send_to_sector(sector_id, payload, tenant_id)

    async def send_to_admins(
        self,
        branch_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to admin connections in a branch."""
        return await self._broadcaster.send_to_admins(branch_id, payload, tenant_id)

    async def send_to_waiters_only(
        self,
        branch_id: int,
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to NON-admin connections in a branch."""
        return await self._broadcaster.send_to_waiters_only(branch_id, payload, tenant_id)

    async def send_to_kitchen(
        self, branch_id: int, payload: dict[str, Any], tenant_id: int | None = None
    ) -> int:
        """Send to kitchen connections in a branch."""
        return await self._broadcaster.send_to_kitchen(
            branch_id, payload, tenant_id
        )

    async def send_to_sectors(
        self,
        sector_ids: list[int],
        payload: dict[str, Any],
        tenant_id: int | None = None,
    ) -> int:
        """Send a message to all connections assigned to any of the given sectors."""
        return await self._broadcaster.send_to_sectors(sector_ids, payload, tenant_id)

    async def broadcast(self, payload: dict[str, Any]) -> int:
        """Send a message to all connected clients."""
        return await self._broadcaster.broadcast(payload)

    # =========================================================================
    # Statistics (delegate to stats)
    # =========================================================================

    async def get_stats(self) -> dict[str, Any]:
        """Get connection statistics."""
        return await self._stats.get_stats()

    def get_stats_sync(self) -> dict[str, Any]:
        """Get connection statistics (sync version for health check)."""
        return self._stats.get_stats_sync()

    # =========================================================================
    # Shutdown
    # =========================================================================

    async def shutdown(self) -> int:
        """Graceful shutdown - close all connections."""
        self._lifecycle.set_shutdown(True)
        logger.info("WebSocket manager shutting down...")

        all_connections = self._index.get_all_connections()

        async def close_one(ws: "WebSocket") -> bool:
            try:
                await ws.close(code=WSCloseCode.GOING_AWAY, reason="Server shutdown")
                return True
            except Exception:
                return False

        results = await asyncio.gather(
            *[close_one(ws) for ws in all_connections],
            return_exceptions=True,
        )
        closed = sum(1 for r in results if r is True)

        # Disconnect all
        for ws in all_connections:
            try:
                await self.disconnect(ws)
            except Exception:
                pass

        logger.info("WebSocket shutdown complete. Closed %d connections.", closed)
        return closed

    def is_shutting_down(self) -> bool:
        """Check if the manager is in shutdown mode."""
        return self._lifecycle.is_shutdown
