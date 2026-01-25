"""
Event Processing.

Handles incoming Redis messages and processes event batches.
Extracted from redis_subscriber.py for better maintainability.

ARCH-MODULAR-07: Single Responsibility - event processing only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any, Awaitable, Callable

from shared.config.settings import settings
from ws_gateway.components.core.constants import WSConstants
from ws_gateway.core.subscriber.validator import validate_event_schema
from ws_gateway.core.subscriber.drop_tracker import EventDropRateTracker

logger = logging.getLogger(__name__)

# Configuration from settings
MAX_MESSAGE_SIZE = settings.ws_max_message_size
MAX_EVENT_QUEUE_SIZE = settings.redis_event_queue_size
EVENT_PROCESS_BATCH_SIZE = settings.redis_event_batch_size
EVENT_CALLBACK_TIMEOUT = settings.ws_event_callback_timeout
EVENT_STALENESS_THRESHOLD = getattr(settings, "redis_event_staleness_threshold", 5.0)
EVENT_STRICT_ORDERING = getattr(settings, "redis_event_strict_ordering", False)


async def process_event_batch(
    event_queue: deque[dict],
    on_message: Callable[[dict], Awaitable[None]],
    drop_tracker: EventDropRateTracker,
    batch_size: int = EVENT_PROCESS_BATCH_SIZE,
    callback_timeout: float = EVENT_CALLBACK_TIMEOUT,
    staleness_threshold: float = EVENT_STALENESS_THRESHOLD,
    strict_ordering: bool = EVENT_STRICT_ORDERING,
) -> None:
    """
    Process a batch of events from the queue.

    Features:
    - Timeout handling with proper alerting
    - Re-queues events on timeout (up to max retries)
    - Tracks stale events that waited too long
    - Configurable strict/relaxed ordering

    Args:
        event_queue: Queue of pending events.
        on_message: Callback for each event.
        drop_tracker: Tracker for drop rate metrics.
        batch_size: Max events to process per batch.
        callback_timeout: Timeout for each callback.
        staleness_threshold: Warn if event waited longer than this.
        strict_ordering: If True, retried events go to front of queue.
    """
    batch_count = 0

    while event_queue and batch_count < batch_size:
        event = event_queue.popleft()
        retry_count = event.get("_retry_count", 0)

        # Check for stale events that waited too long in queue
        enqueued_at = event.get("_enqueued_at", 0)
        if enqueued_at > 0:
            wait_time = time.time() - enqueued_at
            if wait_time > staleness_threshold:
                logger.warning(
                    "Stale event detected - waited too long in queue",
                    event_type=event.get("type", "UNKNOWN"),
                    wait_time_seconds=round(wait_time, 2),
                    threshold_seconds=staleness_threshold,
                    retry_count=retry_count,
                    queue_size=len(event_queue),
                )

        try:
            await asyncio.wait_for(
                on_message(event),
                timeout=callback_timeout,
            )
        except asyncio.TimeoutError:
            _handle_callback_timeout(
                event,
                event_queue,
                drop_tracker,
                retry_count,
                callback_timeout,
                strict_ordering,
            )
        except Exception as e:
            logger.error(
                "Error processing queued event",
                error=str(e),
                event_type=event.get("type"),
                exc_info=True,
            )

        batch_count += 1


def _handle_callback_timeout(
    event: dict,
    event_queue: deque[dict],
    drop_tracker: EventDropRateTracker,
    retry_count: int,
    callback_timeout: float,
    strict_ordering: bool,
) -> None:
    """
    Handle callback timeout with retry logic.

    Args:
        event: The event that timed out.
        event_queue: Queue for re-queuing.
        drop_tracker: For tracking dropped events.
        retry_count: Current retry attempt.
        callback_timeout: Timeout value for logging.
        strict_ordering: Whether to use strict FIFO ordering.
    """
    event_type = event.get("type", "UNKNOWN")
    max_retries = 2

    if retry_count < max_retries:
        # Re-queue with incremented retry count
        event["_retry_count"] = retry_count + 1

        # Strict ordering: front of queue. Relaxed: end of queue
        if strict_ordering:
            event_queue.appendleft(event)
        else:
            event_queue.append(event)

        logger.warning(
            "Event callback timed out, re-queuing for retry",
            event_type=event_type,
            timeout=callback_timeout,
            retry_count=retry_count + 1,
            max_retries=max_retries,
            strict_ordering=strict_ordering,
        )
    else:
        # Max retries exceeded - log as ERROR (possible event loss)
        logger.error(
            "CRITICAL: Event callback timeout after max retries - EVENT LOST",
            event_type=event_type,
            timeout=callback_timeout,
            retry_count=retry_count,
            tenant_id=event.get("tenant_id"),
            branch_id=event.get("branch_id"),
            session_id=event.get("session_id"),
        )
        # Track in drop rate
        drop_tracker.record_dropped()


def handle_incoming_message(
    msg: dict[str, Any],
    event_queue: deque[dict],
    events_dropped: dict[str, int],
    drop_tracker: EventDropRateTracker,
    max_message_size: int = MAX_MESSAGE_SIZE,
    max_queue_size: int = MAX_EVENT_QUEUE_SIZE,
) -> None:
    """
    Handle an incoming Redis message.

    Validates message size and schema, then queues for processing.
    The deque with maxlen handles overflow automatically.

    Args:
        msg: Raw Redis message.
        event_queue: Queue to add validated events.
        events_dropped: Mutable dict with "count" key for tracking.
        drop_tracker: For drop rate metrics.
        max_message_size: Maximum allowed message size.
        max_queue_size: Maximum queue size for drop detection.
    """
    try:
        raw_data = msg["data"]

        # Validate message size
        if isinstance(raw_data, (str, bytes)):
            msg_size = len(
                raw_data.encode() if isinstance(raw_data, str) else raw_data
            )
            if msg_size > max_message_size:
                logger.warning(
                    "Message exceeds size limit",
                    size=msg_size,
                    limit=max_message_size,
                    channel=msg.get("channel"),
                )
                return

        # Parse JSON
        data = json.loads(raw_data)

        # Validate schema
        is_valid, error = validate_event_schema(data)
        if not is_valid:
            logger.warning(
                "Invalid event schema",
                error=error,
                channel=msg.get("channel"),
            )
            return

        # Add timestamp for order tracking and staleness detection
        data["_enqueued_at"] = time.time()

        # Track drops by checking queue size before/after append
        old_size = len(event_queue)
        event_queue.append(data)
        new_size = len(event_queue)

        # Only count as dropped if queue was at capacity AND didn't grow
        if old_size >= max_queue_size and new_size == old_size:
            events_dropped["count"] += 1
            drop_tracker.record_dropped()

            # Log FIRST drop immediately, then every 100th
            is_first_drop = events_dropped["count"] == 1
            is_interval = events_dropped["count"] % WSConstants.DROP_LOG_INTERVAL == 0

            if is_first_drop or is_interval:
                log_level = logging.ERROR if is_first_drop else logging.WARNING
                logger.log(
                    log_level,
                    "Event queue at capacity, oldest event was rotated out",
                    dropped_total=events_dropped["count"],
                    queue_size=new_size,
                    max_size=max_queue_size,
                    first_drop=is_first_drop,
                )
        else:
            drop_tracker.record_processed()

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Redis message", error=str(e))
    except Exception as e:
        logger.error("Error handling Redis message", error=str(e), exc_info=True)
