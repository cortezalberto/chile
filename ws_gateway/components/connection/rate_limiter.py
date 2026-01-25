"""
WebSocket Rate Limiter.

Per-connection rate limiting using sliding window counter algorithm.
Prevents message flooding and DoS attacks.

ARCH-01 FIX: Extracted from ConnectionManager (Single Responsibility).
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from ws_gateway.components.core.constants import WSConstants

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketRateLimiter:
    """
    Per-connection rate limiter for WebSocket messages.

    Uses a sliding window counter algorithm:
    - Each connection has a list of message timestamps
    - Timestamps outside the window are removed
    - If timestamps within window exceed limit, message is rejected

    Memory bounded by MAX_TRACKED_CONNECTIONS to prevent leaks.

    CRIT-WS-02 FIX: Added MAX_TRACKED_CONNECTIONS limit.
    """

    def __init__(
        self,
        max_messages: int,
        window_seconds: int,
        max_tracked: int = WSConstants.MAX_TRACKED_CONNECTIONS,
    ):
        """
        Initialize the rate limiter.

        Args:
            max_messages: Maximum messages allowed per window.
            window_seconds: Window size in seconds.
            max_tracked: Maximum connections to track (memory bound).
        """
        self._max_messages = max_messages
        self._window_seconds = window_seconds
        self._max_tracked = max_tracked

        self._counters: dict[WebSocket, list[float]] = {}
        self._lock = asyncio.Lock()
        self._overflow_warning_logged = False

        # HIGH-AUD-03 FIX: Track evicted connections to prevent rate limit reset
        # When a connection is evicted, it's added here with its timestamp count
        # If it tries to reconnect, it inherits the penalty
        # CRIT-06 FIX: Store (message_count, eviction_timestamp) to support TTL expiration
        self._evicted_penalty: dict[int, tuple[int, float]] = {}  # id(ws) -> (message_count, eviction_time)
        self._max_evicted_penalty_entries = max_tracked // 10  # 10% of max tracked
        self._penalty_ttl_seconds = 3600.0  # CRIT-06 FIX: Penalties expire after 1 hour

        # Metrics
        self._total_allowed = 0
        self._total_rejected = 0
        self._evictions = 0

    @property
    def max_messages(self) -> int:
        """Maximum messages allowed per window."""
        return self._max_messages

    @property
    def window_seconds(self) -> int:
        """Window size in seconds."""
        return self._window_seconds

    @property
    def tracked_count(self) -> int:
        """Number of connections currently being tracked."""
        return len(self._counters)

    async def is_allowed(self, ws: WebSocket) -> bool:
        """
        Check if a message from this connection is allowed.

        Thread-safe implementation using asyncio lock.

        Args:
            ws: The WebSocket connection sending the message.

        Returns:
            True if message is allowed, False if rate limited.
        """
        now = time.time()
        window_start = now - self._window_seconds

        async with self._lock:
            ws_id = id(ws)

            # Handle new connections with capacity check
            if ws not in self._counters:
                if len(self._counters) >= self._max_tracked:
                    await self._evict_oldest_entries()

                # HIGH-AUD-03 FIX: Check for eviction penalty
                # CRIT-06 FIX: Check TTL on penalty entries before applying
                penalty_entry = self._evicted_penalty.pop(ws_id, None)
                if penalty_entry is not None:
                    penalty_count, eviction_time = penalty_entry
                    # Only apply penalty if within TTL
                    if now - eviction_time < self._penalty_ttl_seconds and penalty_count > 0:
                        # MED-WS-14 FIX: Start penalty timestamps INSIDE the window
                        # Use (i+1) to ensure first timestamp is > window_start
                        # This ensures all penalty timestamps survive the filter
                        penalty_count_capped = min(penalty_count, self._max_messages)
                        penalty_timestamps = [
                            window_start + ((i + 1) * self._window_seconds / (penalty_count_capped + 1))
                            for i in range(penalty_count_capped)
                        ]
                        self._counters[ws] = penalty_timestamps
                        logger.debug(
                            "Connection reappeared after eviction, applying penalty",
                            ws_id=ws_id,
                            penalty_messages=len(penalty_timestamps),
                            penalty_age_seconds=round(now - eviction_time, 1),
                        )
                    else:
                        # Penalty expired, start fresh
                        self._counters[ws] = []
                        if penalty_count > 0:
                            logger.debug(
                                "Penalty expired for evicted connection",
                                ws_id=ws_id,
                                penalty_age_seconds=round(now - eviction_time, 1),
                            )
                else:
                    self._counters[ws] = []

            # Remove timestamps outside the window
            timestamps = self._counters[ws]
            self._counters[ws] = [t for t in timestamps if t > window_start]

            # Check if under limit
            if len(self._counters[ws]) >= self._max_messages:
                self._total_rejected += 1
                return False

            # Record this message
            self._counters[ws].append(now)
            self._total_allowed += 1
            return True

    async def _evict_oldest_entries(self) -> None:
        """
        Evict oldest entries when at capacity.

        Removes EVICTION_PERCENTAGE of entries to make room.
        """
        if not self._overflow_warning_logged:
            logger.warning(
                "Rate limiter at capacity, evicting oldest entries",
                max_tracked=self._max_tracked,
                current_tracked=len(self._counters),
            )
            self._overflow_warning_logged = True

        # Remove percentage of oldest entries
        # DEF-01 FIX: Sort by oldest timestamp to evict truly oldest connections
        entries_to_remove = max(1, self._max_tracked * WSConstants.EVICTION_PERCENTAGE // 100)

        # Sort connections by their oldest timestamp (or 0 if empty)
        sorted_connections = sorted(
            self._counters.items(),
            key=lambda x: min(x[1]) if x[1] else 0,
        )

        for i in range(min(entries_to_remove, len(sorted_connections))):
            ws, timestamps = sorted_connections[i]
            ws_id = id(ws)

            # HIGH-AUD-03 FIX: Record penalty for evicted connections
            # So they can't reset their rate limit by forcing eviction
            # CRIT-06 FIX: Store timestamp with penalty for TTL-based expiration
            if timestamps:
                now = time.time()

                # CRIT-06 FIX: Clean up expired penalty entries by TTL, not arbitrary halving
                if len(self._evicted_penalty) >= self._max_evicted_penalty_entries:
                    expired_keys = [
                        key for key, (_, evict_time) in self._evicted_penalty.items()
                        if now - evict_time > self._penalty_ttl_seconds
                    ]
                    for key in expired_keys:
                        del self._evicted_penalty[key]

                    # If still at capacity after TTL cleanup, remove oldest by eviction time
                    if len(self._evicted_penalty) >= self._max_evicted_penalty_entries:
                        sorted_by_time = sorted(
                            self._evicted_penalty.items(),
                            key=lambda x: x[1][1],  # Sort by eviction_time
                        )
                        keys_to_remove = [k for k, _ in sorted_by_time[:len(sorted_by_time) // 2]]
                        for key in keys_to_remove:
                            del self._evicted_penalty[key]

                self._evicted_penalty[ws_id] = (len(timestamps), now)

            del self._counters[ws]
            self._evictions += 1

    async def remove_connection(self, ws: WebSocket) -> None:
        """
        Remove a connection from tracking.

        Call this when a connection is closed.

        Args:
            ws: The WebSocket connection to remove.
        """
        async with self._lock:
            self._counters.pop(ws, None)

    async def cleanup_stale(self) -> int:
        """
        Remove entries with no recent timestamps.

        CRIT-WS-03 FIX: More aggressive cleanup for disconnected WebSockets.
        HIGH-WS-04 FIX: Separated identification and removal phases.

        Returns:
            Number of entries cleaned up.
        """
        now = time.time()
        window_start = now - self._window_seconds
        cleaned = 0

        async with self._lock:
            # HIGH-WS-04 FIX: Phase 1 - Identify entries to clean (no modification)
            # LOW-DEEP-04 FIX: Added explicit type annotations for clarity
            to_remove: list[WebSocket] = []
            to_update: dict[WebSocket, list[float]] = {}

            for ws, timestamps in self._counters.items():
                # Filter timestamps within window
                valid_timestamps = [t for t in timestamps if t > window_start]

                if not valid_timestamps:
                    to_remove.append(ws)
                elif len(valid_timestamps) != len(timestamps):
                    to_update[ws] = valid_timestamps

            # HIGH-WS-04 FIX: Phase 2 - Apply changes
            for ws in to_remove:
                del self._counters[ws]
                cleaned += 1

            for ws, timestamps in to_update.items():
                self._counters[ws] = timestamps

            # CRIT-WS-03 FIX: Also clean up entries where WebSocket appears closed
            # CRIT-NEW-02 FIX: Safer WebSocket state check with defensive coding
            # Check for WebSockets that may have been disconnected
            additional_cleanup = []
            for ws in list(self._counters.keys()):  # Copy keys to avoid modification during iteration
                try:
                    # Check if WebSocket is still valid by accessing a property
                    # If the WebSocket is garbage collected or closed, this may fail
                    client_state = getattr(ws, 'client_state', None)
                    if client_state is not None:
                        from starlette.websockets import WebSocketState
                        if client_state != WebSocketState.CONNECTED:
                            additional_cleanup.append(ws)
                except (AttributeError, ReferenceError, RuntimeError):
                    # CRIT-NEW-02 FIX: Handle garbage collected or invalidated references
                    # ReferenceError: weak reference is dead
                    # RuntimeError: event loop issues
                    additional_cleanup.append(ws)
                except Exception as e:
                    # Log unexpected exceptions but still clean up
                    logger.debug("Unexpected error checking WebSocket state", error=str(e))
                    additional_cleanup.append(ws)

            for ws in additional_cleanup:
                if ws in self._counters:
                    del self._counters[ws]
                    cleaned += 1

            # Reset overflow warning if below threshold
            if len(self._counters) < self._max_tracked * 0.9:
                self._overflow_warning_logged = False

            # HIGH-WS-12 FIX: Also clean up expired penalty entries
            # This ensures penalty dict doesn't grow unbounded even without evictions
            expired_penalties = [
                ws_id for ws_id, (_, evict_time) in self._evicted_penalty.items()
                if now - evict_time > self._penalty_ttl_seconds
            ]
            for ws_id in expired_penalties:
                del self._evicted_penalty[ws_id]
            if expired_penalties:
                logger.debug(
                    "Cleaned up expired eviction penalties",
                    count=len(expired_penalties),
                    remaining=len(self._evicted_penalty),
                )

        return cleaned

    def get_stats(self) -> dict[str, int | float]:
        """Get rate limiter statistics."""
        return {
            "tracked_connections": len(self._counters),
            "max_tracked": self._max_tracked,
            "max_messages_per_window": self._max_messages,
            "window_seconds": self._window_seconds,
            "total_allowed": self._total_allowed,
            "total_rejected": self._total_rejected,
            "evictions": self._evictions,
            # HIGH-AUD-03 FIX: Include penalty tracking info
            "evicted_penalties_tracked": len(self._evicted_penalty),
            # CRIT-06 FIX: Include penalty TTL for observability
            "penalty_ttl_seconds": self._penalty_ttl_seconds,
        }

    def get_connection_usage(self, ws: WebSocket) -> dict[str, int | float]:
        """
        Get rate limit usage for a specific connection.

        Args:
            ws: The WebSocket connection to check.

        Returns:
            Dict with current message count and percentage used.
        """
        timestamps = self._counters.get(ws, [])
        now = time.time()
        window_start = now - self._window_seconds
        current_count = sum(1 for t in timestamps if t > window_start)

        return {
            "messages_in_window": current_count,
            "max_messages": self._max_messages,
            "usage_percent": round(current_count / self._max_messages * 100, 1),
        }
