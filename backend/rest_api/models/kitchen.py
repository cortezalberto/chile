"""
Kitchen Models: KitchenTicket, KitchenTicketItem, ServiceCall.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .order import Round, RoundItem
    from .table import TableSession


class KitchenTicket(AuditMixin, Base):
    """
    A kitchen ticket groups items from a round by preparation station.

    Phase 4 improvement: Allows kitchen to have separate tickets for:
    - Bar (drinks)
    - Hot kitchen (main dishes)
    - Cold kitchen (salads, desserts)
    - etc.

    Each ticket tracks its own status, allowing partial completion of rounds.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "kitchen_ticket"

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
    # BACK-CRIT-03 FIX: Add index for frequent station/status queries
    station: Mapped[str] = mapped_column(
        Text, nullable=False, index=True
    )  # BAR, HOT_KITCHEN, COLD_KITCHEN, GRILL, etc.
    status: Mapped[str] = mapped_column(
        Text, default="PENDING", index=True
    )  # PENDING, IN_PROGRESS, READY, DELIVERED
    priority: Mapped[int] = mapped_column(Integer, default=0)  # Higher = more urgent
    notes: Mapped[Optional[str]] = mapped_column(Text)  # Kitchen notes
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # DB-HIGH-09 FIX: Composite index for kitchen queue queries by station+status
    __table_args__ = (
        Index("ix_kitchen_ticket_station_status", "station", "status"),
        Index("ix_kitchen_ticket_branch_status", "branch_id", "status"),
    )

    # Relationships
    round: Mapped["Round"] = relationship(back_populates="kitchen_tickets")
    items: Mapped[list["KitchenTicketItem"]] = relationship(back_populates="ticket")


class KitchenTicketItem(AuditMixin, Base):
    """
    Links a RoundItem to a KitchenTicket.

    Allows tracking which items are in which ticket and their preparation status.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "kitchen_ticket_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    ticket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("kitchen_ticket.id"), nullable=False, index=True
    )
    round_item_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("round_item.id"), nullable=False, index=True
    )
    qty: Mapped[int] = mapped_column(Integer, nullable=False)  # May be partial qty
    status: Mapped[str] = mapped_column(
        Text, default="PENDING"
    )  # PENDING, IN_PROGRESS, READY

    # Relationships
    ticket: Mapped["KitchenTicket"] = relationship(back_populates="items")
    round_item: Mapped["RoundItem"] = relationship()


class ServiceCall(AuditMixin, Base):
    """
    A request from diners to get waiter attention.
    Can be for general service or payment help.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "service_call"

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
    type: Mapped[str] = mapped_column(
        Text, default="WAITER_CALL"
    )  # WAITER_CALL, PAYMENT_HELP, OTHER
    # BACK-CRIT-03 FIX: Add index for frequent status queries
    status: Mapped[str] = mapped_column(Text, default="OPEN", index=True)  # OPEN, ACKED, CLOSED
    acked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acked_by_user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id")
    )

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="service_calls")

    __table_args__ = (
        # Composite index for waiter pending service calls query (branch_id + status)
        Index("ix_service_call_branch_status", "branch_id", "status"),
    )
