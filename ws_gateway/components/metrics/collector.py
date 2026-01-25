"""
Metrics Collector for WebSocket Gateway.

Centralizes metrics collection for observability.
Thread-safe counter operations for concurrent access.

ARCH-01 FIX: Extracted from ConnectionManager (Single Responsibility).
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field  # LOW-WS-05 NOTE: field is used in @dataclass definitions below
from typing import Any


@dataclass
class BroadcastMetrics:
    """Metrics for broadcast operations."""
    total: int = 0
    failed: int = 0
    recipients_failed: int = 0
    rate_limited: int = 0  # HIGH-NEW-01 FIX: Track rate-limited broadcasts


@dataclass
class ConnectionMetrics:
    """Metrics for connection management."""
    rejected_limit: int = 0
    rejected_rate_limit: int = 0
    rejected_auth: int = 0
    timeouts: int = 0


@dataclass
class EventMetrics:
    """Metrics for event processing."""
    processed: int = 0
    dropped: int = 0
    invalid_schema: int = 0
    callback_timeouts: int = 0


class MetricsCollector:
    """
    Thread-safe metrics collector for WebSocket Gateway.

    Provides atomic increment operations and snapshot retrieval.

    Usage:
        metrics = MetricsCollector()
        metrics.increment_broadcast_total()
        stats = metrics.get_snapshot()
    """

    def __init__(self):
        """Initialize metrics collector."""
        self._lock = asyncio.Lock()
        # CRIT-WS-08 FIX: Add threading lock for sync methods
        # Ensures thread safety even in non-GIL Python implementations (PyPy, etc.)
        self._sync_lock = threading.Lock()
        self._broadcast = BroadcastMetrics()
        self._connection = ConnectionMetrics()
        self._event = EventMetrics()
        self._locks_cleaned = 0
        self._custom: dict[str, int] = {}

    # ==========================================================================
    # Broadcast Metrics
    # ==========================================================================

    async def increment_broadcast_total(self) -> None:
        """Increment total broadcast count."""
        async with self._lock:
            self._broadcast.total += 1

    async def increment_broadcast_failed(self) -> None:
        """Increment failed broadcast count."""
        async with self._lock:
            self._broadcast.failed += 1

    async def add_failed_recipients(self, count: int) -> None:
        """Add count of failed recipients in a broadcast."""
        async with self._lock:
            self._broadcast.recipients_failed += count

    def increment_broadcast_total_sync(self) -> None:
        """
        Increment total broadcast count (sync version for hot path).

        CRIT-WS-08 FIX: Uses threading.Lock for thread safety in all Python implementations.
        """
        with self._sync_lock:
            self._broadcast.total += 1

    def increment_broadcast_failed_sync(self) -> None:
        """
        Increment failed broadcast count (sync version).

        CRIT-WS-08 FIX: Uses threading.Lock for thread safety.
        """
        with self._sync_lock:
            self._broadcast.failed += 1

    def add_failed_recipients_sync(self, count: int) -> None:
        """
        Add failed recipients count (sync version).

        CRIT-WS-08 FIX: Uses threading.Lock for thread safety.
        """
        with self._sync_lock:
            self._broadcast.recipients_failed += count

    def increment_broadcast_rate_limited_sync(self) -> None:
        """
        Increment rate-limited broadcasts count (sync version).

        CRIT-WS-08 FIX: Uses threading.Lock for thread safety.
        """
        with self._sync_lock:
            self._broadcast.rate_limited += 1

    # ==========================================================================
    # Connection Metrics
    # ==========================================================================

    async def increment_connection_rejected_limit(self) -> None:
        """Increment count of connections rejected due to limit."""
        async with self._lock:
            self._connection.rejected_limit += 1

    async def increment_connection_rejected_rate_limit(self) -> None:
        """Increment count of connections rejected due to rate limiting."""
        async with self._lock:
            self._connection.rejected_rate_limit += 1

    async def increment_connection_rejected_auth(self) -> None:
        """Increment count of connections rejected due to auth failure."""
        async with self._lock:
            self._connection.rejected_auth += 1

    async def increment_connection_timeouts(self) -> None:
        """Increment count of connection timeouts."""
        async with self._lock:
            self._connection.timeouts += 1

    def increment_connection_rejected_limit_sync(self) -> None:
        """Increment connection rejected limit (sync version). CRIT-WS-08 FIX."""
        with self._sync_lock:
            self._connection.rejected_limit += 1

    def increment_connection_rejected_rate_limit_sync(self) -> None:
        """Increment connection rejected rate limit (sync version). CRIT-WS-08 FIX."""
        with self._sync_lock:
            self._connection.rejected_rate_limit += 1

    # ==========================================================================
    # Event Metrics
    # ==========================================================================

    async def increment_events_processed(self) -> None:
        """Increment count of events processed."""
        async with self._lock:
            self._event.processed += 1

    async def increment_events_dropped(self) -> None:
        """Increment count of events dropped due to queue full."""
        async with self._lock:
            self._event.dropped += 1

    async def increment_events_invalid_schema(self) -> None:
        """Increment count of events with invalid schema."""
        async with self._lock:
            self._event.invalid_schema += 1

    async def increment_callback_timeouts(self) -> None:
        """Increment count of callback timeouts."""
        async with self._lock:
            self._event.callback_timeouts += 1

    def increment_events_dropped_sync(self) -> None:
        """Increment events dropped (sync version). CRIT-WS-08 FIX."""
        with self._sync_lock:
            self._event.dropped += 1

    # ==========================================================================
    # Lock Metrics
    # ==========================================================================

    async def add_locks_cleaned(self, count: int) -> None:
        """Add count of locks cleaned."""
        async with self._lock:
            self._locks_cleaned += count

    def add_locks_cleaned_sync(self, count: int) -> None:
        """Add locks cleaned count (sync version). CRIT-WS-08 FIX."""
        with self._sync_lock:
            self._locks_cleaned += count

    # ==========================================================================
    # Custom Metrics
    # ==========================================================================

    async def increment_custom(self, name: str, count: int = 1) -> None:
        """Increment a custom metric by name."""
        async with self._lock:
            self._custom[name] = self._custom.get(name, 0) + count

    def increment_custom_sync(self, name: str, count: int = 1) -> None:
        """Increment custom metric (sync version). CRIT-WS-08 FIX."""
        with self._sync_lock:
            self._custom[name] = self._custom.get(name, 0) + count

    # ==========================================================================
    # Snapshot
    # ==========================================================================

    async def get_snapshot(self) -> dict[str, Any]:
        """
        Get a snapshot of all metrics.

        Returns a copy to prevent modification of internal state.
        """
        async with self._lock:
            return self._get_snapshot_internal()

    def get_snapshot_sync(self) -> dict[str, Any]:
        """Get metrics snapshot (sync version for health checks). CRIT-WS-08 FIX."""
        with self._sync_lock:
            return self._get_snapshot_internal()

    def _get_snapshot_internal(self) -> dict[str, Any]:
        """
        Internal method to build snapshot dict.

        LOW-AUD-03 FIX: Metric names follow consistent pattern:
        {category}_{metric} where category is plural (broadcasts, connections, events).
        """
        return {
            # Broadcast metrics
            "broadcasts_total": self._broadcast.total,
            "broadcasts_failed": self._broadcast.failed,
            "broadcasts_failed_recipients": self._broadcast.recipients_failed,  # LOW-AUD-03 FIX
            "broadcasts_rate_limited": self._broadcast.rate_limited,
            # Connection metrics
            "connections_rejected_limit": self._connection.rejected_limit,
            "connections_rejected_rate_limit": self._connection.rejected_rate_limit,
            "connections_rejected_auth": self._connection.rejected_auth,
            "connections_timeouts": self._connection.timeouts,  # LOW-AUD-03 FIX
            # Event metrics
            "events_processed": self._event.processed,
            "events_dropped": self._event.dropped,
            "events_invalid_schema": self._event.invalid_schema,
            "events_callback_timeouts": self._event.callback_timeouts,  # LOW-AUD-03 FIX
            # Other metrics
            "locks_cleaned": self._locks_cleaned,
            **self._custom,
        }

    async def reset(self) -> dict[str, Any]:
        """
        Reset all metrics and return the previous values.

        Useful for periodic metric collection systems.
        """
        async with self._lock:
            snapshot = self._get_snapshot_internal()
            self._broadcast = BroadcastMetrics()
            self._connection = ConnectionMetrics()
            self._event = EventMetrics()
            self._locks_cleaned = 0
            self._custom.clear()
            return snapshot
