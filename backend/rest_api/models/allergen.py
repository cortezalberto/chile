"""
Allergen Models: Allergen, ProductAllergen, AllergenCrossReaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .catalog import Product
    from .recipe import RecipeAllergen


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
    # MDL-HIGH-06 FIX: Added reverse relationship from RecipeAllergen
    recipe_allergens: Mapped[list["RecipeAllergen"]] = relationship(back_populates="allergen")
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
