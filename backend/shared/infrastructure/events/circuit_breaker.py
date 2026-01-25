"""
Circuit Breaker for Redis Event Publishing.

REDIS-CRIT-03 FIX: Prevents cascading failures when Redis is unavailable.
REDIS-MED-01 FIX: Includes exponential backoff with jitter utilities.
"""

from __future__ import annotations

import random
import threading
import time
from enum import Enum

from shared.config.settings import settings
from shared.config.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """States of the circuit breaker."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failure mode - requests rejected
    HALF_OPEN = "half_open"  # Recovery testing


class EventCircuitBreaker:
    """
    REDIS-CRIT-03 FIX: Lightweight circuit breaker for event publishing.

    Prevents cascading failures when Redis is unavailable by failing fast
    instead of waiting for timeout on each publish attempt.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ):
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0
        self._lock = threading.Lock()

        # Metrics
        self._rejected_count = 0

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    def can_execute(self) -> bool:
        """
        Check if a call can proceed.

        Returns True if allowed, False if circuit is open.
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if time.time() - self._last_failure_time >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Event circuit breaker transitioning to HALF_OPEN")
                    return True
                self._rejected_count += 1
                return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._half_open_max_calls:
                    return False
                self._half_open_calls += 1
                return True

            return True

    def record_failure(self) -> None:
        """Record a failure."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.error("Event circuit breaker OPEN (half-open test failed)")
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._state = CircuitState.OPEN
                    logger.error(
                        "Event circuit breaker OPEN",
                        failure_count=self._failure_count,
                        threshold=self._failure_threshold,
                    )

    def record_success(self) -> None:
        """Record a success."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("Event circuit breaker recovered to CLOSED")
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        with self._lock:
            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "rejected_count": self._rejected_count,
                "last_failure_time": self._last_failure_time,
            }


# =============================================================================
# Singleton instance
# =============================================================================

_event_circuit_breaker: EventCircuitBreaker | None = None
_circuit_breaker_lock = threading.Lock()


def get_event_circuit_breaker() -> EventCircuitBreaker:
    """Get or create the event circuit breaker singleton."""
    global _event_circuit_breaker
    if _event_circuit_breaker is None:
        with _circuit_breaker_lock:
            if _event_circuit_breaker is None:
                _event_circuit_breaker = EventCircuitBreaker(
                    failure_threshold=settings.redis_publish_max_retries + 2,
                    recovery_timeout=30.0,
                    half_open_max_calls=3,
                )
    return _event_circuit_breaker


# =============================================================================
# Jitter utilities for retry delay
# =============================================================================


def calculate_retry_delay_with_jitter(attempt: int, base_delay: float = 0.5) -> float:
    """
    REDIS-MED-01 FIX: Calculate retry delay with exponential backoff and jitter.

    Uses decorrelated jitter to prevent thundering herd problem.

    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds

    Returns:
        Delay in seconds with jitter applied
    """
    # Exponential backoff: delay = base_delay * 2^attempt
    exp_delay = base_delay * (2 ** attempt)
    # Cap at max delay
    max_delay = 10.0
    exp_delay = min(exp_delay, max_delay)
    # Add decorrelated jitter: random between base and exp_delay
    jitter_delay = random.uniform(base_delay, exp_delay)
    return jitter_delay
