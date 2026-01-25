"""
Authentication and authorization utilities.
Handles JWT tokens for staff and HMAC tokens for diners.

CRIT-AUTH-01 FIX: Now verifies tokens against blacklist
CRIT-AUTH-04 FIX: JWT tokens now include "jti" (unique token ID)
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import jwt


def _hash_jti(jti: str) -> str:
    """
    HIGH-AUTH-01 FIX: Hash JTI for logging to avoid exposing token identifiers.
    Returns first 8 characters of SHA256 hash.
    """
    return hashlib.sha256(jti.encode()).hexdigest()[:8]
from fastapi import Depends, HTTPException, Header, Query, status

from shared.config.settings import (
    JWT_SECRET,
    JWT_ISSUER,
    JWT_AUDIENCE,
    TABLE_TOKEN_SECRET,
    settings,
)
from shared.config.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# JWT Functions (for staff authentication)
# =============================================================================


def sign_jwt(
    payload: dict[str, Any],
    ttl_seconds: int | None = None,
    token_type: str = "access",
) -> str:
    """
    Sign a JWT token with the given payload.

    CRIT-AUTH-04 FIX: Now includes "jti" (JWT ID) for individual token blacklisting.

    Args:
        payload: Claims to include in the token (sub, tenant_id, branch_ids, roles, etc.)
        ttl_seconds: Token lifetime in seconds. Defaults to access token expiry.
        token_type: Type of token ("access" or "refresh").

    Returns:
        Signed JWT token string.
    """
    if ttl_seconds is None:
        if token_type == "refresh":
            ttl_seconds = settings.jwt_refresh_token_expire_days * 24 * 60 * 60
        else:
            ttl_seconds = settings.jwt_access_token_expire_minutes * 60

    now = int(time.time())
    data = {
        **payload,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
        "type": token_type,
        # CRIT-AUTH-04 FIX: Add unique token ID for individual blacklisting
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(data, JWT_SECRET, algorithm="HS256")


def sign_refresh_token(user_id: int, tenant_id: int) -> str:
    """
    Create a refresh token for a user.

    Refresh tokens have longer expiry and contain minimal claims.
    They can only be used to obtain new access tokens.
    """
    return sign_jwt(
        {"sub": str(user_id), "tenant_id": tenant_id},
        token_type="refresh"
    )


def verify_refresh_token(token: str) -> dict[str, Any]:
    """
    Verify and decode a refresh token.

    Raises:
        HTTPException: If token is invalid, expired, or not a refresh token.
    """
    payload = verify_jwt(token)
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected refresh token.",
        )
    return payload


def verify_jwt(token: str, check_blacklist: bool = True) -> dict[str, Any]:
    """
    Verify and decode a JWT token.

    CRIT-AUTH-01 FIX: Now checks token against blacklist.
    SHARED-HIGH-03 FIX: Added validation of required claims.

    Args:
        token: The JWT token string.
        check_blacklist: Whether to check token against blacklist (default True).

    Returns:
        Decoded token claims.

    Raises:
        HTTPException: If token is invalid, expired, or blacklisted.
    """
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=["HS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
        )

        # SHARED-HIGH-03 FIX: Validate required claims for access tokens
        # Access tokens must have: sub, tenant_id, type
        if "sub" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject claim",
            )

        if "tenant_id" not in payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing tenant_id claim",
            )

        # SHARED-HIGH-03 FIX: Validate type claim exists
        token_type = payload.get("type")
        if token_type not in ("access", "refresh", None):  # None for legacy tokens
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: invalid type claim",
            )

        # SHARED-HIGH-03 FIX: Validate sub is a valid integer string
        try:
            int(payload["sub"])
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: malformed subject claim",
            )

        # SHARED-HIGH-03 FIX: Validate tenant_id is an integer
        if not isinstance(payload["tenant_id"], int):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: malformed tenant_id claim",
            )

        # CRIT-AUTH-01 FIX: Check token against blacklist
        if check_blacklist:
            _check_token_blacklist(payload)

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError as e:
        # SHARED-CRIT-01 FIX: Sanitize error message to avoid exposing internal details
        # Log the actual error for debugging, but return generic message to client
        logger.warning("JWT validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


def _check_token_blacklist(payload: dict[str, Any]) -> None:
    """
    CRIT-AUTH-01 FIX: Check if token is blacklisted.
    SHARED-CRIT-01 FIX: Refactored to avoid deadlock with ThreadPoolExecutor+asyncio.run.

    Checks both:
    1. Individual token blacklist (by jti)
    2. User-level revocation (all tokens before timestamp)

    Raises:
        HTTPException: If token is blacklisted/revoked.
    """
    from shared.security.token_blacklist import (
        is_token_blacklisted_sync,
        is_token_revoked_by_user_sync,
    )

    token_jti = payload.get("jti")
    user_id = payload.get("sub")
    token_iat = payload.get("iat")

    # SHARED-CRIT-01 FIX: Use synchronous wrappers that handle event loop correctly
    # SHARED-HIGH-01 FIX: Changed from "fail open" to "fail closed" for security
    # If Redis is unavailable, we deny access rather than allowing potentially revoked tokens

    # If token has jti, check individual blacklist
    if token_jti:
        try:
            is_blacklisted = is_token_blacklisted_sync(token_jti)

            if is_blacklisted:
                # HIGH-AUTH-01 FIX: Hash JTI in logs to avoid exposing token identifiers
                logger.warning("Blacklisted token used", jti_hash=_hash_jti(token_jti))
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )
        except HTTPException:
            raise
        except Exception as e:
            # SHARED-HIGH-01 FIX: Fail closed - deny access if we can't verify token status
            # HIGH-AUTH-01 FIX: Hash JTI in logs
            logger.error("Error checking token blacklist - denying access for security", jti_hash=_hash_jti(token_jti), error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again.",
            )

    # Check user-level revocation
    if user_id and token_iat:
        try:
            token_iat_dt = datetime.fromtimestamp(token_iat, tz=timezone.utc)
            user_id_int = int(user_id)

            is_revoked = is_token_revoked_by_user_sync(user_id_int, token_iat_dt)

            if is_revoked:
                logger.warning("User-revoked token used", user_id=user_id)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )
        except HTTPException:
            raise
        except Exception as e:
            # SHARED-HIGH-01 FIX: Fail closed - deny access if we can't verify token status
            logger.error("Error checking user token revocation - denying access for security", user_id=user_id, error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable. Please try again.",
            )


def get_bearer_token(authorization: str | None) -> str:
    """
    Extract bearer token from Authorization header.

    Args:
        authorization: The Authorization header value.

    Returns:
        The token string without "Bearer " prefix.

    Raises:
        HTTPException: If header is missing or malformed.
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected: Bearer <token>",
        )
    return authorization.split(" ", 1)[1].strip()


