"""
Circuit Breaker implementation for external service calls.

REC-01 FIX: Provides fault tolerance for Mercado Pago and other external APIs.

The circuit breaker prevents cascading failures by:
1. CLOSED: Normal operation, requests pass through
2. OPEN: After failures exceed threshold, requests fail fast
3. HALF-OPEN: After timeout, allow test requests to check recovery

Usage:
    from rest_api.services.circuit_breaker import mercadopago_breaker

    async with mercadopago_breaker.call():
        response = await client.post(...)
"""

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncGenerator, Callable, Any

from shared.config.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing fast, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for a circuit breaker instance."""
    name: str
    failure_threshold: int = 5       # Failures before opening
    success_threshold: int = 2       # Successes in half-open before closing
    timeout_seconds: float = 30.0    # Time before trying half-open
    half_open_max_calls: int = 3     # Max concurrent calls in half-open


@dataclass
class CircuitBreakerStats:
    """Statistics for monitoring circuit breaker behavior."""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    state_changes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None


class CircuitBreakerError(Exception):
    """Raised when circuit is open and request is rejected."""
    def __init__(self, breaker_name: str, retry_after: float):
        self.breaker_name = breaker_name
        self.retry_after = retry_after
        super().__init__(f"Circuit breaker '{breaker_name}' is open. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Thread-safe implementation using asyncio locks.
    """

    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()
        self._stats = CircuitBreakerStats()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def stats(self) -> CircuitBreakerStats:
        """Get circuit breaker statistics."""
        return self._stats

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        old_state = self._state
        self._state = new_state
        self._stats.state_changes += 1

        logger.info(
            f"Circuit breaker '{self.config.name}' state change",
            old_state=old_state.value,
            new_state=new_state.value,
            failure_count=self._failure_count,
            success_count=self._success_count,
        )

        # Reset counters on state change
        if new_state == CircuitState.CLOSED:
            self._failure_count = 0
            self._success_count = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._success_count = 0
            self._half_open_calls = 0

    async def _check_timeout(self) -> bool:
        """Check if timeout has passed since last failure (should try half-open)."""
        if self._last_failure_time is None:
            return True

        elapsed = time.time() - self._last_failure_time
        return elapsed >= self.config.timeout_seconds

    async def _can_attempt(self) -> tuple[bool, float]:
        """
        Check if a request can be attempted.

        Returns:
            Tuple of (can_attempt, retry_after_seconds)
        """
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True, 0.0

            elif self._state == CircuitState.OPEN:
                if await self._check_timeout():
                    await self._transition_to(CircuitState.HALF_OPEN)
                    return True, 0.0
                else:
                    retry_after = (
                        self.config.timeout_seconds -
                        (time.time() - (self._last_failure_time or 0))
                    )
                    return False, max(0, retry_after)

            elif self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.config.half_open_max_calls:
                    self._half_open_calls += 1
                    return True, 0.0
                else:
                    # Too many concurrent half-open calls
                    return False, 1.0

        return False, 0.0

    async def record_success(self) -> None:
        """Record a successful call."""
        async with self._lock:
            self._stats.total_calls += 1
            self._stats.successful_calls += 1
            self._stats.last_success_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                self._half_open_calls = max(0, self._half_open_calls - 1)

                if self._success_count >= self.config.success_threshold:
                    await self._transition_to(CircuitState.CLOSED)

            elif self._state == CircuitState.CLOSED:
                # Reset failure count on success
                self._failure_count = 0

    async def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed call."""
        async with self._lock:
            self._stats.total_calls += 1
            self._stats.failed_calls += 1
            self._stats.last_failure_time = time.time()
            self._last_failure_time = time.time()
            self._failure_count += 1

            if error:
                logger.warning(
                    f"Circuit breaker '{self.config.name}' recorded failure",
                    error=str(error),
                    failure_count=self._failure_count,
                    threshold=self.config.failure_threshold,
                )

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open reopens the circuit
                await self._transition_to(CircuitState.OPEN)

            elif self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    await self._transition_to(CircuitState.OPEN)

    @asynccontextmanager
    async def call(self) -> AsyncGenerator[None, None]:
        """
        Context manager for making a protected call.

        Usage:
            async with breaker.call():
                # Make external service call
                response = await client.post(...)

        Raises:
            CircuitBreakerError: If circuit is open
        """
        can_attempt, retry_after = await self._can_attempt()

        if not can_attempt:
            self._stats.rejected_calls += 1
            raise CircuitBreakerError(self.config.name, retry_after)

        try:
            yield
            await self.record_success()
        except Exception as e:
            await self.record_failure(e)
            raise

    async def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._half_open_calls = 0
            logger.info(f"Circuit breaker '{self.config.name}' manually reset")


# =============================================================================
# Pre-configured Circuit Breakers
# =============================================================================

# Mercado Pago API circuit breaker
# Opens after 5 failures, closes after 2 successes in half-open
mercadopago_breaker = CircuitBreaker(
    CircuitBreakerConfig(
        name="mercadopago",
        failure_threshold=5,
        success_threshold=2,
        timeout_seconds=30.0,
        half_open_max_calls=2,
    )
)

# Ollama RAG API circuit breaker
# More lenient since it's internal
ollama_breaker = CircuitBreaker(
    CircuitBreakerConfig(
        name="ollama",
        failure_threshold=3,
        success_threshold=1,
        timeout_seconds=10.0,
        half_open_max_calls=1,
    )
)


# =============================================================================
# Health Check Endpoint Data
# =============================================================================

def get_all_breaker_stats() -> dict[str, dict]:
    """
    Get statistics for all circuit breakers.

    Useful for health check endpoints and monitoring.
    """
    breakers = {
        "mercadopago": mercadopago_breaker,
        "ollama": ollama_breaker,
    }

    return {
        name: {
            "state": breaker.state.value,
            "total_calls": breaker.stats.total_calls,
            "successful_calls": breaker.stats.successful_calls,
            "failed_calls": breaker.stats.failed_calls,
            "rejected_calls": breaker.stats.rejected_calls,
            "state_changes": breaker.stats.state_changes,
        }
        for name, breaker in breakers.items()
    }
