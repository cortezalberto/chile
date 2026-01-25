"""
Core Event Publishing with Retry and Validation.

REDIS-HIGH-03/04/07 FIX: Retry logic, validation, and size checking.
REDIS-CRIT-03 FIX: Circuit breaker integration.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as redis

from shared.config.settings import settings
from shared.config.logging import get_logger
from .event_types import MAX_EVENT_SIZE
from .event_schema import Event
from .circuit_breaker import get_event_circuit_breaker, calculate_retry_delay_with_jitter

logger = get_logger(__name__)


def _validate_event_size(event_json: str, event_type: str) -> bool:
    """
    REDIS-HIGH-07 FIX: Validate event size before publishing.

    Returns True if valid, raises ValueError if too large.
    """
    size = len(event_json.encode('utf-8'))
    if size > MAX_EVENT_SIZE:
        raise ValueError(
            f"Event {event_type} exceeds max size: {size} > {MAX_EVENT_SIZE} bytes"
        )
    return True


async def publish_event(
    redis_client: redis.Redis,
    channel: str,
    event: Event,
) -> int:
    """
    Publish an event to a Redis channel.

    REDIS-HIGH-03 FIX: Added retry logic with configurable retries.
    REDIS-HIGH-04 FIX: Event is validated in Event.__post_init__.
    REDIS-HIGH-07 FIX: Validates message size before publishing.
    REDIS-CRIT-03 FIX: Added circuit breaker to prevent cascading failures.
    REDIS-MED-01 FIX: Added exponential backoff with jitter.

    Args:
        redis_client: Async Redis client.
        channel: Redis channel name.
        event: Event to publish.

    Returns:
        Number of subscribers that received the message.
        Returns 0 if circuit breaker is open (fail-fast).

    Raises:
        ValueError: If event is too large.
        Exception: If all retries fail and circuit breaker allows.
    """
    event_json = event.to_json()

    # REDIS-HIGH-07 FIX: Validate size before publishing
    _validate_event_size(event_json, event.type)

    # REDIS-CRIT-03 FIX: Check circuit breaker before attempting
    circuit_breaker = get_event_circuit_breaker()
    if not circuit_breaker.can_execute():
        logger.warning(
            "Event publish skipped - circuit breaker open",
            channel=channel,
            event_type=event.type,
        )
        return 0  # Fail-fast: return 0 subscribers

    last_error = None
    for attempt in range(settings.redis_publish_max_retries):
        try:
            result = await redis_client.publish(channel, event_json)
            # REDIS-CRIT-03 FIX: Record success
            circuit_breaker.record_success()
            return result
        except Exception as e:
            last_error = e
            if attempt < settings.redis_publish_max_retries - 1:
                # REDIS-MED-01 FIX: Use exponential backoff with jitter
                delay = calculate_retry_delay_with_jitter(
                    attempt, settings.redis_publish_retry_delay
                )
                logger.warning(
                    "Redis publish failed, retrying",
                    channel=channel,
                    event_type=event.type,
                    attempt=attempt + 1,
                    max_retries=settings.redis_publish_max_retries,
                    delay_seconds=round(delay, 2),
                    error=str(e),
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    "Redis publish failed after all retries",
                    channel=channel,
                    event_type=event.type,
                    error=str(e),
                )

    # REDIS-CRIT-03 FIX: Record failure after all retries exhausted
    circuit_breaker.record_failure()

    # All retries exhausted - raise the last error
    raise last_error  # type: ignore
