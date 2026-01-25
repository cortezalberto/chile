"""
Broadcast Router for WebSocket Gateway.

Extracts broadcast logic from ConnectionManager into a dedicated component.
Implements Strategy pattern for flexible routing strategies.

ARCH-GOD-01 FIX: Extracted from ConnectionManager (Single Responsibility).
PATTERN: Strategy - Different broadcast routing strategies.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections import deque
from typing import TYPE_CHECKING, Any, Protocol

from starlette.websockets import WebSocketState

from ws_gateway.components.core.constants import WSConstants

if TYPE_CHECKING:
    from fastapi import WebSocket


logger = logging.getLogger(__name__)


# =============================================================================
# Protocols
# =============================================================================


class MetricsRecorder(Protocol):
    """Protocol for metrics recording (legacy, use BroadcastObserver for new code)."""

    def increment_broadcast_total_sync(self) -> None:
        """Increment total broadcast count."""
        ...

    def increment_broadcast_failed_sync(self) -> None:
        """Increment failed broadcast count."""
        ...

    def add_failed_recipients_sync(self, count: int) -> None:
        """Add count of failed recipients."""
        ...

    def increment_broadcast_rate_limited_sync(self) -> None:
        """Increment rate-limited broadcasts count."""
        ...


class BroadcastObserver(Protocol):
    """
    MED-02 FIX: Observer pattern for broadcast events.

    PATTERN: Observer - Decouples broadcast logic from metrics/logging concerns.

    Implementations can:
    - Record metrics (MetricsCollector adapter)
    - Log broadcast events
    - Trigger alerts on failures
    - Update dashboards in real-time

    Usage:
        class AlertingObserver:
            def on_broadcast_complete(self, sent, failed, context):
                if failed > sent * 0.1:  # >10% failure rate
                    alert_ops_team(context, failed)

            def on_broadcast_rate_limited(self, context):
                log.warning("Rate limited", context=context)

        router.add_observer(AlertingObserver())
    """

    def on_broadcast_complete(self, sent: int, failed: int, context: str) -> None:
        """Called after broadcast completes."""
        ...

    def on_broadcast_rate_limited(self, context: str) -> None:
        """Called when broadcast is rate limited."""
        ...


class MetricsObserverAdapter:
    """
    Adapter to use existing MetricsRecorder as BroadcastObserver.

    MED-02 FIX: Bridges legacy MetricsRecorder to new Observer pattern
    for backward compatibility.
    """

    def __init__(self, metrics: MetricsRecorder) -> None:
        self._metrics = metrics

    def on_broadcast_complete(self, sent: int, failed: int, context: str) -> None:
        """Record broadcast metrics."""
        self._metrics.increment_broadcast_total_sync()
        if failed > 0:
            self._metrics.increment_broadcast_failed_sync()
            self._metrics.add_failed_recipients_sync(failed)

    def on_broadcast_rate_limited(self, context: str) -> None:
        """Record rate limit event."""
        self._metrics.increment_broadcast_rate_limited_sync()


class DeadConnectionTracker(Protocol):
    """Protocol for tracking dead connections."""

    async def mark_dead(self, ws: "WebSocket") -> None:
        """Mark a connection as dead for later cleanup."""
        ...


# =============================================================================
# Helper Functions
# =============================================================================


def is_ws_connected(ws: "WebSocket") -> bool:
    """
    Check if WebSocket is in connected state before sending.

    MED-WS-02 NOTE: This checks for CONNECTED state only.
    Starlette WebSockets have limited state visibility.
    """
    return (
        ws.client_state == WebSocketState.CONNECTED
        and ws.application_state == WebSocketState.CONNECTED
    )


# =============================================================================
# Broadcast Strategy Interface
# =============================================================================


class BroadcastStrategy(ABC):
    """
    Abstract base class for broadcast strategies.

    PATTERN: Strategy - Different algorithms for broadcast delivery.
    MED-01 FIX: Extracted common _send_single method to base class (DRY).
    """

    def __init__(self, dead_tracker: DeadConnectionTracker | None = None) -> None:
        """
        Initialize broadcast strategy.

        Args:
            dead_tracker: Optional tracker for marking dead connections.
        """
        self._dead_tracker = dead_tracker

    async def _send_single(
        self,
        ws: "WebSocket",
        payload: dict[str, Any],
    ) -> bool:
        """
        Send to a single connection.

        MED-01 FIX: Common implementation moved from concrete strategies
        to base class to avoid code duplication.

        Args:
            ws: WebSocket connection to send to.
            payload: Message payload.

        Returns:
            True if successful, False otherwise.
        """
        if not is_ws_connected(ws):
            if self._dead_tracker:
                await self._dead_tracker.mark_dead(ws)
            return False

        try:
            await ws.send_json(payload)
            return True
        except Exception as e:
            logger.debug("Send failed: %s", str(e))
            if self._dead_tracker:
                await self._dead_tracker.mark_dead(ws)
            return False

    @abstractmethod
    async def send_to_connections(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str,
    ) -> tuple[int, int]:
        """
        Send payload to connections.

        Args:
            connections: WebSocket connections to send to.
            payload: Message payload.
            context: Context string for logging.

        Returns:
            Tuple of (sent_count, failed_count).
        """
        ...


# =============================================================================
# Batch Broadcast Strategy
# =============================================================================


class BatchBroadcastStrategy(BroadcastStrategy):
    """
    Broadcast strategy using parallel batches.

    LOAD-LEVEL2: Processes connections in parallel batches
    for optimal performance with many connections.
    MED-01 FIX: Uses _send_single from base class (DRY).
    """

    def __init__(
        self,
        batch_size: int,
        dead_tracker: DeadConnectionTracker | None = None,
    ) -> None:
        """
        Initialize batch broadcast strategy.

        Args:
            batch_size: Number of connections per batch.
            dead_tracker: Optional tracker for dead connections.
        """
        super().__init__(dead_tracker=dead_tracker)
        self._batch_size = batch_size

    async def send_to_connections(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str,
    ) -> tuple[int, int]:
        """Send to connections in parallel batches."""
        if not connections:
            return 0, 0

        sent = 0
        failed = 0

        # Process in batches
        for i in range(0, len(connections), self._batch_size):
            batch = connections[i:i + self._batch_size]
            results = await asyncio.gather(
                *[self._send_single(ws, payload) for ws in batch],
                return_exceptions=True,
            )

            for idx, result in enumerate(results):
                if result is True:
                    sent += 1
                else:
                    failed += 1
                    if isinstance(result, Exception):
                        logger.debug(
                            "Batch send exception",
                            context=context,
                            batch_index=idx,
                            error=str(result),
                        )

        return sent, failed


# =============================================================================
# Adaptive Batch Strategy
# =============================================================================


class AdaptiveBatchStrategy(BroadcastStrategy):
    """
    Broadcast strategy with adaptive batch sizing.

    ARCH-OPP-09: Adjusts batch size based on observed latency
    to optimize throughput dynamically.
    MED-01 FIX: Uses _send_single from base class (DRY).
    """

    def __init__(
        self,
        min_batch_size: int = 10,
        max_batch_size: int = 100,
        target_latency_ms: float = 50.0,
        dead_tracker: DeadConnectionTracker | None = None,
    ) -> None:
        """
        Initialize adaptive batch strategy.

        Args:
            min_batch_size: Minimum connections per batch.
            max_batch_size: Maximum connections per batch.
            target_latency_ms: Target latency per batch.
            dead_tracker: Optional tracker for dead connections.
        """
        super().__init__(dead_tracker=dead_tracker)
        self._min_batch_size = min_batch_size
        self._max_batch_size = max_batch_size
        self._target_latency_ms = target_latency_ms
        self._current_batch_size = min_batch_size
        self._latency_ema: float = 0.0  # Exponential moving average
        self._ema_alpha = 0.3  # Smoothing factor

    @property
    def current_batch_size(self) -> int:
        """Current batch size being used."""
        return self._current_batch_size

    def _adjust_batch_size(self, batch_latency_ms: float) -> None:
        """Adjust batch size based on observed latency."""
        # Update exponential moving average
        if self._latency_ema == 0.0:
            self._latency_ema = batch_latency_ms
        else:
            self._latency_ema = (
                self._ema_alpha * batch_latency_ms +
                (1 - self._ema_alpha) * self._latency_ema
            )

        # Adjust batch size
        if self._latency_ema < self._target_latency_ms * 0.5:
            # Latency is low, increase batch size
            self._current_batch_size = min(
                self._max_batch_size,
                int(self._current_batch_size * 1.2),
            )
        elif self._latency_ema > self._target_latency_ms * 1.5:
            # Latency is high, decrease batch size
            self._current_batch_size = max(
                self._min_batch_size,
                int(self._current_batch_size * 0.8),
            )

    async def send_to_connections(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str,
    ) -> tuple[int, int]:
        """Send to connections with adaptive batching."""
        if not connections:
            return 0, 0

        sent = 0
        failed = 0

        # Process in adaptive batches
        for i in range(0, len(connections), self._current_batch_size):
            batch = connections[i:i + self._current_batch_size]

            start_time = time.perf_counter()
            results = await asyncio.gather(
                *[self._send_single(ws, payload) for ws in batch],
                return_exceptions=True,
            )
            batch_latency_ms = (time.perf_counter() - start_time) * 1000

            # Adjust batch size based on latency
            self._adjust_batch_size(batch_latency_ms)

            for result in results:
                if result is True:
                    sent += 1
                else:
                    failed += 1

        return sent, failed

    def get_stats(self) -> dict[str, Any]:
        """Get adaptive batch strategy stats."""
        return {
            "current_batch_size": self._current_batch_size,
            "latency_ema_ms": round(self._latency_ema, 2),
            "min_batch_size": self._min_batch_size,
            "max_batch_size": self._max_batch_size,
            "target_latency_ms": self._target_latency_ms,
        }


# =============================================================================
# Broadcast Router
# =============================================================================


class BroadcastRouter:
    """
    Routes broadcasts to WebSocket connections.

    ARCH-GOD-01 FIX: Extracted broadcast logic from ConnectionManager.
    MED-02 FIX: Added Observer pattern for decoupled event handling.

    PATTERNS:
    - Strategy: Flexible broadcast delivery algorithms
    - Observer: Decoupled metrics/alerting/logging

    Responsibilities:
    - Route messages to connections
    - Notify observers of broadcast events
    - Rate limit global broadcasts
    """

    def __init__(
        self,
        strategy: BroadcastStrategy,
        metrics: MetricsRecorder | None = None,
        rate_limit: int = WSConstants.MAX_BROADCASTS_PER_SECOND,
        observers: list[BroadcastObserver] | None = None,
    ) -> None:
        """
        Initialize broadcast router.

        Args:
            strategy: Broadcast strategy to use.
            metrics: Optional metrics recorder (legacy, prefer observers).
            rate_limit: Max global broadcasts per second.
            observers: List of broadcast observers.
        """
        self._strategy = strategy
        self._rate_limit = rate_limit
        # Deque for O(1) append with automatic cleanup
        self._broadcast_timestamps: deque[float] = deque(maxlen=rate_limit * 2)

        # MED-02 FIX: Observer pattern for decoupled event handling
        self._observers: list[BroadcastObserver] = list(observers) if observers else []

        # Backward compatibility: wrap legacy metrics in observer adapter
        if metrics is not None:
            self._observers.append(MetricsObserverAdapter(metrics))

    @property
    def strategy(self) -> BroadcastStrategy:
        """Current broadcast strategy."""
        return self._strategy

    def set_strategy(self, strategy: BroadcastStrategy) -> None:
        """
        Change broadcast strategy at runtime.

        PATTERN: Strategy - Allows switching algorithms dynamically.
        """
        self._strategy = strategy

    def add_observer(self, observer: BroadcastObserver) -> None:
        """
        Add a broadcast observer.

        MED-02 FIX: Observer pattern allows adding listeners without
        modifying router code.

        Args:
            observer: Observer to add.
        """
        self._observers.append(observer)

    def remove_observer(self, observer: BroadcastObserver) -> bool:
        """
        Remove a broadcast observer.

        Args:
            observer: Observer to remove.

        Returns:
            True if observer was removed, False if not found.
        """
        try:
            self._observers.remove(observer)
            return True
        except ValueError:
            return False

    def _notify_broadcast_complete(self, sent: int, failed: int, context: str) -> None:
        """Notify all observers of broadcast completion."""
        for observer in self._observers:
            try:
                observer.on_broadcast_complete(sent, failed, context)
            except Exception as e:
                logger.warning("Observer error on broadcast_complete", error=str(e))

    def _notify_rate_limited(self, context: str) -> None:
        """Notify all observers of rate limiting."""
        for observer in self._observers:
            try:
                observer.on_broadcast_rate_limited(context)
            except Exception as e:
                logger.warning("Observer error on rate_limited", error=str(e))

    async def broadcast_to_connections(
        self,
        connections: list["WebSocket"],
        payload: dict[str, Any],
        context: str = "broadcast",
    ) -> int:
        """
        Send payload to a list of connections.

        Args:
            connections: List of WebSocket connections.
            payload: Message payload.
            context: Context string for logging.

        Returns:
            Number of connections that received the message.
        """
        if not connections:
            return 0

        sent, failed = await self._strategy.send_to_connections(
            connections, payload, context
        )

        # MED-02 FIX: Notify observers instead of direct metrics call
        self._notify_broadcast_complete(sent, failed, context)

        if failed > 0:
            logger.debug(
                "Broadcast completed with failures",
                context=context,
                sent=sent,
                failed=failed,
                total=len(connections),
            )

        return sent

    async def broadcast_global(
        self,
        connections_by_user: dict[int, set["WebSocket"]],
        payload: dict[str, Any],
    ) -> int:
        """
        Broadcast to all connections with rate limiting.

        HIGH-NEW-01 FIX: Rate limiting prevents broadcast spam.

        Args:
            connections_by_user: Dict mapping user IDs to their connections.
            payload: Message payload.

        Returns:
            Number of connections that received the message.
        """
        now = time.time()
        window_start = now - 1.0

        # Count recent broadcasts
        recent_count = sum(1 for ts in self._broadcast_timestamps if ts > window_start)

        if recent_count >= self._rate_limit:
            logger.warning(
                "Broadcast rate limit exceeded, dropping message",
                current_rate=recent_count,
                limit=self._rate_limit,
                payload_type=payload.get("type"),
            )
            # MED-02 FIX: Notify observers of rate limiting
            self._notify_rate_limited("global")
            return 0

        # Record timestamp (O(1) due to deque)
        self._broadcast_timestamps.append(now)

        # Collect all connections
        all_connections: set["WebSocket"] = set()
        for connections in connections_by_user.values():
            all_connections.update(connections)

        return await self.broadcast_to_connections(
            list(all_connections), payload, "global"
        )

    def get_stats(self) -> dict[str, Any]:
        """Get broadcast router statistics."""
        now = time.time()
        recent_count = sum(
            1 for ts in self._broadcast_timestamps
            if ts > now - 1.0
        )

        stats: dict[str, Any] = {
            "rate_limit": self._rate_limit,
            "recent_broadcasts": recent_count,
            "strategy_type": type(self._strategy).__name__,
            "observer_count": len(self._observers),  # MED-02 FIX
        }

        # Add strategy-specific stats if available
        if hasattr(self._strategy, "get_stats"):
            stats["strategy_stats"] = self._strategy.get_stats()

        return stats


# =============================================================================
# Factory Functions
# =============================================================================


def create_default_router(
    batch_size: int,
    metrics: MetricsRecorder | None = None,
    dead_tracker: DeadConnectionTracker | None = None,
    observers: list[BroadcastObserver] | None = None,
) -> BroadcastRouter:
    """
    Create a broadcast router with default batch strategy.

    Args:
        batch_size: Connections per batch.
        metrics: Optional metrics recorder (legacy, prefer observers).
        dead_tracker: Optional dead connection tracker.
        observers: Optional list of broadcast observers.

    Returns:
        Configured BroadcastRouter.
    """
    strategy = BatchBroadcastStrategy(
        batch_size=batch_size,
        dead_tracker=dead_tracker,
    )
    return BroadcastRouter(strategy=strategy, metrics=metrics, observers=observers)


def create_adaptive_router(
    metrics: MetricsRecorder | None = None,
    dead_tracker: DeadConnectionTracker | None = None,
    min_batch_size: int = 10,
    max_batch_size: int = 100,
    target_latency_ms: float = 50.0,
    observers: list[BroadcastObserver] | None = None,
) -> BroadcastRouter:
    """
    Create a broadcast router with adaptive batching strategy.

    ARCH-OPP-09: For high-load scenarios where batch size
    should adapt to network conditions.

    Args:
        metrics: Optional metrics recorder (legacy, prefer observers).
        dead_tracker: Optional dead connection tracker.
        min_batch_size: Minimum connections per batch.
        max_batch_size: Maximum connections per batch.
        target_latency_ms: Target latency per batch.
        observers: Optional list of broadcast observers.

    Returns:
        Configured BroadcastRouter with adaptive strategy.
    """
    strategy = AdaptiveBatchStrategy(
        min_batch_size=min_batch_size,
        max_batch_size=max_batch_size,
        target_latency_ms=target_latency_ms,
        dead_tracker=dead_tracker,
    )
    return BroadcastRouter(strategy=strategy, metrics=metrics, observers=observers)
