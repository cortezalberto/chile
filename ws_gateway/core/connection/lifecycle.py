"""
Connection Lifecycle Management.

Handles WebSocket connection acceptance and disconnection.
Extracted from ConnectionManager for better maintainability.

ARCH-MODULAR-01: Single Responsibility - connection lifecycle only.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ws_gateway.components.core.constants import WSConstants

if TYPE_CHECKING:
    from fastapi import WebSocket
    from ws_gateway.components.connection.locks import LockManager
    from ws_gateway.components.connection.heartbeat import HeartbeatTracker
    from ws_gateway.components.connection.rate_limiter import WebSocketRateLimiter
    from ws_gateway.components.connection.index import ConnectionIndex
    from ws_gateway.components.metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)


class ConnectionLifecycle:
    """
    Manages the lifecycle of WebSocket connections.

    Responsibilities:
    - Accept new connections with validation
    - Register connections in indices
    - Disconnect and cleanup connections

    Lock Ordering (must follow to prevent deadlocks):
    1. connection_counter_lock (global)
    2. user_lock (per-user, ascending user_id)
    3. branch_locks (per-branch, ascending branch_id)
    4. sector_lock (global)
    5. session_lock (global)
    """

    def __init__(
        self,
        lock_manager: "LockManager",
        metrics: "MetricsCollector",
        heartbeat_tracker: "HeartbeatTracker",
        rate_limiter: "WebSocketRateLimiter",
        index: "ConnectionIndex",
        max_connections_per_user: int,
        max_total_connections: int,
    ) -> None:
        """
        Initialize lifecycle manager with dependencies.

        Args:
            lock_manager: Manages sharded locks
            metrics: Collects connection metrics
            heartbeat_tracker: Tracks connection activity
            rate_limiter: Limits message rates
            index: Connection indexing
            max_connections_per_user: Per-user connection limit
            max_total_connections: Global connection limit
        """
        self._lock_manager = lock_manager
        self._metrics = metrics
        self._heartbeat_tracker = heartbeat_tracker
        self._rate_limiter = rate_limiter
        self._index = index
        self._max_connections_per_user = max_connections_per_user
        self._max_total_connections = max_total_connections
        self._total_connections = 0
        self._shutdown = False

    @property
    def total_connections(self) -> int:
        """Current number of active connections."""
        return self._total_connections

    @property
    def is_shutdown(self) -> bool:
        """Whether shutdown has been initiated."""
        return self._shutdown

    def set_shutdown(self, value: bool) -> None:
        """Set shutdown state."""
        self._shutdown = value

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
        """
        Accept a WebSocket connection and register it.

        Args:
            websocket: The WebSocket to connect.
            user_id: User ID for tracking (negative for diners).
            branch_ids: List of branch IDs the user has access to.
            sector_ids: Optional list of sector IDs for waiters.
            is_admin: Whether this is an admin/manager connection.
            timeout: Timeout for accepting the WebSocket.
            tenant_id: Tenant ID for multi-tenant isolation.

        Raises:
            ConnectionError: If server is at capacity or shutting down.
            ValueError: If invalid branch_ids or sector_ids provided.
        """
        if self._shutdown:
            raise ConnectionError("Server is shutting down")

        # Validate branch_ids
        self._validate_branch_ids(branch_ids, user_id)

        # Validate sector_ids
        if sector_ids is not None:
            self._validate_sector_ids(sector_ids, user_id, tenant_id)

        # Atomic check-and-increment for connection limit
        async with self._lock_manager.connection_counter_lock:
            if self._total_connections >= self._max_total_connections:
                self._metrics.increment_connection_rejected_limit_sync()
                raise ConnectionError(
                    f"Server at capacity ({self._max_total_connections} connections)"
                )
            self._total_connections += 1

        # Accept WebSocket with error handling
        try:
            await asyncio.wait_for(websocket.accept(), timeout=timeout)
        except asyncio.TimeoutError:
            await self._decrement_connection_count()
            raise ConnectionError("WebSocket accept timed out")
        except Exception as e:
            await self._decrement_connection_count()
            raise ConnectionError(f"WebSocket accept failed: {e}")

        # Register with user lock to prevent race conditions
        # Register with user lock to prevent race conditions
        await self._register_connection(
            websocket, user_id, branch_ids, sector_ids, is_admin, is_kitchen, tenant_id
        )


    async def disconnect(self, websocket: "WebSocket") -> None:
        """
        Remove a WebSocket connection from all registrations.

        Args:
            websocket: The WebSocket to disconnect.
        """
        # Remove from heartbeat tracker and rate limiter
        self._heartbeat_tracker.remove(websocket)
        await self._rate_limiter.remove_connection(websocket)

        # Get user ID via ConnectionIndex
        user_id = self._index.get_user_id(websocket)
        if user_id is None:
            return

        user_lock = await self._lock_manager.get_user_lock(user_id)
        async with user_lock:
            # Decrement connection counter
            await self._decrement_connection_count()

            # Get info before unregistering
            is_admin = self._index.is_admin(websocket)
            is_kitchen = self._index.is_kitchen(websocket)
            branch_ids = self._index.get_branch_ids(websocket)
            session_ids = self._index.get_session_ids(websocket)
            sector_ids = self._index.get_sector_ids(websocket)

            # Unregister from user index
            self._index.unregister_user(websocket)

            # Remove from branch indices (sorted for consistent lock ordering)
            for branch_id in sorted(branch_ids):
                branch_lock = await self._lock_manager.get_branch_lock(branch_id)
                async with branch_lock:
                    self._index.unregister_branch(websocket, branch_id, is_admin, is_kitchen)


            # Remove from session indices
            async with self._lock_manager.session_lock:
                for session_id in session_ids:
                    self._index.unregister_session(websocket, session_id)

            # Remove from sector indices
            async with self._lock_manager.sector_lock:
                self._index.unregister_sectors(websocket, sector_ids)

    def _validate_branch_ids(self, branch_ids: list[int], user_id: int) -> None:
        """Validate branch_ids format and values."""
        if not isinstance(branch_ids, list):
            raise ValueError("branch_ids must be a list")

        if not branch_ids:
            logger.warning(
                "Connection with empty branch_ids",
                user_id=user_id,
            )

        for branch_id in branch_ids:
            if not isinstance(branch_id, int) or branch_id <= 0:
                raise ValueError(f"Invalid branch_id: {branch_id}")

    def _validate_sector_ids(
        self,
        sector_ids: list[int],
        user_id: int,
        tenant_id: int | None,
    ) -> None:
        """Validate sector_ids format and values."""
        if not isinstance(sector_ids, list):
            raise ValueError("sector_ids must be a list")

        for sector_id in sector_ids:
            if not isinstance(sector_id, int) or sector_id <= 0:
                raise ValueError(f"Invalid sector_id: {sector_id}")

        # Warn on suspicious patterns
        if len(sector_ids) > WSConstants.MAX_SECTORS_PER_WAITER:
            logger.warning(
                "Waiter registered with unusually many sectors",
                user_id=user_id,
                sector_count=len(sector_ids),
                max_expected=WSConstants.MAX_SECTORS_PER_WAITER,
                tenant_id=tenant_id,
            )

        if len(sector_ids) != len(set(sector_ids)):
            logger.warning(
                "Waiter registered with duplicate sector IDs",
                user_id=user_id,
                sector_ids=sector_ids,
                tenant_id=tenant_id,
            )

    async def _decrement_connection_count(self) -> None:
        """Safely decrement the connection counter."""
        async with self._lock_manager.connection_counter_lock:
            self._total_connections = max(0, self._total_connections - 1)

    async def _register_connection(
        self,
        websocket: "WebSocket",
        user_id: int,
        branch_ids: list[int],
        sector_ids: list[int] | None,
        is_admin: bool,
        is_kitchen: bool,
        tenant_id: int | None,
    ) -> None:

        """Register connection in all indices with proper locking."""
        user_lock = await self._lock_manager.get_user_lock(user_id)
        async with user_lock:
            # Check per-user limit
            user_connections = self._index.get_user_connections(user_id)
            if len(user_connections) >= self._max_connections_per_user:
                await self._decrement_connection_count()
                raise ConnectionError(
                    f"User {user_id} exceeded max connections ({self._max_connections_per_user})"
                )

            # Record heartbeat
            self._heartbeat_tracker.record(websocket)

            # Register via ConnectionIndex
            self._index.register_user(websocket, user_id, is_admin, is_kitchen, tenant_id)

            # Register by branches (sorted for consistent lock ordering)
            for branch_id in sorted(branch_ids):
                branch_lock = await self._lock_manager.get_branch_lock(branch_id)
                async with branch_lock:
                    self._index.register_branch(websocket, branch_id, is_admin, is_kitchen)


            # Register by sectors
            if sector_ids:
                async with self._lock_manager.sector_lock:
                    self._index.register_sectors(websocket, sector_ids)
