"""
Audit log endpoints.
"""

from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    get_db, current_user, AuditLog,
)
from shared.utils.admin_schemas import AuditLogOutput


router = APIRouter(tags=["admin-audit"])


@router.get("/audit-log", response_model=list[AuditLogOutput])
def get_audit_log(
    entity_type: str | None = None,
    entity_id: int | None = None,
    action: str | None = None,
    user_id: int | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[AuditLogOutput]:
    """
    Get audit log entries with optional filters.

    Filters:
    - entity_type: Filter by entity type (e.g., "product", "category")
    - entity_id: Filter by specific entity ID
    - action: Filter by action (CREATE, UPDATE, DELETE)
    - user_id: Filter by user who made the change
    """
    # Require ADMIN or MANAGER role
    user_roles = set(user.get("roles", []))
    if not user_roles.intersection({"ADMIN", "MANAGER"}):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only ADMIN or MANAGER can view audit log",
        )

    query = select(AuditLog).where(AuditLog.tenant_id == user["tenant_id"])

    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type)
    if entity_id:
        query = query.where(AuditLog.entity_id == entity_id)
    if action:
        query = query.where(AuditLog.action == action)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)

    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)

    entries = db.execute(query).scalars().all()

    return [
        AuditLogOutput(
            id=entry.id,
            user_id=entry.user_id,
            user_email=entry.user_email,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            action=entry.action,
            old_values=entry.old_values,
            new_values=entry.new_values,
            changes=entry.changes,
            ip_address=entry.ip_address,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
