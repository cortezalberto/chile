"""
Allergen Service - Clean Architecture Implementation.

CLEAN-ARCH: Handles all allergen-related business logic including:
- Basic allergen CRUD
- Cross-reaction management

Usage:
    from rest_api.services.domain import AllergenService

    service = AllergenService(db)
    allergens = service.list_all(tenant_id)
    allergen = service.create(data, tenant_id, user_id, user_email)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, joinedload

from rest_api.models import Allergen, AllergenCrossReaction
from shared.utils.admin_schemas import (
    AllergenOutput, CrossReactionInfo, CrossReactionOutput,
)
from rest_api.services.base_service import BaseCRUDService
from rest_api.services.crud.soft_delete import soft_delete, set_created_by, set_updated_by
from rest_api.services.events import publish_entity_deleted
from shared.utils.exceptions import ValidationError, NotFoundError
from shared.config.logging import get_logger

logger = get_logger(__name__)


class AllergenService(BaseCRUDService[Allergen, AllergenOutput]):
    """
    Service for allergen management.

    Business rules:
    - Allergens belong to a tenant
    - Allergens can have cross-reactions with other allergens
    - Soft delete preserves audit trail
    """

    def __init__(self, db: Session):
        super().__init__(
            db=db,
            model=Allergen,
            output_schema=AllergenOutput,
            entity_name="Alérgeno",
            image_url_fields=set(),  # Allergens don't have image URLs
        )

    # =========================================================================
    # Query Methods
    # =========================================================================

    def list_with_cross_reactions(
        self,
        tenant_id: int,
        *,
        include_inactive: bool = False,
        mandatory_only: bool = False,
    ) -> list[AllergenOutput]:
        """List allergens with cross-reactions eagerly loaded."""
        query = (
            select(Allergen)
            .options(
                selectinload(Allergen.cross_reactions_from)
                .joinedload(AllergenCrossReaction.cross_reacts_with)
            )
            .where(Allergen.tenant_id == tenant_id)
        )

        if not include_inactive:
            query = query.where(Allergen.is_active.is_(True))

        if mandatory_only:
            query = query.where(Allergen.is_mandatory.is_(True))

        allergens = self._db.execute(query.order_by(Allergen.name)).scalars().unique().all()
        return [self._to_output_with_cross_reactions(a) for a in allergens]

    def get_with_cross_reactions(
        self,
        allergen_id: int,
        tenant_id: int,
    ) -> AllergenOutput:
        """Get single allergen with cross-reactions."""
        allergen = self._db.scalar(
            select(Allergen).where(
                Allergen.id == allergen_id,
                Allergen.tenant_id == tenant_id,
                Allergen.is_active.is_(True),
            )
        )

        if not allergen:
            raise NotFoundError(self._entity_name, allergen_id, tenant_id=tenant_id)

        return self._to_output_with_query(allergen)

    # =========================================================================
    # Cross-Reaction Management
    # =========================================================================

    def list_cross_reactions(
        self,
        tenant_id: int,
        *,
        allergen_id: int | None = None,
        include_inactive: bool = False,
    ) -> list[CrossReactionOutput]:
        """List all cross-reactions for the tenant."""
        query = (
            select(AllergenCrossReaction, Allergen)
            .join(Allergen, AllergenCrossReaction.cross_reacts_with_id == Allergen.id)
            .where(AllergenCrossReaction.tenant_id == tenant_id)
        )

        if not include_inactive:
            query = query.where(AllergenCrossReaction.is_active.is_(True))

        if allergen_id:
            query = query.where(AllergenCrossReaction.allergen_id == allergen_id)

        results = self._db.execute(query.order_by(AllergenCrossReaction.allergen_id)).all()

        # Batch load allergen names
        allergen_ids = {r.AllergenCrossReaction.allergen_id for r in results}
        allergen_names = {}
        if allergen_ids:
            allergens = self._db.execute(
                select(Allergen).where(Allergen.id.in_(allergen_ids))
            ).scalars().all()
            allergen_names = {a.id: a.name for a in allergens}

        return [
            CrossReactionOutput(
                id=r.AllergenCrossReaction.id,
                tenant_id=r.AllergenCrossReaction.tenant_id,
                allergen_id=r.AllergenCrossReaction.allergen_id,
                allergen_name=allergen_names.get(r.AllergenCrossReaction.allergen_id, ""),
                cross_reacts_with_id=r.AllergenCrossReaction.cross_reacts_with_id,
                cross_reacts_with_name=r.Allergen.name,
                probability=r.AllergenCrossReaction.probability,
                notes=r.AllergenCrossReaction.notes,
                is_active=r.AllergenCrossReaction.is_active,
            )
            for r in results
        ]

    def create_cross_reaction(
        self,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> CrossReactionOutput:
        """Create a cross-reaction between two allergens."""
        allergen_id = data["allergen_id"]
        cross_reacts_with_id = data["cross_reacts_with_id"]

        # Validate both allergens exist
        allergen = self._db.scalar(
            select(Allergen).where(
                Allergen.id == allergen_id,
                Allergen.tenant_id == tenant_id,
                Allergen.is_active.is_(True),
            )
        )
        if not allergen:
            raise ValidationError("Alérgeno primario no encontrado", field="allergen_id")

        cross_allergen = self._db.scalar(
            select(Allergen).where(
                Allergen.id == cross_reacts_with_id,
                Allergen.tenant_id == tenant_id,
                Allergen.is_active.is_(True),
            )
        )
        if not cross_allergen:
            raise ValidationError("Alérgeno de reacción cruzada no encontrado", field="cross_reacts_with_id")

        # Check if already exists
        existing = self._db.scalar(
            select(AllergenCrossReaction).where(
                AllergenCrossReaction.allergen_id == allergen_id,
                AllergenCrossReaction.cross_reacts_with_id == cross_reacts_with_id,
                AllergenCrossReaction.tenant_id == tenant_id,
            )
        )

        if existing:
            if existing.is_active:
                raise ValidationError("La reacción cruzada ya existe", field="cross_reacts_with_id")
            # Restore soft-deleted record
            existing.restore(user_id, user_email)
            existing.probability = data.get("probability", "medium")
            existing.notes = data.get("notes")
            self._db.commit()
            self._db.refresh(existing)
            return self._build_cross_reaction_output(existing, allergen, cross_allergen)

        # Create new
        cross_reaction = AllergenCrossReaction(
            tenant_id=tenant_id,
            allergen_id=allergen_id,
            cross_reacts_with_id=cross_reacts_with_id,
            probability=data.get("probability", "medium"),
            notes=data.get("notes"),
        )
        set_created_by(cross_reaction, user_id, user_email)
        self._db.add(cross_reaction)
        self._db.commit()
        self._db.refresh(cross_reaction)

        return self._build_cross_reaction_output(cross_reaction, allergen, cross_allergen)

    def update_cross_reaction(
        self,
        cross_reaction_id: int,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> CrossReactionOutput:
        """Update a cross-reaction."""
        cross_reaction = self._db.scalar(
            select(AllergenCrossReaction).where(
                AllergenCrossReaction.id == cross_reaction_id,
                AllergenCrossReaction.tenant_id == tenant_id,
                AllergenCrossReaction.is_active.is_(True),
            )
        )
        if not cross_reaction:
            raise NotFoundError("Reacción cruzada", cross_reaction_id, tenant_id=tenant_id)

        for key, value in data.items():
            if hasattr(cross_reaction, key):
                setattr(cross_reaction, key, value)

        set_updated_by(cross_reaction, user_id, user_email)
        self._db.commit()
        self._db.refresh(cross_reaction)

        allergen = self._db.scalar(select(Allergen).where(Allergen.id == cross_reaction.allergen_id))
        cross_allergen = self._db.scalar(select(Allergen).where(Allergen.id == cross_reaction.cross_reacts_with_id))

        return self._build_cross_reaction_output(cross_reaction, allergen, cross_allergen)

    def delete_cross_reaction(
        self,
        cross_reaction_id: int,
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """Soft delete a cross-reaction."""
        cross_reaction = self._db.scalar(
            select(AllergenCrossReaction).where(
                AllergenCrossReaction.id == cross_reaction_id,
                AllergenCrossReaction.tenant_id == tenant_id,
                AllergenCrossReaction.is_active.is_(True),
            )
        )
        if not cross_reaction:
            raise NotFoundError("Reacción cruzada", cross_reaction_id, tenant_id=tenant_id)

        soft_delete(self._db, cross_reaction, user_id, user_email)

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
            entity_type="allergen",
            entity_id=entity_info["id"],
            entity_name=entity_info.get("name"),
            actor_user_id=user_id,
        )

    # =========================================================================
    # Transformation
    # =========================================================================

    def _to_output_with_cross_reactions(self, allergen: Allergen) -> AllergenOutput:
        """Build output from pre-loaded relationships."""
        cross_reaction_infos = []
        for cr in allergen.cross_reactions_from:
            if cr.is_active and cr.cross_reacts_with and cr.cross_reacts_with.is_active:
                cross_reaction_infos.append(
                    CrossReactionInfo(
                        id=cr.id,
                        cross_reacts_with_id=cr.cross_reacts_with_id,
                        cross_reacts_with_name=cr.cross_reacts_with.name,
                        probability=cr.probability,
                        notes=cr.notes,
                    )
                )

        return AllergenOutput(
            id=allergen.id,
            tenant_id=allergen.tenant_id,
            name=allergen.name,
            icon=allergen.icon,
            description=allergen.description,
            is_mandatory=allergen.is_mandatory,
            severity=allergen.severity,
            is_active=allergen.is_active,
            cross_reactions=cross_reaction_infos if cross_reaction_infos else None,
        )

    def _to_output_with_query(self, allergen: Allergen) -> AllergenOutput:
        """Build output with separate query for cross-reactions."""
        cross_reactions = self._db.execute(
            select(AllergenCrossReaction, Allergen)
            .join(Allergen, AllergenCrossReaction.cross_reacts_with_id == Allergen.id)
            .where(
                AllergenCrossReaction.allergen_id == allergen.id,
                AllergenCrossReaction.is_active.is_(True),
                Allergen.is_active.is_(True),
            )
        ).all()

        cross_reaction_infos = [
            CrossReactionInfo(
                id=cr.AllergenCrossReaction.id,
                cross_reacts_with_id=cr.AllergenCrossReaction.cross_reacts_with_id,
                cross_reacts_with_name=cr.Allergen.name,
                probability=cr.AllergenCrossReaction.probability,
                notes=cr.AllergenCrossReaction.notes,
            )
            for cr in cross_reactions
        ]

        return AllergenOutput(
            id=allergen.id,
            tenant_id=allergen.tenant_id,
            name=allergen.name,
            icon=allergen.icon,
            description=allergen.description,
            is_mandatory=allergen.is_mandatory,
            severity=allergen.severity,
            is_active=allergen.is_active,
            cross_reactions=cross_reaction_infos if cross_reaction_infos else None,
        )

    @staticmethod
    def _build_cross_reaction_output(
        cr: AllergenCrossReaction,
        allergen: Allergen | None,
        cross_allergen: Allergen | None,
    ) -> CrossReactionOutput:
        """Build CrossReactionOutput."""
        return CrossReactionOutput(
            id=cr.id,
            tenant_id=cr.tenant_id,
            allergen_id=cr.allergen_id,
            allergen_name=allergen.name if allergen else "",
            cross_reacts_with_id=cr.cross_reacts_with_id,
            cross_reacts_with_name=cross_allergen.name if cross_allergen else "",
            probability=cr.probability,
            notes=cr.notes,
            is_active=cr.is_active,
        )
