"""
Redis Channel Naming.

REDIS-HIGH-01/MED-07 FIX: Standardized naming with validation.
"""

from __future__ import annotations


def _validate_positive_id(id_value: int, name: str) -> None:
    """REDIS-MED-07 FIX: Validate that ID is a positive integer."""
    if not isinstance(id_value, int) or id_value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {id_value}")


def channel_branch_waiters(branch_id: int) -> str:
    """Channel for waiter notifications in a branch."""
    _validate_positive_id(branch_id, "branch_id")
    return f"branch:{branch_id}:waiters"


def channel_branch_kitchen(branch_id: int) -> str:
    """Channel for kitchen notifications in a branch."""
    _validate_positive_id(branch_id, "branch_id")
    return f"branch:{branch_id}:kitchen"


def channel_user(user_id: int) -> str:
    """Channel for direct user notifications."""
    _validate_positive_id(user_id, "user_id")
    return f"user:{user_id}"


def channel_table_session(session_id: int) -> str:
    """Channel for diner notifications on a table session."""
    _validate_positive_id(session_id, "session_id")
    return f"session:{session_id}"


def channel_sector_waiters(sector_id: int) -> str:
    """
    Channel for waiter notifications filtered by sector assignment.

    REDIS-LOW-04 FIX: Added docstring for consistency.
    """
    _validate_positive_id(sector_id, "sector_id")
    return f"sector:{sector_id}:waiters"


def channel_branch_admin(branch_id: int) -> str:
    """Channel for admin/dashboard notifications in a branch."""
    _validate_positive_id(branch_id, "branch_id")
    return f"branch:{branch_id}:admin"


def channel_tenant_admin(tenant_id: int) -> str:
    """Channel for tenant-wide admin notifications."""
    _validate_positive_id(tenant_id, "tenant_id")
    return f"tenant:{tenant_id}:admin"
