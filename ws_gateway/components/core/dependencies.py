"""
FastAPI Dependencies for WebSocket Gateway.

Centralizes dependency injection for better testability and configuration.
All dependencies are created as singletons or factories.

ARCH-OPP-03 FIX: Implemented FastAPI Depends for dependency injection.
"""

from __future__ import annotations

import threading
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from fastapi import Depends

from shared.config.settings import settings
from ws_gateway.components.core.constants import WSConstants
from ws_gateway.components.connection.locks import LockManager
from ws_gateway.components.metrics.collector import MetricsCollector
from ws_gateway.components.connection.heartbeat import HeartbeatTracker
from ws_gateway.components.connection.rate_limiter import WebSocketRateLimiter
from ws_gateway.components.data.sector_repository import (
    SectorAssignmentRepository,
    get_sector_repository,
)
from ws_gateway.components.broadcast.router import (
    BroadcastRouter,
    BatchBroadcastStrategy,
    AdaptiveBatchStrategy,
    create_default_router,
)
from ws_gateway.components.broadcast.tenant_filter import TenantFilter
from ws_gateway.components.auth.strategies import (
    AuthStrategy,
    JWTAuthStrategy,
    TableTokenAuthStrategy,
    create_waiter_auth_strategy,
    create_kitchen_auth_strategy,
    create_admin_auth_strategy,
    create_diner_auth_strategy,
)

if TYPE_CHECKING:
    from ws_gateway.connection_manager import ConnectionManager


# =============================================================================
# Singleton Instances
# =============================================================================

_lock_manager: LockManager | None = None
_metrics_collector: MetricsCollector | None = None
_heartbeat_tracker: HeartbeatTracker | None = None
_rate_limiter: WebSocketRateLimiter | None = None
_singleton_lock = threading.Lock()


# =============================================================================
# Component Factories (Thread-safe singletons)
# =============================================================================


def get_lock_manager() -> LockManager:
    """
    Get singleton LockManager instance.

    Thread-safe with double-check locking.
    """
    global _lock_manager
    if _lock_manager is None:
        with _singleton_lock:
            if _lock_manager is None:
                _lock_manager = LockManager()
    return _lock_manager


def get_metrics_collector() -> MetricsCollector:
    """
    Get singleton MetricsCollector instance.

    Thread-safe with double-check locking.
    """
    global _metrics_collector
    if _metrics_collector is None:
        with _singleton_lock:
            if _metrics_collector is None:
                _metrics_collector = MetricsCollector()
    return _metrics_collector


def get_heartbeat_tracker() -> HeartbeatTracker:
    """
    Get singleton HeartbeatTracker instance.

    Thread-safe with double-check locking.
    """
    global _heartbeat_tracker
    if _heartbeat_tracker is None:
        with _singleton_lock:
            if _heartbeat_tracker is None:
                _heartbeat_tracker = HeartbeatTracker(
                    timeout_seconds=settings.ws_heartbeat_timeout,
                )
    return _heartbeat_tracker


def get_rate_limiter() -> WebSocketRateLimiter:
    """
    Get singleton WebSocketRateLimiter instance.

    Thread-safe with double-check locking.
    """
    global _rate_limiter
    if _rate_limiter is None:
        with _singleton_lock:
            if _rate_limiter is None:
                _rate_limiter = WebSocketRateLimiter(
                    max_messages=settings.ws_message_rate_limit,
                    window_seconds=settings.ws_message_rate_window,
                )
    return _rate_limiter


# =============================================================================
# Cached Factory Functions
# =============================================================================


@lru_cache(maxsize=1)
def get_waiter_auth() -> JWTAuthStrategy:
    """Get cached waiter authentication strategy."""
    return create_waiter_auth_strategy()


@lru_cache(maxsize=1)
def get_kitchen_auth() -> JWTAuthStrategy:
    """Get cached kitchen authentication strategy."""
    return create_kitchen_auth_strategy()


@lru_cache(maxsize=1)
def get_admin_auth() -> JWTAuthStrategy:
    """Get cached admin authentication strategy."""
    return create_admin_auth_strategy()


@lru_cache(maxsize=1)
def get_diner_auth() -> TableTokenAuthStrategy:
    """Get cached diner authentication strategy."""
    return create_diner_auth_strategy()


