"""
Authentication Strategies for WebSocket Gateway.

Implements Strategy pattern for pluggable authentication.
Supports JWT tokens, table tokens, and extensible custom strategies.

ARCH-OPP-05 FIX: Extracted authentication logic into pluggable strategies.
PATTERN: Strategy - Different authentication algorithms.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from fastapi import HTTPException

from ws_gateway.components.core.constants import WSCloseCode

if TYPE_CHECKING:
    from fastapi import WebSocket


logger = logging.getLogger(__name__)


# =============================================================================
# Result Types
# =============================================================================


@dataclass(frozen=True, slots=True)
class AuthResult:
    """
    Result of authentication attempt.

    Attributes:
        success: Whether authentication succeeded.
        data: Authentication data (JWT claims, token data, etc.) if successful.
        error_message: Human-readable error message if failed.
        close_code: WebSocket close code to use if failed.
        audit_reason: Short reason code for audit logging.
    """

    success: bool
    data: dict[str, Any] | None = None
    error_message: str | None = None
    close_code: int = WSCloseCode.AUTH_FAILED
    audit_reason: str | None = None

    @classmethod
    def ok(cls, data: dict[str, Any]) -> "AuthResult":
        """Create successful authentication result."""
        return cls(success=True, data=data)

    @classmethod
    def fail(
        cls,
        message: str,
        close_code: int = WSCloseCode.AUTH_FAILED,
        audit_reason: str = "auth_failed",
    ) -> "AuthResult":
        """Create failed authentication result."""
        return cls(
            success=False,
            error_message=message,
            close_code=close_code,
            audit_reason=audit_reason,
        )

    @classmethod
    def forbidden(cls, message: str, audit_reason: str = "forbidden") -> "AuthResult":
        """Create forbidden (access denied) result."""
        return cls(
            success=False,
            error_message=message,
            close_code=WSCloseCode.FORBIDDEN,
            audit_reason=audit_reason,
        )


# =============================================================================
# Strategy Interface
# =============================================================================


class AuthStrategy(ABC):
    """
    Abstract base class for authentication strategies.

    PATTERN: Strategy - Encapsulates authentication algorithm.

    Implementations:
    - JWTAuthStrategy: JWT token validation with role checking
    - TableTokenAuthStrategy: Table token validation for diners
    - CompositeAuthStrategy: Combines multiple strategies

    Usage:
        strategy = JWTAuthStrategy(required_roles=["WAITER", "ADMIN"])
        result = await strategy.authenticate(websocket, token)
        if result.success:
            claims = result.data
    """

    @abstractmethod
    async def authenticate(
        self,
        websocket: "WebSocket",
        token: str,
    ) -> AuthResult:
        """
        Authenticate a WebSocket connection.

        Args:
            websocket: The WebSocket connection (for headers, etc.).
            token: Authentication token (JWT or table token).

        Returns:
            AuthResult indicating success/failure with data or error.
        """
        pass

    @abstractmethod
    async def revalidate(
        self,
        token: str,
    ) -> bool:
        """
        Revalidate a token during an active connection.

        Used for periodic token validation (e.g., detect revoked JWT).

        Args:
            token: The token to revalidate.

        Returns:
            True if token is still valid, False otherwise.
        """
        pass


# =============================================================================
# Origin Validation Mixin
# =============================================================================


class OriginValidationMixin:
    """
    Mixin providing WebSocket origin validation.

    HIGH-NEW-03 FIX: Shared origin validation across strategies.
    """

    def validate_origin(self, websocket: "WebSocket") -> bool:
        """
        Validate WebSocket origin header.

        Args:
            websocket: WebSocket connection with headers.

        Returns:
            True if origin is allowed, False otherwise.
        """
        from shared.config.settings import settings
        from ws_gateway.components.core.constants import validate_websocket_origin

        origin = websocket.headers.get("origin")
        return validate_websocket_origin(origin, settings)


# =============================================================================
# JWT Authentication Strategy
# =============================================================================


class JWTAuthStrategy(AuthStrategy, OriginValidationMixin):
    """
    JWT token authentication strategy.

    Features:
    - Origin validation
    - JWT signature and expiration verification
    - Role-based access control
    - Refresh token rejection

    Usage:
        strategy = JWTAuthStrategy(required_roles=["WAITER", "MANAGER", "ADMIN"])
        result = await strategy.authenticate(websocket, jwt_token)
    """

    def __init__(
        self,
        required_roles: list[str],
        reject_refresh_tokens: bool = True,
    ) -> None:
        """
        Initialize JWT auth strategy.

        Args:
            required_roles: List of roles allowed to authenticate.
            reject_refresh_tokens: Whether to reject refresh tokens (security).
        """
        self._required_roles = required_roles
        self._reject_refresh_tokens = reject_refresh_tokens

    @property
    def required_roles(self) -> list[str]:
        """Roles required for authentication."""
        return list(self._required_roles)

    async def authenticate(
        self,
        websocket: "WebSocket",
        token: str,
    ) -> AuthResult:
        """Authenticate using JWT token."""
        from shared.security.auth import verify_jwt

        # Step 1: Validate origin
        if not self.validate_origin(websocket):
            origin = websocket.headers.get("origin")
            logger.warning("JWT auth rejected - invalid origin", origin=origin)
            return AuthResult.forbidden(
                "Origin not allowed",
                audit_reason="invalid_origin",
            )

        # Step 2: Verify JWT
        try:
            claims = verify_jwt(token)
        except HTTPException as e:
            logger.warning("JWT validation failed", error=str(e.detail))
            return AuthResult.fail(
                "Authentication failed",
                audit_reason="jwt_validation_failed",
            )

        # Step 3: Reject refresh tokens
        if self._reject_refresh_tokens and claims.get("type") == "refresh":
            logger.warning("Refresh token used for WebSocket auth")
            return AuthResult.fail(
                "Authentication failed",
                audit_reason="refresh_token_used",
            )

        # Step 4: Verify roles
        # CROSS-SYS-03 FIX: Explicit validation for empty/missing roles array
        roles = claims.get("roles", [])
        if not isinstance(roles, list):
            logger.warning(
                "JWT auth rejected - roles claim is not a list",
                roles_type=type(roles).__name__,
            )
            return AuthResult.fail(
                "Authentication failed",
                audit_reason="malformed_roles_claim",
            )

        if not roles:
            logger.warning(
                "JWT auth rejected - empty roles array",
                user_id=claims.get("sub"),
                required_roles=self._required_roles,
            )
            return AuthResult.forbidden(
                "Access denied - no roles assigned",
                audit_reason="empty_roles",
            )

        if not any(role in roles for role in self._required_roles):
            logger.warning(
                "JWT auth rejected - insufficient role",
                user_roles=roles,
                required_roles=self._required_roles,
            )
            return AuthResult.forbidden(
                "Access denied",
                audit_reason="insufficient_role",
            )

        return AuthResult.ok(claims)

    async def revalidate(self, token: str) -> bool:
        """Revalidate JWT token."""
        from shared.security.auth import verify_jwt

        try:
            claims = verify_jwt(token)
            if self._reject_refresh_tokens and claims.get("type") == "refresh":
                return False
            return True
        except HTTPException:
            return False


# =============================================================================
# Table Token Authentication Strategy
# =============================================================================


class TableTokenAuthStrategy(AuthStrategy, OriginValidationMixin):
    """
    Table token authentication strategy for diners.

    Features:
    - Origin validation
    - HMAC token verification
    - Session-based authentication

    Usage:
        strategy = TableTokenAuthStrategy()
        result = await strategy.authenticate(websocket, table_token)
    """

    async def authenticate(
        self,
        websocket: "WebSocket",
        token: str,
    ) -> AuthResult:
        """Authenticate using table token."""
        from shared.security.auth import verify_table_token

        # Step 1: Validate origin
        if not self.validate_origin(websocket):
            origin = websocket.headers.get("origin")
            logger.warning("Table token auth rejected - invalid origin", origin=origin)
            return AuthResult.forbidden(
                "Origin not allowed",
                audit_reason="invalid_origin",
            )

        # Step 2: Verify table token
        try:
            token_data = verify_table_token(token)
            return AuthResult.ok(token_data)
        except HTTPException as e:
            logger.warning("Table token validation failed", error=str(e.detail))
            return AuthResult.fail(
                "Authentication failed",
                audit_reason="table_token_validation_failed",
            )

    async def revalidate(self, token: str) -> bool:
        """
        Revalidate table token.

        Table tokens don't typically need revalidation during a session
        as they represent physical presence at a table.
        """
        from shared.security.auth import verify_table_token

        try:
            verify_table_token(token)
            return True
        except HTTPException:
            return False


# =============================================================================
# Composite Strategy (Chain of Responsibility)
# =============================================================================


class CompositeAuthStrategy(AuthStrategy):
    """
    Composite strategy that tries multiple strategies in order.

    PATTERN: Chain of Responsibility - Try strategies until one succeeds.

    Useful for endpoints that accept multiple auth methods.

    Usage:
        composite = CompositeAuthStrategy([
            JWTAuthStrategy(["ADMIN"]),
            TableTokenAuthStrategy(),
        ])
        result = await composite.authenticate(websocket, token)
    """

    def __init__(self, strategies: list[AuthStrategy]) -> None:
        """
        Initialize with list of strategies.

        Args:
            strategies: Strategies to try in order.
        """
        if not strategies:
            raise ValueError("At least one strategy required")
        self._strategies = strategies

    async def authenticate(
        self,
        websocket: "WebSocket",
        token: str,
    ) -> AuthResult:
        """Try each strategy until one succeeds."""
        last_result: AuthResult | None = None

        for strategy in self._strategies:
            result = await strategy.authenticate(websocket, token)
            if result.success:
                return result
            last_result = result

        # Return last failure result
        return last_result or AuthResult.fail("No authentication strategy succeeded")

    async def revalidate(self, token: str) -> bool:
        """Try revalidation with all strategies."""
        for strategy in self._strategies:
            if await strategy.revalidate(token):
                return True
        return False


# =============================================================================
# Null Strategy (for testing)
# =============================================================================


class NullAuthStrategy(AuthStrategy):
    """
    Null strategy that always succeeds or fails based on configuration.

    Useful for testing and development.

    PATTERN: Null Object - Provides neutral behavior.
    """

    def __init__(
        self,
        always_succeed: bool = True,
        mock_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Initialize null strategy.

        Args:
            always_succeed: Whether to always return success.
            mock_data: Mock authentication data to return on success.
        """
        self._always_succeed = always_succeed
        self._mock_data = mock_data or {
            "sub": "1",
            "tenant_id": 1,
            "roles": ["ADMIN"],
            "branch_ids": [1],
        }

    async def authenticate(
        self,
        websocket: "WebSocket",
        token: str,
    ) -> AuthResult:
        """Return configured result."""
        if self._always_succeed:
            return AuthResult.ok(self._mock_data)
        return AuthResult.fail("Auth disabled", audit_reason="null_strategy")

    async def revalidate(self, token: str) -> bool:
        """Return configured result."""
        return self._always_succeed


# =============================================================================
# Factory Functions
# =============================================================================


def create_waiter_auth_strategy() -> JWTAuthStrategy:
    """Create auth strategy for waiter endpoint."""
    return JWTAuthStrategy(required_roles=["WAITER", "MANAGER", "ADMIN"])


def create_kitchen_auth_strategy() -> JWTAuthStrategy:
    """Create auth strategy for kitchen endpoint."""
    return JWTAuthStrategy(required_roles=["KITCHEN", "MANAGER", "ADMIN"])


def create_admin_auth_strategy() -> JWTAuthStrategy:
    """Create auth strategy for admin endpoint."""
    return JWTAuthStrategy(required_roles=["MANAGER", "ADMIN"])


def create_diner_auth_strategy() -> TableTokenAuthStrategy:
    """Create auth strategy for diner endpoint."""
    return TableTokenAuthStrategy()
