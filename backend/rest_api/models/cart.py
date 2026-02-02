"""
Cart Models: CartItem for real-time shared cart synchronization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .table import TableSession
    from .customer import Diner
    from .catalog import Product


class CartItem(AuditMixin, Base):
    """
    An item in the shared cart for a table session.

    Cart items are synchronized in real-time across all diners at a table
    via WebSocket events (CART_ITEM_ADDED, CART_ITEM_UPDATED, CART_ITEM_REMOVED).

    When the round is submitted, cart items are converted to RoundItems
    and the cart is cleared.

    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "cart_item"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )
    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("table_session.id"), nullable=False, index=True
    )
    diner_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("diner.id"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("product.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="cart_items")
    diner: Mapped["Diner"] = relationship(back_populates="cart_items")
    product: Mapped["Product"] = relationship()

    __table_args__ = (
        # One item per product per diner per session (UPSERT on conflict)
        UniqueConstraint(
            "session_id", "diner_id", "product_id",
            name="uq_cart_item_session_diner_product"
        ),
        # Index for session queries (get all cart items for a session)
        Index("ix_cart_item_session", "session_id"),
        # Index for diner queries (get cart items for a specific diner)
        Index("ix_cart_item_session_diner", "session_id", "diner_id"),
        # Quantity must be between 1 and 99
        CheckConstraint("quantity > 0 AND quantity <= 99", name="ck_cart_item_quantity"),
    )

    def __repr__(self) -> str:
        return f"<CartItem(id={self.id}, session_id={self.session_id}, product_id={self.product_id}, qty={self.quantity})>"
