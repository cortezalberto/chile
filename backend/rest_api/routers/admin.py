"""
Admin router for Dashboard management operations.
Requires JWT authentication with appropriate roles.
"""

from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import re

from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select, func, or_

from rest_api.db import get_db
from rest_api.models import (
    Tenant,
    Branch,
    BranchSector,
    Category,
    Subcategory,
    Product,
    BranchProduct,
    Allergen,
    ProductAllergen,
    Table,
    User,
    UserBranchRole,
    Round,
    RoundItem,
    TableSession,
    Diner,
    AuditLog,
    BranchCategoryExclusion,
    BranchSubcategoryExclusion,
    WaiterSectorAssignment,
)
from shared.auth import current_user_context as current_user
from rest_api.services.audit import log_create, log_update, log_delete, serialize_model
from rest_api.services.admin_events import publish_entity_deleted
from rest_api.services.soft_delete_service import (
    soft_delete,
    restore_entity,
    set_created_by,
    set_updated_by,
    get_model_class,
    find_active_entity,
    find_deleted_entity,
    filter_active,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])


# =============================================================================
# Pydantic Schemas for Admin Operations
# =============================================================================


class TenantOutput(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None = None
    logo: str | None = None
    theme_color: str
    created_at: datetime

    class Config:
        from_attributes = True


class TenantUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    logo: str | None = None
    theme_color: str | None = None


class BranchOutput(BaseModel):
    id: int
    tenant_id: int
    name: str
    slug: str
    address: str | None = None
    phone: str | None = None
    timezone: str
    opening_time: str | None = None
    closing_time: str | None = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BranchCreate(BaseModel):
    name: str
    slug: str
    address: str | None = None
    phone: str | None = None
    timezone: str = "America/Argentina/Mendoza"
    opening_time: str | None = None
    closing_time: str | None = None
    is_active: bool = True


class BranchUpdate(BaseModel):
    name: str | None = None
    slug: str | None = None
    address: str | None = None
    phone: str | None = None
    timezone: str | None = None
    opening_time: str | None = None
    closing_time: str | None = None
    is_active: bool | None = None


class CategoryOutput(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    name: str
    icon: str | None = None
    image: str | None = None
    order: int
    is_active: bool

    class Config:
        from_attributes = True


class CategoryCreate(BaseModel):
    branch_id: int
    name: str
    icon: str | None = None
    image: str | None = None
    order: int | None = None
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    image: str | None = None
    order: int | None = None
    is_active: bool | None = None


class SubcategoryOutput(BaseModel):
    id: int
    tenant_id: int
    category_id: int
    name: str
    image: str | None = None
    order: int
    is_active: bool

    class Config:
        from_attributes = True


class SubcategoryCreate(BaseModel):
    category_id: int
    name: str
    image: str | None = None
    order: int | None = None
    is_active: bool = True


class SubcategoryUpdate(BaseModel):
    name: str | None = None
    image: str | None = None
    order: int | None = None
    is_active: bool | None = None


class BranchPriceOutput(BaseModel):
    branch_id: int
    price_cents: int
    is_available: bool


class ProductOutput(BaseModel):
    id: int
    tenant_id: int
    name: str
    description: str | None = None
    image: str | None = None
    category_id: int
    subcategory_id: int | None = None
    featured: bool
    popular: bool
    badge: str | None = None
    seal: str | None = None
    # Old format (backward compatible) - will be deprecated
    allergen_ids: list[int] = []
    # New format with presence types (Phase 0)
    allergens: list["AllergenPresenceOutput"] = []
    is_active: bool
    created_at: datetime
    branch_prices: list[BranchPriceOutput] = []

    class Config:
        from_attributes = True


class BranchPriceInput(BaseModel):
    branch_id: int
    price_cents: int
    is_available: bool = True


# =============================================================================
# Allergen Presence Types (Phase 0 - Canonical Model)
# =============================================================================


class AllergenPresenceInput(BaseModel):
    """Input for allergen with presence type."""
    allergen_id: int
    presence_type: str = "contains"  # contains, may_contain, free_from


class AllergenPresenceOutput(BaseModel):
    """Output for allergen with presence type and details."""
    allergen_id: int
    allergen_name: str
    allergen_icon: str | None = None
    presence_type: str  # contains, may_contain, free_from


class ProductCreate(BaseModel):
    name: str
    description: str | None = None
    image: str | None = None
    category_id: int
    subcategory_id: int | None = None
    featured: bool = False
    popular: bool = False
    badge: str | None = None
    seal: str | None = None
    # Old format (backward compatible) - will be deprecated
    allergen_ids: list[int] = []
    # New format with presence types (Phase 0)
    allergens: list[AllergenPresenceInput] = []
    is_active: bool = True
    branch_prices: list[BranchPriceInput] = []


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    image: str | None = None
    category_id: int | None = None
    subcategory_id: int | None = None
    featured: bool | None = None
    popular: bool | None = None
    badge: str | None = None
    seal: str | None = None
    # Old format (backward compatible) - will be deprecated
    allergen_ids: list[int] | None = None
    # New format with presence types (Phase 0)
    allergens: list[AllergenPresenceInput] | None = None
    is_active: bool | None = None
    branch_prices: list[BranchPriceInput] | None = None


class AllergenOutput(BaseModel):
    id: int
    tenant_id: int
    name: str
    icon: str | None = None
    description: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class AllergenCreate(BaseModel):
    name: str
    icon: str | None = None
    description: str | None = None
    is_active: bool = True


class AllergenUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    description: str | None = None
    is_active: bool | None = None


class TableOutput(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    code: str
    capacity: int
    sector: str | None = None
    status: str
    is_active: bool

    class Config:
        from_attributes = True


class TableCreate(BaseModel):
    branch_id: int
    code: str
    capacity: int = 4
    sector: str | None = None
    is_active: bool = True


class TableUpdate(BaseModel):
    code: str | None = None
    capacity: int | None = None
    sector: str | None = None
    status: str | None = None
    is_active: bool | None = None


# =============================================================================
# Sector Schemas
# =============================================================================


class BranchSectorOutput(BaseModel):
    id: int
    tenant_id: int
    branch_id: int | None = None
    name: str
    prefix: str
    display_order: int
    is_active: bool
    is_global: bool = False  # Computed field

    class Config:
        from_attributes = True


class BranchSectorCreate(BaseModel):
    branch_id: int | None = None  # None for global sector
    name: str
    prefix: str  # 2-4 uppercase letters for table codes


class BranchSectorUpdate(BaseModel):
    name: str | None = None
    prefix: str | None = None
    display_order: int | None = None
    is_active: bool | None = None


# =============================================================================
# Bulk Table Creation Schemas
# =============================================================================


class TableBulkItem(BaseModel):
    """Single table specification in bulk creation."""
    sector_id: int
    capacity: int  # 1-20 people
    count: int     # Number of tables with this capacity (1-100)


class TableBulkCreate(BaseModel):
    """Bulk table creation request."""
    branch_id: int
    tables: list[TableBulkItem]


class TableBulkResult(BaseModel):
    """Result of bulk table creation."""
    created_count: int
    tables: list[TableOutput]


# =============================================================================
# Waiter Sector Assignment Schemas
# =============================================================================


class WaiterSectorAssignmentOutput(BaseModel):
    """Output schema for waiter-sector assignment."""
    id: int
    tenant_id: int
    branch_id: int
    sector_id: int
    sector_name: str
    sector_prefix: str
    waiter_id: int
    waiter_name: str
    waiter_email: str
    assignment_date: date
    shift: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


class WaiterSectorAssignmentCreate(BaseModel):
    """Create a single waiter-sector assignment."""
    sector_id: int
    waiter_id: int
    assignment_date: date
    shift: str | None = None  # "MORNING", "AFTERNOON", "NIGHT" or None for all day


class WaiterSectorBulkAssignment(BaseModel):
    """Bulk assignment: assign multiple waiters to multiple sectors."""
    branch_id: int
    assignment_date: date
    shift: str | None = None
    assignments: list[dict]  # [{"sector_id": 1, "waiter_ids": [1, 2, 3]}, ...]


class WaiterSectorBulkResult(BaseModel):
    """Result of bulk assignment."""
    created_count: int
    skipped_count: int
    assignments: list[WaiterSectorAssignmentOutput]


class SectorWithWaiters(BaseModel):
    """Sector with its assigned waiters for a given date."""
    sector_id: int
    sector_name: str
    sector_prefix: str
    waiters: list[dict]  # [{"id": 1, "name": "Juan Perez", "email": "..."}, ...]


class BranchAssignmentOverview(BaseModel):
    """Overview of all sector assignments for a branch on a given date."""
    branch_id: int
    branch_name: str
    assignment_date: date
    shift: str | None = None
    sectors: list[SectorWithWaiters]
    unassigned_waiters: list[dict]  # Waiters in the branch not assigned to any sector


class StaffOutput(BaseModel):
    id: int
    tenant_id: int
    email: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    dni: str | None = None
    hire_date: str | None = None
    is_active: bool
    created_at: datetime
    branch_roles: list[dict] = []

    class Config:
        from_attributes = True


class StaffCreate(BaseModel):
    email: str
    password: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    dni: str | None = None
    hire_date: str | None = None
    is_active: bool = True
    branch_roles: list[dict] = []  # [{"branch_id": 1, "role": "WAITER"}]


class StaffUpdate(BaseModel):
    email: str | None = None
    password: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    dni: str | None = None
    hire_date: str | None = None
    is_active: bool | None = None
    branch_roles: list[dict] | None = None


# =============================================================================
# Branch Exclusion Schemas
# =============================================================================


class BranchCategoryExclusionOutput(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    category_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class BranchSubcategoryExclusionOutput(BaseModel):
    id: int
    tenant_id: int
    branch_id: int
    subcategory_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ExclusionCreate(BaseModel):
    """Create an exclusion for category or subcategory."""
    branch_ids: list[int]  # List of branch IDs to exclude from


class ExclusionBulkUpdate(BaseModel):
    """Bulk update exclusions for a category or subcategory."""
    excluded_branch_ids: list[int]  # Complete list of branches where item is excluded


class CategoryExclusionSummary(BaseModel):
    """Summary of category exclusions across branches."""
    category_id: int
    category_name: str
    excluded_branch_ids: list[int]


class SubcategoryExclusionSummary(BaseModel):
    """Summary of subcategory exclusions across branches."""
    subcategory_id: int
    subcategory_name: str
    category_id: int
    category_name: str
    excluded_branch_ids: list[int]


class ExclusionOverview(BaseModel):
    """Complete overview of all exclusions."""
    category_exclusions: list[CategoryExclusionSummary]
    subcategory_exclusions: list[SubcategoryExclusionSummary]


# =============================================================================
# Tenant (Restaurant) Endpoints
# =============================================================================


@router.get("/tenant", response_model=TenantOutput)
def get_tenant(
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TenantOutput:
    """Get current user's tenant (restaurant) information."""
    tenant = db.scalar(select(Tenant).where(Tenant.id == user["tenant_id"]))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )
    return TenantOutput.model_validate(tenant)


@router.patch("/tenant", response_model=TenantOutput)
def update_tenant(
    body: TenantUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TenantOutput:
    """Update tenant information. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    tenant = db.scalar(select(Tenant).where(Tenant.id == user["tenant_id"]))
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(tenant, key, value)

    db.commit()
    db.refresh(tenant)
    return TenantOutput.model_validate(tenant)


# =============================================================================
# Branch Endpoints
# =============================================================================


@router.get("/branches", response_model=list[BranchOutput])
def list_branches(
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[BranchOutput]:
    """List all branches for the user's tenant."""
    query = select(Branch).where(Branch.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Branch.is_active == True)

    branches = db.execute(query.order_by(Branch.name)).scalars().all()
    return [BranchOutput.model_validate(b) for b in branches]


@router.get("/branches/{branch_id}", response_model=BranchOutput)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchOutput:
    """Get a specific branch."""
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )
    return BranchOutput.model_validate(branch)


@router.post("/branches", response_model=BranchOutput, status_code=status.HTTP_201_CREATED)
def create_branch(
    body: BranchCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchOutput:
    """Create a new branch. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    branch = Branch(
        tenant_id=user["tenant_id"],
        **body.model_dump(),
    )
    # Set audit fields
    set_created_by(branch, user.get("user_id"), user.get("email", ""))
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return BranchOutput.model_validate(branch)


@router.patch("/branches/{branch_id}", response_model=BranchOutput)
def update_branch(
    branch_id: int,
    body: BranchUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchOutput:
    """Update a branch. Requires ADMIN or MANAGER role."""
    if "ADMIN" not in user["roles"] and "MANAGER" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(branch, key, value)

    # Set audit fields
    set_updated_by(branch, user.get("user_id"), user.get("email", ""))

    db.commit()
    db.refresh(branch)
    return BranchOutput.model_validate(branch)


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a branch. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active == True,  # Only find active branches
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )

    branch_name = branch.name
    tenant_id = branch.tenant_id

    # Soft delete: set is_active=False with audit trail
    soft_delete(db, branch, user.get("user_id"), user.get("email", ""))

    # Publish delete event (no cascade - children remain active but hidden)
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="branch",
        entity_id=branch_id,
        entity_name=branch_name,
        actor_user_id=user.get("user_id"),
    )


# =============================================================================
# Category Endpoints
# =============================================================================


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

    categories = db.execute(query.order_by(Category.branch_id, Category.order)).scalars().all()
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
    user: dict = Depends(current_user),
) -> CategoryOutput:
    """Create a new category."""
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
    # Set audit fields
    set_created_by(category, user.get("user_id"), user.get("email", ""))
    db.add(category)
    db.commit()
    db.refresh(category)
    return CategoryOutput.model_validate(category)


@router.patch("/categories/{category_id}", response_model=CategoryOutput)
def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> CategoryOutput:
    """Update a category."""
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

    # Set audit fields
    set_updated_by(category, user.get("user_id"), user.get("email", ""))

    db.commit()
    db.refresh(category)
    return CategoryOutput.model_validate(category)


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(
    category_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a category. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.tenant_id == user["tenant_id"],
            Category.is_active == True,  # Only find active categories
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    category_name = category.name
    branch_id = category.branch_id
    tenant_id = category.tenant_id

    # Soft delete: set is_active=False with audit trail
    soft_delete(db, category, user.get("user_id"), user.get("email", ""))

    # Publish delete event (no cascade - children remain active but hidden)
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="category",
        entity_id=category_id,
        entity_name=category_name,
        branch_id=branch_id,
        actor_user_id=user.get("user_id"),
    )


# =============================================================================
# Subcategory Endpoints
# =============================================================================


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
        query = query.where(Subcategory.is_active == True)

    if category_id:
        query = query.where(Subcategory.category_id == category_id)

    subcategories = db.execute(query.order_by(Subcategory.category_id, Subcategory.order)).scalars().all()
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
            Subcategory.is_active == True,
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
    user: dict = Depends(current_user),
) -> SubcategoryOutput:
    """Create a new subcategory."""
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
        image=body.image,
        order=order,
        is_active=body.is_active,
    )
    # Set audit fields
    set_created_by(subcategory, user.get("user_id"), user.get("email", ""))
    db.add(subcategory)
    db.commit()
    db.refresh(subcategory)
    return SubcategoryOutput.model_validate(subcategory)


@router.patch("/subcategories/{subcategory_id}", response_model=SubcategoryOutput)
def update_subcategory(
    subcategory_id: int,
    body: SubcategoryUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> SubcategoryOutput:
    """Update a subcategory."""
    subcategory = db.scalar(
        select(Subcategory).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == user["tenant_id"],
            Subcategory.is_active == True,
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(subcategory, key, value)

    # Set audit fields
    set_updated_by(subcategory, user.get("user_id"), user.get("email", ""))

    db.commit()
    db.refresh(subcategory)
    return SubcategoryOutput.model_validate(subcategory)


@router.delete("/subcategories/{subcategory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_subcategory(
    subcategory_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a subcategory. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    subcategory = db.scalar(
        select(Subcategory).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == user["tenant_id"],
            Subcategory.is_active == True,  # Only find active subcategories
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

    # Soft delete: set is_active=False with audit trail
    soft_delete(db, subcategory, user.get("user_id"), user.get("email", ""))

    # Publish delete event (no cascade - children remain active but hidden)
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="subcategory",
        entity_id=subcategory_id,
        entity_name=subcategory_name,
        branch_id=branch_id,
        actor_user_id=user.get("user_id"),
    )


# =============================================================================
# Product Endpoints
# =============================================================================


def _build_product_output(product: Product, db: Session = None, preloaded_branch_products: list = None) -> ProductOutput:
    """Build ProductOutput with branch prices and allergens.

    Args:
        product: The Product model instance
        db: Database session (only needed if branch_products not preloaded)
        preloaded_branch_products: Pre-fetched BranchProduct list (avoids N+1)
    """
    import json

    # Use preloaded branch_products if available, otherwise query (for single product fetch)
    if preloaded_branch_products is not None:
        branch_products = preloaded_branch_products
    elif hasattr(product, 'branch_products') and product.branch_products is not None:
        # Access eager-loaded relationship
        branch_products = product.branch_products
    elif db is not None:
        # Fallback to query (for backwards compatibility)
        branch_products = db.execute(
            select(BranchProduct).where(BranchProduct.product_id == product.id)
        ).scalars().all()
    else:
        branch_products = []

    branch_prices = [
        BranchPriceOutput(
            branch_id=bp.branch_id,
            price_cents=bp.price_cents,
            is_available=bp.is_available,
        )
        for bp in branch_products
    ]

    # Parse allergen_ids (old format - backward compatible)
    allergen_ids = []
    if product.allergen_ids:
        try:
            allergen_ids = json.loads(product.allergen_ids)
        except (json.JSONDecodeError, TypeError):
            pass

    # Build allergens list from ProductAllergen relationship (new format - Phase 0)
    allergens = []
    if hasattr(product, 'product_allergens') and product.product_allergens:
        for pa in product.product_allergens:
            if pa.allergen and pa.allergen.is_active:
                allergens.append(AllergenPresenceOutput(
                    allergen_id=pa.allergen_id,
                    allergen_name=pa.allergen.name,
                    allergen_icon=pa.allergen.icon,
                    presence_type=pa.presence_type,
                ))
    elif db is not None:
        # Fallback: query ProductAllergen with allergen details
        product_allergens = db.execute(
            select(ProductAllergen)
            .options(joinedload(ProductAllergen.allergen))
            .where(
                ProductAllergen.product_id == product.id,
                ProductAllergen.is_active == True,
            )
        ).scalars().unique().all()
        for pa in product_allergens:
            if pa.allergen and pa.allergen.is_active:
                allergens.append(AllergenPresenceOutput(
                    allergen_id=pa.allergen_id,
                    allergen_name=pa.allergen.name,
                    allergen_icon=pa.allergen.icon,
                    presence_type=pa.presence_type,
                ))

    return ProductOutput(
        id=product.id,
        tenant_id=product.tenant_id,
        name=product.name,
        description=product.description,
        image=product.image,
        category_id=product.category_id,
        subcategory_id=product.subcategory_id,
        featured=product.featured,
        popular=product.popular,
        badge=product.badge,
        seal=product.seal,
        allergen_ids=allergen_ids,
        allergens=allergens,
        is_active=product.is_active,
        created_at=product.created_at,
        branch_prices=branch_prices,
    )


@router.get("/products", response_model=list[ProductOutput])
def list_products(
    category_id: int | None = None,
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[ProductOutput]:
    """List products, optionally filtered by category or branch."""
    # Eager load branch_products and product_allergens to avoid N+1 queries
    query = select(Product).options(
        selectinload(Product.branch_products),
        selectinload(Product.product_allergens).joinedload(ProductAllergen.allergen),
    ).where(Product.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Product.is_active == True)

    if category_id:
        query = query.where(Product.category_id == category_id)

    if branch_id:
        # Filter to products available in this branch
        query = query.join(BranchProduct).where(BranchProduct.branch_id == branch_id)

    products = db.execute(query.order_by(Product.name)).scalars().unique().all()
    return [_build_product_output(p) for p in products]


@router.get("/products/{product_id}", response_model=ProductOutput)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ProductOutput:
    """Get a specific product with branch prices and allergens."""
    # Eager load branch_products and product_allergens to avoid additional queries
    product = db.scalar(
        select(Product).options(
            selectinload(Product.branch_products),
            selectinload(Product.product_allergens).joinedload(ProductAllergen.allergen),
        ).where(
            Product.id == product_id,
            Product.tenant_id == user["tenant_id"],
            Product.is_active == True,
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return _build_product_output(product)


@router.post("/products", response_model=ProductOutput, status_code=status.HTTP_201_CREATED)
def create_product(
    body: ProductCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ProductOutput:
    """Create a new product with branch prices and allergens."""
    import json

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

    # Verify subcategory if provided
    if body.subcategory_id:
        subcategory = db.scalar(
            select(Subcategory).where(
                Subcategory.id == body.subcategory_id,
                Subcategory.tenant_id == user["tenant_id"],
            )
        )
        if not subcategory:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid subcategory_id",
            )

    # Determine which allergen format is being used
    # Priority: new format (allergens) > old format (allergen_ids)
    allergen_ids_for_legacy = []
    if body.allergens:
        # New format: extract allergen_ids for backward compatible field
        allergen_ids_for_legacy = [a.allergen_id for a in body.allergens if a.presence_type == "contains"]
    elif body.allergen_ids:
        allergen_ids_for_legacy = body.allergen_ids

    product = Product(
        tenant_id=user["tenant_id"],
        name=body.name,
        description=body.description,
        image=body.image,
        category_id=body.category_id,
        subcategory_id=body.subcategory_id,
        featured=body.featured,
        popular=body.popular,
        badge=body.badge,
        seal=body.seal,
        # Legacy field (backward compatible)
        allergen_ids=json.dumps(allergen_ids_for_legacy) if allergen_ids_for_legacy else None,
        is_active=body.is_active,
    )
    # Set audit fields
    set_created_by(product, user.get("user_id"), user.get("email", ""))
    db.add(product)
    db.flush()  # Get product ID

    # Create ProductAllergen records (Phase 0 - new format)
    if body.allergens:
        for allergen_input in body.allergens:
            # Verify allergen exists and belongs to tenant
            allergen = db.scalar(
                select(Allergen).where(
                    Allergen.id == allergen_input.allergen_id,
                    Allergen.tenant_id == user["tenant_id"],
                    Allergen.is_active == True,
                )
            )
            if not allergen:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid allergen_id: {allergen_input.allergen_id}",
                )
            # Validate presence_type
            if allergen_input.presence_type not in ("contains", "may_contain", "free_from"):
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid presence_type: {allergen_input.presence_type}. Must be contains, may_contain, or free_from",
                )
            product_allergen = ProductAllergen(
                tenant_id=user["tenant_id"],
                product_id=product.id,
                allergen_id=allergen_input.allergen_id,
                presence_type=allergen_input.presence_type,
            )
            set_created_by(product_allergen, user.get("user_id"), user.get("email", ""))
            db.add(product_allergen)
    elif body.allergen_ids:
        # Old format: migrate allergen_ids to ProductAllergen as "contains"
        for allergen_id in body.allergen_ids:
            # Verify allergen exists and belongs to tenant
            allergen = db.scalar(
                select(Allergen).where(
                    Allergen.id == allergen_id,
                    Allergen.tenant_id == user["tenant_id"],
                    Allergen.is_active == True,
                )
            )
            if not allergen:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid allergen_id: {allergen_id}",
                )
            product_allergen = ProductAllergen(
                tenant_id=user["tenant_id"],
                product_id=product.id,
                allergen_id=allergen_id,
                presence_type="contains",  # Default to "contains" for legacy format
            )
            set_created_by(product_allergen, user.get("user_id"), user.get("email", ""))
            db.add(product_allergen)

    # Create branch prices
    for bp in body.branch_prices:
        # Verify branch belongs to tenant
        branch = db.scalar(
            select(Branch).where(
                Branch.id == bp.branch_id,
                Branch.tenant_id == user["tenant_id"],
            )
        )
        if not branch:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid branch_id: {bp.branch_id}",
            )

        branch_product = BranchProduct(
            tenant_id=user["tenant_id"],
            branch_id=bp.branch_id,
            product_id=product.id,
            price_cents=bp.price_cents,
            is_available=bp.is_available,
        )
        db.add(branch_product)

    db.commit()
    db.refresh(product)
    return _build_product_output(product, db)


@router.patch("/products/{product_id}", response_model=ProductOutput)
def update_product(
    product_id: int,
    body: ProductUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ProductOutput:
    """Update a product and its branch prices and allergens."""
    import json

    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == user["tenant_id"],
            Product.is_active == True,
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    update_data = body.model_dump(exclude_unset=True)

    # Handle allergens (new format) - Phase 0
    allergens = update_data.pop("allergens", None)

    # Handle allergen_ids (old format) separately for backward compatibility
    if "allergen_ids" in update_data:
        allergen_ids = update_data.pop("allergen_ids")
        # If new format is not provided, use old format
        if allergens is None and allergen_ids is not None:
            # Convert old format to new format
            allergens = [{"allergen_id": aid, "presence_type": "contains"} for aid in allergen_ids]
        # Keep legacy field updated
        update_data["allergen_ids"] = json.dumps(allergen_ids) if allergen_ids else None

    # Handle branch_prices separately
    branch_prices = update_data.pop("branch_prices", None)

    for key, value in update_data.items():
        setattr(product, key, value)

    # Set audit fields
    set_updated_by(product, user.get("user_id"), user.get("email", ""))

    # Update allergens if provided (Phase 0 - new format)
    if allergens is not None:
        # Delete existing ProductAllergen records
        db.execute(
            ProductAllergen.__table__.delete().where(ProductAllergen.product_id == product_id)
        )

        # Create new ProductAllergen records
        allergen_ids_for_legacy = []
        for allergen_input in allergens:
            allergen_id = allergen_input.get("allergen_id") if isinstance(allergen_input, dict) else allergen_input.allergen_id
            presence_type = allergen_input.get("presence_type", "contains") if isinstance(allergen_input, dict) else allergen_input.presence_type

            # Verify allergen exists and belongs to tenant
            allergen = db.scalar(
                select(Allergen).where(
                    Allergen.id == allergen_id,
                    Allergen.tenant_id == user["tenant_id"],
                    Allergen.is_active == True,
                )
            )
            if not allergen:
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid allergen_id: {allergen_id}",
                )
            # Validate presence_type
            if presence_type not in ("contains", "may_contain", "free_from"):
                db.rollback()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid presence_type: {presence_type}. Must be contains, may_contain, or free_from",
                )
            product_allergen = ProductAllergen(
                tenant_id=user["tenant_id"],
                product_id=product_id,
                allergen_id=allergen_id,
                presence_type=presence_type,
            )
            set_created_by(product_allergen, user.get("user_id"), user.get("email", ""))
            db.add(product_allergen)

            # Track allergens that "contains" for legacy field
            if presence_type == "contains":
                allergen_ids_for_legacy.append(allergen_id)

        # Update legacy allergen_ids field
        product.allergen_ids = json.dumps(allergen_ids_for_legacy) if allergen_ids_for_legacy else None

    # Update branch prices if provided
    if branch_prices is not None:
        # Delete existing branch prices
        db.execute(
            BranchProduct.__table__.delete().where(BranchProduct.product_id == product_id)
        )

        # Create new branch prices
        for bp in branch_prices:
            branch_product = BranchProduct(
                tenant_id=user["tenant_id"],
                branch_id=bp.branch_id,
                product_id=product_id,
                price_cents=bp.price_cents,
                is_available=bp.is_available,
            )
            db.add(branch_product)

    db.commit()
    db.refresh(product)
    return _build_product_output(product, db)


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a product (branch prices remain but product is hidden). Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == user["tenant_id"],
            Product.is_active == True,  # Only find active products
        )
    )
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    # Get category to find branch_id
    category = db.scalar(
        select(Category).where(Category.id == product.category_id)
    )
    branch_id = category.branch_id if category else None

    product_name = product.name
    tenant_id = product.tenant_id

    # Soft delete: set is_active=False with audit trail
    soft_delete(db, product, user.get("user_id"), user.get("email", ""))

    # Publish delete event
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="product",
        entity_id=product_id,
        entity_name=product_name,
        branch_id=branch_id,
        actor_user_id=user.get("user_id"),
    )


# =============================================================================
# Allergen Endpoints
# =============================================================================


@router.get("/allergens", response_model=list[AllergenOutput])
def list_allergens(
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[AllergenOutput]:
    """List all allergens for the tenant."""
    query = select(Allergen).where(Allergen.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Allergen.is_active == True)

    allergens = db.execute(query.order_by(Allergen.name)).scalars().all()
    return [AllergenOutput.model_validate(a) for a in allergens]


@router.post("/allergens", response_model=AllergenOutput, status_code=status.HTTP_201_CREATED)
def create_allergen(
    body: AllergenCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> AllergenOutput:
    """Create a new allergen."""
    allergen = Allergen(
        tenant_id=user["tenant_id"],
        **body.model_dump(),
    )
    # Set audit fields
    set_created_by(allergen, user.get("user_id"), user.get("email", ""))
    db.add(allergen)
    db.commit()
    db.refresh(allergen)
    return AllergenOutput.model_validate(allergen)


@router.patch("/allergens/{allergen_id}", response_model=AllergenOutput)
def update_allergen(
    allergen_id: int,
    body: AllergenUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> AllergenOutput:
    """Update an allergen."""
    allergen = db.scalar(
        select(Allergen).where(
            Allergen.id == allergen_id,
            Allergen.tenant_id == user["tenant_id"],
            Allergen.is_active == True,
        )
    )
    if not allergen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergen not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(allergen, key, value)

    # Set audit fields
    set_updated_by(allergen, user.get("user_id"), user.get("email", ""))

    db.commit()
    db.refresh(allergen)
    return AllergenOutput.model_validate(allergen)


@router.delete("/allergens/{allergen_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_allergen(
    allergen_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete an allergen. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    allergen = db.scalar(
        select(Allergen).where(
            Allergen.id == allergen_id,
            Allergen.tenant_id == user["tenant_id"],
            Allergen.is_active == True,  # Only find active allergens
        )
    )
    if not allergen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergen not found",
        )

    allergen_name = allergen.name
    tenant_id = allergen.tenant_id

    # Soft delete: set is_active=False with audit trail
    soft_delete(db, allergen, user.get("user_id"), user.get("email", ""))

    # Publish delete event (allergens are tenant-wide, no branch_id)
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="allergen",
        entity_id=allergen_id,
        entity_name=allergen_name,
        actor_user_id=user.get("user_id"),
    )


# =============================================================================
# Table Endpoints
# =============================================================================


@router.get("/tables", response_model=list[TableOutput])
def list_tables(
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[TableOutput]:
    """List tables, optionally filtered by branch."""
    query = select(Table).where(Table.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(Table.is_active == True)

    if branch_id:
        query = query.where(Table.branch_id == branch_id)

    tables = db.execute(query.order_by(Table.branch_id, Table.code)).scalars().all()
    return [TableOutput.model_validate(t) for t in tables]


@router.post("/tables", response_model=TableOutput, status_code=status.HTTP_201_CREATED)
def create_table(
    body: TableCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableOutput:
    """Create a new table."""
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

    table = Table(
        tenant_id=user["tenant_id"],
        **body.model_dump(),
    )
    # Set audit fields
    set_created_by(table, user.get("user_id"), user.get("email", ""))
    db.add(table)
    db.commit()
    db.refresh(table)
    return TableOutput.model_validate(table)


@router.patch("/tables/{table_id}", response_model=TableOutput)
def update_table(
    table_id: int,
    body: TableUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableOutput:
    """Update a table."""
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active == True,
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(table, key, value)

    # Set audit fields
    set_updated_by(table, user.get("user_id"), user.get("email", ""))

    db.commit()
    db.refresh(table)
    return TableOutput.model_validate(table)


@router.delete("/tables/{table_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_table(
    table_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a table. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.tenant_id == user["tenant_id"],
            Table.is_active == True,  # Only find active tables
        )
    )
    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table not found",
        )

    table_code = table.code
    branch_id = table.branch_id
    tenant_id = table.tenant_id

    # Soft delete: set is_active=False with audit trail
    soft_delete(db, table, user.get("user_id"), user.get("email", ""))

    # Publish delete event
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="table",
        entity_id=table_id,
        entity_name=table_code,
        branch_id=branch_id,
        actor_user_id=user.get("user_id"),
    )


# =============================================================================
# Sector Endpoints
# =============================================================================


def _sector_to_output(sector: BranchSector) -> BranchSectorOutput:
    """Convert BranchSector model to output schema with computed is_global field."""
    return BranchSectorOutput(
        id=sector.id,
        tenant_id=sector.tenant_id,
        branch_id=sector.branch_id,
        name=sector.name,
        prefix=sector.prefix,
        display_order=sector.display_order,
        is_active=sector.is_active,
        is_global=sector.branch_id is None,
    )


@router.get("/sectors", response_model=list[BranchSectorOutput])
def list_sectors(
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[BranchSectorOutput]:
    """
    List sectors available for a branch.
    If branch_id provided, returns global sectors + branch-specific sectors.
    If no branch_id, returns only global sectors.
    """
    tenant_id = user["tenant_id"]

    query = select(BranchSector).where(
        BranchSector.tenant_id == tenant_id,
        BranchSector.is_active == True,
    )

    if branch_id:
        # Global sectors (branch_id=None) + branch-specific sectors
        query = query.where(
            or_(
                BranchSector.branch_id == None,
                BranchSector.branch_id == branch_id,
            )
        )
    else:
        # Only global sectors
        query = query.where(BranchSector.branch_id == None)

    query = query.order_by(BranchSector.display_order, BranchSector.name)
    sectors = db.scalars(query).all()

    return [_sector_to_output(s) for s in sectors]


@router.post("/sectors", response_model=BranchSectorOutput, status_code=status.HTTP_201_CREATED)
def create_sector(
    body: BranchSectorCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchSectorOutput:
    """
    Create a new sector. Branch-specific sectors can be created by ADMIN/MANAGER.
    Global sectors (branch_id=None) require ADMIN role.
    """
    tenant_id = user["tenant_id"]
    roles = user.get("roles", [])

    # Global sectors require ADMIN
    if body.branch_id is None and "ADMIN" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to create global sectors",
        )

    # Branch sectors require ADMIN or MANAGER
    if body.branch_id is not None and "ADMIN" not in roles and "MANAGER" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    # Validate prefix format (2-4 uppercase letters)
    prefix = body.prefix.upper().strip()
    if not re.match(r'^[A-Z]{2,4}$', prefix):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prefix must be 2-4 uppercase letters",
        )

    # Check if prefix already exists for this tenant+branch combination
    existing = db.scalar(
        select(BranchSector).where(
            BranchSector.tenant_id == tenant_id,
            BranchSector.branch_id == body.branch_id,
            BranchSector.prefix == prefix,
            BranchSector.is_active == True,
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sector with prefix '{prefix}' already exists",
        )

    # Get next display_order
    max_order = db.scalar(
        select(func.coalesce(func.max(BranchSector.display_order), 0)).where(
            BranchSector.tenant_id == tenant_id,
            or_(
                BranchSector.branch_id == body.branch_id,
                BranchSector.branch_id == None,
            ),
        )
    )

    sector = BranchSector(
        tenant_id=tenant_id,
        branch_id=body.branch_id,
        name=body.name.strip(),
        prefix=prefix,
        display_order=(max_order or 0) + 1,
    )
    set_created_by(sector, user.get("user_id"), user.get("email", ""))

    db.add(sector)
    db.commit()
    db.refresh(sector)

    return _sector_to_output(sector)


@router.delete("/sectors/{sector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sector(
    sector_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """
    Soft delete a sector. Cannot delete global sectors.
    Requires ADMIN role.
    """
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    sector = db.scalar(
        select(BranchSector).where(
            BranchSector.id == sector_id,
            BranchSector.tenant_id == user["tenant_id"],
            BranchSector.is_active == True,
        )
    )
    if not sector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sector not found",
        )

    # Cannot delete global sectors
    if sector.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete global sectors",
        )

    soft_delete(db, sector, user.get("user_id"), user.get("email", ""))


# =============================================================================
# Bulk Table Creation
# =============================================================================


def _generate_table_codes(
    db: Session,
    tenant_id: int,
    branch_id: int,
    sector_prefix: str,
    count: int,
) -> list[str]:
    """
    Generate sequential table codes for a sector.
    Finds the highest existing number and continues from there.
    Example: If TER-05 exists, generates TER-06, TER-07, etc.
    """
    # Find existing tables with this prefix in this branch
    existing_codes = db.scalars(
        select(Table.code).where(
            Table.tenant_id == tenant_id,
            Table.branch_id == branch_id,
            Table.code.like(f"{sector_prefix}-%"),
        )
    ).all()

    # Extract max number from existing codes
    max_num = 0
    pattern = re.compile(rf"^{re.escape(sector_prefix)}-(\d+)$")
    for code in existing_codes:
        match = pattern.match(code)
        if match:
            max_num = max(max_num, int(match.group(1)))

    # Generate new codes
    return [f"{sector_prefix}-{max_num + i + 1:02d}" for i in range(count)]


@router.post("/tables/batch", response_model=TableBulkResult, status_code=status.HTTP_201_CREATED)
def create_tables_batch(
    body: TableBulkCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> TableBulkResult:
    """
    Create multiple tables in a single transaction.
    Generates table codes automatically based on sector prefix.
    Requires ADMIN or MANAGER role.
    """
    roles = user.get("roles", [])
    if "ADMIN" not in roles and "MANAGER" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    tenant_id = user["tenant_id"]

    # Validate branch exists
    branch = db.scalar(
        select(Branch).where(
            Branch.id == body.branch_id,
            Branch.tenant_id == tenant_id,
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )

    # Validate total count
    total_count = sum(item.count for item in body.tables)
    if total_count > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create more than 200 tables at once",
        )
    if total_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tables specified",
        )

    # Validate and process each item
    created_tables: list[Table] = []
    sector_cache: dict[int, BranchSector] = {}

    for item in body.tables:
        # Validate capacity
        if item.capacity < 1 or item.capacity > 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid capacity: {item.capacity}. Must be between 1 and 20.",
            )

        # Validate count
        if item.count < 1 or item.count > 100:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid count: {item.count}. Must be between 1 and 100.",
            )

        # Get sector (with caching)
        if item.sector_id not in sector_cache:
            sector = db.scalar(
                select(BranchSector).where(
                    BranchSector.id == item.sector_id,
                    BranchSector.tenant_id == tenant_id,
                    BranchSector.is_active == True,
                    or_(
                        BranchSector.branch_id == body.branch_id,
                        BranchSector.branch_id == None,  # Global sectors
                    ),
                )
            )
            if not sector:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Sector not found: {item.sector_id}",
                )
            sector_cache[item.sector_id] = sector

        sector = sector_cache[item.sector_id]

        # Generate codes for this batch
        codes = _generate_table_codes(
            db, tenant_id, body.branch_id, sector.prefix, item.count
        )

        # Create tables
        for code in codes:
            table = Table(
                tenant_id=tenant_id,
                branch_id=body.branch_id,
                code=code,
                capacity=item.capacity,
                sector=sector.name,
                status="FREE",
            )
            set_created_by(table, user.get("user_id"), user.get("email", ""))
            db.add(table)
            created_tables.append(table)

    db.commit()

    # Refresh all tables to get IDs
    for table in created_tables:
        db.refresh(table)

    return TableBulkResult(
        created_count=len(created_tables),
        tables=[TableOutput.model_validate(t) for t in created_tables],
    )


# =============================================================================
# Staff Endpoints
# =============================================================================


def _build_staff_output(user_obj: User, db: Session = None) -> StaffOutput:
    """Build StaffOutput with branch roles.

    Args:
        user_obj: The User model instance
        db: Database session (only needed if branch_roles not preloaded)
    """
    # Use eager-loaded relationship if available, otherwise query
    if hasattr(user_obj, 'branch_roles') and user_obj.branch_roles is not None:
        branch_roles = user_obj.branch_roles
    elif db is not None:
        branch_roles = db.execute(
            select(UserBranchRole).where(UserBranchRole.user_id == user_obj.id)
        ).scalars().all()
    else:
        branch_roles = []

    roles_list = [
        {"branch_id": br.branch_id, "role": br.role}
        for br in branch_roles
    ]

    return StaffOutput(
        id=user_obj.id,
        tenant_id=user_obj.tenant_id,
        email=user_obj.email,
        first_name=user_obj.first_name,
        last_name=user_obj.last_name,
        phone=user_obj.phone,
        dni=user_obj.dni,
        hire_date=user_obj.hire_date,
        is_active=user_obj.is_active,
        created_at=user_obj.created_at,
        branch_roles=roles_list,
    )


@router.get("/staff", response_model=list[StaffOutput])
def list_staff(
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[StaffOutput]:
    """List staff members, optionally filtered by branch.

    ADMIN: Can see all staff across all branches
    MANAGER: Can only see staff assigned to their branches
    """
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]

    if not is_admin and not is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    # Get user's branch IDs for filtering (MANAGER only)
    user_branch_ids = user.get("branch_ids", [])

    # Eager load branch_roles to avoid N+1 queries
    query = select(User).options(
        selectinload(User.branch_roles)
    ).where(User.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(User.is_active == True)

    # Filter by branch_id if provided
    if branch_id:
        # MANAGER can only access their assigned branches
        if is_manager and not is_admin and branch_id not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a esta sucursal",
            )
        query = query.join(UserBranchRole).where(UserBranchRole.branch_id == branch_id)
    elif is_manager and not is_admin:
        # MANAGER without branch_id filter: only show staff from their branches
        if user_branch_ids:
            query = query.join(UserBranchRole).where(
                UserBranchRole.branch_id.in_(user_branch_ids)
            )
        else:
            # MANAGER with no branch assignments sees no staff
            return []

    staff = db.execute(query.order_by(User.email)).scalars().unique().all()
    return [_build_staff_output(s) for s in staff]


@router.get("/staff/{staff_id}", response_model=StaffOutput)
def get_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> StaffOutput:
    """Get a specific staff member.

    ADMIN: Can see any staff member
    MANAGER: Can only see staff assigned to their branches
    """
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]

    if not is_admin and not is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    # Eager load branch_roles to avoid additional query
    staff = db.scalar(
        select(User).options(
            selectinload(User.branch_roles)
        ).where(
            User.id == staff_id,
            User.tenant_id == user["tenant_id"],
            User.is_active == True,
        )
    )
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )

    # MANAGER can only see staff from their branches
    if is_manager and not is_admin:
        user_branch_ids = set(user.get("branch_ids", []))
        staff_branch_ids = {br.branch_id for br in staff.branch_roles}
        if not user_branch_ids.intersection(staff_branch_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este empleado",
            )

    return _build_staff_output(staff)


@router.post("/staff", response_model=StaffOutput, status_code=status.HTTP_201_CREATED)
def create_staff(
    body: StaffCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> StaffOutput:
    """Create a new staff member.

    ADMIN: Can create staff in any branch with any role
    MANAGER: Can only create staff in their assigned branches, cannot create ADMIN role
    """
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]

    if not is_admin and not is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    # Validate branch access for MANAGER
    if is_manager and not is_admin:
        user_branch_ids = set(user.get("branch_ids", []))

        for role in body.branch_roles:
            branch_id = role.get("branch_id")
            role_name = role.get("role", "")

            # MANAGER cannot create staff in branches they don't have access to
            if branch_id not in user_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes acceso a la sucursal {branch_id}",
                )

            # MANAGER cannot assign ADMIN role
            if role_name == "ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo un administrador puede asignar el rol de ADMIN",
                )

    # Check if email already exists
    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    staff = User(
        tenant_id=user["tenant_id"],
        email=body.email,
        password=body.password,  # In production, hash this
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        dni=body.dni,
        hire_date=body.hire_date,
        is_active=body.is_active,
    )
    # Set audit fields
    set_created_by(staff, user.get("user_id"), user.get("email", ""))
    db.add(staff)
    db.flush()

    # Create branch roles
    for role in body.branch_roles:
        branch_role = UserBranchRole(
            user_id=staff.id,
            tenant_id=user["tenant_id"],
            branch_id=role["branch_id"],
            role=role["role"],
        )
        db.add(branch_role)

    db.commit()
    db.refresh(staff)
    return _build_staff_output(staff, db)


@router.patch("/staff/{staff_id}", response_model=StaffOutput)
def update_staff(
    staff_id: int,
    body: StaffUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> StaffOutput:
    """Update a staff member.

    ADMIN: Can update any staff member in any branch with any role
    MANAGER: Can only update staff in their branches, cannot assign ADMIN role
    """
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]

    if not is_admin and not is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    # Get user's branch IDs
    user_branch_ids = set(user.get("branch_ids", []))

    # Eager load branch_roles to check access
    staff = db.scalar(
        select(User).options(
            selectinload(User.branch_roles)
        ).where(
            User.id == staff_id,
            User.tenant_id == user["tenant_id"],
            User.is_active == True,
        )
    )
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )

    # MANAGER access validation
    if is_manager and not is_admin:
        # Check if MANAGER has access to this staff member (at least one common branch)
        staff_branch_ids = {br.branch_id for br in staff.branch_roles}
        if not user_branch_ids.intersection(staff_branch_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este empleado",
            )

    update_data = body.model_dump(exclude_unset=True)
    branch_roles = update_data.pop("branch_roles", None)

    # Validate new branch_roles for MANAGER
    if branch_roles is not None and is_manager and not is_admin:
        for role in branch_roles:
            branch_id = role.get("branch_id")
            role_name = role.get("role", "")

            # MANAGER cannot assign staff to branches they don't have access to
            if branch_id not in user_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes acceso a la sucursal {branch_id}",
                )

            # MANAGER cannot assign ADMIN role
            if role_name == "ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo un administrador puede asignar el rol de ADMIN",
                )

    for key, value in update_data.items():
        setattr(staff, key, value)

    # Set audit fields
    set_updated_by(staff, user.get("user_id"), user.get("email", ""))

    # Update branch roles if provided
    if branch_roles is not None:
        # Delete existing roles
        db.execute(
            UserBranchRole.__table__.delete().where(UserBranchRole.user_id == staff_id)
        )

        # Create new roles
        for role in branch_roles:
            branch_role = UserBranchRole(
                user_id=staff_id,
                tenant_id=user["tenant_id"],
                branch_id=role["branch_id"],
                role=role["role"],
            )
            db.add(branch_role)

    db.commit()
    db.refresh(staff)
    return _build_staff_output(staff, db)


@router.delete("/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a staff member (branch roles remain but user is hidden)."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    staff = db.scalar(
        select(User).where(
            User.id == staff_id,
            User.tenant_id == user["tenant_id"],
            User.is_active == True,  # Only find active staff
        )
    )
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )

    staff_name = f"{staff.first_name or ''} {staff.last_name or ''}".strip() or staff.email
    tenant_id = staff.tenant_id

    # Soft delete: set is_active=False with audit trail
    soft_delete(db, staff, user.get("user_id"), user.get("email", ""))

    # Publish delete event (staff is tenant-wide, no branch_id)
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="staff",
        entity_id=staff_id,
        entity_name=staff_name,
        actor_user_id=user.get("user_id"),
    )


# =============================================================================
# Active Orders (for Orders page)
# =============================================================================


class OrderItemOutput(BaseModel):
    id: int
    product_id: int
    product_name: str
    qty: int
    unit_price_cents: int
    notes: str | None = None
    diner_name: str | None = None

    class Config:
        from_attributes = True


class ActiveOrderOutput(BaseModel):
    id: int
    round_number: int
    status: str
    table_id: int | None = None
    table_code: str | None = None
    branch_id: int
    branch_name: str
    session_id: int
    items: list[OrderItemOutput]
    submitted_at: datetime | None = None
    total_cents: int = 0

    class Config:
        from_attributes = True


class OrderStatsOutput(BaseModel):
    total_active: int
    pending: int
    in_kitchen: int
    ready: int


@router.get("/orders/stats", response_model=OrderStatsOutput)
def get_order_stats(
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> OrderStatsOutput:
    """Get order statistics for the dashboard."""
    branch_ids = user.get("branch_ids", [])
    if not branch_ids:
        return OrderStatsOutput(total_active=0, pending=0, in_kitchen=0, ready=0)

    # Filter by specific branch if provided
    if branch_id is not None:
        if branch_id not in branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this branch",
            )
        branch_ids = [branch_id]

    # Count orders by status
    active_statuses = ["SUBMITTED", "IN_KITCHEN", "READY"]

    base_query = select(Round).where(
        Round.branch_id.in_(branch_ids),
        Round.status.in_(active_statuses),
    )

    all_rounds = db.execute(base_query).scalars().all()

    pending = sum(1 for r in all_rounds if r.status == "SUBMITTED")
    in_kitchen = sum(1 for r in all_rounds if r.status == "IN_KITCHEN")
    ready = sum(1 for r in all_rounds if r.status == "READY")

    return OrderStatsOutput(
        total_active=len(all_rounds),
        pending=pending,
        in_kitchen=in_kitchen,
        ready=ready,
    )


@router.get("/orders", response_model=list[ActiveOrderOutput])
def get_active_orders(
    branch_id: int | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[ActiveOrderOutput]:
    """
    Get all active orders (rounds) across branches.
    Includes SUBMITTED, IN_KITCHEN, and READY orders.
    """
    branch_ids = user.get("branch_ids", [])
    if not branch_ids:
        return []

    # Filter by specific branch if provided
    if branch_id is not None:
        if branch_id not in branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this branch",
            )
        branch_ids = [branch_id]

    # Build query
    active_statuses = ["SUBMITTED", "IN_KITCHEN", "READY"]
    if status_filter and status_filter in active_statuses:
        active_statuses = [status_filter]

    # Eager load all relationships to avoid N+1 queries:
    # - items with products and diners
    # - session with table
    rounds = db.execute(
        select(Round)
        .options(
            selectinload(Round.items).joinedload(RoundItem.product),
            selectinload(Round.items).joinedload(RoundItem.diner),
            joinedload(Round.session).joinedload(TableSession.table),
        )
        .where(
            Round.branch_id.in_(branch_ids),
            Round.status.in_(active_statuses),
        )
        .order_by(Round.submitted_at.asc())
    ).scalars().unique().all()

    # Pre-fetch all branches for these rounds in a single query
    unique_branch_ids = list(set(r.branch_id for r in rounds))
    if unique_branch_ids:
        branches_result = db.execute(
            select(Branch).where(Branch.id.in_(unique_branch_ids))
        ).scalars().all()
        branches_by_id = {b.id: b for b in branches_result}
    else:
        branches_by_id = {}

    result = []
    for round_obj in rounds:
        # Access pre-loaded relationships (no additional queries)
        session = round_obj.session
        table = session.table if session else None
        branch = branches_by_id.get(round_obj.branch_id)

        order_items = []
        total_cents = 0
        for item in round_obj.items:
            total_cents += item.unit_price_cents * item.qty
            # Access pre-loaded diner (no additional query)
            diner_name = item.diner.name if item.diner else None

            order_items.append(OrderItemOutput(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name,
                qty=item.qty,
                unit_price_cents=item.unit_price_cents,
                notes=item.notes,
                diner_name=diner_name,
            ))

        result.append(ActiveOrderOutput(
            id=round_obj.id,
            round_number=round_obj.round_number,
            status=round_obj.status,
            table_id=table.id if table else None,
            table_code=table.code if table else None,
            branch_id=round_obj.branch_id,
            branch_name=branch.name if branch else "Unknown",
            session_id=round_obj.table_session_id,
            items=order_items,
            submitted_at=round_obj.submitted_at,
            total_cents=total_cents,
        ))

    return result


# =============================================================================
# Reports Endpoints
# =============================================================================


class DailySalesOutput(BaseModel):
    """Daily sales summary."""
    date: str
    total_sales_cents: int
    order_count: int
    avg_order_cents: int


class TopProductOutput(BaseModel):
    """Top selling product."""
    product_id: int
    product_name: str
    quantity_sold: int
    total_revenue_cents: int


class ReportsSummaryOutput(BaseModel):
    """Summary statistics for reports."""
    total_revenue_cents: int
    total_orders: int
    avg_order_value_cents: int
    total_sessions: int
    busiest_hour: int | None = None


class SalesReportOutput(BaseModel):
    """Complete sales report."""
    summary: ReportsSummaryOutput
    daily_sales: list[DailySalesOutput]
    top_products: list[TopProductOutput]


@router.get("/reports/summary", response_model=ReportsSummaryOutput)
def get_reports_summary(
    branch_id: int | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ReportsSummaryOutput:
    """
    Get summary statistics for reports.
    """
    from datetime import timedelta
    from rest_api.models import Check, Payment

    # Get user's branches
    user_branch_ids = user.get("branch_ids", [])
    if branch_id and branch_id not in user_branch_ids:
        raise HTTPException(status_code=403, detail="No access to this branch")
    branch_ids = [branch_id] if branch_id else user_branch_ids

    # Date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Get total revenue from paid payments
    total_revenue = db.scalar(
        select(func.sum(Payment.amount_cents))
        .where(
            Payment.branch_id.in_(branch_ids),
            Payment.status == "APPROVED",
            Payment.created_at >= start_date,
        )
    ) or 0

    # Get total orders (rounds with status != DRAFT, CANCELED)
    total_orders = db.scalar(
        select(func.count(Round.id))
        .where(
            Round.branch_id.in_(branch_ids),
            Round.status.in_(["SUBMITTED", "IN_KITCHEN", "READY", "SERVED"]),
            Round.submitted_at >= start_date,
        )
    ) or 0

    # Calculate average order value
    avg_order = total_revenue // total_orders if total_orders > 0 else 0

    # Get total sessions
    total_sessions = db.scalar(
        select(func.count(TableSession.id))
        .join(Table, TableSession.table_id == Table.id)
        .where(
            Table.branch_id.in_(branch_ids),
            TableSession.opened_at >= start_date,
        )
    ) or 0

    # Get busiest hour (most orders)
    busiest_hour = db.scalar(
        select(func.extract("hour", Round.submitted_at))
        .where(
            Round.branch_id.in_(branch_ids),
            Round.submitted_at >= start_date,
            Round.submitted_at.isnot(None),
        )
        .group_by(func.extract("hour", Round.submitted_at))
        .order_by(func.count().desc())
        .limit(1)
    )

    return ReportsSummaryOutput(
        total_revenue_cents=total_revenue,
        total_orders=total_orders,
        avg_order_value_cents=avg_order,
        total_sessions=total_sessions,
        busiest_hour=int(busiest_hour) if busiest_hour is not None else None,
    )


@router.get("/reports/daily-sales", response_model=list[DailySalesOutput])
def get_daily_sales(
    branch_id: int | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[DailySalesOutput]:
    """
    Get daily sales breakdown.
    """
    from datetime import timedelta
    from rest_api.models import Payment

    # Get user's branches
    user_branch_ids = user.get("branch_ids", [])
    if branch_id and branch_id not in user_branch_ids:
        raise HTTPException(status_code=403, detail="No access to this branch")
    branch_ids = [branch_id] if branch_id else user_branch_ids

    # Date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Get daily totals
    daily_stats = db.execute(
        select(
            func.date(Payment.created_at).label("date"),
            func.sum(Payment.amount_cents).label("total"),
            func.count(Payment.id).label("count"),
        )
        .where(
            Payment.branch_id.in_(branch_ids),
            Payment.status == "APPROVED",
            Payment.created_at >= start_date,
        )
        .group_by(func.date(Payment.created_at))
        .order_by(func.date(Payment.created_at))
    ).all()

    return [
        DailySalesOutput(
            date=str(row.date),
            total_sales_cents=row.total or 0,
            order_count=row.count or 0,
            avg_order_cents=(row.total // row.count) if row.count > 0 else 0,
        )
        for row in daily_stats
    ]


@router.get("/reports/top-products", response_model=list[TopProductOutput])
def get_top_products(
    branch_id: int | None = None,
    days: int = 30,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[TopProductOutput]:
    """
    Get top selling products.
    """
    from datetime import timedelta

    # Get user's branches
    user_branch_ids = user.get("branch_ids", [])
    if branch_id and branch_id not in user_branch_ids:
        raise HTTPException(status_code=403, detail="No access to this branch")
    branch_ids = [branch_id] if branch_id else user_branch_ids

    # Date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Get top products by quantity sold
    top_products = db.execute(
        select(
            RoundItem.product_id,
            Product.name.label("product_name"),
            func.sum(RoundItem.qty).label("quantity"),
            func.sum(RoundItem.qty * RoundItem.unit_price_cents).label("revenue"),
        )
        .join(Round, RoundItem.round_id == Round.id)
        .join(Product, RoundItem.product_id == Product.id)
        .where(
            Round.branch_id.in_(branch_ids),
            Round.status.in_(["SUBMITTED", "IN_KITCHEN", "READY", "SERVED"]),
            Round.submitted_at >= start_date,
        )
        .group_by(RoundItem.product_id, Product.name)
        .order_by(func.sum(RoundItem.qty).desc())
        .limit(limit)
    ).all()

    return [
        TopProductOutput(
            product_id=row.product_id,
            product_name=row.product_name,
            quantity_sold=row.quantity or 0,
            total_revenue_cents=row.revenue or 0,
        )
        for row in top_products
    ]


# =============================================================================
# Restore Endpoints (Soft Delete Recovery)
# =============================================================================


class RestoreOutput(BaseModel):
    """Output for restore operation."""
    success: bool
    message: str
    entity_type: str
    entity_id: int


@router.post("/{entity_type}/{entity_id}/restore", response_model=RestoreOutput)
def restore_deleted_entity(
    entity_type: str,
    entity_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> RestoreOutput:
    """
    Restore a soft-deleted entity. Requires ADMIN role.

    Supported entity types:
    - branches, categories, subcategories, products
    - allergens, tables, staff, promotions
    """
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    # Get the model class for this entity type
    model_class = get_model_class(entity_type)
    if not model_class:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity type: {entity_type}",
        )

    # Find the soft-deleted entity
    entity = find_deleted_entity(db, model_class, entity_id)
    if not entity:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type} not found or already active",
        )

    # Verify tenant ownership
    if hasattr(entity, 'tenant_id') and entity.tenant_id != user["tenant_id"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type} not found",
        )

    # Restore the entity
    restore_entity(db, entity, user.get("user_id"), user.get("email", ""))

    # Get entity name for response
    entity_name = getattr(entity, 'name', None) or getattr(entity, 'code', None) or getattr(entity, 'email', None) or str(entity_id)

    return RestoreOutput(
        success=True,
        message=f"{entity_type} '{entity_name}' restored successfully",
        entity_type=entity_type,
        entity_id=entity_id,
    )


# =============================================================================
# Branch Exclusion Endpoints (Category/Subcategory per Branch)
# =============================================================================


@router.get("/exclusions", response_model=ExclusionOverview)
def get_exclusions_overview(
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ExclusionOverview:
    """
    Get complete overview of all category and subcategory exclusions.
    Returns which categories/subcategories are excluded from which branches.
    Requires ADMIN role.
    """
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    tenant_id = user["tenant_id"]

    # Get all active categories with their exclusions
    categories = db.execute(
        select(Category).where(
            Category.tenant_id == tenant_id,
            Category.is_active == True,
        ).order_by(Category.name)
    ).scalars().all()

    # Get all category exclusions
    cat_exclusions = db.execute(
        select(BranchCategoryExclusion).where(
            BranchCategoryExclusion.tenant_id == tenant_id,
            BranchCategoryExclusion.is_active == True,
        )
    ).scalars().all()

    # Build category exclusion map: category_id -> [branch_ids]
    cat_exclusion_map: dict[int, list[int]] = {}
    for exc in cat_exclusions:
        if exc.category_id not in cat_exclusion_map:
            cat_exclusion_map[exc.category_id] = []
        cat_exclusion_map[exc.category_id].append(exc.branch_id)

    category_summaries = [
        CategoryExclusionSummary(
            category_id=cat.id,
            category_name=cat.name,
            excluded_branch_ids=cat_exclusion_map.get(cat.id, []),
        )
        for cat in categories
    ]

    # Get all active subcategories with their category info
    subcategories = db.execute(
        select(Subcategory).options(
            joinedload(Subcategory.category)
        ).where(
            Subcategory.tenant_id == tenant_id,
            Subcategory.is_active == True,
        ).order_by(Subcategory.name)
    ).scalars().unique().all()

    # Get all subcategory exclusions
    subcat_exclusions = db.execute(
        select(BranchSubcategoryExclusion).where(
            BranchSubcategoryExclusion.tenant_id == tenant_id,
            BranchSubcategoryExclusion.is_active == True,
        )
    ).scalars().all()

    # Build subcategory exclusion map: subcategory_id -> [branch_ids]
    subcat_exclusion_map: dict[int, list[int]] = {}
    for exc in subcat_exclusions:
        if exc.subcategory_id not in subcat_exclusion_map:
            subcat_exclusion_map[exc.subcategory_id] = []
        subcat_exclusion_map[exc.subcategory_id].append(exc.branch_id)

    subcategory_summaries = [
        SubcategoryExclusionSummary(
            subcategory_id=subcat.id,
            subcategory_name=subcat.name,
            category_id=subcat.category_id,
            category_name=subcat.category.name if subcat.category else "Unknown",
            excluded_branch_ids=subcat_exclusion_map.get(subcat.id, []),
        )
        for subcat in subcategories
    ]

    return ExclusionOverview(
        category_exclusions=category_summaries,
        subcategory_exclusions=subcategory_summaries,
    )


@router.get("/exclusions/categories/{category_id}", response_model=CategoryExclusionSummary)
def get_category_exclusions(
    category_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> CategoryExclusionSummary:
    """Get exclusion details for a specific category."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

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

    exclusions = db.execute(
        select(BranchCategoryExclusion).where(
            BranchCategoryExclusion.category_id == category_id,
            BranchCategoryExclusion.tenant_id == user["tenant_id"],
            BranchCategoryExclusion.is_active == True,
        )
    ).scalars().all()

    return CategoryExclusionSummary(
        category_id=category.id,
        category_name=category.name,
        excluded_branch_ids=[exc.branch_id for exc in exclusions],
    )


@router.put("/exclusions/categories/{category_id}", response_model=CategoryExclusionSummary)
def update_category_exclusions(
    category_id: int,
    body: ExclusionBulkUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> CategoryExclusionSummary:
    """
    Update exclusions for a category. Replaces all existing exclusions.
    Pass empty list to remove all exclusions (available in all branches).
    Requires ADMIN role.
    """
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    tenant_id = user["tenant_id"]

    # Verify category exists and belongs to tenant
    category = db.scalar(
        select(Category).where(
            Category.id == category_id,
            Category.tenant_id == tenant_id,
            Category.is_active == True,
        )
    )
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Category not found",
        )

    # Verify all branch_ids belong to tenant
    if body.excluded_branch_ids:
        branches = db.execute(
            select(Branch).where(
                Branch.id.in_(body.excluded_branch_ids),
                Branch.tenant_id == tenant_id,
            )
        ).scalars().all()
        valid_branch_ids = {b.id for b in branches}
        invalid_ids = set(body.excluded_branch_ids) - valid_branch_ids
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid branch IDs: {list(invalid_ids)}",
            )

    # Delete existing exclusions (soft delete)
    existing = db.execute(
        select(BranchCategoryExclusion).where(
            BranchCategoryExclusion.category_id == category_id,
            BranchCategoryExclusion.tenant_id == tenant_id,
            BranchCategoryExclusion.is_active == True,
        )
    ).scalars().all()

    for exc in existing:
        soft_delete(db, exc, user.get("user_id"), user.get("email", ""))

    # Create new exclusions
    for branch_id in body.excluded_branch_ids:
        exclusion = BranchCategoryExclusion(
            tenant_id=tenant_id,
            branch_id=branch_id,
            category_id=category_id,
        )
        set_created_by(exclusion, user.get("user_id"), user.get("email", ""))
        db.add(exclusion)

    db.commit()

    return CategoryExclusionSummary(
        category_id=category.id,
        category_name=category.name,
        excluded_branch_ids=body.excluded_branch_ids,
    )


@router.get("/exclusions/subcategories/{subcategory_id}", response_model=SubcategoryExclusionSummary)
def get_subcategory_exclusions(
    subcategory_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> SubcategoryExclusionSummary:
    """Get exclusion details for a specific subcategory."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    subcategory = db.scalar(
        select(Subcategory).options(
            joinedload(Subcategory.category)
        ).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == user["tenant_id"],
            Subcategory.is_active == True,
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )

    exclusions = db.execute(
        select(BranchSubcategoryExclusion).where(
            BranchSubcategoryExclusion.subcategory_id == subcategory_id,
            BranchSubcategoryExclusion.tenant_id == user["tenant_id"],
            BranchSubcategoryExclusion.is_active == True,
        )
    ).scalars().all()

    return SubcategoryExclusionSummary(
        subcategory_id=subcategory.id,
        subcategory_name=subcategory.name,
        category_id=subcategory.category_id,
        category_name=subcategory.category.name if subcategory.category else "Unknown",
        excluded_branch_ids=[exc.branch_id for exc in exclusions],
    )


@router.put("/exclusions/subcategories/{subcategory_id}", response_model=SubcategoryExclusionSummary)
def update_subcategory_exclusions(
    subcategory_id: int,
    body: ExclusionBulkUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> SubcategoryExclusionSummary:
    """
    Update exclusions for a subcategory. Replaces all existing exclusions.
    Pass empty list to remove all exclusions (available in all branches).
    Requires ADMIN role.
    """
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    tenant_id = user["tenant_id"]

    # Verify subcategory exists and belongs to tenant
    subcategory = db.scalar(
        select(Subcategory).options(
            joinedload(Subcategory.category)
        ).where(
            Subcategory.id == subcategory_id,
            Subcategory.tenant_id == tenant_id,
            Subcategory.is_active == True,
        )
    )
    if not subcategory:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subcategory not found",
        )

    # Verify all branch_ids belong to tenant
    if body.excluded_branch_ids:
        branches = db.execute(
            select(Branch).where(
                Branch.id.in_(body.excluded_branch_ids),
                Branch.tenant_id == tenant_id,
            )
        ).scalars().all()
        valid_branch_ids = {b.id for b in branches}
        invalid_ids = set(body.excluded_branch_ids) - valid_branch_ids
        if invalid_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid branch IDs: {list(invalid_ids)}",
            )

    # Delete existing exclusions (soft delete)
    existing = db.execute(
        select(BranchSubcategoryExclusion).where(
            BranchSubcategoryExclusion.subcategory_id == subcategory_id,
            BranchSubcategoryExclusion.tenant_id == tenant_id,
            BranchSubcategoryExclusion.is_active == True,
        )
    ).scalars().all()

    for exc in existing:
        soft_delete(db, exc, user.get("user_id"), user.get("email", ""))

    # Create new exclusions
    for branch_id in body.excluded_branch_ids:
        exclusion = BranchSubcategoryExclusion(
            tenant_id=tenant_id,
            branch_id=branch_id,
            subcategory_id=subcategory_id,
        )
        set_created_by(exclusion, user.get("user_id"), user.get("email", ""))
        db.add(exclusion)

    db.commit()

    return SubcategoryExclusionSummary(
        subcategory_id=subcategory.id,
        subcategory_name=subcategory.name,
        category_id=subcategory.category_id,
        category_name=subcategory.category.name if subcategory.category else "Unknown",
        excluded_branch_ids=body.excluded_branch_ids,
    )


# =============================================================================
# Audit Log Endpoints
# =============================================================================


class AuditLogOutput(BaseModel):
    """Output for audit log entry."""
    id: int
    user_id: int | None = None
    user_email: str | None = None
    entity_type: str
    entity_id: int
    action: str
    old_values: str | None = None
    new_values: str | None = None
    changes: str | None = None
    ip_address: str | None = None
    created_at: datetime


@router.get("/audit-log", response_model=list[AuditLogOutput])
def get_audit_log(
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[AuditLogOutput]:
    """
    Get audit log entries with optional filters.

    Filters:
    - entity_type: Filter by entity type (e.g., "product", "category")
    - entity_id: Filter by specific entity ID
    - action: Filter by action (CREATE, UPDATE, DELETE)
    - user_id: Filter by user who made the change
    """
    # Require ADMIN or MANAGER role
    user_roles = set(user.get("roles", []))
    if not user_roles.intersection({"ADMIN", "MANAGER"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN or MANAGER can view audit log",
        )

    query = select(AuditLog).where(AuditLog.tenant_id == user["tenant_id"])

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)

    entries = db.execute(query).scalars().all()

    return [
        AuditLogOutput(
            id=entry.id,
            user_id=entry.user_id,
            user_email=entry.user_email,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            action=entry.action,
            old_values=entry.old_values,
            new_values=entry.new_values,
            changes=entry.changes,
            ip_address=entry.ip_address,
            created_at=entry.created_at,
        )
        for entry in entries
    ]


# =============================================================================
# Waiter Sector Assignment Endpoints
# =============================================================================


@router.get("/assignments", response_model=BranchAssignmentOverview)
async def get_branch_assignments(
    branch_id: int,
    assignment_date: date,
    shift: str | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchAssignmentOverview:
    """
    Get all waiter-sector assignments for a branch on a given date.
    Returns sectors with their assigned waiters and unassigned waiters.
    """
    tenant_id = user["tenant_id"]

    # Get branch
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == tenant_id,
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    # Get all sectors for this branch (global + branch-specific)
    sectors = db.execute(
        select(BranchSector).where(
            BranchSector.tenant_id == tenant_id,
            BranchSector.is_active == True,
            or_(
                BranchSector.branch_id == branch_id,
                BranchSector.branch_id.is_(None),  # Global sectors
            ),
        ).order_by(BranchSector.display_order)
    ).scalars().all()

    # Get all waiters in this branch
    waiter_roles = db.execute(
        select(UserBranchRole).where(
            UserBranchRole.tenant_id == tenant_id,
            UserBranchRole.branch_id == branch_id,
            UserBranchRole.role == "WAITER",
        ).options(joinedload(UserBranchRole.user))
    ).scalars().unique().all()

    all_waiters = {
        role.user_id: {
            "id": role.user_id,
            "name": f"{role.user.first_name or ''} {role.user.last_name or ''}".strip(),
            "email": role.user.email,
        }
        for role in waiter_roles
        if role.user and role.user.is_active
    }

    # Get assignments for this date
    query = select(WaiterSectorAssignment).where(
        WaiterSectorAssignment.tenant_id == tenant_id,
        WaiterSectorAssignment.branch_id == branch_id,
        WaiterSectorAssignment.assignment_date == assignment_date,
        WaiterSectorAssignment.is_active == True,
    )
    if shift:
        query = query.where(
            or_(
                WaiterSectorAssignment.shift == shift,
                WaiterSectorAssignment.shift.is_(None),  # All-day assignments
            )
        )

    assignments = db.execute(query).scalars().all()

    # Build sector-to-waiters mapping
    sector_waiters: dict[int, list[dict]] = {s.id: [] for s in sectors}
    assigned_waiter_ids: set[int] = set()

    for assignment in assignments:
        if assignment.sector_id in sector_waiters and assignment.waiter_id in all_waiters:
            sector_waiters[assignment.sector_id].append(all_waiters[assignment.waiter_id])
            assigned_waiter_ids.add(assignment.waiter_id)

    # Build response
    sectors_with_waiters = [
        SectorWithWaiters(
            sector_id=s.id,
            sector_name=s.name,
            sector_prefix=s.prefix,
            waiters=sector_waiters.get(s.id, []),
        )
        for s in sectors
    ]

    unassigned_waiters = [
        waiter for waiter_id, waiter in all_waiters.items()
        if waiter_id not in assigned_waiter_ids
    ]

    return BranchAssignmentOverview(
        branch_id=branch_id,
        branch_name=branch.name,
        assignment_date=assignment_date,
        shift=shift,
        sectors=sectors_with_waiters,
        unassigned_waiters=unassigned_waiters,
    )


@router.post("/assignments/bulk", response_model=WaiterSectorBulkResult)
async def create_bulk_assignments(
    data: WaiterSectorBulkAssignment,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> WaiterSectorBulkResult:
    """
    Create multiple waiter-sector assignments at once.
    Skips duplicates (same waiter+sector+date+shift).

    Expected format:
    {
        "branch_id": 1,
        "assignment_date": "2026-01-10",
        "shift": null,
        "assignments": [
            {"sector_id": 1, "waiter_ids": [1, 2, 3]},
            {"sector_id": 2, "waiter_ids": [4, 5]}
        ]
    }
    """
    tenant_id = user["tenant_id"]
    user_id = int(user["sub"])
    user_email = user.get("email", "")

    # Verify branch exists
    branch = db.scalar(
        select(Branch).where(
            Branch.id == data.branch_id,
            Branch.tenant_id == tenant_id,
            Branch.is_active == True,
        )
    )
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    # Get valid sector IDs for this branch
    valid_sectors = db.execute(
        select(BranchSector).where(
            BranchSector.tenant_id == tenant_id,
            BranchSector.is_active == True,
            or_(
                BranchSector.branch_id == data.branch_id,
                BranchSector.branch_id.is_(None),
            ),
        )
    ).scalars().all()
    valid_sector_ids = {s.id for s in valid_sectors}
    sector_map = {s.id: s for s in valid_sectors}

    # Get valid waiter IDs for this branch
    waiter_roles = db.execute(
        select(UserBranchRole).where(
            UserBranchRole.tenant_id == tenant_id,
            UserBranchRole.branch_id == data.branch_id,
            UserBranchRole.role == "WAITER",
        ).options(joinedload(UserBranchRole.user))
    ).scalars().unique().all()
    valid_waiter_ids = {r.user_id for r in waiter_roles if r.user and r.user.is_active}
    waiter_map = {r.user_id: r.user for r in waiter_roles if r.user}

    # Get existing assignments to avoid duplicates
    existing = db.execute(
        select(WaiterSectorAssignment).where(
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.branch_id == data.branch_id,
            WaiterSectorAssignment.assignment_date == data.assignment_date,
            WaiterSectorAssignment.shift == data.shift,
            WaiterSectorAssignment.is_active == True,
        )
    ).scalars().all()
    existing_keys = {(a.sector_id, a.waiter_id) for a in existing}

    created: list[WaiterSectorAssignment] = []
    skipped = 0

    for assignment_group in data.assignments:
        sector_id = assignment_group.get("sector_id")
        waiter_ids = assignment_group.get("waiter_ids", [])

        if sector_id not in valid_sector_ids:
            skipped += len(waiter_ids)
            continue

        for waiter_id in waiter_ids:
            if waiter_id not in valid_waiter_ids:
                skipped += 1
                continue

            if (sector_id, waiter_id) in existing_keys:
                skipped += 1
                continue

            assignment = WaiterSectorAssignment(
                tenant_id=tenant_id,
                branch_id=data.branch_id,
                sector_id=sector_id,
                waiter_id=waiter_id,
                assignment_date=data.assignment_date,
                shift=data.shift,
            )
            set_created_by(assignment, user_id, user_email)
            db.add(assignment)
            created.append(assignment)
            existing_keys.add((sector_id, waiter_id))

    db.commit()

    # Refresh to get IDs
    for a in created:
        db.refresh(a)

    # Build output
    outputs = []
    for a in created:
        sector = sector_map.get(a.sector_id)
        waiter = waiter_map.get(a.waiter_id)
        if sector and waiter:
            outputs.append(WaiterSectorAssignmentOutput(
                id=a.id,
                tenant_id=a.tenant_id,
                branch_id=a.branch_id,
                sector_id=a.sector_id,
                sector_name=sector.name,
                sector_prefix=sector.prefix,
                waiter_id=a.waiter_id,
                waiter_name=f"{waiter.first_name or ''} {waiter.last_name or ''}".strip(),
                waiter_email=waiter.email,
                assignment_date=a.assignment_date,
                shift=a.shift,
                is_active=a.is_active,
            ))

    return WaiterSectorBulkResult(
        created_count=len(created),
        skipped_count=skipped,
        assignments=outputs,
    )


@router.delete("/assignments-bulk")
async def delete_bulk_assignments(
    branch_id: int,
    assignment_date: date,
    shift: str | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    """
    Delete all assignments for a branch on a given date (and optionally shift).
    Useful for clearing a day's assignments before reassigning.
    """
    tenant_id = user["tenant_id"]
    user_id = int(user["sub"])
    user_email = user.get("email", "")

    query = select(WaiterSectorAssignment).where(
        WaiterSectorAssignment.tenant_id == tenant_id,
        WaiterSectorAssignment.branch_id == branch_id,
        WaiterSectorAssignment.assignment_date == assignment_date,
        WaiterSectorAssignment.is_active == True,
    )
    if shift:
        query = query.where(WaiterSectorAssignment.shift == shift)

    assignments = db.execute(query).scalars().all()

    for a in assignments:
        soft_delete(db, a, user_id, user_email)

    db.commit()

    return {"message": f"Deleted {len(assignments)} assignments", "deleted_count": len(assignments)}


@router.delete("/assignments/{assignment_id}")
async def delete_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> dict:
    """Delete a single waiter-sector assignment."""
    tenant_id = user["tenant_id"]

    assignment = db.scalar(
        select(WaiterSectorAssignment).where(
            WaiterSectorAssignment.id == assignment_id,
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.is_active == True,
        )
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    soft_delete(db, assignment, int(user["sub"]), user.get("email", ""))
    db.commit()

    return {"message": "Assignment deleted", "id": assignment_id}


@router.post("/assignments/copy")
async def copy_assignments(
    branch_id: int,
    from_date: date,
    to_date: date,
    shift: str | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> WaiterSectorBulkResult:
    """
    Copy all assignments from one date to another.
    Useful for repeating yesterday's assignments.
    """
    tenant_id = user["tenant_id"]
    user_id = int(user["sub"])
    user_email = user.get("email", "")

    # Get source assignments
    query = select(WaiterSectorAssignment).where(
        WaiterSectorAssignment.tenant_id == tenant_id,
        WaiterSectorAssignment.branch_id == branch_id,
        WaiterSectorAssignment.assignment_date == from_date,
        WaiterSectorAssignment.is_active == True,
    )
    if shift:
        query = query.where(WaiterSectorAssignment.shift == shift)

    source_assignments = db.execute(query).scalars().all()

    if not source_assignments:
        return WaiterSectorBulkResult(created_count=0, skipped_count=0, assignments=[])

    # Check for existing assignments on target date
    existing = db.execute(
        select(WaiterSectorAssignment).where(
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.branch_id == branch_id,
            WaiterSectorAssignment.assignment_date == to_date,
            WaiterSectorAssignment.is_active == True,
        )
    ).scalars().all()
    existing_keys = {(a.sector_id, a.waiter_id, a.shift) for a in existing}

    # Get sector and waiter info for output
    sector_ids = {a.sector_id for a in source_assignments}
    waiter_ids = {a.waiter_id for a in source_assignments}

    sectors = db.execute(
        select(BranchSector).where(BranchSector.id.in_(sector_ids))
    ).scalars().all()
    sector_map = {s.id: s for s in sectors}

    waiters = db.execute(
        select(User).where(User.id.in_(waiter_ids))
    ).scalars().all()
    waiter_map = {w.id: w for w in waiters}

    created: list[WaiterSectorAssignment] = []
    skipped = 0

    for src in source_assignments:
        if (src.sector_id, src.waiter_id, src.shift) in existing_keys:
            skipped += 1
            continue

        new_assignment = WaiterSectorAssignment(
            tenant_id=tenant_id,
            branch_id=branch_id,
            sector_id=src.sector_id,
            waiter_id=src.waiter_id,
            assignment_date=to_date,
            shift=src.shift,
        )
        set_created_by(new_assignment, user_id, user_email)
        db.add(new_assignment)
        created.append(new_assignment)

    db.commit()

    for a in created:
        db.refresh(a)

    outputs = []
    for a in created:
        sector = sector_map.get(a.sector_id)
        waiter = waiter_map.get(a.waiter_id)
        if sector and waiter:
            outputs.append(WaiterSectorAssignmentOutput(
                id=a.id,
                tenant_id=a.tenant_id,
                branch_id=a.branch_id,
                sector_id=a.sector_id,
                sector_name=sector.name,
                sector_prefix=sector.prefix,
                waiter_id=a.waiter_id,
                waiter_name=f"{waiter.first_name or ''} {waiter.last_name or ''}".strip(),
                waiter_email=waiter.email,
                assignment_date=a.assignment_date,
                shift=a.shift,
                is_active=a.is_active,
            ))

    return WaiterSectorBulkResult(
        created_count=len(created),
        skipped_count=skipped,
        assignments=outputs,
    )
