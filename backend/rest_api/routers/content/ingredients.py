"""
Ingredients router for managing product ingredients (Phase 1 - Canonical Product Model).
CRUD operations for IngredientGroup, Ingredient, and SubIngredient.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select

from shared.infrastructure.db import get_db
from rest_api.models import IngredientGroup, Ingredient, SubIngredient
from shared.security.auth import current_user_context as current_user
from rest_api.services.crud.soft_delete import (
    soft_delete,
    set_created_by,
    set_updated_by,
)
from rest_api.routers._common.base import get_user_id, get_user_email
from shared.config.logging import rest_api_logger as logger


router = APIRouter(prefix="/api/admin/ingredients", tags=["ingredients"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class IngredientGroupOutput(BaseModel):
    id: int
    name: str
    description: str | None = None
    icon: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class IngredientGroupCreate(BaseModel):
    name: str
    description: str | None = None
    icon: str | None = None


class SubIngredientOutput(BaseModel):
    id: int
    ingredient_id: int
    name: str
    description: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class SubIngredientCreate(BaseModel):
    name: str
    description: str | None = None


class IngredientOutput(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str | None = None
    group_id: int | None = None
    group_name: str | None = None
    is_processed: bool
    is_active: bool
    created_at: datetime
    sub_ingredients: list[SubIngredientOutput] = []

    class Config:
        from_attributes = True


class IngredientCreate(BaseModel):
    name: str
    description: str | None = None
    group_id: int | None = None
    is_processed: bool = False


class IngredientUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    group_id: int | None = None
    is_processed: bool | None = None
    is_active: bool | None = None


# =============================================================================
# Ingredient Group Endpoints (Global catalogs)
# =============================================================================


@router.get("/groups", response_model=list[IngredientGroupOutput])
def list_ingredient_groups(
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[IngredientGroupOutput]:
    """List all ingredient groups (global catalog)."""
    groups = db.execute(
        select(IngredientGroup)
        .where(IngredientGroup.is_active.is_(True))
        .order_by(IngredientGroup.name)
    ).scalars().all()
    return [IngredientGroupOutput.model_validate(g) for g in groups]


@router.post("/groups", response_model=IngredientGroupOutput, status_code=status.HTTP_201_CREATED)
def create_ingredient_group(
    body: IngredientGroupCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> IngredientGroupOutput:
    """Create a new ingredient group (ADMIN only)."""
    if "ADMIN" not in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN can create ingredient groups",
        )

    # Check for duplicate name
    existing = db.scalar(
        select(IngredientGroup).where(
            IngredientGroup.name == body.name.lower(),
            IngredientGroup.is_active.is_(True),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ingredient group '{body.name}' already exists",
        )

    group = IngredientGroup(
        name=body.name.lower(),
        description=body.description,
        icon=body.icon,
    )
    set_created_by(group, get_user_id(user), get_user_email(user))
    db.add(group)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(group)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create ingredient group", name=body.name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ingredient group - please try again",
        )
    return IngredientGroupOutput.model_validate(group)


# =============================================================================
# Ingredient Endpoints
# =============================================================================


def _build_ingredient_output(ingredient: Ingredient) -> IngredientOutput:
    """Build IngredientOutput with sub-ingredients and group name."""
    sub_ingredients = [
        SubIngredientOutput.model_validate(sub)
        for sub in (ingredient.sub_ingredients or [])
        if sub.is_active
    ]

    return IngredientOutput(
        id=ingredient.id,
        tenant_id=ingredient.tenant_id,
        name=ingredient.name,
        description=ingredient.description,
        group_id=ingredient.group_id,
        group_name=ingredient.group.name if ingredient.group else None,
        is_processed=ingredient.is_processed,
        is_active=ingredient.is_active,
        created_at=ingredient.created_at,
        sub_ingredients=sub_ingredients,
    )


@router.get("", response_model=list[IngredientOutput])
def list_ingredients(
    group_id: int | None = None,
    include_deleted: bool = False,
    # MED-03 FIX: Added pagination for large ingredient lists
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[IngredientOutput]:
    """List ingredients for the tenant, optionally filtered by group.

    Supports pagination via limit/offset parameters (default: 100, max: 500).
    """
    # Validate pagination limits
    limit = min(max(1, limit), 500)  # Clamp between 1 and 500
    offset = max(0, offset)
    query = select(Ingredient).options(
        selectinload(Ingredient.group),
        selectinload(Ingredient.sub_ingredients),
    ).where(Ingredient.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Ingredient.is_active.is_(True))

    if group_id:
        query = query.where(Ingredient.group_id == group_id)

    # MED-03 FIX: Apply pagination
    query = query.order_by(Ingredient.name).offset(offset).limit(limit)
    ingredients = db.execute(query).scalars().all()
    return [_build_ingredient_output(ing) for ing in ingredients]


@router.get("/{ingredient_id}", response_model=IngredientOutput)
def get_ingredient(
    ingredient_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> IngredientOutput:
    """Get a specific ingredient with sub-ingredients."""
    ingredient = db.scalar(
        select(Ingredient).options(
            selectinload(Ingredient.group),
            selectinload(Ingredient.sub_ingredients),
        ).where(
            Ingredient.id == ingredient_id,
            Ingredient.tenant_id == user["tenant_id"],
            Ingredient.is_active.is_(True),
        )
    )
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found",
        )
    return _build_ingredient_output(ingredient)


@router.post("", response_model=IngredientOutput, status_code=status.HTTP_201_CREATED)
def create_ingredient(
    body: IngredientCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> IngredientOutput:
    """Create a new ingredient."""
    # Verify group exists if provided
    if body.group_id:
        group = db.scalar(
            select(IngredientGroup).where(
                IngredientGroup.id == body.group_id,
                IngredientGroup.is_active.is_(True),
            )
        )
        if not group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid group_id",
            )

    # Check for duplicate name within tenant
    existing = db.scalar(
        select(Ingredient).where(
            Ingredient.tenant_id == user["tenant_id"],
            Ingredient.name == body.name,
            Ingredient.is_active.is_(True),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ingredient '{body.name}' already exists",
        )

    ingredient = Ingredient(
        tenant_id=user["tenant_id"],
        name=body.name,
        description=body.description,
        group_id=body.group_id,
        is_processed=body.is_processed,
    )
    set_created_by(ingredient, get_user_id(user), get_user_email(user))
    db.add(ingredient)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(ingredient)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create ingredient", name=body.name, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create ingredient - please try again",
        )

    # Load relationships for response
    ingredient = db.scalar(
        select(Ingredient).options(
            selectinload(Ingredient.group),
            selectinload(Ingredient.sub_ingredients),
        ).where(Ingredient.id == ingredient.id)
    )
    return _build_ingredient_output(ingredient)


@router.patch("/{ingredient_id}", response_model=IngredientOutput)
def update_ingredient(
    ingredient_id: int,
    body: IngredientUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> IngredientOutput:
    """Update an ingredient."""
    ingredient = db.scalar(
        select(Ingredient).where(
            Ingredient.id == ingredient_id,
            Ingredient.tenant_id == user["tenant_id"],
            Ingredient.is_active.is_(True),
        )
    )
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Verify group exists if being updated
    if "group_id" in update_data and update_data["group_id"]:
        group = db.scalar(
            select(IngredientGroup).where(
                IngredientGroup.id == update_data["group_id"],
                IngredientGroup.is_active.is_(True),
            )
        )
        if not group:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid group_id",
            )

    for key, value in update_data.items():
        setattr(ingredient, key, value)

    set_updated_by(ingredient, get_user_id(user), get_user_email(user))

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(ingredient)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update ingredient", ingredient_id=ingredient_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update ingredient - please try again",
        )

    # Load relationships for response
    ingredient = db.scalar(
        select(Ingredient).options(
            selectinload(Ingredient.group),
            selectinload(Ingredient.sub_ingredients),
        ).where(Ingredient.id == ingredient.id)
    )
    return _build_ingredient_output(ingredient)


@router.delete("/{ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ingredient(
    ingredient_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete an ingredient (ADMIN only)."""
    if "ADMIN" not in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN can delete ingredients",
        )

    ingredient = db.scalar(
        select(Ingredient).where(
            Ingredient.id == ingredient_id,
            Ingredient.tenant_id == user["tenant_id"],
            Ingredient.is_active.is_(True),
        )
    )
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found",
        )

    soft_delete(db, ingredient, get_user_id(user), get_user_email(user))

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to delete ingredient", ingredient_id=ingredient_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete ingredient - please try again",
        )


