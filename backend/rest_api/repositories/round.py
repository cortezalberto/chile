"""
Round Repository - Data access for rounds/orders.
CRIT-02 FIX: Eager loading prevents N+1 queries.
"""

from dataclasses import dataclass
from typing import Sequence
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import Select, select

from rest_api.models import Round, RoundItem, TableSession, Table, Product
from shared.config.constants import RoundStatus
from .base import BaseRepository, RepositoryFilters


@dataclass
class RoundFilters(RepositoryFilters):
    """Filters specific to rounds."""

    status: str | None = None
    statuses: list[str] | None = None
    session_id: int | None = None
    table_id: int | None = None
    waiter_id: int | None = None


class RoundRepository(BaseRepository[Round]):
    """
    Repository for Round entities.

    Guarantees eager loading of:
    - items -> product
    - session -> table
    """

    @property
    def model(self) -> type[Round]:
        return Round

    def _base_query(self, tenant_id: int) -> Select:
        """
        Base query with comprehensive eager loading.
        Prevents N+1 when accessing items and session info.
        """
        return (
            select(Round)
            .where(Round.tenant_id == tenant_id)
            # Items with product info
            .options(
                selectinload(Round.items)
                .joinedload(RoundItem.product)
            )
            # Session with table info
            .options(
                joinedload(Round.session)
                .joinedload(TableSession.table)
            )
            .order_by(Round.submitted_at.desc())
        )

    def _apply_filters(self, query: Select, filters: RepositoryFilters) -> Select:
        """Apply round-specific filters."""
        if not isinstance(filters, RoundFilters):
            filters = RoundFilters(**filters.__dict__)

        # Branch filter
        if filters.branch_id:
            query = query.where(Round.branch_id == filters.branch_id)
        elif filters.branch_ids:
            query = query.where(Round.branch_id.in_(filters.branch_ids))

        # Status filter
        if filters.status:
            query = query.where(Round.status == filters.status)
        elif filters.statuses:
            query = query.where(Round.status.in_(filters.statuses))

        # Session filter
        if filters.session_id:
            query = query.where(Round.session_id == filters.session_id)

        return query

    def find_pending(
        self,
        tenant_id: int,
        branch_id: int | None = None,
    ) -> Sequence[Round]:
        """Find pending rounds awaiting processing."""
        filters = RoundFilters(
            status=RoundStatus.PENDING,
            branch_id=branch_id,
        )
        return self.find_all(tenant_id, filters)

    def find_active(
        self,
        tenant_id: int,
        branch_id: int | None = None,
    ) -> Sequence[Round]:
        """Find all active (non-completed) rounds."""
        filters = RoundFilters(
            statuses=RoundStatus.ACTIVE,
            branch_id=branch_id,
        )
        return self.find_all(tenant_id, filters)

    def find_for_session(
        self,
        tenant_id: int,
        session_id: int,
    ) -> Sequence[Round]:
        """Find all rounds for a table session."""
        filters = RoundFilters(session_id=session_id)
        return self.find_all(tenant_id, filters)

    def find_for_kitchen(
        self,
        tenant_id: int,
        branch_id: int,
        statuses: list[str] | None = None,
    ) -> Sequence[Round]:
        """
        Find rounds visible to kitchen.
        Defaults to IN_KITCHEN status.
        """
        statuses = statuses or [RoundStatus.IN_KITCHEN]

        query = (
            self._base_query(tenant_id)
            .where(
                Round.branch_id == branch_id,
                Round.status.in_(statuses),
                Round.is_active.is_(True),
            )
        )

        return self._db.execute(query).scalars().unique().all()

    def find_recent_by_table(
        self,
        tenant_id: int,
        table_id: int,
        limit: int = 10,
    ) -> Sequence[Round]:
        """Find recent rounds for a specific table."""
        query = (
            self._base_query(tenant_id)
            .join(Round.session)
            .where(
                TableSession.table_id == table_id,
                Round.is_active.is_(True),
            )
            .limit(limit)
        )

        return self._db.execute(query).scalars().unique().all()


def get_round_repository(db: Session) -> RoundRepository:
    """Factory function for dependency injection."""
    return RoundRepository(db)
