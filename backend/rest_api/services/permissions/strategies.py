"""
Permission Strategy implementations.
Strategy Pattern for role-based access control.

Each strategy defines what actions a role can perform on entities.

LOW-02 FIX: Applied Interface Segregation Principle (ISP).
Separated permission concerns into focused protocols:
- CanRead: Read permission checks
- CanCreate: Create permission checks
- CanUpdate: Update permission checks
- CanDelete: Delete permission checks
- QueryFilter: Query filtering for listings

Strategies can implement only the protocols they need via mixins,
while PermissionStrategy maintains backward compatibility.
"""

from abc import ABC, abstractmethod
from typing import Any, Protocol, runtime_checkable
from sqlalchemy import Select

from shared.config.constants import Roles, MANAGEMENT_ROLES


# =============================================================================
# Entity Protocols
# =============================================================================


@runtime_checkable
class HasBranchId(Protocol):
    """Protocol for entities with branch_id."""
    branch_id: int | None


@runtime_checkable
class HasTenantId(Protocol):
    """Protocol for entities with tenant_id."""
    tenant_id: int


# =============================================================================
# LOW-02 FIX: Segregated Permission Protocols (ISP)
# =============================================================================


class CanRead(Protocol):
    """
    Protocol for read permission checks.

    LOW-02 FIX: Segregated interface for read-only access.
    Implement this for roles that can read entities.
    """

    def can_read(self, user: dict, entity: Any) -> bool:
        """Check if user can read entity."""
        ...


class CanCreate(Protocol):
    """
    Protocol for create permission checks.

    LOW-02 FIX: Segregated interface for create access.
    Implement this for roles that can create entities.
    """

    def can_create(self, user: dict, entity_type: str, branch_id: int | None = None) -> bool:
        """Check if user can create entity of given type."""
        ...


class CanUpdate(Protocol):
    """
    Protocol for update permission checks.

    LOW-02 FIX: Segregated interface for update access.
    Implement this for roles that can update entities.
    """

    def can_update(self, user: dict, entity: Any) -> bool:
        """Check if user can update entity."""
        ...


class CanDelete(Protocol):
    """
    Protocol for delete permission checks.

    LOW-02 FIX: Segregated interface for delete access.
    Implement this for roles that can delete entities.
    """

    def can_delete(self, user: dict, entity: Any) -> bool:
        """Check if user can delete entity."""
        ...


class QueryFilter(Protocol):
    """
    Protocol for query filtering.

    LOW-02 FIX: Segregated interface for query scope limiting.
    """

    def filter_query(self, query: Select, user: dict, model: Any) -> Select:
        """Apply permission filters to query."""
        ...


# =============================================================================
# LOW-02 FIX: Default Mixins for Common Patterns
# =============================================================================


class NoCreateMixin:
    """Mixin for roles that cannot create anything."""

    def can_create(self, user: dict, entity_type: str, branch_id: int | None = None) -> bool:
        return False


class NoDeleteMixin:
    """Mixin for roles that cannot delete anything."""

    def can_delete(self, user: dict, entity: Any) -> bool:
        return False


class BranchFilterMixin:
    """Mixin for branch-based query filtering."""

    def filter_query(self, query: Select, user: dict, model: Any) -> Select:
        if hasattr(model, "branch_id"):
            branch_ids = user.get("branch_ids", [])
            if branch_ids:
                query = query.where(model.branch_id.in_(branch_ids))
        return query


class BranchAccessMixin:
    """Mixin providing branch access helper methods."""

    def _user_has_branch_access(self, user: dict, branch_id: int | None) -> bool:
        """Check if user has access to branch."""
        if branch_id is None:
            return True  # Tenant-wide entity
        branch_ids = user.get("branch_ids", [])
        return branch_id in branch_ids

    def _get_entity_branch_id(self, entity: Any) -> int | None:
        """Extract branch_id from entity if it has one."""
        if isinstance(entity, HasBranchId):
            return entity.branch_id
        return getattr(entity, "branch_id", None)


# =============================================================================
# Base Permission Strategy (Backward Compatible)
# =============================================================================


