"""
Authentication router.
Handles login and token refresh.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from rest_api.db import get_db
from rest_api.models import User, UserBranchRole
from shared.auth import sign_jwt, sign_refresh_token, verify_refresh_token
from shared.schemas import LoginRequest, LoginResponse, UserInfo, RefreshTokenRequest
from shared.settings import settings
from shared.rate_limit import limiter


router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    """
    # Find user by email
    user = db.scalar(
        select(User).where(User.email == body.email, User.is_active == True)
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # MVP: plain text password comparison
    # TODO: Use passlib bcrypt in production
    if user.password != body.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Get user's roles and branches
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
    ctx: dict = Depends(__import__("shared.auth", fromlist=["current_user_context"]).current_user_context),
) -> UserInfo:
    """Get current authenticated user info."""
    return UserInfo(
        id=int(ctx["sub"]),
        email=ctx["email"],
        tenant_id=ctx["tenant_id"],
        branch_ids=ctx["branch_ids"],
        roles=ctx["roles"],
    )
