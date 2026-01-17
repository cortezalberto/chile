"""
Kitchen Ticket router (BACK-004).
Handles operations for kitchen ticket management by station.
"""

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select

from rest_api.db import get_db
from rest_api.models import (
    Category,
    KitchenTicket,
    KitchenTicketItem,
    Product,
    Round,
    RoundItem,
    Table,
    TableSession,
)
from shared.auth import current_user_context, require_roles
from shared.logging import kitchen_logger as logger
from shared.events import (
    Event,
    get_redis_client,
    publish_to_kitchen,
    publish_to_waiters,
)


# =============================================================================
# Event Types for Kitchen Tickets
# =============================================================================

TICKET_IN_PROGRESS = "TICKET_IN_PROGRESS"
TICKET_READY = "TICKET_READY"
TICKET_DELIVERED = "TICKET_DELIVERED"


# =============================================================================
# Pydantic Schemas
# =============================================================================

# Station types
StationType = Literal["BAR", "HOT_KITCHEN", "COLD_KITCHEN", "GRILL", "PASTRY", "OTHER"]
TicketStatus = Literal["PENDING", "IN_PROGRESS", "READY", "DELIVERED"]
TicketItemStatus = Literal["PENDING", "IN_PROGRESS", "READY"]


class KitchenTicketItemOutput(BaseModel):
    """Output for a single item in a kitchen ticket."""

    id: int
    round_item_id: int
    product_id: int
    product_name: str
    qty: int
    status: TicketItemStatus
    notes: str | None = None


class KitchenTicketOutput(BaseModel):
    """Output for a kitchen ticket with its items."""

    id: int
    round_id: int
    round_number: int
    station: StationType
    status: TicketStatus
    priority: int
    notes: str | None = None
    table_id: int | None = None
    table_code: str | None = None
    items: list[KitchenTicketItemOutput]
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    delivered_at: datetime | None = None


class KitchenTicketsByStation(BaseModel):
    """Tickets grouped by station."""

    station: StationType
    tickets: list[KitchenTicketOutput]


class ListTicketsResponse(BaseModel):
    """Response for listing tickets grouped by station."""

    stations: list[KitchenTicketsByStation]


class UpdateTicketStatusRequest(BaseModel):
    """Request to update ticket status."""

    status: Literal["IN_PROGRESS", "READY", "DELIVERED"]


class GenerateTicketsRequest(BaseModel):
    """Request to generate tickets from a round."""

    station_mapping: dict[int, StationType] | None = Field(
        default=None,
        description="Optional mapping of category_id to station. If not provided, uses default mapping."
    )
    priority: int = Field(default=0, description="Priority for generated tickets (higher = more urgent)")


class GenerateTicketsResponse(BaseModel):
    """Response after generating tickets."""

    round_id: int
    tickets_created: int
    tickets: list[KitchenTicketOutput]


# =============================================================================
# Default Station Mapping
# =============================================================================

# Default category name patterns to station mapping
DEFAULT_STATION_MAPPING: dict[str, StationType] = {
    "bebida": "BAR",
    "drink": "BAR",
    "bar": "BAR",
    "cocktail": "BAR",
    "cerveza": "BAR",
    "beer": "BAR",
    "vino": "BAR",
    "wine": "BAR",
    "ensalada": "COLD_KITCHEN",
    "salad": "COLD_KITCHEN",
    "entrada fria": "COLD_KITCHEN",
    "cold": "COLD_KITCHEN",
    "postre": "PASTRY",
    "dessert": "PASTRY",
    "torta": "PASTRY",
    "cake": "PASTRY",
    "parrilla": "GRILL",
    "grill": "GRILL",
    "carne": "GRILL",
    "meat": "GRILL",
    "asado": "GRILL",
}


def get_station_for_category(category_name: str) -> StationType:
    """
    Determine the station for a category based on name patterns.
    Defaults to HOT_KITCHEN if no pattern matches.
    """
    name_lower = category_name.lower()
    for pattern, station in DEFAULT_STATION_MAPPING.items():
        if pattern in name_lower:
            return station
    return "HOT_KITCHEN"


