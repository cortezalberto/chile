"""
SQLAlchemy ORM models for the restaurant management system.
All models include tenant_id for multi-tenancy isolation.
All models inherit from AuditMixin for soft delete and audit trail.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, declared_attr
from pgvector.sqlalchemy import Vector


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


# =============================================================================
# Audit Mixin for Soft Delete and Audit Trail
# =============================================================================


class AuditMixin:
    """
    Mixin providing soft delete and audit trail fields for all models.

    Fields added:
    - is_active: Soft delete flag (False = deleted, True = active)
    - created_at, updated_at, deleted_at: Audit timestamps
    - created_by_id/email, updated_by_id/email, deleted_by_id/email: User tracking

    Methods:
    - soft_delete(user_id, user_email): Mark entity as deleted
    - restore(user_id, user_email): Restore a soft-deleted entity
    """

    # Soft delete flag (False = deleted/inactive, True = active)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # User tracking - store ID and email for denormalization
    # Note: Cannot use FK to app_user here as it would create circular dependency
    created_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    updated_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    deleted_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    deleted_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def soft_delete(self, user_id: int, user_email: str) -> None:
        """
        Perform soft delete with audit trail.
        SVC-CRIT-01 FIX: Uses timezone-aware datetime.now(timezone.utc) instead of naive utcnow().
        """
        from datetime import timezone as tz
        self.is_active = False
        self.deleted_at = datetime.now(tz.utc)
        self.deleted_by_id = user_id
        self.deleted_by_email = user_email

    def restore(self, user_id: int, user_email: str) -> None:
        """
        Restore a soft-deleted record.
        SVC-CRIT-01 FIX: Uses timezone-aware datetime.now(timezone.utc) instead of naive utcnow().
        """
        from datetime import timezone as tz
        self.is_active = True
        self.deleted_at = None
        self.deleted_by_id = None
        self.deleted_by_email = None
        self.updated_at = datetime.now(tz.utc)
        self.updated_by_id = user_id
        self.updated_by_email = user_email

    def set_created_by(self, user_id: int, user_email: str) -> None:
        """Set created_by fields on new entity."""
        self.created_by_id = user_id
        self.created_by_email = user_email

    def set_updated_by(self, user_id: int, user_email: str) -> None:
        """
        Set updated_by fields on entity update.
        SVC-CRIT-01 FIX: Uses timezone-aware datetime.now(timezone.utc) instead of naive utcnow().
        """
        from datetime import timezone as tz
        self.updated_by_id = user_id
        self.updated_by_email = user_email
        self.updated_at = datetime.now(tz.utc)

    def __repr__(self) -> str:
        """DB-LOW-01 FIX: Add __repr__ for better debugging."""
        class_name = self.__class__.__name__
        id_val = getattr(self, 'id', None)
        active = 'active' if self.is_active else 'deleted'
        return f"<{class_name}(id={id_val}, {active})>"


# =============================================================================
# Multi-Tenancy Models
# =============================================================================


class Tenant(AuditMixin, Base):
    """
    Represents a restaurant or brand (top-level tenant).
    All other entities belong to a tenant for complete data isolation.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "tenant"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    logo: Mapped[Optional[str]] = mapped_column(Text)
    theme_color: Mapped[str] = mapped_column(Text, default="#f97316")  # Orange

    # Relationships
    branches: Mapped[list["Branch"]] = relationship(back_populates="tenant")
    users: Mapped[list["User"]] = relationship(back_populates="tenant")
    products: Mapped[list["Product"]] = relationship(back_populates="tenant")

    # MED-01 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class Branch(AuditMixin, Base):
    """
    Represents a physical restaurant location/branch.
    Each branch has its own tables, staff assignments, and pricing.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "branch"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    address: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text, default="America/Argentina/Mendoza")
    opening_time: Mapped[Optional[str]] = mapped_column(Text)  # "09:00"
    closing_time: Mapped[Optional[str]] = mapped_column(Text)  # "23:00"

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="branches")
    tables: Mapped[list["Table"]] = relationship(back_populates="branch")
    sectors: Mapped[list["BranchSector"]] = relationship(back_populates="branch")
    branch_products: Mapped[list["BranchProduct"]] = relationship(
        back_populates="branch"
    )

    # MED-01 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        return f"<Branch(id={self.id}, name='{self.name}', slug='{self.slug}', tenant_id={self.tenant_id})>"


# =============================================================================
# User and Authentication Models
# =============================================================================


class User(AuditMixin, Base):
    """
    Represents a staff member (waiter, kitchen, manager, admin).
    Users can have different roles in different branches.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    # DB-CRIT-01 FIX: Email is now unique per tenant instead of globally unique
    email: Mapped[str] = mapped_column(Text, nullable=False)
    password: Mapped[str] = mapped_column(Text, nullable=False)  # Hashed in production
    first_name: Mapped[Optional[str]] = mapped_column(Text)
    last_name: Mapped[Optional[str]] = mapped_column(Text)
    phone: Mapped[Optional[str]] = mapped_column(Text)  # D004: Staff phone number
    dni: Mapped[Optional[str]] = mapped_column(Text)  # D004: National ID document
    hire_date: Mapped[Optional[str]] = mapped_column(Text)  # D004: Date hired (YYYY-MM-DD)

    # DB-CRIT-01 FIX: Unique constraint per tenant, not global
    __table_args__ = (
        UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
        Index("ix_user_email", "email"),  # Still index email for lookups
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship(back_populates="users")
    branch_roles: Mapped[list["UserBranchRole"]] = relationship(back_populates="user")

    # MED-01 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', name='{self.first_name} {self.last_name}')>"


class UserBranchRole(AuditMixin, Base):
    """
    Maps users to branches with specific roles.
    A user can have different roles in different branches.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "user_branch_role"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # WAITER, KITCHEN, MANAGER, ADMIN

    # Relationships
    user: Mapped["User"] = relationship(back_populates="branch_roles")


# =============================================================================
# Catalog Models
# =============================================================================


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

    __table_args__ = (
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

    __table_args__ = (
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
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    popular: Mapped[bool] = mapped_column(Boolean, default=False)
    badge: Mapped[Optional[str]] = mapped_column(Text)  # "Nuevo", "Popular", etc.
    # DEPRECATED: Use ProductDietaryProfile instead (Phase 2)
    seal: Mapped[Optional[str]] = mapped_column(Text)  # "Vegano", "Sin Gluten", etc.
    # DEPRECATED: Use ProductAllergen table instead (Phase 0)
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
    is_available: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    branch: Mapped["Branch"] = relationship(back_populates="branch_products")
    product: Mapped["Product"] = relationship(back_populates="branch_products")

    # CRIT-04 FIX: Unique constraint to prevent duplicate branch-product entries
    __table_args__ = (
        UniqueConstraint("branch_id", "product_id", name="uq_branch_product"),
        Index("ix_branch_product_branch_product", "branch_id", "product_id"),
    )


class Allergen(AuditMixin, Base):
    """
    Allergen definition.
    Supports the 14 mandatory EU allergens plus optional/regional allergens.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "allergen"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # EU 1169/2011 - 14 mandatory allergens vs optional ones
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Severity level for the allergen (general severity, not per-product)
    # Values: "mild", "moderate", "severe", "life_threatening"
    severity: Mapped[str] = mapped_column(Text, default="moderate", nullable=False)

    # Relationships
    product_allergens: Mapped[list["ProductAllergen"]] = relationship(back_populates="allergen")
    # Cross-reactions where this allergen is the primary
    cross_reactions_from: Mapped[list["AllergenCrossReaction"]] = relationship(
        back_populates="allergen",
        foreign_keys="AllergenCrossReaction.allergen_id"
    )
    # Cross-reactions where this allergen is the related one
    cross_reactions_to: Mapped[list["AllergenCrossReaction"]] = relationship(
        back_populates="cross_reacts_with",
        foreign_keys="AllergenCrossReaction.cross_reacts_with_id"
    )


# =============================================================================
# Product Allergen (Normalized M:N with presence type) - Phase 0
# =============================================================================


class ProductAllergen(AuditMixin, Base):
    """
    Normalized many-to-many relationship between products and allergens.
    Replaces the allergen_ids JSON field with proper relational structure.
    Supports three presence types: contains, may_contain (traces), free_from.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product_allergen"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allergen_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("allergen.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Presence types: "contains" (definitely has), "may_contain" (traces), "free_from" (guaranteed free)
    presence_type: Mapped[str] = mapped_column(Text, default="contains", nullable=False)

    # Risk level specific to this product-allergen combination
    # Values: "low" (minimal traces), "standard" (normal presence), "high" (main ingredient)
    risk_level: Mapped[str] = mapped_column(Text, default="standard", nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="product_allergens")
    allergen: Mapped["Allergen"] = relationship(back_populates="product_allergens")

    __table_args__ = (
        UniqueConstraint("product_id", "allergen_id", "presence_type", name="uq_product_allergen_presence"),
        Index("ix_product_allergen_product", "product_id"),
        Index("ix_product_allergen_allergen", "allergen_id"),
    )


# =============================================================================
# Allergen Cross-Reactions (Self-referential M:N)
# =============================================================================


class AllergenCrossReaction(AuditMixin, Base):
    """
    Cross-reaction information between allergens.
    Example: People allergic to latex may react to avocado, banana, kiwi.

    This is a self-referential M:N relationship on the Allergen table.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "allergen_cross_reaction"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )

    # The primary allergen (the allergy the person has)
    allergen_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("allergen.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # The food/allergen that may cause cross-reaction
    cross_reacts_with_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("allergen.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Probability of cross-reaction: "high", "medium", "low"
    probability: Mapped[str] = mapped_column(Text, default="medium", nullable=False)

    # Additional notes about the cross-reaction
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    allergen: Mapped["Allergen"] = relationship(
        back_populates="cross_reactions_from",
        foreign_keys=[allergen_id]
    )
    cross_reacts_with: Mapped["Allergen"] = relationship(
        back_populates="cross_reactions_to",
        foreign_keys=[cross_reacts_with_id]
    )

    __table_args__ = (
        UniqueConstraint("allergen_id", "cross_reacts_with_id", name="uq_allergen_cross_reaction"),
        Index("ix_cross_reaction_allergen", "allergen_id"),
        Index("ix_cross_reaction_cross_reacts", "cross_reacts_with_id"),
    )


# =============================================================================
# Ingredient System - Phase 1
# =============================================================================


class IngredientGroup(AuditMixin, Base):
    """
    Classification group for ingredients.
    Groups: proteina, vegetal, lacteo, cereal, condimento, otro
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "ingredient_group"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    ingredients: Mapped[list["Ingredient"]] = relationship(back_populates="group")


class Ingredient(AuditMixin, Base):
    """
    Ingredient catalog entry.
    Ingredients can be simple (e.g., tomato) or processed (e.g., mayonnaise with sub-ingredients).
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "ingredient"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    group_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("ingredient_group.id"), index=True
    )
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    group: Mapped[Optional["IngredientGroup"]] = relationship(back_populates="ingredients")
    sub_ingredients: Mapped[list["SubIngredient"]] = relationship(back_populates="ingredient", cascade="all, delete-orphan")
    product_ingredients: Mapped[list["ProductIngredient"]] = relationship(back_populates="ingredient")


class SubIngredient(AuditMixin, Base):
    """
    Sub-ingredient of a processed ingredient.
    Example: Mayonnaise (processed) contains eggs, oil, lemon.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "sub_ingredient"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    ingredient: Mapped["Ingredient"] = relationship(back_populates="sub_ingredients")


class ProductIngredient(AuditMixin, Base):
    """
    Many-to-many relationship between products and ingredients.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product_ingredient"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ingredient_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ingredient.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)  # Main ingredient flag
    notes: Mapped[Optional[str]] = mapped_column(Text)  # e.g., "fresco", "sin semillas"

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="product_ingredients")
    ingredient: Mapped["Ingredient"] = relationship(back_populates="product_ingredients")

    __table_args__ = (
        UniqueConstraint("product_id", "ingredient_id", name="uq_product_ingredient"),
    )


