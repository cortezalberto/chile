"""
Shared dependencies and helpers for admin routers.

This module provides common imports, dependencies, and utility functions
used across all admin sub-routers.
"""

from datetime import date, datetime, timezone
from typing import Optional, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select, func, or_

from shared.infrastructure.db import get_db
from rest_api.models import (
    Tenant,
    Branch,
    BranchSector,
    Category,
    Subcategory,
    Product,
    BranchProduct,
    Allergen,
    AllergenCrossReaction,
    ProductAllergen,
    Table,
    User,
    UserBranchRole,
    Round,
    RoundItem,
    TableSession,
    Diner,
    AuditLog,
    BranchCategoryExclusion,
    BranchSubcategoryExclusion,
    WaiterSectorAssignment,
    Payment,
    # Canonical Product Model (Phases 1-4)
    Ingredient,
    ProductIngredient,
    ProductDietaryProfile,
    CookingMethod,
    FlavorProfile,
    TextureProfile,
    ProductCookingMethod,
    ProductFlavor,
    ProductTexture,
    ProductCooking,
    ProductModification,
    ProductWarning,
    ProductRAGConfig,
)
from shared.security.auth import current_user_context as current_user
from shared.security.password import hash_password
from rest_api.services.crud.audit import log_create, log_update, log_delete, serialize_model
from rest_api.services.events.admin_events import publish_entity_deleted
from rest_api.services.crud.soft_delete import (
    soft_delete,
    restore_entity,
    set_created_by,
    set_updated_by,
    get_model_class,
    find_active_entity,
    find_deleted_entity,
    filter_active,
)
from rest_api.routers._common.base import get_user_id, get_user_email


# =============================================================================
# Role-based Dependencies
# =============================================================================


def require_admin(user: dict = Depends(current_user)) -> dict:
    """Dependency that requires ADMIN role."""
    if "ADMIN" not in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )
    return user


def require_admin_or_manager(user: dict = Depends(current_user)) -> dict:
    """Dependency that requires ADMIN or MANAGER role."""
    roles = user.get("roles", [])
    if "ADMIN" not in roles and "MANAGER" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )
    return user


def require_any_staff(user: dict = Depends(current_user)) -> dict:
    """Dependency that requires any staff role (ADMIN, MANAGER, KITCHEN, WAITER)."""
    roles = user.get("roles", [])
    valid_roles = {"ADMIN", "MANAGER", "KITCHEN", "WAITER"}
    if not any(role in valid_roles for role in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff role required",
        )
    return user


# =============================================================================
# Common Utility Functions
# =============================================================================


def validate_branch_access(user: dict, branch_id: int) -> None:
    """Validate that user has access to the specified branch."""
    branch_ids = user.get("branch_ids", [])
    if branch_id not in branch_ids and "ADMIN" not in user.get("roles", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )


def get_accessible_branch_ids(user: dict, requested_branch_id: int | None = None) -> list[int]:
    """
    Get list of branch IDs the user can access.

    For ADMIN: Returns [requested_branch_id] if specified, else None (no filter needed).
    For MANAGER/other: Returns intersection of user's branches and requested branch.

    Args:
        user: User context from JWT
        requested_branch_id: Optional specific branch requested

    Returns:
        List of branch IDs to filter by. Empty list means no access.

    Raises:
        HTTPException 403 if user requests a branch they don't have access to.
    """
    if is_admin(user):
        # ADMIN has access to all branches - return requested or signal no filter
        return [requested_branch_id] if requested_branch_id else []

    user_branch_ids = user.get("branch_ids", [])

    if not user_branch_ids:
        # User has no branches assigned - return empty (no access)
        return []

    if requested_branch_id is not None:
        # Validate user has access to the requested branch
        if requested_branch_id not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this branch",
            )
        return [requested_branch_id]

    # No specific branch requested - return all user's branches
    return list(user_branch_ids)


def filter_by_accessible_branches(user: dict, requested_branch_id: int | None = None) -> tuple[list[int] | None, bool]:
    """
    Get branch filter info for queries.

    Returns:
        Tuple of (branch_ids_to_filter, should_filter)
        - If should_filter is False, no branch filtering needed (ADMIN without specific request)
        - If should_filter is True, filter by branch_ids_to_filter
        - If branch_ids_to_filter is empty and should_filter is True, return no results
    """
    if is_admin(user):
        if requested_branch_id:
            return [requested_branch_id], True
        return None, False  # ADMIN sees all, no filter

    user_branch_ids = user.get("branch_ids", [])

    if not user_branch_ids:
        return [], True  # No access

    if requested_branch_id is not None:
        if requested_branch_id not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this branch",
            )
        return [requested_branch_id], True

    return list(user_branch_ids), True


def is_admin(user: dict) -> bool:
    """Check if user has ADMIN role."""
    return "ADMIN" in user.get("roles", [])


def is_manager(user: dict) -> bool:
    """Check if user has MANAGER role."""
    return "MANAGER" in user.get("roles", [])


def is_admin_or_manager(user: dict) -> bool:
    """Check if user has ADMIN or MANAGER role."""
    roles = user.get("roles", [])
    return "ADMIN" in roles or "MANAGER" in roles


# =============================================================================
# Re-exports for convenience
# =============================================================================

__all__ = [
    # FastAPI
    "APIRouter",
    "Depends",
    "HTTPException",
    "status",
    # SQLAlchemy
    "Session",
    "select",
    "func",
    "or_",
    "selectinload",
    "joinedload",
    # Database
    "get_db",
    # Models
    "Tenant",
    "Branch",
    "BranchSector",
    "Category",
    "Subcategory",
    "Product",
    "BranchProduct",
    "Allergen",
    "AllergenCrossReaction",
    "ProductAllergen",
    "Table",
    "User",
    "UserBranchRole",
    "Round",
    "RoundItem",
    "TableSession",
    "Diner",
    "AuditLog",
    "BranchCategoryExclusion",
    "BranchSubcategoryExclusion",
    "WaiterSectorAssignment",
    "Payment",
    "Ingredient",
    "ProductIngredient",
    "ProductDietaryProfile",
    "CookingMethod",
    "FlavorProfile",
    "TextureProfile",
    "ProductCookingMethod",
    "ProductFlavor",
    "ProductTexture",
    "ProductCooking",
    "ProductModification",
    "ProductWarning",
    "ProductRAGConfig",
    # Auth
    "current_user",
    "hash_password",
    # Audit
    "log_create",
    "log_update",
    "log_delete",
    "serialize_model",
    # Events
    "publish_entity_deleted",
    # Soft delete
    "soft_delete",
    "restore_entity",
    "set_created_by",
    "set_updated_by",
    "get_model_class",
    "find_active_entity",
    "find_deleted_entity",
    "filter_active",
    # User helpers
    "get_user_id",
    "get_user_email",
    # Role dependencies
    "require_admin",
    "require_admin_or_manager",
    "require_any_staff",
    # Utility functions
    "validate_branch_access",
    "get_accessible_branch_ids",
    "filter_by_accessible_branches",
    "is_admin",
    "is_manager",
    "is_admin_or_manager",
    # Types
    "date",
    "datetime",
    "timezone",
    "Optional",
    "Any",
]
