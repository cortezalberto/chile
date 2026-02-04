"""
Billing Models: Check, Payment, Charge, Allocation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .table import TableSession
    from .customer import Diner
    from .order import RoundItem
    from .user import User


class Check(AuditMixin, Base):
    """
    The bill/check for a table session.
    Tracks total amount, payments, and status.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    MDL-CRIT-01 FIX: Table renamed from "check" to "app_check" because
    "CHECK" is a reserved SQL keyword (used for CHECK constraints).
    """

    __tablename__ = "app_check"

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

    # MDL-LOW-01 FIX: Add __repr__ for consistent debugging
    def __repr__(self) -> str:
        return f"<Check(id={self.id}, session={self.table_session_id}, total={self.total_cents}, paid={self.paid_cents}, status={self.status})>"

    __table_args__ = (
        # MED-CONS-01: Ensure paid_cents never exceeds total_cents
        CheckConstraint("paid_cents <= total_cents", name="chk_paid_not_exceed_total"),
        # MED-CONS-02: Ensure amounts are non-negative
        CheckConstraint("total_cents >= 0", name="chk_total_non_negative"),
        CheckConstraint("paid_cents >= 0", name="chk_paid_non_negative"),
        # OPT-02: Composite index for branch + status queries
        Index("ix_check_branch_status", "branch_id", "status"),
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
        BigInteger, ForeignKey("app_check.id"), nullable=False, index=True
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
    # MDL-MED-11 FIX: Added relationship for FK
    payer_diner: Mapped[Optional["Diner"]] = relationship()
    # MDL-MED-12 FIX: Added relationship for FK
    registered_by_waiter: Mapped[Optional["User"]] = relationship()

    # MDL-LOW-01 FIX: Add __repr__ for consistent debugging
    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, check={self.check_id}, amount={self.amount_cents}, status={self.status}, provider={self.provider})>"


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
        BigInteger, ForeignKey("app_check.id"), nullable=False, index=True
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
