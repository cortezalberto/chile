"""
Sector management endpoints for organizing tables.
"""

import re
from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select, func, or_,
    get_db, current_user, BranchSector,
    soft_delete, set_created_by,
    get_user_id, get_user_email,
    require_admin, require_admin_or_manager,
    is_admin, validate_branch_access, filter_by_accessible_branches,
)
from shared.utils.admin_schemas import BranchSectorOutput, BranchSectorCreate


router = APIRouter(tags=["admin-sectors"])


def _sector_to_output(sector: BranchSector) -> BranchSectorOutput:
    """Convert BranchSector model to output schema with computed is_global field."""
    return BranchSectorOutput(
        id=sector.id,
        tenant_id=sector.tenant_id,
        branch_id=sector.branch_id,
        name=sector.name,
        prefix=sector.prefix,
        display_order=sector.display_order,
        is_active=sector.is_active,
        is_global=sector.branch_id is None,
    )


@router.get("/sectors", response_model=list[BranchSectorOutput])
def list_sectors(
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[BranchSectorOutput]:
    """
    List sectors available for a branch.
    If branch_id provided, returns global sectors + branch-specific sectors.
    If no branch_id, returns only global sectors.

    MANAGER users can only see sectors from their assigned branches.
    """
    tenant_id = user["tenant_id"]

    # MANAGER branch isolation
    branch_ids_filter, should_filter = filter_by_accessible_branches(user, branch_id)
    if should_filter and not branch_ids_filter:
        # No branch access, return only global sectors
        query = select(BranchSector).where(
            BranchSector.tenant_id == tenant_id,
            BranchSector.is_active.is_(True),
            BranchSector.branch_id == None,
        )
        query = query.order_by(BranchSector.display_order, BranchSector.name)
        sectors = db.scalars(query).all()
        return [_sector_to_output(s) for s in sectors]

    query = select(BranchSector).where(
        BranchSector.tenant_id == tenant_id,
        BranchSector.is_active.is_(True),
    )

    if should_filter:
        # MANAGER: global sectors + sectors from accessible branches
        query = query.where(
            or_(
                BranchSector.branch_id == None,
                BranchSector.branch_id.in_(branch_ids_filter),
            )
        )
    elif branch_id:
        # ADMIN with specific branch_id
        query = query.where(
            or_(
                BranchSector.branch_id == None,
                BranchSector.branch_id == branch_id,
            )
        )
    else:
        # ADMIN without branch_id - only global sectors
        query = query.where(BranchSector.branch_id == None)

    query = query.order_by(BranchSector.display_order, BranchSector.name)
    sectors = db.scalars(query).all()

    return [_sector_to_output(s) for s in sectors]


@router.post("/sectors", response_model=BranchSectorOutput, status_code=status.HTTP_201_CREATED)
def create_sector(
    body: BranchSectorCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchSectorOutput:
    """
    Create a new sector.
    Global sectors (branch_id=None) require ADMIN role.
    Branch-specific sectors require ADMIN or MANAGER role.

    MANAGER users can only create sectors in their assigned branches.
    """
    tenant_id = user["tenant_id"]
    roles = user.get("roles", [])

    if body.branch_id is None and "ADMIN" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to create global sectors",
        )

    if body.branch_id is not None and "ADMIN" not in roles and "MANAGER" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or Manager role required",
        )

    # MANAGER branch isolation
    if body.branch_id is not None and not is_admin(user):
        validate_branch_access(user, body.branch_id)

    prefix = body.prefix.upper().strip()
    if not re.match(r'^[A-Z]{2,4}$', prefix):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prefix must be 2-4 uppercase letters",
        )

    existing = db.scalar(
        select(BranchSector).where(
            BranchSector.tenant_id == tenant_id,
            BranchSector.branch_id == body.branch_id,
            BranchSector.prefix == prefix,
            BranchSector.is_active.is_(True),
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Sector with prefix '{prefix}' already exists",
        )

    max_order = db.scalar(
        select(func.coalesce(func.max(BranchSector.display_order), 0)).where(
            BranchSector.tenant_id == tenant_id,
            or_(
                BranchSector.branch_id == body.branch_id,
                BranchSector.branch_id == None,
            ),
        )
    )

    sector = BranchSector(
        tenant_id=tenant_id,
        branch_id=body.branch_id,
        name=body.name.strip(),
        prefix=prefix,
        display_order=(max_order or 0) + 1,
    )
    set_created_by(sector, get_user_id(user), get_user_email(user))

    db.add(sector)
    db.commit()
    db.refresh(sector)

    return _sector_to_output(sector)


@router.delete("/sectors/{sector_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sector(
    sector_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> None:
    """
    Soft delete a sector. Cannot delete global sectors.
    Requires ADMIN or MANAGER role.

    MANAGER users can only delete sectors from their assigned branches.
    """
    sector = db.scalar(
        select(BranchSector).where(
            BranchSector.id == sector_id,
            BranchSector.tenant_id == user["tenant_id"],
            BranchSector.is_active.is_(True),
        )
    )
    if not sector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sector not found",
        )

    if sector.branch_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete global sectors",
        )

    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, sector.branch_id)

    soft_delete(db, sector, get_user_id(user), get_user_email(user))
