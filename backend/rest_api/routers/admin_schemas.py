"""
Pydantic schemas for admin API endpoints.
Centralized to avoid circular imports and improve maintainability.

This file contains all request/response schemas used by admin routers.
"""

from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


# =============================================================================
# Tenant Schemas
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


# =============================================================================
# Branch Schemas
# =============================================================================


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


# =============================================================================
# Category Schemas
# =============================================================================


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


# =============================================================================
# Subcategory Schemas
# =============================================================================


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


# =============================================================================
# Product Schemas
# =============================================================================


class BranchPriceOutput(BaseModel):
    branch_id: int
    price_cents: int
    is_available: bool


class BranchPriceInput(BaseModel):
    branch_id: int
    price_cents: int
    is_available: bool = True


class ProductIngredientInput(BaseModel):
    """Input for product ingredient relationship."""
    ingredient_id: int
    is_main: bool = False
    notes: str | None = None


class DietaryProfileInput(BaseModel):
    """Input for product dietary profile."""
    is_vegetarian: bool = False
    is_vegan: bool = False
    is_gluten_free: bool = False
    is_dairy_free: bool = False
    is_celiac_safe: bool = False
    is_keto: bool = False
    is_low_sodium: bool = False


class CookingInfoInput(BaseModel):
    """Input for product cooking information."""
    cooking_method_ids: list[int] = []
    uses_oil: bool = False
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None


class SensoryProfileInput(BaseModel):
    """Input for product sensory profile."""
    flavor_ids: list[int] = []
    texture_ids: list[int] = []


class ModificationInput(BaseModel):
    """Input for product modification."""
    action: str  # "remove" or "substitute"
    item: str
    is_allowed: bool = True
    extra_cost_cents: int = 0


class WarningInput(BaseModel):
    """Input for product warning."""
    text: str
    severity: str = "info"  # info, warning, danger


class RAGConfigInput(BaseModel):
    """Input for product RAG chatbot configuration."""
    risk_level: str = "low"  # low, medium, high
    custom_disclaimer: str | None = None
    highlight_allergens: bool = True


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
    allergen_ids: list[int] = []
    allergens: list[AllergenPresenceOutput] = []
    recipe_id: int | None = None
    inherits_from_recipe: bool = False
    recipe_name: str | None = None
    is_active: bool
    created_at: datetime
    branch_prices: list[BranchPriceOutput] = []

    class Config:
        from_attributes = True


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
    allergen_ids: list[int] = []
    allergens: list[AllergenPresenceInput] = []
    is_active: bool = True
    branch_prices: list[BranchPriceInput] = []
    recipe_id: int | None = None
    inherits_from_recipe: bool = False
    ingredients: list[ProductIngredientInput] = []
    dietary_profile: DietaryProfileInput | None = None
    cooking_info: CookingInfoInput | None = None
    sensory_profile: SensoryProfileInput | None = None
    modifications: list[ModificationInput] = []
    warnings: list[WarningInput] = []
    rag_config: RAGConfigInput | None = None


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
    allergen_ids: list[int] | None = None
    allergens: list[AllergenPresenceInput] | None = None
    is_active: bool | None = None
    branch_prices: list[BranchPriceInput] | None = None
    recipe_id: int | None = None
    inherits_from_recipe: bool | None = None
    ingredients: list[ProductIngredientInput] | None = None
    dietary_profile: DietaryProfileInput | None = None
    cooking_info: CookingInfoInput | None = None
    sensory_profile: SensoryProfileInput | None = None
    modifications: list[ModificationInput] | None = None
    warnings: list[WarningInput] | None = None
    rag_config: RAGConfigInput | None = None


# =============================================================================
# Allergen Schemas
# =============================================================================


class CrossReactionInfo(BaseModel):
    """Cross-reaction summary for allergen output."""
    id: int
    cross_reacts_with_id: int
    cross_reacts_with_name: str
    probability: str
    notes: str | None = None


class AllergenOutput(BaseModel):
    id: int
    tenant_id: int
    name: str
    icon: str | None = None
    description: str | None = None
    is_mandatory: bool = False
    severity: str = "moderate"
    is_active: bool
    cross_reactions: list[CrossReactionInfo] | None = None

    class Config:
        from_attributes = True


