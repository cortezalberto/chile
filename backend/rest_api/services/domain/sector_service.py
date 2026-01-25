"""
Sector Service - Clean Architecture Implementation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rest_api.models import BranchSector, Branch
from shared.utils.admin_schemas import BranchSectorOutput as SectorOutput
from rest_api.services.base_service import BranchScopedService
from rest_api.services.events import publish_entity_deleted
from shared.utils.exceptions import ValidationError


class SectorService(BranchScopedService[BranchSector, SectorOutput]):
    """Service for sector management."""

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=BranchSector,
            output_schema=SectorOutput,
            entity_name="Sector",
            image_url_fields=set(),  # Sectors don't have images
        )

    def list_by_branch_ordered(
        self,
        tenant_id: int,
        branch_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[SectorOutput]:
        """List sectors for branch, ordered by name."""
        return self.list_by_branch(
            tenant_id=tenant_id,
            branch_id=branch_id,
            include_inactive=include_inactive,
            order_by=BranchSector.name,
        )

    def _validate_create(self, data: dict[str, Any], tenant_id: int) -> None:
        """Validate sector creation."""
        branch_id = data.get("branch_id")
        if not branch_id:
            raise ValidationError("branch_id es requerido", field="branch_id")

        branch = self._db.scalar(
            select(Branch).where(
                Branch.id == branch_id,
                Branch.tenant_id == tenant_id,
            )
        )
        if not branch:
            raise ValidationError("branch_id inválido", field="branch_id")

    def _after_delete(
        self,
        entity_info: dict[str, Any],
        user_id: int,
        user_email: str,
    ) -> None:
        """Publish deletion event."""
        publish_entity_deleted(
            tenant_id=entity_info["tenant_id"],
            entity_type="sector",
            entity_id=entity_info["id"],
            entity_name=entity_info.get("name"),
            branch_id=entity_info.get("branch_id"),
            actor_user_id=user_id,
        )
