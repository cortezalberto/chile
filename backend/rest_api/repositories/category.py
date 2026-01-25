"""
Category Repository - Data access for categories and subcategories.
"""

from dataclasses import dataclass
from typing import Sequence
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import Select, select, or_

from rest_api.models import Category, Subcategory
from .base import BaseRepository, RepositoryFilters


@dataclass
class CategoryFilters(RepositoryFilters):
    """Filters specific to categories."""

    is_visible: bool | None = None
    has_products: bool | None = None


class CategoryRepository(BaseRepository[Category]):
    """
    Repository for Category entities.

    Guarantees eager loading of:
    - subcategories
    """

    @property
    def model(self) -> type[Category]:
        return Category

    def _base_query(self, tenant_id: int) -> Select:
        """Base query with eager loading of subcategories."""
        return (
            select(Category)
            .where(Category.tenant_id == tenant_id)
            .options(
                selectinload(Category.subcategories)
            )
            .order_by(Category.display_order, Category.name)
        )

    def _apply_filters(self, query: Select, filters: RepositoryFilters) -> Select:
        """Apply category-specific filters."""
        if not isinstance(filters, CategoryFilters):
            filters = CategoryFilters(**filters.__dict__)

        # Branch filter (categories may be branch-specific or tenant-wide)
        if filters.branch_id and hasattr(Category, "branch_id"):
            query = query.where(
                or_(
                    Category.branch_id == filters.branch_id,
                    Category.branch_id.is_(None),  # Tenant-wide
                )
            )

        # Visibility filter
        if filters.is_visible is not None:
            query = query.where(Category.is_visible.is_(filters.is_visible))

        # Search filter
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(Category.name.ilike(search_term))

        return query

    def find_with_products(
        self,
        tenant_id: int,
        branch_id: int | None = None,
    ) -> Sequence[Category]:
        """Find categories that have products."""
        from rest_api.models import Product

        query = (
            self._base_query(tenant_id)
            .join(Product, Product.category_id == Category.id)
            .where(
                Category.is_active.is_(True),
                Product.is_active.is_(True),
            )
        )

        if branch_id:
            query = query.where(Product.branch_id == branch_id)

        return self._db.execute(query).scalars().unique().all()

    def find_for_menu(
        self,
        tenant_id: int,
        branch_id: int,
    ) -> Sequence[Category]:
        """
        Find categories for menu display.
        Only visible categories with active products in the branch.
        """
        from rest_api.models import Product, BranchProduct

        query = (
            select(Category)
            .where(
                Category.tenant_id == tenant_id,
                Category.is_active.is_(True),
                Category.is_visible.is_(True),
            )
            .options(selectinload(Category.subcategories))
            .join(Product, Product.category_id == Category.id)
            .join(
                BranchProduct,
                (BranchProduct.product_id == Product.id) &
                (BranchProduct.branch_id == branch_id) &
                (BranchProduct.is_active.is_(True))
            )
            .where(
                Product.is_active.is_(True),
                Product.is_available.is_(True),
            )
            .order_by(Category.display_order, Category.name)
        )

        return self._db.execute(query).scalars().unique().all()


def get_category_repository(db: Session) -> CategoryRepository:
    """Factory function for dependency injection."""
    return CategoryRepository(db)
