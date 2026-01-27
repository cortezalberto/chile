"""
Table and Session Models: Table, TableSession.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .tenant import Branch
    from .sector import BranchSector
    from .order import Round
    from .kitchen import ServiceCall
    from .billing import Check
    from .customer import Diner
    from .user import User


class Table(AuditMixin, Base):
    """
    Physical table in a branch.
    Tables have a status that changes as diners use them.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    # MDL-LOW-02 FIX: "table" is a reserved SQL keyword, using "restaurant_table"
    # to avoid quoting issues and improve readability in raw SQL queries
    __tablename__ = "restaurant_table"

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
    # HIGH-BACK-POP-01 FIX: Added back_populates for bidirectional relationship
    sector_rel: Mapped[Optional["BranchSector"]] = relationship(back_populates="tables")


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
    # MDL-MED-14 FIX: Added relationship for FK
    assigned_waiter: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[assigned_waiter_id]
    )
    # MDL-MED-15 FIX: Added relationship for FK
    opened_by_waiter: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys=[opened_by_waiter_id]
    )

    # MDL-LOW-01 FIX: Add __repr__ for consistent debugging
    def __repr__(self) -> str:
        return f"<TableSession(id={self.id}, table_id={self.table_id}, status={self.status})>"

    __table_args__ = (
        # Composite index for tables list by branch and status
        Index("ix_table_session_branch_status", "branch_id", "status"),
    )
