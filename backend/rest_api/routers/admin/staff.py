"""
Staff management endpoints - Clean Architecture refactor.

CLEAN-ARCH: Thin router that delegates to StaffService.
All business logic is in rest_api/services/domain/staff_service.py.

Reduced from 333 lines to ~130 lines (61% reduction).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.infrastructure.db import get_db
from shared.security.auth import current_user_context as current_user
from shared.utils.admin_schemas import StaffOutput, StaffCreate, StaffUpdate
from shared.utils.exceptions import NotFoundError, ForbiddenError, ValidationError
from rest_api.routers._common import get_user_id, get_user_email
from rest_api.routers.admin._base import require_admin_or_manager
from rest_api.services.domain import StaffService
from shared.config.constants import Roles


router = APIRouter(tags=["admin-staff"])


def _get_service(db: Session) -> StaffService:
    """Get StaffService instance."""
    return StaffService(db)


@router.get("/staff", response_model=list[StaffOutput])
def list_staff(
    branch_id: int | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> list[StaffOutput]:
    """
    List staff members, optionally filtered by branch.

    ADMIN: Can see all staff across all branches
    MANAGER: Can only see staff assigned to their branches
    Supports pagination via limit/offset parameters (default: 50, max: 200).
    """
    service = _get_service(db)

    try:
        return service.list_all(
            tenant_id=user["tenant_id"],
            requesting_user=user,
            branch_id=branch_id,
            include_inactive=include_deleted,
            limit=limit,
            offset=offset,
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.get("/staff/{staff_id}", response_model=StaffOutput)
def get_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> StaffOutput:
    """Get a specific staff member."""
    service = _get_service(db)

    try:
        return service.get_by_id(
            staff_id=staff_id,
            tenant_id=user["tenant_id"],
            requesting_user=user,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.post("/staff", response_model=StaffOutput, status_code=status.HTTP_201_CREATED)
def create_staff(
    body: StaffCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> StaffOutput:
    """
    Create a new staff member.

    ADMIN: Can create staff in any branch with any role
    MANAGER: Can only create staff in their assigned branches, cannot create ADMIN role
    """
    service = _get_service(db)

    try:
        return service.create_with_roles(
            data=body.model_dump(),
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
            requesting_user=user,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.patch("/staff/{staff_id}", response_model=StaffOutput)
def update_staff(
    staff_id: int,
    body: StaffUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> StaffOutput:
    """
    Update a staff member.

    ADMIN: Can update any staff member in any branch with any role
    MANAGER: Can only update staff in their branches, cannot assign ADMIN role
    """
    service = _get_service(db)

    try:
        return service.update_with_roles(
            staff_id=staff_id,
            data=body.model_dump(exclude_unset=True),
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
            requesting_user=user,
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )
    except ForbiddenError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        )


@router.delete("/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a staff member. Requires ADMIN role."""
    if Roles.ADMIN not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    service = _get_service(db)

    try:
        service.delete_staff(
            staff_id=staff_id,
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )
