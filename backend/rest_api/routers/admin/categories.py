"""
Category management endpoints.

CLEAN-ARCH: Thin router that delegates to CategoryService.
Router handles: HTTP concerns, request validation, response formatting.
Service handles: Business logic, data access via Repository.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from shared.infrastructure.db import get_db
from shared.security.auth import current_user_context as current_user

from shared.utils.admin_schemas import CategoryOutput, CategoryCreate, CategoryUpdate
from rest_api.routers._common.pagination import Pagination, get_pagination
from rest_api.services.permissions import PermissionContext
from rest_api.services.domain import CategoryService


router = APIRouter(tags=["admin-categories"])


# =============================================================================
# Endpoints
# =============================================================================


@router.get("/categories", response_model=list[CategoryOutput])
def list_categories(
    branch_id: int | None = None,
    include_deleted: bool = False,
    pagination: Pagination = Depends(get_pagination),
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[CategoryOutput]:
    """
    List categories, optionally filtered by branch.
    MANAGER users only see categories from their assigned branches.
    """
    ctx = PermissionContext(user)
    service = CategoryService(db)

    # Branch filtering based on role
    if branch_id:
        ctx.require_branch_access(branch_id)
        return service.list_by_branch_ordered(
            tenant_id=ctx.tenant_id,
            branch_id=branch_id,
            include_inactive=include_deleted,
            limit=pagination.limit,
            offset=pagination.offset,
        )

    if not ctx.is_admin:
        # MANAGER: filter to accessible branches
        if ctx.branch_ids:
            return service.list_by_branches(
                tenant_id=ctx.tenant_id,
                branch_ids=ctx.branch_ids,
                include_inactive=include_deleted,
                limit=pagination.limit,
                offset=pagination.offset,
            )
        return []

    # ADMIN: all categories
    return service.list_all(
        tenant_id=ctx.tenant_id,
        include_inactive=include_deleted,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get("/categories/{category_id}", response_model=CategoryOutput)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> CategoryOutput:
    """
    Get a specific category.
    MANAGER users can only access categories from their assigned branches.
    """
    ctx = PermissionContext(user)
    service = CategoryService(db)

    # Get category (raises NotFoundError if not found)
    output = service.get_by_id(category_id, ctx.tenant_id)

    # Get raw entity for branch validation
    entity = service.get_entity(category_id, ctx.tenant_id)
    if entity:
        ctx.require_branch_access(entity.branch_id)

    return output


@router.post("/categories", response_model=CategoryOutput, status_code=201)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> CategoryOutput:
    """
    Create a new category. Requires ADMIN or MANAGER role.
    MANAGER users can only create categories in their assigned branches.
    """
    ctx = PermissionContext(user)
    ctx.require_management()
    ctx.require_branch_access(body.branch_id)

    service = CategoryService(db)

    return service.create_with_auto_order(
        data=body.model_dump(),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        user_email=ctx.user_email,
    )


@router.patch("/categories/{category_id}", response_model=CategoryOutput)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> CategoryOutput:
    """
    Update a category. Requires ADMIN or MANAGER role.
    MANAGER users can only update categories in their assigned branches.
    """
    ctx = PermissionContext(user)
    ctx.require_management()

    service = CategoryService(db)

    # Validate branch access
    entity = service.get_entity(category_id, ctx.tenant_id)
    if entity:
        service.validate_branch_access(entity, ctx.branch_ids if not ctx.is_admin else None)

    return service.update(
        entity_id=category_id,
        data=body.model_dump(exclude_unset=True),
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        user_email=ctx.user_email,
    )


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """
    Soft delete a category. Requires ADMIN or MANAGER role.
    MANAGER users can only delete categories in their assigned branches.
    """
    ctx = PermissionContext(user)
    ctx.require_management()

    service = CategoryService(db)

    # Validate branch access
    entity = service.get_entity(category_id, ctx.tenant_id)
    if entity:
        service.validate_branch_access(entity, ctx.branch_ids if not ctx.is_admin else None)

    # Delete (service handles event publishing)
    service.delete(
        entity_id=category_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        user_email=ctx.user_email,
    )
