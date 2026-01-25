"""
Ingredient Models: IngredientGroup, Ingredient, SubIngredient, ProductIngredient.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .catalog import Product


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
