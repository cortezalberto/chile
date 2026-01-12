"""
Promotions router for Dashboard management operations.
Requires JWT authentication with appropriate roles.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from rest_api.db import get_db
from rest_api.models import (
    Promotion,
    PromotionBranch,
    PromotionItem,
    Branch,
    Product,
)
from rest_api.services.soft_delete_service import (
    soft_delete,
    set_created_by,
    set_updated_by,
)
from shared.auth import current_user_context as current_user


router = APIRouter(prefix="/api/admin/promotions", tags=["promotions"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class PromotionItemInput(BaseModel):
    product_id: int
    quantity: int = 1


class PromotionItemOutput(BaseModel):
    product_id: int
    quantity: int

    class Config:
        from_attributes = True


class PromotionOutput(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str | None = None
    price_cents: int
    image: str | None = None
    start_date: str
    end_date: str
    start_time: str
    end_time: str
    promotion_type_id: str | None = None
    branch_ids: list[int] = []
    items: list[PromotionItemOutput] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PromotionCreate(BaseModel):
    name: str
    description: str | None = None
    price_cents: int
    image: str | None = None
    start_date: str
    end_date: str
    start_time: str = "00:00"
    end_time: str = "23:59"
    promotion_type_id: str | None = None
    branch_ids: list[int] = []
    items: list[PromotionItemInput] = []
    is_active: bool = True


class PromotionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    price_cents: int | None = None
    image: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    promotion_type_id: str | None = None
    branch_ids: list[int] | None = None
    items: list[PromotionItemInput] | None = None
    is_active: bool | None = None


# =============================================================================
# Helper Functions
# =============================================================================


def _build_promotion_output(promotion: Promotion, db: Session) -> PromotionOutput:
    """Build PromotionOutput with branch_ids and items."""
    # Get branch IDs
    branch_relations = db.execute(
        select(PromotionBranch).where(PromotionBranch.promotion_id == promotion.id)
    ).scalars().all()
    branch_ids = [pb.branch_id for pb in branch_relations]

    # Get items
    item_relations = db.execute(
        select(PromotionItem).where(PromotionItem.promotion_id == promotion.id)
    ).scalars().all()
    items = [
        PromotionItemOutput(product_id=pi.product_id, quantity=pi.quantity)
        for pi in item_relations
    ]

    return PromotionOutput(
        id=promotion.id,
        tenant_id=promotion.tenant_id,
        name=promotion.name,
        description=promotion.description,
        price_cents=promotion.price_cents,
        image=promotion.image,
        start_date=promotion.start_date,
        end_date=promotion.end_date,
        start_time=promotion.start_time,
        end_time=promotion.end_time,
        promotion_type_id=promotion.promotion_type_id,
        branch_ids=branch_ids,
        items=items,
        is_active=promotion.is_active,
        created_at=promotion.created_at,
        updated_at=promotion.updated_at,
    )


# =============================================================================
# Promotion Endpoints
# =============================================================================


@router.get("", response_model=list[PromotionOutput])
def list_promotions(
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[PromotionOutput]:
    """List promotions, optionally filtered by branch."""
    query = select(Promotion).where(Promotion.tenant_id == user["tenant_id"])

    # Filter by is_active unless include_deleted is True
    if not include_deleted:
        query = query.where(Promotion.is_active == True)

    if branch_id:
        # Filter to promotions available in this branch
        query = query.join(PromotionBranch).where(PromotionBranch.branch_id == branch_id)

    promotions = db.execute(query.order_by(Promotion.name)).scalars().all()
    return [_build_promotion_output(p, db) for p in promotions]


@router.get("/{promotion_id}", response_model=PromotionOutput)
def get_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> PromotionOutput:
    """Get a specific promotion with branch_ids and items."""
    promotion = db.scalar(
        select(Promotion).where(
            Promotion.id == promotion_id,
            Promotion.tenant_id == user["tenant_id"],
            Promotion.is_active == True,
        )
    )
    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )
    return _build_promotion_output(promotion, db)


@router.post("", response_model=PromotionOutput, status_code=status.HTTP_201_CREATED)
def create_promotion(
    body: PromotionCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> PromotionOutput:
    """Create a new promotion with branch associations and items."""
    # Verify all branches belong to tenant
    for branch_id in body.branch_ids:
        branch = db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.tenant_id == user["tenant_id"],
            )
        )
        if not branch:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid branch_id: {branch_id}",
            )

    # Verify all products belong to tenant
    for item in body.items:
        product = db.scalar(
            select(Product).where(
                Product.id == item.product_id,
                Product.tenant_id == user["tenant_id"],
            )
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid product_id: {item.product_id}",
            )

    # Create promotion
    promotion = Promotion(
        tenant_id=user["tenant_id"],
        name=body.name,
        description=body.description,
        price_cents=body.price_cents,
        image=body.image,
        start_date=body.start_date,
        end_date=body.end_date,
        start_time=body.start_time,
        end_time=body.end_time,
        promotion_type_id=body.promotion_type_id,
        is_active=body.is_active,
    )
    # Set audit fields
    set_created_by(promotion, user.get("user_id"), user.get("email", ""))
    db.add(promotion)
    db.flush()  # Get promotion ID

    # Create branch associations
    for branch_id in body.branch_ids:
        pb = PromotionBranch(
            tenant_id=user["tenant_id"],
            promotion_id=promotion.id,
            branch_id=branch_id,
        )
        db.add(pb)

    # Create items
    for item in body.items:
        pi = PromotionItem(
            tenant_id=user["tenant_id"],
            promotion_id=promotion.id,
            product_id=item.product_id,
            quantity=item.quantity,
        )
        db.add(pi)

    db.commit()
    db.refresh(promotion)
    return _build_promotion_output(promotion, db)


@router.patch("/{promotion_id}", response_model=PromotionOutput)
def update_promotion(
    promotion_id: int,
    body: PromotionUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> PromotionOutput:
    """Update a promotion and its branch associations and items."""
    promotion = db.scalar(
        select(Promotion).where(
            Promotion.id == promotion_id,
            Promotion.tenant_id == user["tenant_id"],
            Promotion.is_active == True,
        )
    )
    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Set audit fields
    set_updated_by(promotion, user.get("user_id"), user.get("email", ""))

    # Handle branch_ids separately
    branch_ids = update_data.pop("branch_ids", None)

    # Handle items separately
    items = update_data.pop("items", None)

    # Update basic fields
    for key, value in update_data.items():
        setattr(promotion, key, value)

    # Update branch associations if provided
    if branch_ids is not None:
        # Verify all branches belong to tenant
        for branch_id in branch_ids:
            branch = db.scalar(
                select(Branch).where(
                    Branch.id == branch_id,
                    Branch.tenant_id == user["tenant_id"],
                )
            )
            if not branch:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid branch_id: {branch_id}",
                )

        # Delete existing branch associations
        db.execute(
            PromotionBranch.__table__.delete().where(
                PromotionBranch.promotion_id == promotion_id
            )
        )

        # Create new branch associations
        for branch_id in branch_ids:
            pb = PromotionBranch(
                tenant_id=user["tenant_id"],
                promotion_id=promotion_id,
                branch_id=branch_id,
            )
            db.add(pb)

    # Update items if provided
    if items is not None:
        # Verify all products belong to tenant
        for item in items:
            product = db.scalar(
                select(Product).where(
                    Product.id == item.product_id,
                    Product.tenant_id == user["tenant_id"],
                )
            )
            if not product:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid product_id: {item.product_id}",
                )

        # Delete existing items
        db.execute(
            PromotionItem.__table__.delete().where(
                PromotionItem.promotion_id == promotion_id
            )
        )

        # Create new items
        for item in items:
            pi = PromotionItem(
                tenant_id=user["tenant_id"],
                promotion_id=promotion_id,
                product_id=item.product_id,
                quantity=item.quantity,
            )
            db.add(pi)

    db.commit()
    db.refresh(promotion)
    return _build_promotion_output(promotion, db)


@router.delete("/{promotion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a promotion. Branch associations and items remain intact. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    promotion = db.scalar(
        select(Promotion).where(
            Promotion.id == promotion_id,
            Promotion.tenant_id == user["tenant_id"],
            Promotion.is_active == True,
        )
    )
    if not promotion:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )

    # Soft delete - no cascade needed, just mark as inactive
    soft_delete(db, promotion, user.get("user_id"), user.get("email", ""))
