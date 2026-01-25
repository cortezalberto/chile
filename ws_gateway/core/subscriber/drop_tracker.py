"""
Event Drop Rate Tracker.

Tracks event drop rate over a sliding window and alerts if threshold exceeded.
Extracted from redis_subscriber.py for better maintainability.

ARCH-MODULAR-05: Single Responsibility - drop rate tracking only.
CRIT-05 FIX: Silent service degradation prevention.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

logger = logging.getLogger(__name__)


class EventDropRateTracker:
    """
    Tracks event drop rate over a sliding window and alerts if threshold exceeded.

    Features:
    - Sliding window tracking with configurable size
    - Alert threshold with cooldown to prevent alert storms
    - Thread-safe operations via lock
    - Bounded memory via deque maxlen

    Usage:
        tracker = EventDropRateTracker(window_seconds=60, alert_threshold_percent=5)
        tracker.record_processed()  # Success
        tracker.record_dropped()    # Failure (triggers alert check)
        stats = tracker.get_stats()  # Get current metrics
    """

    def __init__(
        self,
        window_seconds: float = 60.0,
        alert_threshold_percent: float = 5.0,
        alert_cooldown_seconds: float = 300.0,
    ) -> None:
        """
        Initialize drop rate tracker.

        Args:
            window_seconds: Window size for calculating drop rate.
            alert_threshold_percent: Alert if drop rate exceeds this % (default 5%).
            alert_cooldown_seconds: Minimum seconds between alerts.
        """
        self._window_seconds = window_seconds
        self._alert_threshold = alert_threshold_percent / 100.0
        self._alert_cooldown = alert_cooldown_seconds

        # Sliding window counters with maxlen to prevent memory leak
        # Under burst load, limit to window_seconds * 1000 entries
        max_entries = int(window_seconds * 1000)
        self._window: deque[tuple[float, int, int]] = deque(maxlen=max_entries)

        # Lifetime counters
        self._total_processed = 0
        self._total_dropped = 0

        # Alert state
        self._last_alert_time = 0.0
        self._alert_count = 0

        # Thread safety
        self._lock = threading.Lock()

    def record_processed(self) -> None:
        """Record a successfully processed event. Thread-safe."""
        now = time.time()
        with self._lock:
            self._cleanup_window(now)
            self._window.append((now, 1, 0))
            self._total_processed += 1

    def record_dropped(self) -> None:
        """Record a dropped event and check if alert needed. Thread-safe."""
        now = time.time()
        with self._lock:
            self._cleanup_window(now)
            self._window.append((now, 0, 1))
            self._total_dropped += 1
            self._check_alert(now)

    def _cleanup_window(self, now: float) -> None:
        """
        Remove entries outside the sliding window.

        MUST be called with lock held.
        """
        cutoff = now - self._window_seconds
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _check_alert(self, now: float) -> None:
        """Check if drop rate exceeds threshold and alert if needed."""
        if now - self._last_alert_time < self._alert_cooldown:
            return

        window_processed = sum(p for _, p, _ in self._window)
        window_dropped = sum(d for _, _, d in self._window)
        window_total = window_processed + window_dropped

        if window_total == 0:
            return

        drop_rate = window_dropped / window_total
        if drop_rate > self._alert_threshold:
            self._last_alert_time = now
            self._alert_count += 1
            logger.error(
                "CRITICAL: Event drop rate exceeds threshold!",
                drop_rate_percent=round(drop_rate * 100, 2),
                threshold_percent=round(self._alert_threshold * 100, 2),
                window_dropped=window_dropped,
                window_processed=window_processed,
                window_seconds=self._window_seconds,
                alert_count=self._alert_count,
            )

    def get_stats(self) -> dict[str, Any]:
        """Get drop rate statistics. Thread-safe."""
        now = time.time()
        with self._lock:
            self._cleanup_window(now)

            window_processed = sum(p for _, p, _ in self._window)
            window_dropped = sum(d for _, _, d in self._window)
            window_total = window_processed + window_dropped

            return {
                "total_processed": self._total_processed,
                "total_dropped": self._total_dropped,
                "window_processed": window_processed,
                "window_dropped": window_dropped,
                "window_drop_rate_percent": round(
                    (window_dropped / window_total * 100) if window_total > 0 else 0.0,
                    2,
                ),
                "alert_threshold_percent": round(self._alert_threshold * 100, 2),
                "alert_count": self._alert_count,
                "window_seconds": self._window_seconds,
            }


# Default global tracker instance
_default_tracker: EventDropRateTracker | None = None


def get_drop_tracker(
    window_seconds: float = 60.0,
    alert_threshold_percent: float = 5.0,
    alert_cooldown_seconds: float = 300.0,
) -> EventDropRateTracker:
    """
    Get or create the global drop rate tracker.

    Args:
        window_seconds: Window size for calculating drop rate.
        alert_threshold_percent: Alert if drop rate exceeds this %.
        alert_cooldown_seconds: Minimum seconds between alerts.

    Returns:
        Singleton EventDropRateTracker instance.
    """
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = EventDropRateTracker(
            window_seconds=window_seconds,
            alert_threshold_percent=alert_threshold_percent,
            alert_cooldown_seconds=alert_cooldown_seconds,
        )
    return _default_tracker


def reset_drop_tracker() -> None:
    """Reset the global drop tracker (for testing)."""
    global _default_tracker
    _default_tracker = None
