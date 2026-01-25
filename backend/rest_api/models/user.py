"""
User and Authentication Models.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .tenant import Tenant
    from .sector import WaiterSectorAssignment


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
    # MDL-HIGH-01 FIX: Added reverse relationship from WaiterSectorAssignment
    sector_assignments: Mapped[list["WaiterSectorAssignment"]] = relationship(
        back_populates="waiter"
    )

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
