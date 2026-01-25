"""
Permission Strategy Pattern implementation.
HIGH-03 FIX: Eliminates 40+ role-checking if/elif/else blocks.

Usage:
    from rest_api.services.permissions import PermissionContext, Action

    ctx = PermissionContext(user)
    if not ctx.can(Action.CREATE, entity):
        raise ForbiddenError("crear este recurso")

    # Or use decorator
    @require_permission(Action.DELETE)
    def delete_product(product_id: int, user: dict = Depends(current_user)):
        ...
"""

from .strategies import (
    PermissionStrategy,
    AdminStrategy,
    ManagerStrategy,
    KitchenStrategy,
    WaiterStrategy,
    ReadOnlyStrategy,
)
from .context import PermissionContext, Action
from .decorators import (
    require_permission,
    check_branch_access,
    require_admin,
    require_management,
)

__all__ = [
    # Strategies
    "PermissionStrategy",
    "AdminStrategy",
    "ManagerStrategy",
    "KitchenStrategy",
    "WaiterStrategy",
    "ReadOnlyStrategy",
    # Context
    "PermissionContext",
    "Action",
    # Decorators
    "require_permission",
    "check_branch_access",
    "require_admin",
    "require_management",
]
