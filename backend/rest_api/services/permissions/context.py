"""
Permission Context - Main entry point for permission checks.
"""

from enum import Enum, auto
from typing import Any
from sqlalchemy import Select

from .strategies import (
    PermissionStrategy,
    get_highest_privilege_strategy,
)


class Action(Enum):
    """Available actions for permission checks."""
    CREATE = auto()
    READ = auto()
    UPDATE = auto()
    DELETE = auto()
    LIST = auto()  # Alias for READ with filtering


class PermissionContext:
    """
    Context for performing permission checks.

    Automatically selects the appropriate strategy based on user roles.

    Usage:
        ctx = PermissionContext(user)

        # Check specific action
        if ctx.can(Action.CREATE, "Product", branch_id=5):
            product = create_product(...)

        # Filter query by permissions
        query = ctx.filter_query(query, Product)

        # Get user info
        print(ctx.user_id, ctx.tenant_id, ctx.roles)
    """

    def __init__(self, user: dict):
        self._user = user
        self._roles = user.get("roles", [])
        self._strategy = get_highest_privilege_strategy(self._roles)

    @property
    def user(self) -> dict:
        """Get raw user dict."""
        return self._user

    @property
    def user_id(self) -> int:
        """Get user ID."""
        sub = self._user.get("sub")
        if sub is None:
            return 0
        return int(sub) if isinstance(sub, str) else sub

    @property
    def user_email(self) -> str:
        """Get user email."""
        return self._user.get("email", "")

    @property
    def tenant_id(self) -> int:
        """Get tenant ID."""
        return self._user.get("tenant_id", 0)

    @property
    def branch_ids(self) -> list[int]:
        """Get user's accessible branch IDs."""
        return self._user.get("branch_ids", [])

    @property
    def roles(self) -> list[str]:
        """Get user roles."""
        return self._roles

    @property
    def strategy(self) -> PermissionStrategy:
        """Get current permission strategy."""
        return self._strategy

    @property
    def is_admin(self) -> bool:
        """Check if user is admin."""
        return "ADMIN" in self._roles

    @property
    def is_manager(self) -> bool:
        """Check if user is manager."""
        return "MANAGER" in self._roles

    @property
    def is_management(self) -> bool:
        """Check if user is admin or manager."""
        return self.is_admin or self.is_manager

    def can(
        self,
        action: Action,
        entity_or_type: Any,
        branch_id: int | None = None,
    ) -> bool:
        """
        Check if user can perform action.

        Args:
            action: The action to check (CREATE, READ, UPDATE, DELETE)
            entity_or_type: Either an entity instance or entity type name (str)
            branch_id: Optional branch ID for CREATE action

        Returns:
            True if action is allowed
        """
        if action == Action.CREATE:
            # For create, we need entity type name
            entity_type = entity_or_type if isinstance(entity_or_type, str) else type(entity_or_type).__name__
            return self._strategy.can_create(self._user, entity_type, branch_id)

        elif action == Action.READ or action == Action.LIST:
            return self._strategy.can_read(self._user, entity_or_type)

        elif action == Action.UPDATE:
            return self._strategy.can_update(self._user, entity_or_type)

        elif action == Action.DELETE:
            return self._strategy.can_delete(self._user, entity_or_type)

        return False

    def can_create(self, entity_type: str, branch_id: int | None = None) -> bool:
        """Shorthand for can(Action.CREATE, ...)."""
        return self.can(Action.CREATE, entity_type, branch_id)

    def can_read(self, entity: Any) -> bool:
        """Shorthand for can(Action.READ, ...)."""
        return self.can(Action.READ, entity)

    def can_update(self, entity: Any) -> bool:
        """Shorthand for can(Action.UPDATE, ...)."""
        return self.can(Action.UPDATE, entity)

    def can_delete(self, entity: Any) -> bool:
        """Shorthand for can(Action.DELETE, ...)."""
        return self.can(Action.DELETE, entity)

    def filter_query(self, query: Select, model: Any) -> Select:
        """
        Apply permission filters to query.

        Args:
            query: SQLAlchemy Select query
            model: SQLAlchemy model class

        Returns:
            Filtered query
        """
        return self._strategy.filter_query(query, self._user, model)

    def has_branch_access(self, branch_id: int | None) -> bool:
        """Check if user has access to specific branch."""
        if branch_id is None:
            return True
        if self.is_admin:
            return True
        return branch_id in self.branch_ids

    def require_branch_access(self, branch_id: int | None) -> None:
        """Raise ForbiddenError if user doesn't have branch access."""
        if not self.has_branch_access(branch_id):
            from shared.utils.exceptions import ForbiddenError
            raise ForbiddenError("acceder a esta sucursal", branch_id=branch_id)

    def require_admin(self) -> None:
        """Raise ForbiddenError if user is not admin."""
        if not self.is_admin:
            from shared.utils.exceptions import ForbiddenError
            raise ForbiddenError("realizar esta acción (se requiere ADMIN)")

    def require_management(self) -> None:
        """Raise ForbiddenError if user is not admin or manager."""
        if not self.is_management:
            from shared.utils.exceptions import ForbiddenError
            raise ForbiddenError("realizar esta acción (se requiere ADMIN o MANAGER)")
