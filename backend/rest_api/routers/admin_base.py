"""
Base utilities and common imports for admin routers.
"""

# LOW-01 FIX: Removed unused Optional import
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
import re

from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select, func, or_

from rest_api.db import get_db
from shared.auth import current_user_context as current_user
from shared.password import hash_password
from rest_api.services.audit import log_create, log_update, log_delete, serialize_model
from rest_api.services.admin_events import publish_entity_deleted
from rest_api.services.soft_delete_service import (
    soft_delete,
    restore_entity,
    set_created_by,
    set_updated_by,
    get_model_class,
    find_active_entity,
    find_deleted_entity,
    filter_active,
)


def require_admin(user: dict) -> None:
    """Raise 403 if user is not ADMIN."""
    if "ADMIN" not in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )


def require_admin_or_manager(user: dict) -> None:
    """Raise 403 if user is neither ADMIN nor MANAGER."""
    roles = user.get("roles", [])
    if "ADMIN" not in roles and "MANAGER" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )


def get_user_id(user: dict) -> int:
    """Get user ID from context, handling string format."""
    sub = user.get("sub")
    if sub is None:
        return 0
    return int(sub) if isinstance(sub, str) else sub


def get_user_email(user: dict) -> str:
    """Get user email from context with default."""
    return user.get("email", "")
