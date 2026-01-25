"""
Subcategory Service - Clean Architecture Implementation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from rest_api.models import Subcategory, Category
from shared.utils.admin_schemas import SubcategoryOutput
from rest_api.services.base_service import BranchScopedService
from rest_api.services.events import publish_entity_deleted
from shared.utils.exceptions import ValidationError


class SubcategoryService(BranchScopedService[Subcategory, SubcategoryOutput]):
    """Service for subcategory management."""

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Subcategory,
            output_schema=SubcategoryOutput,
            entity_name="Subcategoría",
        )

    def list_by_category(
        self,
        tenant_id: int,
        category_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[SubcategoryOutput]:
        """List subcategories for a specific category."""
        entities = self._repo.find_all(
            tenant_id=tenant_id,
            include_inactive=include_inactive,
            order_by=Subcategory.order,
        )
        filtered = [e for e in entities if e.category_id == category_id]
        return [self.to_output(e) for e in filtered]

    def get_next_order(self, category_id: int) -> int:
        """Get next available order for category."""
        max_order = self._db.scalar(
            select(func.max(Subcategory.order))
            .where(Subcategory.category_id == category_id)
        )
        return (max_order or 0) + 1

    def _validate_create(self, data: dict[str, Any], tenant_id: int) -> None:
        """Validate subcategory creation."""
        category_id = data.get("category_id")
        if not category_id:
            raise ValidationError("category_id es requerido", field="category_id")

        category = self._db.scalar(
            select(Category).where(
                Category.id == category_id,
                Category.tenant_id == tenant_id,
                Category.is_active.is_(True),
            )
        )
        if not category:
            raise ValidationError("category_id inválido", field="category_id")

        # Copy branch_id from parent category
        data["branch_id"] = category.branch_id

    def _after_delete(
        self,
        entity_info: dict[str, Any],
        user_id: int,
        user_email: str,
    ) -> None:
        """Publish deletion event."""
        publish_entity_deleted(
            tenant_id=entity_info["tenant_id"],
            entity_type="subcategory",
            entity_id=entity_info["id"],
            entity_name=entity_info.get("name"),
            branch_id=entity_info.get("branch_id"),
            actor_user_id=user_id,
        )
