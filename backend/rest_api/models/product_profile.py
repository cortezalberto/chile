"""
Product Profile Models: Dietary, Cooking, Flavor, Texture profiles and extensions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .catalog import Product


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


class CuisineType(AuditMixin, Base):
    """
    Cuisine type catalog for recipes.
    Types: Argentina, Italiana, Mexicana, Japonesa, China, Peruana, etc.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "cuisine_type"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    icon: Mapped[Optional[str]] = mapped_column(Text)  # Flag emoji


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
