"""
Generic CRUD Factory for Admin Routers.

DEPRECATED: Use domain services instead for Clean Architecture compliance.
See rest_api/services/domain/ for the new pattern.

Migration example:
    # OLD (deprecated):
    crud = CRUDFactory(CRUDConfig(model=Category, ...))
    return crud.list_all(db, tenant_id)

    # NEW (preferred - Clean Architecture):
    from rest_api.services.domain import CategoryService
    service = CategoryService(db)
    return service.list_all(tenant_id)

This module is kept for backward compatibility. Existing routers
will continue to work, but new code should use domain services.
"""

from typing import Any, TypeVar, Type, Generic, Callable
from dataclasses import dataclass, field
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import select, Select
from fastapi import HTTPException, status

from shared.infrastructure.db import safe_commit
from .soft_delete import soft_delete, set_created_by, set_updated_by
from shared.config.logging import get_logger
from shared.utils.exceptions import NotFoundError, ForbiddenError, DatabaseError, ValidationError
from shared.utils.validators import validate_image_url

logger = get_logger(__name__)

# Type variables
ModelT = TypeVar("ModelT")
OutputT = TypeVar("OutputT", bound=BaseModel)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


@dataclass
class CRUDConfig(Generic[ModelT, OutputT, CreateT, UpdateT]):
    """Configuration for CRUD factory."""

    # Required
    model: Type[ModelT]
    output_schema: Type[OutputT]
    create_schema: Type[CreateT]
    update_schema: Type[UpdateT]
    entity_name: str  # Human-readable name for error messages (Spanish)

    # Optional customization
    tenant_field: str = "tenant_id"
    is_active_field: str = "is_active"
    default_order_by: str = "name"  # Field to order by in list operations

    # Branch isolation (if entity has branch_id)
    has_branch_id: bool = False
    branch_field: str = "branch_id"

    # Soft delete support
    supports_soft_delete: bool = True

    # Custom output builder (if entity needs special handling)
    output_builder: Callable[[Any, Session], OutputT] | None = None

    # Fields to exclude from auto-update
    exclude_from_update: set[str] = field(default_factory=set)

    # HIGH-04 FIX: Image URL fields that need SSRF validation
    image_url_fields: set[str] = field(default_factory=lambda: {"image"})

    # Pagination defaults
    default_limit: int = 50
    max_limit: int = 200