class PermissionStrategy(ABC, BranchAccessMixin):
    """
    Abstract base for permission strategies.

    Each implementation defines access rules for a specific role.

    LOW-02 FIX: Inherits from BranchAccessMixin for shared helpers.
    Consider using segregated protocols (CanRead, CanCreate, etc.)
    and mixins (NoCreateMixin, NoDeleteMixin) for cleaner implementations.
    """

    @property
    @abstractmethod
    def role_name(self) -> str:
        """Return the role this strategy handles."""
        ...

    @abstractmethod
    def can_create(self, user: dict, entity_type: str, branch_id: int | None = None) -> bool:
        """Check if user can create entity of given type."""
        ...

    @abstractmethod
    def can_read(self, user: dict, entity: Any) -> bool:
        """Check if user can read entity."""
        ...

    @abstractmethod
    def can_update(self, user: dict, entity: Any) -> bool:
        """Check if user can update entity."""
        ...

    @abstractmethod
    def can_delete(self, user: dict, entity: Any) -> bool:
        """Check if user can delete entity."""
        ...

    @abstractmethod
    def filter_query(self, query: Select, user: dict, model: Any) -> Select:
        """Apply permission filters to query."""
        ...


class AdminStrategy(PermissionStrategy):
    """
    Admin has full access to all tenant resources.
    No branch restrictions.
    """

    @property
    def role_name(self) -> str:
        return Roles.ADMIN

    def can_create(self, user: dict, entity_type: str, branch_id: int | None = None) -> bool:
        return True

    def can_read(self, user: dict, entity: Any) -> bool:
        return True

    def can_update(self, user: dict, entity: Any) -> bool:
        return True

    def can_delete(self, user: dict, entity: Any) -> bool:
        return True

    def filter_query(self, query: Select, user: dict, model: Any) -> Select:
        # Admin sees all in tenant (tenant filter applied elsewhere)
        return query


