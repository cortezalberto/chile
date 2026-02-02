"""
Event Type Constants.

Defines all event types used in the system for Redis pub/sub.
"""

from shared.config.settings import settings

# =============================================================================
# Round lifecycle events
# Flow: PENDING → CONFIRMED → SUBMITTED → IN_KITCHEN → READY → SERVED
# =============================================================================

ROUND_PENDING = "ROUND_PENDING"      # Client created order (waiter must verify at table)
ROUND_CONFIRMED = "ROUND_CONFIRMED"  # Waiter verified order at table (admin can now send to kitchen)
ROUND_SUBMITTED = "ROUND_SUBMITTED"  # Admin/Manager sent to kitchen (visible in Kitchen "Nuevo")
ROUND_IN_KITCHEN = "ROUND_IN_KITCHEN"
ROUND_READY = "ROUND_READY"
ROUND_SERVED = "ROUND_SERVED"
ROUND_CANCELED = "ROUND_CANCELED"
ROUND_ITEM_DELETED = "ROUND_ITEM_DELETED"  # Waiter deleted item from pending/confirmed round

# =============================================================================
# Service call events
# =============================================================================

SERVICE_CALL_CREATED = "SERVICE_CALL_CREATED"
SERVICE_CALL_ACKED = "SERVICE_CALL_ACKED"
SERVICE_CALL_CLOSED = "SERVICE_CALL_CLOSED"

# =============================================================================
# Billing events
# =============================================================================

CHECK_REQUESTED = "CHECK_REQUESTED"
PAYMENT_APPROVED = "PAYMENT_APPROVED"
PAYMENT_REJECTED = "PAYMENT_REJECTED"
PAYMENT_FAILED = "PAYMENT_FAILED"  # CROSS-SYS-01 FIX: Added for consistency with ws_gateway
CHECK_PAID = "CHECK_PAID"

# =============================================================================
# Table events
# =============================================================================

TABLE_SESSION_STARTED = "TABLE_SESSION_STARTED"
TABLE_CLEARED = "TABLE_CLEARED"
# CROSS-SYS-01 FIX: Added TABLE_STATUS_CHANGED for consistency with ws_gateway
TABLE_STATUS_CHANGED = "TABLE_STATUS_CHANGED"

# =============================================================================
# Kitchen ticket events
# =============================================================================

# CROSS-SYS-01 FIX: Added kitchen ticket events for consistency with ws_gateway
TICKET_IN_PROGRESS = "TICKET_IN_PROGRESS"
TICKET_READY = "TICKET_READY"
TICKET_DELIVERED = "TICKET_DELIVERED"

# =============================================================================
# Shared cart events (real-time sync between diners)
# =============================================================================

CART_ITEM_ADDED = "CART_ITEM_ADDED"      # Diner added item to shared cart
CART_ITEM_UPDATED = "CART_ITEM_UPDATED"  # Diner updated quantity/notes
CART_ITEM_REMOVED = "CART_ITEM_REMOVED"  # Diner removed item from cart
CART_CLEARED = "CART_CLEARED"            # Cart cleared (after round submit)
CART_SYNC = "CART_SYNC"                  # Full cart state for reconnection

# =============================================================================
# Admin CRUD events
# =============================================================================

# DEF-HIGH-01 FIX: Admin CRUD events for real-time sync between Dashboard users
ENTITY_CREATED = "ENTITY_CREATED"
ENTITY_UPDATED = "ENTITY_UPDATED"
ENTITY_DELETED = "ENTITY_DELETED"
CASCADE_DELETE = "CASCADE_DELETE"

# =============================================================================
# Size limits
# =============================================================================

# REDIS-HIGH-07: Maximum message size for events (same as WebSocket limit)
MAX_EVENT_SIZE = settings.ws_max_message_size
