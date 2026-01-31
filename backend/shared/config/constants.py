"""
Centralized constants for the backend application.
MED-02 FIX: Avoid magic strings and repeated constants.

Usage:
    from shared.constants import Roles, MANAGEMENT_ROLES, RoundStatus

    if role in MANAGEMENT_ROLES:
        ...

    if status == RoundStatus.PENDING:
        ...
"""

from enum import Enum
from typing import Final


# =============================================================================
# User Roles
# =============================================================================


class Roles:
    """User role constants."""

    ADMIN: Final[str] = "ADMIN"
    MANAGER: Final[str] = "MANAGER"
    KITCHEN: Final[str] = "KITCHEN"
    WAITER: Final[str] = "WAITER"

    ALL: Final[list[str]] = [ADMIN, MANAGER, KITCHEN, WAITER]


# Role groups for common access patterns
MANAGEMENT_ROLES: Final[frozenset[str]] = frozenset({Roles.ADMIN, Roles.MANAGER})
STAFF_ROLES: Final[frozenset[str]] = frozenset({Roles.ADMIN, Roles.MANAGER, Roles.WAITER})
KITCHEN_ACCESS_ROLES: Final[frozenset[str]] = frozenset({Roles.ADMIN, Roles.MANAGER, Roles.KITCHEN})
ALL_STAFF_ROLES: Final[frozenset[str]] = frozenset({Roles.ADMIN, Roles.MANAGER, Roles.KITCHEN, Roles.WAITER})


# =============================================================================
# Entity Status Constants
# =============================================================================


class RoundStatus:
    """Round/order status constants."""

    PENDING: Final[str] = "PENDING"
    CONFIRMED: Final[str] = "CONFIRMED"  # Waiter verified the order at table
    SUBMITTED: Final[str] = "SUBMITTED"  # Admin/Manager sent to kitchen
    IN_KITCHEN: Final[str] = "IN_KITCHEN"
    READY: Final[str] = "READY"
    SERVED: Final[str] = "SERVED"
    CANCELED: Final[str] = "CANCELED"

    # Status groups
    ACTIVE: Final[list[str]] = [PENDING, CONFIRMED, SUBMITTED, IN_KITCHEN, READY]
    KITCHEN_VISIBLE: Final[list[str]] = [SUBMITTED, IN_KITCHEN]  # Kitchen only sees after admin sends
    COMPLETED: Final[list[str]] = [SERVED, CANCELED]


class TableStatus:
    """Table status constants - matches schemas.py Literal types."""

    FREE: Final[str] = "FREE"
    ACTIVE: Final[str] = "ACTIVE"  # Was OCCUPIED
    PAYING: Final[str] = "PAYING"
    OUT_OF_SERVICE: Final[str] = "OUT_OF_SERVICE"  # Was RESERVED

    IN_USE: Final[list[str]] = [ACTIVE, PAYING]  # Tables with active sessions


class SessionStatus:
    """Table session status constants."""

    OPEN: Final[str] = "OPEN"
    PAYING: Final[str] = "PAYING"
    CLOSED: Final[str] = "CLOSED"

    ACTIVE: Final[list[str]] = [OPEN, PAYING]


class CheckStatus:
    """Check/bill status constants."""

    OPEN: Final[str] = "OPEN"
    REQUESTED: Final[str] = "REQUESTED"
    IN_PAYMENT: Final[str] = "IN_PAYMENT"
    PAID: Final[str] = "PAID"

    UNPAID: Final[list[str]] = [OPEN, REQUESTED, IN_PAYMENT]


class PaymentStatus:
    """Payment status constants."""

    PENDING: Final[str] = "PENDING"
    APPROVED: Final[str] = "APPROVED"
    REJECTED: Final[str] = "REJECTED"
    REFUNDED: Final[str] = "REFUNDED"


class PaymentProvider:
    """Payment provider constants."""

    CASH: Final[str] = "CASH"
    MERCADO_PAGO: Final[str] = "MERCADO_PAGO"


class TicketStatus:
    """HIGH-07 FIX: Kitchen ticket status constants."""

    PENDING: Final[str] = "PENDING"
    IN_PROGRESS: Final[str] = "IN_PROGRESS"
    READY: Final[str] = "READY"
    DELIVERED: Final[str] = "DELIVERED"

    ALL: Final[list[str]] = [PENDING, IN_PROGRESS, READY, DELIVERED]
    ACTIVE: Final[list[str]] = [PENDING, IN_PROGRESS, READY]


class TicketItemStatus:
    """HIGH-07 FIX: Kitchen ticket item status constants."""

    PENDING: Final[str] = "PENDING"
    IN_PROGRESS: Final[str] = "IN_PROGRESS"
    READY: Final[str] = "READY"

    ALL: Final[list[str]] = [PENDING, IN_PROGRESS, READY]