# =============================================================================
# FastAPI Dependency Functions
# =============================================================================


async def get_lock_manager_dep() -> LockManager:
    """FastAPI dependency for LockManager."""
    return get_lock_manager()


async def get_metrics_dep() -> MetricsCollector:
    """FastAPI dependency for MetricsCollector."""
    return get_metrics_collector()


async def get_heartbeat_dep() -> HeartbeatTracker:
    """FastAPI dependency for HeartbeatTracker."""
    return get_heartbeat_tracker()


async def get_rate_limiter_dep() -> WebSocketRateLimiter:
    """FastAPI dependency for WebSocketRateLimiter."""
    return get_rate_limiter()


async def get_sector_repository_dep() -> SectorAssignmentRepository:
    """FastAPI dependency for SectorAssignmentRepository."""
    return get_sector_repository()


async def get_waiter_auth_dep() -> JWTAuthStrategy:
    """FastAPI dependency for waiter auth strategy."""
    return get_waiter_auth()


async def get_kitchen_auth_dep() -> JWTAuthStrategy:
    """FastAPI dependency for kitchen auth strategy."""
    return get_kitchen_auth()


async def get_admin_auth_dep() -> JWTAuthStrategy:
    """FastAPI dependency for admin auth strategy."""
    return get_admin_auth()


async def get_diner_auth_dep() -> TableTokenAuthStrategy:
    """FastAPI dependency for diner auth strategy."""
    return get_diner_auth()


# =============================================================================
# Connection Manager Dependencies
# =============================================================================


class ConnectionManagerDependencies:
    """
    Container for ConnectionManager dependencies.

    ARCH-OPP-03 FIX: Allows injecting mock dependencies for testing.

    Usage:
        deps = ConnectionManagerDependencies()
        manager = ConnectionManager(deps=deps)

        # For testing:
        mock_deps = ConnectionManagerDependencies(
            metrics=MockMetricsCollector(),
        )
        manager = ConnectionManager(deps=mock_deps)
    """

    def __init__(
        self,
        lock_manager: LockManager | None = None,
        metrics: MetricsCollector | None = None,
        heartbeat_tracker: HeartbeatTracker | None = None,
        rate_limiter: WebSocketRateLimiter | None = None,
    ) -> None:
        """
        Initialize dependencies.

        If None, uses singleton instances.

        Args:
            lock_manager: Optional custom LockManager.
            metrics: Optional custom MetricsCollector.
            heartbeat_tracker: Optional custom HeartbeatTracker.
            rate_limiter: Optional custom WebSocketRateLimiter.
        """
        self.lock_manager = lock_manager or get_lock_manager()
        self.metrics = metrics or get_metrics_collector()
        self.heartbeat_tracker = heartbeat_tracker or get_heartbeat_tracker()
        self.rate_limiter = rate_limiter or get_rate_limiter()


def get_connection_manager_deps() -> ConnectionManagerDependencies:
    """Get default ConnectionManager dependencies."""
    return ConnectionManagerDependencies()


# =============================================================================
# Cleanup Functions (for testing)
# =============================================================================


def reset_singletons() -> None:
    """
    Reset all singleton instances.

    Useful for testing to ensure clean state between tests.
    """
    global _lock_manager, _metrics_collector, _heartbeat_tracker, _rate_limiter

    with _singleton_lock:
        _lock_manager = None
        _metrics_collector = None
        _heartbeat_tracker = None
        _rate_limiter = None

    # Clear lru_cache
    get_waiter_auth.cache_clear()
    get_kitchen_auth.cache_clear()
    get_admin_auth.cache_clear()
    get_diner_auth.cache_clear()


# =============================================================================
# Type aliases for dependency injection
# =============================================================================

# These can be used with Depends() in FastAPI endpoints
LockManagerDep = Depends(get_lock_manager_dep)
MetricsDep = Depends(get_metrics_dep)
HeartbeatDep = Depends(get_heartbeat_dep)
RateLimiterDep = Depends(get_rate_limiter_dep)
SectorRepositoryDep = Depends(get_sector_repository_dep)
WaiterAuthDep = Depends(get_waiter_auth_dep)
KitchenAuthDep = Depends(get_kitchen_auth_dep)
AdminAuthDep = Depends(get_admin_auth_dep)
DinerAuthDep = Depends(get_diner_auth_dep)
