"""
Secure Audit Logging.

SEC-03: Tamper-evident audit logging with hash chain.
"""

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from shared.config.logging import get_logger

logger = get_logger(__name__)


async def get_audit_log() -> "SecureAuditLog":
    """
    Get a SecureAuditLog instance with Redis connection.
    
    SEC-AUDIT-03: Helper to facilitate integration of audit logging
    in async endpoints.
    """
    from shared.infrastructure.events import get_redis_pool
    redis_client = await get_redis_pool()
    return SecureAuditLog(redis_client)



@dataclass
class AuditEvent:
    """
    Immutable audit event record.
    
    Each event includes a hash of the previous event,
    creating a tamper-evident chain.
    """
    
    # Event metadata
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    event_type: str = ""
    action: str = ""
    
    # Actor information
    user_id: Optional[int] = None
    user_email: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Resource information
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    
    # Event data
    data: dict[str, Any] = field(default_factory=dict)
    
    # Chain verification
    prev_hash: str = ""
    hash: str = ""
    sequence: int = 0
    
    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this event."""
        # Create deterministic payload
        payload = (
            f"{self.prev_hash}:"
            f"{self.timestamp}:"
            f"{self.event_type}:"
            f"{self.action}:"
            f"{self.user_id}:"
            f"{self.resource_type}:"
            f"{self.resource_id}:"
            f"{json.dumps(self.data, sort_keys=True)}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class SecureAuditLog:
    """
    Tamper-evident audit logging service.
    
    SEC-03: Creates a hash chain where each event includes
    the hash of the previous event, making tampering detectable.
    """
    
    PREFIX = "audit:events"
    LAST_HASH_KEY = "audit:last_hash"
    SEQUENCE_KEY = "audit:sequence"
    
    def __init__(self, redis_client):
        self._redis = redis_client
    
    async def log(
        self,
        event_type: str,
        action: str,
        user_id: Optional[int] = None,
        user_email: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[int] = None,
        data: Optional[dict] = None,
    ) -> AuditEvent:
        """
        Log an audit event.
        
        Creates an immutable record with hash chain for tamper detection.
        """
        # Get previous hash and sequence atomically
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.get(self.LAST_HASH_KEY)
            pipe.incr(self.SEQUENCE_KEY)
            results = await pipe.execute()
        
        prev_hash = results[0] or "genesis"
        sequence = results[1]
        
        # Create event
        event = AuditEvent(
            event_type=event_type,
            action=action,
            user_id=user_id,
            user_email=user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type=resource_type,
            resource_id=resource_id,
            data=data or {},
            prev_hash=prev_hash,
            sequence=sequence,
        )
        
        # Compute and set hash
        event.hash = event.compute_hash()
        
        # Store event and update last hash
        event_key = f"{self.PREFIX}:{sequence}"
        event_json = json.dumps(event.to_dict())
        
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.set(event_key, event_json)
            pipe.set(self.LAST_HASH_KEY, event.hash)
            # Keep sorted set for time-range queries
            pipe.zadd(
                f"{self.PREFIX}:index",
                {str(sequence): datetime.now(timezone.utc).timestamp()},
            )
            await pipe.execute()
        
        logger.info(
            "Audit event logged",
            event_type=event_type,
            action=action,
            sequence=sequence,
        )
        
        return event
    
    async def get_events(
        self,
        start_sequence: int = 0,
        end_sequence: Optional[int] = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Get audit events by sequence range."""
        if end_sequence is None:
            end_sequence = await self._redis.get(self.SEQUENCE_KEY)
            end_sequence = int(end_sequence) if end_sequence else 0
        
        events = []
        for seq in range(start_sequence, min(end_sequence + 1, start_sequence + limit)):
            event_json = await self._redis.get(f"{self.PREFIX}:{seq}")
            if event_json:
                event_data = json.loads(event_json)
                events.append(AuditEvent(**event_data))
        
        return events
    
    async def get_events_by_user(
        self,
        user_id: int,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Get audit events for a specific user."""
        events = await self.get_events(limit=limit * 3)  # Oversample
        user_events = [e for e in events if e.user_id == user_id]
        return user_events[:limit]
    
    async def get_events_by_resource(
        self,
        resource_type: str,
        resource_id: int,
        limit: int = 100,
    ) -> list[AuditEvent]:
        """Get audit events for a specific resource."""
        events = await self.get_events(limit=limit * 3)
        resource_events = [
            e for e in events
            if e.resource_type == resource_type and e.resource_id == resource_id
        ]
        return resource_events[:limit]
    
    async def verify_chain(
        self,
        start_sequence: int = 1,
        end_sequence: Optional[int] = None,
    ) -> tuple[bool, Optional[int]]:
        """
        Verify the integrity of the audit chain.
        
        Returns (is_valid, first_invalid_sequence).
        """
        if end_sequence is None:
            end_sequence = await self._redis.get(self.SEQUENCE_KEY)
            end_sequence = int(end_sequence) if end_sequence else 0
        
        prev_hash = "genesis"
        
        for seq in range(start_sequence, end_sequence + 1):
            event_json = await self._redis.get(f"{self.PREFIX}:{seq}")
            if not event_json:
                logger.error("Missing audit event", sequence=seq)
                return False, seq
            
            event_data = json.loads(event_json)
            event = AuditEvent(**event_data)
            
            # Verify previous hash
            if event.prev_hash != prev_hash:
                logger.error(
                    "Audit chain broken: prev_hash mismatch",
                    sequence=seq,
                    expected=prev_hash,
                    actual=event.prev_hash,
                )
                return False, seq
            
            # Verify event hash
            computed_hash = event.compute_hash()
            if event.hash != computed_hash:
                logger.error(
                    "Audit chain broken: hash mismatch",
                    sequence=seq,
                    stored=event.hash,
                    computed=computed_hash,
                )
                return False, seq
            
            prev_hash = event.hash
        
        logger.info(
            "Audit chain verified",
            start=start_sequence,
            end=end_sequence,
        )
        
        return True, None
    
    async def get_chain_stats(self) -> dict[str, Any]:
        """Get statistics about the audit chain."""
        sequence = await self._redis.get(self.SEQUENCE_KEY)
        sequence = int(sequence) if sequence else 0
        
        last_hash = await self._redis.get(self.LAST_HASH_KEY)
        
        # Get oldest event
        oldest = None
        if sequence > 0:
            oldest_json = await self._redis.get(f"{self.PREFIX}:1")
            if oldest_json:
                oldest_data = json.loads(oldest_json)
                oldest = oldest_data.get("timestamp")
        
        # Get newest event
        newest = None
        if sequence > 0:
            newest_json = await self._redis.get(f"{self.PREFIX}:{sequence}")
            if newest_json:
                newest_data = json.loads(newest_json)
                newest = newest_data.get("timestamp")
        
        return {
            "total_events": sequence,
            "last_hash": last_hash,
            "oldest_event": oldest,
            "newest_event": newest,
        }