class ServiceCallStatus:
    """HIGH-07 FIX: Service call status constants."""

    ACTIVE: Final[str] = "ACTIVE"
    ACKNOWLEDGED: Final[str] = "ACKNOWLEDGED"
    CLOSED: Final[str] = "CLOSED"

    ALL: Final[list[str]] = [ACTIVE, ACKNOWLEDGED, CLOSED]


# =============================================================================
# Status Transitions
# =============================================================================

# Valid round status transitions (from -> [allowed to states])
# New flow: PENDING → CONFIRMED → SUBMITTED → IN_KITCHEN → READY → SERVED
ROUND_TRANSITIONS: Final[dict[str, list[str]]] = {
    RoundStatus.PENDING: [RoundStatus.CONFIRMED, RoundStatus.CANCELED],  # Waiter confirms
    RoundStatus.CONFIRMED: [RoundStatus.SUBMITTED, RoundStatus.CANCELED],  # Admin/Manager sends to kitchen
    RoundStatus.SUBMITTED: [RoundStatus.IN_KITCHEN, RoundStatus.CANCELED],
    RoundStatus.IN_KITCHEN: [RoundStatus.READY, RoundStatus.CANCELED],
    RoundStatus.READY: [RoundStatus.SERVED],
    RoundStatus.SERVED: [],  # Terminal state
    RoundStatus.CANCELED: [],  # Terminal state
}

# Role-based transition restrictions
# Format: (from_status, to_status) -> [allowed_roles]
# New flow: Waiter confirms (PENDING→CONFIRMED), Admin sends to kitchen (CONFIRMED→SUBMITTED)
ROUND_TRANSITION_ROLES: Final[dict[tuple[str, str], frozenset[str]]] = {
    # Waiter, Admin, or Manager can confirm order (verified at table)
    (RoundStatus.PENDING, RoundStatus.CONFIRMED): frozenset({Roles.WAITER, Roles.ADMIN, Roles.MANAGER}),
    # Only ADMIN/MANAGER can send to kitchen
    (RoundStatus.CONFIRMED, RoundStatus.SUBMITTED): MANAGEMENT_ROLES,
    (RoundStatus.SUBMITTED, RoundStatus.IN_KITCHEN): MANAGEMENT_ROLES,
    # Only KITCHEN can mark as ready
    (RoundStatus.IN_KITCHEN, RoundStatus.READY): frozenset({Roles.KITCHEN}),
    # ADMIN/MANAGER/WAITER can mark as served
    (RoundStatus.READY, RoundStatus.SERVED): STAFF_ROLES,
    # Only ADMIN/MANAGER can cancel
    (RoundStatus.PENDING, RoundStatus.CANCELED): MANAGEMENT_ROLES,
    (RoundStatus.CONFIRMED, RoundStatus.CANCELED): MANAGEMENT_ROLES,
    (RoundStatus.SUBMITTED, RoundStatus.CANCELED): MANAGEMENT_ROLES,
    (RoundStatus.IN_KITCHEN, RoundStatus.CANCELED): MANAGEMENT_ROLES,
}


# =============================================================================
# Validation Constants
# =============================================================================


class Limits:
    """Validation limits."""

    # Quantity limits
    MIN_QUANTITY: Final[int] = 1
    MAX_QUANTITY: Final[int] = 99

    # Price limits (in cents)
    MIN_PRICE_CENTS: Final[int] = 0
    MAX_PRICE_CENTS: Final[int] = 100_000_00  # $100,000

    # String lengths
    MAX_NAME_LENGTH: Final[int] = 200
    MAX_DESCRIPTION_LENGTH: Final[int] = 2000
    MAX_SHORT_DESCRIPTION_LENGTH: Final[int] = 200
    MAX_URL_LENGTH: Final[int] = 2048
    MAX_SEARCH_TERM_LENGTH: Final[int] = 100

    # Pagination defaults
    DEFAULT_PAGE_SIZE: Final[int] = 50
    MAX_PAGE_SIZE: Final[int] = 200
    DEFAULT_OFFSET: Final[int] = 0

    # Diner limits
    DEFAULT_DINER_COUNT: Final[int] = 1
    MAX_DINER_COUNT: Final[int] = 20


# =============================================================================
# Event Types (for WebSocket/Redis)
# =============================================================================


