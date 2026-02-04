"""
Dead Letter Queue Processor.

REDIS-04: Process and analyze messages in the DLQ.
"""

import json
from datetime import datetime, timezone
from typing import Any

from shared.config.logging import get_logger
from shared.infrastructure.redis.constants import PREFIX_WEBHOOK_DEAD_LETTER

logger = get_logger(__name__)


class DeadLetterProcessor:
    """
    Processes messages from the Dead Letter Queue.
    
    REDIS-04: DLQ management for failed event processing.
    
    Provides:
    - DLQ message retrieval and analysis
    - Retry logic for recoverable errors
    - Archival for unrecoverable messages
    """
    
    # Error types that are retryable
    RETRYABLE_ERRORS = {
        "timeout",
        "connection_refused",
        "rate_limited",
        "temporary_failure",
    }
    
    # Max retry attempts before archival
    MAX_RETRIES = 3
    
    def __init__(self, redis_client):
        self._redis = redis_client
    
    async def get_dlq_stats(self) -> dict[str, Any]:
        """
        Get statistics about the DLQ.
        
        Returns message count, oldest message, error breakdown.
        """
        # Get DLQ length
        dlq_key = f"{PREFIX_WEBHOOK_DEAD_LETTER}queue"
        length = await self._redis.llen(dlq_key)
        
        if length == 0:
            return {
                "message_count": 0,
                "oldest_message": None,
                "error_breakdown": {},
            }
        
        # Get oldest message (at the end of list)
        oldest_raw = await self._redis.lindex(dlq_key, -1)
        oldest = json.loads(oldest_raw) if oldest_raw else None
        
        # Sample messages for error breakdown (up to 100)
        sample_size = min(length, 100)
        messages_raw = await self._redis.lrange(dlq_key, 0, sample_size - 1)
        
        error_breakdown: dict[str, int] = {}
        for msg_raw in messages_raw:
            msg = json.loads(msg_raw)
            error_type = msg.get("error_type", "unknown")
            error_breakdown[error_type] = error_breakdown.get(error_type, 0) + 1
        
        return {
            "message_count": length,
            "oldest_message": oldest.get("added_at") if oldest else None,
            "error_breakdown": error_breakdown,
        }
    
    async def process_dlq(
        self,
        max_messages: int = 100,
        dry_run: bool = False,
    ) -> dict[str, int]:
        """
        Process messages from the DLQ.
        
        Args:
            max_messages: Maximum messages to process
            dry_run: If True, analyze but don't modify
            
        Returns dict with counts: retried, archived, skipped.
        """
        dlq_key = f"{PREFIX_WEBHOOK_DEAD_LETTER}queue"
        retry_key = f"{PREFIX_WEBHOOK_DEAD_LETTER}retry"
        
        results = {"retried": 0, "archived": 0, "skipped": 0}
        
        messages_raw = await self._redis.lrange(dlq_key, 0, max_messages - 1)
        
        for msg_raw in messages_raw:
            msg = json.loads(msg_raw)
            
            action = self._analyze_message(msg)
            
            if action == "retry":
                if not dry_run:
                    await self._requeue_message(msg, retry_key)
                results["retried"] += 1
                
            elif action == "archive":
                if not dry_run:
                    await self._archive_message(msg)
                results["archived"] += 1
                
            else:
                results["skipped"] += 1
        
        # Trim processed messages
        if not dry_run and messages_raw:
            await self._redis.ltrim(dlq_key, len(messages_raw), -1)
        
        logger.info(
            "DLQ processing complete",
            dry_run=dry_run,
            **results,
        )
        
        return results
    
    def _analyze_message(self, msg: dict[str, Any]) -> str:
        """
        Analyze a DLQ message and decide action.
        
        Returns: "retry", "archive", or "skip"
        """
        error_type = msg.get("error_type", "unknown")
        retry_count = msg.get("retry_count", 0)
        
        # Check if retryable
        if error_type not in self.RETRYABLE_ERRORS:
            return "archive"
        
        # Check retry count
        if retry_count >= self.MAX_RETRIES:
            return "archive"
        
        return "retry"
    
    async def _requeue_message(self, msg: dict[str, Any], retry_key: str) -> None:
        """Requeue a message for retry."""
        msg["retry_count"] = msg.get("retry_count", 0) + 1
        msg["requeued_at"] = datetime.now(timezone.utc).isoformat()
        
        await self._redis.lpush(retry_key, json.dumps(msg))
        
        logger.debug(
            "Message requeued for retry",
            event_id=msg.get("event_id"),
            retry_count=msg["retry_count"],
        )
    
    async def _archive_message(self, msg: dict[str, Any]) -> None:
        """
        Archive a message (e.g., to S3 or permanent storage).
        
        For now, logs the message for manual review.
        """
        logger.warning(
            "DLQ message archived (unrecoverable)",
            event_id=msg.get("event_id"),
            event_type=msg.get("event_type"),
            error_type=msg.get("error_type"),
            original_error=msg.get("error_message"),
        )
        
        # TODO: Implement S3/persistent storage archival
        # await self._archive_to_s3(msg)
    
    async def purge_dlq(self) -> int:
        """
        Purge all messages from DLQ.
        
        WARNING: This permanently deletes all DLQ messages.
        Returns number of messages purged.
        """
        dlq_key = f"{PREFIX_WEBHOOK_DEAD_LETTER}queue"
        
        length = await self._redis.llen(dlq_key)
        await self._redis.delete(dlq_key)
        
        logger.warning("DLQ purged", messages_deleted=length)
        
        return length