def current_user_context(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> dict[str, Any]:
    """
    FastAPI dependency to get the current user context from JWT.

    Usage:
        @app.get("/protected")
        def protected_endpoint(ctx = Depends(current_user_context)):
            user_id = ctx["sub"]
            tenant_id = ctx["tenant_id"]
            ...

    Returns:
        Dict with: sub (user_id), tenant_id, branch_ids, roles, email
    """
    token = get_bearer_token(authorization)
    return verify_jwt(token)


def require_roles(ctx: dict[str, Any], allowed: list[str]) -> None:
    """
    Verify that the user has at least one of the allowed roles.

    Args:
        ctx: User context from current_user_context.
        allowed: List of role names that are permitted.

    Raises:
        HTTPException: If user lacks required role.
    """
    user_roles = set(ctx.get("roles", []))
    if not user_roles.intersection(set(allowed)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Insufficient permissions. Required role: one of {allowed}",
        )


def require_branch(ctx: dict[str, Any], branch_id: int) -> None:
    """
    Verify that the user has access to the specified branch.

    Args:
        ctx: User context from current_user_context.
        branch_id: The branch ID to check access for.

    Raises:
        HTTPException: If user lacks access to the branch.
    """
    user_branches = set(ctx.get("branch_ids", []))
    if branch_id not in user_branches:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No access to branch {branch_id}",
        )


# =============================================================================
# Table Token Functions (for diner authentication)
# Phase 5: Migrated from HMAC to JWT for better standardization
# =============================================================================


# Constants for table token JWT
TABLE_TOKEN_ISSUER = "integrador:table"
TABLE_TOKEN_AUDIENCE = "integrador:diner"