class EventType:
    """WebSocket/Redis event type constants."""

    # Round events
    ROUND_SUBMITTED: Final[str] = "ROUND_SUBMITTED"
    ROUND_IN_KITCHEN: Final[str] = "ROUND_IN_KITCHEN"
    ROUND_READY: Final[str] = "ROUND_READY"
    ROUND_SERVED: Final[str] = "ROUND_SERVED"
    ROUND_CANCELED: Final[str] = "ROUND_CANCELED"

    # Service call events
    SERVICE_CALL_CREATED: Final[str] = "SERVICE_CALL_CREATED"
    SERVICE_CALL_ACKED: Final[str] = "SERVICE_CALL_ACKED"
    SERVICE_CALL_CLOSED: Final[str] = "SERVICE_CALL_CLOSED"

    # Check/payment events
    CHECK_REQUESTED: Final[str] = "CHECK_REQUESTED"
    CHECK_PAID: Final[str] = "CHECK_PAID"
    PAYMENT_APPROVED: Final[str] = "PAYMENT_APPROVED"
    PAYMENT_REJECTED: Final[str] = "PAYMENT_REJECTED"

    # Table events
    TABLE_SESSION_STARTED: Final[str] = "TABLE_SESSION_STARTED"
    TABLE_STATUS_CHANGED: Final[str] = "TABLE_STATUS_CHANGED"
    TABLE_CLEARED: Final[str] = "TABLE_CLEARED"

    # Admin events
    ENTITY_CREATED: Final[str] = "ENTITY_CREATED"
    ENTITY_UPDATED: Final[str] = "ENTITY_UPDATED"
    ENTITY_DELETED: Final[str] = "ENTITY_DELETED"
    CASCADE_DELETE: Final[str] = "CASCADE_DELETE"


# =============================================================================
# Allergen Presence Types
# =============================================================================


class AllergenPresence:
    """Allergen presence type constants."""

    CONTAINS: Final[str] = "contains"
    MAY_CONTAIN: Final[str] = "may_contain"  # Traces
    FREE_FROM: Final[str] = "free_from"

    ALL: Final[list[str]] = [CONTAINS, MAY_CONTAIN, FREE_FROM]


# =============================================================================
# Dietary Tags
# =============================================================================


class DietaryTags:
    """Dietary restriction tag constants."""

    VEGETARIAN: Final[str] = "vegetarian"
    VEGAN: Final[str] = "vegan"
    GLUTEN_FREE: Final[str] = "gluten_free"
    DAIRY_FREE: Final[str] = "dairy_free"
    CELIAC_SAFE: Final[str] = "celiac_safe"
    KETO: Final[str] = "keto"
    LOW_SODIUM: Final[str] = "low_sodium"

    ALL: Final[list[str]] = [
        VEGETARIAN, VEGAN, GLUTEN_FREE, DAIRY_FREE, CELIAC_SAFE, KETO, LOW_SODIUM
    ]


# =============================================================================
# Cooking Methods
# =============================================================================


class CookingMethods:
    """Cooking method constants."""

    BAKED: Final[str] = "horneado"
    FRIED: Final[str] = "frito"
    GRILLED: Final[str] = "grillado"
    RAW: Final[str] = "crudo"
    BOILED: Final[str] = "hervido"
    STEAMED: Final[str] = "vapor"
    SAUTEED: Final[str] = "salteado"
    BRAISED: Final[str] = "braseado"

    ALL: Final[list[str]] = [
        BAKED, FRIED, GRILLED, RAW, BOILED, STEAMED, SAUTEED, BRAISED
    ]


# =============================================================================
# Shifts
# =============================================================================


class ShiftType(str, Enum):
    """Shift type enum for waiter assignments."""

    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    ALL_DAY = "all_day"


# =============================================================================
# Risk Levels (RAG)
# =============================================================================


class RiskLevel:
    """RAG risk level constants."""

    LOW: Final[str] = "low"
    MEDIUM: Final[str] = "medium"
    HIGH: Final[str] = "high"

    ALL: Final[list[str]] = [LOW, MEDIUM, HIGH]


class WarningSeverity:
    """Product warning severity constants."""

    INFO: Final[str] = "info"
    WARNING: Final[str] = "warning"
    DANGER: Final[str] = "danger"

    ALL: Final[list[str]] = [INFO, WARNING, DANGER]


class ModificationAction:
    """Product modification action constants."""

    REMOVE: Final[str] = "remove"
    SUBSTITUTE: Final[str] = "substitute"

    ALL: Final[list[str]] = [REMOVE, SUBSTITUTE]


# =============================================================================
# Error Messages (Spanish)
# =============================================================================


