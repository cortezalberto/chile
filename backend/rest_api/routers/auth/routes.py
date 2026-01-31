"""
Authentication router.
Handles login and token refresh.
"""

from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, status, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from shared.infrastructure.db import get_db
from rest_api.models import User, UserBranchRole, Branch
from shared.security.auth import sign_jwt, sign_refresh_token, verify_refresh_token
from shared.config.logging import rest_api_logger as logger, mask_email
from shared.utils.schemas import LoginRequest, LoginResponse, UserInfo, RefreshTokenRequest
from shared.config.settings import settings
from shared.security.rate_limit import limiter, set_rate_limit_email, check_email_rate_limit_sync
from shared.security.password import verify_password, needs_rehash, hash_password
from shared.security.token_blacklist import revoke_all_user_tokens, blacklist_token_sync, is_token_blacklisted_sync
from shared.security.auth import current_user_context


router = APIRouter(prefix="/api/auth", tags=["auth"])


# =============================================================================
# SEC-09: HttpOnly Cookie Helper
# =============================================================================

def set_refresh_token_cookie(response: Response, refresh_token: str) -> None:
    """
    SEC-09: Set refresh token as HttpOnly cookie with security flags.

    - httponly: Cannot be accessed by JavaScript (XSS protection)
    - secure: Only sent over HTTPS (configurable for dev)
    - samesite: CSRF protection (lax allows top-level navigation)
    - path: Only sent to /api/auth endpoints
    - max_age: 7 days (matches refresh token expiry)
    """
    max_age_seconds = settings.jwt_refresh_token_expire_days * 24 * 60 * 60

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=max_age_seconds,
        path="/api/auth",
        domain=settings.cookie_domain or None,
    )


def clear_refresh_token_cookie(response: Response) -> None:
    """SEC-09: Clear refresh token cookie on logout."""
    response.delete_cookie(
        key="refresh_token",
        path="/api/auth",
        domain=settings.cookie_domain or None,
    )


class LogoutResponse(BaseModel):
    """Response for logout."""
    success: bool
    message: str


class TokenRefreshResponse(BaseModel):
    """Response for token refresh with rotated refresh token."""
    access_token: str
    refresh_token: str  # SEC-06: Always rotate refresh token
    token_type: str = "Bearer"
    expires_in: int


class LoginWithRefreshResponse(LoginResponse):
    """Login response including refresh token."""
    refresh_token: str