# =============================================================================
# Dietary Profile - Phase 2
# =============================================================================


class ProductDietaryProfile(AuditMixin, Base):
    """
    Dietary profile flags for a product.
    1:1 relationship with Product (one profile per product).
    Replaces the 'seal' field with structured boolean flags.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product_dietary_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False)
    is_gluten_free: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dairy_free: Mapped[bool] = mapped_column(Boolean, default=False)
    is_celiac_safe: Mapped[bool] = mapped_column(Boolean, default=False)  # More restrictive than gluten-free
    is_keto: Mapped[bool] = mapped_column(Boolean, default=False)
    is_low_sodium: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="dietary_profile")

    __table_args__ = (
        Index("ix_dietary_vegan", "is_vegan"),
        Index("ix_dietary_vegetarian", "is_vegetarian"),
        Index("ix_dietary_gluten_free", "is_gluten_free"),
    )


# =============================================================================
# Cooking and Sensory Profiles - Phase 3
# =============================================================================


class CookingMethod(AuditMixin, Base):
    """
    Cooking method catalog.
    Methods: horneado, frito, grillado, crudo, hervido, vapor, salteado, braseado
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "cooking_method"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(Text)


class FlavorProfile(AuditMixin, Base):
    """
    Flavor profile catalog.
    Flavors: suave, intenso, dulce, salado, acido, amargo, umami, picante
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    DB-LOW-10 FIX: Added index on name for efficient lookups.
    """

    __tablename__ = "flavor_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(Text)


