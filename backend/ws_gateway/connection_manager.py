"""
WebSocket connection manager.
Tracks active connections organized by user and branch.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.

    Connections are indexed by:
    - user_id: for direct user notifications
    - branch_id: for branch-wide broadcasts
    - sector_id: for sector-specific notifications (waiter assignments)

    Thread-safe for async operations.
    """

    def __init__(self):
        self.by_user: dict[int, set[WebSocket]] = defaultdict(set)
        self.by_branch: dict[int, set[WebSocket]] = defaultdict(set)
        self.by_session: dict[int, set[WebSocket]] = defaultdict(set)
        self.by_sector: dict[int, set[WebSocket]] = defaultdict(set)
        self._ws_to_user: dict[WebSocket, int] = {}
        self._ws_to_branches: dict[WebSocket, list[int]] = {}
        self._ws_to_sessions: dict[WebSocket, set[int]] = defaultdict(set)
        self._ws_to_sectors: dict[WebSocket, list[int]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        branch_ids: list[int],
        sector_ids: list[int] | None = None,
    ) -> None:
        """
        Accept a WebSocket connection and register it.

        Args:
            websocket: The WebSocket connection.
            user_id: The authenticated user's ID.
            branch_ids: List of branches the user has access to.
            sector_ids: Optional list of assigned sector IDs (for waiters).
        """
        await websocket.accept()

        # Register by user
        self.by_user[user_id].add(websocket)
        self._ws_to_user[websocket] = user_id

        # Register by branches
        self._ws_to_branches[websocket] = branch_ids
        for branch_id in branch_ids:
            self.by_branch[branch_id].add(websocket)

        # Register by sectors (for waiter assignments)
        if sector_ids:
            self._ws_to_sectors[websocket] = sector_ids
            for sector_id in sector_ids:
                self.by_sector[sector_id].add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from all registrations.

        Args:
            websocket: The WebSocket connection to remove.
        """
        # Remove from user index
        user_id = self._ws_to_user.pop(websocket, None)
        if user_id is not None:
            self.by_user[user_id].discard(websocket)
            if not self.by_user[user_id]:
                del self.by_user[user_id]

        # Remove from branch indices
        branch_ids = self._ws_to_branches.pop(websocket, [])
        for branch_id in branch_ids:
            self.by_branch[branch_id].discard(websocket)
            if not self.by_branch[branch_id]:
                del self.by_branch[branch_id]

        # Remove from session indices
        session_ids = self._ws_to_sessions.pop(websocket, set())
        for session_id in session_ids:
            self.by_session[session_id].discard(websocket)
            if not self.by_session[session_id]:
                del self.by_session[session_id]

        # Remove from sector indices
        sector_ids = self._ws_to_sectors.pop(websocket, [])
        for sector_id in sector_ids:
            self.by_sector[sector_id].discard(websocket)
            if not self.by_sector[sector_id]:
                del self.by_sector[sector_id]

    def register_session(self, websocket: WebSocket, session_id: int) -> None:
        """Register a WebSocket connection to a table session."""
        self.by_session[session_id].add(websocket)
        self._ws_to_sessions[websocket].add(session_id)

    def unregister_session(self, websocket: WebSocket, session_id: int) -> None:
        """Unregister a WebSocket connection from a table session."""
        self.by_session[session_id].discard(websocket)
        if not self.by_session[session_id]:
            del self.by_session[session_id]
        self._ws_to_sessions[websocket].discard(session_id)

    def update_sectors(self, websocket: WebSocket, sector_ids: list[int]) -> None:
        """
        Update sector assignments for a WebSocket connection.

        Useful when waiter assignments change during an active session.

        Args:
            websocket: The WebSocket connection to update.
            sector_ids: New list of assigned sector IDs.
        """
        # Remove from old sectors
        old_sector_ids = self._ws_to_sectors.get(websocket, [])
        for sector_id in old_sector_ids:
            self.by_sector[sector_id].discard(websocket)
            if not self.by_sector[sector_id]:
                del self.by_sector[sector_id]

        # Add to new sectors
        self._ws_to_sectors[websocket] = sector_ids
        for sector_id in sector_ids:
            self.by_sector[sector_id].add(websocket)

    def get_sectors(self, websocket: WebSocket) -> list[int]:
        """Get the sector IDs assigned to a WebSocket connection."""
        return self._ws_to_sectors.get(websocket, [])

    async def send_to_user(self, user_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections of a specific user.

        Args:
            user_id: Target user's ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_user.get(user_id, []))
        sent = 0
        for ws in connections:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                # Connection might be closed, will be cleaned up later
                pass
        return sent

    async def send_to_branch(self, branch_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections in a branch.

        Args:
            branch_id: Target branch ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_branch.get(branch_id, []))
        sent = 0
        for ws in connections:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                # Connection might be closed, will be cleaned up later
                pass
        return sent

    async def send_to_session(self, session_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections in a table session.

        Args:
            session_id: Target table session ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_session.get(session_id, []))
        sent = 0
        for ws in connections:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                pass
        return sent

    async def send_to_sector(self, sector_id: int, payload: dict[str, Any]) -> int:
        """
        Send a message to all connections assigned to a sector.

        Args:
            sector_id: Target sector ID.
            payload: JSON-serializable message payload.

        Returns:
            Number of connections that received the message.
        """
        connections = list(self.by_sector.get(sector_id, []))
        sent = 0
        for ws in connections:
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                pass
        return sent

    async def send_to_sectors(self, sector_ids: list[int], payload: dict[str, Any]) -> int:
        """
        Send a message to all connections assigned to any of the given sectors.

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
            try:
                await ws.send_json(payload)
                sent += 1
            except Exception:
                pass
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
            except Exception:
                pass
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
