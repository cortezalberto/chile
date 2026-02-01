"""
Redis Stream Consumer for Critical Events.

Implements reliable delivery and rewind capability for the WebSocket Gateway.
Reads from 'events:critical' stream using Consumer Groups.

ARCH-STREAM-01: First implementation of Stream Consumer.
MED-STREAM-03 FIX: Added PEL recovery for failed messages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Awaitable, Callable

import redis.asyncio as redis
from redis.exceptions import ResponseError

from shared.infrastructure.events import get_redis_pool
from shared.infrastructure.redis.constants import (
    STREAM_EVENTS_CRITICAL,
    CONSUMER_GROUP_WS_GATEWAY,
)
from shared.config.settings import settings

logger = logging.getLogger(__name__)

# Consumer name (should be stable for single-instance, or unique for fan-out)
# For this implementation, we assume a single gateway instance or shared workload.
# Using a fixed name allows "rewind" after restart.
CONSUMER_NAME = "gateway-primary"

# Stream configuration
BATCH_COUNT = 10
BLOCK_MS = 2000  # 2 seconds blocking wait

# PEL Recovery configuration
PEL_CHECK_INTERVAL_CYCLES = 30  # Check PEL every N main loop cycles (~1 minute)
PEL_MIN_IDLE_MS = 30000  # Only claim messages idle for 30+ seconds
PEL_MAX_RETRIES = 3  # Max retry attempts before sending to DLQ

# RES-MED-02 FIX: Error backoff configuration
ERROR_BASE_DELAY = 1.0  # Base delay in seconds
ERROR_MAX_DELAY = 30.0  # Maximum delay in seconds
ERROR_JITTER_FACTOR = 0.3  # Add up to 30% jitter

# RES-LOW-01 FIX: Dead Letter Queue stream name
STREAM_DLQ = "events:dlq"

def _calculate_error_backoff(error_count: int) -> float:
    """
    RES-MED-02 FIX: Calculate exponential backoff delay with jitter.
    
    Args:
        error_count: Number of consecutive errors
        
    Returns:
        Delay in seconds with jitter applied
    """
    import random
    
    # Exponential delay capped at max
    exponential_delay = min(
        ERROR_BASE_DELAY * (2 ** (error_count - 1)),
        ERROR_MAX_DELAY
    )
    
    # Add jitter to prevent thundering herd
    jitter = exponential_delay * ERROR_JITTER_FACTOR * random.random()
    return exponential_delay + jitter


async def run_stream_consumer(
    on_event: Callable[[dict], Awaitable[None]],
) -> None:
    """
    Run the Redis Stream Consumer loop.
    
    1. Ensures Consumer Group exists (MKSTREAM).
    2. Reads new messages (>) via XREADGROUP.
    3. Processes events via callback.
    4. Acknowledges (XACK) upon success.
    5. Handles errors gracefully.
    6. MED-STREAM-03 FIX: Periodically recovers pending messages (PEL).
    """
    redis_pool = await get_redis_pool()
    
    # 1. Ensure Consumer Group Exists
    try:
        # '$' means "start from now" for NEW group. Existing group keeps its offset.
        # If the stream is new, $ is effectively 0.
        await redis_pool.xgroup_create(
            name=STREAM_EVENTS_CRITICAL,
            groupname=CONSUMER_GROUP_WS_GATEWAY,
            id="$",
            mkstream=True
        )
        logger.info(
            "Created consumer group",
            stream=STREAM_EVENTS_CRITICAL,
            group=CONSUMER_GROUP_WS_GATEWAY
        )
    except ResponseError as e:
        if "BUSYGROUP" in str(e):
            logger.debug(
                "Consumer group already exists",
                stream=STREAM_EVENTS_CRITICAL,
                group=CONSUMER_GROUP_WS_GATEWAY
            )
        else:
            logger.error("Error creating consumer group", error=str(e))
            raise

    logger.info(
        "Starting Stream Consumer",
        stream=STREAM_EVENTS_CRITICAL,
        group=CONSUMER_GROUP_WS_GATEWAY,
        consumer=CONSUMER_NAME
    )

    # MED-STREAM-03 FIX: On startup, recover any pending messages from previous session
    await _recover_pending_messages(redis_pool, on_event)

    # 2. Main Loop
    cycle_count = 0
    while True:
        try:
            cycle_count += 1

            # MED-STREAM-03 FIX: Periodically check for stuck pending messages
            if cycle_count % PEL_CHECK_INTERVAL_CYCLES == 0:
                await _recover_pending_messages(redis_pool, on_event)

            # XREADGROUP GROUP group consumer BLOCK ms STREAMS key >
            entries = await redis_pool.xreadgroup(
                groupname=CONSUMER_GROUP_WS_GATEWAY,
                consumername=CONSUMER_NAME,
                streams={STREAM_EVENTS_CRITICAL: ">"},
                count=BATCH_COUNT,
                block=BLOCK_MS,
            )

            if not entries:
                continue

            # entries is [ [stream_name, [ [id, fields], ... ]] ]
            for stream_name, messages in entries:
                for message_id, fields in messages:
                    await _process_stream_message(
                        redis_pool, 
                        stream_name, 
                        message_id, 
                        fields, 
                        on_event
                    )

        except asyncio.CancelledError:
            logger.info("Stream consumer cancelled")
            break
        except ResponseError as e:
            # FAIL-MED-03 FIX: Handle NOGROUP - consumer group was externally deleted
            if "NOGROUP" in str(e):
                logger.warning(
                    "Consumer group was deleted externally, recreating",
                    stream=STREAM_EVENTS_CRITICAL,
                    group=CONSUMER_GROUP_WS_GATEWAY
                )
                try:
                    await redis_pool.xgroup_create(
                        name=STREAM_EVENTS_CRITICAL,
                        groupname=CONSUMER_GROUP_WS_GATEWAY,
                        id="$",
                        mkstream=True
                    )
                    logger.info("Consumer group recreated successfully")
                except ResponseError as create_error:
                    if "BUSYGROUP" not in str(create_error):
                        logger.error("Failed to recreate consumer group", error=str(create_error))
                        await asyncio.sleep(5)
                continue
            else:
                logger.error("Redis error in stream consumer loop", error=str(e))
                # RES-MED-02 FIX: Use exponential backoff with jitter
                error_count = getattr(run_stream_consumer, '_error_count', 0) + 1
                run_stream_consumer._error_count = error_count
                delay = _calculate_error_backoff(error_count)
                logger.debug("Backing off after Redis error", delay=round(delay, 2), error_count=error_count)
                await asyncio.sleep(delay)
        except Exception as e:
            logger.error("Error in stream consumer loop", error=str(e))
            # RES-MED-02 FIX: Use exponential backoff with jitter for generic errors
            error_count = getattr(run_stream_consumer, '_error_count', 0) + 1
            run_stream_consumer._error_count = error_count
            delay = _calculate_error_backoff(error_count)
            logger.debug("Backing off after generic error", delay=round(delay, 2), error_count=error_count)
            await asyncio.sleep(delay)


async def _recover_pending_messages(
    redis_pool: redis.Redis,
    on_event: Callable[[dict], Awaitable[None]],
) -> int:
    """
    MED-STREAM-03 FIX: Recover pending messages that failed processing.
    
    Uses XAUTOCLAIM to atomically claim and retrieve stale pending messages.
    Returns the number of messages recovered.
    """
    recovered = 0
    try:
        # XAUTOCLAIM key group consumer min-idle-time start [COUNT count]
        # Returns: [next_start_id, [[id, fields], ...], [deleted_ids]]
        result = await redis_pool.xautoclaim(
            name=STREAM_EVENTS_CRITICAL,
            groupname=CONSUMER_GROUP_WS_GATEWAY,
            consumername=CONSUMER_NAME,
            min_idle_time=PEL_MIN_IDLE_MS,
            start_id="0-0",
            count=BATCH_COUNT,
        )

        if not result or len(result) < 2:
            return 0

        # result[1] contains the claimed messages
        claimed_messages = result[1]
        if not claimed_messages:
            return 0

        logger.info(
            "Recovering pending messages",
            count=len(claimed_messages),
            stream=STREAM_EVENTS_CRITICAL
        )

        for message_id, fields in claimed_messages:
            # Check retry count from message metadata
            retry_count = await _get_message_retry_count(
                redis_pool, message_id
            )

            if retry_count >= PEL_MAX_RETRIES:
                # RES-LOW-01 FIX: Send to physical DLQ for manual review
                logger.error(
                    "Message exceeded max retries, moving to DLQ",
                    msg_id=message_id,
                    retries=retry_count,
                    stream=STREAM_EVENTS_CRITICAL
                )
                
                # Store in DLQ stream with metadata
                try:
                    data_str = fields.get("data") or fields.get(b"data") or ""
                    if isinstance(data_str, bytes):
                        data_str = data_str.decode("utf-8")
                    
                    await redis_pool.xadd(
                        STREAM_DLQ,
                        {
                            "original_id": str(message_id),
                            "original_stream": STREAM_EVENTS_CRITICAL,
                            "data": data_str,
                            "retry_count": str(retry_count),
                            "failed_at": str(time.time()),
                            "consumer": CONSUMER_NAME,
                        },
                        maxlen=1000,  # Keep last 1000 DLQ entries
                    )
                    logger.info("Message stored in DLQ", msg_id=message_id, dlq_stream=STREAM_DLQ)
                except Exception as dlq_error:
                    logger.error("Failed to write to DLQ", msg_id=message_id, error=str(dlq_error))
                
                # ACK the original message to remove from PEL
                await redis_pool.xack(
                    STREAM_EVENTS_CRITICAL, 
                    CONSUMER_GROUP_WS_GATEWAY, 
                    message_id
                )
                continue

            # Attempt reprocessing
            success = await _process_stream_message(
                redis_pool,
                STREAM_EVENTS_CRITICAL,
                message_id,
                fields,
                on_event,
                is_retry=True
            )
            if success:
                recovered += 1

        if recovered > 0:
            logger.info("Recovered pending messages", count=recovered)

    except Exception as e:
        logger.warning("Error during PEL recovery", error=str(e))

    return recovered


async def _get_message_retry_count(
    redis_pool: redis.Redis,
    message_id: str,
) -> int:
    """
    Get the delivery count for a message from XPENDING.
    
    XPENDING returns delivery count which we use as retry count.
    """
    try:
        # XPENDING key group [[IDLE min-idle-time] start end count [consumer]]
        pending_info = await redis_pool.xpending_range(
            name=STREAM_EVENTS_CRITICAL,
            groupname=CONSUMER_GROUP_WS_GATEWAY,
            min=message_id,
            max=message_id,
            count=1,
        )
        
        if pending_info and len(pending_info) > 0:
            # Each entry: {'message_id': id, 'consumer': name, 'time_since_delivered': ms, 'times_delivered': count}
            entry = pending_info[0]
            return entry.get("times_delivered", 0)
    except Exception as e:
        logger.debug("Could not get retry count", msg_id=message_id, error=str(e))
    
    return 0


async def _process_stream_message(
    redis_pool: redis.Redis,
    stream: str,
    message_id: str,
    fields: dict,
    on_event: Callable[[dict], Awaitable[None]],
    is_retry: bool = False,
) -> bool:
    """
    Process a single stream message and ACK it.
    
    Returns True if successfully processed, False otherwise.
    """
    try:
        # fields is { "data": "{json_string}" }
        data_str = fields.get("data") or fields.get(b"data")
        if not data_str:
            logger.warning("Empty data in stream message", msg_id=message_id)
            # Ack anyway to skip bad message
            await redis_pool.xack(stream, CONSUMER_GROUP_WS_GATEWAY, message_id)
            return True  # "Success" in terms of handling

        # Handle bytes if returned
        if isinstance(data_str, bytes):
            data_str = data_str.decode("utf-8")

        event_data = json.loads(data_str)
        
        # Dispatch to WebSocket clients
        await on_event(event_data)

        # Acknowledge success
        await redis_pool.xack(stream, CONSUMER_GROUP_WS_GATEWAY, message_id)

        if is_retry:
            logger.info("Successfully reprocessed pending message", msg_id=message_id)

        return True
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON in stream event", msg_id=message_id)
        # Ack to remove from pending (unrecoverable)
        await redis_pool.xack(stream, CONSUMER_GROUP_WS_GATEWAY, message_id)
        return True  # Handled (cannot retry invalid JSON)
        
    except Exception as e:
        logger.error(
            "Error processing stream event", 
            msg_id=message_id, 
            error=str(e),
            is_retry=is_retry
        )
        # DO NOT ACK - leave in PEL for recovery
        return False