class TextureProfile(AuditMixin, Base):
    """
    Texture profile catalog.
    Textures: crocante, cremoso, tierno, firme, esponjoso, gelatinoso, granulado
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    DB-LOW-10 FIX: Added index on name for efficient lookups.
    """

    __tablename__ = "texture_profile"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(Text)


class ProductCookingMethod(Base):
    """
    Many-to-many relationship between products and cooking methods.
    Composite primary key for efficiency.
    HIGH-08 FIX: Added tenant_id for multi-tenant consistency.
    """

    __tablename__ = "product_cooking_method"

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), primary_key=True
    )
    cooking_method_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("cooking_method.id", ondelete="CASCADE"), primary_key=True
    )
    # CRIT-DB-01 FIX: tenant_id is NOT NULL for multi-tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )

    # DB-CRIT-02 FIX: Indexes for M:N query performance
    __table_args__ = (
        Index("ix_product_cooking_method_product", "product_id"),
        Index("ix_product_cooking_method_method", "cooking_method_id"),
    )


class ProductFlavor(Base):
    """
    Many-to-many relationship between products and flavor profiles.
    Composite primary key for efficiency.
    HIGH-08 FIX: Added tenant_id for multi-tenant consistency.
    """

    __tablename__ = "product_flavor"

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), primary_key=True
    )
    flavor_profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("flavor_profile.id", ondelete="CASCADE"), primary_key=True
    )
    # CRIT-DB-02 FIX: tenant_id is NOT NULL for multi-tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )

    # DB-CRIT-02 FIX: Indexes for M:N query performance
    __table_args__ = (
        Index("ix_product_flavor_product", "product_id"),
        Index("ix_product_flavor_flavor", "flavor_profile_id"),
    )


class ProductTexture(Base):
    """
    Many-to-many relationship between products and texture profiles.
    Composite primary key for efficiency.
    HIGH-08 FIX: Added tenant_id for multi-tenant consistency.
    """

    __tablename__ = "product_texture"

    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), primary_key=True
    )
    texture_profile_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("texture_profile.id", ondelete="CASCADE"), primary_key=True
    )
    # CRIT-DB-03 FIX: tenant_id is NOT NULL for multi-tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )

    # DB-CRIT-02 FIX: Indexes for M:N query performance
    __table_args__ = (
        Index("ix_product_texture_product", "product_id"),
        Index("ix_product_texture_texture", "texture_profile_id"),
    )


class ProductCooking(AuditMixin, Base):
    """
    Additional cooking information for a product.
    1:1 relationship with Product.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product_cooking"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    uses_oil: Mapped[bool] = mapped_column(Boolean, default=False)
    prep_time_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    cook_time_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="cooking_info")


# =============================================================================
# Advanced Features - Phase 4
# =============================================================================


class ProductModification(AuditMixin, Base):
    """
    Allowed modifications for a product.
    Examples: remove onion, substitute bread for gluten-free.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product_modification"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)  # "remove" or "substitute"
    item: Mapped[str] = mapped_column(Text, nullable=False)  # e.g., "cebolla", "pan común por pan sin gluten"
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    extra_cost_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="modifications")


class ProductWarning(AuditMixin, Base):
    """
    Important warnings for a product.
    Examples: "Contains small bones", "Very spicy".
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product_warning"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(Text, default="info")  # info, warning, danger

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="warnings")


class ProductRAGConfig(AuditMixin, Base):
    """
    RAG chatbot configuration for a product.
    Controls how the AI responds about this product.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "product_rag_config"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    risk_level: Mapped[str] = mapped_column(Text, default="low")  # low, medium, high
    custom_disclaimer: Mapped[Optional[str]] = mapped_column(Text)
    highlight_allergens: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    product: Mapped["Product"] = relationship(back_populates="rag_config")


# =============================================================================
# Sector Model
# =============================================================================


