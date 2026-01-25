"""
Branch Exclusion Models: BranchCategoryExclusion, BranchSubcategoryExclusion.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .tenant import Branch
    from .catalog import Category, Subcategory


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

    # DB-HIGH-01 FIX: UniqueConstraint to prevent duplicate exclusions
    __table_args__ = (
        UniqueConstraint("branch_id", "category_id", name="uq_branch_category_exclusion"),
    )

    # MDL-HIGH-04 FIX: Added back_populates for bidirectional relationships
    # Relationships
    branch: Mapped["Branch"] = relationship(back_populates="category_exclusions")
    category: Mapped["Category"] = relationship(back_populates="branch_exclusions")


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

    # DB-HIGH-02 FIX: UniqueConstraint to prevent duplicate exclusions
    __table_args__ = (
        UniqueConstraint("branch_id", "subcategory_id", name="uq_branch_subcategory_exclusion"),
    )

    # MDL-HIGH-04 FIX: Added back_populates for bidirectional relationships
    # Relationships
    branch: Mapped["Branch"] = relationship(back_populates="subcategory_exclusions")
    subcategory: Mapped["Subcategory"] = relationship(back_populates="branch_exclusions")
