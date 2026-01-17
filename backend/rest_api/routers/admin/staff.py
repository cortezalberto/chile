"""
Staff management endpoints with branch-based access control.
"""

from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    selectinload,
    get_db, current_user, User, UserBranchRole,
    soft_delete, set_created_by, set_updated_by,
    get_user_id, get_user_email, publish_entity_deleted,
    require_admin_or_manager, hash_password,
)
from rest_api.routers.admin_schemas import StaffOutput, StaffCreate, StaffUpdate


router = APIRouter(tags=["admin-staff"])


def _build_staff_output(user_obj: User, db: Session = None) -> StaffOutput:
    """Build StaffOutput with branch roles."""
    if hasattr(user_obj, 'branch_roles') and user_obj.branch_roles is not None:
        branch_roles = user_obj.branch_roles
    elif db is not None:
        branch_roles = db.execute(
            select(UserBranchRole).where(UserBranchRole.user_id == user_obj.id)
        ).scalars().all()
    else:
        branch_roles = []

    roles_list = [
        {"branch_id": br.branch_id, "role": br.role}
        for br in branch_roles
    ]

    return StaffOutput(
        id=user_obj.id,
        tenant_id=user_obj.tenant_id,
        email=user_obj.email,
        first_name=user_obj.first_name,
        last_name=user_obj.last_name,
        phone=user_obj.phone,
        dni=user_obj.dni,
        hire_date=user_obj.hire_date,
        is_active=user_obj.is_active,
        created_at=user_obj.created_at,
        branch_roles=roles_list,
    )


@router.get("/staff", response_model=list[StaffOutput])
def list_staff(
    branch_id: int | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> list[StaffOutput]:
    """List staff members, optionally filtered by branch.

    ADMIN: Can see all staff across all branches
    MANAGER: Can only see staff assigned to their branches
    """
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]
    user_branch_ids = user.get("branch_ids", [])

    query = select(User).options(
        selectinload(User.branch_roles)
    ).where(User.tenant_id == user["tenant_id"])

    if not include_deleted:
        query = query.where(User.is_active == True)

    if branch_id:
        if is_manager and not is_admin and branch_id not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a esta sucursal",
            )
        query = query.join(UserBranchRole).where(UserBranchRole.branch_id == branch_id)
    elif is_manager and not is_admin:
        if user_branch_ids:
            query = query.join(UserBranchRole).where(
                UserBranchRole.branch_id.in_(user_branch_ids)
            )
        else:
            return []

    staff = db.execute(query.order_by(User.email)).scalars().unique().all()
    return [_build_staff_output(s) for s in staff]


@router.get("/staff/{staff_id}", response_model=StaffOutput)
def get_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> StaffOutput:
    """Get a specific staff member."""
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]

    staff = db.scalar(
        select(User).options(
            selectinload(User.branch_roles)
        ).where(
            User.id == staff_id,
            User.tenant_id == user["tenant_id"],
            User.is_active == True,
        )
    )
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )

    if is_manager and not is_admin:
        user_branch_ids = set(user.get("branch_ids", []))
        staff_branch_ids = {br.branch_id for br in staff.branch_roles}
        if not user_branch_ids.intersection(staff_branch_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este empleado",
            )

    return _build_staff_output(staff)


@router.post("/staff", response_model=StaffOutput, status_code=status.HTTP_201_CREATED)
def create_staff(
    body: StaffCreate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> StaffOutput:
    """Create a new staff member.

    ADMIN: Can create staff in any branch with any role
    MANAGER: Can only create staff in their assigned branches, cannot create ADMIN role
    """
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]

    if is_manager and not is_admin:
        user_branch_ids = set(user.get("branch_ids", []))

        for role in body.branch_roles:
            branch_id = role.get("branch_id")
            role_name = role.get("role", "")

            if branch_id not in user_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes acceso a la sucursal {branch_id}",
                )

            if role_name == "ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo un administrador puede asignar el rol de ADMIN",
                )

    existing = db.scalar(select(User).where(User.email == body.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    staff = User(
        tenant_id=user["tenant_id"],
        email=body.email,
        password=hash_password(body.password),
        first_name=body.first_name,
        last_name=body.last_name,
        phone=body.phone,
        dni=body.dni,
        hire_date=body.hire_date,
        is_active=body.is_active,
    )
    set_created_by(staff, get_user_id(user), get_user_email(user))
    db.add(staff)
    db.flush()

    for role in body.branch_roles:
        branch_role = UserBranchRole(
            user_id=staff.id,
            tenant_id=user["tenant_id"],
            branch_id=role["branch_id"],
            role=role["role"],
        )
        db.add(branch_role)

    db.commit()
    db.refresh(staff)
    return _build_staff_output(staff, db)


@router.patch("/staff/{staff_id}", response_model=StaffOutput)
def update_staff(
    staff_id: int,
    body: StaffUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(require_admin_or_manager),
) -> StaffOutput:
    """Update a staff member.

    ADMIN: Can update any staff member in any branch with any role
    MANAGER: Can only update staff in their branches, cannot assign ADMIN role
    """
    is_admin = "ADMIN" in user["roles"]
    is_manager = "MANAGER" in user["roles"]
    user_branch_ids = set(user.get("branch_ids", []))

    staff = db.scalar(
        select(User).options(
            selectinload(User.branch_roles)
        ).where(
            User.id == staff_id,
            User.tenant_id == user["tenant_id"],
            User.is_active == True,
        )
    )
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )

    if is_manager and not is_admin:
        staff_branch_ids = {br.branch_id for br in staff.branch_roles}
        if not user_branch_ids.intersection(staff_branch_ids):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes acceso a este empleado",
            )

    update_data = body.model_dump(exclude_unset=True)
    branch_roles = update_data.pop("branch_roles", None)

    if "password" in update_data and update_data["password"]:
        update_data["password"] = hash_password(update_data["password"])

    if branch_roles is not None and is_manager and not is_admin:
        for role in branch_roles:
            branch_id = role.get("branch_id")
            role_name = role.get("role", "")

            if branch_id not in user_branch_ids:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"No tienes acceso a la sucursal {branch_id}",
                )

            if role_name == "ADMIN":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Solo un administrador puede asignar el rol de ADMIN",
                )

    for key, value in update_data.items():
        setattr(staff, key, value)

    set_updated_by(staff, get_user_id(user), get_user_email(user))

    if branch_roles is not None:
        db.execute(
            UserBranchRole.__table__.delete().where(UserBranchRole.user_id == staff_id)
        )

        for role in branch_roles:
            branch_role = UserBranchRole(
                user_id=staff_id,
                tenant_id=user["tenant_id"],
                branch_id=role["branch_id"],
                role=role["role"],
            )
            db.add(branch_role)

    db.commit()
    db.refresh(staff)
    return _build_staff_output(staff, db)


@router.delete("/staff/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    staff_id: int,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> None:
    """Soft delete a staff member. Requires ADMIN role."""
    if "ADMIN" not in user["roles"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required",
        )

    staff = db.scalar(
        select(User).where(
            User.id == staff_id,
            User.tenant_id == user["tenant_id"],
            User.is_active == True,
        )
    )
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff not found",
        )

    staff_name = f"{staff.first_name or ''} {staff.last_name or ''}".strip() or staff.email
    tenant_id = staff.tenant_id

    soft_delete(db, staff, get_user_id(user), get_user_email(user))

    publish_entity_deleted(
        tenant_id=tenant_id,
        entity_type="staff",
        entity_id=staff_id,
        entity_name=staff_name,
        actor_user_id=get_user_id(user),
    )
