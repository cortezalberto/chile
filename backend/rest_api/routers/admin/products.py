"""
Product management endpoints - Clean Architecture refactor.

CLEAN-ARCH: Thin router that delegates to ProductService.
All business logic is in rest_api/services/domain/product_service.py.

Reduced from 1022 lines to ~200 lines (80% reduction).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from shared.infrastructure.db import get_db
from shared.security.auth import current_user_context as current_user
from shared.utils.admin_schemas import ProductOutput, ProductCreate, ProductUpdate
from shared.utils.exceptions import NotFoundError, ValidationError
from rest_api.routers._common import get_user_id, get_user_email
from rest_api.routers.admin._base import (
    require_admin_or_manager,
    is_admin,
    validate_branch_access,
    filter_by_accessible_branches,
)
from rest_api.services.domain import ProductService


router = APIRouter(tags=["admin-products"])


def _get_service(db: Session) -> ProductService:
    """Get ProductService instance."""
    return ProductService(db)


@router.get("/products", response_model=list[ProductOutput])
def list_products(
    category_id: int | None = None,
    branch_id: int | None = None,
    include_deleted: bool = False,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[ProductOutput]:
    """
    List products, optionally filtered by category or branch.

    MANAGER users only see products available in their assigned branches.
    Supports pagination via limit/offset parameters (default: 100, max: 500).
    """
    service = _get_service(db)

    # MANAGER branch isolation
    branch_ids_filter, should_filter = filter_by_accessible_branches(user, branch_id)
    if should_filter and not branch_ids_filter:
        return []

    return service.list_with_relations(
        tenant_id=user["tenant_id"],
        category_id=category_id,
        branch_id=branch_id if not should_filter else None,
        branch_ids=branch_ids_filter if should_filter else None,
        include_inactive=include_deleted,
        limit=limit,
        offset=offset,
    )


@router.get("/products/{product_id}", response_model=ProductOutput)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ProductOutput:
    """
    Get a specific product with branch prices and allergens.

    MANAGER users can only access products available in their assigned branches.
    """
    service = _get_service(db)

    try:
        product = service.get_with_relations(product_id, user["tenant_id"])
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # MANAGER branch isolation
    if not is_admin(user):
        user_branch_ids = user.get("branch_ids", [])
        product_entity = service.get_entity(product_id, user["tenant_id"])
        if product_entity:
            product_branch_ids = service.get_product_branch_ids(product_entity)
            if not any(bid in user_branch_ids for bid in product_branch_ids):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="No access to this product",
                )

    return product


@router.post("/products", response_model=ProductOutput, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> ProductOutput:
    """
    Create a new product with branch prices and allergens.

    MANAGER users can only create products for their assigned branches.
    """
    service = _get_service(db)

    # MANAGER branch isolation
    if not is_admin(user):
        _validate_manager_branch_access_for_create(db, body, user)

    try:
        return service.create_full(
            data=body.model_dump(),
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch("/products/{product_id}", response_model=ProductOutput)
def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> ProductOutput:
    """
    Update a product and its branch prices and allergens.

    MANAGER users can only update products available in their assigned branches.
    """
    service = _get_service(db)

    # MANAGER branch isolation
    if not is_admin(user):
        _validate_manager_branch_access_for_update(service, product_id, body, user)

    try:
        return service.update_full(
            product_id=product_id,
            data=body.model_dump(exclude_unset=True),
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> None:
    """
    Soft delete a product. Requires ADMIN or MANAGER role.

    MANAGER users can only delete products available in their assigned branches.
    """
    service = _get_service(db)

    # MANAGER branch isolation
    if not is_admin(user):
        _validate_manager_branch_access_for_delete(service, product_id, user)

    try:
        service.delete_product(
            product_id=product_id,
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )


# =============================================================================
# Private Helpers - MANAGER Branch Access Validation
# =============================================================================


def _validate_manager_branch_access_for_create(
    db: Session,
    body: ProductCreate,
    user: dict,
) -> None:
    """Validate MANAGER has access to branches for product creation."""
    from sqlalchemy import select
    from rest_api.models import Category

    # Validate category's branch access
    category = db.scalar(
        select(Category).where(
            Category.id == body.category_id,
            Category.tenant_id == user["tenant_id"],
        )
    )
    if category:
        validate_branch_access(user, category.branch_id)

    # Validate branch access for prices
    for bp in body.branch_prices:
        validate_branch_access(user, bp.branch_id)


def _validate_manager_branch_access_for_update(
    service: ProductService,
    product_id: int,
    body: ProductUpdate,
    user: dict,
) -> None:
    """Validate MANAGER has access to product for update."""
    product_entity = service.get_entity(product_id, user["tenant_id"])
    if not product_entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    user_branch_ids = user.get("branch_ids", [])
    product_branch_ids = service.get_product_branch_ids(product_entity)
    if not any(bid in user_branch_ids for bid in product_branch_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this product",
        )

    # Validate branch access for new prices
    if body.branch_prices:
        for bp in body.branch_prices:
            validate_branch_access(user, bp.branch_id)


def _validate_manager_branch_access_for_delete(
    service: ProductService,
    product_id: int,
    user: dict,
) -> None:
    """Validate MANAGER has access to product for deletion."""
    product_entity = service.get_entity(product_id, user["tenant_id"])
    if not product_entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    user_branch_ids = user.get("branch_ids", [])
    product_branch_ids = service.get_product_branch_ids(product_entity)
    if not any(bid in user_branch_ids for bid in product_branch_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this product",
        )