class BranchSector(AuditMixin, Base):
    """
    Sector/zone within a branch where tables are located.
    Can be global (branch_id=NULL) or branch-specific.
    Used for organizing tables and generating table codes.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "branch_sector"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=True, index=True
    )  # NULL = global sector available to all branches
    name: Mapped[str] = mapped_column(Text, nullable=False)  # "Interior", "Terraza", "VIP"
    prefix: Mapped[str] = mapped_column(Text, nullable=False)  # "INT", "TER", "VIP" for table codes
    display_order: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    branch: Mapped[Optional["Branch"]] = relationship(back_populates="sectors")

    __table_args__ = (
        UniqueConstraint("tenant_id", "branch_id", "prefix", name="uq_sector_prefix"),
        # HIGH-DB-01 FIX: Partial unique index for global sectors (branch_id IS NULL)
        # In PostgreSQL, NULL values are not considered equal, so the UniqueConstraint
        # won't prevent duplicate global sectors. This partial index handles that case.
        Index(
            "uq_sector_prefix_global",
            "tenant_id",
            "prefix",
            unique=True,
            postgresql_where=text("branch_id IS NULL"),
        ),
    )


class WaiterSectorAssignment(AuditMixin, Base):
    """
    Daily assignment of waiters to sectors.
    A waiter can be assigned to multiple sectors.
    A sector can have multiple waiters assigned.
    Assignments are per-date to support shift scheduling.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "waiter_sector_assignment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    sector_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch_sector.id"), nullable=False, index=True
    )
    waiter_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), nullable=False, index=True
    )
    assignment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    shift: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )  # "MORNING", "AFTERNOON", "NIGHT" or NULL for all day

    # Relationships
    branch: Mapped["Branch"] = relationship()
    sector: Mapped["BranchSector"] = relationship()
    waiter: Mapped["User"] = relationship()

    __table_args__ = (
        # A waiter can only be assigned once to a sector on a given date/shift
        UniqueConstraint(
            "tenant_id", "branch_id", "sector_id", "waiter_id", "assignment_date", "shift",
            name="uq_waiter_sector_assignment"
        ),
        # HIGH-DB-02 FIX: A waiter can only be assigned to ONE sector per date/shift
        # This enforces exclusivity - a waiter cannot be in multiple sectors simultaneously
        UniqueConstraint(
            "tenant_id", "branch_id", "waiter_id", "assignment_date", "shift",
            name="uq_waiter_exclusive_assignment"
        ),
        Index("ix_assignment_date_branch", "assignment_date", "branch_id"),
    )


# =============================================================================
# Table and Session Models
# =============================================================================


class Table(AuditMixin, Base):
    """
    Physical table in a branch.
    Tables have a status that changes as diners use them.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "restaurant_table"  # "table" is reserved in SQL

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)  # "M-07", "Terraza-3"
    capacity: Mapped[int] = mapped_column(Integer, default=4)
    sector: Mapped[Optional[str]] = mapped_column(Text)  # Legacy: "Main", "Terrace", "VIP"
    # NEW: FK to BranchSector for sector-based waiter notifications
    sector_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branch_sector.id"), nullable=True, index=True
    )
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(
        Text, default="FREE", index=True
    )  # FREE, ACTIVE, PAYING, OUT_OF_SERVICE

    # DB-HIGH-05 FIX: Indexes for QR code lookup and status queries
    __table_args__ = (
        Index("ix_table_code", "code"),
        Index("ix_table_branch_status", "branch_id", "status"),
    )

    # Relationships
    branch: Mapped["Branch"] = relationship(back_populates="tables")
    sessions: Mapped[list["TableSession"]] = relationship(back_populates="table")
    sector_rel: Mapped[Optional["BranchSector"]] = relationship()


class TableSession(AuditMixin, Base):
    """
    An active dining session at a table.
    A session starts when diners sit down and ends when they pay and leave.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    Waiter-managed flow (HU-WAITER-MESA):
    - opened_by: "DINER" (QR scan) or "WAITER" (manual activation)
    - opened_by_waiter_id: Waiter who activated the table (when opened_by="WAITER")
    """

    __tablename__ = "table_session"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    table_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("restaurant_table.id"), nullable=False, index=True
    )
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(Text, default="OPEN", index=True)  # OPEN, PAYING, CLOSED
    assigned_waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # HU-WAITER-MESA: Traceability fields for session origin
    # "DINER" = opened by customer scanning QR, "WAITER" = opened manually by waiter
    opened_by: Mapped[str] = mapped_column(Text, default="DINER", nullable=False)
    # Waiter who opened the session (only set when opened_by="WAITER")
    opened_by_waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )

    # Relationships
    table: Mapped["Table"] = relationship(back_populates="sessions")
    rounds: Mapped[list["Round"]] = relationship(back_populates="session")
    service_calls: Mapped[list["ServiceCall"]] = relationship(back_populates="session")
    checks: Mapped[list["Check"]] = relationship(back_populates="session")
    diners: Mapped[list["Diner"]] = relationship(back_populates="session")

    __table_args__ = (
        # Composite index for tables list by branch and status
        Index("ix_table_session_branch_status", "branch_id", "status"),
    )


class Diner(AuditMixin, Base):
    """
    A person dining at a table session.
    Tracks who is at the table for order attribution and payment allocation.
    Phase 2 improvement: Persistent diner entities instead of anonymous strings.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "diner"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("table_session.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)  # Diner's display name
    color: Mapped[str] = mapped_column(Text, nullable=False)  # Hex color for UI (#RRGGBB)
    # HIGH-03 FIX: Add index for idempotency lookups
    local_id: Mapped[Optional[str]] = mapped_column(Text, index=True)  # Frontend UUID for syncing
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="diners")
    round_items: Mapped[list["RoundItem"]] = relationship(back_populates="diner")
    charges: Mapped[list["Charge"]] = relationship(back_populates="diner")

    __table_args__ = (
        # HIGH-03 FIX: Composite index for idempotency check (session_id + local_id)
        Index("ix_diner_session_local_id", "session_id", "local_id"),
        # MED-CONS-03: Unique constraint for idempotency (prevents duplicate diners)
        UniqueConstraint("session_id", "local_id", name="uq_diner_session_local_id"),
    )


