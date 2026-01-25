"""
Promotions router - Clean Architecture refactor.

CLEAN-ARCH: Thin router that delegates to PromotionService.
All business logic is in rest_api/services/domain/promotion_service.py.

Reduced from 499 lines to ~150 lines (70% reduction).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from shared.infrastructure.db import get_db
from shared.security.auth import current_user_context as current_user
from shared.utils.exceptions import NotFoundError, ValidationError
from rest_api.routers._common.base import get_user_id, get_user_email
from rest_api.services.domain import PromotionService
from rest_api.services.domain.promotion_service import PromotionOutput
from shared.config.constants import Roles


router = APIRouter(prefix="/api/admin/promotions", tags=["promotions"])


# =============================================================================
# Input Schemas (kept in router for API contract)
# =============================================================================


class PromotionItemInput(BaseModel):
    product_id: int
    quantity: int = 1


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
# Endpoints
# =============================================================================


def _get_service(db: Session) -> PromotionService:
    """Get PromotionService instance."""
    return PromotionService(db)


@router.get("", response_model=list[PromotionOutput])
def list_promotions(
    branch_id: int | None = None,
    include_deleted: bool = False,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[PromotionOutput]:
    """
    List promotions, optionally filtered by branch.

    Supports pagination via limit/offset parameters (default: 50, max: 200).
    """
    service = _get_service(db)

    return service.list_all(
        tenant_id=user["tenant_id"],
        branch_id=branch_id,
        include_inactive=include_deleted,
        limit=limit,
        offset=offset,
    )


@router.get("/{promotion_id}", response_model=PromotionOutput)
def get_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> PromotionOutput:
    """Get a specific promotion with branch_ids and items."""
    service = _get_service(db)

    try:
        return service.get_by_id(
            promotion_id=promotion_id,
            tenant_id=user["tenant_id"],
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )


@router.post("", response_model=PromotionOutput, status_code=status.HTTP_201_CREATED)
def create_promotion(
    body: PromotionCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> PromotionOutput:
    """Create a new promotion with branch associations and items."""
    service = _get_service(db)

    # Convert items to dict format
    data = body.model_dump()
    data["items"] = [{"product_id": i.product_id, "quantity": i.quantity} for i in body.items]

    try:
        return service.create_full(
            data=data,
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.patch("/{promotion_id}", response_model=PromotionOutput)
def update_promotion(
    promotion_id: int,
    body: PromotionUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> PromotionOutput:
    """Update a promotion and its branch associations and items."""
    service = _get_service(db)

    # Convert items to dict format if provided
    data = body.model_dump(exclude_unset=True)
    if "items" in data and data["items"] is not None:
        data["items"] = [{"product_id": i["product_id"], "quantity": i["quantity"]} for i in data["items"]]

    try:
        return service.update_full(
            promotion_id=promotion_id,
            data=data,
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.delete("/{promotion_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_promotion(
    promotion_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a promotion. Requires ADMIN role."""
    if Roles.ADMIN not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    service = _get_service(db)

    try:
        service.delete_promotion(
            promotion_id=promotion_id,
            tenant_id=user["tenant_id"],
            user_id=get_user_id(user),
            user_email=get_user_email(user),
        )
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Promotion not found",
        )
