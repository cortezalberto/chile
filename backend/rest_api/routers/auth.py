"""
Authentication router.
Handles login and token refresh.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from rest_api.db import get_db
from rest_api.models import User, UserBranchRole, Branch
from shared.auth import sign_jwt, sign_refresh_token, verify_refresh_token
from shared.logging import rest_api_logger as logger, mask_email
from shared.schemas import LoginRequest, LoginResponse, UserInfo, RefreshTokenRequest
from shared.settings import settings
from shared.rate_limit import limiter, email_limiter, set_rate_limit_email
from shared.password import verify_password, needs_rehash, hash_password
from shared.token_blacklist import revoke_all_user_tokens
from shared.auth import current_user_context


router = APIRouter(prefix="/api/auth", tags=["auth"])


class LogoutResponse(BaseModel):
    """Response for logout."""
    success: bool
    message: str


class TokenRefreshResponse(BaseModel):
    """Response for token refresh."""
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


class LoginWithRefreshResponse(LoginResponse):
    """Login response including refresh token."""
    refresh_token: str


@router.post("/login", response_model=LoginWithRefreshResponse)
@limiter.limit("5/minute")
@email_limiter.limit("5/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)) -> LoginWithRefreshResponse:
    """
    Authenticate a staff member and return access + refresh tokens.

    The access token contains:
    - sub: user ID
    - tenant_id: restaurant tenant ID
    - branch_ids: list of branches the user has access to
    - roles: list of roles the user has
    - email: user's email

    The refresh token can be used to obtain new access tokens.

    CRIT-AUTH-02 FIX: Rate limited by both IP (5/min) and email (5/min)
    to prevent credential stuffing attacks from distributed IPs.
    """
    # CRIT-AUTH-02 FIX: Set email for email-based rate limiting
    set_rate_limit_email(request, body.email)

    # Find user by email
    user = db.scalar(
        select(User).where(User.email == body.email, User.is_active == True)
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

    return LoginWithRefreshResponse(
        access_token=access_token,
        refresh_token=refresh_token,
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
@limiter.limit("10/minute")
def refresh_token(request: Request, body: RefreshTokenRequest, db: Session = Depends(get_db)) -> TokenRefreshResponse:
    """
    Exchange a refresh token for a new access token.

    The refresh token is verified and a new access token is issued
    with the user's current roles and branches (re-fetched from DB).
    """
    # Verify the refresh token
    payload = verify_refresh_token(body.refresh_token)
    user_id = int(payload["sub"])

    # Fetch user to verify still active and get current roles
    user = db.scalar(
        select(User).where(User.id == user_id, User.is_active == True)
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

    # Create new access token
    access_token = sign_jwt({
        "sub": str(user.id),
        "tenant_id": user.tenant_id,
        "branch_ids": branch_ids,
        "roles": roles,
        "email": user.email,
    })

    return TokenRefreshResponse(
        access_token=access_token,
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
