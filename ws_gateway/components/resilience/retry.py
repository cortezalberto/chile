"""
Retry Utilities for WebSocket Gateway.

Provides retry logic with exponential backoff and jitter.
Prevents thundering herd problems in distributed systems.

ARCH-OPP-04 FIX: Adds jitter to retry delays.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Final


# =============================================================================
# Constants
# =============================================================================


# Default jitter range: ±25% of calculated delay
DEFAULT_JITTER_FACTOR: Final[float] = 0.25

# Default exponential backoff base
DEFAULT_BACKOFF_BASE: Final[float] = 2.0

# Default initial delay in seconds
DEFAULT_INITIAL_DELAY: Final[float] = 1.0


# =============================================================================
# Data Classes
# =============================================================================


@dataclass(frozen=True, slots=True)
class RetryConfig:
    """
    Configuration for retry behavior.

    Attributes:
        initial_delay: Base delay in seconds (default: 1.0).
        max_delay: Maximum delay cap in seconds (default: 30.0).
        backoff_base: Exponential backoff multiplier (default: 2.0).
        jitter_factor: Random jitter range as fraction (default: 0.25 = ±25%).
        max_attempts: Maximum retry attempts (default: 10).
    """

    initial_delay: float = DEFAULT_INITIAL_DELAY
    max_delay: float = 30.0
    backoff_base: float = DEFAULT_BACKOFF_BASE
    jitter_factor: float = DEFAULT_JITTER_FACTOR
    max_attempts: int = 10

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.initial_delay <= 0:
            raise ValueError("initial_delay must be positive")
        if self.max_delay < self.initial_delay:
            raise ValueError("max_delay must be >= initial_delay")
        if self.backoff_base < 1:
            raise ValueError("backoff_base must be >= 1")
        if not 0 <= self.jitter_factor <= 1:
            raise ValueError("jitter_factor must be between 0 and 1")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")


# =============================================================================
# Retry Functions
# =============================================================================


def calculate_delay_with_jitter(
    attempt: int,
    config: RetryConfig | None = None,
) -> float:
    """
    Calculate retry delay with exponential backoff and jitter.

    ARCH-OPP-04 FIX: Adds jitter to prevent thundering herd.

    The delay is calculated as:
        base_delay = initial_delay * (backoff_base ^ attempt)
        capped_delay = min(base_delay, max_delay)
        final_delay = capped_delay * (1 ± jitter_factor)

    Args:
        attempt: Current attempt number (0-indexed).
        config: Retry configuration (uses defaults if None).

    Returns:
        Delay in seconds with jitter applied.

    Example:
        >>> config = RetryConfig(initial_delay=1.0, max_delay=30.0)
        >>> delay = calculate_delay_with_jitter(0, config)  # ~1.0s ± 25%
        >>> delay = calculate_delay_with_jitter(1, config)  # ~2.0s ± 25%
        >>> delay = calculate_delay_with_jitter(5, config)  # ~30.0s ± 25% (capped)
    """
    if config is None:
        config = RetryConfig()

    # Calculate base exponential delay
    base_delay = config.initial_delay * (config.backoff_base ** attempt)

    # Cap at max_delay
    capped_delay = min(base_delay, config.max_delay)

    # Apply jitter
    jitter_range = capped_delay * config.jitter_factor
    jitter = random.uniform(-jitter_range, jitter_range)

    # Ensure delay is never negative
    return max(0.0, capped_delay + jitter)


def calculate_delay_simple(
    attempt: int,
    max_delay: float = 30.0,
    jitter: bool = True,
) -> float:
    """
    Simple delay calculation with sensible defaults.

    For use in existing code with minimal changes.

    Args:
        attempt: Current attempt number (1-indexed for compatibility).
        max_delay: Maximum delay cap in seconds.
        jitter: Whether to apply jitter.

    Returns:
        Delay in seconds.
    """
    # Use attempt-1 for 0-indexed calculation if attempt is 1-indexed
    base_delay = min(2 ** attempt, max_delay)

    if jitter:
        # Apply ±25% jitter
        jitter_range = base_delay * DEFAULT_JITTER_FACTOR
        jitter_value = random.uniform(-jitter_range, jitter_range)
        return max(0.0, base_delay + jitter_value)

    return base_delay


def should_retry(attempt: int, max_attempts: int) -> bool:
    """
    Determine if another retry attempt should be made.

    Args:
        attempt: Current attempt number (1-indexed).
        max_attempts: Maximum allowed attempts.

    Returns:
        True if should retry, False if max attempts reached.
    """
    return attempt < max_attempts


# =============================================================================
# Decorrelated Jitter (AWS recommended)
# =============================================================================


class DecorrelatedJitter:
    """
    Implements decorrelated jitter algorithm.

    This is the AWS-recommended approach for distributed systems
    as it provides better spread across retry attempts than
    simple jitter.

    Reference: https://aws.amazon.com/blogs/architecture/exponential-backoff-and-jitter/

    Usage:
        jitter = DecorrelatedJitter(base=1.0, cap=30.0)
        for attempt in range(max_attempts):
            delay = jitter.next_delay()
            await asyncio.sleep(delay)
            try:
                result = await operation()
                break
            except RetryableError:
                continue
    """

    def __init__(
        self,
        base: float = 1.0,
        cap: float = 30.0,
    ) -> None:
        """
        Initialize decorrelated jitter.

        Args:
            base: Base delay in seconds.
            cap: Maximum delay cap in seconds.
        """
        self._base = base
        self._cap = cap
        self._last_delay = base

    def next_delay(self) -> float:
        """
        Calculate next delay using decorrelated jitter.

        Returns:
            Next delay in seconds.
        """
        self._last_delay = random.uniform(
            self._base,
            self._last_delay * 3,
        )
        return min(self._cap, self._last_delay)

    def reset(self) -> None:
        """Reset jitter state to initial values."""
        self._last_delay = self._base


# =============================================================================
# Factory Functions
# =============================================================================


def create_redis_retry_config(
    max_delay: float = 30.0,
    max_attempts: int = 10,
) -> RetryConfig:
    """
    Create retry config optimized for Redis reconnection.

    Args:
        max_delay: Maximum delay between attempts.
        max_attempts: Maximum retry attempts before giving up.

    Returns:
        RetryConfig for Redis operations.
    """
    return RetryConfig(
        initial_delay=1.0,
        max_delay=max_delay,
        backoff_base=2.0,
        jitter_factor=0.25,
        max_attempts=max_attempts,
    )


def create_ws_retry_config(
    max_delay: float = 10.0,
    max_attempts: int = 5,
) -> RetryConfig:
    """
    Create retry config for WebSocket operations.

    Uses shorter delays as WebSocket operations should be quick.

    Args:
        max_delay: Maximum delay between attempts.
        max_attempts: Maximum retry attempts.

    Returns:
        RetryConfig for WebSocket operations.
    """
    return RetryConfig(
        initial_delay=0.5,
        max_delay=max_delay,
        backoff_base=2.0,
        jitter_factor=0.3,  # Slightly more jitter for WS
        max_attempts=max_attempts,
    )