class ManagerStrategy(NoDeleteMixin, BranchFilterMixin, PermissionStrategy):
    """
    Manager has limited access:
    - Can create/update in assigned branches only
    - Can manage staff, tables, allergens, promotions in their branches
    - Cannot delete most entities

    LOW-02 FIX: Uses mixins for common patterns (ISP compliance).
    - NoDeleteMixin: can_delete() always returns False
    - BranchFilterMixin: filter_query() filters by branch_ids
    """

    # Entity types managers can create
    CREATABLE_ENTITIES = frozenset({
        "Staff", "Table", "Allergen", "Promotion", "BranchSector",
        "WaiterSectorAssignment", "ServiceCall",
    })

    # Entity types managers can update
    UPDATABLE_ENTITIES = frozenset({
        "Staff", "Table", "Allergen", "Promotion", "BranchSector",
        "WaiterSectorAssignment", "Round", "TableSession", "ServiceCall",
        "KitchenTicket",
    })

    @property
    def role_name(self) -> str:
        return Roles.MANAGER

    def can_create(self, user: dict, entity_type: str, branch_id: int | None = None) -> bool:
        if entity_type not in self.CREATABLE_ENTITIES:
            return False
        return self._user_has_branch_access(user, branch_id)

    def can_read(self, user: dict, entity: Any) -> bool:
        branch_id = self._get_entity_branch_id(entity)
        return self._user_has_branch_access(user, branch_id)

    def can_update(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.UPDATABLE_ENTITIES:
            return False
        branch_id = self._get_entity_branch_id(entity)
        return self._user_has_branch_access(user, branch_id)


class KitchenStrategy(NoCreateMixin, NoDeleteMixin, BranchFilterMixin, PermissionStrategy):
    """
    Kitchen staff has very limited access:
    - Can read rounds and tickets assigned to their branch
    - Can update ticket/round status (IN_KITCHEN -> READY)
    - Cannot create or delete anything

    LOW-02 FIX: Uses mixins for common patterns (ISP compliance).
    - NoCreateMixin: can_create() always returns False
    - NoDeleteMixin: can_delete() always returns False
    - BranchFilterMixin: filter_query() filters by branch_ids
    """

    # Entity types kitchen can read
    READABLE_ENTITIES = frozenset({
        "Round", "RoundItem", "KitchenTicket", "KitchenTicketItem",
        "Product", "Category", "Subcategory", "Recipe",
    })

    # Entity types kitchen can update
    UPDATABLE_ENTITIES = frozenset({
        "Round", "KitchenTicket",
    })

    @property
    def role_name(self) -> str:
        return Roles.KITCHEN

    def can_read(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.READABLE_ENTITIES:
            return False
        branch_id = self._get_entity_branch_id(entity)
        return self._user_has_branch_access(user, branch_id)

    def can_update(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.UPDATABLE_ENTITIES:
            return False
        branch_id = self._get_entity_branch_id(entity)
        return self._user_has_branch_access(user, branch_id)


class WaiterStrategy(NoDeleteMixin, BranchFilterMixin, PermissionStrategy):
    """
    Waiter has operational access:
    - Can read tables, rounds, sessions in assigned sectors
    - Can create service calls, submit rounds
    - Can update round status (READY -> SERVED)
    - Cannot delete anything

    LOW-02 FIX: Uses mixins for common patterns (ISP compliance).
    - NoDeleteMixin: can_delete() always returns False
    - BranchFilterMixin: filter_query() filters by branch_ids
    """

    # Entity types waiter can create
    CREATABLE_ENTITIES = frozenset({
        "ServiceCall", "Round", "RoundItem", "Diner",
    })

    # Entity types waiter can read
    READABLE_ENTITIES = frozenset({
        "Table", "TableSession", "Round", "RoundItem", "ServiceCall",
        "Product", "Category", "Subcategory", "Check", "Diner",
        "BranchSector", "WaiterSectorAssignment",
    })

    # Entity types waiter can update
    UPDATABLE_ENTITIES = frozenset({
        "Round", "ServiceCall",
    })

    @property
    def role_name(self) -> str:
        return Roles.WAITER

    def can_create(self, user: dict, entity_type: str, branch_id: int | None = None) -> bool:
        if entity_type not in self.CREATABLE_ENTITIES:
            return False
        return self._user_has_branch_access(user, branch_id)

    def can_read(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.READABLE_ENTITIES:
            return False
        branch_id = self._get_entity_branch_id(entity)
        return self._user_has_branch_access(user, branch_id)

    def can_update(self, user: dict, entity: Any) -> bool:
        entity_type = type(entity).__name__
        if entity_type not in self.UPDATABLE_ENTITIES:
            return False
        branch_id = self._get_entity_branch_id(entity)
        return self._user_has_branch_access(user, branch_id)


class NoUpdateMixin:
    """Mixin for roles that cannot update anything."""

    def can_update(self, user: dict, entity: Any) -> bool:
        return False


class ReadOnlyStrategy(NoCreateMixin, NoUpdateMixin, NoDeleteMixin, PermissionStrategy):
    """
    Read-only fallback for users without specific roles.
    Can only read public information.

    LOW-02 FIX: Uses mixins for common patterns (ISP compliance).
    - NoCreateMixin: can_create() always returns False
    - NoUpdateMixin: can_update() always returns False
    - NoDeleteMixin: can_delete() always returns False
    """

    @property
    def role_name(self) -> str:
        return "READ_ONLY"

    def can_read(self, user: dict, entity: Any) -> bool:
        # Only public entities
        return getattr(entity, "is_public", False)

    def filter_query(self, query: Select, user: dict, model: Any) -> Select:
        # Only public entities
        if hasattr(model, "is_public"):
            query = query.where(model.is_public.is_(True))
        return query


# Strategy registry
STRATEGY_REGISTRY: dict[str, type[PermissionStrategy]] = {
    Roles.ADMIN: AdminStrategy,
    Roles.MANAGER: ManagerStrategy,
    Roles.KITCHEN: KitchenStrategy,
    Roles.WAITER: WaiterStrategy,
}


def get_strategy_for_role(role: str) -> PermissionStrategy:
    """Get permission strategy for a role."""
    strategy_class = STRATEGY_REGISTRY.get(role, ReadOnlyStrategy)
    return strategy_class()


def get_highest_privilege_strategy(roles: list[str]) -> PermissionStrategy:
    """
    Get strategy for highest privilege role.
    Priority: ADMIN > MANAGER > KITCHEN > WAITER > READ_ONLY
    """
    priority = [Roles.ADMIN, Roles.MANAGER, Roles.KITCHEN, Roles.WAITER]

    for role in priority:
        if role in roles:
            return get_strategy_for_role(role)

    return ReadOnlyStrategy()
