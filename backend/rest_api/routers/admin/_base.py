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

from rest_api.db import get_db
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
from rest_api.routers.admin_base import get_user_id, get_user_email


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
