"""
Allergen management endpoints with cross-reaction support.
"""

from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    selectinload, joinedload,
    get_db, current_user, Allergen, AllergenCrossReaction,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin, require_admin_or_manager,
)
from shared.utils.admin_schemas import (
    AllergenOutput, AllergenCreate, AllergenUpdate,
    CrossReactionInfo, CrossReactionOutput, CrossReactionCreate, CrossReactionUpdate,
)


router = APIRouter(tags=["admin-allergens"])



def _build_allergen_output(allergen: Allergen) -> AllergenOutput:
    """
    Build AllergenOutput from allergen model.
    Optimized to use pre-loaded relationships (avoiding N+1).
    """
    cross_reaction_infos = []
    
    # Access relationship safely
    # If relationship is not loaded, this might trigger a query (lazy load), 
    # but we will ensure endpoints use eager loading.
    if hasattr(allergen, "cross_reactions_from"):
        for cr in allergen.cross_reactions_from:
            # Filter active cross reactions
            if cr.is_active:
                # Access related allergen safely
                cross_name = "Unknown"
                if hasattr(cr, "cross_reacts_with") and cr.cross_reacts_with:
                    cross_name = cr.cross_reacts_with.name
                
                cross_reaction_infos.append(
                    CrossReactionInfo(
                        id=cr.id,
                        cross_reacts_with_id=cr.cross_reacts_with_id,
                        cross_reacts_with_name=cross_name,
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

@router.get("/allergens", response_model=list[AllergenOutput])
def list_allergens(
    include_deleted: bool = False,
    mandatory_only: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[AllergenOutput]:
    """List all allergens for the tenant with cross-reactions."""
    query = (
        select(Allergen)
        .options(
            selectinload(Allergen.cross_reactions_from)
            .joinedload(AllergenCrossReaction.cross_reacts_with)
        )
        .where(Allergen.tenant_id == user["tenant_id"])
    )

    if not include_deleted:
        query = query.where(Allergen.is_active.is_(True))

    if mandatory_only:
        query = query.where(Allergen.is_mandatory.is_(True))

    allergens = db.execute(query.order_by(Allergen.name)).scalars().unique().all()
    return [_build_allergen_output(a) for a in allergens]


@router.get("/allergens/{allergen_id}", response_model=AllergenOutput)
def get_allergen(
    allergen_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> AllergenOutput:
    """Get a single allergen by ID with cross-reactions."""
    allergen = db.scalar(
        select(Allergen)
        .options(
            selectinload(Allergen.cross_reactions_from)
            .joinedload(AllergenCrossReaction.cross_reacts_with)
        )
        .where(
            Allergen.id == allergen_id,
            Allergen.tenant_id == user["tenant_id"],
            Allergen.is_active.is_(True),
        )
    )
    if not allergen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergen not found",
        )
    return _build_allergen_output(allergen)


@router.post("/allergens", response_model=AllergenOutput, status_code=status.HTTP_201_CREATED)
def create_allergen(
    body: AllergenCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),  # RTR-CRIT-03 FIX: Require ADMIN or MANAGER
) -> AllergenOutput:
    """Create a new allergen. Requires ADMIN or MANAGER role."""
    allergen = Allergen(
        tenant_id=user["tenant_id"],
        **body.model_dump(),
    )
    set_created_by(allergen, get_user_id(user), get_user_email(user))
    db.add(allergen)
    db.commit()
    # Refresh with eager loading
    allergen = db.scalar(
        select(Allergen)
        .options(
            selectinload(Allergen.cross_reactions_from)
            .joinedload(AllergenCrossReaction.cross_reacts_with)
        )
        .where(Allergen.id == allergen.id)
    )
    return _build_allergen_output(allergen)


@router.patch("/allergens/{allergen_id}", response_model=AllergenOutput)
def update_allergen(
    allergen_id: int,
    body: AllergenUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),  # RTR-CRIT-03 FIX: Require ADMIN or MANAGER
) -> AllergenOutput:
    """Update an allergen. Requires ADMIN or MANAGER role."""
    allergen = db.scalar(
        select(Allergen).where(
            Allergen.id == allergen_id,
            Allergen.tenant_id == user["tenant_id"],
            Allergen.is_active.is_(True),
        )
    )
    if not allergen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergen not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(allergen, key, value)

    set_updated_by(allergen, get_user_id(user), get_user_email(user))

    db.commit()
    # Refresh with eager loading
    allergen = db.scalar(
        select(Allergen)
        .options(
            selectinload(Allergen.cross_reactions_from)
            .joinedload(AllergenCrossReaction.cross_reacts_with)
        )
        .where(Allergen.id == allergen.id)
    )
    return _build_allergen_output(allergen)


@router.delete("/allergens/{allergen_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_allergen(
    allergen_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete an allergen. Requires ADMIN role."""
    allergen = db.scalar(
        select(Allergen).where(
            Allergen.id == allergen_id,
            Allergen.tenant_id == user["tenant_id"],
            Allergen.is_active.is_(True),
        )
    )
    if not allergen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Allergen not found",
        )

    allergen_name = allergen.name
    tenant_id = allergen.tenant_id

    soft_delete(db, allergen, get_user_id(user), get_user_email(user))

    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="allergen",
        entity_id=allergen_id,
        entity_name=allergen_name,
        actor_user_id=get_user_id(user),
    )


# =============================================================================
# Cross-Reaction Endpoints
# =============================================================================


@router.get("/allergens/cross-reactions", response_model=list[CrossReactionOutput])
def list_cross_reactions(
    allergen_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[CrossReactionOutput]:
    """List all cross-reactions for the tenant."""
    query = (
        select(AllergenCrossReaction, Allergen)
        .join(Allergen, AllergenCrossReaction.cross_reacts_with_id == Allergen.id)
        .where(AllergenCrossReaction.tenant_id == user["tenant_id"])
    )

    if not include_deleted:
        query = query.where(AllergenCrossReaction.is_active.is_(True))

    if allergen_id:
        query = query.where(AllergenCrossReaction.allergen_id == allergen_id)

    results = db.execute(query.order_by(AllergenCrossReaction.allergen_id)).all()

    allergen_names = {}
    allergen_ids = {r.AllergenCrossReaction.allergen_id for r in results}
    if allergen_ids:
        allergens = db.execute(
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


@router.post("/allergens/cross-reactions", response_model=CrossReactionOutput, status_code=status.HTTP_201_CREATED)
def create_cross_reaction(
    body: CrossReactionCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),  # RTR-CRIT-03 FIX: Require ADMIN or MANAGER
) -> CrossReactionOutput:
    """Create a cross-reaction between two allergens. Requires ADMIN or MANAGER role."""
    tenant_id = user["tenant_id"]

    allergen = db.scalar(
        select(Allergen).where(
            Allergen.id == body.allergen_id,
            Allergen.tenant_id == tenant_id,
            Allergen.is_active.is_(True),
        )
    )
    if not allergen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Primary allergen not found",
        )

    cross_allergen = db.scalar(
        select(Allergen).where(
            Allergen.id == body.cross_reacts_with_id,
            Allergen.tenant_id == tenant_id,
            Allergen.is_active.is_(True),
        )
    )
    if not cross_allergen:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cross-reaction allergen not found",
        )

    existing = db.scalar(
        select(AllergenCrossReaction).where(
            AllergenCrossReaction.allergen_id == body.allergen_id,
            AllergenCrossReaction.cross_reacts_with_id == body.cross_reacts_with_id,
            AllergenCrossReaction.tenant_id == tenant_id,
        )
    )
    if existing:
        if existing.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cross-reaction already exists",
            )
        # Restore soft-deleted record
        existing.restore(get_user_id(user) or 0, get_user_email(user))
        existing.probability = body.probability
        existing.notes = body.notes
        db.commit()
        db.refresh(existing)
        return CrossReactionOutput(
            id=existing.id,
            tenant_id=existing.tenant_id,
            allergen_id=existing.allergen_id,
            allergen_name=allergen.name,
            cross_reacts_with_id=existing.cross_reacts_with_id,
            cross_reacts_with_name=cross_allergen.name,
            probability=existing.probability,
            notes=existing.notes,
            is_active=existing.is_active,
        )

    cross_reaction = AllergenCrossReaction(
        tenant_id=tenant_id,
        allergen_id=body.allergen_id,
        cross_reacts_with_id=body.cross_reacts_with_id,
        probability=body.probability,
        notes=body.notes,
    )
    set_created_by(cross_reaction, get_user_id(user), get_user_email(user))
    db.add(cross_reaction)
    db.commit()
    db.refresh(cross_reaction)

    return CrossReactionOutput(
        id=cross_reaction.id,
        tenant_id=cross_reaction.tenant_id,
        allergen_id=cross_reaction.allergen_id,
        allergen_name=allergen.name,
        cross_reacts_with_id=cross_reaction.cross_reacts_with_id,
        cross_reacts_with_name=cross_allergen.name,
        probability=cross_reaction.probability,
        notes=cross_reaction.notes,
        is_active=cross_reaction.is_active,
    )


@router.patch("/allergens/cross-reactions/{cross_reaction_id}", response_model=CrossReactionOutput)
def update_cross_reaction(
    cross_reaction_id: int,
    body: CrossReactionUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),  # RTR-CRIT-03 FIX: Require ADMIN or MANAGER
) -> CrossReactionOutput:
    """Update a cross-reaction's probability or notes. Requires ADMIN or MANAGER role."""
    cross_reaction = db.scalar(
        select(AllergenCrossReaction).where(
            AllergenCrossReaction.id == cross_reaction_id,
            AllergenCrossReaction.tenant_id == user["tenant_id"],
            AllergenCrossReaction.is_active.is_(True),
        )
    )
    if not cross_reaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cross-reaction not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(cross_reaction, key, value)

    set_updated_by(cross_reaction, get_user_id(user), get_user_email(user))
    db.commit()
    db.refresh(cross_reaction)

    allergen = db.scalar(select(Allergen).where(Allergen.id == cross_reaction.allergen_id))
    cross_allergen = db.scalar(select(Allergen).where(Allergen.id == cross_reaction.cross_reacts_with_id))

    return CrossReactionOutput(
        id=cross_reaction.id,
        tenant_id=cross_reaction.tenant_id,
        allergen_id=cross_reaction.allergen_id,
        allergen_name=allergen.name if allergen else "",
        cross_reacts_with_id=cross_reaction.cross_reacts_with_id,
        cross_reacts_with_name=cross_allergen.name if cross_allergen else "",
        probability=cross_reaction.probability,
        notes=cross_reaction.notes,
        is_active=cross_reaction.is_active,
    )


@router.delete("/allergens/cross-reactions/{cross_reaction_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_cross_reaction(
    cross_reaction_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete a cross-reaction. Requires ADMIN role."""
    cross_reaction = db.scalar(
        select(AllergenCrossReaction).where(
            AllergenCrossReaction.id == cross_reaction_id,
            AllergenCrossReaction.tenant_id == user["tenant_id"],
            AllergenCrossReaction.is_active.is_(True),
        )
    )
    if not cross_reaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cross-reaction not found",
        )

    soft_delete(db, cross_reaction, get_user_id(user), get_user_email(user))
