"""
Connection Index - Manages all WebSocket connection indices.

ARCH-AUDIT-01: Extracted from ConnectionManager to follow Single Responsibility Principle.
This class handles all connection indexing by user, branch, sector, session, and admin status.

The ConnectionManager now delegates index operations to this class, reducing its
size from 1060 lines to ~700 lines.
"""

from __future__ import annotations

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


class LockManagerProtocol(Protocol):
    """Protocol for lock manager to avoid circular imports."""

    async def get_user_lock(self, user_id: int): ...
    async def get_branch_lock(self, branch_id: int): ...

    @property
    def connection_counter_lock(self): ...

    @property
    def sector_lock(self): ...

    @property
    def session_lock(self): ...


class ConnectionIndex:
    """
    Manages WebSocket connection indices.

    Indices maintained:
    - by_user: user_id -> set[WebSocket]
    - by_branch: branch_id -> set[WebSocket]
    - by_session: session_id -> set[WebSocket]
    - by_sector: sector_id -> set[WebSocket]
    - admins_by_branch: branch_id -> set[WebSocket] (admin/manager only)

    Reverse mappings for efficient disconnect:
    - ws_to_user: WebSocket -> user_id
    - ws_to_branches: WebSocket -> list[branch_id]
    - ws_to_sessions: WebSocket -> set[session_id]
    - ws_to_sectors: WebSocket -> list[sector_id]
    - ws_is_admin: WebSocket -> bool
    - ws_to_tenant: WebSocket -> tenant_id (multi-tenant isolation)

    Thread Safety:
    - All mutations require appropriate locks from LockManager
    - Read-only properties return immutable views (MappingProxyType)
    """

    def __init__(self) -> None:
        """Initialize empty indices."""
        # Primary indices
        self._by_user: dict[int, set[WebSocket]] = {}
        self._by_branch: dict[int, set[WebSocket]] = {}
        self._by_session: dict[int, set[WebSocket]] = {}
        self._by_sector: dict[int, set[WebSocket]] = {}
        self._admins_by_branch: dict[int, set[WebSocket]] = {}
        self._kitchen_by_branch: dict[int, set[WebSocket]] = {}


        # Reverse mappings
        self._ws_to_user: dict[WebSocket, int] = {}
        self._ws_to_branches: dict[WebSocket, list[int]] = {}
        self._ws_to_sessions: dict[WebSocket, set[int]] = {}
        self._ws_to_sectors: dict[WebSocket, list[int]] = {}
        self._ws_is_admin: dict[WebSocket, bool] = {}
        self._ws_is_kitchen: dict[WebSocket, bool] = {}

        self._ws_to_tenant: dict[WebSocket, int] = {}

        # Connection counter
        self._total_connections = 0

    # =========================================================================
    # Immutable views (MED-NEW-01 FIX: Prevent external mutation)
    # =========================================================================

    @property
    def by_user(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by user ID (immutable view)."""
        return MappingProxyType(self._by_user)

    @property
    def by_branch(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by branch ID (immutable view)."""
        return MappingProxyType(self._by_branch)

    @property
    def by_session(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by session ID (immutable view)."""
        return MappingProxyType(self._by_session)

    @property
    def by_sector(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Connections indexed by sector ID (immutable view)."""
        return MappingProxyType(self._by_sector)

    @property
    def admins_by_branch(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Admin connections indexed by branch ID (immutable view)."""
        return MappingProxyType(self._admins_by_branch)

    @property
    def kitchen_by_branch(self) -> MappingProxyType[int, set["WebSocket"]]:
        """Kitchen connections indexed by branch ID (immutable view)."""
        return MappingProxyType(self._kitchen_by_branch)


    @property
    def total_connections(self) -> int:
        """Total number of active connections."""
        return self._total_connections

    # =========================================================================
    # Query methods (no locks needed - read-only)
    # =========================================================================

    def get_user_id(self, ws: "WebSocket") -> int | None:
        """Get user ID for a WebSocket connection."""
        return self._ws_to_user.get(ws)

    def get_branch_ids(self, ws: "WebSocket") -> list[int]:
        """Get branch IDs for a WebSocket connection."""
        return self._ws_to_branches.get(ws, [])

    def get_sector_ids(self, ws: "WebSocket") -> list[int]:
        """Get sector IDs for a WebSocket connection."""
        return self._ws_to_sectors.get(ws, [])

    def get_session_ids(self, ws: "WebSocket") -> set[int]:
        """Get session IDs for a WebSocket connection."""
        return self._ws_to_sessions.get(ws, set())

    def is_admin(self, ws: "WebSocket") -> bool:
        """Check if connection is admin/manager."""
        return self._ws_is_admin.get(ws, False)

    def is_kitchen(self, ws: "WebSocket") -> bool:
        """Check if connection is kitchen staff."""
        return self._ws_is_kitchen.get(ws, False)


    def get_tenant_id(self, ws: "WebSocket") -> int | None:
        """Get tenant ID for a WebSocket connection (multi-tenant isolation)."""
        return self._ws_to_tenant.get(ws)

    def get_connections_for_user(self, user_id: int) -> set["WebSocket"]:
        """Get all connections for a user (returns copy for safety)."""
        return set(self._by_user.get(user_id, set()))

    def get_connections_for_branch(self, branch_id: int) -> set["WebSocket"]:
        """Get all connections for a branch (returns copy for safety)."""
        return set(self._by_branch.get(branch_id, set()))

    def get_connections_for_sector(self, sector_id: int) -> set["WebSocket"]:
        """Get all connections for a sector (returns copy for safety)."""
        return set(self._by_sector.get(sector_id, set()))

    def get_connections_for_session(self, session_id: int) -> set["WebSocket"]:
        """Get all connections for a session (returns copy for safety)."""
        return set(self._by_session.get(session_id, set()))

    def get_admin_connections_for_branch(self, branch_id: int) -> set["WebSocket"]:
        """Get admin connections for a branch (returns copy for safety)."""
        return set(self._admins_by_branch.get(branch_id, set()))

    def get_kitchen_connections_for_branch(self, branch_id: int) -> set["WebSocket"]:
        """Get kitchen connections for a branch (returns copy for safety)."""
        return set(self._kitchen_by_branch.get(branch_id, set()))


    def count_user_connections(self, user_id: int) -> int:
        """Count connections for a user."""
        return len(self._by_user.get(user_id, set()))

    # =========================================================================
    # Registration methods (require locks from caller)
    # =========================================================================

    def increment_total(self) -> None:
        """Increment total connection count. MUST be called with connection_counter_lock."""
        self._total_connections += 1

    def decrement_total(self) -> None:
        """Decrement total connection count. MUST be called with connection_counter_lock."""
        self._total_connections = max(0, self._total_connections - 1)

    def register_user(
        self,
        ws: "WebSocket",
        user_id: int,
        is_admin: bool = False,
        is_kitchen: bool = False,
        tenant_id: int | None = None,
    ) -> None:
        """
        Register connection for a user with admin status and tenant.
        MUST be called with user_lock.

        Args:
            ws: WebSocket connection
            user_id: User ID (negative for diners)
            is_admin: Whether this is an admin connection
            is_kitchen: Whether this is a kitchen connection
            tenant_id: Tenant ID for multi-tenant isolation
        """
        if user_id not in self._by_user:
            self._by_user[user_id] = set()
        self._by_user[user_id].add(ws)
        self._ws_to_user[ws] = user_id
        self._ws_is_admin[ws] = is_admin
        self._ws_is_kitchen[ws] = is_kitchen
        if tenant_id is not None:
            self._ws_to_tenant[ws] = tenant_id

    def register_admin_status(self, ws: "WebSocket", is_admin: bool) -> None:
        """Register admin status. MUST be called with user_lock."""
        self._ws_is_admin[ws] = is_admin

    def register_kitchen_status(self, ws: "WebSocket", is_kitchen: bool) -> None:
        """Register kitchen status. MUST be called with user_lock."""
        self._ws_is_kitchen[ws] = is_kitchen


    def register_tenant(self, ws: "WebSocket", tenant_id: int) -> None:
        """Register tenant ID for multi-tenant isolation. MUST be called with user_lock."""
        self._ws_to_tenant[ws] = tenant_id

    def register_branch(
        self, ws: "WebSocket", branch_id: int, is_admin: bool = False, is_kitchen: bool = False
    ) -> None:
        """
        Register connection for a branch. MUST be called with branch_lock.

        Args:
            ws: WebSocket connection
            branch_id: Branch ID
            is_admin: Whether this is an admin connection
            is_kitchen: Whether this is a kitchen connection
        """
        if branch_id not in self._by_branch:
            self._by_branch[branch_id] = set()
        self._by_branch[branch_id].add(ws)

        if is_admin:
            if branch_id not in self._admins_by_branch:
                self._admins_by_branch[branch_id] = set()
            self._admins_by_branch[branch_id].add(ws)

        if is_kitchen:
            if branch_id not in self._kitchen_by_branch:
                self._kitchen_by_branch[branch_id] = set()
            self._kitchen_by_branch[branch_id].add(ws)


    def set_branches(self, ws: "WebSocket", branch_ids: list[int]) -> None:
        """Set branch IDs for reverse mapping. MUST be called with user_lock."""
        self._ws_to_branches[ws] = branch_ids

    def register_sector(self, ws: "WebSocket", sector_id: int) -> None:
        """Register connection for a sector. MUST be called with sector_lock."""
        if sector_id not in self._by_sector:
            self._by_sector[sector_id] = set()
        self._by_sector[sector_id].add(ws)

    def set_sectors(self, ws: "WebSocket", sector_ids: list[int]) -> None:
        """Set sector IDs for reverse mapping. MUST be called with sector_lock."""
        self._ws_to_sectors[ws] = sector_ids

    def register_session(self, ws: "WebSocket", session_id: int) -> None:
        """Register connection for a session. MUST be called with session_lock."""
        if session_id not in self._by_session:
            self._by_session[session_id] = set()
        self._by_session[session_id].add(ws)

        if ws not in self._ws_to_sessions:
            self._ws_to_sessions[ws] = set()
        self._ws_to_sessions[ws].add(session_id)

    # =========================================================================
    # Unregistration methods (require locks from caller)
    # =========================================================================

    def unregister_user(self, ws: "WebSocket") -> int | None:
        """
        Unregister connection from user index and clean up related mappings.
        MUST be called with user_lock.

        Returns:
            The user_id that was unregistered, or None if not found.
        """
        user_id = self._ws_to_user.pop(ws, None)
        if user_id is not None and user_id in self._by_user:
            self._by_user[user_id].discard(ws)
            if not self._by_user[user_id]:
                del self._by_user[user_id]
        # Clean up admin status, kitchen status and tenant
        self._ws_is_admin.pop(ws, None)
        self._ws_is_kitchen.pop(ws, None)
        self._ws_to_tenant.pop(ws, None)

        return user_id

    def unregister_admin_status(self, ws: "WebSocket") -> bool:
        """
        Unregister admin status. MUST be called with user_lock.

        Returns:
            True if was admin, False otherwise.
        """
        return self._ws_is_admin.pop(ws, False)

    def unregister_kitchen_status(self, ws: "WebSocket") -> bool:
        """
        Unregister kitchen status. MUST be called with user_lock.

        Returns:
            True if was kitchen, False otherwise.
        """
        return self._ws_is_kitchen.pop(ws, False)


    def unregister_tenant(self, ws: "WebSocket") -> int | None:
        """Unregister tenant. MUST be called with user_lock."""
        return self._ws_to_tenant.pop(ws, None)

    def unregister_branch(
        self, ws: "WebSocket", branch_id: int, is_admin: bool = False, is_kitchen: bool = False
    ) -> None:
        """Unregister connection from branch. MUST be called with branch_lock."""
        if branch_id in self._by_branch:
            self._by_branch[branch_id].discard(ws)
            if not self._by_branch[branch_id]:
                del self._by_branch[branch_id]

        if is_admin and branch_id in self._admins_by_branch:
            self._admins_by_branch[branch_id].discard(ws)
            if not self._admins_by_branch[branch_id]:
                del self._admins_by_branch[branch_id]

        if is_kitchen and branch_id in self._kitchen_by_branch:
            self._kitchen_by_branch[branch_id].discard(ws)
            if not self._kitchen_by_branch[branch_id]:
                del self._kitchen_by_branch[branch_id]


    def pop_branches(self, ws: "WebSocket") -> list[int]:
        """Remove and return branch IDs for reverse mapping. MUST be called with user_lock."""
        return self._ws_to_branches.pop(ws, [])

    def unregister_sector(self, ws: "WebSocket", sector_id: int) -> None:
        """Unregister connection from sector. MUST be called with sector_lock."""
        if sector_id in self._by_sector:
            self._by_sector[sector_id].discard(ws)
            if not self._by_sector[sector_id]:
                del self._by_sector[sector_id]

    def pop_sectors(self, ws: "WebSocket") -> list[int]:
        """Remove and return sector IDs for reverse mapping. MUST be called with sector_lock."""
        return self._ws_to_sectors.pop(ws, [])

    def clear_sectors(self, ws: "WebSocket") -> None:
        """Clear sector IDs for a connection. MUST be called with sector_lock."""
        self._ws_to_sectors[ws] = []

    def unregister_session(self, ws: "WebSocket", session_id: int) -> None:
        """Unregister connection from session. MUST be called with session_lock."""
        if session_id in self._by_session:
            self._by_session[session_id].discard(ws)
            if not self._by_session[session_id]:
                del self._by_session[session_id]

        if ws in self._ws_to_sessions:
            self._ws_to_sessions[ws].discard(session_id)

    def pop_sessions(self, ws: "WebSocket") -> set[int]:
        """Remove and return session IDs for reverse mapping. MUST be called with session_lock."""
        return self._ws_to_sessions.pop(ws, set())

    # =========================================================================
    # Utility methods
    # =========================================================================

    def get_stats(self) -> dict:
        """Get index statistics for monitoring."""
        return {
            "total_connections": self._total_connections,
            "users_count": len(self._by_user),
            "branches_count": len(self._by_branch),
            "sectors_count": len(self._by_sector),
            "sessions_count": len(self._by_session),
            "admin_connections": sum(len(admins) for admins in self._admins_by_branch.values()),
        }

    def filter_by_tenant(
        self, connections: list["WebSocket"] | set["WebSocket"], tenant_id: int | None
    ) -> list["WebSocket"]:
        """
        Filter connections by tenant ID for multi-tenant isolation.

        Args:
            connections: List or set of WebSocket connections to filter
            tenant_id: Tenant ID to filter by (None = no filtering)

        Returns:
            List of connections belonging to the specified tenant
        """
        if tenant_id is None:
            return list(connections)

        return [
            ws for ws in connections if self._ws_to_tenant.get(ws) == tenant_id
        ]

    def filter_non_admin(self, connections: set["WebSocket"]) -> list["WebSocket"]:
        """
        Filter to get only non-admin connections (waiters only).

        Args:
            connections: Set of WebSocket connections to filter

        Returns:
            List of non-admin connections
        """
        return [ws for ws in connections if not self._ws_is_admin.get(ws, False)]

    # =========================================================================
    # Convenience methods for ConnectionManager (ARCH-AUDIT-01)
    # =========================================================================

    def get_user_connections(self, user_id: int) -> set["WebSocket"]:
        """Get all connections for a user (alias for get_connections_for_user)."""
        return self.get_connections_for_user(user_id)

    def get_branch_connections(self, branch_id: int) -> set["WebSocket"]:
        """Get all connections for a branch (alias for get_connections_for_branch)."""
        return self.get_connections_for_branch(branch_id)

    def get_session_connections(self, session_id: int) -> set["WebSocket"]:
        """Get all connections for a session (alias for get_connections_for_session)."""
        return self.get_connections_for_session(session_id)

    def get_sector_connections(self, sector_id: int) -> set["WebSocket"]:
        """Get all connections for a sector (alias for get_connections_for_sector)."""
        return self.get_connections_for_sector(sector_id)

    def get_admin_connections(self, branch_id: int) -> set["WebSocket"]:
        """Get admin connections for a branch (alias for get_admin_connections_for_branch)."""
        return self.get_admin_connections_for_branch(branch_id)

    def get_kitchen_connections(self, branch_id: int) -> set["WebSocket"]:
        """Get kitchen connections for a branch (alias for get_kitchen_connections_for_branch)."""
        return self.get_kitchen_connections_for_branch(branch_id)

    def get_waiter_connections(self, branch_id: int) -> set["WebSocket"]:
        """Get non-admin, non-kitchen connections for a branch (waiters)."""

        all_branch = self._by_branch.get(branch_id, set())
        admins = self._admins_by_branch.get(branch_id, set())
        kitchen = self._kitchen_by_branch.get(branch_id, set())
        return set(all_branch - admins - kitchen)


    def get_sectors_connections(self, sector_ids: list[int]) -> set["WebSocket"]:
        """Get all connections assigned to any of the given sectors."""
        result: set["WebSocket"] = set()
        for sector_id in sector_ids:
            result.update(self._by_sector.get(sector_id, set()))
        return result

    def get_all_connections(self) -> set["WebSocket"]:
        """Get all registered connections."""
        all_connections: set["WebSocket"] = set()
        for connections in self._by_user.values():
            all_connections.update(connections)
        return all_connections

    def get_active_branch_ids(self) -> set[int]:
        """Get set of branch IDs with active connections."""
        return set(self._by_branch.keys())

    def get_active_user_ids(self) -> set[int]:
        """Get set of user IDs with active connections."""
        return set(self._by_user.keys())

    def register_sectors(self, ws: "WebSocket", sector_ids: list[int]) -> None:
        """
        Register connection for multiple sectors. MUST be called with sector_lock.

        Args:
            ws: WebSocket connection
            sector_ids: List of sector IDs
        """
        self._ws_to_sectors[ws] = sector_ids
        for sector_id in sector_ids:
            if sector_id not in self._by_sector:
                self._by_sector[sector_id] = set()
            self._by_sector[sector_id].add(ws)

    def unregister_sectors(self, ws: "WebSocket", sector_ids: list[int]) -> None:
        """
        Unregister connection from multiple sectors. MUST be called with sector_lock.

        Args:
            ws: WebSocket connection
            sector_ids: List of sector IDs to unregister from
        """
        self._ws_to_sectors.pop(ws, None)
        for sector_id in sector_ids:
            if sector_id in self._by_sector:
                self._by_sector[sector_id].discard(ws)
                if not self._by_sector[sector_id]:
                    del self._by_sector[sector_id]

    def update_sectors(self, ws: "WebSocket", new_sector_ids: list[int]) -> None:
        """
        Update sector assignments for a connection. MUST be called with sector_lock.

        Args:
            ws: WebSocket connection
            new_sector_ids: New list of sector IDs
        """
        # Remove from old sectors
        old_sector_ids = self._ws_to_sectors.get(ws, [])
        for sector_id in old_sector_ids:
            if sector_id in self._by_sector:
                self._by_sector[sector_id].discard(ws)
                if not self._by_sector[sector_id]:
                    del self._by_sector[sector_id]

        # Add to new sectors
        self._ws_to_sectors[ws] = new_sector_ids
        for sector_id in new_sector_ids:
            if sector_id not in self._by_sector:
                self._by_sector[sector_id] = set()
            self._by_sector[sector_id].add(ws)
