"""
Centralized HTTP exceptions for consistent error handling.
HIGH-02 FIX: Standardized HTTP status codes and error messages.

Usage:
    from shared.exceptions import NotFoundError, ForbiddenError, ValidationError

    raise NotFoundError("Product", product_id)
    raise ForbiddenError("delete products")
    raise ValidationError("Invalid price format")
"""

from fastapi import HTTPException, status
from typing import Any

from shared.config.logging import get_logger

logger = get_logger(__name__)


class AppException(HTTPException):
    """
    Base exception with automatic logging.

    All custom exceptions should inherit from this class
    to ensure consistent logging and response format.
    """

    def __init__(
        self,
        status_code: int,
        detail: str,
        log_level: str = "warning",
        headers: dict[str, str] | None = None,
        **log_context: Any,
    ):
        # Log the error with context
        log_fn = getattr(logger, log_level, logger.warning)
        log_fn(detail, status_code=status_code, **log_context)

        super().__init__(status_code=status_code, detail=detail, headers=headers)


# =============================================================================
# 404 Not Found Errors
# =============================================================================


class NotFoundError(AppException):
    """
    Entity not found error (404).

    Usage:
        raise NotFoundError("Product", 123)
        raise NotFoundError("Branch", branch_id, tenant_id=tenant_id)
    """

    def __init__(self, entity: str, entity_id: int | str | None = None, **log_context: Any):
        if entity_id is not None:
            detail = f"{entity} con ID {entity_id} no encontrado"
        else:
            detail = f"{entity} no encontrado"

        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
            log_level="warning",
            entity=entity,
            entity_id=entity_id,
            **log_context,
        )


class SessionNotFoundError(NotFoundError):
    """Table session not found."""

    def __init__(self, session_id: int | None = None, **log_context: Any):
        super().__init__("Sesión de mesa", session_id, **log_context)


class CheckNotFoundError(NotFoundError):
    """Check/bill not found."""

    def __init__(self, check_id: int | None = None, **log_context: Any):
        super().__init__("Cuenta", check_id, **log_context)


class RoundNotFoundError(NotFoundError):
    """Round/order not found."""

    def __init__(self, round_id: int | None = None, **log_context: Any):
        super().__init__("Pedido", round_id, **log_context)


# =============================================================================
# 403 Forbidden Errors
# =============================================================================


class ForbiddenError(AppException):
    """
    Authorization/permission error (403).

    Usage:
        raise ForbiddenError("delete products")
        raise ForbiddenError("access this branch", user_id=user_id)
    """

    def __init__(self, action: str | None = None, **log_context: Any):
        if action:
            detail = f"No autorizado para {action}"
        else:
            detail = "Acceso denegado"

        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail,
            log_level="warning",
            action=action,
            **log_context,
        )


class BranchAccessError(ForbiddenError):
    """User doesn't have access to the branch."""

    def __init__(self, branch_id: int | None = None, **log_context: Any):
        super().__init__("acceder a esta sucursal", branch_id=branch_id, **log_context)


class InsufficientRoleError(ForbiddenError):
    """User doesn't have the required role."""

    def __init__(self, required_roles: list[str], **log_context: Any):
        roles_str = ", ".join(required_roles)
        super().__init__(
            f"realizar esta acción (requiere rol: {roles_str})",
            required_roles=required_roles,
            **log_context,
        )


# =============================================================================
# 400 Bad Request Errors
# =============================================================================


class ValidationError(AppException):
    """
    Input validation error (400).

    Usage:
        raise ValidationError("El precio debe ser positivo")
        raise ValidationError("Cantidad inválida", field="quantity", value=-1)
    """

    def __init__(self, detail: str, **log_context: Any):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail,
            log_level="warning",
            **log_context,
        )


class InvalidStateError(ValidationError):
    """Entity is in an invalid state for the operation."""

    def __init__(self, entity: str, current_state: str, expected_states: list[str] | None = None, **log_context: Any):
        if expected_states:
            states_str = ", ".join(expected_states)
            detail = f"{entity} está en estado '{current_state}', se esperaba: {states_str}"
        else:
            detail = f"{entity} no puede estar en estado '{current_state}' para esta operación"

        super().__init__(detail, entity=entity, current_state=current_state, **log_context)


class InvalidTransitionError(ValidationError):
    """Invalid status transition."""

    def __init__(self, entity: str, from_status: str, to_status: str, **log_context: Any):
        detail = f"Transición inválida de '{from_status}' a '{to_status}' para {entity}"
        super().__init__(detail, entity=entity, from_status=from_status, to_status=to_status, **log_context)


class DuplicateEntityError(ValidationError):
    """Entity already exists."""

    def __init__(self, entity: str, identifier: str | None = None, **log_context: Any):
        if identifier:
            detail = f"{entity} con identificador '{identifier}' ya existe"
        else:
            detail = f"{entity} ya existe"

        super().__init__(detail, entity=entity, identifier=identifier, **log_context)


class PaymentAmountError(ValidationError):
    """Payment amount validation error."""

    def __init__(self, amount: int, reason: str, **log_context: Any):
        detail = f"Monto de pago inválido ({amount}): {reason}"
        super().__init__(detail, amount=amount, **log_context)


# =============================================================================
# 409 Conflict Errors
# =============================================================================


class ConflictError(AppException):
    """
    Resource conflict error (409).

    Usage:
        raise ConflictError("La mesa ya tiene una sesión activa")
    """

    def __init__(self, detail: str, **log_context: Any):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
            log_level="warning",
            **log_context,
        )


class AlreadyPaidError(ConflictError):
    """Check/payment is already paid."""

    def __init__(self, check_id: int, **log_context: Any):
        super().__init__(f"La cuenta {check_id} ya está pagada", check_id=check_id, **log_context)


# =============================================================================
# 500 Internal Server Errors
# =============================================================================


class InternalError(AppException):
    """
    Internal server error (500).

    Usage:
        raise InternalError("Failed to process payment", payment_id=123)
    """

    def __init__(self, detail: str = "Error interno del servidor", **log_context: Any):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
            log_level="error",
            **log_context,
        )


class DatabaseError(InternalError):
    """Database operation failed."""

    def __init__(self, operation: str, **log_context: Any):
        detail = f"Error de base de datos durante {operation}. Por favor intente de nuevo."
        super().__init__(detail, operation=operation, **log_context)


class ExternalServiceError(AppException):
    """External service error (502 or 503)."""

    def __init__(
        self,
        service: str,
        is_unavailable: bool = False,
        retry_after: int | None = None,
        **log_context: Any,
    ):
        if is_unavailable:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            detail = f"Servicio {service} temporalmente no disponible"
        else:
            status_code = status.HTTP_502_BAD_GATEWAY
            detail = f"Error al comunicarse con {service}"

        headers = None
        if retry_after:
            headers = {"Retry-After": str(retry_after)}

        super().__init__(
            status_code=status_code,
            detail=detail,
            log_level="error",
            headers=headers,
            service=service,
            **log_context,
        )


# =============================================================================
# Rate Limiting Errors
# =============================================================================


class RateLimitError(AppException):
    """Rate limit exceeded (429)."""

    def __init__(self, retry_after: int, context: str | None = None, **log_context: Any):
        detail = f"Demasiadas solicitudes. Intente de nuevo en {retry_after} segundos."
        if context:
            detail = f"{context}: {detail}"

        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=detail,
            log_level="warning",
            headers={"Retry-After": str(retry_after)},
            retry_after=retry_after,
            **log_context,
        )
