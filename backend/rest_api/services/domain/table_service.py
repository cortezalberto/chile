"""
Table Service - Clean Architecture Implementation.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from rest_api.models import Table, BranchSector
from shared.utils.admin_schemas import TableOutput
from rest_api.services.base_service import BranchScopedService
from rest_api.services.events import publish_entity_deleted
from shared.utils.exceptions import ValidationError


class TableService(BranchScopedService[Table, TableOutput]):
    """Service for table management."""

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Table,
            output_schema=TableOutput,
            entity_name="Mesa",
            image_url_fields=set(),  # Tables don't have images
        )

    def list_by_sector(
        self,
        tenant_id: int,
        sector_id: int,
        *,
        include_inactive: bool = False,
    ) -> list[TableOutput]:
        """List tables for a specific sector."""
        entities = self._repo.find_all(
            tenant_id=tenant_id,
            include_inactive=include_inactive,
            order_by=Table.code,
        )
        filtered = [e for e in entities if e.sector_id == sector_id]
        return [self.to_output(e) for e in filtered]

    def get_by_code(
        self,
        tenant_id: int,
        branch_id: int,
        code: str,
    ) -> TableOutput | None:
        """Get table by code within branch."""
        from rest_api.services.crud.repository import BranchRepository

        repo: BranchRepository = self._repo
        entities = repo.find_by_branch(branch_id, tenant_id)
        for entity in entities:
            if entity.code == code:
                return self.to_output(entity)
        return None

    def _validate_create(self, data: dict[str, Any], tenant_id: int) -> None:
        """Validate table creation."""
        sector_id = data.get("sector_id")
        if not sector_id:
            raise ValidationError("sector_id es requerido", field="sector_id")

        sector = self._db.scalar(
            select(BranchSector).where(
                BranchSector.id == sector_id,
                BranchSector.tenant_id == tenant_id,
                BranchSector.is_active.is_(True),
            )
        )
        if not sector:
            raise ValidationError("sector_id inválido", field="sector_id")

        # Copy branch_id from sector
        data["branch_id"] = sector.branch_id

    def _after_delete(
        self,
        entity_info: dict[str, Any],
        user_id: int,
        user_email: str,
    ) -> None:
        """Publish deletion event."""
        publish_entity_deleted(
            tenant_id=entity_info["tenant_id"],
            entity_type="table",
            entity_id=entity_info["id"],
            entity_name=entity_info.get("name"),
            branch_id=entity_info.get("branch_id"),
            actor_user_id=user_id,
        )