class CRUDFactory(Generic[ModelT, OutputT, CreateT, UpdateT]):
    """
    Generic CRUD operations factory.

    Provides consistent implementations for:
    - List with filtering, pagination, tenant isolation
    - Get by ID with tenant/branch validation
    - Create with audit trail
    - Update with audit trail
    - Soft delete with audit trail
    """

    def __init__(self, config: CRUDConfig[ModelT, OutputT, CreateT, UpdateT]):
        self.config = config
        self.model = config.model
        self.output_schema = config.output_schema
        self.entity_name = config.entity_name

    # =========================================================================
    # List Operations
    # =========================================================================

    def list_all(
        self,
        db: Session,
        tenant_id: int,
        include_deleted: bool = False,
        branch_id: int | None = None,
        user_branch_ids: list[int] | None = None,
        filters: dict[str, Any] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[OutputT]:
        """
        List entities with filtering and pagination.

        Args:
            db: Database session
            tenant_id: Tenant ID for isolation
            include_deleted: Include soft-deleted entities
            branch_id: Filter by specific branch
            user_branch_ids: User's accessible branches (for branch filtering)
            filters: Additional filters as {field_name: value}
            limit: Max results (defaults to config.default_limit)
            offset: Offset for pagination

        Returns:
            List of output schemas
        """
        query = self._base_query(tenant_id, include_deleted)

        # Branch filtering
        if self.config.has_branch_id:
            if branch_id:
                # Validate branch access if user_branch_ids provided
                if user_branch_ids and branch_id not in user_branch_ids:
                    raise ForbiddenError("acceder a esta sucursal", branch_id=branch_id)
                query = query.where(getattr(self.model, self.config.branch_field) == branch_id)
            elif user_branch_ids:
                # Filter to user's accessible branches
                query = query.where(getattr(self.model, self.config.branch_field).in_(user_branch_ids))

        # Apply additional filters
        if filters:
            for field_name, value in filters.items():
                if hasattr(self.model, field_name) and value is not None:
                    query = query.where(getattr(self.model, field_name) == value)

        # Order and pagination
        if hasattr(self.model, self.config.default_order_by):
            query = query.order_by(getattr(self.model, self.config.default_order_by))

        limit = min(limit or self.config.default_limit, self.config.max_limit)
        query = query.offset(offset).limit(limit)

        entities = db.execute(query).scalars().all()
        return [self._to_output(e, db) for e in entities]

    # =========================================================================
    # Get Operations
    # =========================================================================

    def get_by_id(
        self,
        db: Session,
        entity_id: int,
        tenant_id: int,
        user_branch_ids: list[int] | None = None,
        include_deleted: bool = False,
    ) -> OutputT:
        """
        Get entity by ID with tenant validation.

        Args:
            db: Database session
            entity_id: Entity ID
            tenant_id: Tenant ID for isolation
            user_branch_ids: User's accessible branches (for branch validation)
            include_deleted: Include soft-deleted entities

        Returns:
            Output schema

        Raises:
            NotFoundError: If entity not found
            ForbiddenError: If user doesn't have branch access
        """
        entity = self._get_entity(db, entity_id, tenant_id, include_deleted)

        if entity is None:
            raise NotFoundError(self.entity_name, entity_id, tenant_id=tenant_id)

        # Validate branch access if applicable
        if self.config.has_branch_id and user_branch_ids:
            entity_branch_id = getattr(entity, self.config.branch_field)
            if entity_branch_id not in user_branch_ids:
                raise ForbiddenError(f"acceder a este {self.entity_name.lower()}", branch_id=entity_branch_id)

        return self._to_output(entity, db)

    def get_entity(
        self,
        db: Session,
        entity_id: int,
        tenant_id: int,
        include_deleted: bool = False,
    ) -> ModelT | None:
        """
        Get raw entity (for internal use).

        Returns the SQLAlchemy model instance, not the Pydantic output.
        """
        return self._get_entity(db, entity_id, tenant_id, include_deleted)

    # =========================================================================
    # Create Operations
    # =========================================================================

    def create(
        self,
        db: Session,
        data: CreateT,
        tenant_id: int,
        user_id: int,
        user_email: str,
        user_branch_ids: list[int] | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> OutputT:
        """
        Create new entity.

        Args:
            db: Database session
            data: Create schema with entity data
            tenant_id: Tenant ID
            user_id: Creating user ID
            user_email: Creating user email
            user_branch_ids: User's accessible branches (for branch validation)
            extra_fields: Additional fields to set on entity

        Returns:
            Output schema for created entity

        Raises:
            ForbiddenError: If user doesn't have branch access
            DatabaseError: If creation fails
        """
        # Convert Pydantic model to dict
        entity_data = data.model_dump()

        # HIGH-04 FIX: Validate image URLs to prevent SSRF attacks
        entity_data = self._validate_image_urls(entity_data)

        # Validate branch access if applicable
        if self.config.has_branch_id and user_branch_ids:
            branch_id = entity_data.get(self.config.branch_field)
            if branch_id and branch_id not in user_branch_ids:
                raise ForbiddenError("crear en esta sucursal", branch_id=branch_id)

        # Add tenant_id
        entity_data[self.config.tenant_field] = tenant_id

        # Add extra fields
        if extra_fields:
            entity_data.update(extra_fields)

        # Create entity
        entity = self.model(**entity_data)
        set_created_by(entity, user_id, user_email)

        db.add(entity)

        try:
            safe_commit(db)
            db.refresh(entity)
        except Exception as e:
            logger.error(f"Failed to create {self.entity_name}", error=str(e), tenant_id=tenant_id)
            raise DatabaseError(f"crear {self.entity_name.lower()}")

        return self._to_output(entity, db)

    # =========================================================================
    # Update Operations
    # =========================================================================

    def update(
        self,
        db: Session,
        entity_id: int,
        data: UpdateT,
        tenant_id: int,
        user_id: int,
        user_email: str,
        user_branch_ids: list[int] | None = None,
    ) -> OutputT:
        """
        Update existing entity.

        Args:
            db: Database session
            entity_id: Entity ID
            data: Update schema with changed fields
            tenant_id: Tenant ID
            user_id: Updating user ID
            user_email: Updating user email
            user_branch_ids: User's accessible branches (for branch validation)

        Returns:
            Output schema for updated entity

        Raises:
            NotFoundError: If entity not found
            ForbiddenError: If user doesn't have access
            DatabaseError: If update fails
        """
        entity = self._get_entity(db, entity_id, tenant_id, include_deleted=False)

        if entity is None:
            raise NotFoundError(self.entity_name, entity_id, tenant_id=tenant_id)

        # Validate branch access if applicable
        if self.config.has_branch_id and user_branch_ids:
            entity_branch_id = getattr(entity, self.config.branch_field)
            if entity_branch_id not in user_branch_ids:
                raise ForbiddenError(f"modificar este {self.entity_name.lower()}", branch_id=entity_branch_id)

        # Update fields
        update_data = data.model_dump(exclude_unset=True)

        # HIGH-04 FIX: Validate image URLs to prevent SSRF attacks
        update_data = self._validate_image_urls(update_data)

        for field_name, value in update_data.items():
            if field_name not in self.config.exclude_from_update:
                if hasattr(entity, field_name):
                    setattr(entity, field_name, value)

        set_updated_by(entity, user_id, user_email)

        try:
            safe_commit(db)
            db.refresh(entity)
        except Exception as e:
            logger.error(f"Failed to update {self.entity_name}", error=str(e), entity_id=entity_id)
            raise DatabaseError(f"actualizar {self.entity_name.lower()}")

        return self._to_output(entity, db)

    # =========================================================================
    # Delete Operations
    # =========================================================================

    def delete(
        self,
        db: Session,
        entity_id: int,
        tenant_id: int,
        user_id: int,
        user_email: str,
        user_branch_ids: list[int] | None = None,
    ) -> None:
        """
        Soft delete entity.

        Args:
            db: Database session
            entity_id: Entity ID
            tenant_id: Tenant ID
            user_id: Deleting user ID
            user_email: Deleting user email
            user_branch_ids: User's accessible branches (for branch validation)

        Raises:
            NotFoundError: If entity not found
            ForbiddenError: If user doesn't have access
        """
        entity = self._get_entity(db, entity_id, tenant_id, include_deleted=False)

        if entity is None:
            raise NotFoundError(self.entity_name, entity_id, tenant_id=tenant_id)

        # Validate branch access if applicable
        if self.config.has_branch_id and user_branch_ids:
            entity_branch_id = getattr(entity, self.config.branch_field)
            if entity_branch_id not in user_branch_ids:
                raise ForbiddenError(f"eliminar este {self.entity_name.lower()}", branch_id=entity_branch_id)

        if self.config.supports_soft_delete:
            soft_delete(db, entity, user_id, user_email)
        else:
            db.delete(entity)
            safe_commit(db)

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _base_query(self, tenant_id: int, include_deleted: bool = False) -> Select:
        """Build base query with tenant isolation."""
        query = select(self.model).where(
            getattr(self.model, self.config.tenant_field) == tenant_id
        )

        # HIGH-03 FIX: Use .is_(True) instead of == True for proper SQL generation
        if not include_deleted and self.config.supports_soft_delete:
            query = query.where(getattr(self.model, self.config.is_active_field).is_(True))

        return query

    def _get_entity(
        self,
        db: Session,
        entity_id: int,
        tenant_id: int,
        include_deleted: bool = False,
    ) -> ModelT | None:
        """Get entity by ID."""
        query = self._base_query(tenant_id, include_deleted).where(
            self.model.id == entity_id
        )
        return db.scalar(query)

    def _to_output(self, entity: ModelT, db: Session) -> OutputT:
        """Convert entity to output schema."""
        if self.config.output_builder:
            return self.config.output_builder(entity, db)

        # Default: auto-map fields
        return self.output_schema.model_validate(entity)

    def _validate_image_urls(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        HIGH-04 FIX: Validate and sanitize image URL fields to prevent SSRF attacks.

        Args:
            data: Entity data dictionary

        Returns:
            Data with validated image URLs

        Raises:
            ValidationError: If any image URL fails validation
        """
        for field_name in self.config.image_url_fields:
            if field_name in data and data[field_name]:
                try:
                    data[field_name] = validate_image_url(data[field_name])
                except ValueError as e:
                    raise ValidationError(str(e), field=field_name)
        return data


# =============================================================================
# Pre-configured CRUD Factories (examples)
# =============================================================================

# Note: These are lazy-initialized to avoid circular imports
# Usage:
#   from rest_api.services.crud_factory import get_category_crud
#   crud = get_category_crud()

_category_crud: CRUDFactory | None = None


def get_category_crud() -> CRUDFactory:
    """Get or create Category CRUD factory."""
    global _category_crud
    if _category_crud is None:
        from rest_api.models import Category
        from shared.utils.admin_schemas import CategoryOutput, CategoryCreate, CategoryUpdate

        _category_crud = CRUDFactory(
            CRUDConfig(
                model=Category,
                output_schema=CategoryOutput,
                create_schema=CategoryCreate,
                update_schema=CategoryUpdate,
                entity_name="Categoría",
                has_branch_id=False,
            )
        )
    return _category_crud