class AllergenCreate(BaseModel):
    name: str
    icon: str | None = None
    description: str | None = None
    is_mandatory: bool = False
    severity: str = "moderate"
    is_active: bool = True


class AllergenUpdate(BaseModel):
    name: str | None = None
    icon: str | None = None
    description: str | None = None
    is_mandatory: bool | None = None
    severity: str | None = None
    is_active: bool | None = None


class CrossReactionCreate(BaseModel):
    """Create a cross-reaction between two allergens."""
    allergen_id: int
    cross_reacts_with_id: int
    probability: str = "medium"
    notes: str | None = None


class CrossReactionUpdate(BaseModel):
    """Update a cross-reaction."""
    probability: str | None = None
    notes: str | None = None


class CrossReactionOutput(BaseModel):
    """Full cross-reaction output."""
    id: int
    tenant_id: int
    allergen_id: int
    allergen_name: str
    cross_reacts_with_id: int
    cross_reacts_with_name: str
    probability: str
    notes: str | None = None
    is_active: bool

    class Config:
        from_attributes = True


# =============================================================================
# Table Schemas
# =============================================================================


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
    is_global: bool = False

    class Config:
        from_attributes = True


class BranchSectorCreate(BaseModel):
    branch_id: int | None = None
    name: str
    prefix: str


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
    capacity: int
    count: int


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
    shift: str | None = None


class WaiterSectorBulkAssignment(BaseModel):
    """Bulk assignment: assign multiple waiters to multiple sectors."""
    branch_id: int
    assignment_date: date
    shift: str | None = None
    assignments: list[dict]


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
    waiters: list[dict]


class BranchAssignmentOverview(BaseModel):
    """Overview of all sector assignments for a branch on a given date."""
    branch_id: int
    branch_name: str
    assignment_date: date
    shift: str | None = None
    sectors: list[SectorWithWaiters]
    unassigned_waiters: list[dict]


# =============================================================================
# Staff Schemas
# =============================================================================


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
    branch_roles: list[dict] = []


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
    branch_ids: list[int]


class ExclusionBulkUpdate(BaseModel):
    """Bulk update exclusions for a category or subcategory."""
    excluded_branch_ids: list[int]


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
# Order Schemas
# =============================================================================


class OrderItemOutput(BaseModel):
    """Order item output for active orders list."""
    product_id: int
    product_name: str
    qty: int
    unit_price_cents: int
    notes: str | None = None
    diner_id: int | None = None
    diner_name: str | None = None


class ActiveOrderOutput(BaseModel):
    """Active order (round) output."""
    id: int
    round_number: int
    status: str
    table_id: int
    table_code: str
    session_id: int
    items: list[OrderItemOutput]
    submitted_at: datetime | None = None
    created_at: datetime


class OrderStatsOutput(BaseModel):
    """Order statistics output."""
    total_orders_today: int
    pending_orders: int
    in_kitchen_orders: int
    ready_orders: int
    served_orders: int
    total_revenue_today_cents: int


# =============================================================================
# Report Schemas
# =============================================================================


class DailySalesOutput(BaseModel):
    """Daily sales data point."""
    date: str
    total_cents: int
    order_count: int


class TopProductOutput(BaseModel):
    """Top selling product."""
    product_id: int
    product_name: str
    quantity_sold: int
    revenue_cents: int


class ReportsSummaryOutput(BaseModel):
    """Summary of reports."""
    total_revenue_cents: int
    total_orders: int
    average_order_cents: int
    top_products: list[TopProductOutput]


class SalesReportOutput(BaseModel):
    """Full sales report."""
    start_date: str
    end_date: str
    daily_sales: list[DailySalesOutput]
    summary: ReportsSummaryOutput


# =============================================================================
# Restore Schemas
# =============================================================================


class RestoreOutput(BaseModel):
    """Result of entity restoration."""
    success: bool
    message: str
    entity_type: str
    entity_id: int


# =============================================================================
# Audit Log Schemas
# =============================================================================


class AuditLogOutput(BaseModel):
    """Audit log entry output."""
    id: int
    tenant_id: int
    user_id: int | None = None
    user_email: str | None = None
    action: str
    entity_type: str
    entity_id: int | None = None
    old_values: dict | None = None
    new_values: dict | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime

    class Config:
        from_attributes = True
