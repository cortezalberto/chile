"""
Base Service Classes for Clean Architecture.

CLEAN-ARCH: Provides abstract base classes for application services that:
- Use Repository for data access (not direct queries)
- Use EntityOutputBuilder for DTO transformation
- Handle business logic and orchestration
- Integrate with audit logging

Architecture:
    Router (thin) → Service (business logic) → Repository (data access) → Model

Usage:
    from rest_api.services.base_service import BaseService, BaseCRUDService

    class CategoryService(BaseCRUDService[Category, CategoryOutput]):
        def __init__(self, db: Session):
            super().__init__(
                db=db,
                model=Category,
                output_schema=CategoryOutput,
                entity_name="Categoría",
            )

        def list_by_branch(self, tenant_id: int, branch_id: int) -> list[CategoryOutput]:
            entities = self.repo.find_all(
                tenant_id=tenant_id,
                order_by=Category.order,
            )
            return [self.to_output(e) for e in entities if e.branch_id == branch_id]
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Sequence, TypeVar, Type

from pydantic import BaseModel
from sqlalchemy.orm import Session

from rest_api.models import Base
from rest_api.services.crud.repository import TenantRepository, BranchRepository
from rest_api.services.crud.soft_delete import soft_delete, set_created_by, set_updated_by
from rest_api.services.crud.audit import log_create, log_update, log_delete
from shared.infrastructure.db import safe_commit
from shared.config.logging import get_logger
from shared.utils.exceptions import NotFoundError, ForbiddenError, DatabaseError, ValidationError
from shared.utils.validators import validate_image_url

logger = get_logger(__name__)

ModelT = TypeVar("ModelT", bound=Base)
OutputT = TypeVar("OutputT", bound=BaseModel)
CreateT = TypeVar("CreateT", bound=BaseModel)
UpdateT = TypeVar("UpdateT", bound=BaseModel)


class BaseService(ABC, Generic[ModelT]):
    """
    Abstract base service for domain operations.

    Subclasses implement specific business logic while this class
    provides common infrastructure (repository access, logging).
    """

    def __init__(self, db: Session, model: Type[ModelT]):
        self._db = db
        self._model = model
        self._repo = TenantRepository(model, db)

    @property
    def db(self) -> Session:
        """Database session."""
        return self._db

    @property
    def repo(self) -> TenantRepository[ModelT]:
        """Repository for data access."""
        return self._repo


class BaseCRUDService(BaseService[ModelT], Generic[ModelT, OutputT]):
    """
    Base service for entities with CRUD operations.

    Provides standard CRUD methods that can be overridden for
    custom business logic. Uses Repository for all data access.

    Responsibilities:
    - Data access via Repository (not direct queries)
    - DTO transformation via output schema
    - Audit trail for mutations
    - Business rule validation
    - Event publishing hooks
    """

    def __init__(
        self,
        db: Session,
        model: Type[ModelT],
        output_schema: Type[OutputT],
        entity_name: str,
        *,
        has_branch_id: bool = False,
        supports_soft_delete: bool = True,
        image_url_fields: set[str] | None = None,
    ):
        super().__init__(db, model)
        self._output_schema = output_schema
        self._entity_name = entity_name
        self._has_branch_id = has_branch_id
        self._supports_soft_delete = supports_soft_delete
        self._image_url_fields = image_url_fields or {"image"}

        # Use BranchRepository if entity has branch_id
        if has_branch_id:
            self._repo = BranchRepository(model, db)

    @property
    def entity_name(self) -> str:
        """Human-readable entity name for messages."""
        return self._entity_name

    # =========================================================================
    # Read Operations
    # =========================================================================

    def get_by_id(
        self,
        entity_id: int,
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
    ) -> OutputT:
        """
        Get entity by ID.

        Args:
            entity_id: Entity primary key.
            tenant_id: Tenant ID for isolation.
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.

        Returns:
            Output DTO.

        Raises:
            NotFoundError: If entity not found.
        """
        entity = self._repo.find_by_id(
            entity_id,
            tenant_id,
            options=options,
            include_inactive=include_inactive,
        )

        if entity is None:
            raise NotFoundError(self._entity_name, entity_id, tenant_id=tenant_id)

        return self.to_output(entity)

    def get_entity(
        self,
        entity_id: int,
        tenant_id: int,
        *,
        include_inactive: bool = False,
    ) -> ModelT | None:
        """Get raw entity (for internal use)."""
        return self._repo.find_by_id(entity_id, tenant_id, include_inactive=include_inactive)

    def list_all(
        self,
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> list[OutputT]:
        """
        List all entities for tenant.

        Args:
            tenant_id: Tenant ID for isolation.
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.
            limit: Maximum results.
            offset: Skip count.
            order_by: Order expression.

        Returns:
            List of output DTOs.
        """
        entities = self._repo.find_all(
            tenant_id,
            options=options,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )
        return [self.to_output(e) for e in entities]

    def count(self, tenant_id: int, *, include_inactive: bool = False) -> int:
        """Count entities for tenant."""
        return self._repo.count(tenant_id, include_inactive=include_inactive)

    def exists(self, entity_id: int, tenant_id: int) -> bool:
        """Check if entity exists."""
        return self._repo.exists(entity_id, tenant_id)

    # =========================================================================
    # Write Operations
    # =========================================================================

    def create(
        self,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> OutputT:
        """
        Create new entity.

        Args:
            data: Entity data dictionary.
            tenant_id: Tenant ID.
            user_id: Creating user ID.
            user_email: Creating user email.

        Returns:
            Output DTO for created entity.

        Raises:
            ValidationError: If data is invalid.
            DatabaseError: If creation fails.
        """
        # Validate before creation
        self._validate_create(data, tenant_id)

        # Validate image URLs
        data = self._validate_image_urls(data)

        # Add tenant_id
        data["tenant_id"] = tenant_id

        # Create entity
        entity = self._model(**data)
        set_created_by(entity, user_id, user_email)

        self._db.add(entity)

        try:
            safe_commit(self._db)
            self._db.refresh(entity)
        except Exception as e:
            logger.error(
                f"Failed to create {self._entity_name}",
                error=str(e),
                tenant_id=tenant_id,
            )
            raise DatabaseError(f"crear {self._entity_name.lower()}")

        # Hook for post-create actions
        self._after_create(entity, user_id, user_email)

        return self.to_output(entity)

    def update(
        self,
        entity_id: int,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> OutputT:
        """
        Update existing entity.

        Args:
            entity_id: Entity ID.
            data: Update data dictionary.
            tenant_id: Tenant ID.
            user_id: Updating user ID.
            user_email: Updating user email.

        Returns:
            Output DTO for updated entity.

        Raises:
            NotFoundError: If entity not found.
            ValidationError: If data is invalid.
            DatabaseError: If update fails.
        """
        entity = self._repo.find_by_id(entity_id, tenant_id)

        if entity is None:
            raise NotFoundError(self._entity_name, entity_id, tenant_id=tenant_id)

        # Validate before update
        self._validate_update(entity, data, tenant_id)

        # Validate image URLs
        data = self._validate_image_urls(data)

        # Store old values for audit
        old_values = {k: getattr(entity, k) for k in data.keys() if hasattr(entity, k)}

        # Update fields
        for field_name, value in data.items():
            if hasattr(entity, field_name):
                setattr(entity, field_name, value)

        set_updated_by(entity, user_id, user_email)

        try:
            safe_commit(self._db)
            self._db.refresh(entity)
        except Exception as e:
            logger.error(
                f"Failed to update {self._entity_name}",
                error=str(e),
                entity_id=entity_id,
            )
            raise DatabaseError(f"actualizar {self._entity_name.lower()}")

        # Hook for post-update actions
        self._after_update(entity, old_values, user_id, user_email)

        return self.to_output(entity)

    def delete(
        self,
        entity_id: int,
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """
        Delete entity (soft delete if supported).

        Args:
            entity_id: Entity ID.
            tenant_id: Tenant ID.
            user_id: Deleting user ID.
            user_email: Deleting user email.

        Raises:
            NotFoundError: If entity not found.
        """
        entity = self._repo.find_by_id(entity_id, tenant_id)

        if entity is None:
            raise NotFoundError(self._entity_name, entity_id, tenant_id=tenant_id)

        # Validate before delete
        self._validate_delete(entity, tenant_id)

        # Store info for event before deletion
        entity_info = self._get_entity_info_for_event(entity)

        if self._supports_soft_delete:
            soft_delete(self._db, entity, user_id, user_email)
        else:
            self._db.delete(entity)
            safe_commit(self._db)

        # Hook for post-delete actions
        self._after_delete(entity_info, user_id, user_email)

    # =========================================================================
    # Transformation
    # =========================================================================

    def to_output(self, entity: ModelT) -> OutputT:
        """
        Convert entity to output DTO.

        Override this method for custom transformation logic.
        """
        return self._output_schema.model_validate(entity)

    # =========================================================================
    # Validation Hooks (override in subclasses)
    # =========================================================================

    def _validate_create(self, data: dict[str, Any], tenant_id: int) -> None:
        """
        Validate data before create.

        Override to add custom validation rules.

        Raises:
            ValidationError: If validation fails.
        """
        pass

    def _validate_update(
        self, entity: ModelT, data: dict[str, Any], tenant_id: int
    ) -> None:
        """
        Validate data before update.

        Override to add custom validation rules.

        Raises:
            ValidationError: If validation fails.
        """
        pass

    def _validate_delete(self, entity: ModelT, tenant_id: int) -> None:
        """
        Validate before delete.

        Override to check for dependent entities, etc.

        Raises:
            ValidationError: If deletion is not allowed.
        """
        pass

    # =========================================================================
    # Lifecycle Hooks (override in subclasses)
    # =========================================================================

    def _after_create(self, entity: ModelT, user_id: int, user_email: str) -> None:
        """Hook called after entity creation. Override for side effects."""
        pass

    def _after_update(
        self,
        entity: ModelT,
        old_values: dict[str, Any],
        user_id: int,
        user_email: str,
    ) -> None:
        """Hook called after entity update. Override for side effects."""
        pass

    def _after_delete(
        self,
        entity_info: dict[str, Any],
        user_id: int,
        user_email: str,
    ) -> None:
        """Hook called after entity deletion. Override for event publishing."""
        pass

    def _get_entity_info_for_event(self, entity: ModelT) -> dict[str, Any]:
        """Get entity info to store before deletion for event publishing."""
        return {
            "id": entity.id,
            "name": getattr(entity, "name", None),
            "tenant_id": getattr(entity, "tenant_id", None),
            "branch_id": getattr(entity, "branch_id", None),
        }

    # =========================================================================
    # Internal Helpers
    # =========================================================================

    def _validate_image_urls(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate and sanitize image URL fields."""
        for field_name in self._image_url_fields:
            if field_name in data and data[field_name]:
                try:
                    data[field_name] = validate_image_url(data[field_name])
                except ValueError as e:
                    raise ValidationError(str(e), field=field_name)
        return data