# =============================================================================
# Order Models
# =============================================================================


class Round(AuditMixin, Base):
    """
    A round of orders within a table session.
    Diners can submit multiple rounds during their visit.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    Waiter-managed flow (HU-WAITER-MESA):
    - submitted_by: "DINER" (pwaMenu) or "WAITER" (pwaWaiter)
    - submitted_by_waiter_id: Waiter who submitted the round (when submitted_by="WAITER")
    """

    __tablename__ = "round"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    table_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("table_session.id"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(
        Text, default="DRAFT", index=True
    )  # DRAFT, SUBMITTED, IN_KITCHEN, READY, SERVED, CANCELED
    # HIGH-03 FIX: Add index for kitchen queue ordering
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    # CRIT-IDEMP-01 FIX: Idempotency key to prevent duplicate round submissions
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text, index=True)

    # HU-WAITER-MESA: Traceability fields for round submission origin
    # "DINER" = submitted via pwaMenu, "WAITER" = submitted via pwaWaiter
    submitted_by: Mapped[str] = mapped_column(Text, default="DINER", nullable=False)
    # Waiter who submitted the round (only set when submitted_by="WAITER")
    submitted_by_waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="rounds")
    items: Mapped[list["RoundItem"]] = relationship(back_populates="round")
    kitchen_tickets: Mapped[list["KitchenTicket"]] = relationship(back_populates="round")

    __table_args__ = (
        # Composite index for kitchen pending rounds query (branch_id + status)
        Index("ix_round_branch_status", "branch_id", "status"),
        # HIGH-03 FIX: Composite index for kitchen queue ordering (status + submitted_at)
        Index("ix_round_status_submitted", "status", "submitted_at"),
    )

    # MED-01 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        return f"<Round(id={self.id}, round_number={self.round_number}, status='{self.status}', session_id={self.table_session_id})>"


class RoundItem(AuditMixin, Base):
    """
    A single item within a round.
    Stores the price at the time of order for historical accuracy.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "round_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    round_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("round.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id"), nullable=False, index=True
    )
    diner_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("diner.id"), index=True
    )  # Phase 2: Optional FK to Diner (nullable for backwards compatibility)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # DB-CRIT-05 FIX: CHECK constraint to ensure positive quantity
    __table_args__ = (
        CheckConstraint("qty > 0", name="chk_round_item_qty_positive"),
        CheckConstraint("unit_price_cents >= 0", name="chk_round_item_price_non_negative"),
    )

    # Relationships
    round: Mapped["Round"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
    diner: Mapped[Optional["Diner"]] = relationship(back_populates="round_items")


# =============================================================================
# Kitchen Ticket Model (Phase 4)
# =============================================================================


class KitchenTicket(AuditMixin, Base):
    """
    A kitchen ticket groups items from a round by preparation station.

    Phase 4 improvement: Allows kitchen to have separate tickets for:
    - Bar (drinks)
    - Hot kitchen (main dishes)
    - Cold kitchen (salads, desserts)
    - etc.

    Each ticket tracks its own status, allowing partial completion of rounds.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "kitchen_ticket"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    round_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("round.id"), nullable=False, index=True
    )
    # BACK-CRIT-03 FIX: Add index for frequent station/status queries
    station: Mapped[str] = mapped_column(
        Text, nullable=False, index=True
    )  # BAR, HOT_KITCHEN, COLD_KITCHEN, GRILL, etc.
    status: Mapped[str] = mapped_column(
        Text, default="PENDING", index=True
    )  # PENDING, IN_PROGRESS, READY, DELIVERED
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher = more urgent
    notes: Mapped[Optional[str]] = mapped_column(Text)  # Kitchen notes
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # DB-HIGH-09 FIX: Composite index for kitchen queue queries by station+status
    __table_args__ = (
        Index("ix_kitchen_ticket_station_status", "station", "status"),
        Index("ix_kitchen_ticket_branch_status", "branch_id", "status"),
    )

    # Relationships
    round: Mapped["Round"] = relationship(back_populates="kitchen_tickets")
    items: Mapped[list["KitchenTicketItem"]] = relationship(back_populates="ticket")


class KitchenTicketItem(AuditMixin, Base):
    """
    Links a RoundItem to a KitchenTicket.

    Allows tracking which items are in which ticket and their preparation status.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "kitchen_ticket_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    ticket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kitchen_ticket.id"), nullable=False, index=True
    )
    round_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("round_item.id"), nullable=False, index=True
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)  # May be partial qty
    status: Mapped[str] = mapped_column(
        Text, default="PENDING"
    )  # PENDING, IN_PROGRESS, READY

    # Relationships
    ticket: Mapped["KitchenTicket"] = relationship(back_populates="items")
    round_item: Mapped["RoundItem"] = relationship()


# =============================================================================
# Service Call Model
# =============================================================================


class ServiceCall(AuditMixin, Base):
    """
    A request from diners to get waiter attention.
    Can be for general service or payment help.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "service_call"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    table_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("table_session.id"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(
        Text, default="WAITER_CALL"
    )  # WAITER_CALL, PAYMENT_HELP, OTHER
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(Text, default="OPEN", index=True)  # OPEN, ACKED, CLOSED
    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acked_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id")
    )

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="service_calls")

    __table_args__ = (
        # Composite index for waiter pending service calls query (branch_id + status)
        Index("ix_service_call_branch_status", "branch_id", "status"),
    )


# =============================================================================
# Billing Models
# =============================================================================


