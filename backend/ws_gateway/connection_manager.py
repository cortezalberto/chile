"""
WebSocket connection manager.
Tracks active connections organized by user and branch.
CRIT-05 FIX: Replaced defaultdict with regular dict to prevent memory leaks.
CRIT-06 FIX: Added heartbeat tracking for connection health monitoring.
HIGH-29-07 FIX: Added logging for WebSocket send failures instead of silent pass.
WS-MED-01 FIX: Added graceful shutdown method.
WS-MED-02 FIX: Added input validation for sector IDs.
WS-MED-04 FIX: Added connection limits per user.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import WebSocket
from starlette.websockets import WebSocketState

# HIGH-29-07 FIX: Add logger for WebSocket send failures
logger = logging.getLogger(__name__)

# WS-MED-04 FIX: Maximum connections per user
MAX_CONNECTIONS_PER_USER = 5


def _is_ws_connected(ws: WebSocket) -> bool:
    """
    WS-CRIT-01 FIX: Check if WebSocket is in connected state before sending.
    Returns True if the connection is ready to send/receive messages.
    """
    return ws.client_state == WebSocketState.CONNECTED and ws.application_state == WebSocketState.CONNECTED


class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.

    Connections are indexed by:
    - user_id: for direct user notifications
    - branch_id: for branch-wide broadcasts
    - sector_id: for sector-specific notifications (waiter assignments)

    Thread-safe for async operations.
    CRIT-05 FIX: Uses regular dict instead of defaultdict to prevent memory leaks.
    CRIT-06 FIX: Tracks last heartbeat time per connection.
    CRIT-WS-07 FIX: Uses asyncio.Lock for thread-safe dict modifications.
    """

    # CRIT-06 FIX: Heartbeat timeout in seconds
    HEARTBEAT_TIMEOUT = 60  # Consider connection dead after 60s without heartbeat
    # WS-MED-04 FIX: Maximum connections per user
    MAX_CONNECTIONS_PER_USER = MAX_CONNECTIONS_PER_USER

    def __init__(self):
        self._shutdown = False  # WS-MED-01 FIX: Shutdown flag
        # CRIT-05 FIX: Use regular dicts instead of defaultdict to prevent memory leaks
        self.by_user: dict[int, set[WebSocket]] = {}
        self.by_branch: dict[int, set[WebSocket]] = {}
        self.by_session: dict[int, set[WebSocket]] = {}
        self.by_sector: dict[int, set[WebSocket]] = {}
        self._ws_to_user: dict[WebSocket, int] = {}
        self._ws_to_branches: dict[WebSocket, list[int]] = {}
        self._ws_to_sessions: dict[WebSocket, set[int]] = {}
        self._ws_to_sectors: dict[WebSocket, list[int]] = {}
        # CRIT-06 FIX: Track last heartbeat time per connection
        self._last_heartbeat: dict[WebSocket, float] = {}
        # CRIT-WS-07 FIX: Lock for thread-safe dict modifications
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        branch_ids: list[int],
        sector_ids: list[int] | None = None,
        timeout: float = 5.0,
    ) -> None:
        """
        Accept a WebSocket connection and register it.

        WS-CRIT-02 FIX: Uses asyncio.Lock for thread-safe dict modifications.

        Args:
            websocket: The WebSocket connection.
            user_id: The authenticated user's ID.
            branch_ids: List of branches the user has access to.
            sector_ids: Optional list of assigned sector IDs (for waiters).
            timeout: Timeout for accept handshake (CRIT-14 FIX).
        """
        # WS-MED-01 FIX: Reject new connections during shutdown
        if self._shutdown:
            raise ConnectionError("Server is shutting down")

        # CRIT-14 FIX: Add timeout to prevent hanging on accept
        try:
            await asyncio.wait_for(websocket.accept(), timeout=timeout)
        except asyncio.TimeoutError:
            raise ConnectionError("WebSocket accept timed out")

        # WS-MED-04 FIX: Check connection limit per user before accepting
        if user_id in self.by_user and len(self.by_user[user_id]) >= self.MAX_CONNECTIONS_PER_USER:
            await websocket.close(code=1008, reason="Too many connections")
            raise ConnectionError(f"User {user_id} exceeded max connections ({self.MAX_CONNECTIONS_PER_USER})")

        # WS-CRIT-02 FIX: Use lock for thread-safe dict modifications
        async with self._lock:
            # CRIT-06 FIX: Record initial heartbeat time
            self._last_heartbeat[websocket] = time.time()

            # Register by user (CRIT-05 FIX: Initialize set if not exists)
            if user_id not in self.by_user:
                self.by_user[user_id] = set()
            self.by_user[user_id].add(websocket)
            self._ws_to_user[websocket] = user_id

            # Register by branches (CRIT-05 FIX: Initialize sets if not exists)
            self._ws_to_branches[websocket] = branch_ids
            for branch_id in branch_ids:
                if branch_id not in self.by_branch:
                    self.by_branch[branch_id] = set()
                self.by_branch[branch_id].add(websocket)

            # Register by sectors (for waiter assignments)
            if sector_ids:
                self._ws_to_sectors[websocket] = sector_ids
                for sector_id in sector_ids:
                    if sector_id not in self.by_sector:
                        self.by_sector[sector_id] = set()
                    self.by_sector[sector_id].add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from all registrations.

        CRIT-WS-07 FIX: Uses asyncio.Lock to prevent race conditions
        when multiple disconnections happen concurrently.

        Args:
            websocket: The WebSocket connection to remove.
        """
        async with self._lock:
            # CRIT-06 FIX: Remove heartbeat tracking
            self._last_heartbeat.pop(websocket, None)

            # Remove from user index
            user_id = self._ws_to_user.pop(websocket, None)
            if user_id is not None and user_id in self.by_user:
                self.by_user[user_id].discard(websocket)
                if not self.by_user[user_id]:
                    del self.by_user[user_id]

            # Remove from branch indices
            branch_ids = self._ws_to_branches.pop(websocket, [])
            for branch_id in branch_ids:
                if branch_id in self.by_branch:
                    self.by_branch[branch_id].discard(websocket)
                    if not self.by_branch[branch_id]:
                        del self.by_branch[branch_id]

            # Remove from session indices
            session_ids = self._ws_to_sessions.pop(websocket, set())
            for session_id in session_ids:
                if session_id in self.by_session:
                    self.by_session[session_id].discard(websocket)
                    if not self.by_session[session_id]:
                        del self.by_session[session_id]

            # Remove from sector indices
            sector_ids = self._ws_to_sectors.pop(websocket, [])
            for sector_id in sector_ids:
                if sector_id in self.by_sector:
                    self.by_sector[sector_id].discard(websocket)
                    if not self.by_sector[sector_id]:
                        del self.by_sector[sector_id]

    async def register_session(self, websocket: WebSocket, session_id: int) -> None:
        """
        Register a WebSocket connection to a table session.
        WS-CRIT-02 FIX: Made async and uses lock for thread-safe dict modifications.
        """
        async with self._lock:
            # CRIT-05 FIX: Initialize sets if not exists
            if session_id not in self.by_session:
                self.by_session[session_id] = set()
            self.by_session[session_id].add(websocket)
            if websocket not in self._ws_to_sessions:
                self._ws_to_sessions[websocket] = set()
            self._ws_to_sessions[websocket].add(session_id)

    async def unregister_session(self, websocket: WebSocket, session_id: int) -> None:
        """
        Unregister a WebSocket connection from a table session.
        WS-CRIT-02 FIX: Made async and uses lock for thread-safe dict modifications.
        """
        async with self._lock:
            # CRIT-05 FIX: Check if key exists before accessing
            if session_id in self.by_session:
                self.by_session[session_id].discard(websocket)
                if not self.by_session[session_id]:
                    del self.by_session[session_id]
            if websocket in self._ws_to_sessions:
                self._ws_to_sessions[websocket].discard(session_id)

    async def update_sectors(self, websocket: WebSocket, sector_ids: list[int]) -> None:
        """
        Update sector assignments for a WebSocket connection.
        WS-CRIT-02 FIX: Made async and uses lock for thread-safe dict modifications.
        WS-MED-02 FIX: Added input validation for sector IDs.

        Useful when waiter assignments change during an active session.

        Args:
            websocket: The WebSocket connection to update.
            sector_ids: New list of assigned sector IDs.

        Raises:
            ValueError: If sector_ids contains invalid values.
        """
        # WS-MED-02 FIX: Validate sector_ids input
        if not isinstance(sector_ids, list):
            raise ValueError("sector_ids must be a list")
        for sector_id in sector_ids:
            if not isinstance(sector_id, int) or sector_id <= 0:
                raise ValueError(f"Invalid sector_id: {sector_id}. Must be a positive integer.")

        async with self._lock:
            # Remove from old sectors (CRIT-05 FIX: Check if key exists)
            old_sector_ids = self._ws_to_sectors.get(websocket, [])
            for sector_id in old_sector_ids:
                if sector_id in self.by_sector:
                    self.by_sector[sector_id].discard(websocket)
                    if not self.by_sector[sector_id]:
                        del self.by_sector[sector_id]

            # Add to new sectors (CRIT-05 FIX: Initialize sets if not exists)
            self._ws_to_sectors[websocket] = sector_ids
            for sector_id in sector_ids:
                if sector_id not in self.by_sector:
                    self.by_sector[sector_id] = set()
                self.by_sector[sector_id].add(websocket)

    def get_sectors(self, websocket: WebSocket) -> list[int]:
        """Get the sector IDs assigned to a WebSocket connection."""
        return self._ws_to_sectors.get(websocket, [])

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections of a specific user.

        WS-CRIT-01 FIX: Verifies connection state before sending.

        Args:
            user_id: Target user's ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_user.get(user_id, []))
        sent = 0
        for ws in connections:
            # WS-CRIT-01 FIX: Check connection state before sending
            if not _is_ws_connected(ws):
                logger.debug("Skipping send to disconnected socket for user %s", user_id)
                continue
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception as e:
                # HIGH-29-07 FIX: Log exception instead of silent pass
                logger.warning(
                    "Failed to send message to user %s: %s",
                    user_id,
                    str(e),
                )
        return sent

    async def send_to_branch(self, branch_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections in a branch.

        WS-CRIT-01 FIX: Verifies connection state before sending.

        Args:
            branch_id: Target branch ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_branch.get(branch_id, []))
        sent = 0
        for ws in connections:
            # WS-CRIT-01 FIX: Check connection state before sending
            if not _is_ws_connected(ws):
                logger.debug("Skipping send to disconnected socket for branch %s", branch_id)
                continue
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception as e:
                # HIGH-29-07 FIX: Log exception instead of silent pass
                logger.warning(
                    "Failed to send message to branch %s: %s",
                    branch_id,
                    str(e),
                )
        return sent

    async def send_to_session(self, session_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections in a table session.

        WS-CRIT-01 FIX: Verifies connection state before sending.

        Args:
            session_id: Target table session ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_session.get(session_id, []))
        sent = 0
        for ws in connections:
            # WS-CRIT-01 FIX: Check connection state before sending
            if not _is_ws_connected(ws):
                logger.debug("Skipping send to disconnected socket for session %s", session_id)
                continue
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception as e:
                # HIGH-29-07 FIX: Log exception instead of silent pass
                logger.warning(
                    "Failed to send message to session %s: %s",
                    session_id,
                    str(e),
                )
        return sent

    async def send_to_sector(self, sector_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections assigned to a sector.

        WS-CRIT-01 FIX: Verifies connection state before sending.

        Args:
            sector_id: Target sector ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_sector.get(sector_id, []))
        sent = 0
        for ws in connections:
            # WS-CRIT-01 FIX: Check connection state before sending
            if not _is_ws_connected(ws):
                logger.debug("Skipping send to disconnected socket for sector %s", sector_id)
                continue
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception as e:
                # HIGH-29-07 FIX: Log exception instead of silent pass
                logger.warning(
                    "Failed to send message to sector %s: %s",
                    sector_id,
                    str(e),
                )
        return sent

    async def send_to_sectors(self, sector_ids: list[int], payload: dict[str, Any]) -> int:
        """
        Send a message to all connections assigned to any of the given sectors.

        WS-CRIT-01 FIX: Verifies connection state before sending.

        Args:
            sector_ids: List of target sector IDs.
            payload: JSON-serializable message payload.

        Returns:
            Number of unique connections that received the message.
        """
        # Collect unique connections across all sectors
        all_connections: set[WebSocket] = set()
        for sector_id in sector_ids:
            all_connections.update(self.by_sector.get(sector_id, set()))

        sent = 0
        for ws in all_connections:
            # WS-CRIT-01 FIX: Check connection state before sending
            if not _is_ws_connected(ws):
                logger.debug("Skipping send to disconnected socket for sectors %s", sector_ids)
                continue
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception as e:
                # HIGH-29-07 FIX: Log exception instead of silent pass
                logger.warning(
                    "Failed to send message to sectors %s: %s",
                    sector_ids,
                    str(e),
                )
        return sent

    async def broadcast(self, payload: dict[str, Any]) -> int:
        """
        Send a message to all connected clients.

        Args:
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        # Use all unique connections
        all_connections = set()
        for connections in self.by_user.values():
            all_connections.update(connections)

        sent = 0
        for ws in all_connections:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception as e:
                # HIGH-29-07 FIX: Log exception instead of silent pass
                logger.warning("Failed to broadcast message: %s", str(e))
        return sent

    @property
    def total_connections(self) -> int:
        """Get total number of active connections."""
        return len(self._ws_to_user)

    def get_stats(self) -> dict[str, Any]:
        """Get connection statistics."""
        return {
            "total_connections": self.total_connections,
            "users_connected": len(self.by_user),
            "branches_with_connections": len(self.by_branch),
            "sectors_with_connections": len(self.by_sector),
            "sessions_with_connections": len(self.by_session),
        }

    # =========================================================================
    # CRIT-06 FIX: Heartbeat tracking methods
    # =========================================================================

    def record_heartbeat(self, websocket: WebSocket) -> None:
        """Record a heartbeat from a connection."""
        self._last_heartbeat[websocket] = time.time()

    def get_stale_connections(self) -> list[WebSocket]:
        """
        Get connections that haven't sent a heartbeat within the timeout period.

        Returns:
            List of stale WebSocket connections.

        CRIT-05 FIX: Use list() to avoid RuntimeError when dict changes during iteration.
        """
        now = time.time()
        stale = []
        # CRIT-05 FIX: Create a snapshot of items to avoid RuntimeError
        for ws, last_time in list(self._last_heartbeat.items()):
            if now - last_time > self.HEARTBEAT_TIMEOUT:
                stale.append(ws)
        return stale

    async def cleanup_stale_connections(self) -> int:
        """
        Close and remove stale connections.

        CRIT-WS-07 FIX: Updated to use async disconnect().

        Returns:
            Number of connections cleaned up.
        """
        stale = self.get_stale_connections()
        for ws in stale:
            try:
                await ws.close(code=1001, reason="Heartbeat timeout")
            except Exception as e:
                # HIGH-29-07 FIX: Log exception instead of silent pass
                logger.warning("Failed to close stale connection: %s", str(e))
            await self.disconnect(ws)
        return len(stale)

    async def shutdown(self) -> int:
        """
        WS-MED-01 FIX: Graceful shutdown - close all connections.

        Sets shutdown flag to reject new connections and closes existing ones.

        Returns:
            Number of connections closed.
        """
        self._shutdown = True
        logger.info("WebSocket manager shutting down...")

        # Get all unique connections
        all_connections: set[WebSocket] = set()
        async with self._lock:
            for connections in self.by_user.values():
                all_connections.update(connections)

        closed = 0
        for ws in all_connections:
            try:
                await ws.close(code=1001, reason="Server shutdown")
                closed += 1
            except Exception as e:
                logger.warning("Failed to close connection during shutdown: %s", str(e))
            await self.disconnect(ws)

        logger.info("WebSocket shutdown complete. Closed %d connections.", closed)
        return closed

    def is_shutting_down(self) -> bool:
        """Check if the manager is in shutdown mode."""
        return self._shutdown
