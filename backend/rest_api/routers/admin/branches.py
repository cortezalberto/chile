"""
Branch management endpoints.

PERF-BGTASK-01: Uses FastAPI BackgroundTasks for event publishing.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException, status

from rest_api.routers.admin._base import (
    Depends, Session, select,
    get_db, current_user, Branch,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin, require_admin_or_manager,
    is_admin, validate_branch_access,
)
from shared.utils.admin_schemas import BranchOutput, BranchCreate, BranchUpdate
from shared.config.logging import rest_api_logger as logger


router = APIRouter(tags=["admin-branches"])


@router.get("/branches", response_model=list[BranchOutput])
def list_branches(
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[BranchOutput]:
    """List all branches for the user's tenant.

    MANAGER users only see branches they have access to.
    ADMIN users see all branches in the tenant.
    """
    query = select(Branch).where(Branch.tenant_id == user["tenant_id"])

    # MANAGER branch isolation: only see assigned branches
    if not is_admin(user):
        user_branch_ids = user.get("branch_ids", [])
        if not user_branch_ids:
            return []
        query = query.where(Branch.id.in_(user_branch_ids))

    if not include_deleted:
        query = query.where(Branch.is_active.is_(True))

    branches = db.execute(query.order_by(Branch.name)).scalars().all()
    return [BranchOutput.model_validate(b) for b in branches]


@router.get("/branches/{branch_id}", response_model=BranchOutput)
def get_branch(
    branch_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> BranchOutput:
    """Get a specific branch.

    MANAGER users can only access branches they have access to.
    """
    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, branch_id)

    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active.is_(True),
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )
    return BranchOutput.model_validate(branch)


@router.post("/branches", response_model=BranchOutput, status_code=status.HTTP_201_CREATED)
def create_branch(
    body: BranchCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> BranchOutput:
    """Create a new branch. Requires ADMIN role."""
    branch = Branch(
        tenant_id=user["tenant_id"],
        **body.model_dump(),
    )
    set_created_by(branch, get_user_id(user), get_user_email(user))
    db.add(branch)

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(branch)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create branch", tenant_id=user["tenant_id"], error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create branch - please try again",
        )
    return BranchOutput.model_validate(branch)


@router.patch("/branches/{branch_id}", response_model=BranchOutput)
def update_branch(
    branch_id: int,
    body: BranchUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> BranchOutput:
    """Update a branch. Requires ADMIN or MANAGER role.

    MANAGER users can only update branches they have access to.
    """
    # MANAGER branch isolation
    if not is_admin(user):
        validate_branch_access(user, branch_id)

    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active.is_(True),
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(branch, key, value)

    set_updated_by(branch, get_user_id(user), get_user_email(user))

    # AUDIT-FIX: Wrap commit in try-except for consistent error handling
    try:
        db.commit()
        db.refresh(branch)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update branch", branch_id=branch_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update branch - please try again",
        )
    return BranchOutput.model_validate(branch)


@router.delete("/branches/{branch_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_branch(
    branch_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin),
) -> None:
    """Soft delete a branch. Requires ADMIN role.

    PERF-BGTASK-01: Uses BackgroundTasks for async event publishing.
    """
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == user["tenant_id"],
            Branch.is_active.is_(True),
        )
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Branch not found",
        )

    branch_name = branch.name
    tenant_id = branch.tenant_id

    soft_delete(db, branch, get_user_id(user), get_user_email(user))

    # PERF-BGTASK-01: Pass BackgroundTasks for proper lifecycle management
    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="branch",
        entity_id=branch_id,
        entity_name=branch_name,
        actor_user_id=get_user_id(user),
        background_tasks=background_tasks,
    )
