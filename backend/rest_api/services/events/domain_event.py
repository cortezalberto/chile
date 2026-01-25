"""
Domain Event definition.
Immutable value object for events.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import json


class EventType(str, Enum):
    """Event type enumeration for type safety."""

    # Entity lifecycle
    ENTITY_CREATED = "ENTITY_CREATED"
    ENTITY_UPDATED = "ENTITY_UPDATED"
    ENTITY_DELETED = "ENTITY_DELETED"
    CASCADE_DELETE = "CASCADE_DELETE"

    # Round lifecycle
    ROUND_SUBMITTED = "ROUND_SUBMITTED"
    ROUND_IN_KITCHEN = "ROUND_IN_KITCHEN"
    ROUND_READY = "ROUND_READY"
    ROUND_SERVED = "ROUND_SERVED"
    ROUND_CANCELED = "ROUND_CANCELED"

    # Service calls
    SERVICE_CALL_CREATED = "SERVICE_CALL_CREATED"
    SERVICE_CALL_ACKED = "SERVICE_CALL_ACKED"
    SERVICE_CALL_CLOSED = "SERVICE_CALL_CLOSED"

    # Billing
    CHECK_REQUESTED = "CHECK_REQUESTED"
    CHECK_PAID = "CHECK_PAID"
    PAYMENT_APPROVED = "PAYMENT_APPROVED"
    PAYMENT_REJECTED = "PAYMENT_REJECTED"
    PAYMENT_FAILED = "PAYMENT_FAILED"

    # Tables
    TABLE_SESSION_STARTED = "TABLE_SESSION_STARTED"
    TABLE_STATUS_CHANGED = "TABLE_STATUS_CHANGED"
    TABLE_CLEARED = "TABLE_CLEARED"

    # Kitchen tickets
    TICKET_IN_PROGRESS = "TICKET_IN_PROGRESS"
    TICKET_READY = "TICKET_READY"
    TICKET_DELIVERED = "TICKET_DELIVERED"


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """
    Immutable domain event.

    Represents something that happened in the domain.
    Used for publishing to Redis/WebSocket.

    Attributes:
        event_type: Type of event (from EventType enum)
        entity_type: Type of entity involved (e.g., "Product", "Round")
        entity_id: ID of the entity
        tenant_id: Tenant ID for isolation
        branch_id: Branch ID (optional for tenant-wide events)
        actor_user_id: User who triggered the event
        actor_email: Email of user (optional)
        payload: Additional event data
        timestamp: When the event occurred
    """

    event_type: EventType
    entity_type: str
    entity_id: int
    tenant_id: int
    actor_user_id: int
    branch_id: int | None = None
    actor_email: str | None = None
    payload: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.event_type.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "tenant_id": self.tenant_id,
            "branch_id": self.branch_id,
            "actor_user_id": self.actor_user_id,
            "actor_email": self.actor_email,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DomainEvent":
        """Create from dictionary."""
        event_type = data.get("type") or data.get("event_type")
        if isinstance(event_type, str):
            event_type = EventType(event_type)

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.now(timezone.utc)

        return cls(
            event_type=event_type,
            entity_type=data["entity_type"],
            entity_id=data["entity_id"],
            tenant_id=data["tenant_id"],
            branch_id=data.get("branch_id"),
            actor_user_id=data.get("actor_user_id", 0),
            actor_email=data.get("actor_email"),
            payload=data.get("payload"),
            timestamp=timestamp,
        )

    @classmethod
    def from_json(cls, json_str: str) -> "DomainEvent":
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))

    # ==========================================================================
    # Factory methods for common events
    # ==========================================================================

    @classmethod
    def entity_created(
        cls,
        entity_type: str,
        entity_id: int,
        tenant_id: int,
        actor_user_id: int,
        branch_id: int | None = None,
        actor_email: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "DomainEvent":
        """Create ENTITY_CREATED event."""
        return cls(
            event_type=EventType.ENTITY_CREATED,
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            payload=payload,
        )

    @classmethod
    def entity_updated(
        cls,
        entity_type: str,
        entity_id: int,
        tenant_id: int,
        actor_user_id: int,
        branch_id: int | None = None,
        actor_email: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "DomainEvent":
        """Create ENTITY_UPDATED event."""
        return cls(
            event_type=EventType.ENTITY_UPDATED,
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            payload=payload,
        )

    @classmethod
    def entity_deleted(
        cls,
        entity_type: str,
        entity_id: int,
        tenant_id: int,
        actor_user_id: int,
        branch_id: int | None = None,
        actor_email: str | None = None,
    ) -> "DomainEvent":
        """Create ENTITY_DELETED event."""
        return cls(
            event_type=EventType.ENTITY_DELETED,
            entity_type=entity_type,
            entity_id=entity_id,
            tenant_id=tenant_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            actor_email=actor_email,
        )

    @classmethod
    def round_submitted(
        cls,
        round_id: int,
        tenant_id: int,
        branch_id: int,
        session_id: int,
        table_id: int,
        items_count: int,
    ) -> "DomainEvent":
        """Create ROUND_SUBMITTED event."""
        return cls(
            event_type=EventType.ROUND_SUBMITTED,
            entity_type="Round",
            entity_id=round_id,
            tenant_id=tenant_id,
            branch_id=branch_id,
            actor_user_id=0,  # Diner-initiated
            payload={
                "session_id": session_id,
                "table_id": table_id,
                "items_count": items_count,
            },
        )

    @classmethod
    def round_status_changed(
        cls,
        round_id: int,
        tenant_id: int,
        branch_id: int,
        new_status: str,
        actor_user_id: int,
    ) -> "DomainEvent":
        """Create round status change event."""
        event_type_map = {
            "IN_KITCHEN": EventType.ROUND_IN_KITCHEN,
            "READY": EventType.ROUND_READY,
            "SERVED": EventType.ROUND_SERVED,
            "CANCELED": EventType.ROUND_CANCELED,
        }

        event_type = event_type_map.get(new_status, EventType.ENTITY_UPDATED)

        return cls(
            event_type=event_type,
            entity_type="Round",
            entity_id=round_id,
            tenant_id=tenant_id,
            branch_id=branch_id,
            actor_user_id=actor_user_id,
            payload={"status": new_status},
        )
