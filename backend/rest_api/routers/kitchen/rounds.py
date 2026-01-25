"""
Kitchen router.
Handles operations for kitchen staff.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, selectinload, joinedload
from sqlalchemy import select

from shared.infrastructure.db import get_db
from rest_api.models import (
    Round,
    RoundItem,
    Product,
    Table,
    TableSession,
)
from shared.security.auth import current_user_context, require_roles
from shared.utils.schemas import (
    RoundOutput,
    RoundItemOutput,
    UpdateRoundStatusRequest,
)
from shared.config.logging import kitchen_logger as logger
from shared.infrastructure.events import (
    get_redis_client,
    publish_round_event,
    ROUND_IN_KITCHEN,
    ROUND_READY,
    ROUND_SERVED,
)


router = APIRouter(prefix="/api/kitchen", tags=["kitchen"])


@router.get("/rounds", response_model=list[RoundOutput])
def get_pending_rounds(
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[RoundOutput]:
    """
    Get all pending rounds for the kitchen.

    Returns rounds with status SUBMITTED or IN_KITCHEN,
    ordered by submission time (oldest first).

    Requires KITCHEN, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["KITCHEN", "MANAGER", "ADMIN"])

    branch_ids = ctx.get("branch_ids", [])
    if not branch_ids:
        return []

    # Get pending rounds with eager loading to avoid N+1 queries
    # - selectinload for items (one-to-many collection)
    # - joinedload for session->table chain (many-to-one)
    rounds = db.execute(
        select(Round)
        .options(
            selectinload(Round.items).joinedload(RoundItem.product),
            joinedload(Round.session).joinedload(TableSession.table),
        )
        .where(
            Round.branch_id.in_(branch_ids),
            Round.status.in_(["SUBMITTED", "IN_KITCHEN"]),
        )
        .order_by(Round.submitted_at.asc())
    ).scalars().unique().all()

    result = []
    for round_obj in rounds:
        # Access pre-loaded relationships (no additional queries)
        session = round_obj.session
        table = session.table if session else None

        item_outputs = [
            RoundItemOutput(
                id=item.id,
                product_id=item.product_id,
                product_name=item.product.name,
                qty=item.qty,
                unit_price_cents=item.unit_price_cents,
                notes=item.notes,
            )
            for item in round_obj.items
        ]

        result.append(
            RoundOutput(
                id=round_obj.id,
                round_number=round_obj.round_number,
                status=round_obj.status,
                items=item_outputs,
                created_at=round_obj.created_at,
                table_id=table.id if table else None,
                table_code=table.code if table else None,
                submitted_at=round_obj.submitted_at,
            )
        )

    return result


