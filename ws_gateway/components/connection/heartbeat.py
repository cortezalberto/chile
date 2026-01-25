"""
Heartbeat Tracker for WebSocket Gateway.

Tracks last activity time for each WebSocket connection.
Identifies stale connections that haven't sent heartbeats.

ARCH-01 FIX: Extracted from ConnectionManager (Single Responsibility).
CRIT-03 FIX: Added thread-safety with threading.Lock.
HIGH-DEEP-03 FIX: Moved logger import to module level.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from ws_gateway.components.core.constants import MSG_PING_PLAIN, MSG_PING_JSON, MSG_PONG_JSON

if TYPE_CHECKING:
    from fastapi import WebSocket

# HIGH-DEEP-03 FIX: Module-level logger instead of import inside function
_heartbeat_logger = logging.getLogger(__name__)


class HeartbeatTracker:
    """
    Tracks heartbeat timestamps for WebSocket connections.

    CRIT-03 FIX: Thread-safe implementation using threading.Lock.
    All dictionary operations are protected to prevent RuntimeError
    from concurrent modification.

    Each connection's last activity time is recorded when:
    - Connection is established
    - Any message is received (including heartbeats)

    Connections without recent activity are considered stale.
    """

    def __init__(self, timeout_seconds: float = 60.0):
        """
        Initialize heartbeat tracker.

        Args:
            timeout_seconds: Seconds without activity before connection is stale.
        """
        self._timeout = timeout_seconds
        self._last_heartbeat: dict[WebSocket, float] = {}
        # CRIT-03 FIX: Lock for thread-safe operations
        self._lock = threading.Lock()

    @property
    def timeout(self) -> float:
        """Get the heartbeat timeout in seconds."""
        return self._timeout

    @property
    def tracked_count(self) -> int:
        """Get number of connections being tracked."""
        with self._lock:
            return len(self._last_heartbeat)

    def record(self, websocket: WebSocket, timestamp: float | None = None) -> None:
        """
        Record activity from a connection.

        CRIT-03 FIX: Thread-safe with lock.
        MED-09 FIX: Added optional timestamp parameter for testing and
        external timestamp control.

        Call this when:
        - A new connection is established
        - Any message is received from the connection

        Args:
            websocket: The WebSocket connection to record.
            timestamp: Optional Unix timestamp. If None, uses current time.
                       Useful for testing and when timestamp is known externally.
        """
        with self._lock:
            self._last_heartbeat[websocket] = timestamp if timestamp is not None else time.time()

    def remove(self, websocket: WebSocket) -> None:
        """
        Stop tracking a connection.

        CRIT-03 FIX: Thread-safe with lock.

        Call this when a connection is closed or disconnected.

        Args:
            websocket: The WebSocket connection to remove.
        """
        with self._lock:
            self._last_heartbeat.pop(websocket, None)

    def get_last_activity(self, websocket: WebSocket) -> float | None:
        """
        Get the last activity time for a connection.

        CRIT-03 FIX: Thread-safe with lock.

        Args:
            websocket: The WebSocket connection to check.

        Returns:
            Unix timestamp of last activity, or None if not tracked.
        """
        with self._lock:
            return self._last_heartbeat.get(websocket)

    def get_last_heartbeat_time(self, websocket: WebSocket, default: float | None = None) -> float:
        """
        HIGH-03 FIX: Get the last heartbeat time with default value.
        MED-WS-11 FIX: Changed default from 0.0 to None (uses current time).

        Thread-safe method for external callers that need a default value.
        Use this instead of accessing _last_heartbeat directly.

        Args:
            websocket: The WebSocket connection to check.
            default: Default value if websocket not tracked.
                     If None, returns current time (treats unknown as "just seen").
                     LOW-WS-06 FIX: Unix timestamp in seconds (float, from time.time()).

        Returns:
            Unix timestamp (seconds since epoch, float) of last heartbeat,
            or default/current time if not tracked.
        """
        with self._lock:
            result = self._last_heartbeat.get(websocket)
            if result is not None:
                return result
            # MED-WS-11 FIX: Return current time for unknown connections
            # This prevents unknown connections from appearing "oldest"
            return default if default is not None else time.time()

    def is_stale(self, websocket: WebSocket) -> bool:
        """
        Check if a connection is stale (no recent activity).

        CRIT-03 FIX: Thread-safe with lock.

        Args:
            websocket: The WebSocket connection to check.

        Returns:
            True if the connection hasn't had activity within timeout period.
        """
        with self._lock:
            last_time = self._last_heartbeat.get(websocket)
        if last_time is None:
            return True  # Unknown connections are considered stale
        return time.time() - last_time > self._timeout

    def get_stale_connections(self) -> list[WebSocket]:
        """
        Get all connections that haven't sent a heartbeat within timeout.

        CRIT-03 FIX: Thread-safe - copies dict under lock.

        Returns:
            List of stale WebSocket connections.
        """
        now = time.time()
        stale = []
        # CRIT-03 FIX: Copy under lock to prevent concurrent modification
        with self._lock:
            items = list(self._last_heartbeat.items())
        for ws, last_time in items:
            if now - last_time > self._timeout:
                stale.append(ws)
        return stale

    def cleanup_stale(self) -> list[WebSocket]:
        """
        Remove and return stale connections from tracking.

        CRIT-03 FIX: Thread-safe atomic operation.

        This both identifies stale connections and removes them from
        tracking in one operation.

        Returns:
            List of stale connections that were removed.
        """
        now = time.time()
        stale = []
        # CRIT-03 FIX: Single lock for atomic read-modify-write
        with self._lock:
            for ws, last_time in list(self._last_heartbeat.items()):
                if now - last_time > self._timeout:
                    stale.append(ws)
                    del self._last_heartbeat[ws]
        return stale

    def get_stats(self) -> dict[str, float | int]:
        """Get heartbeat tracker statistics."""
        with self._lock:
            now = time.time()
            ages = [now - t for t in self._last_heartbeat.values()]
            tracked = len(self._last_heartbeat)

        return {
            "tracked_connections": tracked,
            "timeout_seconds": self._timeout,
            "oldest_heartbeat_age": max(ages) if ages else 0,
            "newest_heartbeat_age": min(ages) if ages else 0,
            "average_heartbeat_age": sum(ages) / len(ages) if ages else 0,
        }


async def handle_heartbeat(ws: WebSocket, data: str) -> bool:
    """
    Centralized heartbeat handling.

    Responds to ping messages with pong. Supports both plain text
    and JSON formatted pings.

    MED-WS-07 FIX: Only catches expected WebSocket exceptions, re-raises critical errors.
    HIGH-DEEP-03 FIX: Uses module-level logger instead of import inside function.

    Args:
        ws: The WebSocket connection.
        data: The received message data.

    Returns:
        True if message was a heartbeat and was handled, False otherwise.
    """
    if data == MSG_PING_PLAIN or data == MSG_PING_JSON:
        try:
            await ws.send_text(MSG_PONG_JSON)
        except (ConnectionError, RuntimeError, OSError):
            # MED-WS-07 FIX: Only catch expected connection-related errors
            # Connection may have closed - caller will handle cleanup
            pass
        except (KeyboardInterrupt, SystemExit):
            # MED-AUD-04 FIX: Don't catch system signals - allow graceful shutdown
            raise
        except Exception as e:
            # MED-WS-07 FIX: Log unexpected exceptions but don't re-raise
            # HIGH-DEEP-03 FIX: Use module-level logger
            _heartbeat_logger.warning(
                "Unexpected error sending heartbeat response",
                error=type(e).__name__,
                message=str(e),
            )
        return True
    return False