class Check(AuditMixin, Base):
    """
    The bill/check for a table session.
    Tracks total amount, payments, and status.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "check"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    table_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("table_session.id"), nullable=False, index=True
    )
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(
        Text, default="OPEN", index=True
    )  # OPEN, REQUESTED, IN_PAYMENT, PAID, FAILED
    total_cents: Mapped[int] = mapped_column(Integer, default=0)
    paid_cents: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="checks")
    payments: Mapped[list["Payment"]] = relationship(back_populates="check")
    # HIGH-03 FIX: Added charges relationship for bidirectional access
    charges: Mapped[list["Charge"]] = relationship(back_populates="check")

    __table_args__ = (
        # MED-CONS-01: Ensure paid_cents never exceeds total_cents
        CheckConstraint("paid_cents <= total_cents", name="chk_paid_not_exceed_total"),
        # MED-CONS-02: Ensure amounts are non-negative
        CheckConstraint("total_cents >= 0", name="chk_total_non_negative"),
        CheckConstraint("paid_cents >= 0", name="chk_paid_non_negative"),
    )


class Payment(AuditMixin, Base):
    """
    A payment towards a check.
    Multiple payments can be made for partial payments.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    Waiter-managed flow (HU-WAITER-MESA):
    - payment_category: "DIGITAL" (Mercado Pago) or "MANUAL" (waiter-registered)
    - registered_by: "SYSTEM" (automatic), "DINER" (pwaMenu), or "WAITER" (pwaWaiter)
    - registered_by_waiter_id: Waiter who registered the payment
    - manual_method: Payment method for manual payments (CASH, CARD_PHYSICAL, TRANSFER_EXTERNAL, OTHER)
    """

    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    check_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("check.id"), nullable=False, index=True
    )
    payer_diner_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("diner.id"), index=True
    )  # Phase 3: Who made the payment
    provider: Mapped[str] = mapped_column(Text, default="CASH")  # CASH, MERCADO_PAGO
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(
        Text, default="PENDING", index=True
    )  # PENDING, APPROVED, REJECTED
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    external_id: Mapped[Optional[str]] = mapped_column(Text)  # MP payment ID

    # HU-WAITER-MESA: Payment category and registration traceability
    # "DIGITAL" = processed via Mercado Pago, "MANUAL" = registered manually by waiter
    payment_category: Mapped[str] = mapped_column(Text, default="DIGITAL", nullable=False)
    # Who registered the payment: "SYSTEM" (webhook/automatic), "DINER" (pwaMenu), "WAITER" (pwaWaiter)
    registered_by: Mapped[str] = mapped_column(Text, default="SYSTEM", nullable=False)
    # Waiter who registered the payment (only set when registered_by="WAITER")
    registered_by_waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )
    # Payment method for manual payments: CASH, CARD_PHYSICAL, TRANSFER_EXTERNAL, OTHER_MANUAL
    manual_method: Mapped[Optional[str]] = mapped_column(Text)
    # Optional notes for manual payments (e.g., "Paid with $5000 bill, change given")
    manual_notes: Mapped[Optional[str]] = mapped_column(Text)

    # DB-CRIT-04 FIX: CHECK constraint to ensure positive payment amounts
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="chk_payment_amount_positive"),
    )

    # Relationships
    check: Mapped["Check"] = relationship(back_populates="payments")
    allocations: Mapped[list["Allocation"]] = relationship(back_populates="payment")


class Charge(AuditMixin, Base):
    """
    A charge assigned to a specific diner.
    Phase 3 improvement: Each item consumed generates a charge for payment allocation.
    Allows flexible split payment scenarios.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "charge"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    check_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("check.id"), nullable=False, index=True
    )
    diner_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("diner.id"), index=True
    )  # Who is responsible for this charge (nullable for shared items)
    round_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("round_item.id"), nullable=False, index=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # DB-HIGH-07 FIX: CHECK constraint to ensure positive charge amounts
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="chk_charge_amount_positive"),
    )

    # Relationships
    # HIGH-03 FIX: Added back_populates for bidirectional relationship
    check: Mapped["Check"] = relationship(back_populates="charges")
    diner: Mapped[Optional["Diner"]] = relationship(back_populates="charges")
    allocations: Mapped[list["Allocation"]] = relationship(back_populates="charge")


class Allocation(AuditMixin, Base):
    """
    Links a Payment to specific Charges.
    Phase 3 improvement: Supports FIFO allocation and flexible split payments.
    A single payment can cover multiple charges, and a charge can be covered by multiple payments.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "allocation"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    payment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("payment.id"), nullable=False, index=True
    )
    charge_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("charge.id"), nullable=False, index=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    payment: Mapped["Payment"] = relationship(back_populates="allocations")
    charge: Mapped["Charge"] = relationship(back_populates="allocations")

    __table_args__ = (
        # MED-IDX-01: Composite index for balance queries
        Index("ix_allocation_charge_payment", "charge_id", "payment_id"),
        # DB-HIGH-08 FIX: CHECK constraint to ensure positive allocation amounts
        CheckConstraint("amount_cents > 0", name="chk_allocation_amount_positive"),
    )


# =============================================================================
# RAG Knowledge Base Models
# =============================================================================


class KnowledgeDocument(AuditMixin, Base):
    """
    A document chunk in the RAG knowledge base.
    Stores text content with its vector embedding for semantic search.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "knowledge_document"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branch.id"), index=True
    )  # NULL means applies to all branches

    # Document content
    title: Mapped[Optional[str]] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(Text)  # "product", "menu", "faq", etc.
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger)  # Reference to source entity

    # Vector embedding (1536 dimensions for nomic-embed-text)
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=True)


