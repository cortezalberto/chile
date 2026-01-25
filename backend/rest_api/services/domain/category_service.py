"""
Category Service - Clean Architecture Implementation.

CLEAN-ARCH: Handles all category-related business logic.
Uses Repository for data access, not direct queries.

Usage:
    from rest_api.services.domain import CategoryService

    service = CategoryService(db)
    categories = service.list_by_branch(tenant_id, branch_id)
    category = service.create(data, tenant_id, user_id, user_email)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from rest_api.models import Category, Branch
from shared.utils.admin_schemas import CategoryOutput
from rest_api.services.base_service import BranchScopedService
from rest_api.services.events import publish_entity_deleted
from shared.utils.exceptions import ValidationError


class CategoryService(BranchScopedService[Category, CategoryOutput]):
    """
    Service for category management.

    Business rules:
    - Categories belong to a branch
    - Order is auto-calculated if not provided
    - Soft delete preserves audit trail
    - Deletion publishes domain event
    """

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Category,
            output_schema=CategoryOutput,
            entity_name="Categoría",
        )

    # =========================================================================
    # Query Methods
    # =========================================================================

    def list_by_branch_ordered(
        self,
        tenant_id: int,
        branch_id: int,
        *,
        include_inactive: bool = False,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[CategoryOutput]:
        """List categories for branch, ordered by display order."""
        return self.list_by_branch(
            tenant_id=tenant_id,
            branch_id=branch_id,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
            order_by=Category.order,
        )

    def get_next_order(self, branch_id: int) -> int:
        """Get the next available order number for a branch."""
        max_order = self._db.scalar(
            select(func.max(Category.order))
            .where(Category.branch_id == branch_id)
        )
        return (max_order or 0) + 1

    # =========================================================================
    # Command Methods
    # =========================================================================

    def create_with_auto_order(
        self,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> CategoryOutput:
        """
        Create category with auto-calculated order if not provided.

        Args:
            data: Category data including branch_id.
            tenant_id: Tenant ID.
            user_id: Creating user ID.
            user_email: Creating user email.

        Returns:
            Created category DTO.
        """
        # Auto-calculate order if not provided
        if data.get("order") is None:
            data["order"] = self.get_next_order(data["branch_id"])

        return self.create(data, tenant_id, user_id, user_email)

    # =========================================================================
    # Validation Hooks
    # =========================================================================

    def _validate_create(self, data: dict[str, Any], tenant_id: int) -> None:
        """Validate category creation data."""
        branch_id = data.get("branch_id")
        if not branch_id:
            raise ValidationError("branch_id es requerido", field="branch_id")

        # Verify branch belongs to tenant
        branch = self._db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.tenant_id == tenant_id,
            )
        )
        if not branch:
            raise ValidationError("branch_id inválido", field="branch_id")

    def _validate_delete(self, entity: Category, tenant_id: int) -> None:
        """Validate category can be deleted."""
        # Check if category has active subcategories
        from rest_api.models import Subcategory

        active_subcategories = self._db.scalar(
            select(func.count())
            .select_from(Subcategory)
            .where(
                Subcategory.category_id == entity.id,
                Subcategory.is_active.is_(True),
            )
        )

        if active_subcategories and active_subcategories > 0:
            raise ValidationError(
                f"La categoría tiene {active_subcategories} subcategorías activas. "
                "Elimine las subcategorías primero.",
                field="id",
            )

    # =========================================================================
    # Lifecycle Hooks
    # =========================================================================

    def _after_delete(
        self,
        entity_info: dict[str, Any],
        user_id: int,
        user_email: str,
    ) -> None:
        """Publish deletion event."""
        publish_entity_deleted(
            tenant_id=entity_info["tenant_id"],
            entity_type="category",
            entity_id=entity_info["id"],
            entity_name=entity_info.get("name"),
            branch_id=entity_info.get("branch_id"),
            actor_user_id=user_id,
        )