class ErrorMessages:
    """Standardized error messages in Spanish."""

    # Auth errors
    NOT_AUTHENTICATED: Final[str] = "No autenticado"
    INVALID_TOKEN: Final[str] = "Token inválido"
    TOKEN_EXPIRED: Final[str] = "Token expirado"
    TOKEN_REVOKED: Final[str] = "Token revocado"
    INSUFFICIENT_PERMISSIONS: Final[str] = "Permisos insuficientes"

    # Not found errors
    ENTITY_NOT_FOUND: Final[str] = "{entity} no encontrado"
    BRANCH_NOT_FOUND: Final[str] = "Sucursal no encontrada"
    TABLE_NOT_FOUND: Final[str] = "Mesa no encontrada"
    SESSION_NOT_FOUND: Final[str] = "Sesión no encontrada"
    PRODUCT_NOT_FOUND: Final[str] = "Producto no encontrado"
    CATEGORY_NOT_FOUND: Final[str] = "Categoría no encontrada"
    CHECK_NOT_FOUND: Final[str] = "Cuenta no encontrada"
    ROUND_NOT_FOUND: Final[str] = "Pedido no encontrado"

    # Access errors
    NO_BRANCH_ACCESS: Final[str] = "No tienes acceso a esta sucursal"
    NO_TENANT_ACCESS: Final[str] = "No tienes acceso a este tenant"
    ADMIN_REQUIRED: Final[str] = "Se requiere rol de administrador"
    MANAGER_REQUIRED: Final[str] = "Se requiere rol de administrador o gerente"

    # Validation errors
    INVALID_QUANTITY: Final[str] = "Cantidad inválida"
    INVALID_PRICE: Final[str] = "Precio inválido"
    INVALID_STATUS: Final[str] = "Estado inválido"
    INVALID_TRANSITION: Final[str] = "Transición de estado inválida"

    # State errors
    SESSION_NOT_ACTIVE: Final[str] = "La sesión no está activa"
    CHECK_ALREADY_PAID: Final[str] = "La cuenta ya está pagada"
    TABLE_NOT_FREE: Final[str] = "La mesa no está libre"

    # Rate limit
    RATE_LIMIT_EXCEEDED: Final[str] = "Demasiadas solicitudes. Intente más tarde."


# =============================================================================
# HIGH-07 FIX: Status Validation Functions
# =============================================================================


def validate_round_status(status: str) -> bool:
    """Validate that a round status is valid."""
    return status in [
        RoundStatus.PENDING, RoundStatus.CONFIRMED, RoundStatus.SUBMITTED,
        RoundStatus.IN_KITCHEN, RoundStatus.READY, RoundStatus.SERVED, RoundStatus.CANCELED
    ]


def validate_ticket_status(status: str) -> bool:
    """Validate that a ticket status is valid."""
    return status in TicketStatus.ALL


def validate_ticket_item_status(status: str) -> bool:
    """Validate that a ticket item status is valid."""
    return status in TicketItemStatus.ALL


def validate_payment_status(status: str) -> bool:
    """Validate that a payment status is valid."""
    return status in [
        PaymentStatus.PENDING, PaymentStatus.APPROVED,
        PaymentStatus.REJECTED, PaymentStatus.REFUNDED
    ]


def validate_session_status(status: str) -> bool:
    """Validate that a session status is valid."""
    return status in [SessionStatus.OPEN, SessionStatus.PAYING, SessionStatus.CLOSED]


def validate_table_status(status: str) -> bool:
    """Validate that a table status is valid."""
    return status in [
        TableStatus.FREE, TableStatus.ACTIVE,
        TableStatus.PAYING, TableStatus.OUT_OF_SERVICE
    ]


def validate_check_status(status: str) -> bool:
    """Validate that a check status is valid."""
    return status in [
        CheckStatus.OPEN, CheckStatus.REQUESTED,
        CheckStatus.IN_PAYMENT, CheckStatus.PAID
    ]


def validate_service_call_status(status: str) -> bool:
    """Validate that a service call status is valid."""
    return status in ServiceCallStatus.ALL


def validate_round_transition(current_status: str, new_status: str) -> bool:
    """
    Validate that a round status transition is allowed.

    Returns True if transition is valid, False otherwise.
    """
    allowed = ROUND_TRANSITIONS.get(current_status, [])
    return new_status in allowed


def get_allowed_round_transitions(current_status: str, roles: list[str]) -> list[str]:
    """
    Get allowed round transitions for a given status and user roles.

    Returns list of status values the user can transition to.
    """
    allowed_by_status = ROUND_TRANSITIONS.get(current_status, [])
    result = []

    for new_status in allowed_by_status:
        key = (current_status, new_status)
        allowed_roles = ROUND_TRANSITION_ROLES.get(key, ALL_STAFF_ROLES)
        if any(role in allowed_roles for role in roles):
            result.append(new_status)

    return result