# =============================================================================
# Sub-Ingredient Endpoints
# =============================================================================


@router.post("/{ingredient_id}/sub", response_model=SubIngredientOutput, status_code=status.HTTP_201_CREATED)
def create_sub_ingredient(
    ingredient_id: int,
    body: SubIngredientCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> SubIngredientOutput:
    """Add a sub-ingredient to a processed ingredient."""
    ingredient = db.scalar(
        select(Ingredient).where(
            Ingredient.id == ingredient_id,
            Ingredient.tenant_id == user["tenant_id"],
            Ingredient.is_active.is_(True),
        )
    )
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found",
        )

    if not ingredient.is_processed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sub-ingredients can only be added to processed ingredients",
        )

    # Check for duplicate name within ingredient
    existing = db.scalar(
        select(SubIngredient).where(
            SubIngredient.ingredient_id == ingredient_id,
            SubIngredient.name == body.name,
            SubIngredient.is_active.is_(True),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sub-ingredient '{body.name}' already exists for this ingredient",
        )

    sub_ingredient = SubIngredient(
        ingredient_id=ingredient_id,
        name=body.name,
        description=body.description,
    )
    set_created_by(sub_ingredient, get_user_id(user), get_user_email(user))
    db.add(sub_ingredient)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(sub_ingredient)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create sub-ingredient", ingredient_id=ingredient_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create sub-ingredient - please try again",
        )
    return SubIngredientOutput.model_validate(sub_ingredient)


@router.delete("/{ingredient_id}/sub/{sub_ingredient_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sub_ingredient(
    ingredient_id: int,
    sub_ingredient_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a sub-ingredient."""
    # Verify ingredient belongs to tenant
    ingredient = db.scalar(
        select(Ingredient).where(
            Ingredient.id == ingredient_id,
            Ingredient.tenant_id == user["tenant_id"],
            Ingredient.is_active.is_(True),
        )
    )
    if not ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingredient not found",
        )

    sub_ingredient = db.scalar(
        select(SubIngredient).where(
            SubIngredient.id == sub_ingredient_id,
            SubIngredient.ingredient_id == ingredient_id,
            SubIngredient.is_active.is_(True),
        )
    )
    if not sub_ingredient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sub-ingredient not found",
        )

    soft_delete(db, sub_ingredient, get_user_id(user), get_user_email(user))

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("Failed to delete sub-ingredient", sub_ingredient_id=sub_ingredient_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete sub-ingredient - please try again",
        )