@router.post("/rounds/{round_id}/status", response_model=RoundOutput)
async def update_round_status(
    round_id: int,
    body: UpdateRoundStatusRequest,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> RoundOutput:
    """
    Update the status of a round.

    Valid transitions (role-restricted):
    - PENDING -> IN_KITCHEN (ADMIN/MANAGER only - sends to kitchen)
    - IN_KITCHEN -> READY (KITCHEN only - kitchen finished)
    - READY -> SERVED (ADMIN/MANAGER/WAITER - confirms delivery)

    Publishes corresponding events for real-time updates.
    """
    require_roles(ctx, ["KITCHEN", "WAITER", "MANAGER", "ADMIN"])

    # Find the round with eager loading for items, session, and table
    round_obj = db.scalar(
        select(Round)
        .options(
            selectinload(Round.items).joinedload(RoundItem.product),
            joinedload(Round.session).joinedload(TableSession.table),
        )
        .where(Round.id == round_id)
    )

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

    # Validate status transition
    # PENDING: Round received from diner, waiting for admin/manager to send to kitchen
    # SUBMITTED: Legacy status (kept for backwards compatibility)
    valid_transitions = {
        "PENDING": ["IN_KITCHEN"],     # Admin/Manager sends to kitchen
        "SUBMITTED": ["IN_KITCHEN"],   # Legacy: direct to kitchen
        "IN_KITCHEN": ["READY"],       # Kitchen marks as ready
        "READY": ["SERVED"],           # Admin/Manager/Waiter confirms delivery
    }

    current_status = round_obj.status
    new_status = body.status
    user_roles = ctx.get("roles", [])

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

    # Role-based transition restrictions
    # IN_KITCHEN -> READY: Only KITCHEN can mark as ready
    if current_status == "IN_KITCHEN" and new_status == "READY":
        if "KITCHEN" not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo cocina puede marcar el pedido como listo",
            )

    # PENDING/SUBMITTED -> IN_KITCHEN: Only ADMIN/MANAGER can send to kitchen
    if current_status in ["PENDING", "SUBMITTED"] and new_status == "IN_KITCHEN":
        if not any(role in user_roles for role in ["ADMIN", "MANAGER"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo admin o manager puede enviar pedidos a cocina",
            )

    # Update status
    # ROUTER-HIGH-02 FIX: Add error handling for commit
    round_obj.status = new_status
    # HIGH-KITCHEN-01 FIX: Store session/table info before commit since we'll re-query after
    # This avoids the need for db.refresh() which invalidates relationships
    pre_commit_session = round_obj.session
    pre_commit_table = pre_commit_session.table if pre_commit_session else None
    pre_commit_sector_id = pre_commit_table.sector_id if pre_commit_table else None

    try:
        db.commit()
        # Note: Skip db.refresh() - we'll do a single eager-loaded query below for response
    except Exception as e:
        db.rollback()
        logger.error("Failed to update round status", round_id=round_id, new_status=new_status, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update round status - please try again",
        )

    # Use pre-commit session for event publishing (avoids extra query)
    session = pre_commit_session

    # SECTOR-DISPATCH FIX: Get sector_id from table for targeted waiter notifications
    # HIGH-KITCHEN-01 FIX: Use pre-commit data instead of re-querying
    sector_id = pre_commit_sector_id

    # Publish event
    event_type_map = {
        "IN_KITCHEN": ROUND_IN_KITCHEN,
        "READY": ROUND_READY,
        "SERVED": ROUND_SERVED,
    }

    redis = None
    try:
        redis = await get_redis_client()
        await publish_round_event(
            redis_client=redis,
            event_type=event_type_map[new_status],
            tenant_id=round_obj.tenant_id,
            branch_id=round_obj.branch_id,
            table_id=session.table_id if session else None,
            session_id=round_obj.table_session_id,
            round_id=round_obj.id,
            round_number=round_obj.round_number,
            actor_user_id=int(ctx["sub"]),
            actor_role=ctx["roles"][0] if ctx.get("roles") else "UNKNOWN",
            sector_id=sector_id,  # SECTOR-DISPATCH FIX
        )
    except Exception as e:
        logger.error("Failed to publish round status event", round_id=round_id, new_status=new_status, error=str(e))
    # Note: Don't close pooled Redis connection - pool manages lifecycle

    # Build response using pre-loaded relationships (no additional queries)
    # Note: After db.refresh(), relationships need to be re-queried
    # so we do a single efficient query with eager loading
    round_obj = db.scalar(
        select(Round)
        .options(
            selectinload(Round.items).joinedload(RoundItem.product),
            joinedload(Round.session).joinedload(TableSession.table),
        )
        .where(Round.id == round_id)
    )

    session = round_obj.session
    table = session.table if session else None

    item_outputs = [
        RoundItemOutput(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product.name,
            qty=item.qty,
            unit_price_cents=item.unit_price_cents,
            notes=item.notes,
        )
        for item in round_obj.items
    ]

    return RoundOutput(
        id=round_obj.id,
        round_number=round_obj.round_number,
        status=round_obj.status,
        items=item_outputs,
        created_at=round_obj.created_at,
        table_id=table.id if table else None,
        table_code=table.code if table else None,
        submitted_at=round_obj.submitted_at,
    )


@router.get("/rounds/{round_id}", response_model=RoundOutput)
def get_round(
    round_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> RoundOutput:
    """
    Get details of a specific round.
    """
    require_roles(ctx, ["KITCHEN", "WAITER", "MANAGER", "ADMIN"])

    # Eager load items with products, and session with table
    round_obj = db.scalar(
        select(Round)
        .options(
            selectinload(Round.items).joinedload(RoundItem.product),
            joinedload(Round.session).joinedload(TableSession.table),
        )
        .where(Round.id == round_id)
    )

    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Round {round_id} not found",
        )

    branch_ids = ctx.get("branch_ids", [])
    if round_obj.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Access pre-loaded relationships (no additional queries)
    session = round_obj.session
    table = session.table if session else None

    item_outputs = [
        RoundItemOutput(
            id=item.id,
            product_id=item.product_id,
            product_name=item.product.name,
            qty=item.qty,
            unit_price_cents=item.unit_price_cents,
            notes=item.notes,
        )
        for item in round_obj.items
    ]

    return RoundOutput(
        id=round_obj.id,
        round_number=round_obj.round_number,
        status=round_obj.status,
        items=item_outputs,
        created_at=round_obj.created_at,
        table_id=table.id if table else None,
        table_code=table.code if table else None,
        submitted_at=round_obj.submitted_at,
    )
