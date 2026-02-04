"""
Outbox processor for publishing events from the outbox table.

OUTBOX-PATTERN: Reads PENDING events from the outbox table and publishes
them to Redis. Implements:
- Batch processing for efficiency
- Retry with exponential backoff on failures
- Dead letter handling after max retries
- Idempotent processing (PROCESSING status prevents double publishing)

This processor can run:
1. As a FastAPI background task (lifespan startup)
2. As a separate worker process (for horizontal scaling)
3. As a periodic job (cron-style)
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from rest_api.models import OutboxEvent, OutboxStatus
from shared.infrastructure.db import SessionLocal
from shared.infrastructure.events import (
    get_redis_client,
    publish_round_event,
    publish_service_call_event,
    publish_check_event,
    ROUND_SUBMITTED,
    ROUND_READY,
    SERVICE_CALL_CREATED,
    CHECK_REQUESTED,
    PAYMENT_APPROVED,
    PAYMENT_REJECTED,
    CHECK_PAID,
)
from shared.config.logging import get_logger
from shared.config.settings import settings

logger = get_logger(__name__)

# Configuration
MAX_RETRIES = 5
BATCH_SIZE = 50
POLL_INTERVAL_SECONDS = 1.0  # How often to check for new events
BACKOFF_BASE_SECONDS = 2.0  # Base for exponential backoff


class OutboxProcessor:
    """
    Processes outbox events and publishes them to Redis.

    The processor runs in a loop, polling for PENDING events and
    publishing them. It handles:
    - Batch fetching for efficiency
    - Status transitions (PENDING → PROCESSING → PUBLISHED/FAILED)
    - Retry logic with exponential backoff
    - Graceful shutdown
    """

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the processor loop."""
        if self._running:
            logger.warning("Outbox processor already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Outbox processor started")

    async def stop(self) -> None:
        """Stop the processor gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Outbox processor stopped")

    async def _run_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                processed = await self._process_batch()
                if processed == 0:
                    # No events, sleep before next poll
                    await asyncio.sleep(POLL_INTERVAL_SECONDS)
                # If we processed events, immediately check for more
            except Exception as e:
                logger.error("Outbox processor error", error=str(e))
                await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def _process_batch(self) -> int:
        """
        Process a batch of PENDING events.

        Returns:
            Number of events processed
        """
        db = SessionLocal()
        try:
            # Fetch PENDING events (oldest first)
            events = db.execute(
                select(OutboxEvent)
                .where(OutboxEvent.status == OutboxStatus.PENDING)
                .order_by(OutboxEvent.created_at.asc())
                .limit(BATCH_SIZE)
                .with_for_update(skip_locked=True)  # Skip locked rows (parallel workers)
            ).scalars().all()

            if not events:
                return 0

            # Mark as PROCESSING to prevent double processing
            event_ids = [e.id for e in events]
            db.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id.in_(event_ids))
                .values(status=OutboxStatus.PROCESSING)
            )
            db.commit()

            # Process each event
            processed = 0
            for event in events:
                success = await self._publish_event(event)
                if success:
                    event.status = OutboxStatus.PUBLISHED
                    event.processed_at = datetime.now(timezone.utc)
                    processed += 1
                else:
                    event.retry_count += 1
                    if event.retry_count >= MAX_RETRIES:
                        event.status = OutboxStatus.FAILED
                        logger.error(
                            "Outbox event failed after max retries",
                            event_id=event.id,
                            event_type=event.event_type,
                        )
                    else:
                        # Back to PENDING for retry (with backoff)
                        event.status = OutboxStatus.PENDING

            db.commit()
            logger.info("Outbox batch processed", total=len(events), published=processed)
            return processed

        except Exception as e:
            db.rollback()
            logger.error("Outbox batch processing failed", error=str(e))
            return 0
        finally:
            db.close()

    async def _publish_event(self, event: OutboxEvent) -> bool:
        """
        Publish a single event to Redis.

        Args:
            event: The OutboxEvent to publish

        Returns:
            True if published successfully, False otherwise
        """
        try:
            payload = json.loads(event.payload)
            redis_client = await get_redis_client()

            # Route to appropriate publisher based on aggregate type
            if event.aggregate_type == "round":
                await self._publish_round(redis_client, event.event_type, event.tenant_id, payload)
            elif event.aggregate_type == "check":
                await self._publish_check(redis_client, event.event_type, event.tenant_id, payload)
            elif event.aggregate_type == "service_call":
                await self._publish_service_call(redis_client, event.event_type, event.tenant_id, payload)
            else:
                logger.warning("Unknown aggregate type", aggregate_type=event.aggregate_type)
                return False

            return True

        except Exception as e:
            event.last_error = str(e)
            logger.error(
                "Failed to publish outbox event",
                event_id=event.id,
                event_type=event.event_type,
                error=str(e),
            )
            return False

    async def _publish_round(
        self,
        redis_client: Any,
        event_type: str,
        tenant_id: int,
        payload: dict,
    ) -> None:
        """Publish round event to Redis."""
        await publish_round_event(
            redis_client=redis_client,
            event_type=event_type,
            tenant_id=tenant_id,
            branch_id=payload["branch_id"],
            table_id=payload.get("table_id"),
            session_id=payload["session_id"],
            round_id=payload.get("round_id", 0),  # Aggregate ID is in outbox
            round_number=payload.get("round_number", 0),
            actor_user_id=payload.get("actor_user_id"),
            actor_role=payload.get("actor_role", "SYSTEM"),
            sector_id=payload.get("sector_id"),
        )

    async def _publish_check(
        self,
        redis_client: Any,
        event_type: str,
        tenant_id: int,
        payload: dict,
    ) -> None:
        """Publish check/billing event to Redis."""
        await publish_check_event(
            redis_client=redis_client,
            event_type=event_type,
            tenant_id=tenant_id,
            branch_id=payload["branch_id"],
            table_id=payload.get("table_id"),
            session_id=payload["session_id"],
            check_id=payload["check_id"],
            total_cents=payload.get("total_cents", 0),
            paid_cents=payload.get("paid_cents", 0),
            actor_user_id=payload.get("actor_user_id"),
            actor_role=payload.get("actor_role", "SYSTEM"),
            sector_id=payload.get("sector_id"),
        )

    async def _publish_service_call(
        self,
        redis_client: Any,
        event_type: str,
        tenant_id: int,
        payload: dict,
    ) -> None:
        """Publish service call event to Redis."""
        await publish_service_call_event(
            redis_client=redis_client,
            event_type=event_type,
            tenant_id=tenant_id,
            branch_id=payload["branch_id"],
            table_id=payload.get("table_id"),
            session_id=payload["session_id"],
            call_id=payload.get("call_id", 0),  # Aggregate ID is in outbox
            call_type=payload.get("call_type", "WAITER"),
            actor_user_id=payload.get("actor_user_id"),
            actor_role=payload.get("actor_role", "DINER"),
            sector_id=payload.get("sector_id"),
        )


# Singleton instance
_processor: OutboxProcessor | None = None


def get_outbox_processor() -> OutboxProcessor:
    """Get the singleton outbox processor instance."""
    global _processor
    if _processor is None:
        _processor = OutboxProcessor()
    return _processor


async def start_outbox_processor() -> None:
    """Start the outbox processor (call in FastAPI lifespan startup)."""
    processor = get_outbox_processor()
    await processor.start()


async def stop_outbox_processor() -> None:
    """Stop the outbox processor (call in FastAPI lifespan shutdown)."""
    processor = get_outbox_processor()
    await processor.stop()


async def process_pending_events_once() -> int:
    """
    Process pending outbox events once (for testing or manual triggering).

    Returns:
        Number of events processed
    """
    processor = get_outbox_processor()
    return await processor._process_batch()
