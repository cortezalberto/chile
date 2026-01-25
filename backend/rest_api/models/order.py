"""
Order Models: Round, RoundItem.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .table import TableSession
    from .catalog import Product
    from .customer import Diner
    from .kitchen import KitchenTicket


class Round(AuditMixin, Base):
    """
    A round of orders within a table session.
    Diners can submit multiple rounds during their visit.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    Waiter-managed flow (HU-WAITER-MESA):
    - submitted_by: "DINER" (pwaMenu) or "WAITER" (pwaWaiter)
    - submitted_by_waiter_id: Waiter who submitted the round (when submitted_by="WAITER")
    """

    __tablename__ = "round"

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
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(
        Text, default="DRAFT", index=True
    )  # DRAFT, SUBMITTED, IN_KITCHEN, READY, SERVED, CANCELED
    # HIGH-03 FIX: Add index for kitchen queue ordering
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    # CRIT-IDEMP-01 FIX: Idempotency key to prevent duplicate round submissions
    idempotency_key: Mapped[Optional[str]] = mapped_column(Text, index=True)

    # HU-WAITER-MESA: Traceability fields for round submission origin
    # "DINER" = submitted via pwaMenu, "WAITER" = submitted via pwaWaiter
    submitted_by: Mapped[str] = mapped_column(Text, default="DINER", nullable=False)
    # Waiter who submitted the round (only set when submitted_by="WAITER")
    submitted_by_waiter_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="rounds")
    items: Mapped[list["RoundItem"]] = relationship(back_populates="round")
    kitchen_tickets: Mapped[list["KitchenTicket"]] = relationship(back_populates="round")

    __table_args__ = (
        # Composite index for kitchen pending rounds query (branch_id + status)
        Index("ix_round_branch_status", "branch_id", "status"),
        # HIGH-03 FIX: Composite index for kitchen queue ordering (status + submitted_at)
        Index("ix_round_status_submitted", "status", "submitted_at"),
    )

    # MED-01 FIX: Add __repr__ for debugging
    def __repr__(self) -> str:
        return f"<Round(id={self.id}, round_number={self.round_number}, status='{self.status}', session_id={self.table_session_id})>"


class RoundItem(AuditMixin, Base):
    """
    A single item within a round.
    Stores the price at the time of order for historical accuracy.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "round_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    round_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("round.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id"), nullable=False, index=True
    )
    diner_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("diner.id"), index=True
    )  # Phase 2: Optional FK to Diner (nullable for backwards compatibility)
    qty: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    # DB-CRIT-05 FIX: CHECK constraint to ensure positive quantity
    __table_args__ = (
        CheckConstraint("qty > 0", name="chk_round_item_qty_positive"),
        CheckConstraint("unit_price_cents >= 0", name="chk_round_item_price_non_negative"),
    )

    # Relationships
    round: Mapped["Round"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
    diner: Mapped[Optional["Diner"]] = relationship(back_populates="round_items")
