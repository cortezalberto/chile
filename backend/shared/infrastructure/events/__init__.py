"""
Event System for Real-time Notifications via Redis pub/sub.

This package provides:
- Event schema and validation
- Redis connection pool management
- Event publishing with retry and circuit breaker
- Channel naming conventions
- Domain-specific event publishers

ARCHITECTURE: Split from monolithic events.py (1087 lines) into focused modules:
- circuit_breaker.py: Circuit breaker pattern for resilience
- event_types.py: Event type constants
- event_schema.py: Event dataclass with validation
- channels.py: Channel naming functions
- redis_pool.py: Connection pool management
- health_checks.py: Redis health check functions
- publisher.py: Core publish_event with retry
- routing.py: Convenience publish_to_* functions
- domain_publishers.py: High-level domain event publishers
"""

# =============================================================================
# Circuit Breaker
# =============================================================================

from .circuit_breaker import (
    CircuitState,
    EventCircuitBreaker,
    get_event_circuit_breaker,
    calculate_retry_delay_with_jitter,
)

# =============================================================================
# Event Types
# =============================================================================

from .event_types import (
    # Round lifecycle
    ROUND_PENDING,
    ROUND_CONFIRMED,
    ROUND_SUBMITTED,
    ROUND_IN_KITCHEN,
    ROUND_READY,
    ROUND_SERVED,
    ROUND_CANCELED,
    # Service calls
    SERVICE_CALL_CREATED,
    SERVICE_CALL_ACKED,
    SERVICE_CALL_CLOSED,
    # Billing
    CHECK_REQUESTED,
    PAYMENT_APPROVED,
    PAYMENT_REJECTED,
    PAYMENT_FAILED,
    CHECK_PAID,
    # Tables
    TABLE_SESSION_STARTED,
    TABLE_CLEARED,
    TABLE_STATUS_CHANGED,
    # Kitchen tickets
    TICKET_IN_PROGRESS,
    TICKET_READY,
    TICKET_DELIVERED,
    # Admin CRUD
    ENTITY_CREATED,
    ENTITY_UPDATED,
    ENTITY_DELETED,
    CASCADE_DELETE,
    # Shared cart
    CART_ITEM_ADDED,
    CART_ITEM_UPDATED,
    CART_ITEM_REMOVED,
    CART_CLEARED,
    CART_SYNC,
    # Size limits
    MAX_EVENT_SIZE,
)

# =============================================================================
# Event Schema
# =============================================================================

from .event_schema import Event

# =============================================================================
# Channels
# =============================================================================

from .channels import (
    channel_branch_waiters,
    channel_branch_kitchen,
    channel_user,
    channel_table_session,
    channel_sector_waiters,
    channel_branch_admin,
    channel_tenant_admin,
)

# =============================================================================
# Redis Pool
# =============================================================================

from .redis_pool import (
    get_redis_pool,
    get_redis_client,  # Deprecated alias for get_redis_pool
    get_redis_sync_client,
    close_redis_pool,
    close_redis_sync_client,
)

# =============================================================================
# Health Checks
# =============================================================================

from .health_checks import (
    check_redis_async_health,
    check_redis_sync_health,
    check_redis_async_health_legacy,
    check_redis_sync_health_legacy,
)

# =============================================================================
# Core Publishing
# =============================================================================

from .publisher import publish_event

# =============================================================================
# Routing Helpers
# =============================================================================

from .routing import (
    publish_to_waiters,
    publish_to_kitchen,
    publish_to_sector,
    publish_to_session,
    publish_to_admin,
    publish_to_tenant_admin,
)

# =============================================================================
# Domain Publishers
# =============================================================================

from .domain_publishers import (
    publish_round_event,
    publish_service_call_event,
    publish_check_event,
    publish_table_event,
    publish_admin_crud_event,
    publish_cart_event,
)

# =============================================================================
# __all__ for explicit exports
# =============================================================================

__all__ = [
    # Circuit Breaker
    "CircuitState",
    "EventCircuitBreaker",
    "get_event_circuit_breaker",
    "calculate_retry_delay_with_jitter",
    # Event Types
    "ROUND_PENDING",
    "ROUND_CONFIRMED",
    "ROUND_SUBMITTED",
    "ROUND_IN_KITCHEN",
    "ROUND_READY",
    "ROUND_SERVED",
    "ROUND_CANCELED",
    "SERVICE_CALL_CREATED",
    "SERVICE_CALL_ACKED",
    "SERVICE_CALL_CLOSED",
    "CHECK_REQUESTED",
    "PAYMENT_APPROVED",
    "PAYMENT_REJECTED",
    "PAYMENT_FAILED",
    "CHECK_PAID",
    "TABLE_SESSION_STARTED",
    "TABLE_CLEARED",
    "TABLE_STATUS_CHANGED",
    "TICKET_IN_PROGRESS",
    "TICKET_READY",
    "TICKET_DELIVERED",
    "ENTITY_CREATED",
    "ENTITY_UPDATED",
    "ENTITY_DELETED",
    "CASCADE_DELETE",
    "CART_ITEM_ADDED",
    "CART_ITEM_UPDATED",
    "CART_ITEM_REMOVED",
    "CART_CLEARED",
    "CART_SYNC",
    "MAX_EVENT_SIZE",
    # Event Schema
    "Event",
    # Channels
    "channel_branch_waiters",
    "channel_branch_kitchen",
    "channel_user",
    "channel_table_session",
    "channel_sector_waiters",
    "channel_branch_admin",
    "channel_tenant_admin",
    # Redis Pool
    "get_redis_pool",
    "get_redis_client",
    "get_redis_sync_client",
    "close_redis_pool",
    "close_redis_sync_client",
    # Health Checks
    "check_redis_async_health",
    "check_redis_sync_health",
    "check_redis_async_health_legacy",
    "check_redis_sync_health_legacy",
    # Core Publishing
    "publish_event",
    # Routing Helpers
    "publish_to_waiters",
    "publish_to_kitchen",
    "publish_to_sector",
    "publish_to_session",
    "publish_to_admin",
    "publish_to_tenant_admin",
    # Domain Publishers
    "publish_round_event",
    "publish_service_call_event",
    "publish_check_event",
    "publish_table_event",
    "publish_admin_crud_event",
    "publish_cart_event",
]