class BranchScopedService(BaseCRUDService[ModelT, OutputT], Generic[ModelT, OutputT]):
    """
    Service for branch-scoped entities.

    Extends BaseCRUDService with branch filtering and access validation.
    """

    def __init__(
        self,
        db: Session,
        model: Type[ModelT],
        output_schema: Type[OutputT],
        entity_name: str,
        **kwargs,
    ):
        super().__init__(
            db=db,
            model=model,
            output_schema=output_schema,
            entity_name=entity_name,
            has_branch_id=True,
            **kwargs,
        )

    def list_by_branch(
        self,
        tenant_id: int,
        branch_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> list[OutputT]:
        """List entities for a specific branch."""
        repo: BranchRepository = self._repo
        entities = repo.find_by_branch(
            branch_id=branch_id,
            tenant_id=tenant_id,
            options=options,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )
        return [self.to_output(e) for e in entities]

    def list_by_branches(
        self,
        tenant_id: int,
        branch_ids: Sequence[int],
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> list[OutputT]:
        """List entities for multiple branches."""
        repo: BranchRepository = self._repo
        entities = repo.find_by_branches(
            branch_ids=branch_ids,
            tenant_id=tenant_id,
            options=options,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
            order_by=order_by,
        )
        return [self.to_output(e) for e in entities]

    def validate_branch_access(
        self,
        entity: ModelT,
        user_branch_ids: list[int] | None,
    ) -> None:
        """
        Validate user has access to entity's branch.

        Raises:
            ForbiddenError: If user doesn't have branch access.
        """
        if user_branch_ids is None:
            return  # Admin has full access

        entity_branch_id = getattr(entity, "branch_id", None)
        if entity_branch_id and entity_branch_id not in user_branch_ids:
            raise ForbiddenError(
                f"acceder a este {self._entity_name.lower()}",
                branch_id=entity_branch_id,
            )
