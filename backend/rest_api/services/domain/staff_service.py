"""
Staff Service - Clean Architecture Implementation.

CLEAN-ARCH: Handles all staff-related business logic including:
- User CRUD with password hashing
- Branch role management (UserBranchRole)
- Role-based access control (MANAGER restrictions)

Usage:
    from rest_api.services.domain import StaffService

    service = StaffService(db)
    staff = service.list_all(tenant_id, requesting_user)
    staff = service.create_with_roles(data, tenant_id, user_id, user_email, requesting_user)
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.orm import Session, selectinload

from rest_api.models import User, UserBranchRole
from shared.utils.admin_schemas import StaffOutput
from rest_api.services.crud.soft_delete import soft_delete, set_created_by, set_updated_by
from rest_api.services.events import publish_entity_deleted
from shared.security.password import hash_password
from shared.utils.exceptions import NotFoundError, ValidationError, ForbiddenError
from shared.config.logging import get_logger
from shared.config.constants import Roles

logger = get_logger(__name__)


class StaffService:
    """
    Service for staff (user) management.

    Business rules:
    - Staff belong to a tenant
    - Staff have roles per branch via UserBranchRole
    - MANAGER cannot create/assign ADMIN role
    - MANAGER can only see/manage staff in their branches
    - Soft delete preserves audit trail
    """

    def __init__(self, db: Session):
        self._db = db
        self._entity_name = "Empleado"

    # =========================================================================
    # Query Methods
    # =========================================================================

    def list_all(
        self,
        tenant_id: int,
        requesting_user: dict,
        *,
        branch_id: int | None = None,
        include_inactive: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[StaffOutput]:
        """
        List staff members with branch-based access control.

        ADMIN: Can see all staff across all branches
        MANAGER: Can only see staff assigned to their branches

        Args:
            tenant_id: Tenant ID for isolation.
            requesting_user: User dict with roles and branch_ids.
            branch_id: Filter by specific branch.
            include_inactive: Include soft-deleted staff.
            limit: Max results (capped at 200).
            offset: Skip count.

        Returns:
            List of StaffOutput DTOs.
        """
        # Validate pagination
        limit = min(max(1, limit), 200)
        offset = max(0, offset)

        is_admin = Roles.ADMIN in requesting_user.get("roles", [])
        is_manager = Roles.MANAGER in requesting_user.get("roles", [])
        user_branch_ids = requesting_user.get("branch_ids", [])

        query = (
            select(User)
            .options(selectinload(User.branch_roles))
            .where(User.tenant_id == tenant_id)
        )

        if not include_inactive:
            query = query.where(User.is_active.is_(True))

        # Branch filtering
        if branch_id:
            self._validate_branch_access(is_admin, is_manager, user_branch_ids, branch_id)
            query = query.join(UserBranchRole).where(UserBranchRole.branch_id == branch_id)
        elif is_manager and not is_admin:
            if user_branch_ids:
                query = query.join(UserBranchRole).where(
                    UserBranchRole.branch_id.in_(user_branch_ids)
                )
            else:
                return []

        query = query.order_by(User.email).offset(offset).limit(limit)
        staff = self._db.execute(query).scalars().unique().all()
        return [self._to_output(s) for s in staff]

    def get_by_id(
        self,
        staff_id: int,
        tenant_id: int,
        requesting_user: dict,
    ) -> StaffOutput:
        """
        Get a specific staff member with access validation.

        Args:
            staff_id: Staff user ID.
            tenant_id: Tenant ID.
            requesting_user: User dict with roles and branch_ids.

        Returns:
            StaffOutput DTO.

        Raises:
            NotFoundError: If staff not found.
            ForbiddenError: If manager doesn't have access.
        """
        staff = self._get_entity(staff_id, tenant_id)
        if not staff:
            raise NotFoundError(self._entity_name, staff_id, tenant_id=tenant_id)

        # MANAGER access check
        self._validate_staff_access(staff, requesting_user)

        return self._to_output(staff)

    def get_entity(
        self,
        staff_id: int,
        tenant_id: int,
    ) -> User | None:
        """Get raw entity (for internal use)."""
        return self._get_entity(staff_id, tenant_id)

    # =========================================================================
    # Write Methods
    # =========================================================================

    def create_with_roles(
        self,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
        requesting_user: dict,
    ) -> StaffOutput:
        """
        Create a new staff member with branch roles.

        ADMIN: Can create staff in any branch with any role.
        MANAGER: Can only create staff in their branches, cannot assign ADMIN role.

        Args:
            data: Staff data including branch_roles list.
            tenant_id: Tenant ID.
            user_id: Creating user ID.
            user_email: Creating user email.
            requesting_user: User dict for access validation.

        Returns:
            StaffOutput DTO.

        Raises:
            ValidationError: If email exists or invalid data.
            ForbiddenError: If manager exceeds permissions.
        """
        branch_roles_data = data.pop("branch_roles", [])

        # Validate manager permissions
        self._validate_manager_permissions_for_roles(
            requesting_user, branch_roles_data
        )

        # Check email uniqueness
        existing = self._db.scalar(select(User).where(User.email == data["email"]))
        if existing:
            raise ValidationError("Email ya registrado", field="email")

        # Hash password
        if "password" in data:
            data["password"] = hash_password(data["password"])

        # Create user
        staff = User(tenant_id=tenant_id, **data)
        set_created_by(staff, user_id, user_email)
        self._db.add(staff)
        self._db.flush()

        # Create branch roles
        for role_data in branch_roles_data:
            branch_role = UserBranchRole(
                user_id=staff.id,
                tenant_id=tenant_id,
                branch_id=role_data["branch_id"],
                role=role_data["role"],
            )
            self._db.add(branch_role)

        self._db.commit()
        self._db.refresh(staff)

        logger.info(
            "Staff created",
            staff_id=staff.id,
            email=staff.email,
            tenant_id=tenant_id,
        )

        return self._to_output_with_query(staff)

    def update_with_roles(
        self,
        staff_id: int,
        data: dict[str, Any],
        tenant_id: int,
        user_id: int,
        user_email: str,
        requesting_user: dict,
    ) -> StaffOutput:
        """
        Update a staff member and optionally their branch roles.

        ADMIN: Can update any staff in any branch with any role.
        MANAGER: Can only update staff in their branches, cannot assign ADMIN role.

        Args:
            staff_id: Staff user ID.
            data: Update data, may include branch_roles list.
            tenant_id: Tenant ID.
            user_id: Updating user ID.
            user_email: Updating user email.
            requesting_user: User dict for access validation.

        Returns:
            StaffOutput DTO.

        Raises:
            NotFoundError: If staff not found.
            ForbiddenError: If manager exceeds permissions.
        """
        staff = self._get_entity(staff_id, tenant_id)
        if not staff:
            raise NotFoundError(self._entity_name, staff_id, tenant_id=tenant_id)

        # Validate staff access
        self._validate_staff_access(staff, requesting_user)

        branch_roles_data = data.pop("branch_roles", None)

        # Validate manager permissions for new roles
        if branch_roles_data is not None:
            self._validate_manager_permissions_for_roles(
                requesting_user, branch_roles_data
            )

        # Hash password if provided
        if "password" in data and data["password"]:
            data["password"] = hash_password(data["password"])
        else:
            data.pop("password", None)

        # Update fields
        for key, value in data.items():
            if hasattr(staff, key):
                setattr(staff, key, value)

        set_updated_by(staff, user_id, user_email)

        # Replace branch roles if provided
        if branch_roles_data is not None:
            self._db.execute(
                delete(UserBranchRole).where(UserBranchRole.user_id == staff_id)
            )

            for role_data in branch_roles_data:
                branch_role = UserBranchRole(
                    user_id=staff_id,
                    tenant_id=tenant_id,
                    branch_id=role_data["branch_id"],
                    role=role_data["role"],
                )
                self._db.add(branch_role)

        self._db.commit()
        self._db.refresh(staff)

        logger.info(
            "Staff updated",
            staff_id=staff_id,
            tenant_id=tenant_id,
        )

        return self._to_output_with_query(staff)

    def delete_staff(
        self,
        staff_id: int,
        tenant_id: int,
        user_id: int,
        user_email: str,
    ) -> None:
        """
        Soft delete a staff member. Requires ADMIN role (validated at router level).

        Args:
            staff_id: Staff user ID.
            tenant_id: Tenant ID.
            user_id: Deleting user ID.
            user_email: Deleting user email.

        Raises:
            NotFoundError: If staff not found.
        """
        staff = self._get_entity(staff_id, tenant_id)
        if not staff:
            raise NotFoundError(self._entity_name, staff_id, tenant_id=tenant_id)

        staff_name = f"{staff.first_name or ''} {staff.last_name or ''}".strip() or staff.email

        soft_delete(self._db, staff, user_id, user_email)

        publish_entity_deleted(
            tenant_id=tenant_id,
            entity_type="staff",
            entity_id=staff_id,
            entity_name=staff_name,
            actor_user_id=user_id,
        )

        logger.info(
            "Staff deleted",
            staff_id=staff_id,
            tenant_id=tenant_id,
        )

    # =========================================================================
    # Private Helpers
    # =========================================================================

    def _get_entity(self, staff_id: int, tenant_id: int) -> User | None:
        """Get staff entity with branch roles loaded."""
        return self._db.scalar(
            select(User)
            .options(selectinload(User.branch_roles))
            .where(
                User.id == staff_id,
                User.tenant_id == tenant_id,
                User.is_active.is_(True),
            )
        )

    def _validate_branch_access(
        self,
        is_admin: bool,
        is_manager: bool,
        user_branch_ids: list[int],
        branch_id: int,
    ) -> None:
        """Validate user has access to specified branch."""
        if is_manager and not is_admin and branch_id not in user_branch_ids:
            raise ForbiddenError(
                "acceder a esta sucursal",
                branch_id=branch_id,
            )

    def _validate_staff_access(
        self,
        staff: User,
        requesting_user: dict,
    ) -> None:
        """Validate manager has access to staff member."""
        is_admin = Roles.ADMIN in requesting_user.get("roles", [])
        is_manager = Roles.MANAGER in requesting_user.get("roles", [])

        if is_manager and not is_admin:
            user_branch_ids = set(requesting_user.get("branch_ids", []))
            staff_branch_ids = {br.branch_id for br in staff.branch_roles}

            if not user_branch_ids.intersection(staff_branch_ids):
                raise ForbiddenError(
                    "acceder a este empleado",
                    staff_id=staff.id,
                )

    def _validate_manager_permissions_for_roles(
        self,
        requesting_user: dict,
        branch_roles: list[dict],
    ) -> None:
        """Validate manager doesn't exceed permissions when assigning roles."""
        is_admin = Roles.ADMIN in requesting_user.get("roles", [])
        is_manager = Roles.MANAGER in requesting_user.get("roles", [])

        if is_manager and not is_admin:
            user_branch_ids = set(requesting_user.get("branch_ids", []))

            for role in branch_roles:
                branch_id = role.get("branch_id")
                role_name = role.get("role", "")

                if branch_id not in user_branch_ids:
                    raise ForbiddenError(
                        f"asignar roles en la sucursal {branch_id}",
                        branch_id=branch_id,
                    )

                if role_name == Roles.ADMIN:
                    raise ForbiddenError(
                        "asignar el rol de ADMIN",
                        detail="Solo un administrador puede asignar el rol de ADMIN",
                    )

    def _to_output(self, user: User) -> StaffOutput:
        """Build StaffOutput from pre-loaded branch_roles."""
        roles_list = [
            {"branch_id": br.branch_id, "role": br.role}
            for br in (user.branch_roles or [])
        ]

        return StaffOutput(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            dni=user.dni,
            hire_date=user.hire_date,
            is_active=user.is_active,
            created_at=user.created_at,
            branch_roles=roles_list,
        )

    def _to_output_with_query(self, user: User) -> StaffOutput:
        """Build StaffOutput with separate query for branch_roles."""
        branch_roles = self._db.execute(
            select(UserBranchRole).where(UserBranchRole.user_id == user.id)
        ).scalars().all()

        roles_list = [
            {"branch_id": br.branch_id, "role": br.role}
            for br in branch_roles
        ]

        return StaffOutput(
            id=user.id,
            tenant_id=user.tenant_id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            phone=user.phone,
            dni=user.dni,
            hire_date=user.hire_date,
            is_active=user.is_active,
            created_at=user.created_at,
            branch_roles=roles_list,
        )
