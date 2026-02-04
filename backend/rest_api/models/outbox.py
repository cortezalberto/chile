"""
Outbox model for transactional event publishing.

OUTBOX-PATTERN: Implements the Transactional Outbox Pattern for guaranteed
event delivery. Events are written atomically with business data, then
processed asynchronously by a background worker.

This ensures events are never lost even if:
- Redis is temporarily unavailable
- The application crashes after DB commit
- Network issues prevent immediate publishing
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, DateTime, Enum as SQLEnum, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OutboxStatus(str, Enum):
    """Status of an outbox event."""
    PENDING = "PENDING"      # Ready to be processed
    PROCESSING = "PROCESSING"  # Currently being processed (prevents double processing)
    PUBLISHED = "PUBLISHED"  # Successfully published
    FAILED = "FAILED"        # Failed after max retries


class OutboxEvent(Base):
    """
    Outbox event for guaranteed delivery.

    Events are inserted in the same transaction as business data,
    ensuring atomicity. A background processor reads PENDING events
    and publishes them to Redis, then marks them as PUBLISHED.

    Critical events that use this pattern:
    - Billing: CHECK_REQUESTED, PAYMENT_APPROVED, PAYMENT_REJECTED, CHECK_PAID
    - Rounds: ROUND_SUBMITTED, ROUND_READY
    - Service calls: SERVICE_CALL_CREATED
    """
    __tablename__ = "outbox_event"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # Event metadata
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Target routing (for Redis pub/sub)
    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)  # e.g., "round", "check", "service_call"
    aggregate_id: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Event payload (JSON serialized)
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    # Processing status
    status: Mapped[OutboxStatus] = mapped_column(
        SQLEnum(OutboxStatus, name="outbox_status"),
        default=OutboxStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Composite index for efficient polling by the processor
    __table_args__ = (
        Index("ix_outbox_event_status_created", "status", "created_at"),
        Index("ix_outbox_event_tenant_status", "tenant_id", "status"),
    )

    def __repr__(self) -> str:
        return f"<OutboxEvent(id={self.id}, type={self.event_type}, status={self.status.value})>"
