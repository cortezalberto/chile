"""
Catalogs router for cooking methods, flavors, and textures (Phase 3 - Canonical Product Model).
Read-only endpoints for global catalogs used in product configuration.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select

from rest_api.db import get_db
from rest_api.models import CookingMethod, FlavorProfile, TextureProfile
from shared.auth import current_user_context as current_user


router = APIRouter(prefix="/api/admin/catalogs", tags=["catalogs"])


# =============================================================================
# Pydantic Schemas
# =============================================================================


class CookingMethodOutput(BaseModel):
    id: int
    name: str
    description: str | None = None
    icon: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class FlavorProfileOutput(BaseModel):
    id: int
    name: str
    description: str | None = None
    icon: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class TextureProfileOutput(BaseModel):
    id: int
    name: str
    description: str | None = None
    icon: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


# =============================================================================
# Cooking Method Endpoints
# =============================================================================


@router.get("/cooking-methods", response_model=list[CookingMethodOutput])
def list_cooking_methods(
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[CookingMethodOutput]:
    """
    List all cooking methods.
    Global catalog - same for all tenants.
    """
    methods = db.execute(
        select(CookingMethod)
        .where(CookingMethod.is_active == True)
        .order_by(CookingMethod.name)
    ).scalars().all()
    return [CookingMethodOutput.model_validate(m) for m in methods]


# =============================================================================
# Flavor Profile Endpoints
# =============================================================================


@router.get("/flavor-profiles", response_model=list[FlavorProfileOutput])
def list_flavor_profiles(
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[FlavorProfileOutput]:
    """
    List all flavor profiles.
    Global catalog - same for all tenants.
    """
    profiles = db.execute(
        select(FlavorProfile)
        .where(FlavorProfile.is_active == True)
        .order_by(FlavorProfile.name)
    ).scalars().all()
    return [FlavorProfileOutput.model_validate(p) for p in profiles]


# =============================================================================
# Texture Profile Endpoints
# =============================================================================


@router.get("/texture-profiles", response_model=list[TextureProfileOutput])
def list_texture_profiles(
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[TextureProfileOutput]:
    """
    List all texture profiles.
    Global catalog - same for all tenants.
    """
    profiles = db.execute(
        select(TextureProfile)
        .where(TextureProfile.is_active == True)
        .order_by(TextureProfile.name)
    ).scalars().all()
    return [TextureProfileOutput.model_validate(p) for p in profiles]
