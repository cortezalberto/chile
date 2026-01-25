"""
Event Publisher implementation.
Handles publishing domain events to Redis channels.
"""

import asyncio
from typing import Callable, Any
import concurrent.futures

from shared.config.logging import get_logger
from shared.infrastructure.events import get_redis_pool, publish_event
from .domain_event import DomainEvent, EventType

logger = get_logger(__name__)


class EventPublisher:
    """
    Event publisher for domain events.

    Handles both sync and async publishing to Redis.
    Provides a clean API for publishing events.

    Usage:
        publisher = EventPublisher()

        # Sync (most common in routers)
        publisher.publish_sync(event)

        # Async
        await publisher.publish(event)
    """

    # Channel mapping by event type
    CHANNEL_MAP: dict[EventType, str] = {
        # Admin events
        EventType.ENTITY_CREATED: "admin",
        EventType.ENTITY_UPDATED: "admin",
        EventType.ENTITY_DELETED: "admin",
        EventType.CASCADE_DELETE: "admin",
        # Round events (multiple channels)
        EventType.ROUND_SUBMITTED: "waiter",  # NOT kitchen (goes through dashboard first)
        EventType.ROUND_IN_KITCHEN: "kitchen",
        EventType.ROUND_READY: "kitchen",
        EventType.ROUND_SERVED: "waiter",
        EventType.ROUND_CANCELED: "waiter",
        # Service calls
        EventType.SERVICE_CALL_CREATED: "waiter",
        EventType.SERVICE_CALL_ACKED: "waiter",
        EventType.SERVICE_CALL_CLOSED: "waiter",
        # Billing
        EventType.CHECK_REQUESTED: "waiter",
        EventType.CHECK_PAID: "waiter",
        EventType.PAYMENT_APPROVED: "diner",
        EventType.PAYMENT_REJECTED: "diner",
        EventType.PAYMENT_FAILED: "diner",
        # Tables
        EventType.TABLE_SESSION_STARTED: "waiter",
        EventType.TABLE_STATUS_CHANGED: "waiter",
        EventType.TABLE_CLEARED: "waiter",
        # Kitchen tickets
        EventType.TICKET_IN_PROGRESS: "kitchen",
        EventType.TICKET_READY: "kitchen",
        EventType.TICKET_DELIVERED: "kitchen",
    }

    def __init__(self):
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def _get_channel(self, event: DomainEvent) -> str:
        """
        Determine Redis channel for event.

        Format: {role}:{branch_id} or {role} for tenant-wide
        """
        base_channel = self.CHANNEL_MAP.get(event.event_type, "admin")

        if event.branch_id:
            return f"{base_channel}:{event.branch_id}"
        return base_channel

    async def publish(self, event: DomainEvent) -> bool:
        """
        Publish event asynchronously.

        Args:
            event: Domain event to publish

        Returns:
            True if published successfully
        """
        try:
            channel = self._get_channel(event)
            await publish_event(channel, event.to_dict())

            logger.debug(
                "Event published",
                event_type=event.event_type.value,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                channel=channel,
            )
            return True

        except Exception as e:
            logger.error(
                "Failed to publish event",
                event_type=event.event_type.value,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                error=str(e),
            )
            return False

    def publish_sync(self, event: DomainEvent) -> bool:
        """
        Publish event synchronously.

        Uses thread pool to run async code from sync context.

        Args:
            event: Domain event to publish

        Returns:
            True if published successfully
        """
        try:
            loop = asyncio.get_running_loop()
            # Running inside event loop - use thread pool
            future = self._thread_pool.submit(
                asyncio.run,
                self.publish(event),
            )
            return future.result(timeout=5.0)
        except RuntimeError:
            # No running loop - can use asyncio.run directly
            return asyncio.run(self.publish(event))
        except Exception as e:
            logger.error(
                "Sync publish failed",
                event_type=event.event_type.value,
                error=str(e),
            )
            return False

    async def publish_multiple(self, events: list[DomainEvent]) -> int:
        """
        Publish multiple events.

        Args:
            events: List of events to publish

        Returns:
            Count of successfully published events
        """
        results = await asyncio.gather(
            *[self.publish(e) for e in events],
            return_exceptions=True,
        )

        success_count = sum(1 for r in results if r is True)
        return success_count

    def publish_multiple_sync(self, events: list[DomainEvent]) -> int:
        """
        Publish multiple events synchronously.

        Args:
            events: List of events to publish

        Returns:
            Count of successfully published events
        """
        try:
            loop = asyncio.get_running_loop()
            future = self._thread_pool.submit(
                asyncio.run,
                self.publish_multiple(events),
            )
            return future.result(timeout=10.0)
        except RuntimeError:
            return asyncio.run(self.publish_multiple(events))
        except Exception as e:
            logger.error("Sync multiple publish failed", error=str(e))
            return 0


# =============================================================================
# Singleton instance
# =============================================================================

_publisher: EventPublisher | None = None


def get_event_publisher() -> EventPublisher:
    """Get or create event publisher singleton."""
    global _publisher
    if _publisher is None:
        _publisher = EventPublisher()
    return _publisher


# =============================================================================
# Convenience functions
# =============================================================================


def publish_event_sync(event: DomainEvent) -> bool:
    """Convenience function for sync publishing."""
    return get_event_publisher().publish_sync(event)


async def publish_event_async(event: DomainEvent) -> bool:
    """Convenience function for async publishing."""
    return await get_event_publisher().publish(event)
