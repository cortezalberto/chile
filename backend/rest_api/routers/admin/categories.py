"""
Category management endpoints.
"""

from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select, func,
    get_db, current_user, Category, Branch,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin,
)
from rest_api.routers.admin_schemas import CategoryOutput, CategoryCreate, CategoryUpdate


router = APIRouter(tags=["admin-categories"])


@router.get("/categories", response_model=list[CategoryOutput])
def list_categories(
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[CategoryOutput]:
    """List categories, optionally filtered by branch."""
    query = select(Category).where(Category.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Category.is_active == True)

    if branch_id:
        query = query.where(Category.branch_id == branch_id)

    categories = db.execute(query.order_by(Category.order)).scalars().all()
    return [CategoryOutput.model_validate(c) for c in categories]


@router.get("/categories/{category_id}", response_model=CategoryOutput)
def get_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> CategoryOutput:
    """Get a specific category."""
    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.tenant_id == user["tenant_id"],
            Category.is_active == True,
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )
    return CategoryOutput.model_validate(category)


@router.post("/categories", response_model=CategoryOutput, status_code=status.HTTP_201_CREATED)
def create_category(
    body: CategoryCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> CategoryOutput:
    """Create a new category. Requires ADMIN role."""
    # Verify branch belongs to tenant
    branch = db.scalar(
        select(Branch).where(
            Branch.id == body.branch_id,
            Branch.tenant_id == user["tenant_id"],
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid branch_id",
        )

    # Auto-calculate order if not provided
    order = body.order
    if order is None:
        max_order = db.scalar(
            select(func.max(Category.order))
            .where(Category.branch_id == body.branch_id)
        ) or 0
        order = max_order + 1

    category = Category(
        tenant_id=user["tenant_id"],
        branch_id=body.branch_id,
        name=body.name,
        icon=body.icon,
        image=body.image,
        order=order,
        is_active=body.is_active,
    )
    set_created_by(category, get_user_id(user), get_user_email(user))
    db.add(category)
    db.commit()
    db.refresh(category)
    return CategoryOutput.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryOutput)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> CategoryOutput:
    """Update a category. Requires ADMIN role."""
    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.tenant_id == user["tenant_id"],
            Category.is_active == True,
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(category, key, value)

    set_updated_by(category, get_user_id(user), get_user_email(user))

    db.commit()
    db.refresh(category)
    return CategoryOutput.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete a category. Requires ADMIN role."""
    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.tenant_id == user["tenant_id"],
            Category.is_active == True,
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    category_name = category.name
    tenant_id = category.tenant_id
    branch_id = category.branch_id

    soft_delete(db, category, get_user_id(user), get_user_email(user))

    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="category",
        entity_id=category_id,
        entity_name=category_name,
        branch_id=branch_id,
        actor_user_id=get_user_id(user),
    )
