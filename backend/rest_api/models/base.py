"""
Base class and AuditMixin for all SQLAlchemy ORM models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class AuditMixin:
    """
    Mixin providing soft delete and audit trail fields for all models.

    Fields added:
    - is_active: Soft delete flag (False = deleted, True = active)
    - created_at, updated_at, deleted_at: Audit timestamps
    - created_by_id/email, updated_by_id/email, deleted_by_id/email: User tracking

    Methods:
    - soft_delete(user_id, user_email): Mark entity as deleted
    - restore(user_id, user_email): Restore a soft-deleted entity
    """

    # Soft delete flag (False = deleted/inactive, True = active)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # User tracking - store ID and email for denormalization
    # Note: Cannot use FK to app_user here as it would create circular dependency
    created_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    updated_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    updated_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    deleted_by_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    deleted_by_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    def soft_delete(self, user_id: int | None, user_email: str | None) -> None:
        """
        Perform soft delete with audit trail.
        SVC-CRIT-01 FIX: Uses timezone-aware datetime.now(timezone.utc) instead of naive utcnow().
        MDL-MED-03 FIX: Parameter types now match field types (Optional).
        """
        from datetime import timezone as tz
        self.is_active = False
        self.deleted_at = datetime.now(tz.utc)
        self.deleted_by_id = user_id
        self.deleted_by_email = user_email

    def restore(self, user_id: int, user_email: str) -> None:
        """
        Restore a soft-deleted record.
        SVC-CRIT-01 FIX: Uses timezone-aware datetime.now(timezone.utc) instead of naive utcnow().
        """
        from datetime import timezone as tz
        self.is_active = True
        self.deleted_at = None
        self.deleted_by_id = None
        self.deleted_by_email = None
        self.updated_at = datetime.now(tz.utc)
        self.updated_by_id = user_id
        self.updated_by_email = user_email

    def set_created_by(self, user_id: int, user_email: str) -> None:
        """Set created_by fields on new entity."""
        self.created_by_id = user_id
        self.created_by_email = user_email

    def set_updated_by(self, user_id: int, user_email: str) -> None:
        """
        Set updated_by fields on entity update.
        SVC-CRIT-01 FIX: Uses timezone-aware datetime.now(timezone.utc) instead of naive utcnow().
        """
        from datetime import timezone as tz
        self.updated_by_id = user_id
        self.updated_by_email = user_email
        self.updated_at = datetime.now(tz.utc)

    def __repr__(self) -> str:
        """DB-LOW-01 FIX: Add __repr__ for better debugging."""
        class_name = self.__class__.__name__
        id_val = getattr(self, 'id', None)
        active = 'active' if self.is_active else 'deleted'
        return f"<{class_name}(id={id_val}, {active})>"
