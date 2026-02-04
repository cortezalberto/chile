"""
Subcategory management endpoints.

PERF-BGTASK-01: Uses FastAPI BackgroundTasks for event publishing.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from rest_api.routers.admin._base import (
    Depends, Session, select, func,
    get_db, current_user, Subcategory, Category,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin,
)
from shared.utils.validators import validate_image_url
from shared.utils.admin_schemas import SubcategoryOutput, SubcategoryCreate, SubcategoryUpdate
from shared.config.logging import rest_api_logger as logger


router = APIRouter(tags=["admin-subcategories"])


@router.get("/subcategories", response_model=list[SubcategoryOutput])
def list_subcategories(
    category_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[SubcategoryOutput]:
    """List subcategories, optionally filtered by category."""
    query = select(Subcategory).where(Subcategory.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Subcategory.is_active.is_(True))

    if category_id:
        query = query.where(Subcategory.category_id == category_id)

    subcategories = db.execute(query.order_by(Subcategory.order)).scalars().all()
    return [SubcategoryOutput.model_validate(s) for s in subcategories]


@router.get("/subcategories/{subcategory_id}", response_model=SubcategoryOutput)
def get_subcategory(
    subcategory_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> SubcategoryOutput:
    """Get a specific subcategory."""
    subcategory = db.scalar(
        select(Subcategory).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == user["tenant_id"],
            Subcategory.is_active.is_(True),
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )
    return SubcategoryOutput.model_validate(subcategory)


@router.post("/subcategories", response_model=SubcategoryOutput, status_code=status.HTTP_201_CREATED)
def create_subcategory(
    body: SubcategoryCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> SubcategoryOutput:
    """Create a new subcategory. Requires ADMIN role."""
    # Verify category belongs to tenant
    category = db.scalar(
        select(Category).where(
            Category.id == body.category_id,
            Category.tenant_id == user["tenant_id"],
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid category_id",
        )

    # HIGH-04 FIX: Validate image URL to prevent SSRF attacks
    validated_image = None
    if body.image:
        try:
            validated_image = validate_image_url(body.image)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    # Auto-calculate order if not provided
    order = body.order
    if order is None:
        max_order = db.scalar(
            select(func.max(Subcategory.order))
            .where(Subcategory.category_id == body.category_id)
        ) or 0
        order = max_order + 1

    subcategory = Subcategory(
        tenant_id=user["tenant_id"],
        category_id=body.category_id,
        name=body.name,
        image=validated_image,  # HIGH-04 FIX: Use validated image URL
        order=order,
        is_active=body.is_active,
    )
    set_created_by(subcategory, get_user_id(user), get_user_email(user))
    db.add(subcategory)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(subcategory)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create subcategory", category_id=body.category_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subcategory - please try again",
        )
    return SubcategoryOutput.model_validate(subcategory)


@router.patch("/subcategories/{subcategory_id}", response_model=SubcategoryOutput)
def update_subcategory(
    subcategory_id: int,
    body: SubcategoryUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> SubcategoryOutput:
    """Update a subcategory. Requires ADMIN role."""
    subcategory = db.scalar(
        select(Subcategory).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == user["tenant_id"],
            Subcategory.is_active.is_(True),
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # HIGH-04 FIX: Validate image URL if being updated
    if "image" in update_data and update_data["image"]:
        try:
            update_data["image"] = validate_image_url(update_data["image"])
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )

    for key, value in update_data.items():
        setattr(subcategory, key, value)

    set_updated_by(subcategory, get_user_id(user), get_user_email(user))

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(subcategory)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update subcategory", subcategory_id=subcategory_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update subcategory - please try again",
        )
    return SubcategoryOutput.model_validate(subcategory)


@router.delete("/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subcategory(
    subcategory_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete a subcategory. Requires ADMIN role.

    PERF-BGTASK-01: Uses BackgroundTasks for async event publishing.
    """
    subcategory = db.scalar(
        select(Subcategory).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == user["tenant_id"],
            Subcategory.is_active.is_(True),
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )

    # Get category to find branch_id
    category = db.scalar(
        select(Category).where(Category.id == subcategory.category_id)
    )
    branch_id = category.branch_id if category else None

    subcategory_name = subcategory.name
    tenant_id = subcategory.tenant_id

    soft_delete(db, subcategory, get_user_id(user), get_user_email(user))

    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="subcategory",
        entity_id=subcategory_id,
        entity_name=subcategory_name,
        branch_id=branch_id,
        actor_user_id=get_user_id(user),
        background_tasks=background_tasks,
    )
