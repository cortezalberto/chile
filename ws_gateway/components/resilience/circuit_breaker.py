"""
Circuit Breaker for Redis connections.

Implements the Circuit Breaker pattern to prevent cascading failures
when Redis is unavailable or degraded.

ARCH-05 FIX: Added Circuit Breaker to prevent infinite retry loops.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import threading
import time
from enum import Enum
from typing import Any, Callable, Coroutine, TypeVar

from ws_gateway.components.core.constants import WSConstants

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """States of the circuit breaker."""
    CLOSED = "closed"  # Normal operation - requests pass through
    OPEN = "open"  # Failure mode - requests are rejected immediately
    HALF_OPEN = "half_open"  # Recovery testing - limited requests allowed


class CircuitBreaker:
    """
    Circuit Breaker implementation for async operations.

    States:
    - CLOSED: Normal operation. Failures are counted.
    - OPEN: All calls fail fast without executing. Transitions to HALF_OPEN
            after recovery timeout.
    - HALF_OPEN: Limited calls allowed to test recovery. Success transitions
                 to CLOSED, failure returns to OPEN.

    Usage:
        breaker = CircuitBreaker("redis")

        async def call_redis():
            async with breaker:
                return await redis.get("key")

        # Or with decorator:
        @breaker.protect
        async def get_from_redis(key: str):
            return await redis.get(key)
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = WSConstants.CIRCUIT_FAILURE_THRESHOLD,
        recovery_timeout: float = WSConstants.CIRCUIT_RECOVERY_TIMEOUT,
        half_open_max_calls: int = WSConstants.CIRCUIT_HALF_OPEN_MAX_CALLS,
    ):
        """
        Initialize the circuit breaker.

        Args:
            name: Name for logging and identification.
            failure_threshold: Consecutive failures before opening circuit.
            recovery_timeout: Seconds to wait in OPEN before trying recovery.
            half_open_max_calls: Max calls allowed in HALF_OPEN state.
        """
        self._name = name
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0

        # CRIT-AUD-01 FIX: Use single threading.Lock for both sync and async operations
        # asyncio.Lock cannot be used from sync context, and having two separate locks
        # causes race conditions when both async and sync methods modify the same state.
        # threading.Lock is safe to use in async context (just blocks the thread briefly).
        self._lock = threading.Lock()

        # Metrics
        self._total_calls = 0
        self._successful_calls = 0
        self._failed_calls = 0
        self._rejected_calls = 0
        self._state_changes = 0

    @property
    def name(self) -> str:
        """Circuit breaker name."""
        return self._name

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        """Check if circuit is closed (normal operation)."""
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        """Check if circuit is open (failing fast)."""
        return self._state == CircuitState.OPEN

    async def __aenter__(self) -> "CircuitBreaker":
        """Context manager entry - check if call is allowed."""
        # CRIT-AUD-01 FIX: Use sync method since we now have a single threading.Lock
        self._before_call_sync()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Context manager exit - record result."""
        # CRIT-AUD-01 FIX: Use sync methods since we now have a single threading.Lock
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure(exc_val)
        return False  # Don't suppress exceptions

    def _before_call_sync(self) -> None:
        """
        Check if call is allowed and update state (sync version).

        CRIT-AUD-01 FIX: Unified sync implementation using threading.Lock.
        All state modifications now use the same lock to prevent race conditions.

        Raises:
            CircuitOpenError: If circuit is open and rejecting calls.
        """
        with self._lock:
            self._total_calls += 1

            if self._state == CircuitState.CLOSED:
                return  # Allow call

            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has passed
                if time.time() - self._last_failure_time >= self._recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
                else:
                    self._rejected_calls += 1
                    raise CircuitOpenError(
                        f"Circuit breaker '{self._name}' is OPEN. "
                        f"Recovery in {self._recovery_timeout - (time.time() - self._last_failure_time):.1f}s"
                    )

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self._half_open_max_calls:
                    self._rejected_calls += 1
                    raise CircuitOpenError(
                        f"Circuit breaker '{self._name}' is HALF_OPEN and at max test calls"
                    )
                self._half_open_calls += 1

    # CRIT-02 FIX: Public methods for external failure/success recording
    # CRIT-WS-01 FIX: Added threading.Lock for thread-safe sync operations

    def record_failure(self, error: BaseException | None = None) -> None:
        """
        Record a failure (thread-safe).

        CRIT-02 FIX: Public method to record failures without accessing private methods.
        CRIT-AUD-01 FIX: Uses unified threading.Lock for all operations.

        Args:
            error: Optional exception that caused the failure.
        """
        with self._lock:
            self._failed_calls += 1
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self._failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def record_success(self) -> None:
        """
        Record a success (thread-safe).

        CRIT-02 FIX: Public method to record success without accessing private methods.
        CRIT-AUD-01 FIX: Uses unified threading.Lock for all operations.
        """
        with self._lock:
            self._successful_calls += 1

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0

    def _transition_to_internal(self, new_state: CircuitState) -> bool:
        """
        Internal state transition - MUST be called with lock held.

        CRIT-DEEP-01 FIX: Renamed from _transition_to to make it clear
        this requires external locking.
        CRIT-AUD-01 FIX: Now all methods use the same threading.Lock.
        CRIT-WS-10 FIX: Returns bool and guards against no-op transitions
        to prevent duplicate state changes and logging.

        Args:
            new_state: The new circuit state.

        Returns:
            True if state changed, False if already in target state (no-op).
        """
        old_state = self._state

        # CRIT-WS-10 FIX: Guard against no-op transitions
        if old_state == new_state:
            return False

        self._state = new_state
        self._state_changes += 1

        # MED-04 FIX: Reset appropriate counters for each state
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._half_open_calls = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
        elif new_state == CircuitState.OPEN:
            self._half_open_calls = 0

        # MED-WS-15 FIX: Use appropriate log level for different transitions
        log_level = logging.WARNING
        if new_state == CircuitState.CLOSED:
            log_level = logging.INFO  # Recovery success is info, not warning
        elif new_state == CircuitState.OPEN:
            log_level = logging.ERROR  # Circuit opening is an error condition

        logger.log(
            log_level,
            "Circuit breaker state change",
            name=self._name,
            from_state=old_state.value,
            to_state=new_state.value,
            failure_count=self._failure_count,
        )
        return True

    def _transition_to(self, new_state: CircuitState) -> None:
        """
        Transition to a new state (legacy wrapper for backward compatibility).

        CRIT-DEEP-01 FIX: This method assumes caller holds appropriate lock.
        For new code, use _transition_to_internal directly when lock is held.
        """
        self._transition_to_internal(new_state)

    def protect(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        """
        Decorator to protect an async function with the circuit breaker.

        MED-WS-04 FIX: Uses functools.wraps to preserve function metadata.

        Usage:
            @breaker.protect
            async def call_redis():
                return await redis.get("key")
        """
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            async with self:
                return await func(*args, **kwargs)

        return wrapper

    async def reset(self) -> None:
        """Manually reset the circuit breaker to CLOSED state."""
        # CRIT-AUD-01 FIX: Use sync lock wrapper for async interface
        self.reset_sync()

    def reset_sync(self) -> None:
        """Manually reset the circuit breaker to CLOSED state (sync version)."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)
            self._failure_count = 0
            logger.info("Circuit breaker manually reset", name=self._name)

    def get_stats(self) -> dict[str, Any]:
        """
        Get circuit breaker statistics.

        MED-DEEP-01 FIX: Uses lock to ensure consistent snapshot.
        CRIT-AUD-01 FIX: Uses unified threading.Lock.
        """
        with self._lock:
            return {
                "name": self._name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self._failure_threshold,
                "recovery_timeout": self._recovery_timeout,
                "total_calls": self._total_calls,
                "successful_calls": self._successful_calls,
                "failed_calls": self._failed_calls,
                "rejected_calls": self._rejected_calls,
                "state_changes": self._state_changes,
                "time_since_last_failure": (
                    time.time() - self._last_failure_time
                    if self._last_failure_time > 0
                    else None
                ),
            }


class CircuitOpenError(Exception):
    """Raised when circuit breaker is open and rejecting calls."""
    pass
