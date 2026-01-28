"""
Event Value Objects for WebSocket Gateway.

Domain objects representing WebSocket events with integrated validation.
Replaces anemic dict-based events with rich domain objects.

ARCH-AP-06 FIX: Replaced Anemic Domain Model with Value Objects.
ARCH-04 FIX: Centralized event schema definition.
CRIT-DEEP-03 FIX: Added deep copy for immutability protection.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Self

from ws_gateway.components.core.constants import WSConstants

logger = logging.getLogger(__name__)

# HIGH-AUD-05 FIX: Fields that may contain sensitive data and should be excluded from raw_data
SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "password", "token", "secret", "api_key", "apikey",
    "credit_card", "card_number", "cvv", "ssn",
    "email", "phone", "address",
})


class EventType(str, Enum):
    """
    Valid event types for WebSocket messages.

    Synchronized with backend/shared/events.py.
    MED-WS-10 FIX: Added ROUND_CANCELED, PAYMENT_REJECTED.
    """

    # Round lifecycle events
    ROUND_PENDING = "ROUND_PENDING"
    ROUND_SUBMITTED = "ROUND_SUBMITTED"
    ROUND_IN_KITCHEN = "ROUND_IN_KITCHEN"
    ROUND_READY = "ROUND_READY"
    ROUND_SERVED = "ROUND_SERVED"
    ROUND_CANCELED = "ROUND_CANCELED"

    # Service call events
    SERVICE_CALL_CREATED = "SERVICE_CALL_CREATED"
    SERVICE_CALL_ACKED = "SERVICE_CALL_ACKED"
    SERVICE_CALL_CLOSED = "SERVICE_CALL_CLOSED"

    # Check/payment events
    CHECK_REQUESTED = "CHECK_REQUESTED"
    CHECK_PAID = "CHECK_PAID"
    PAYMENT_APPROVED = "PAYMENT_APPROVED"
    PAYMENT_REJECTED = "PAYMENT_REJECTED"
    PAYMENT_FAILED = "PAYMENT_FAILED"

    # Table events
    TABLE_CLEARED = "TABLE_CLEARED"
    TABLE_SESSION_STARTED = "TABLE_SESSION_STARTED"
    TABLE_STATUS_CHANGED = "TABLE_STATUS_CHANGED"

    # Kitchen ticket events
    TICKET_IN_PROGRESS = "TICKET_IN_PROGRESS"
    TICKET_READY = "TICKET_READY"
    TICKET_DELIVERED = "TICKET_DELIVERED"

    # Entity CRUD events (admin)
    ENTITY_CREATED = "ENTITY_CREATED"
    ENTITY_UPDATED = "ENTITY_UPDATED"
    ENTITY_DELETED = "ENTITY_DELETED"
    CASCADE_DELETE = "CASCADE_DELETE"


# Set for O(1) lookup
VALID_EVENT_TYPES: frozenset[str] = frozenset(e.value for e in EventType)

# Required and optional fields for validation
# LOW-AUD-04 FIX: Documented all fields with their purposes
REQUIRED_EVENT_FIELDS: frozenset[str] = frozenset({"type", "tenant_id"})

# Optional event fields - synchronized with backend/shared/infrastructure/events.py Event dataclass
# Field documentation:
#   branch_id   - Target branch for branch-specific events (int)
#   table_id    - Target table for table-specific events (int)
#   session_id  - Table session ID for diner notifications (int)
#   sector_id   - Sector ID for waiter sector-based targeting (int)
#   entity      - Event payload data (dict with IDs, changes, etc.)
#   actor       - Who triggered the event (dict with user_id, email, etc.)
#   timestamp   - Legacy alias for ts (ISO 8601 string) - deprecated
#   ts          - Event timestamp in ISO 8601 format (str)
#   v           - Schema version for forward compatibility (int, default: 1)
OPTIONAL_EVENT_FIELDS: frozenset[str] = frozenset({
    # Targeting fields
    "branch_id", "table_id", "session_id", "sector_id",
    # Payload fields
    "entity", "actor",
    # Metadata fields
    "timestamp", "ts", "v",
})


@dataclass(frozen=True, slots=True)
class WebSocketEvent:
    """
    Immutable Value Object representing a WebSocket event.

    All validation is performed at construction time.
    Invalid events raise ValueError.

    Attributes:
        event_type: The type of event (from EventType enum or unknown string).
        tenant_id: Tenant ID for multi-tenant isolation.
        branch_id: Optional branch ID for branch-specific events.
        table_id: Optional table ID for table-specific events.
        session_id: Optional session ID for session-specific events.
        sector_id: Optional sector ID for sector-targeted notifications.
        entity: Optional entity data for CRUD events.
        actor: Optional actor information (who triggered the event).
        timestamp: Optional event timestamp.
        raw_data: Original dict data for forward compatibility.
    """

    event_type: str
    tenant_id: int
    branch_id: int | None = None
    table_id: int | None = None
    session_id: int | None = None
    sector_id: int | None = None
    entity: dict[str, Any] | None = None
    actor: dict[str, Any] | None = None
    timestamp: str | None = None
    raw_data: dict[str, Any] = field(default_factory=dict, repr=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """
        Create a WebSocketEvent from a dictionary.

        Performs validation and raises ValueError if invalid.

        Args:
            data: Dictionary containing event data.

        Returns:
            Validated WebSocketEvent instance.

        Raises:
            ValueError: If data fails validation.
        """
        # Validate input type
        if not isinstance(data, dict):
            raise ValueError("Event must be a dictionary")

        # Check required fields
        missing = REQUIRED_EVENT_FIELDS - set(data.keys())
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Validate tenant_id type and value
        # MED-03 FIX: Also reject negative/zero tenant IDs
        tenant_id = data.get("tenant_id")
        if not isinstance(tenant_id, int):
            raise ValueError(f"tenant_id must be an integer, got {type(tenant_id).__name__}")
        if tenant_id <= 0:
            raise ValueError(f"tenant_id must be positive, got {tenant_id}")

        # Validate event type (warn but allow unknown for forward compatibility)
        event_type = data.get("type", "")
        if event_type not in VALID_EVENT_TYPES:
            logger.debug(
                "Unknown event type received",
                event_type=event_type,
            )

        # Validate optional integer fields
        # MED-03 FIX: Also reject negative/zero values for ID fields
        # CROSS-SYS-02 FIX: branch_id=0 is valid for tenant-wide entities (e.g., categories)
        # This matches backend validation in shared/infrastructure/events.py
        for field_name in ("branch_id", "table_id", "session_id", "sector_id"):
            value = data.get(field_name)
            if value is not None:
                if not isinstance(value, int):
                    raise ValueError(f"{field_name} must be an integer, got {type(value).__name__}")
                # CROSS-SYS-02 FIX: Allow 0 for branch_id only (tenant-wide entities)
                if field_name == "branch_id":
                    if value < 0:
                        raise ValueError(f"{field_name} must be non-negative, got {value}")
                elif value <= 0:
                    raise ValueError(f"{field_name} must be positive, got {value}")

        # Check for too many unknown fields (potential attack)
        known_fields = REQUIRED_EVENT_FIELDS | OPTIONAL_EVENT_FIELDS
        unknown_fields = set(data.keys()) - known_fields
        if len(unknown_fields) > WSConstants.MAX_UNKNOWN_FIELDS:
            raise ValueError(f"Too many unknown fields: {len(unknown_fields)}")

        # CRIT-DEEP-03 FIX: Deep copy to ensure immutability
        # MED-DEEP-02 FIX: Deep copy nested dicts (entity, actor)
        # HIGH-AUD-05 FIX: Sanitize raw_data to exclude sensitive fields
        sanitized_raw_data = _sanitize_event_data(copy.deepcopy(data))

        # ARCH-OPP-08 FIX: Use MappingProxyType for immutable raw_data view
        # The raw_data is stored as regular dict but exposed as immutable proxy
        return cls(
            event_type=event_type,
            tenant_id=tenant_id,
            branch_id=data.get("branch_id"),
            table_id=data.get("table_id"),
            session_id=data.get("session_id"),
            sector_id=data.get("sector_id"),
            entity=copy.deepcopy(data.get("entity")),
            actor=copy.deepcopy(data.get("actor")),
            timestamp=data.get("timestamp") or data.get("ts"),
            raw_data=sanitized_raw_data,  # HIGH-AUD-05 FIX: Sanitized copy
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert event back to dictionary for serialization.

        MED-WS-06 FIX: Returns a copy to preserve immutability.
        CRIT-DEEP-03 FIX: Deep copy to protect nested dicts.
        """
        return copy.deepcopy(self.raw_data)

    def get_raw_data(self) -> MappingProxyType:
        """
        Get an immutable view of the raw event data.

        ARCH-OPP-08 FIX: Returns MappingProxyType instead of deep copy
        for better performance while maintaining immutability.

        Note: For serialization or modification, use to_dict() which
        returns a mutable deep copy.

        Returns:
            Immutable MappingProxyType view of raw event data.
        """
        return MappingProxyType(self.raw_data)

    @property
    def is_known_type(self) -> bool:
        """Check if this event type is a known type."""
        return self.event_type in VALID_EVENT_TYPES

    @property
    def is_round_event(self) -> bool:
        """Check if this is a round lifecycle event."""
        return self.event_type in {
            EventType.ROUND_PENDING.value,
            EventType.ROUND_SUBMITTED.value,
            EventType.ROUND_IN_KITCHEN.value,
            EventType.ROUND_READY.value,
            EventType.ROUND_SERVED.value,
            EventType.ROUND_CANCELED.value,
        }

    @property
    def is_payment_event(self) -> bool:
        """Check if this is a payment-related event."""
        return self.event_type in {
            EventType.CHECK_REQUESTED.value,
            EventType.CHECK_PAID.value,
            EventType.PAYMENT_APPROVED.value,
            EventType.PAYMENT_REJECTED.value,
            EventType.PAYMENT_FAILED.value,
        }

    @property
    def is_admin_event(self) -> bool:
        """Check if this is an admin CRUD event."""
        return self.event_type in {
            EventType.ENTITY_CREATED.value,
            EventType.ENTITY_UPDATED.value,
            EventType.ENTITY_DELETED.value,
            EventType.CASCADE_DELETE.value,
        }