# =============================================================================
# Router
# =============================================================================

router = APIRouter(prefix="/api/kitchen", tags=["kitchen-tickets"])


def _build_ticket_output(
    ticket: KitchenTicket,
    round_obj: Round,
    table: Table | None,
    db: Session,
) -> KitchenTicketOutput:
    """
    Helper to build KitchenTicketOutput from models.

    ROUTER-CRIT-02 FIX: Added error handling for database queries.
    """
    item_outputs = []

    try:
        # Get ticket items with product info
        ticket_items = db.execute(
            select(KitchenTicketItem, RoundItem, Product)
            .join(RoundItem, KitchenTicketItem.round_item_id == RoundItem.id)
            .join(Product, RoundItem.product_id == Product.id)
            .where(KitchenTicketItem.ticket_id == ticket.id)
        ).all()

        item_outputs = [
            KitchenTicketItemOutput(
                id=ticket_item.id,
                round_item_id=ticket_item.round_item_id,
                product_id=round_item.product_id,
                product_name=product.name,
                qty=ticket_item.qty,
                status=ticket_item.status,
                notes=round_item.notes,
            )
            for ticket_item, round_item, product in ticket_items
        ]
    except Exception as e:
        logger.error(
            "Failed to build ticket items",
            ticket_id=ticket.id,
            error=str(e),
        )
        # Continue with empty items list - ticket info is still valuable

    return KitchenTicketOutput(
        id=ticket.id,
        round_id=ticket.round_id,
        round_number=round_obj.round_number,
        station=ticket.station,
        status=ticket.status,
        priority=ticket.priority,
        notes=ticket.notes,
        table_id=table.id if table else None,
        table_code=table.code if table else None,
        items=item_outputs,
        created_at=ticket.created_at,
        started_at=ticket.started_at,
        completed_at=ticket.completed_at,
        delivered_at=ticket.delivered_at,
    )


@router.get("/tickets", response_model=ListTicketsResponse)
def list_pending_tickets(
    station: StationType | None = None,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ListTicketsResponse:
    """
    List pending kitchen tickets grouped by station.

    Returns tickets with status PENDING, IN_PROGRESS, or READY,
    ordered by priority (desc) and creation time (asc).

    Optionally filter by station.

    Requires KITCHEN, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    branch_ids = ctx.get("branch_ids", [])
    if not branch_ids:
        return ListTicketsResponse(stations=[])

    # CRIT-03 FIX: Build query with eager loading to prevent N+1 queries
    query = (
        select(KitchenTicket)
        .options(
            selectinload(KitchenTicket.items).joinedload(KitchenTicketItem.product),
        )
        .where(
            KitchenTicket.branch_id.in_(branch_ids),
            KitchenTicket.status.in_(["PENDING", "IN_PROGRESS", "READY"]),
        )
    )

    if station:
        query = query.where(KitchenTicket.station == station)

    query = query.order_by(
        KitchenTicket.priority.desc(),
        KitchenTicket.created_at.asc(),
    )

    tickets = db.execute(query).scalars().unique().all()

    # CRIT-03 FIX: Prefetch all rounds and sessions in batch to avoid N+1
    round_ids = {t.round_id for t in tickets if t.round_id}
    rounds_map: dict[int, Round] = {}
    sessions_map: dict[int, TableSession] = {}
    tables_map: dict[int, Table] = {}

    if round_ids:
        rounds = db.execute(
            select(Round)
            .options(
                joinedload(Round.session).joinedload(TableSession.table)
            )
            .where(Round.id.in_(round_ids))
        ).scalars().unique().all()

        for r in rounds:
            rounds_map[r.id] = r
            if r.session:
                sessions_map[r.table_session_id] = r.session
                if r.session.table:
                    tables_map[r.session.table_id] = r.session.table

    # Group tickets by station
    stations_map: dict[str, list[KitchenTicketOutput]] = {}

    for ticket in tickets:
        # Get round and table info from prefetched data
        round_obj = rounds_map.get(ticket.round_id) if ticket.round_id else None
        if not round_obj:
            continue

        session = sessions_map.get(round_obj.table_session_id) if round_obj else None
        table = tables_map.get(session.table_id) if session else None

        ticket_output = _build_ticket_output(ticket, round_obj, table, db)

        if ticket.station not in stations_map:
            stations_map[ticket.station] = []
        stations_map[ticket.station].append(ticket_output)

    # Convert to response format
    stations_list = [
        KitchenTicketsByStation(station=station_name, tickets=tickets_list)
        for station_name, tickets_list in sorted(stations_map.items())
    ]

    return ListTicketsResponse(stations=stations_list)


@router.get("/tickets/{ticket_id}", response_model=KitchenTicketOutput)
def get_ticket(
    ticket_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> KitchenTicketOutput:
    """
    Get details of a specific kitchen ticket.

    Requires KITCHEN, WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "WAITER", "MANAGER", "ADMIN"])

    ticket = db.scalar(select(KitchenTicket).where(KitchenTicket.id == ticket_id))

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if ticket.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Get round and table info
    round_obj = db.scalar(select(Round).where(Round.id == ticket.round_id))
    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round for ticket {ticket_id} not found",
        )

    session = db.scalar(
        select(TableSession).where(TableSession.id == round_obj.table_session_id)
    )
    table = db.scalar(
        select(Table).where(Table.id == session.table_id)
    ) if session else None

    return _build_ticket_output(ticket, round_obj, table, db)


