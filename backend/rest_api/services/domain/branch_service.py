"""
Branch Service - Clean Architecture Implementation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from rest_api.models import Branch
from shared.utils.admin_schemas import BranchOutput
from rest_api.services.base_service import BaseCRUDService
from rest_api.services.events import publish_entity_deleted


class BranchService(BaseCRUDService[Branch, BranchOutput]):
    """Service for branch management."""

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Branch,
            output_schema=BranchOutput,
            entity_name="Sucursal",
            has_branch_id=False,  # Branches don't have branch_id
        )

    def get_by_slug(self, tenant_id: int, slug: str) -> BranchOutput | None:
        """Get branch by slug."""
        entities = self._repo.find_all(tenant_id)
        for entity in entities:
            if entity.slug == slug:
                return self.to_output(entity)
        return None

    def _after_delete(
        self,
        entity_info: dict[str, Any],
        user_id: int,
        user_email: str,
    ) -> None:
        """Publish deletion event."""
        publish_entity_deleted(
            tenant_id=entity_info["tenant_id"],
            entity_type="branch",
            entity_id=entity_info["id"],
            entity_name=entity_info.get("name"),
            branch_id=entity_info["id"],  # Branch is its own branch
            actor_user_id=user_id,
        )