def _sanitize_event_data(data: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively sanitize event data by removing/masking sensitive fields.

    HIGH-AUD-05 FIX: Prevents exposure of PII and other sensitive data
    in logs, error messages, or serialized output.

    Args:
        data: Event data dictionary (already deep copied).

    Returns:
        Sanitized dictionary with sensitive fields masked.
    """
    for key in list(data.keys()):
        key_lower = key.lower()

        # Check if key matches any sensitive field pattern
        if any(sensitive in key_lower for sensitive in SENSITIVE_FIELDS):
            data[key] = "[REDACTED]"
        elif isinstance(data[key], dict):
            # Recursively sanitize nested dicts
            _sanitize_event_data(data[key])
        elif isinstance(data[key], list):
            # Sanitize list items that are dicts
            for i, item in enumerate(data[key]):
                if isinstance(item, dict):
                    _sanitize_event_data(item)

    return data


class UnknownEventTypeTracker:
    """
    Tracks unknown event types for monitoring.

    DEF-02 FIX: Includes maximum size limit to prevent unbounded memory growth.
    MED-07 FIX: Uses dict (insertion-ordered in Python 3.7+) for FIFO eviction.
    MED-AUD-06 FIX: Tracks evicted types to distinguish "first occurrence" from "reappearance".

    MED-WS-12 NOTE: This class REQUIRES Python 3.7+ for correct FIFO ordering.
    Dict insertion order is guaranteed by language spec since Python 3.7 (PEP 468).
    Earlier Python versions will have undefined eviction order.
    """

    def __init__(self, max_types: int = WSConstants.MAX_UNKNOWN_EVENT_TYPES):
        """
        Initialize the tracker.

        Args:
            max_types: Maximum number of unknown types to track.
        """
        self._max_types = max_types
        # MED-07 FIX: Use dict for insertion-order preservation (FIFO eviction)
        # Value is the count of times this event type was seen
        self._seen: dict[str, int] = {}
        self._count = 0
        # MED-AUD-06 FIX: Track evicted types to detect reappearances
        self._evicted_types: set[str] = set()
        self._max_evicted = max_types  # Keep same limit for evicted tracking

    @property
    def count(self) -> int:
        """Total number of unknown events received."""
        return self._count

    @property
    def types_seen(self) -> list[str]:
        """List of unique unknown event types seen (oldest first)."""
        return list(self._seen.keys())

    def record(self, event_type: str) -> bool:
        """
        Record an unknown event type.

        MED-07 FIX: Properly evicts oldest entry using dict ordering.
        MED-AUD-06 FIX: Distinguishes between "first occurrence" and "reappearance after eviction".

        Args:
            event_type: The unknown event type.

        Returns:
            True if this is the first time seeing this type (not just reappearance after eviction).
        """
        self._count += 1
        is_new = event_type not in self._seen
        was_previously_evicted = event_type in self._evicted_types

        if is_new:
            # MED-07 FIX: Evict oldest entry (first key in dict) if at capacity
            if len(self._seen) >= self._max_types:
                oldest_key = next(iter(self._seen))
                del self._seen[oldest_key]
                # MED-AUD-06 FIX: Track evicted type
                if len(self._evicted_types) >= self._max_evicted:
                    # Clear half of evicted set to prevent unbounded growth
                    evicted_list = list(self._evicted_types)
                    self._evicted_types = set(evicted_list[len(evicted_list)//2:])
                self._evicted_types.add(oldest_key)
                logger.warning(
                    "Unknown event types tracker at capacity, evicting oldest",
                    evicted=oldest_key,
                    max_types=self._max_types,
                    total_count=self._count,
                )
            self._seen[event_type] = 1

            # MED-AUD-06 FIX: Log appropriately based on whether this is truly new
            if was_previously_evicted:
                logger.info(
                    "Previously seen unknown event type reappeared",
                    event_type=event_type,
                    total_count=self._count,
                )
                self._evicted_types.discard(event_type)  # Remove from evicted set
        else:
            # Increment count for existing type
            self._seen[event_type] += 1

        # Return True only if truly new (never seen before, not reappearance)
        return is_new and not was_previously_evicted

    def get_metrics(self) -> dict[str, Any]:
        """Get tracker metrics."""
        return {
            "unknown_event_types_count": self._count,
            "unknown_event_types_seen": list(self._seen.keys()),
            "unique_types_count": len(self._seen),
            "max_tracked_types": self._max_types,
            "type_counts": dict(self._seen),  # MED-07: Include per-type counts
        }

    def reset(self) -> dict[str, Any]:
        """Reset tracker and return previous metrics."""
        metrics = self.get_metrics()
        self._seen.clear()
        self._count = 0
        return metrics
