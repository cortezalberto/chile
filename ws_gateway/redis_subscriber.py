"""
Redis pub/sub subscriber for the WebSocket gateway.

Thin orchestrator that uses modular components for event processing.

ARCH-MODULAR-09: Refactored to use composition pattern.
Original monolithic file split into:
- EventDropRateTracker: Drop rate tracking and alerting
- validate_event_schema: Event schema validation
- process_event_batch: Batch event processing
- handle_incoming_message: Message handling

This file maintains backward compatibility while delegating to modules.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Awaitable, Callable

import redis.exceptions

from shared.infrastructure.events import get_redis_pool
from shared.config.settings import settings
from ws_gateway.components.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from ws_gateway.components.core.constants import WSConstants
from ws_gateway.components.events.types import (
    WebSocketEvent,
    UnknownEventTypeTracker,
    VALID_EVENT_TYPES,
    REQUIRED_EVENT_FIELDS,
    OPTIONAL_EVENT_FIELDS,
)
from ws_gateway.components.resilience.retry import (
    calculate_delay_with_jitter,
    create_redis_retry_config,
    RetryConfig,
)

# Import modular components
from ws_gateway.core.subscriber import (
    EventDropRateTracker,
    get_drop_tracker,
    validate_event_schema,
    validate_event_schema_pure,
    track_unknown_event_type,
    get_unknown_event_metrics,
    process_event_batch,
    handle_incoming_message,
)

logger = logging.getLogger(__name__)

# Configuration from settings
MAX_MESSAGE_SIZE = settings.ws_max_message_size
MAX_RECONNECT_ATTEMPTS = settings.redis_max_reconnect_attempts
MAX_EVENT_QUEUE_SIZE = settings.redis_event_queue_size
EVENT_PROCESS_BATCH_SIZE = settings.redis_event_batch_size
EVENT_CALLBACK_TIMEOUT = settings.ws_event_callback_timeout
MAX_RECONNECT_DELAY = getattr(settings, "redis_max_reconnect_delay", 30)

# Timeout configurations
PUBSUB_CLEANUP_TIMEOUT = getattr(settings, "redis_pubsub_cleanup_timeout", 5.0)
PUBSUB_RECONNECT_TOTAL_TIMEOUT = getattr(
    settings, "redis_pubsub_reconnect_total_timeout", 15.0
)

# Circuit breaker for Redis connections
_redis_circuit_breaker = CircuitBreaker(
    name="redis_subscriber",
    failure_threshold=WSConstants.CIRCUIT_FAILURE_THRESHOLD,
    recovery_timeout=WSConstants.CIRCUIT_RECOVERY_TIMEOUT,
)

# Retry configuration with jitter for Redis reconnection
_retry_config = create_redis_retry_config(
    max_delay=MAX_RECONNECT_DELAY,
    max_attempts=MAX_RECONNECT_ATTEMPTS,
)

# Global drop rate tracker (singleton from module)
_drop_rate_tracker = get_drop_tracker(
    window_seconds=60.0,
    alert_threshold_percent=5.0,
    alert_cooldown_seconds=300.0,
)


async def run_subscriber(
    channels: list[str],
    on_message: Callable[[dict], Awaitable[None]],
) -> None:
    """
    Subscribe to Redis channels and dispatch messages.

    This function runs indefinitely, listening for messages
    and calling the callback for each one.

    Features:
    - Circuit breaker for resilient reconnection
    - Backpressure queue for event processing
    - Message size and schema validation
    - Configurable timeouts and batch processing

    Args:
        channels: List of channel patterns to subscribe to.
        on_message: Async callback function that receives parsed message data.

    Raises:
        RuntimeError: If max reconnection attempts exceeded.
    """
    redis_pool = await get_redis_pool()
    pubsub = redis_pool.pubsub()

    await pubsub.psubscribe(*channels)
    logger.info("Redis subscriber started", channels=channels)

    reconnect_attempts = 0
    event_queue: deque[dict] = deque(maxlen=MAX_EVENT_QUEUE_SIZE)
    events_dropped = {"count": 0}

    try:
        while True:
            try:
                # Check circuit breaker state
                if _redis_circuit_breaker.is_open:
                    logger.warning(
                        "Circuit breaker is open, waiting for recovery",
                        state=_redis_circuit_breaker.state.value,
                    )
                    await asyncio.sleep(WSConstants.CIRCUIT_RECOVERY_TIMEOUT / 2)
                    continue

                # Get message with timeout
                msg = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )

                if msg is None:
                    # Process queued events during idle time
                    if event_queue:
                        await process_event_batch(
                            event_queue,
                            on_message,
                            _drop_rate_tracker,
                        )
                    else:
                        await asyncio.sleep(0.01)
                    continue

                # Skip non-data messages
                if msg.get("type") not in ("message", "pmessage"):
                    continue

                # Record success on actual message receipt
                reconnect_attempts = 0
                _redis_circuit_breaker.record_success()

                # Handle incoming message (delegated to module)
                handle_incoming_message(
                    msg,
                    event_queue,
                    events_dropped,
                    _drop_rate_tracker,
                )

            except redis.exceptions.TimeoutError:
                # Normal for pubsub - continue listening
                continue

            except redis.exceptions.ConnectionError as e:
                _redis_circuit_breaker.record_failure(e)
                reconnect_attempts += 1

                if reconnect_attempts > MAX_RECONNECT_ATTEMPTS:
                    logger.error(
                        "Max reconnection attempts exceeded, subscriber giving up",
                        attempts=reconnect_attempts,
                        max_attempts=MAX_RECONNECT_ATTEMPTS,
                    )
                    raise RuntimeError(
                        f"Redis subscriber failed after {reconnect_attempts} reconnection attempts"
                    )

                # Exponential backoff WITH jitter
                delay = calculate_delay_with_jitter(
                    reconnect_attempts - 1, _retry_config
                )
                logger.warning(
                    "Redis connection error, reconnecting with jitter...",
                    error=str(e),
                    attempt=reconnect_attempts,
                    max_attempts=MAX_RECONNECT_ATTEMPTS,
                    delay_with_jitter=round(delay, 2),
                    circuit_state=_redis_circuit_breaker.state.value,
                )
                await asyncio.sleep(delay)

                # Reconnect
                pubsub = await _reconnect_pubsub(pubsub, channels)

            except CircuitOpenError:
                # Circuit is open - wait before retrying
                await asyncio.sleep(WSConstants.CIRCUIT_RECOVERY_TIMEOUT / 2)

    except asyncio.CancelledError:
        logger.info(
            "Redis subscriber cancelled",
            queued_events=len(event_queue),
            dropped_events=events_dropped["count"],
        )
        raise
    finally:
        try:
            await pubsub.punsubscribe(*channels)
        except Exception as e:
            logger.warning("Error during pubsub cleanup", error=str(e))


async def _reconnect_pubsub(pubsub: Any, channels: list[str]) -> Any:
    """
    Reconnect pubsub after connection error.

    Args:
        pubsub: Current pubsub object.
        channels: Channels to resubscribe to.

    Returns:
        New pubsub object.

    Raises:
        asyncio.TimeoutError: If total reconnection takes too long.
    """
    return await asyncio.wait_for(
        _reconnect_pubsub_internal(pubsub, channels),
        timeout=PUBSUB_RECONNECT_TOTAL_TIMEOUT,
    )


async def _reconnect_pubsub_internal(pubsub: Any, channels: list[str]) -> Any:
    """
    Internal reconnection logic with per-operation timeouts.

    Args:
        pubsub: Current pubsub object.
        channels: Channels to resubscribe to.

    Returns:
        New pubsub object.
    """
    old_pubsub = pubsub

    # Cleanup old pubsub with timeout
    try:
        await asyncio.wait_for(
            old_pubsub.punsubscribe(*channels),
            timeout=PUBSUB_CLEANUP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Pubsub unsubscribe timed out", timeout=PUBSUB_CLEANUP_TIMEOUT)
    except Exception as e:
        logger.warning("Error during pubsub cleanup on reconnect", error=str(e))

    # Always attempt to close, even if unsubscribe failed
    try:
        await asyncio.wait_for(
            old_pubsub.close(),
            timeout=PUBSUB_CLEANUP_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("Pubsub close timed out", timeout=PUBSUB_CLEANUP_TIMEOUT)
        # Force reset connection on timeout
        try:
            old_pubsub.connection = None
        except Exception:
            pass
    except Exception as e:
        logger.debug("Error closing old pubsub", error=str(e))

    # Nullify reference to help garbage collection
    del old_pubsub

    # Create new pubsub
    redis_pool = await get_redis_pool()
    new_pubsub = redis_pool.pubsub()
    await new_pubsub.psubscribe(*channels)
    logger.info("Redis subscriber reconnected", channels=channels)

    return new_pubsub


def get_subscriber_metrics() -> dict[str, Any]:
    """
    Get metrics about event processing and circuit breaker state.

    Returns:
        Dictionary with subscriber metrics for monitoring.
    """
    return {
        **get_unknown_event_metrics(),
        "circuit_breaker": _redis_circuit_breaker.get_stats(),
        "drop_rate": _drop_rate_tracker.get_stats(),
    }


def get_circuit_breaker() -> CircuitBreaker:
    """
    Get the Redis subscriber circuit breaker.

    Useful for manual reset or monitoring.

    Returns:
        CircuitBreaker instance.
    """
    return _redis_circuit_breaker


async def reset_circuit_breaker() -> None:
    """Manually reset the circuit breaker to closed state."""
    await _redis_circuit_breaker.reset()
