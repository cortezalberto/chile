"""
Redis pub/sub subscriber for the WebSocket gateway.
Listens for events and dispatches them to connected clients.

CRIT-WS-09 FIX: Uses the global Redis connection pool instead of standalone connections.
WS-HIGH-01 FIX: Added JSON schema validation for incoming messages.
"""

from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable, Any

from shared.events import get_redis_pool
from shared.logging import get_logger

logger = get_logger(__name__)


# WS-HIGH-01 FIX: Schema validation for Redis messages
REQUIRED_EVENT_FIELDS = {"type", "tenant_id"}
OPTIONAL_EVENT_FIELDS = {"branch_id", "table_id", "session_id", "entity", "actor", "timestamp"}
VALID_EVENT_TYPES = {
    "ROUND_SUBMITTED", "ROUND_IN_KITCHEN", "ROUND_READY", "ROUND_SERVED",
    "SERVICE_CALL_CREATED", "SERVICE_CALL_ACKED", "SERVICE_CALL_CLOSED",
    "CHECK_REQUESTED", "CHECK_PAID", "TABLE_CLEARED", "TABLE_SESSION_STARTED",
    "TICKET_IN_PROGRESS", "TICKET_READY", "TICKET_DELIVERED",
    "ENTITY_CREATED", "ENTITY_UPDATED", "ENTITY_DELETED", "CASCADE_DELETE",
    "PAYMENT_APPROVED", "PAYMENT_FAILED",
}


def validate_event_schema(data: dict[str, Any]) -> tuple[bool, str | None]:
    """
    WS-HIGH-01 FIX: Validate incoming event schema.

    Returns (is_valid, error_message).
    """
    if not isinstance(data, dict):
        return False, "Event must be a dictionary"

    # Check required fields
    missing = REQUIRED_EVENT_FIELDS - set(data.keys())
    if missing:
        return False, f"Missing required fields: {missing}"

    # Validate event type
    event_type = data.get("type")
    if event_type not in VALID_EVENT_TYPES:
        logger.warning("Unknown event type received", event_type=event_type)
        # Don't reject unknown types - allow for forward compatibility
        # Just log a warning

    # Validate tenant_id is an integer
    tenant_id = data.get("tenant_id")
    if not isinstance(tenant_id, int):
        return False, f"tenant_id must be an integer, got {type(tenant_id).__name__}"

    # Validate optional integer fields if present
    for field in ("branch_id", "table_id", "session_id"):
        if field in data and data[field] is not None:
            if not isinstance(data[field], int):
                return False, f"{field} must be an integer, got {type(data[field]).__name__}"

    return True, None


async def run_subscriber(
    channels: list[str],
    on_message: Callable[[dict], Awaitable[None]],
) -> None:
    """
    Subscribe to Redis channels and dispatch messages.

    This function runs indefinitely, listening for messages
    and calling the callback for each one.

    CRIT-WS-09 FIX: Uses the global Redis pool instead of creating
    a standalone connection. This improves connection management
    and resource utilization.

    Args:
        channels: List of channel patterns to subscribe to.
        on_message: Async callback function that receives parsed message data.
    """
    # CRIT-WS-09 FIX: Use pooled connection instead of standalone
    redis_pool = await get_redis_pool()
    pubsub = redis_pool.pubsub()

    # Subscribe to channels (supports patterns with *)
    await pubsub.psubscribe(*channels)

    logger.info("Redis subscriber started", channels=channels)

    try:
        async for msg in pubsub.listen():
            if msg is None:
                continue

            # Skip subscription confirmation messages
            if msg.get("type") not in ("message", "pmessage"):
                continue

            try:
                data = json.loads(msg["data"])

                # WS-HIGH-01 FIX: Validate event schema before dispatching
                is_valid, error = validate_event_schema(data)
                if not is_valid:
                    logger.warning("Invalid event schema", error=error, channel=msg.get("channel"))
                    continue

                await on_message(data)
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse Redis message", error=str(e))
            except Exception as e:
                logger.error("Error handling Redis message", error=str(e), exc_info=True)

    except asyncio.CancelledError:
        logger.info("Redis subscriber cancelled")
        raise
    finally:
        await pubsub.punsubscribe(*channels)
        # CRIT-WS-09 FIX: Don't close the pool connection - pool manages lifecycle


async def subscribe_to_branch_events(
    branch_ids: list[int],
    on_message: Callable[[dict], Awaitable[None]],
) -> None:
    """
    Subscribe to events for specific branches.

    Args:
        branch_ids: List of branch IDs to subscribe to.
        on_message: Async callback for received messages.
    """
    channels = []
    for branch_id in branch_ids:
        channels.append(f"branch:{branch_id}:*")

    await run_subscriber(channels, on_message)


async def subscribe_to_all_events(
    on_message: Callable[[dict], Awaitable[None]],
) -> None:
    """
    Subscribe to all branch events (for development/admin).

    Args:
        on_message: Async callback for received messages.
    """
    channels = [
        "branch:*:waiters",
        "branch:*:kitchen",
        "branch:*:admin",  # DEF-HIGH-01 FIX: Admin CRUD events
        "tenant:*:admin",  # DEF-HIGH-01 FIX: Tenant-wide admin events
        "user:*",
        "session:*",
    ]
    await run_subscriber(channels, on_message)
