"""
Repository Pattern for database access.

ARCH-OPP-06: Provides a clean abstraction layer between business logic
and data access, with built-in multi-tenant isolation.

Usage:
    from rest_api.services.crud.repository import (
        BaseRepository,
        TenantRepository,
        BranchRepository,
    )

    # Create repository instance
    product_repo = TenantRepository(Product, db)

    # Use in routers
    products = product_repo.find_all(tenant_id=1)
    product = product_repo.find_by_id(42, tenant_id=1)
    exists = product_repo.exists(42, tenant_id=1)

    # With eager loading
    product_repo.find_all(
        tenant_id=1,
        options=[selectinload(Product.allergens)]
    )

    # Branch-scoped repository
    table_repo = BranchRepository(Table, db)
    tables = table_repo.find_by_branch(branch_id=5, tenant_id=1)
"""

from __future__ import annotations

from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import select, func, exists as sql_exists
from sqlalchemy.orm import Session, Query
from sqlalchemy.sql import Select

from rest_api.models import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """
    Base repository providing common database operations.

    Subclass this for entities without tenant isolation (rare).
    For multi-tenant entities, use TenantRepository instead.
    """

    def __init__(self, model: type[ModelT], session: Session):
        self._model = model
        self._session = session

    @property
    def model(self) -> type[ModelT]:
        """The SQLAlchemy model class."""
        return self._model

    @property
    def session(self) -> Session:
        """The database session."""
        return self._session

    def _base_query(self) -> Select:
        """Create base select query."""
        return select(self._model)

    def _apply_active_filter(self, query: Select, include_inactive: bool) -> Select:
        """Apply is_active filter if model has it."""
        if hasattr(self._model, "is_active") and not include_inactive:
            query = query.where(self._model.is_active.is_(True))
        return query

    def _apply_options(
        self, query: Select, options: list[Any] | None
    ) -> Select:
        """Apply eager loading options."""
        if options:
            query = query.options(*options)
        return query

    def find_by_id(
        self,
        entity_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
    ) -> ModelT | None:
        """
        Find entity by primary key.

        Args:
            entity_id: The primary key value.
            options: SQLAlchemy loader options (selectinload, joinedload).
            include_inactive: Include soft-deleted entities.

        Returns:
            Entity or None if not found.
        """
        query = self._base_query().where(self._model.id == entity_id)
        query = self._apply_active_filter(query, include_inactive)
        query = self._apply_options(query, options)
        return self._session.scalar(query)

    def find_all(
        self,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> Sequence[ModelT]:
        """
        Find all entities.

        Args:
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.
            limit: Maximum number of results.
            offset: Number of results to skip.
            order_by: Column or expression to order by.

        Returns:
            Sequence of entities.
        """
        query = self._base_query()
        query = self._apply_active_filter(query, include_inactive)
        query = self._apply_options(query, options)

        if order_by is not None:
            query = query.order_by(order_by)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        return self._session.scalars(query).all()

    def count(self, *, include_inactive: bool = False) -> int:
        """Count all entities."""
        query = select(func.count()).select_from(self._model)
        if hasattr(self._model, "is_active") and not include_inactive:
            query = query.where(self._model.is_active.is_(True))
        return self._session.scalar(query) or 0

    def exists(self, entity_id: int) -> bool:
        """Check if entity exists by ID."""
        query = select(sql_exists().where(self._model.id == entity_id))
        return self._session.scalar(query) or False

    def add(self, entity: ModelT) -> ModelT:
        """Add entity to session (not committed)."""
        self._session.add(entity)
        return entity

    def add_all(self, entities: Sequence[ModelT]) -> Sequence[ModelT]:
        """Add multiple entities to session (not committed)."""
        self._session.add_all(entities)
        return entities

    def delete(self, entity: ModelT) -> None:
        """Delete entity from session (not committed)."""
        self._session.delete(entity)

    def refresh(self, entity: ModelT) -> ModelT:
        """Refresh entity from database."""
        self._session.refresh(entity)
        return entity


class TenantRepository(BaseRepository[ModelT]):
    """
    Repository with automatic multi-tenant isolation.

    All queries are filtered by tenant_id to ensure data isolation.
    The model must have a `tenant_id` column.

    Usage:
        repo = TenantRepository(Category, db)
        categories = repo.find_all(tenant_id=1)
    """

    def _tenant_query(self, tenant_id: int) -> Select:
        """Create tenant-filtered base query."""
        if not hasattr(self._model, "tenant_id"):
            raise AttributeError(
                f"Model {self._model.__name__} does not have tenant_id column. "
                "Use BaseRepository instead."
            )
        return self._base_query().where(self._model.tenant_id == tenant_id)

    def find_by_id(
        self,
        entity_id: int,
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
    ) -> ModelT | None:
        """
        Find entity by ID within tenant scope.

        Args:
            entity_id: The primary key value.
            tenant_id: The tenant ID for isolation.
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.

        Returns:
            Entity or None if not found or wrong tenant.
        """
        query = self._tenant_query(tenant_id).where(self._model.id == entity_id)
        query = self._apply_active_filter(query, include_inactive)
        query = self._apply_options(query, options)
        return self._session.scalar(query)

    def find_all(
        self,
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> Sequence[ModelT]:
        """
        Find all entities within tenant scope.

        Args:
            tenant_id: The tenant ID for isolation.
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.
            limit: Maximum results.
            offset: Skip count.
            order_by: Order expression.

        Returns:
            Sequence of entities.
        """
        query = self._tenant_query(tenant_id)
        query = self._apply_active_filter(query, include_inactive)
        query = self._apply_options(query, options)

        if order_by is not None:
            query = query.order_by(order_by)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        return self._session.scalars(query).all()

    def find_by_ids(
        self,
        entity_ids: Sequence[int],
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
    ) -> Sequence[ModelT]:
        """
        Find multiple entities by IDs within tenant scope.

        Args:
            entity_ids: List of primary key values.
            tenant_id: The tenant ID for isolation.
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.

        Returns:
            Sequence of found entities (may be less than requested).
        """
        if not entity_ids:
            return []

        query = self._tenant_query(tenant_id).where(self._model.id.in_(entity_ids))
        query = self._apply_active_filter(query, include_inactive)
        query = self._apply_options(query, options)
        return self._session.scalars(query).all()

    def count(self, tenant_id: int, *, include_inactive: bool = False) -> int:
        """Count entities within tenant scope."""
        query = (
            select(func.count())
            .select_from(self._model)
            .where(self._model.tenant_id == tenant_id)
        )
        if hasattr(self._model, "is_active") and not include_inactive:
            query = query.where(self._model.is_active.is_(True))
        return self._session.scalar(query) or 0

    def exists(self, entity_id: int, tenant_id: int) -> bool:
        """Check if entity exists within tenant scope."""
        query = select(
            sql_exists().where(
                self._model.id == entity_id,
                self._model.tenant_id == tenant_id,
            )
        )
        return self._session.scalar(query) or False


class BranchRepository(TenantRepository[ModelT]):
    """
    Repository for branch-scoped entities.

    Extends TenantRepository with branch filtering.
    The model must have both `tenant_id` and `branch_id` columns.

    Usage:
        repo = BranchRepository(Table, db)
        tables = repo.find_by_branch(branch_id=5, tenant_id=1)
    """

    def _branch_query(self, branch_id: int, tenant_id: int) -> Select:
        """Create branch-filtered query."""
        if not hasattr(self._model, "branch_id"):
            raise AttributeError(
                f"Model {self._model.__name__} does not have branch_id column. "
                "Use TenantRepository instead."
            )
        return self._tenant_query(tenant_id).where(self._model.branch_id == branch_id)

    def find_by_branch(
        self,
        branch_id: int,
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> Sequence[ModelT]:
        """
        Find all entities within branch scope.

        Args:
            branch_id: The branch ID for filtering.
            tenant_id: The tenant ID for isolation.
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.
            limit: Maximum results.
            offset: Skip count.
            order_by: Order expression.

        Returns:
            Sequence of entities.
        """
        query = self._branch_query(branch_id, tenant_id)
        query = self._apply_active_filter(query, include_inactive)
        query = self._apply_options(query, options)

        if order_by is not None:
            query = query.order_by(order_by)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        return self._session.scalars(query).all()

    def find_by_branches(
        self,
        branch_ids: Sequence[int],
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> Sequence[ModelT]:
        """
        Find all entities within multiple branches.

        Args:
            branch_ids: List of branch IDs for filtering.
            tenant_id: The tenant ID for isolation.
            options: SQLAlchemy loader options.
            include_inactive: Include soft-deleted entities.
            limit: Maximum results.
            offset: Skip count.
            order_by: Order expression.

        Returns:
            Sequence of entities.
        """
        if not branch_ids:
            return []

        query = self._tenant_query(tenant_id).where(
            self._model.branch_id.in_(branch_ids)
        )
        query = self._apply_active_filter(query, include_inactive)
        query = self._apply_options(query, options)

        if order_by is not None:
            query = query.order_by(order_by)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        return self._session.scalars(query).all()

    def count_by_branch(
        self,
        branch_id: int,
        tenant_id: int,
        *,
        include_inactive: bool = False,
    ) -> int:
        """Count entities within branch scope."""
        query = (
            select(func.count())
            .select_from(self._model)
            .where(
                self._model.tenant_id == tenant_id,
                self._model.branch_id == branch_id,
            )
        )
        if hasattr(self._model, "is_active") and not include_inactive:
            query = query.where(self._model.is_active.is_(True))
        return self._session.scalar(query) or 0


class SpecificationRepository(TenantRepository[ModelT]):
    """
    Repository with Specification Pattern support.

    Allows composing complex queries from reusable specifications.
    LOW-03 FIX: Added practical domain examples for restaurant system.

    Pattern Benefits:
        - Encapsulates complex query logic in reusable objects
        - Enables composition via logical operators (&, |, ~)
        - Separates query building from repository concerns
        - Improves testability (specifications can be unit tested)

    Basic Usage:
        from rest_api.services.crud.repository import (
            SpecificationRepository,
            Specification,
        )

        class ActiveSpec(Specification):
            def to_expression(self):
                return Product.is_active.is_(True)

        class PriceRangeSpec(Specification):
            def __init__(self, min_price: int, max_price: int):
                self.min_price = min_price
                self.max_price = max_price

            def to_expression(self):
                return Product.price.between(self.min_price, self.max_price)

        repo = SpecificationRepository(Product, db)
        products = repo.find_by_spec(
            ActiveSpec() & PriceRangeSpec(1000, 5000),
            tenant_id=1,
        )

    Domain Examples (Restaurant System):

        # 1. Vegetarian products in category
        class VegetarianSpec(Specification):
            def to_expression(self):
                return Product.is_vegetarian.is_(True)

        class CategorySpec(Specification):
            def __init__(self, category_id: int):
                self.category_id = category_id
            def to_expression(self):
                return Product.category_id == self.category_id

        vegetarian_entradas = repo.find_by_spec(
            VegetarianSpec() & CategorySpec(entradas_id),
            tenant_id=1,
        )

        # 2. Products available in branch
        class AvailableInBranchSpec(Specification):
            def __init__(self, branch_id: int):
                self.branch_id = branch_id
            def to_expression(self):
                from sqlalchemy import exists, select
                from rest_api.models import BranchProduct
                return exists(select(BranchProduct.id).where(
                    BranchProduct.product_id == Product.id,
                    BranchProduct.branch_id == self.branch_id,
                    BranchProduct.is_available.is_(True)
                ))

        # 3. Complex filter composition
        menu_products = repo.find_by_spec(
            ActiveSpec() & AvailableInBranchSpec(branch_id) & ~VegetarianSpec(),
            tenant_id=1,
            order_by=Product.name,
        )

    When to Use:
        - Complex filter combinations across multiple endpoints
        - Filters composed dynamically from user preferences
        - Business rules that should be encapsulated and reusable

    When NOT to Use:
        - Simple single-condition queries (use TenantRepository)
        - One-off queries that won't be reused
    """

    def find_by_spec(
        self,
        spec: "Specification",
        tenant_id: int,
        *,
        options: list[Any] | None = None,
        limit: int | None = None,
        offset: int | None = None,
        order_by: Any | None = None,
    ) -> Sequence[ModelT]:
        """
        Find entities matching a specification.

        Args:
            spec: The specification to apply.
            tenant_id: The tenant ID for isolation.
            options: SQLAlchemy loader options.
            limit: Maximum results.
            offset: Skip count.
            order_by: Order expression.

        Returns:
            Sequence of matching entities.
        """
        query = self._tenant_query(tenant_id).where(spec.to_expression())
        query = self._apply_options(query, options)

        if order_by is not None:
            query = query.order_by(order_by)
        if offset is not None:
            query = query.offset(offset)
        if limit is not None:
            query = query.limit(limit)

        return self._session.scalars(query).all()


class Specification:
    """
    Base class for query specifications.

    Specifications encapsulate query conditions that can be
    combined using logical operators (&, |, ~).

    Subclass this and implement to_expression() to create
    reusable query building blocks.
    """

    def to_expression(self) -> Any:
        """
        Convert specification to SQLAlchemy expression.

        Must be implemented by subclasses.
        """
        raise NotImplementedError

    def __and__(self, other: "Specification") -> "AndSpecification":
        """Combine with AND."""
        return AndSpecification(self, other)

    def __or__(self, other: "Specification") -> "OrSpecification":
        """Combine with OR."""
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification":
        """Negate specification."""
        return NotSpecification(self)


class AndSpecification(Specification):
    """AND combination of two specifications."""

    def __init__(self, left: Specification, right: Specification):
        self._left = left
        self._right = right

    def to_expression(self) -> Any:
        from sqlalchemy import and_
        return and_(self._left.to_expression(), self._right.to_expression())


class OrSpecification(Specification):
    """OR combination of two specifications."""

    def __init__(self, left: Specification, right: Specification):
        self._left = left
        self._right = right

    def to_expression(self) -> Any:
        from sqlalchemy import or_
        return or_(self._left.to_expression(), self._right.to_expression())


class NotSpecification(Specification):
    """Negation of a specification."""

    def __init__(self, spec: Specification):
        self._spec = spec

    def to_expression(self) -> Any:
        from sqlalchemy import not_
        return not_(self._spec.to_expression())


# Convenience function for FastAPI dependency injection
def get_repository(
    model: type[ModelT],
    session: Session,
    *,
    branch_scoped: bool = False,
) -> BaseRepository[ModelT]:
    """
    Factory function for creating repositories.

    Args:
        model: The SQLAlchemy model class.
        session: Database session.
        branch_scoped: Use BranchRepository if True.

    Returns:
        Appropriate repository instance.
    """
    if branch_scoped:
        return BranchRepository(model, session)
    if hasattr(model, "tenant_id"):
        return TenantRepository(model, session)
    return BaseRepository(model, session)
