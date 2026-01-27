"""
Catalog Models: Category, Subcategory, Product, BranchProduct.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .tenant import Tenant, Branch
    from .allergen import ProductAllergen
    from .ingredient import ProductIngredient
    from .product_profile import (
        ProductDietaryProfile, ProductCooking, ProductModification,
        ProductWarning, ProductRAGConfig, ProductCookingMethod, ProductFlavor, ProductTexture
    )
    from .promotion import PromotionItem
    from .exclusion import BranchCategoryExclusion, BranchSubcategoryExclusion
    from .recipe import Recipe
    from .order import RoundItem


class Category(AuditMixin, Base):
    """
    Product category within a branch.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "category"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(Text)
    image: Mapped[Optional[str]] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    subcategories: Mapped[list["Subcategory"]] = relationship(back_populates="category")
    # MDL-HIGH-04 FIX: Added reverse relationship from BranchCategoryExclusion
    branch_exclusions: Mapped[list["BranchCategoryExclusion"]] = relationship(
        back_populates="category"
    )

    __table_args__ = (
        # MDL-HIGH-06 FIX: UniqueConstraint to prevent duplicate names in same branch
        UniqueConstraint("branch_id", "name", name="uq_category_branch_name"),
        # Composite index for catalog queries (branch_id + is_active)
        Index("ix_category_branch_active", "branch_id", "is_active"),
    )


class Subcategory(AuditMixin, Base):
    """
    Product subcategory within a category.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "subcategory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("category.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    image: Mapped[Optional[str]] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    category: Mapped["Category"] = relationship(back_populates="subcategories")
    # MDL-HIGH-04 FIX: Added reverse relationship from BranchSubcategoryExclusion
    branch_exclusions: Mapped[list["BranchSubcategoryExclusion"]] = relationship(
        back_populates="subcategory"
    )

    __table_args__ = (
        # MDL-HIGH-06 FIX: UniqueConstraint to prevent duplicate names in same category
        UniqueConstraint("category_id", "name", name="uq_subcategory_category_name"),
        # Composite index for catalog queries (category_id + is_active)
        Index("ix_subcategory_category_active", "category_id", "is_active"),
    )


class Product(AuditMixin, Base):
    """
    Product definition at the tenant level.
    Actual availability and pricing is per-branch via BranchProduct.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    image: Mapped[Optional[str]] = mapped_column(Text)
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("category.id"), nullable=False, index=True
    )
    subcategory_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("subcategory.id"), index=True
    )
    # MDL-LOW-20 FIX: Added index for featured product queries
    featured: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    popular: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    badge: Mapped[Optional[str]] = mapped_column(Text)  # "Nuevo", "Popular", etc.
    # MDL-LOW-04 FIX: Added migration timeline for deprecated fields
    # DEPRECATED (v2.0): Use ProductDietaryProfile instead (Phase 2)
    # Migration: Run migrate_seal.py then remove field in v3.0
    seal: Mapped[Optional[str]] = mapped_column(Text)  # "Vegano", "Sin Gluten", etc.
    # DEPRECATED (v2.0): Use ProductAllergen table instead (Phase 0)
    # Migration: Run migrate_allergen_ids.py then remove field in v3.0
    allergen_ids: Mapped[Optional[str]] = mapped_column(Text)  # JSON array as string

    # Recipe linkage (propuesta1.md - Recipe opcional pero enriquecedora)
    # A product can optionally be linked to a recipe for enriched data
    recipe_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("recipe.id"), index=True
    )
    # When True, product inherits allergens/dietary info from recipe on sync
    inherits_from_recipe: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships - Core
    tenant: Mapped["Tenant"] = relationship(back_populates="products")
    branch_products: Mapped[list["BranchProduct"]] = relationship(
        back_populates="product"
    )
    # Recipe relationship (propuesta1.md)
    recipe: Mapped[Optional["Recipe"]] = relationship(
        back_populates="products", foreign_keys=[recipe_id]
    )

    # Relationships - Canonical Model (Phases 0-4)
    product_allergens: Mapped[list["ProductAllergen"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    product_ingredients: Mapped[list["ProductIngredient"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    dietary_profile: Mapped[Optional["ProductDietaryProfile"]] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    cooking_info: Mapped[Optional["ProductCooking"]] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    modifications: Mapped[list["ProductModification"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    warnings: Mapped[list["ProductWarning"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    rag_config: Mapped[Optional["ProductRAGConfig"]] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    # MDL-HIGH-03 FIX: Added reverse relationship from PromotionItem
    promotion_items: Mapped[list["PromotionItem"]] = relationship(
        back_populates="product"
    )
    # MDL-HIGH-05 FIX: Added reverse relationship from RoundItem
    round_items: Mapped[list["RoundItem"]] = relationship(
        back_populates="product"
    )
    # MDL-HIGH-05b FIX: Added reverse relationships from M:N profile tables
    cooking_methods: Mapped[list["ProductCookingMethod"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    flavors: Mapped[list["ProductFlavor"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    textures: Mapped[list["ProductTexture"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

    # MED-01 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', category_id={self.category_id})>"


class BranchProduct(AuditMixin, Base):
    """
    Product availability and pricing per branch.
    A product can have different prices in different branches.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    Note: is_available is a separate field for product availability toggle.
    """

    __tablename__ = "branch_product"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id"), nullable=False, index=True
    )
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    # MDL-LOW-21 FIX: Added index for availability queries
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    # Relationships
    branch: Mapped["Branch"] = relationship(back_populates="branch_products")
    product: Mapped["Product"] = relationship(back_populates="branch_products")

    # CRIT-04 FIX: Unique constraint to prevent duplicate branch-product entries
    __table_args__ = (
        UniqueConstraint("branch_id", "product_id", name="uq_branch_product"),
        Index("ix_branch_product_branch_product", "branch_id", "product_id"),
    )
