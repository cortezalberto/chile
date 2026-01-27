"""
Audit Log Model.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import AuditMixin, Base


class AuditLog(AuditMixin, Base):
    """
    Records all significant changes to entities for audit trail.
    Stores who did what, when, and the before/after state.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )

    # Who made the change
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("app_user.id"), index=True
    )
    user_email: Mapped[Optional[str]] = mapped_column(Text)

    # What was changed
    entity_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)  # CREATE, UPDATE, DELETE, SOFT_DELETE, RESTORE

    # Change details (JSON)
    old_values: Mapped[Optional[str]] = mapped_column(Text)  # JSON of previous state
    new_values: Mapped[Optional[str]] = mapped_column(Text)  # JSON of new state
    changes: Mapped[Optional[str]] = mapped_column(Text)  # JSON of changed fields

    # Metadata
    ip_address: Mapped[Optional[str]] = mapped_column(Text)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    # MDL-MED-18 FIX: Composite indexes for common audit queries
    __table_args__ = (
        Index("ix_audit_log_tenant_entity_type", "tenant_id", "entity_type"),
        Index("ix_audit_log_tenant_entity_id", "tenant_id", "entity_id"),
    )
