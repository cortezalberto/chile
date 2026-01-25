"""
Connection Statistics.

Aggregates statistics from various connection components.
Extracted from ConnectionManager for better maintainability.

ARCH-MODULAR-04: Single Responsibility - statistics aggregation only.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ws_gateway.components.connection.locks import LockManager
    from ws_gateway.components.connection.heartbeat import HeartbeatTracker
    from ws_gateway.components.connection.rate_limiter import WebSocketRateLimiter
    from ws_gateway.components.connection.index import ConnectionIndex
    from ws_gateway.components.metrics.collector import MetricsCollector


class ConnectionStats:
    """
    Aggregates connection statistics from components.

    Provides both async and sync versions for different use cases:
    - Async: For detailed stats in management endpoints
    - Sync: For health check endpoints (non-async context)
    """

    def __init__(
        self,
        lock_manager: "LockManager",
        metrics: "MetricsCollector",
        heartbeat_tracker: "HeartbeatTracker",
        rate_limiter: "WebSocketRateLimiter",
        index: "ConnectionIndex",
        get_total_connections: callable,
        get_dead_connections_count: callable,
        max_total_connections: int,
    ) -> None:
        """
        Initialize stats aggregator with dependencies.

        Args:
            lock_manager: Manages sharded locks
            metrics: Collects connection metrics
            heartbeat_tracker: Tracks connection activity
            rate_limiter: Limits message rates
            index: Connection indexing
            get_total_connections: Callback to get total connection count
            get_dead_connections_count: Callback to get dead connections count
            max_total_connections: Maximum allowed connections
        """
        self._lock_manager = lock_manager
        self._metrics = metrics
        self._heartbeat_tracker = heartbeat_tracker
        self._rate_limiter = rate_limiter
        self._index = index
        self._get_total_connections = get_total_connections
        self._get_dead_connections_count = get_dead_connections_count
        self._max_total_connections = max_total_connections

    async def get_stats(self) -> dict[str, Any]:
        """
        Get comprehensive connection statistics.

        Includes data from all components: locks, heartbeat, rate limiter, index.
        """
        metrics_snapshot = self._metrics.get_snapshot_sync()
        lock_stats = self._lock_manager.get_stats()
        heartbeat_stats = self._heartbeat_tracker.get_stats()
        rate_limiter_stats = self._rate_limiter.get_stats()
        index_stats = self._index.get_stats()

        total = self._get_total_connections()

        return {
            "total_connections": total,
            "max_connections": self._max_total_connections,
            "utilization_percent": round(
                total / max(1, self._max_total_connections) * 100, 1
            ),
            "users_connected": index_stats["users_count"],
            "branches_with_connections": index_stats["branches_count"],
            "sectors_with_connections": index_stats["sectors_count"],
            "sessions_with_connections": index_stats["sessions_count"],
            "admin_connections": index_stats["admin_connections"],
            "dead_connections_pending": self._get_dead_connections_count(),
            "rate_limiter_tracked": rate_limiter_stats["tracked_connections"],
            "branch_locks_count": lock_stats["branch_locks_count"],
            "user_locks_count": lock_stats["user_locks_count"],
            "heartbeat_stats": heartbeat_stats,
            "metrics": metrics_snapshot,
        }

    def get_stats_sync(self) -> dict[str, Any]:
        """
        Get connection statistics (sync version for health check).

        Lighter weight version without async components.
        """
        index_stats = self._index.get_stats()
        total = self._get_total_connections()

        return {
            "total_connections": total,
            "max_connections": self._max_total_connections,
            "utilization_percent": round(
                total / max(1, self._max_total_connections) * 100, 1
            ),
            "users_connected": index_stats["users_count"],
            "branches_with_connections": index_stats["branches_count"],
            "sectors_with_connections": index_stats["sectors_count"],
            "sessions_with_connections": index_stats["sessions_count"],
            "admin_connections": index_stats["admin_connections"],
            "rate_limiter_tracked": self._rate_limiter.tracked_count,
            "branch_locks_count": self._lock_manager.branch_lock_count,
            "user_locks_count": self._lock_manager.user_lock_count,
            "metrics": self._metrics.get_snapshot_sync(),
        }