@router.post("/login", response_model=LoginWithRefreshResponse)
@limiter.limit("5/minute")
def login(request: Request, response: Response, body: LoginRequest, db: Session = Depends(get_db)) -> LoginWithRefreshResponse:
    """
    Authenticate a staff member and return access + refresh tokens.

    The access token contains:
    - sub: user ID
    - tenant_id: restaurant tenant ID
    - branch_ids: list of branches the user has access to
    - roles: list of roles the user has
    - email: user's email

    The refresh token can be used to obtain new access tokens.

    CRIT-AUTH-02 FIX: Rate limited by both IP (5/min via slowapi) and
    email (5/min via Redis) to prevent credential stuffing attacks.
    QA-HIGH-01 FIX: Email-based rate limiting using Redis INCR with TTL.
    """
    # QA-HIGH-01 FIX: Check email-based rate limit using Redis
    check_email_rate_limit_sync(body.email)

    # Track email for logging purposes
    set_rate_limit_email(request, body.email)

    # Find user by email
    user = db.scalar(
        select(User).where(User.email == body.email, User.is_active.is_(True))
    )

    if not user:
        # HIGH-AUTH-05 FIX: Log failed login attempt (user not found)
        # SHARED-HIGH-02 FIX: Mask email to protect PII
        logger.warning("LOGIN_FAILED: User not found", email=mask_email(body.email))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Verify password using bcrypt (supports legacy plain-text during migration)
    if not verify_password(body.password, user.password):
        # HIGH-AUTH-05 FIX: Log failed login attempt (wrong password)
        # SHARED-HIGH-02 FIX: Mask email to protect PII
        logger.warning("LOGIN_FAILED: Invalid password", email=mask_email(body.email), user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Rehash password if using legacy plain-text or outdated bcrypt rounds
    if needs_rehash(user.password):
        user.password = hash_password(body.password)
        db.commit()

    # Get user's roles and branches
    branch_roles = db.execute(
        select(UserBranchRole).where(UserBranchRole.user_id == user.id)
    ).scalars().all()

    branch_ids = sorted({r.branch_id for r in branch_roles})
    roles = sorted({r.role for r in branch_roles})

    if not branch_ids:
        # SHARED-HIGH-02 FIX: Mask email to protect PII
        logger.warning("LOGIN_FAILED: No branch assignments", email=mask_email(body.email), user_id=user.id)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no branch assignments",
        )

    # CRIT-AUTH-05 FIX: Validate tenant isolation - all branches must belong to user's tenant
    branches = db.execute(
        select(Branch).where(Branch.id.in_(branch_ids))
    ).scalars().all()

    for branch in branches:
        if branch.tenant_id != user.tenant_id:
            logger.error(
                "SECURITY: Tenant isolation violation detected",
                user_id=user.id,
                user_tenant_id=user.tenant_id,
                branch_id=branch.id,
                branch_tenant_id=branch.tenant_id,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Security error: tenant isolation violation",
            )

    # Create access token
    access_token = sign_jwt({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "branch_ids": branch_ids,
        "roles": roles,
        "email": user.email,
    })

    # Create refresh token
    refresh_token = sign_refresh_token(user.id, user.tenant_id)

    # HIGH-AUTH-05 FIX: Log successful login
    # SHARED-HIGH-02 FIX: Mask email to protect PII
    logger.info("LOGIN_SUCCESS", email=mask_email(user.email), user_id=user.id, roles=roles, branch_count=len(branch_ids))

    # SEC-09: Set refresh token as HttpOnly cookie
    set_refresh_token_cookie(response, refresh_token)

    return LoginWithRefreshResponse(
        access_token=access_token,
        refresh_token=refresh_token,  # Also in body for backward compatibility
        token_type="Bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
        user=UserInfo(
            id=user.id,
            email=user.email,
            tenant_id=user.tenant_id,
            branch_ids=branch_ids,
            roles=roles,
        ),
    )


