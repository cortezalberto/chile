"""
Order management endpoints for active orders and reports.
"""

from datetime import datetime
from pydantic import BaseModel
from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, status, Session, select,
    selectinload, joinedload,
    get_db, current_user, Round, RoundItem, Branch, TableSession,
)


router = APIRouter(tags=["admin-orders"])


# =============================================================================
# Order Schemas
# =============================================================================


class OrderItemOutput(BaseModel):
    id: int
    product_id: int
    product_name: str
    qty: int
    unit_price_cents: int
    notes: str | None = None
    diner_name: str | None = None

    class Config:
        from_attributes = True


class ActiveOrderOutput(BaseModel):
    id: int
    round_number: int
    status: str
    table_id: int | None = None
    table_code: str | None = None
    branch_id: int
    branch_name: str
    session_id: int
    items: list[OrderItemOutput]
    submitted_at: datetime | None = None
    total_cents: int = 0

    class Config:
        from_attributes = True


class OrderStatsOutput(BaseModel):
    total_active: int
    pending: int
    in_kitchen: int
    ready: int


# =============================================================================
# Order Endpoints
# =============================================================================


@router.get("/orders/stats", response_model=OrderStatsOutput)
def get_order_stats(
    branch_id: int | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> OrderStatsOutput:
    """Get order statistics for the dashboard."""
    # RTR-CRIT-02 FIX: Add tenant_id filter for multi-tenant isolation
    tenant_id = user["tenant_id"]
    branch_ids = user.get("branch_ids", [])
    if not branch_ids:
        return OrderStatsOutput(total_active=0, pending=0, in_kitchen=0, ready=0)

    if branch_id is not None:
        if branch_id not in branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this branch",
            )
        branch_ids = [branch_id]

    active_statuses = ["SUBMITTED", "IN_KITCHEN", "READY"]

    # RTR-CRIT-02 FIX: Filter by tenant_id for multi-tenant isolation
    base_query = select(Round).where(
        Round.tenant_id == tenant_id,
        Round.branch_id.in_(branch_ids),
        Round.status.in_(active_statuses),
    )

    all_rounds = db.execute(base_query).scalars().all()

    pending = sum(1 for r in all_rounds if r.status == "SUBMITTED")
    in_kitchen = sum(1 for r in all_rounds if r.status == "IN_KITCHEN")
    ready = sum(1 for r in all_rounds if r.status == "READY")

    return OrderStatsOutput(
        total_active=len(all_rounds),
        pending=pending,
        in_kitchen=in_kitchen,
        ready=ready,
    )


@router.get("/orders", response_model=list[ActiveOrderOutput])
def get_active_orders(
    branch_id: int | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[ActiveOrderOutput]:
    """
    Get all active orders (rounds) across branches.
    Includes SUBMITTED, IN_KITCHEN, and READY orders.
    """
    # RTR-CRIT-02 FIX: Add tenant_id filter for multi-tenant isolation
    tenant_id = user["tenant_id"]
    branch_ids = user.get("branch_ids", [])
    if not branch_ids:
        return []

    if branch_id is not None:
        if branch_id not in branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No access to this branch",
            )
        branch_ids = [branch_id]

    active_statuses = ["SUBMITTED", "IN_KITCHEN", "READY"]
    if status_filter and status_filter in active_statuses:
        active_statuses = [status_filter]

    # RTR-CRIT-02 FIX: Filter by tenant_id for multi-tenant isolation
    rounds = db.execute(
        select(Round)
        .options(
            selectinload(Round.items).joinedload(RoundItem.product),
            selectinload(Round.items).joinedload(RoundItem.diner),
            joinedload(Round.session).joinedload(TableSession.table),
        )
        .where(
            Round.tenant_id == tenant_id,
            Round.branch_id.in_(branch_ids),
            Round.status.in_(active_statuses),
        )
        .order_by(Round.submitted_at.asc())
    ).scalars().unique().all()

    unique_branch_ids = list(set(r.branch_id for r in rounds))
    if unique_branch_ids:
        branches_result = db.execute(
            select(Branch).where(Branch.id.in_(unique_branch_ids))
        ).scalars().all()
        branches_by_id = {b.id: b for b in branches_result}
    else:
        branches_by_id = {}

    result = []
    for round_obj in rounds:
        session = round_obj.session
        table = session.table if session else None
        branch = branches_by_id.get(round_obj.branch_id)

        order_items = []
        total_cents = 0
        for item in round_obj.items:
            total_cents += item.unit_price_cents * item.qty
            diner_name = item.diner.name if item.diner else None

            order_items.append(OrderItemOutput(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name,
                qty=item.qty,
                unit_price_cents=item.unit_price_cents,
                notes=item.notes,
                diner_name=diner_name,
            ))

        result.append(ActiveOrderOutput(
            id=round_obj.id,
            round_number=round_obj.round_number,
            status=round_obj.status,
            table_id=table.id if table else None,
            table_code=table.code if table else None,
            branch_id=round_obj.branch_id,
            branch_name=branch.name if branch else "Unknown",
            session_id=round_obj.table_session_id,
            items=order_items,
            submitted_at=round_obj.submitted_at,
            total_cents=total_cents,
        ))

    return result
