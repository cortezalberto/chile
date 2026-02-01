"""
Redis Lua Scripts for Atomic Operations.

REDIS-02 FIX: Implements atomic rate limiting using Lua scripts.
These scripts execute atomically on Redis, preventing race conditions.

Usage:
    from ws_gateway.components.redis.lua_scripts import (
        get_rate_limit_script,
        execute_rate_limit_check,
    )
    
    result = await execute_rate_limit_check(redis, connection_id, limit, window)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import redis.asyncio as redis

logger = logging.getLogger(__name__)


# =============================================================================
# Rate Limiting Lua Script
# =============================================================================

# REDIS-02 FIX: Atomic rate limiting script
# This script atomically checks and increments the rate limit counter.
# Benefits over Python implementation:
# - No race conditions between GET and INCR
# - Single round-trip to Redis
# - TTL is set atomically with first increment

RATE_LIMIT_SCRIPT = """
-- Rate limiting script with sliding window approximation
-- KEYS[1] = rate limit key (e.g., "ratelimit:ws:12345")
-- ARGV[1] = max messages allowed
-- ARGV[2] = window size in seconds
-- ARGV[3] = current timestamp (for testability)
-- Returns: {allowed (0/1), current_count, ttl_remaining}

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

-- Get current count
local current = tonumber(redis.call('GET', key) or '0')

-- Check if limit exceeded
if current >= limit then
    local ttl = redis.call('TTL', key)
    return {0, current, ttl}
end

-- Increment counter
local new_count = redis.call('INCR', key)

-- Set expiration on first request (when count was 0)
if current == 0 then
    redis.call('EXPIRE', key, window)
end

local ttl = redis.call('TTL', key)
return {1, new_count, ttl}
"""

# Script SHA for cached execution
_rate_limit_script_sha: str | None = None


async def get_rate_limit_script_sha(
    redis_client: "redis.Redis",
) -> str:
    """
    Load the rate limit script into Redis and return its SHA.
    
    The SHA is cached to avoid reloading on every call.
    Uses SCRIPT LOAD for efficient execution via EVALSHA.
    
    Args:
        redis_client: Redis async client
        
    Returns:
        Script SHA for use with EVALSHA
    """
    global _rate_limit_script_sha
    
    if _rate_limit_script_sha is None:
        _rate_limit_script_sha = await redis_client.script_load(RATE_LIMIT_SCRIPT)
        logger.debug(
            "Rate limit script loaded",
            sha=_rate_limit_script_sha[:8],
        )
    
    return _rate_limit_script_sha


async def execute_rate_limit_check(
    redis_client: "redis.Redis",
    connection_id: str,
    max_messages: int,
    window_seconds: int,
    current_timestamp: float | None = None,
) -> tuple[bool, int, int]:
    """
    REDIS-02 FIX: Execute atomic rate limit check using Lua script.
    
    This is more efficient than the Python implementation because:
    1. Single round-trip to Redis
    2. Atomic check-and-increment (no race conditions)
    3. TTL set atomically
    
    Args:
        redis_client: Redis async client
        connection_id: Unique identifier for the connection
        max_messages: Maximum messages allowed per window
        window_seconds: Window size in seconds
        current_timestamp: Optional timestamp for testing
        
    Returns:
        Tuple of (allowed, current_count, ttl_remaining)
    """
    import time
    
    if current_timestamp is None:
        current_timestamp = time.time()
    
    key = f"ratelimit:ws:{connection_id}"
    
    try:
        sha = await get_rate_limit_script_sha(redis_client)
        result = await redis_client.evalsha(
            sha,
            1,  # Number of keys
            key,
            max_messages,
            window_seconds,
            int(current_timestamp),
        )
        
        allowed = bool(result[0])
        current_count = int(result[1])
        ttl = int(result[2]) if result[2] and result[2] > 0 else window_seconds
        
        return allowed, current_count, ttl
        
    except Exception as e:
        # Fallback: allow request if Redis fails
        logger.warning(
            "Rate limit script failed, allowing request",
            error=str(e),
            connection_id=connection_id,
        )
        return True, 0, window_seconds


# =============================================================================
# Broadcast Pipeline Helper
# =============================================================================

PIPELINE_BATCH_SIZE = 100  # Max commands per pipeline


async def pipeline_broadcast_acks(
    redis_client: "redis.Redis",
    stream: str,
    group: str,
    message_ids: list[str],
) -> int:
    """
    REDIS-01 FIX: Batch ACK messages using Redis PIPELINE.
    
    Instead of ACKing messages one by one, batch them into a single
    pipeline for significant performance improvement.
    
    Args:
        redis_client: Redis async client
        stream: Stream name
        group: Consumer group name
        message_ids: List of message IDs to acknowledge
        
    Returns:
        Number of successfully acknowledged messages
    """
    if not message_ids:
        return 0
    
    total_acked = 0
    
    # Process in batches to avoid huge pipelines
    for i in range(0, len(message_ids), PIPELINE_BATCH_SIZE):
        batch = message_ids[i:i + PIPELINE_BATCH_SIZE]
        
        async with redis_client.pipeline(transaction=False) as pipe:
            for msg_id in batch:
                pipe.xack(stream, group, msg_id)
            
            results = await pipe.execute()
            total_acked += sum(1 for r in results if r)
    
    logger.debug(
        "Batch ACK completed",
        stream=stream,
        requested=len(message_ids),
        acked=total_acked,
    )
    
    return total_acked
