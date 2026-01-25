"""
Resilience components.

Fault tolerance: circuit breaker and retry with jitter.
"""

from ws_gateway.components.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)
from ws_gateway.components.resilience.retry import (
    RetryConfig,
    calculate_delay_with_jitter,
    DecorrelatedJitter,
    create_redis_retry_config,
)

__all__ = [
    # Circuit breaker
    "CircuitBreaker",
    "CircuitState",
    # Retry utilities
    "RetryConfig",
    "calculate_delay_with_jitter",
    "DecorrelatedJitter",
    "create_redis_retry_config",
]
