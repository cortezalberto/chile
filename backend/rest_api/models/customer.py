"""
Customer and Diner Models.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .table import TableSession
    from .order import RoundItem
    from .billing import Charge


class Customer(AuditMixin, Base):
    """
    FASE 4: Identified customer with explicit opt-in consent.

    Enables cross-session tracking with user consent for:
    - Personalized greetings and recommendations
    - Persistent preferences (allergens, dietary, cooking methods)
    - Loyalty metrics (RFM analysis)
    - Optional communication (email, WhatsApp)

    Privacy: All identification fields are optional. Customer can exist
    with only device_ids linked (anonymous but trackable).
    """

    __tablename__ = "customer"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )

    # === Optional Identification ===
    name: Mapped[Optional[str]] = mapped_column(Text)  # Display name
    phone: Mapped[Optional[str]] = mapped_column(Text)  # For WhatsApp
    email: Mapped[Optional[str]] = mapped_column(Text)  # For email communications

    # === Visit Metrics (auto-updated) ===
    first_visit_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_visit_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    total_visits: Mapped[int] = mapped_column(Integer, default=1)
    total_spent_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    avg_ticket_cents: Mapped[int] = mapped_column(Integer, default=0)

    # === Persistent Preferences (JSON arrays) ===
    # Format: [1, 3, 7] - allergen IDs to exclude
    excluded_allergen_ids: Mapped[Optional[str]] = mapped_column(Text)
    # Format: ["vegan", "gluten_free"] - dietary preferences
    dietary_preferences: Mapped[Optional[str]] = mapped_column(Text)
    # Format: ["frito", "horneado"] - cooking methods to exclude
    excluded_cooking_methods: Mapped[Optional[str]] = mapped_column(Text)
    # Format: [123, 456, 789] - top 5 product IDs by order frequency
    favorite_product_ids: Mapped[Optional[str]] = mapped_column(Text)

    # === AI Segmentation ===
    # Segment: "new", "occasional", "regular", "vip", "at_risk", "churned"
    # MDL-LOW-22 FIX: Added index for segment-based queries
    segment: Mapped[Optional[str]] = mapped_column(Text, default="new", index=True)
    # Churn risk score: 0.0 (loyal) to 1.0 (high risk)
    churn_risk_score: Mapped[Optional[float]] = mapped_column(Float)
    # Predicted next visit (AI-calculated)
    predicted_next_visit: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # === GDPR Consent ===
    consent_remember: Mapped[bool] = mapped_column(Boolean, default=True)  # Remember preferences
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)  # Allow marketing
    consent_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # QA-CRIT-01 FIX: AI personalization opt-in
    ai_personalization_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # QA-CRIT-01 FIX: Birthday for personalized greetings
    birthday_month: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    birthday_day: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # === Device Linkage (JSON array of device_ids) ===
    # Format: ["uuid-1", "uuid-2"] - allows multiple devices per customer
    device_ids: Mapped[Optional[str]] = mapped_column(Text)

    # === Relationships ===
    visits: Mapped[list["Diner"]] = relationship(back_populates="customer")

    __table_args__ = (
        # Unique phone per tenant (if provided)
        Index(
            "uq_customer_tenant_phone",
            "tenant_id", "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
        # Unique email per tenant (if provided)
        Index(
            "uq_customer_tenant_email",
            "tenant_id", "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )


class Diner(AuditMixin, Base):
    """
    A person dining at a table session.
    Tracks who is at the table for order attribution and payment allocation.
    Phase 2 improvement: Persistent diner entities instead of anonymous strings.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "diner"

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
    name: Mapped[str] = mapped_column(Text, nullable=False)  # Diner's display name
    color: Mapped[str] = mapped_column(Text, nullable=False)  # Hex color for UI (#RRGGBB)
    # HIGH-03 FIX: Add index for idempotency lookups
    local_id: Mapped[Optional[str]] = mapped_column(Text, index=True)  # Frontend UUID for syncing
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # FASE 1: Device tracking for cross-session recognition
    device_id: Mapped[Optional[str]] = mapped_column(Text, index=True)  # Persistent device UUID
    # MDL-MED-02 FIX: Added index for device_fingerprint for lookup queries
    device_fingerprint: Mapped[Optional[str]] = mapped_column(Text, index=True)  # Browser fingerprint hash

    # FASE 2: Implicit preferences (JSON)
    # Format: {"excluded_allergen_ids": [1,3], "dietary": ["vegan"], "excluded_cooking": ["frito"]}
    implicit_preferences: Mapped[Optional[str]] = mapped_column(Text)

    # FASE 4: Link to Customer when identified (optional)
    customer_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("customer.id"), index=True
    )

    # Relationships
    session: Mapped["TableSession"] = relationship(back_populates="diners")
    round_items: Mapped[list["RoundItem"]] = relationship(back_populates="diner")
    charges: Mapped[list["Charge"]] = relationship(back_populates="diner")
    customer: Mapped[Optional["Customer"]] = relationship(back_populates="visits")

    __table_args__ = (
        # HIGH-03 FIX: Composite index for idempotency check (session_id + local_id)
        Index("ix_diner_session_local_id", "session_id", "local_id"),
        # MED-CONS-03: Unique constraint for idempotency (prevents duplicate diners)
        UniqueConstraint("session_id", "local_id", name="uq_diner_session_local_id"),
        # MDL-HIGH-08 FIX: Composite indexes for customer recognition queries
        Index("ix_diner_session_customer", "session_id", "customer_id"),
        Index("ix_diner_customer_device", "customer_id", "device_id"),
    )
