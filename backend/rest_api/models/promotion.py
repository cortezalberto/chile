"""
Promotion Models: Promotion, PromotionBranch, PromotionItem.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .tenant import Branch
    from .catalog import Product


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

    # MDL-HIGH-02 FIX: Added back_populates for bidirectional relationship
    # Relationships
    promotion: Mapped["Promotion"] = relationship(back_populates="branches")
    branch: Mapped["Branch"] = relationship(back_populates="promotions")


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

    # MDL-HIGH-03 FIX: Added back_populates for bidirectional relationship
    # Relationships
    promotion: Mapped["Promotion"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship(back_populates="promotion_items")