class ChatLog(AuditMixin, Base):
    """
    Log of chat interactions for auditing and improvement.
    Records questions, retrieved context, and generated answers.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "chat_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("branch.id"), index=True
    )

    # Session info (can be table session or admin user)
    table_session_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("table_session.id"), index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )

    # Chat content
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    # Retrieved context (JSON array of document IDs and scores)
    context_docs: Mapped[Optional[str]] = mapped_column(Text)  # JSON: [{"id": 1, "score": 0.95}, ...]

    # Quality metrics
    response_time_ms: Mapped[Optional[int]] = mapped_column(Integer)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)

    # User feedback
    feedback_helpful: Mapped[Optional[bool]] = mapped_column(Boolean)


# =============================================================================
# Promotion Models
# =============================================================================


class Promotion(AuditMixin, Base):
    """
    Promotional offers that can apply to multiple branches.
    Can include multiple products at a special price.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    DB-MED-03 FIX: Added CHECK constraint to ensure start_date <= end_date.
    """

    __tablename__ = "promotion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)  # Promotional price
    image: Mapped[Optional[str]] = mapped_column(Text)
    start_date: Mapped[str] = mapped_column(Text, nullable=False)  # "2024-01-01"
    end_date: Mapped[str] = mapped_column(Text, nullable=False)  # "2024-12-31"
    start_time: Mapped[str] = mapped_column(Text, default="00:00")  # "09:00"
    end_time: Mapped[str] = mapped_column(Text, default="23:59")  # "23:00"
    promotion_type_id: Mapped[Optional[str]] = mapped_column(Text)  # Reference to frontend type

    # DB-MED-03 FIX: Ensure date consistency
    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="chk_promotion_dates"),
        CheckConstraint("price_cents >= 0", name="chk_promotion_price_positive"),
    )

    # Relationships
    branches: Mapped[list["PromotionBranch"]] = relationship(
        back_populates="promotion", cascade="all, delete-orphan"
    )
    items: Mapped[list["PromotionItem"]] = relationship(
        back_populates="promotion", cascade="all, delete-orphan"
    )


class PromotionBranch(AuditMixin, Base):
    """
    Many-to-many relationship between promotions and branches.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    DB-MED-09 FIX: Added UniqueConstraint to prevent duplicate promotion-branch pairs.
    """

    __tablename__ = "promotion_branch"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    promotion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("promotion.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )

    # DB-MED-09 FIX: Prevent duplicate promotion-branch pairs
    __table_args__ = (
        UniqueConstraint("promotion_id", "branch_id", name="uq_promotion_branch"),
    )

    # Relationships
    promotion: Mapped["Promotion"] = relationship(back_populates="branches")
    branch: Mapped["Branch"] = relationship()


class PromotionItem(AuditMixin, Base):
    """
    Products included in a promotion with their quantities.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    DB-MED-10 FIX: Added index on product_id for efficient product lookups.
    """

    __tablename__ = "promotion_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    promotion_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("promotion.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    # DB-MED-10 FIX: Index for efficient product lookups + CHECK constraint for quantity
    __table_args__ = (
        Index("ix_promotion_item_product", "product_id"),
        CheckConstraint("quantity > 0", name="chk_promotion_item_qty_positive"),
    )

    # Relationships
    promotion: Mapped["Promotion"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


# =============================================================================
# Branch Exclusion Models (Category/Subcategory exclusions per branch)
# =============================================================================


class BranchCategoryExclusion(AuditMixin, Base):
    """
    Marks a category as excluded (not sold) in a specific branch.
    When a category is excluded, all its subcategories and products are also excluded.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "branch_category_exclusion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("category.id"), nullable=False, index=True
    )

    # Relationships
    branch: Mapped["Branch"] = relationship()
    category: Mapped["Category"] = relationship()


class BranchSubcategoryExclusion(AuditMixin, Base):
    """
    Marks a subcategory as excluded (not sold) in a specific branch.
    When a subcategory is excluded, all its products are also excluded.
    This allows more granular control than category-level exclusion.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "branch_subcategory_exclusion"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    subcategory_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("subcategory.id"), nullable=False, index=True
    )

    # Relationships
    branch: Mapped["Branch"] = relationship()
    subcategory: Mapped["Subcategory"] = relationship()


# =============================================================================
# Audit Log Model
# =============================================================================


class AuditLog(AuditMixin, Base):
    """
    Records all significant changes to entities for audit trail.
    Stores who did what, when, and the before/after state.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )

    # Who made the change
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )
    user_email: Mapped[Optional[str]] = mapped_column(Text)

    # What was changed
    entity_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # CREATE, UPDATE, DELETE, SOFT_DELETE, RESTORE

    # Change details (JSON)
    old_values: Mapped[Optional[str]] = mapped_column(Text)  # JSON of previous state
    new_values: Mapped[Optional[str]] = mapped_column(Text)  # JSON of new state
    changes: Mapped[Optional[str]] = mapped_column(Text)  # JSON of changed fields

    # Metadata
    ip_address: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)


