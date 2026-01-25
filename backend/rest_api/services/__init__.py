"""
Services module for business logic.

CLEAN ARCHITECTURE:
- domain/: Application services (business logic) - USE THESE
- crud/: Repository pattern, soft delete, audit
- payments/: Payment processing and external integrations
- catalog/: Product catalog and content management
- rag/: AI chatbot and retrieval-augmented generation
- events/: Real-time event publishing
- permissions/: Strategy pattern for role-based access control

Usage:
    # PREFERRED: Use domain services (Clean Architecture)
    from rest_api.services.domain import CategoryService
    service = CategoryService(db)
    categories = service.list_by_branch(tenant_id, branch_id)

    # DEPRECATED: CRUDFactory (will be removed in future version)
    from rest_api.services.crud import CRUDFactory  # Use domain services instead
"""

# RAG Service (most commonly used)
from .rag import RAGService, ollama_client

# Payment allocation (commonly used in billing)
from .payments import (
    create_charges_for_check,
    allocate_payment_fifo,
    get_diner_balance,
    get_all_diner_balances,
)

# CRUD utilities (commonly used in admin routers)
from .crud import (
    CRUDFactory,
    CRUDConfig,
    EntityOutputBuilder,
    build_output,
    soft_delete,
    restore_entity,
    set_created_by,
    set_updated_by,
    log_change,
    # CRIT-01 FIX: Cascade delete with audit preservation
    CascadeDeleteService,
    get_cascade_delete_service,
)

# Catalog/Product view (commonly used)
from .catalog import (
    get_product_complete,
    get_products_complete_for_branch,
    generate_product_text_for_rag,
    generate_recipe_text_for_rag,
    sync_product_from_recipe,
)

# Events (commonly used in admin routers)
from .events import (
    publish_entity_created,
    publish_entity_updated,
    publish_entity_deleted,
    publish_cascade_delete,
    # New typed event API
    DomainEvent,
    EventType,
    EventPublisher,
    get_event_publisher,
)

# Circuit breaker and webhooks (less common, import from submodule)
from .payments import (
    CircuitBreaker,
    CircuitBreakerError,
    mercadopago_breaker,
    webhook_retry_queue,
    handle_mp_webhook_retry,
)

# NEW: Permission Strategy Pattern
from .permissions import (
    PermissionContext,
    Action,
    PermissionStrategy,
    AdminStrategy,
    ManagerStrategy,
    require_permission,
    require_admin,
    require_management,
)

# CLEAN ARCHITECTURE: Domain Services (PREFERRED)
from .domain import (
    CategoryService,
    SubcategoryService,
    BranchService,
    TableService,
    SectorService,
)

# Base service classes for creating new domain services
from .base_service import (
    BaseService,
    BaseCRUDService,
    BranchScopedService,
)

__all__ = [
    # RAG
    "RAGService",
    "ollama_client",
    # Payments
    "create_charges_for_check",
    "allocate_payment_fifo",
    "get_diner_balance",
    "get_all_diner_balances",
    "CircuitBreaker",
    "CircuitBreakerError",
    "mercadopago_breaker",
    "webhook_retry_queue",
    "handle_mp_webhook_retry",
    # CRUD
    "CRUDFactory",
    "CRUDConfig",
    "EntityOutputBuilder",
    "build_output",
    "soft_delete",
    "restore_entity",
    "set_created_by",
    "set_updated_by",
    "log_change",
    "CascadeDeleteService",
    "get_cascade_delete_service",
    # Catalog
    "get_product_complete",
    "get_products_complete_for_branch",
    "generate_product_text_for_rag",
    "generate_recipe_text_for_rag",
    "sync_product_from_recipe",
    # Events
    "publish_entity_created",
    "publish_entity_updated",
    "publish_entity_deleted",
    "publish_cascade_delete",
    "DomainEvent",
    "EventType",
    "EventPublisher",
    "get_event_publisher",
    # Permissions (NEW)
    "PermissionContext",
    "Action",
    "PermissionStrategy",
    "AdminStrategy",
    "ManagerStrategy",
    "require_permission",
    "require_admin",
    "require_management",
    # CLEAN ARCHITECTURE: Domain Services (PREFERRED)
    "CategoryService",
    "SubcategoryService",
    "BranchService",
    "TableService",
    "SectorService",
    # Base service classes
    "BaseService",
    "BaseCRUDService",
    "BranchScopedService",
]
