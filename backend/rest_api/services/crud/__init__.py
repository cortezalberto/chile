"""
CRUD Services - Generic operations for entity management.

Provides:
- CRUDFactory: Generic CRUD operations with tenant isolation
- EntityOutputBuilder: Convert SQLAlchemy models to Pydantic schemas
- soft_delete: Soft delete with audit trail
- CascadeDeleteService: Cascade soft delete with audit preservation
- log_change: Audit logging service
- Repository Pattern: Type-safe data access with tenant isolation (ARCH-OPP-06)
"""

from .factory import CRUDFactory, CRUDConfig
from .entity_builder import EntityOutputBuilder, build_output
from .repository import (
    BaseRepository,
    TenantRepository,
    BranchRepository,
    SpecificationRepository,
    Specification,
    AndSpecification,
    OrSpecification,
    NotSpecification,
    get_repository,
)
from .soft_delete import (
    soft_delete,
    restore_entity,
    set_created_by,
    set_updated_by,
    get_model_class,
    find_active_entity,
    find_deleted_entity,
    filter_active,
    MODEL_MAP,
)
from .cascade_delete import CascadeDeleteService, get_cascade_delete_service
from .audit import (
    log_change,
    log_create,
    log_update,
    log_delete,
    serialize_model,
)

__all__ = [
    # Factory
    "CRUDFactory",
    "CRUDConfig",
    # Entity builder
    "EntityOutputBuilder",
    "build_output",
    # Repository Pattern (ARCH-OPP-06)
    "BaseRepository",
    "TenantRepository",
    "BranchRepository",
    "SpecificationRepository",
    "Specification",
    "AndSpecification",
    "OrSpecification",
    "NotSpecification",
    "get_repository",
    # Soft delete
    "soft_delete",
    "restore_entity",
    "set_created_by",
    "set_updated_by",
    "get_model_class",
    "find_active_entity",
    "find_deleted_entity",
    "filter_active",
    "MODEL_MAP",
    # Cascade delete (CRIT-01 FIX)
    "CascadeDeleteService",
    "get_cascade_delete_service",
    # Audit
    "log_change",
    "log_create",
    "log_update",
    "log_delete",
    "serialize_model",
]
