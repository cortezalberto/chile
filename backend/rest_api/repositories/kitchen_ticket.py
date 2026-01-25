"""
Kitchen Ticket Repository - Data access for kitchen tickets.
CRIT-02 FIX: Solves N+1 problem with eager loading.
"""

from dataclasses import dataclass
from typing import Sequence
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import Select, select

from rest_api.models import (
    KitchenTicket,
    KitchenTicketItem,
    RoundItem,
    Product,
    Round,
)
from .base import BaseRepository, RepositoryFilters


@dataclass
class TicketFilters(RepositoryFilters):
    """Filters specific to kitchen tickets."""

    status: str | None = None
    statuses: list[str] | None = None
    station: str | None = None
    round_id: int | None = None


class KitchenTicketRepository(BaseRepository[KitchenTicket]):
    """
    Repository for KitchenTicket entities.

    CRIT-02 FIX: Guarantees eager loading of:
    - items -> round_item -> product
    - items -> round_item -> round

    This prevents the N+1 problem when loading 100+ tickets.
    Without eager loading: 1200+ queries
    With eager loading: ~5 queries
    """

    @property
    def model(self) -> type[KitchenTicket]:
        return KitchenTicket

    def _base_query(self, tenant_id: int) -> Select:
        """
        Base query with comprehensive eager loading.

        CRITICAL: This query structure prevents N+1:
        - Each ticket has N items
        - Each item needs round_item info
        - Each round_item needs product and round info

        Without selectinload: 100 tickets = 100 + 100*N + 100*N + 100*N queries
        With selectinload: 100 tickets = ~5 queries (1 per relationship)
        """
        return (
            select(KitchenTicket)
            .where(KitchenTicket.tenant_id == tenant_id)
            # Items with full context
            .options(
                selectinload(KitchenTicket.items)
                .joinedload(KitchenTicketItem.round_item)
                .joinedload(RoundItem.product)
            )
            .options(
                selectinload(KitchenTicket.items)
                .joinedload(KitchenTicketItem.round_item)
                .joinedload(RoundItem.round)
            )
            .order_by(KitchenTicket.created_at.desc())
        )

    def _apply_filters(self, query: Select, filters: RepositoryFilters) -> Select:
        """Apply ticket-specific filters."""
        if not isinstance(filters, TicketFilters):
            filters = TicketFilters(**filters.__dict__)

        # Branch filter
        if filters.branch_id:
            query = query.where(KitchenTicket.branch_id == filters.branch_id)
        elif filters.branch_ids:
            query = query.where(KitchenTicket.branch_id.in_(filters.branch_ids))

        # Status filter
        if filters.status:
            query = query.where(KitchenTicket.status == filters.status)
        elif filters.statuses:
            query = query.where(KitchenTicket.status.in_(filters.statuses))

        # Station filter
        if filters.station:
            query = query.where(KitchenTicket.station == filters.station)

        # Round filter
        if filters.round_id:
            query = query.where(KitchenTicket.round_id == filters.round_id)

        return query

    def find_pending(
        self,
        tenant_id: int,
        branch_id: int,
        station: str | None = None,
    ) -> Sequence[KitchenTicket]:
        """
        Find pending tickets for kitchen display.

        CRIT-02 FIX: This is the main query that was causing N+1.
        Now uses eager loading to fetch all data in ~5 queries.
        """
        filters = TicketFilters(
            branch_id=branch_id,
            status="PENDING",
            station=station,
        )
        return self.find_all(tenant_id, filters)

    def find_in_progress(
        self,
        tenant_id: int,
        branch_id: int,
        station: str | None = None,
    ) -> Sequence[KitchenTicket]:
        """Find tickets currently being prepared."""
        filters = TicketFilters(
            branch_id=branch_id,
            status="IN_PROGRESS",
            station=station,
        )
        return self.find_all(tenant_id, filters)

    def find_active(
        self,
        tenant_id: int,
        branch_id: int,
        station: str | None = None,
    ) -> Sequence[KitchenTicket]:
        """Find all active (non-completed) tickets."""
        filters = TicketFilters(
            branch_id=branch_id,
            statuses=["PENDING", "IN_PROGRESS"],
            station=station,
        )
        return self.find_all(tenant_id, filters)

    def find_by_round(
        self,
        tenant_id: int,
        round_id: int,
    ) -> Sequence[KitchenTicket]:
        """Find all tickets for a specific round."""
        filters = TicketFilters(round_id=round_id)
        return self.find_all(tenant_id, filters)

    def find_for_display(
        self,
        tenant_id: int,
        branch_id: int,
        station: str | None = None,
        limit: int = 50,
    ) -> Sequence[KitchenTicket]:
        """
        Find tickets for kitchen display screen.
        Optimized query for real-time kitchen view.
        """
        query = (
            self._base_query(tenant_id)
            .where(
                KitchenTicket.branch_id == branch_id,
                KitchenTicket.status.in_(["PENDING", "IN_PROGRESS"]),
                KitchenTicket.is_active.is_(True),
            )
            .order_by(
                KitchenTicket.priority.desc(),
                KitchenTicket.created_at.asc(),
            )
            .limit(limit)
        )

        if station:
            query = query.where(KitchenTicket.station == station)

        return self._db.execute(query).scalars().unique().all()


def get_ticket_repository(db: Session) -> KitchenTicketRepository:
    """Factory function for dependency injection."""
    return KitchenTicketRepository(db)
