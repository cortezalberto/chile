"""
Sector Models: BranchSector, WaiterSectorAssignment.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Date, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .tenant import Branch
    from .user import User
    from .table import Table


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
    # MDL-HIGH-01 FIX: Added reverse relationship from WaiterSectorAssignment
    waiter_assignments: Mapped[list["WaiterSectorAssignment"]] = relationship(
        back_populates="sector"
    )
    # HIGH-BACK-POP-01 FIX: Added reverse relationship for Table.sector_rel
    tables: Mapped[list["Table"]] = relationship(back_populates="sector_rel")

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

    # MDL-HIGH-01 FIX: Added back_populates for bidirectional relationships
    # Note: Reverse relationships added to Branch, BranchSector, and User models
    branch: Mapped["Branch"] = relationship(back_populates="waiter_assignments")
    sector: Mapped["BranchSector"] = relationship(back_populates="waiter_assignments")
    waiter: Mapped["User"] = relationship(back_populates="sector_assignments")

    __table_args__ = (
        # A waiter can only be assigned once to a sector on a given date/shift
        # (prevents duplicate assignment to the SAME sector)
        UniqueConstraint(
            "tenant_id", "branch_id", "sector_id", "waiter_id", "assignment_date", "shift",
            name="uq_waiter_sector_assignment"
        ),
        # MULTI-SECTOR FIX: Removed uq_waiter_exclusive_assignment constraint
        # Waiters can now be assigned to MULTIPLE sectors in the same branch/date/shift
        Index("ix_assignment_date_branch", "assignment_date", "branch_id"),
    )
