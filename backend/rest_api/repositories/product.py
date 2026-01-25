"""
Product Repository - Data access for products.
CRIT-02 FIX: Eager loading prevents N+1 queries.
"""

from dataclasses import dataclass
from typing import Sequence
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import Select, select, or_

from rest_api.models import (
    Product,
    ProductAllergen,
    BranchProduct,
    ProductIngredient,
    Category,
    Subcategory,
)
from .base import BaseRepository, RepositoryFilters


@dataclass
class ProductFilters(RepositoryFilters):
    """Filters specific to products."""

    category_id: int | None = None
    subcategory_id: int | None = None
    is_available: bool | None = None
    has_allergen_id: int | None = None
    min_price_cents: int | None = None
    max_price_cents: int | None = None


class ProductRepository(BaseRepository[Product]):
    """
    Repository for Product entities.

    Guarantees eager loading of:
    - product_allergens -> allergen
    - product_ingredients -> ingredient
    - branch_products -> branch
    - category, subcategory
    """

    @property
    def model(self) -> type[Product]:
        return Product

    def _base_query(self, tenant_id: int) -> Select:
        """
        Base query with comprehensive eager loading.
        Prevents N+1 when accessing related entities.
        """
        return (
            select(Product)
            .where(Product.tenant_id == tenant_id)
            # Allergens (M:N through ProductAllergen)
            .options(
                selectinload(Product.product_allergens)
                .joinedload(ProductAllergen.allergen)
            )
            # Ingredients (M:N through ProductIngredient)
            .options(
                selectinload(Product.product_ingredients)
                .joinedload(ProductIngredient.ingredient)
            )
            # Branch pricing
            .options(
                selectinload(Product.branch_products)
            )
            # Category hierarchy
            .options(
                joinedload(Product.category)
            )
            .options(
                joinedload(Product.subcategory)
            )
            # Order by name for consistent results
            .order_by(Product.name)
        )

    def _apply_filters(self, query: Select, filters: RepositoryFilters) -> Select:
        """Apply product-specific filters."""
        if not isinstance(filters, ProductFilters):
            filters = ProductFilters(**filters.__dict__)

        # Branch filter
        if filters.branch_id:
            query = query.where(Product.branch_id == filters.branch_id)
        elif filters.branch_ids:
            query = query.where(Product.branch_id.in_(filters.branch_ids))

        # Category filter
        if filters.category_id:
            query = query.where(Product.category_id == filters.category_id)

        # Subcategory filter
        if filters.subcategory_id:
            query = query.where(Product.subcategory_id == filters.subcategory_id)

        # Availability filter
        if filters.is_available is not None:
            query = query.where(Product.is_available.is_(filters.is_available))

        # Search filter
        if filters.search:
            search_term = f"%{filters.search}%"
            query = query.where(
                or_(
                    Product.name.ilike(search_term),
                    Product.description.ilike(search_term),
                )
            )

        return query

    def find_by_category(
        self,
        tenant_id: int,
        category_id: int,
        include_subcategories: bool = True,
    ) -> Sequence[Product]:
        """Find all products in a category."""
        query = self._base_query(tenant_id).where(Product.category_id == category_id)

        if hasattr(Product, "is_active"):
            query = query.where(Product.is_active.is_(True))

        return self._db.execute(query).scalars().unique().all()

    def find_by_branch(
        self,
        tenant_id: int,
        branch_id: int,
        filters: ProductFilters | None = None,
    ) -> Sequence[Product]:
        """Find all products available in a branch."""
        filters = filters or ProductFilters()
        filters.branch_id = branch_id

        return self.find_all(tenant_id, filters)

    def find_with_allergen(
        self,
        tenant_id: int,
        allergen_id: int,
        presence_type: str | None = None,
    ) -> Sequence[Product]:
        """Find products containing specific allergen."""
        query = (
            self._base_query(tenant_id)
            .join(Product.product_allergens)
            .where(ProductAllergen.allergen_id == allergen_id)
        )

        if presence_type:
            query = query.where(ProductAllergen.presence_type == presence_type)

        if hasattr(Product, "is_active"):
            query = query.where(Product.is_active.is_(True))

        return self._db.execute(query).scalars().unique().all()

    def find_for_menu(
        self,
        tenant_id: int,
        branch_id: int,
        category_id: int | None = None,
    ) -> Sequence[Product]:
        """
        Find products for menu display.
        Optimized for public menu with minimal joins.
        """
        query = (
            select(Product)
            .where(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
                Product.is_available.is_(True),
            )
            .options(
                selectinload(Product.product_allergens)
                .joinedload(ProductAllergen.allergen)
            )
            .options(joinedload(Product.category))
            .options(joinedload(Product.subcategory))
        )

        # Filter by branch products
        query = query.join(
            BranchProduct,
            (BranchProduct.product_id == Product.id) &
            (BranchProduct.branch_id == branch_id) &
            (BranchProduct.is_active.is_(True))
        )

        if category_id:
            query = query.where(Product.category_id == category_id)

        query = query.order_by(Product.display_order, Product.name)

        return self._db.execute(query).scalars().unique().all()


def get_product_repository(db: Session) -> ProductRepository:
    """Factory function for dependency injection."""
    return ProductRepository(db)