def sign_table_token(
    tenant_id: int,
    branch_id: int,
    table_id: int,
    session_id: int,
    ttl_seconds: int | None = None,
) -> str:
    """
    Create a JWT token for table/diner authentication.

    Phase 5: Migrated from HMAC to JWT for:
    - Better standardization
    - Easier debugging (can decode payload)
    - Support for additional claims (diner_id, etc.)
    - Consistent with staff authentication

    MED-AUTH-01 FIX: Now uses settings.jwt_table_token_expire_hours by default.

    Args:
        tenant_id: Restaurant tenant ID.
        branch_id: Branch ID.
        table_id: Table ID.
        session_id: Active table session ID.
        ttl_seconds: Token lifetime in seconds. Defaults to settings value.

    Returns:
        Signed JWT token string.
    """
    if ttl_seconds is None:
        ttl_seconds = settings.jwt_table_token_expire_hours * 60 * 60
    now = int(time.time())
    payload = {
        "tenant_id": tenant_id,
        "branch_id": branch_id,
        "table_id": table_id,
        "session_id": session_id,
        "type": "table",  # Distinguish from staff JWT
        "iss": TABLE_TOKEN_ISSUER,
        "aud": TABLE_TOKEN_AUDIENCE,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(payload, TABLE_TOKEN_SECRET, algorithm="HS256")


def verify_table_token(token: str) -> dict[str, int]:
    """
    Verify and decode a table token (JWT format).

    Supports both new JWT format and legacy HMAC format for backward compatibility.

    Args:
        token: The table token string (JWT or legacy HMAC).

    Returns:
        Dict with: tenant_id, branch_id, table_id, session_id

    Raises:
        HTTPException: If token is invalid or expired.
    """
    # First, try JWT format (Phase 5)
    if token.count(".") == 2:  # JWT has 3 parts separated by dots
        return _verify_table_token_jwt(token)

    # Fallback to legacy HMAC format for backward compatibility
    return _verify_table_token_hmac(token)


def _verify_table_token_jwt(token: str) -> dict[str, int]:
    """Verify JWT-format table token."""
    try:
        payload = jwt.decode(
            token,
            TABLE_TOKEN_SECRET,
            algorithms=["HS256"],
            audience=TABLE_TOKEN_AUDIENCE,
            issuer=TABLE_TOKEN_ISSUER,
        )

        # Verify it's a table token
        if payload.get("type") != "table":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )

        return {
            "tenant_id": int(payload["tenant_id"]),
            "branch_id": int(payload["branch_id"]),
            "table_id": int(payload["table_id"]),
            "session_id": int(payload["session_id"]),
        }

    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Table token has expired",
        )
    except jwt.InvalidTokenError as e:
        # SHARED-CRIT-02 FIX: Sanitize error message to avoid exposing internal details
        logger.warning("Table token JWT validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid table token",
        )


def _verify_table_token_hmac(token: str) -> dict[str, int]:
    """
    Verify legacy HMAC-format table token (for backward compatibility).

    The token format is: {tenant_id}:{branch_id}:{table_id}:{session_id}:{expires_at}:{signature}
    """
    try:
        parts = token.split(":")
        if len(parts) != 6:
            raise ValueError("Invalid token format")

        tenant_id, branch_id, table_id, session_id, expires_at, signature = parts

        # Verify expiration
        if int(expires_at) < int(time.time()):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Table token has expired",
            )

        # Verify signature
        data = f"{tenant_id}:{branch_id}:{table_id}:{session_id}:{expires_at}"
        expected_signature = hmac.new(
            TABLE_TOKEN_SECRET.encode(),
            data.encode(),
            hashlib.sha256,
        ).hexdigest()[:32]

        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid table token signature",
            )

        return {
            "tenant_id": int(tenant_id),
            "branch_id": int(branch_id),
            "table_id": int(table_id),
            "session_id": int(session_id),
        }

    except ValueError as e:
        # SHARED-CRIT-02 FIX: Sanitize error message to avoid exposing internal details
        logger.warning("Table token HMAC validation failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid table token",
        )


def current_table_context(
    x_table_token: str | None = Header(default=None, alias="X-Table-Token"),
) -> dict[str, int]:
    """
    FastAPI dependency to get table context from X-Table-Token header.

    Usage:
        @app.post("/diner/order")
        def submit_order(table_ctx = Depends(current_table_context)):
            session_id = table_ctx["session_id"]
            ...

    Returns:
        Dict with: tenant_id, branch_id, table_id, session_id
    """
    if not x_table_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Table-Token header",
        )
    return verify_table_token(x_table_token)


# =============================================================================
# WebSocket Authentication (token in query param)
# =============================================================================


def ws_auth_context(token: str = Query(...)) -> dict[str, Any]:
    """
    Verify JWT token from WebSocket query parameter.

    Usage in WebSocket endpoint:
        @app.websocket("/ws/waiter")
        async def waiter_ws(ws: WebSocket, ctx: dict = Depends(ws_auth_context)):
            ...
    """
    return verify_jwt(token)
