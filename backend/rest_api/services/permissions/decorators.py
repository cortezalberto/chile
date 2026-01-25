"""
Permission decorators for FastAPI routes.
"""

from functools import wraps
from typing import Callable, Any

from fastapi import Depends, HTTPException, status

from shared.security.auth import current_user_context as current_user
from shared.utils.exceptions import ForbiddenError
from .context import PermissionContext, Action


def require_permission(action: Action, entity_type: str | None = None):
    """
    Decorator to require permission for an action.

    Usage:
        @router.post("/products")
        @require_permission(Action.CREATE, "Product")
        def create_product(data: ProductCreate, user: dict = Depends(current_user)):
            ...

    Note: This decorator checks if the user's role allows the action in general.
    For entity-specific checks (branch access), use ctx.can() inside the function.
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, user: dict = None, **kwargs):
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            ctx = PermissionContext(user)

            # For CREATE, check general permission
            if action == Action.CREATE and entity_type:
                if not ctx.can_create(entity_type):
                    raise ForbiddenError(f"crear {entity_type}")

            # Inject context into kwargs if function accepts it
            kwargs["_permission_ctx"] = ctx

            return await func(*args, user=user, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, user: dict = None, **kwargs):
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            ctx = PermissionContext(user)

            if action == Action.CREATE and entity_type:
                if not ctx.can_create(entity_type):
                    raise ForbiddenError(f"crear {entity_type}")

            kwargs["_permission_ctx"] = ctx

            return func(*args, user=user, **kwargs)

        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def check_branch_access(branch_id_param: str = "branch_id"):
    """
    Decorator to check branch access.

    Usage:
        @router.get("/branches/{branch_id}/products")
        @check_branch_access("branch_id")
        def list_products(branch_id: int, user: dict = Depends(current_user)):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, user: dict = None, **kwargs):
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            branch_id = kwargs.get(branch_id_param)
            if branch_id is not None:
                ctx = PermissionContext(user)
                ctx.require_branch_access(branch_id)

            return await func(*args, user=user, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, user: dict = None, **kwargs):
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Not authenticated",
                )

            branch_id = kwargs.get(branch_id_param)
            if branch_id is not None:
                ctx = PermissionContext(user)
                ctx.require_branch_access(branch_id)

            return func(*args, user=user, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


def require_admin(func: Callable) -> Callable:
    """
    Decorator to require admin role.

    Usage:
        @router.delete("/products/{id}")
        @require_admin
        def delete_product(id: int, user: dict = Depends(current_user)):
            ...
    """
    @wraps(func)
    async def async_wrapper(*args, user: dict = None, **kwargs):
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        ctx = PermissionContext(user)
        ctx.require_admin()

        return await func(*args, user=user, **kwargs)

    @wraps(func)
    def sync_wrapper(*args, user: dict = None, **kwargs):
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        ctx = PermissionContext(user)
        ctx.require_admin()

        return func(*args, user=user, **kwargs)

    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


def require_management(func: Callable) -> Callable:
    """
    Decorator to require admin or manager role.

    Usage:
        @router.post("/staff")
        @require_management
        def create_staff(data: StaffCreate, user: dict = Depends(current_user)):
            ...
    """
    @wraps(func)
    async def async_wrapper(*args, user: dict = None, **kwargs):
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        ctx = PermissionContext(user)
        ctx.require_management()

        return await func(*args, user=user, **kwargs)

    @wraps(func)
    def sync_wrapper(*args, user: dict = None, **kwargs):
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        ctx = PermissionContext(user)
        ctx.require_management()

        return func(*args, user=user, **kwargs)

    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper
