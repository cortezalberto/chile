"""
Domain Services - Clean Architecture Application Layer.

CLEAN-ARCH: Services contain business logic and orchestrate operations.
They use Repositories for data access and emit domain events.

Structure:
    Router (thin controller)
        ↓
    Service (business logic)  ← YOU ARE HERE
        ↓
    Repository (data access)
        ↓
    Model (entity)

Usage:
    from rest_api.services.domain import CategoryService

    # In router
    service = CategoryService(db)
    categories = service.list_by_branch(tenant_id, branch_id)
"""

from .category_service import CategoryService
from .subcategory_service import SubcategoryService
from .branch_service import BranchService
from .table_service import TableService
from .sector_service import SectorService
from .product_service import ProductService
from .allergen_service import AllergenService
from .staff_service import StaffService
from .promotion_service import PromotionService
from .ticket_service import TicketService

# CRIT-01 FIX: New domain services for thin controller pattern
from .round_service import RoundService
from .service_call_service import ServiceCallService
from .billing_service import BillingService
from .diner_service import DinerService

__all__ = [
    # Existing services
    "CategoryService",
    "SubcategoryService",
    "BranchService",
    "TableService",
    "SectorService",
    "ProductService",
    "AllergenService",
    "StaffService",
    "PromotionService",
    "TicketService",
    # CRIT-01: New domain services
    "RoundService",
    "ServiceCallService",
    "BillingService",
    "DinerService",
]
