"""
Admin API router - combines all admin sub-routers.

This module provides a single router that includes all admin endpoints
organized by domain:

- tenant: Restaurant/tenant info and settings
- branches: Branch CRUD operations
- categories: Category CRUD operations
- subcategories: Subcategory CRUD operations
- products: Product CRUD with canonical model (Phases 0-4)
- allergens: Allergen CRUD with cross-reactions
- staff: Staff management with branch access control
- tables: Table CRUD with batch creation
- sectors: Sector management
- orders: Active orders and stats
- exclusions: Branch category/subcategory exclusions
- assignments: Daily waiter-sector assignments
- reports: Sales analytics and statistics
- audit: Audit log viewing
- restore: Entity restoration

All routes are prefixed with /api/admin
"""

from fastapi import APIRouter

from .tenant import router as tenant_router
from .branches import router as branches_router
from .categories import router as categories_router
from .subcategories import router as subcategories_router
from .products import router as products_router
from .allergens import router as allergens_router
from .staff import router as staff_router
from .tables import router as tables_router
from .sectors import router as sectors_router
from .orders import router as orders_router
from .exclusions import router as exclusions_router
from .assignments import router as assignments_router
from .reports import router as reports_router
from .audit import router as audit_router
from .restore import router as restore_router


# Create the main admin router
router = APIRouter()

# Include all sub-routers
# Note: Order matters for route matching - more specific routes first

# Core entity management
router.include_router(tenant_router)
router.include_router(branches_router)
router.include_router(categories_router)
router.include_router(subcategories_router)
router.include_router(products_router)
router.include_router(allergens_router)

# Staff and resource management
router.include_router(staff_router)
router.include_router(tables_router)
router.include_router(sectors_router)

# Operations and orders
router.include_router(orders_router)

# Branch configuration
router.include_router(exclusions_router)
router.include_router(assignments_router)

# Analytics and reporting
router.include_router(reports_router)

# Audit and restore (generic endpoints)
router.include_router(audit_router)
router.include_router(restore_router)


__all__ = ["router"]