class Recipe(AuditMixin, Base):
    """
    Recipe technical sheet created by kitchen staff.
    Contains detailed preparation instructions, ingredients, and metadata.
    Can be linked to a product or be standalone.
    Used as knowledge source for RAG chatbot ingestion.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    DB-MED-04 FIX: Added CHECK constraint for cost vs suggested_price.
    DB-MED-06 FIX: Added UniqueConstraint for name per branch.
    """

    __tablename__ = "recipe"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )

    # Basic info
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)  # Descripción larga para detalle
    short_description: Mapped[Optional[str]] = mapped_column(Text)  # Descripción corta para preview (100-150 chars)
    image: Mapped[Optional[str]] = mapped_column(Text)

    # Link to product (optional - recipe can exist without product)
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("product.id"), index=True
    )

    # Category/Subcategory relationship (normalized)
    subcategory_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("subcategory.id"), index=True
    )

    # Technical details
    cuisine_type: Mapped[Optional[str]] = mapped_column(Text)  # Italiana, Argentina, Mexicana, etc.
    difficulty: Mapped[Optional[str]] = mapped_column(Text)  # Fácil, Media, Difícil
    prep_time_minutes: Mapped[Optional[int]] = mapped_column(Integer)  # Tiempo de preparación
    cook_time_minutes: Mapped[Optional[int]] = mapped_column(Integer)  # Tiempo de cocción
    servings: Mapped[Optional[int]] = mapped_column(Integer)  # Porciones
    calories_per_serving: Mapped[Optional[int]] = mapped_column(Integer)

    # Ingredients (JSON array)
    # Format: [{"name": "Harina", "quantity": "500", "unit": "g", "notes": "tamizada"}]
    ingredients: Mapped[Optional[str]] = mapped_column(Text)

    # Preparation steps (JSON array)
    # Format: [{"step": 1, "instruction": "Mezclar los ingredientes secos", "time_minutes": 5}]
    preparation_steps: Mapped[Optional[str]] = mapped_column(Text)

    # Additional info
    chef_notes: Mapped[Optional[str]] = mapped_column(Text)  # Notas del chef
    presentation_tips: Mapped[Optional[str]] = mapped_column(Text)  # Tips de presentación
    storage_instructions: Mapped[Optional[str]] = mapped_column(Text)  # Instrucciones de almacenamiento
    allergens: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of allergen names
    dietary_tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array: ["Vegano", "Sin Gluten", etc.]

    # Sensory profile (Phase 3 - planteo.md)
    # Format: ["suave", "intenso", "dulce", "salado", "acido", "amargo", "umami", "picante"]
    flavors: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of flavor profiles
    # Format: ["crocante", "cremoso", "tierno", "firme", "esponjoso", "gelatinoso", "granulado"]
    textures: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of texture profiles

    # Cooking info (Phase 3 - planteo.md)
    # Format: ["horneado", "frito", "grillado", "crudo", "hervido", "vapor", "salteado", "braseado"]
    cooking_methods: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of cooking methods
    uses_oil: Mapped[bool] = mapped_column(Boolean, default=False)  # Si usa aceite en la preparación

    # Celiac safety (different from gluten_free - requires special handling protocols)
    is_celiac_safe: Mapped[bool] = mapped_column(Boolean, default=False)  # Apto celíaco (protocolos especiales)
    allergen_notes: Mapped[Optional[str]] = mapped_column(Text)  # Notas adicionales sobre alérgenos

    # Modifications allowed (Phase 4 - planteo.md)
    # Format: [{"action": "remove", "item": "cebolla", "allowed": true}, {"action": "substitute", "item": "papas por ensalada", "allowed": true}]
    modifications: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of allowed modifications

    # Warnings (Phase 4 - planteo.md)
    # Format: ["Contiene huesos pequeños", "Preparación con alcohol", "Servido muy caliente"]
    warnings: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of warnings

    # Cost calculation
    cost_cents: Mapped[Optional[int]] = mapped_column(Integer)  # Costo de preparación en centavos
    suggested_price_cents: Mapped[Optional[int]] = mapped_column(Integer)  # Precio sugerido de venta

    # Yield and portions
    yield_quantity: Mapped[Optional[str]] = mapped_column(Text)  # Rendimiento (ej: "2kg", "24 unidades")
    yield_unit: Mapped[Optional[str]] = mapped_column(Text)  # Unidad de rendimiento
    portion_size: Mapped[Optional[str]] = mapped_column(Text)  # Tamaño de porción (ej: "200g", "1 unidad")

    # RAG integration (Phase 5 - planteo.md)
    is_ingested: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # Si fue ingestado al RAG
    last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Risk level for RAG responses: low (no disclaimers), medium (verify with staff), high (always defer to staff)
    risk_level: Mapped[str] = mapped_column(Text, default="low")  # low, medium, high
    custom_rag_disclaimer: Mapped[Optional[str]] = mapped_column(Text)  # Disclaimer personalizado para RAG

    # DB-MED-04 FIX: Cost should be less than suggested price (profit margin)
    # DB-MED-06 FIX: Recipe name should be unique per branch
    __table_args__ = (
        UniqueConstraint("branch_id", "name", name="uq_recipe_branch_name"),
        CheckConstraint(
            "(cost_cents IS NULL OR suggested_price_cents IS NULL OR cost_cents <= suggested_price_cents)",
            name="chk_recipe_cost_price"
        ),
        CheckConstraint("cost_cents IS NULL OR cost_cents >= 0", name="chk_recipe_cost_positive"),
        CheckConstraint("suggested_price_cents IS NULL OR suggested_price_cents >= 0", name="chk_recipe_price_positive"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship()
    branch: Mapped["Branch"] = relationship()
    subcategory: Mapped[Optional["Subcategory"]] = relationship()
    recipe_allergens: Mapped[list["RecipeAllergen"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    # Products derived from this recipe (propuesta1.md - 1:N relationship)
    # A recipe can be the source for multiple products (e.g., "Milanesa" recipe
    # can derive "Milanesa Simple", "Milanesa Napolitana", "Milanesa a Caballo")
    products: Mapped[list["Product"]] = relationship(
        back_populates="recipe", foreign_keys="[Product.recipe_id]"
    )


# =============================================================================
# Recipe Allergen (Normalized M:N relationship)
# =============================================================================


class RecipeAllergen(AuditMixin, Base):
    """
    Normalized many-to-many relationship between recipes and allergens.
    Replaces the allergens JSON field with proper relational structure.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "recipe_allergen"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    recipe_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allergen_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("allergen.id"), nullable=False, index=True
    )

    # Risk level specific to this recipe-allergen combination
    # Values: "low" (minimal traces), "standard" (normal presence), "high" (main ingredient)
    risk_level: Mapped[str] = mapped_column(Text, default="standard", nullable=False)

    # Unique constraint: one allergen per recipe
    __table_args__ = (
        UniqueConstraint("recipe_id", "allergen_id", name="uq_recipe_allergen"),
        Index("ix_recipe_allergen_recipe", "recipe_id"),
        Index("ix_recipe_allergen_allergen", "allergen_id"),
    )

    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="recipe_allergens")
    allergen: Mapped["Allergen"] = relationship()
