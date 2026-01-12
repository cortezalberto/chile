"""
Redis pub/sub subscriber for the WebSocket gateway.
Listens for events and dispatches them to connected clients.
"""

from __future__ import annotations

import asyncio
import json
from typing import Awaitable, Callable

import redis.asyncio as redis

from shared.settings import REDIS_URL
from shared.logging import get_logger

logger = get_logger(__name__)


async def run_subscriber(
    channels: list[str],
    on_message: Callable[[dict], Awaitable[None]],
    redis_url: str = REDIS_URL,
) -> None:
    """
    Subscribe to Redis channels and dispatch messages.

    This function runs indefinitely, listening for messages
    and calling the callback for each one.

    Args:
        channels: List of channel patterns to subscribe to.
        on_message: Async callback function that receives parsed message data.
        redis_url: Redis connection URL.
    """
    r = redis.from_url(redis_url, decode_responses=True)
    pubsub = r.pubsub()

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
        await r.close()


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
