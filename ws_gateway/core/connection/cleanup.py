"""
Connection Cleanup Management.

Handles cleanup of stale, dead, and unused connections and locks.
Extracted from ConnectionManager for better maintainability.

ARCH-MODULAR-03: Single Responsibility - cleanup operations only.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, Awaitable, TYPE_CHECKING

from ws_gateway.components.core.constants import WSCloseCode, WSConstants

if TYPE_CHECKING:
    from fastapi import WebSocket
    from ws_gateway.components.connection.locks import LockManager
    from ws_gateway.components.connection.heartbeat import HeartbeatTracker
    from ws_gateway.components.connection.index import ConnectionIndex
    from ws_gateway.components.metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)


class ConnectionCleanup:
    """
    Manages cleanup of connections and resources.

    Responsibilities:
    - Track and clean stale connections (no heartbeat)
    - Track and clean dead connections (send failures)
    - Clean up unused locks

    Dead Connection Tracking:
    - Uses dict with timestamps for proper FIFO eviction
    - Size limited to prevent unbounded memory growth
    - Evicts oldest by mark time when at capacity
    """

    def __init__(
        self,
        lock_manager: "LockManager",
        metrics: "MetricsCollector",
        heartbeat_tracker: "HeartbeatTracker",
        index: "ConnectionIndex",
        disconnect_callback: Callable[["WebSocket"], Awaitable[None]],
        max_dead_connections: int = WSConstants.MAX_DEAD_CONNECTIONS,
    ) -> None:
        """
        Initialize cleanup manager with dependencies.

        Args:
            lock_manager: Manages sharded locks
            metrics: Collects cleanup metrics
            heartbeat_tracker: Tracks connection activity
            index: Connection indexing
            disconnect_callback: Callback to disconnect a connection
            max_dead_connections: Maximum dead connections to track
        """
        self._lock_manager = lock_manager
        self._metrics = metrics
        self._heartbeat_tracker = heartbeat_tracker
        self._index = index
        self._disconnect = disconnect_callback
        self._max_dead_connections = max_dead_connections

        # Dead connection tracking with timestamps for FIFO eviction
        self._dead_connections: dict["WebSocket", float] = {}

    @property
    def dead_connections_count(self) -> int:
        """Number of connections pending cleanup."""
        return len(self._dead_connections)

    # =========================================================================
    # Heartbeat tracking (delegated to HeartbeatTracker)
    # =========================================================================

    async def record_heartbeat(self, websocket: "WebSocket") -> None:
        """Record a heartbeat from a connection."""
        self._heartbeat_tracker.record(websocket)

    async def get_stale_connections(self) -> list["WebSocket"]:
        """Get connections that haven't sent a heartbeat within timeout."""
        return self._heartbeat_tracker.get_stale_connections()

    async def cleanup_stale_connections(self) -> int:
        """
        Close and remove stale connections.

        Returns:
            Number of connections cleaned up.
        """
        stale = self._heartbeat_tracker.cleanup_stale()
        cleaned = 0

        for ws in stale:
            try:
                await ws.close(
                    code=WSCloseCode.GOING_AWAY, reason="Heartbeat timeout"
                )
            except Exception as e:
                logger.debug("Failed to close stale connection: %s", str(e))

            try:
                await self._disconnect(ws)
                cleaned += 1
            except Exception as e:
                logger.debug("Failed to disconnect stale connection: %s", str(e))

        return cleaned

    # =========================================================================
    # Dead connection management
    # =========================================================================

    async def mark_dead_connection(self, ws: "WebSocket") -> None:
        """
        Mark a connection as dead for async cleanup.

        At capacity, evicts oldest dead connection (by mark time)
        before adding new one.
        """
        async with self._lock_manager.dead_connections_lock:
            # Skip if already marked dead
            if ws in self._dead_connections:
                return

            # At capacity, evict oldest before adding new
            if len(self._dead_connections) >= self._max_dead_connections:
                oldest = self._find_oldest_dead_connection()
                if oldest is not None:
                    del self._dead_connections[oldest]
                    logger.warning(
                        "Dead connections at capacity, evicting oldest",
                        current_size=len(self._dead_connections),
                        max_size=self._max_dead_connections,
                        evicted_ws_id=id(oldest),
                    )

            # Record the time when marked dead
            self._dead_connections[ws] = time.time()

    def _find_oldest_dead_connection(self) -> "WebSocket | None":
        """Find the oldest dead connection by mark time."""
        oldest = None
        oldest_time = float("inf")

        for dead_ws, mark_time in self._dead_connections.items():
            if mark_time < oldest_time:
                oldest_time = mark_time
                oldest = dead_ws

        return oldest

    async def cleanup_dead_connections(self) -> int:
        """
        Clean up connections marked as dead during send operations.

        Returns:
            Number of connections cleaned up.
        """
        async with self._lock_manager.dead_connections_lock:
            if not self._dead_connections:
                return 0
            # Get keys (WebSockets) from the dict
            dead = list(self._dead_connections.keys())
            self._dead_connections.clear()

        cleaned = 0
        for ws in dead:
            try:
                await self._disconnect(ws)
                cleaned += 1
            except Exception as e:
                logger.warning("Failed to cleanup dead connection: %s", str(e))

        return cleaned

    # =========================================================================
    # Lock cleanup
    # =========================================================================

    async def cleanup_locks(self) -> int:
        """
        Clean up stale locks for inactive branches/users.

        Returns:
            Number of locks cleaned up.
        """
        active_branches = self._index.get_active_branch_ids()
        active_users = self._index.get_active_user_ids()
        cleaned = await self._lock_manager.cleanup_stale_locks(
            active_branches, active_users
        )

        if cleaned > 0:
            self._metrics.add_locks_cleaned_sync(cleaned)

        return cleaned
