"""
Base Repository implementation.
Provides common data access patterns with tenant isolation.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TypeVar, Generic, Any, Sequence
from sqlalchemy.orm import Session
from sqlalchemy import Select, select, func

from shared.config.constants import Limits


ModelT = TypeVar("ModelT")


@dataclass
class RepositoryFilters:
    """Base filters for repository queries."""

    # Pagination
    limit: int = Limits.DEFAULT_PAGE_SIZE
    offset: int = 0

    # Soft delete
    include_deleted: bool = False

    # Branch filtering
    branch_id: int | None = None
    branch_ids: list[int] | None = None

    # Search
    search: str | None = None

    def __post_init__(self):
        """Validate and normalize filters."""
        self.limit = min(max(1, self.limit), Limits.MAX_PAGE_SIZE)
        self.offset = max(0, self.offset)
        if self.search:
            self.search = self.search.strip()[:Limits.MAX_SEARCH_TERM_LENGTH]


class BaseRepository(ABC, Generic[ModelT]):
    """
    Abstract base repository with common operations.

    Subclasses must implement:
    - _get_model(): Return the SQLAlchemy model class
    - _base_query(): Return base query with eager loading
    """

    def __init__(self, db: Session):
        self._db = db

    @property
    @abstractmethod
    def model(self) -> type[ModelT]:
        """Return the SQLAlchemy model class."""
        ...

    @abstractmethod
    def _base_query(self, tenant_id: int) -> Select:
        """
        Return base query with proper eager loading.
        Subclasses must implement this with selectinload/joinedload.
        """
        ...

    @abstractmethod
    def _apply_filters(self, query: Select, filters: RepositoryFilters) -> Select:
        """Apply entity-specific filters to query."""
        ...

    def find_all(
        self,
        tenant_id: int,
        filters: RepositoryFilters | None = None,
    ) -> Sequence[ModelT]:
        """
        Find all entities matching filters.

        Args:
            tenant_id: Tenant ID for isolation
            filters: Optional filters

        Returns:
            List of entities
        """
        filters = filters or RepositoryFilters()
        query = self._base_query(tenant_id)

        # Apply soft delete filter
        if not filters.include_deleted and hasattr(self.model, "is_active"):
            query = query.where(self.model.is_active.is_(True))

        # Apply entity-specific filters
        query = self._apply_filters(query, filters)

        # Apply pagination
        query = query.offset(filters.offset).limit(filters.limit)

        return self._db.execute(query).scalars().unique().all()

    def find_by_id(
        self,
        entity_id: int,
        tenant_id: int,
        include_deleted: bool = False,
    ) -> ModelT | None:
        """
        Find entity by ID.

        Args:
            entity_id: Entity ID
            tenant_id: Tenant ID for isolation
            include_deleted: Include soft-deleted entities

        Returns:
            Entity or None
        """
        query = self._base_query(tenant_id).where(self.model.id == entity_id)

        if not include_deleted and hasattr(self.model, "is_active"):
            query = query.where(self.model.is_active.is_(True))

        return self._db.scalar(query)

    def find_by_ids(
        self,
        entity_ids: list[int],
        tenant_id: int,
        include_deleted: bool = False,
    ) -> Sequence[ModelT]:
        """
        Find entities by IDs.

        Args:
            entity_ids: List of entity IDs
            tenant_id: Tenant ID for isolation
            include_deleted: Include soft-deleted entities

        Returns:
            List of entities (order not guaranteed)
        """
        if not entity_ids:
            return []

        query = self._base_query(tenant_id).where(self.model.id.in_(entity_ids))

        if not include_deleted and hasattr(self.model, "is_active"):
            query = query.where(self.model.is_active.is_(True))

        return self._db.execute(query).scalars().unique().all()

    def count(
        self,
        tenant_id: int,
        filters: RepositoryFilters | None = None,
    ) -> int:
        """
        Count entities matching filters.

        Args:
            tenant_id: Tenant ID for isolation
            filters: Optional filters

        Returns:
            Count of matching entities
        """
        filters = filters or RepositoryFilters()

        query = (
            select(func.count())
            .select_from(self.model)
            .where(self.model.tenant_id == tenant_id)
        )

        if not filters.include_deleted and hasattr(self.model, "is_active"):
            query = query.where(self.model.is_active.is_(True))

        # Apply filters (simplified - no eager loading needed for count)
        if filters.branch_id and hasattr(self.model, "branch_id"):
            query = query.where(self.model.branch_id == filters.branch_id)
        elif filters.branch_ids and hasattr(self.model, "branch_id"):
            query = query.where(self.model.branch_id.in_(filters.branch_ids))

        return self._db.scalar(query) or 0

    def exists(self, entity_id: int, tenant_id: int) -> bool:
        """Check if entity exists."""
        query = (
            select(func.count())
            .select_from(self.model)
            .where(
                self.model.id == entity_id,
                self.model.tenant_id == tenant_id,
            )
        )

        if hasattr(self.model, "is_active"):
            query = query.where(self.model.is_active.is_(True))

        return (self._db.scalar(query) or 0) > 0

    def save(self, entity: ModelT) -> ModelT:
        """
        Save entity (insert or update).

        Args:
            entity: Entity to save

        Returns:
            Saved entity
        """
        self._db.add(entity)
        self._db.flush()
        self._db.refresh(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        """
        Hard delete entity.
        Use soft_delete service for soft deletes.
        """
        self._db.delete(entity)
        self._db.flush()
