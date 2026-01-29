"""
Kitchen Ticket router (BACK-004).
Handles operations for kitchen ticket management by station.
CLEAN-ARCH: Thin router delegating to TicketService.
"""

from typing import Any

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from shared.infrastructure.db import get_db
from shared.security.auth import current_user_context, require_roles
from shared.utils.kitchen_schemas import (
    KitchenTicketOutput,
    ListTicketsResponse,
    UpdateTicketStatusRequest,
    GenerateTicketsResponse,
    GenerateTicketsRequest,
    StationType
)
from rest_api.services.domain.ticket_service import TicketService

router = APIRouter(prefix="/api/kitchen", tags=["kitchen-tickets"])

def _get_service(db: Session) -> TicketService:
    return TicketService(db)

@router.get("/tickets", response_model=ListTicketsResponse)
def list_pending_tickets(
    station: StationType | None = None,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ListTicketsResponse:
    """
    List pending kitchen tickets grouped by station.
    Requires KITCHEN, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])
    
    service = _get_service(db)
    
    stations_list = service.list_pending_by_stations(
        tenant_id=ctx["tenant_id"],
        branch_ids=ctx.get("branch_ids", []),
        station_filter=station
    )
    
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
    
    service = _get_service(db)
    return service.get_ticket_details(
        ticket_id=ticket_id,
        tenant_id=ctx["tenant_id"],
        branch_ids=ctx.get("branch_ids", [])
    )

@router.patch("/tickets/{ticket_id}/status", response_model=KitchenTicketOutput)
async def update_ticket_status(
    ticket_id: int,
    body: UpdateTicketStatusRequest,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> KitchenTicketOutput:
    """
    Update the status of a kitchen ticket.
    Requires KITCHEN, WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "WAITER", "MANAGER", "ADMIN"])
    
    service = _get_service(db)
    # Note: Service handles event publishing which is async
    # Since Service is initialized with sync DB session, we might need adjustments
    # But here we call an async method on the service.
    return await service.update_status(
        ticket_id=ticket_id,
        new_status=body.status,
        user=ctx
    )

@router.post("/rounds/{round_id}/tickets", response_model=GenerateTicketsResponse)
def generate_tickets_from_round(
    round_id: int,
    body: GenerateTicketsRequest | None = None,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> GenerateTicketsResponse:
    """
    Auto-generate kitchen tickets from round items.
    Requires KITCHEN, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])
    
    if body is None:
        body = GenerateTicketsRequest()
        
    service = _get_service(db)
    return service.generate_from_round(
        round_id=round_id,
        tenant_id=ctx["tenant_id"],
        branch_ids=ctx.get("branch_ids", []),
        station_mapping=body.station_mapping,
        priority=body.priority
    )
