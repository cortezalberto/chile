"""
Tenant Filter Service for WebSocket Gateway.

Centralized multi-tenant isolation for WebSocket connections.
Ensures events are only delivered to connections from the same tenant.

ARCH-GOD-02 FIX: Extracted from ConnectionManager (Single Responsibility).
CRIT-NEW-03: Core component for multi-tenant security.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from fastapi import WebSocket


logger = logging.getLogger(__name__)


# =============================================================================
# Protocols
# =============================================================================


class TenantRegistry(Protocol):
    """
    Protocol for tenant-to-connection mapping.

    Components implementing this protocol can use the TenantFilter.
    """

    def get_tenant_id(self, websocket: "WebSocket") -> int | None:
        """Get the tenant ID for a connection, or None if not tracked."""
        ...


# =============================================================================
# Tenant Filter Service
# =============================================================================


class TenantFilter:
    """
    Filters WebSocket connections by tenant for multi-tenant isolation.

    CRIT-NEW-03 FIX: Ensures cross-tenant data isolation by filtering
    connections before message delivery.

    Security Guarantees:
    - Connections without tenant_id are excluded when filtering is enabled
    - Tenant mismatches are logged for security audit
    - Thread-safe (uses connection registry, no internal state)

    Usage:
        filter = TenantFilter(registry)
        filtered = filter.filter_connections(connections, tenant_id=1)
    """

    def __init__(
        self,
        registry: TenantRegistry,
        strict_mode: bool = True,
    ) -> None:
        """
        Initialize tenant filter.

        Args:
            registry: Registry that maps connections to tenant IDs.
            strict_mode: If True, connections without tenant_id are excluded.
                        If False, connections without tenant_id pass through.
        """
        self._registry = registry
        self._strict_mode = strict_mode
        self._filtered_count = 0  # Metrics: total connections filtered out
        self._bypass_count = 0    # Metrics: filter bypasses (tenant_id=None)

    @property
    def filtered_count(self) -> int:
        """Total connections filtered out due to tenant mismatch."""
        return self._filtered_count

    @property
    def bypass_count(self) -> int:
        """Total filter bypasses (when tenant_id is None)."""
        return self._bypass_count

    def filter_connections(
        self,
        connections: list["WebSocket"],
        tenant_id: int | None,
    ) -> list["WebSocket"]:
        """
        Filter connections to only those belonging to the specified tenant.

        Args:
            connections: List of WebSocket connections to filter.
            tenant_id: Tenant ID to filter by. If None, returns all connections
                       (tenant filtering bypassed).

        Returns:
            Filtered list of connections. Empty list if no matches.

        Note:
            When tenant_id is None, all connections pass through (no filtering).
            This is intentional for system-wide broadcasts that don't need
            tenant isolation.
        """
        if tenant_id is None:
            self._bypass_count += 1
            return connections

        if not connections:
            return []

        filtered: list["WebSocket"] = []
        excluded_count = 0

        for ws in connections:
            ws_tenant = self._registry.get_tenant_id(ws)

            if ws_tenant is None:
                # Connection has no tenant_id
                if not self._strict_mode:
                    # Non-strict: include connections without tenant
                    filtered.append(ws)
                else:
                    # Strict: exclude connections without tenant
                    excluded_count += 1
                continue

            if ws_tenant == tenant_id:
                filtered.append(ws)
            else:
                excluded_count += 1

        if excluded_count > 0:
            self._filtered_count += excluded_count
            logger.debug(
                "Tenant filter excluded connections",
                tenant_id=tenant_id,
                excluded=excluded_count,
                included=len(filtered),
            )

        return filtered

    def validate_tenant_access(
        self,
        websocket: "WebSocket",
        expected_tenant_id: int,
    ) -> bool:
        """
        Validate that a connection belongs to the expected tenant.

        Useful for request-level tenant validation before operations.

        Args:
            websocket: WebSocket connection to validate.
            expected_tenant_id: Expected tenant ID.

        Returns:
            True if connection belongs to expected tenant, False otherwise.
        """
        ws_tenant = self._registry.get_tenant_id(websocket)

        if ws_tenant is None:
            logger.warning(
                "Tenant validation failed: connection has no tenant_id",
                expected_tenant=expected_tenant_id,
            )
            return False

        if ws_tenant != expected_tenant_id:
            logger.warning(
                "Tenant validation failed: mismatch",
                expected_tenant=expected_tenant_id,
                actual_tenant=ws_tenant,
            )
            return False

        return True

    def get_stats(self) -> dict[str, Any]:
        """Get tenant filter statistics."""
        return {
            "filtered_count": self._filtered_count,
            "bypass_count": self._bypass_count,
            "strict_mode": self._strict_mode,
        }

    def reset_stats(self) -> dict[str, Any]:
        """Reset statistics and return previous values."""
        stats = self.get_stats()
        self._filtered_count = 0
        self._bypass_count = 0
        return stats


# =============================================================================
# Tenant-Aware Broadcast Wrapper
# =============================================================================


class TenantAwareBroadcaster:
    """
    Wraps broadcast operations with automatic tenant filtering.

    CRIT-NEW-03 FIX: Ensures all broadcasts are tenant-isolated.

    Usage:
        broadcaster = TenantAwareBroadcaster(filter, router)
        await broadcaster.send_to_branch(branch_id, payload, tenant_id=1)
    """

    def __init__(
        self,
        tenant_filter: TenantFilter,
        broadcast_func: Any,  # Callable for actual broadcast
    ) -> None:
        """
        Initialize tenant-aware broadcaster.

        Args:
            tenant_filter: TenantFilter instance.
            broadcast_func: Function to perform actual broadcast.
        """
        self._filter = tenant_filter
        self._broadcast = broadcast_func

    async def send_filtered(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        tenant_id: int | None,
        context: str = "broadcast",
    ) -> int:
        """
        Send to connections after tenant filtering.

        Args:
            connections: Connections to potentially send to.
            payload: Message payload.
            tenant_id: Tenant ID to filter by.
            context: Context for logging.

        Returns:
            Number of connections that received the message.
        """
        filtered = self._filter.filter_connections(connections, tenant_id)
        return await self._broadcast(filtered, payload, context)


# =============================================================================
# Factory Functions
# =============================================================================


def create_tenant_filter(
    registry: TenantRegistry,
    strict_mode: bool = True,
) -> TenantFilter:
    """
    Create a TenantFilter with specified configuration.

    Args:
        registry: Registry mapping connections to tenants.
        strict_mode: Whether to exclude connections without tenant_id.

    Returns:
        Configured TenantFilter.
    """
    return TenantFilter(registry=registry, strict_mode=strict_mode)
