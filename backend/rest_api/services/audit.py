"""
Audit logging service.
Records all significant entity changes for compliance and debugging.
"""

import json
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session
from rest_api.models import AuditLog


def log_change(
    db: Session,
    *,
    tenant_id: int,
    user_id: Optional[int],
    user_email: Optional[str],
    entity_type: str,
    entity_id: int,
    action: str,
    old_values: Optional[dict] = None,
    new_values: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    """
    Log a change to an entity.

    Args:
        db: Database session
        tenant_id: Tenant ID
        user_id: User who made the change
        user_email: Email of user who made the change
        entity_type: Type of entity (e.g., "product", "category")
        entity_id: ID of the entity
        action: Action performed (CREATE, UPDATE, DELETE)
        old_values: Previous state of the entity (for UPDATE/DELETE)
        new_values: New state of the entity (for CREATE/UPDATE)
        ip_address: Client IP address
        user_agent: Client user agent

    Returns:
        Created AuditLog entry
    """
    # Calculate changes for UPDATE
    changes = None
    if action == "UPDATE" and old_values and new_values:
        changes = {}
        for key in set(old_values.keys()) | set(new_values.keys()):
            old_val = old_values.get(key)
            new_val = new_values.get(key)
            if old_val != new_val:
                changes[key] = {"old": old_val, "new": new_val}

    audit_entry = AuditLog(
        tenant_id=tenant_id,
        user_id=user_id,
        user_email=user_email,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_values=json.dumps(old_values) if old_values else None,
        new_values=json.dumps(new_values) if new_values else None,
        changes=json.dumps(changes) if changes else None,
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(audit_entry)
    # Don't commit here - let the caller handle the transaction
    return audit_entry


def serialize_model(obj: Any, exclude: list[str] = None) -> dict:
    """
    Serialize a SQLAlchemy model to a dictionary for audit logging.

    Args:
        obj: SQLAlchemy model instance
        exclude: Fields to exclude from serialization

    Returns:
        Dictionary representation of the model
    """
    if exclude is None:
        exclude = []

    result = {}
    for column in obj.__table__.columns:
        if column.name in exclude:
            continue
        value = getattr(obj, column.name)
        # Convert datetime to ISO string
        if isinstance(value, datetime):
            value = value.isoformat()
        result[column.name] = value

    return result


# Convenience functions for common operations


def log_create(
    db: Session,
    tenant_id: int,
    user_ctx: dict,
    entity_type: str,
    entity: Any,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Log entity creation."""
    return log_change(
        db,
        tenant_id=tenant_id,
        user_id=int(user_ctx.get("sub")) if user_ctx.get("sub") else None,
        user_email=user_ctx.get("email"),
        entity_type=entity_type,
        entity_id=entity.id,
        action="CREATE",
        new_values=serialize_model(entity),
        ip_address=ip_address,
    )


def log_update(
    db: Session,
    tenant_id: int,
    user_ctx: dict,
    entity_type: str,
    entity: Any,
    old_values: dict,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Log entity update."""
    return log_change(
        db,
        tenant_id=tenant_id,
        user_id=int(user_ctx.get("sub")) if user_ctx.get("sub") else None,
        user_email=user_ctx.get("email"),
        entity_type=entity_type,
        entity_id=entity.id,
        action="UPDATE",
        old_values=old_values,
        new_values=serialize_model(entity),
        ip_address=ip_address,
    )


def log_delete(
    db: Session,
    tenant_id: int,
    user_ctx: dict,
    entity_type: str,
    entity: Any,
    ip_address: Optional[str] = None,
) -> AuditLog:
    """Log entity deletion."""
    return log_change(
        db,
        tenant_id=tenant_id,
        user_id=int(user_ctx.get("sub")) if user_ctx.get("sub") else None,
        user_email=user_ctx.get("email"),
        entity_type=entity_type,
        entity_id=entity.id,
        action="DELETE",
        old_values=serialize_model(entity),
        ip_address=ip_address,
    )