@router.patch("/tickets/{ticket_id}/status", response_model=KitchenTicketOutput)
async def update_ticket_status(
    ticket_id: int,
    body: UpdateTicketStatusRequest,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> KitchenTicketOutput:
    """
    Update the status of a kitchen ticket.

    Valid transitions:
    - PENDING -> IN_PROGRESS (kitchen started working on it)
    - IN_PROGRESS -> READY (kitchen finished, ready for waiter)
    - READY -> DELIVERED (waiter delivered to table)

    Publishes corresponding events for real-time updates.

    Requires KITCHEN, WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "WAITER", "MANAGER", "ADMIN"])

    ticket = db.scalar(select(KitchenTicket).where(KitchenTicket.id == ticket_id))

    if not ticket:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if ticket.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Validate status transition
    valid_transitions = {
        "PENDING": ["IN_PROGRESS"],
        "IN_PROGRESS": ["READY"],
        "READY": ["DELIVERED"],
    }

    current_status = ticket.status
    new_status = body.status

    if current_status not in valid_transitions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot change status from {current_status}",
        )

    if new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid transition from {current_status} to {new_status}",
        )

    # Update status and timestamp
    now = datetime.now(timezone.utc)
    ticket.status = new_status

    if new_status == "IN_PROGRESS":
        ticket.started_at = now
        # Update all items to IN_PROGRESS
        db.execute(
            KitchenTicketItem.__table__.update()
            .where(KitchenTicketItem.ticket_id == ticket_id)
            .values(status="IN_PROGRESS")
        )
    elif new_status == "READY":
        ticket.completed_at = now
        # Update all items to READY
        db.execute(
            KitchenTicketItem.__table__.update()
            .where(KitchenTicketItem.ticket_id == ticket_id)
            .values(status="READY")
        )
    elif new_status == "DELIVERED":
        ticket.delivered_at = now

    db.commit()
    db.refresh(ticket)

    # Get round and table for event publishing
    round_obj = db.scalar(select(Round).where(Round.id == ticket.round_id))
    session = db.scalar(
        select(TableSession).where(TableSession.id == round_obj.table_session_id)
    ) if round_obj else None
    table = db.scalar(
        select(Table).where(Table.id == session.table_id)
    ) if session else None

    # Publish event
    event_type_map = {
        "IN_PROGRESS": TICKET_IN_PROGRESS,
        "READY": TICKET_READY,
        "DELIVERED": TICKET_DELIVERED,
    }

    redis = None
    try:
        redis = await get_redis_client()
        event = Event(
            type=event_type_map[new_status],
            tenant_id=ticket.tenant_id,
            branch_id=ticket.branch_id,
            table_id=table.id if table else None,
            session_id=session.id if session else None,
            entity={
                "ticket_id": ticket.id,
                "round_id": ticket.round_id,
                "station": ticket.station,
            },
            actor={
                "user_id": int(ctx["sub"]),
                "role": ctx["roles"][0] if ctx.get("roles") else "UNKNOWN",
            },
        )

        # Publish to kitchen channel for all ticket events
        await publish_to_kitchen(redis, ticket.branch_id, event)

        # Also publish to waiters for READY and DELIVERED events
        if new_status in ["READY", "DELIVERED"]:
            await publish_to_waiters(redis, ticket.branch_id, event)
    except Exception as e:
        logger.error(
            "Failed to publish ticket status event",
            ticket_id=ticket_id,
            new_status=new_status,
            error=str(e),
        )
    # Note: Don't close pooled Redis connection - pool manages lifecycle

    return _build_ticket_output(ticket, round_obj, table, db)


@router.post("/rounds/{round_id}/tickets", response_model=GenerateTicketsResponse)
def generate_tickets_from_round(
    round_id: int,
    body: GenerateTicketsRequest | None = None,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> GenerateTicketsResponse:
    """
    Auto-generate kitchen tickets from round items.

    Groups items by station based on product categories:
    - Uses provided station_mapping if given
    - Otherwise uses default mapping based on category names
    - Unmatched categories default to HOT_KITCHEN

    Requires KITCHEN, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    if body is None:
        body = GenerateTicketsRequest()

    # Find the round
    round_obj = db.scalar(select(Round).where(Round.id == round_id))

    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round {round_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if round_obj.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Check if tickets already exist for this round
    existing_tickets = db.scalar(
        select(KitchenTicket).where(KitchenTicket.round_id == round_id)
    )
    if existing_tickets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tickets already exist for round {round_id}",
        )

    # Get round items with product and category info
    items_data = db.execute(
        select(RoundItem, Product, Category)
        .join(Product, RoundItem.product_id == Product.id)
        .join(Category, Product.category_id == Category.id)
        .where(RoundItem.round_id == round_id)
    ).all()

    if not items_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No items found in round {round_id}",
        )

    # Group items by station
    items_by_station: dict[StationType, list[tuple[RoundItem, Product, Category]]] = {}

    for round_item, product, category in items_data:
        # Determine station
        if body.station_mapping and category.id in body.station_mapping:
            station = body.station_mapping[category.id]
        else:
            station = get_station_for_category(category.name)

        if station not in items_by_station:
            items_by_station[station] = []
        items_by_station[station].append((round_item, product, category))

    # Create tickets for each station
    created_tickets: list[KitchenTicket] = []

    for station, station_items in items_by_station.items():
        # Create ticket
        ticket = KitchenTicket(
            tenant_id=round_obj.tenant_id,
            branch_id=round_obj.branch_id,
            round_id=round_id,
            station=station,
            status="PENDING",
            priority=body.priority,
        )
        db.add(ticket)
        db.flush()  # Get ticket ID

        # Create ticket items
        for round_item, product, category in station_items:
            ticket_item = KitchenTicketItem(
                tenant_id=round_obj.tenant_id,
                ticket_id=ticket.id,
                round_item_id=round_item.id,
                qty=round_item.qty,
                status="PENDING",
            )
            db.add(ticket_item)

        created_tickets.append(ticket)

    db.commit()

    # Refresh tickets and build output
    session = db.scalar(
        select(TableSession).where(TableSession.id == round_obj.table_session_id)
    )
    table = db.scalar(
        select(Table).where(Table.id == session.table_id)
    ) if session else None

    ticket_outputs = []
    for ticket in created_tickets:
        db.refresh(ticket)
        ticket_outputs.append(_build_ticket_output(ticket, round_obj, table, db))

    return GenerateTicketsResponse(
        round_id=round_id,
        tickets_created=len(created_tickets),
        tickets=ticket_outputs,
    )
