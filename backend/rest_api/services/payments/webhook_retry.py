"""
Webhook Retry Queue for failed webhook processing.

REC-02 FIX: Implements a retry mechanism for failed webhook deliveries/processing.

Uses Redis as the backing store for durability across restarts.
Failed webhooks are stored with exponential backoff retry scheduling.

Usage:
    from rest_api.services.webhook_retry import webhook_retry_queue

    # Store failed webhook for retry
    await webhook_retry_queue.enqueue(
        webhook_type="mercadopago",
        payload={"type": "payment", "data": {"id": "123"}},
        error="Connection timeout",
    )

    # Process retries (call from background task)
    await webhook_retry_queue.process_retries()
"""

import asyncio
import json
import time
from dataclasses import dataclass, asdict
from typing import Callable, Awaitable, Any
from datetime import datetime, timezone

from shared.config.logging import get_logger
from shared.infrastructure.events import get_redis_pool

logger = get_logger(__name__)


@dataclass
class WebhookRetryItem:
    """A webhook item queued for retry."""
    id: str
    webhook_type: str
    payload: dict
    error: str
    attempt: int
    created_at: float
    next_retry_at: float
    max_attempts: int = 5


class WebhookRetryQueue:
    """
    Redis-backed queue for webhook retries with exponential backoff.

    Key structure:
    - webhook_retry:pending (sorted set) - items sorted by next_retry_at
    - webhook_retry:item:{id} (hash) - item details
    - webhook_retry:dead_letter (list) - items that exceeded max retries
    """

    # Redis key prefixes
    PENDING_KEY = "webhook_retry:pending"
    ITEM_PREFIX = "webhook_retry:item:"
    DEAD_LETTER_KEY = "webhook_retry:dead_letter"

    # Backoff configuration
    BASE_DELAY_SECONDS = 10
    MAX_DELAY_SECONDS = 3600  # 1 hour max
    MAX_ATTEMPTS = 5

    def __init__(self):
        self._handlers: dict[str, Callable[[dict], Awaitable[bool]]] = {}
        self._processing = False
        self._lock = asyncio.Lock()

    def register_handler(
        self,
        webhook_type: str,
        handler: Callable[[dict], Awaitable[bool]],
    ) -> None:
        """
        Register a handler for a webhook type.

        Handler should return True on success, False on failure.
        """
        self._handlers[webhook_type] = handler
        logger.info(f"Registered webhook retry handler for: {webhook_type}")

    async def enqueue(
        self,
        webhook_type: str,
        payload: dict,
        error: str,
        attempt: int = 0,
        item_id: str | None = None,
    ) -> str:
        """
        Enqueue a failed webhook for retry.

        Args:
            webhook_type: Type of webhook (e.g., "mercadopago")
            payload: Original webhook payload
            error: Error message from failed processing
            attempt: Current attempt number (0 for first failure)
            item_id: Existing item ID (for re-enqueue after failed retry)

        Returns:
            Item ID
        """
        redis = await get_redis_pool()

        # Generate ID if not provided
        if not item_id:
            item_id = f"{webhook_type}:{int(time.time() * 1000)}"

        # Calculate next retry time with exponential backoff
        delay = min(
            self.BASE_DELAY_SECONDS * (2 ** attempt),
            self.MAX_DELAY_SECONDS,
        )
        next_retry_at = time.time() + delay

        item = WebhookRetryItem(
            id=item_id,
            webhook_type=webhook_type,
            payload=payload,
            error=error,
            attempt=attempt + 1,
            created_at=time.time() if attempt == 0 else 0,  # Keep original created_at
            next_retry_at=next_retry_at,
            max_attempts=self.MAX_ATTEMPTS,
        )

        # Store item details
        item_key = f"{self.ITEM_PREFIX}{item_id}"
        item_data = {
            "id": item.id,
            "webhook_type": item.webhook_type,
            "payload": json.dumps(item.payload),
            "error": item.error,
            "attempt": str(item.attempt),
            "created_at": str(item.created_at) if item.created_at else "",
            "next_retry_at": str(item.next_retry_at),
            "max_attempts": str(item.max_attempts),
        }

        # If re-enqueueing, preserve original created_at
        if attempt > 0:
            existing = await redis.hget(item_key, "created_at")
            if existing:
                item_data["created_at"] = existing

        await redis.hset(item_key, mapping=item_data)

        # Add to sorted set for scheduled processing
        await redis.zadd(self.PENDING_KEY, {item_id: next_retry_at})

        logger.info(
            f"Webhook enqueued for retry",
            item_id=item_id,
            webhook_type=webhook_type,
            attempt=item.attempt,
            next_retry_in=f"{delay:.1f}s",
        )

        return item_id

    async def _get_item(self, item_id: str) -> WebhookRetryItem | None:
        """Get item details from Redis."""
        redis = await get_redis_pool()
        item_key = f"{self.ITEM_PREFIX}{item_id}"

        data = await redis.hgetall(item_key)
        if not data:
            return None

        return WebhookRetryItem(
            id=data.get("id", item_id),
            webhook_type=data.get("webhook_type", ""),
            payload=json.loads(data.get("payload", "{}")),
            error=data.get("error", ""),
            attempt=int(data.get("attempt", "0")),
            created_at=float(data.get("created_at", "0") or "0"),
            next_retry_at=float(data.get("next_retry_at", "0")),
            max_attempts=int(data.get("max_attempts", str(self.MAX_ATTEMPTS))),
        )

    async def _remove_item(self, item_id: str) -> None:
        """Remove item from queue and storage."""
        redis = await get_redis_pool()
        item_key = f"{self.ITEM_PREFIX}{item_id}"

        await redis.zrem(self.PENDING_KEY, item_id)
        await redis.delete(item_key)

    async def _move_to_dead_letter(self, item: WebhookRetryItem) -> None:
        """Move item to dead letter queue after max retries exceeded."""
        redis = await get_redis_pool()

        dead_letter_entry = {
            "id": item.id,
            "webhook_type": item.webhook_type,
            "payload": item.payload,
            "error": item.error,
            "attempts": item.attempt,
            "created_at": item.created_at,
            "failed_at": time.time(),
        }

        await redis.lpush(self.DEAD_LETTER_KEY, json.dumps(dead_letter_entry))

        # Trim dead letter queue to prevent unbounded growth
        await redis.ltrim(self.DEAD_LETTER_KEY, 0, 999)

        # Remove from pending
        await self._remove_item(item.id)

        logger.warning(
            f"Webhook moved to dead letter queue",
            item_id=item.id,
            webhook_type=item.webhook_type,
            attempts=item.attempt,
        )

    async def process_retries(self, batch_size: int = 10) -> int:
        """
        Process pending retries that are due.

        Args:
            batch_size: Maximum items to process in one batch

        Returns:
            Number of items processed
        """
        async with self._lock:
            if self._processing:
                return 0
            self._processing = True

        try:
            redis = await get_redis_pool()

            # Get items due for retry (score <= current time)
            now = time.time()
            due_items = await redis.zrangebyscore(
                self.PENDING_KEY,
                min=0,
                max=now,
                start=0,
                num=batch_size,
            )

            processed = 0

            for item_id in due_items:
                item = await self._get_item(item_id)
                if not item:
                    await redis.zrem(self.PENDING_KEY, item_id)
                    continue

                # Check if we have a handler
                handler = self._handlers.get(item.webhook_type)
                if not handler:
                    logger.warning(f"No handler for webhook type: {item.webhook_type}")
                    await self._move_to_dead_letter(item)
                    continue

                # Attempt retry
                try:
                    success = await handler(item.payload)

                    if success:
                        await self._remove_item(item.id)
                        logger.info(
                            f"Webhook retry successful",
                            item_id=item.id,
                            webhook_type=item.webhook_type,
                            attempt=item.attempt,
                        )
                    else:
                        # Handler returned False - retry again
                        if item.attempt >= item.max_attempts:
                            await self._move_to_dead_letter(item)
                        else:
                            await self.enqueue(
                                webhook_type=item.webhook_type,
                                payload=item.payload,
                                error="Handler returned False",
                                attempt=item.attempt,
                                item_id=item.id,
                            )

                except Exception as e:
                    logger.error(
                        f"Webhook retry failed",
                        item_id=item.id,
                        error=str(e),
                        attempt=item.attempt,
                    )

                    if item.attempt >= item.max_attempts:
                        await self._move_to_dead_letter(item)
                    else:
                        await self.enqueue(
                            webhook_type=item.webhook_type,
                            payload=item.payload,
                            error=str(e),
                            attempt=item.attempt,
                            item_id=item.id,
                        )

                processed += 1

            return processed

        finally:
            self._processing = False

    async def get_pending_count(self) -> int:
        """Get count of pending retries."""
        redis = await get_redis_pool()
        return await redis.zcard(self.PENDING_KEY)

    async def get_dead_letter_count(self) -> int:
        """Get count of dead letter items."""
        redis = await get_redis_pool()
        return await redis.llen(self.DEAD_LETTER_KEY)

    async def get_stats(self) -> dict:
        """Get queue statistics for monitoring."""
        return {
            "pending_count": await self.get_pending_count(),
            "dead_letter_count": await self.get_dead_letter_count(),
            "registered_handlers": list(self._handlers.keys()),
        }


# =============================================================================
# Global Instance
# =============================================================================

webhook_retry_queue = WebhookRetryQueue()


# =============================================================================
# Background Task for Processing Retries
# =============================================================================

async def start_retry_processor(interval_seconds: float = 30.0) -> None:
    """
    Start background task to process webhook retries.

    Call this from application startup.
    """
    logger.info(f"Starting webhook retry processor (interval: {interval_seconds}s)")

    while True:
        try:
            processed = await webhook_retry_queue.process_retries()
            if processed > 0:
                logger.info(f"Processed {processed} webhook retries")
        except Exception as e:
            logger.error(f"Webhook retry processor error: {e}")

        await asyncio.sleep(interval_seconds)
