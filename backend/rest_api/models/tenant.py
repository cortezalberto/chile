"""
Multi-Tenancy Models: Tenant and Branch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .user import User
    from .catalog import Product
    from .table import Table
    from .sector import BranchSector, WaiterSectorAssignment
    from .exclusion import BranchCategoryExclusion, BranchSubcategoryExclusion
    from .promotion import PromotionBranch
    from .catalog import BranchProduct


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
    # MDL-HIGH-01 FIX: Added reverse relationship from WaiterSectorAssignment
    waiter_assignments: Mapped[list["WaiterSectorAssignment"]] = relationship(
        back_populates="branch"
    )
    # MDL-HIGH-02 FIX: Added reverse relationship from PromotionBranch
    promotions: Mapped[list["PromotionBranch"]] = relationship(back_populates="branch")
    # MDL-HIGH-04 FIX: Added reverse relationships from exclusions
    category_exclusions: Mapped[list["BranchCategoryExclusion"]] = relationship(
        back_populates="branch"
    )
    subcategory_exclusions: Mapped[list["BranchSubcategoryExclusion"]] = relationship(
        back_populates="branch"
    )

    # MED-01 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        return f"<Branch(id={self.id}, name='{self.name}', slug='{self.slug}', tenant_id={self.tenant_id})>"