@router.post("/refresh", response_model=TokenRefreshResponse)
@limiter.limit("5/minute")  # SEC-07: Stricter rate limit for refresh endpoint
def refresh_token(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenRequest] = None,
    refresh_token_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
    db: Session = Depends(get_db),
) -> TokenRefreshResponse:
    """
    Exchange a refresh token for new access + refresh tokens.

    SEC-06: Token Rotation - Always issues a new refresh token.
    SEC-08: Reuse Detection - Detects if refresh token was already used.
    SEC-09: Reads refresh token from HttpOnly cookie first, falls back to body.

    The old refresh token is blacklisted immediately after use.
    If a blacklisted refresh token is used, it indicates token theft
    and all user tokens are revoked for security.
    """
    from datetime import datetime, timezone

    # SEC-09: Get refresh token from cookie first, fallback to body
    token_value = refresh_token_cookie
    if not token_value and body and body.refresh_token:
        token_value = body.refresh_token

    if not token_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token not provided",
        )

    # Verify the refresh token
    payload = verify_refresh_token(token_value)
    user_id = int(payload["sub"])
    token_jti = payload.get("jti")
    token_exp = payload.get("exp")

    # SEC-08: Check if this refresh token was already used (reuse detection)
    if token_jti:
        try:
            is_already_used = is_token_blacklisted_sync(token_jti)
            if is_already_used:
                # SECURITY ALERT: Token reuse detected - possible theft
                logger.error(
                    "SECURITY: Refresh token reuse detected - revoking all user tokens",
                    user_id=user_id,
                    jti_hash=token_jti[:8] if token_jti else "N/A",
                )
                # Revoke ALL tokens for this user (nuclear option)
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # We're in an async context, can't use run_until_complete
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            pool.submit(asyncio.run, revoke_all_user_tokens(user_id)).result(timeout=5.0)
                    else:
                        loop.run_until_complete(revoke_all_user_tokens(user_id))
                except Exception as e:
                    logger.error("Failed to revoke user tokens after reuse detection", error=str(e))

                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Refresh token has been revoked. Please login again.",
                )
        except HTTPException:
            raise
        except Exception as e:
            # Fail closed - if we can't verify, deny access
            logger.error("Error checking refresh token reuse", error=str(e))
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service temporarily unavailable",
            )

    # Fetch user to verify still active and get current roles
    user = db.scalar(
        select(User).where(User.id == user_id, User.is_active.is_(True))
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    # Get current roles and branches
    branch_roles = db.execute(
        select(UserBranchRole).where(UserBranchRole.user_id == user.id)
    ).scalars().all()

    branch_ids = sorted({r.branch_id for r in branch_roles})
    roles = sorted({r.role for r in branch_roles})

    if not branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User has no branch assignments",
        )

    # SEC-06: Blacklist the OLD refresh token BEFORE issuing new one
    if token_jti and token_exp:
        try:
            expires_at = datetime.fromtimestamp(token_exp, tz=timezone.utc)
            blacklist_token_sync(token_jti, expires_at)
            logger.debug("Old refresh token blacklisted", user_id=user_id)
        except Exception as e:
            # Log but don't fail - the new token will be issued anyway
            logger.warning("Failed to blacklist old refresh token", error=str(e))

    # Create new access token
    access_token = sign_jwt({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "branch_ids": branch_ids,
        "roles": roles,
        "email": user.email,
    })

    # SEC-06: Create NEW refresh token (rotation)
    new_refresh_token = sign_refresh_token(user.id, user.tenant_id)

    # SEC-09: Set new refresh token as HttpOnly cookie
    set_refresh_token_cookie(response, new_refresh_token)

    logger.info("Token refresh successful", user_id=user_id)

    return TokenRefreshResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,  # Also in body for backward compatibility
        token_type="Bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserInfo)
def get_current_user(
    db: Session = Depends(get_db),
    ctx: dict = Depends(current_user_context),
) -> UserInfo:
    """Get current authenticated user info."""
    return UserInfo(
        id=int(ctx["sub"]),
        email=ctx["email"],
        tenant_id=ctx["tenant_id"],
        branch_ids=ctx["branch_ids"],
        roles=ctx["roles"],
    )


@router.post("/logout", response_model=LogoutResponse)
@limiter.limit("10/minute")
async def logout(
    request: Request,
    response: Response,
    ctx: dict = Depends(current_user_context),
) -> LogoutResponse:
    """
    Logout the current user by revoking all their tokens.

    This invalidates:
    - The current access token
    - The current refresh token
    - All other active sessions for this user

    The user will need to login again on all devices.

    HIGH-AUTH-01 FIX: Properly reports success/failure of token revocation.
    """
    user_id = int(ctx["sub"])
    user_email = ctx.get("email", "")

    # Revoke all tokens for this user
    success = await revoke_all_user_tokens(user_id)

    # SEC-09: Clear refresh token cookie
    clear_refresh_token_cookie(response)

    if success:
        # HIGH-AUTH-05 FIX: Log successful logout
        # SHARED-HIGH-02 FIX: Mask email to protect PII
        logger.info("LOGOUT_SUCCESS", email=mask_email(user_email), user_id=user_id)
        return LogoutResponse(
            success=True,
            message="Logged out successfully. All sessions have been invalidated.",
        )
    else:
        # HIGH-AUTH-01/05 FIX: Log and report failure
        # SHARED-HIGH-02 FIX: Mask email to protect PII
        logger.warning("LOGOUT_PARTIAL: Token revocation may have failed", email=mask_email(user_email), user_id=user_id)
        return LogoutResponse(
            success=False,
            message="Logout completed but token revocation may be delayed.",
        )
