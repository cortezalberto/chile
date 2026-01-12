"""
Tables router.
Handles table management and session creation.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from rest_api.db import get_db
from rest_api.models import (
    Table,
    TableSession,
    Round,
    RoundItem,
    ServiceCall,
    Check,
    Diner,
    Product,
)
from shared.auth import (
    current_user_context,
    sign_table_token,
    require_roles,
    require_branch,
)
from shared.schemas import (
    TableCard,
    TableSessionResponse,
    TableSessionDetail,
    RoundDetail,
    RoundItemDetail,
    DinerOutput,
)
from shared.events import (
    get_redis_client,
    publish_table_event,
    TABLE_SESSION_STARTED,
)
from shared.logging import rest_api_logger as logger


router = APIRouter(tags=["tables"])


@router.get("/api/waiter/tables", response_model=list[TableCard])
def get_waiter_tables(
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[TableCard]:
    """
    Get all tables for the waiter's branch(es).

    Returns a summary of each table including:
    - Current status
    - Active session ID (if any)
    - Number of open rounds
    - Number of pending service calls
    - Check status (if any)

    Requires WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    branch_ids = ctx.get("branch_ids", [])
    if not branch_ids:
        return []

    # Get all tables for user's branches
    tables = db.execute(
        select(Table)
        .where(
            Table.branch_id.in_(branch_ids),
            Table.is_active == True,
        )
        .order_by(Table.branch_id, Table.code)
    ).scalars().all()

    result = []

    for table in tables:
        # Find active session for this table
        active_session = db.scalar(
            select(TableSession)
            .where(
                TableSession.table_id == table.id,
                TableSession.status.in_(["OPEN", "PAYING"]),
            )
            .order_by(TableSession.opened_at.desc())
        )

        session_id = None
        open_rounds = 0
        pending_calls = 0
        check_status = None

        if active_session:
            session_id = active_session.id

            # Count open rounds (not SERVED or CANCELED)
            open_rounds = db.scalar(
                select(func.count())
                .select_from(Round)
                .where(
                    Round.table_session_id == active_session.id,
                    Round.status.in_(["SUBMITTED", "IN_KITCHEN", "READY"]),
                )
            ) or 0

            # Count pending service calls
            pending_calls = db.scalar(
                select(func.count())
                .select_from(ServiceCall)
                .where(
                    ServiceCall.table_session_id == active_session.id,
                    ServiceCall.status == "OPEN",
                )
            ) or 0

            # Get check status if exists
            check = db.scalar(
                select(Check)
                .where(Check.table_session_id == active_session.id)
                .order_by(Check.created_at.desc())
            )
            if check:
                check_status = check.status

        result.append(
            TableCard(
                table_id=table.id,
                code=table.code,
                status=table.status,
                session_id=session_id,
                open_rounds=open_rounds,
                pending_calls=pending_calls,
                check_status=check_status,
            )
        )

    return result


@router.post("/api/tables/{table_id}/session", response_model=TableSessionResponse)
async def create_or_get_session(
    table_id: int,
    db: Session = Depends(get_db),
) -> TableSessionResponse:
    """
    Create a new session for a table, or return the existing active session.

    This endpoint is called when a diner scans a QR code or enters a table number.
    It does not require authentication - the response includes a table token
    that will be used for subsequent diner operations.

    If the table already has an active session, returns that session.
    Otherwise, creates a new session and marks the table as ACTIVE.
    """
    # Find the table
    table = db.scalar(
        select(Table).where(
            Table.id == table_id,
            Table.is_active == True,
        )
    )

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table {table_id} not found",
        )

    if table.status == "OUT_OF_SERVICE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table is out of service",
        )

    # Check for existing active session
    existing_session = db.scalar(
        select(TableSession)
        .where(
            TableSession.table_id == table.id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
        .order_by(TableSession.opened_at.desc())
    )

    if existing_session:
        # Return existing session with new token
        token = sign_table_token(
            tenant_id=existing_session.tenant_id,
            branch_id=existing_session.branch_id,
            table_id=table.id,
            session_id=existing_session.id,
        )
        return TableSessionResponse(
            session_id=existing_session.id,
            table_id=table.id,
            table_code=table.code,
            table_token=token,
            status=existing_session.status,
        )

    # Create new session
    new_session = TableSession(
        tenant_id=table.tenant_id,
        branch_id=table.branch_id,
        table_id=table.id,
        status="OPEN",
    )
    db.add(new_session)

    # Update table status
    table.status = "ACTIVE"

    db.commit()
    db.refresh(new_session)

    # Generate table token
    token = sign_table_token(
        tenant_id=new_session.tenant_id,
        branch_id=new_session.branch_id,
        table_id=table.id,
        session_id=new_session.id,
    )

    # PWAW-C002: Publish TABLE_SESSION_STARTED event for waiters
    redis = None
    try:
        redis = await get_redis_client()
        await publish_table_event(
            redis_client=redis,
            event_type=TABLE_SESSION_STARTED,
            tenant_id=new_session.tenant_id,
            branch_id=new_session.branch_id,
            table_id=table.id,
            table_code=table.code,
            session_id=new_session.id,
        )
        logger.info("TABLE_SESSION_STARTED published", table_id=table.id, session_id=new_session.id)
    except Exception as e:
        # Log but don't fail the request
        logger.error("Failed to publish TABLE_SESSION_STARTED", table_id=table.id, error=str(e))
    finally:
        if redis:
            await redis.close()

    return TableSessionResponse(
        session_id=new_session.id,
        table_id=table.id,
        table_code=table.code,
        table_token=token,
        status=new_session.status,
    )


@router.get("/api/tables/{table_id}", response_model=TableCard)
def get_table(
    table_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> TableCard:
    """
    Get details of a specific table.

    Requires authentication and access to the table's branch.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    table = db.scalar(
        select(Table).where(Table.id == table_id)
    )

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table {table_id} not found",
        )

    require_branch(ctx, table.branch_id)

    # Find active session
    active_session = db.scalar(
        select(TableSession)
        .where(
            TableSession.table_id == table.id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
        .order_by(TableSession.opened_at.desc())
    )

    session_id = None
    open_rounds = 0
    pending_calls = 0
    check_status = None

    if active_session:
        session_id = active_session.id

        open_rounds = db.scalar(
            select(func.count())
            .select_from(Round)
            .where(
                Round.table_session_id == active_session.id,
                Round.status.in_(["SUBMITTED", "IN_KITCHEN", "READY"]),
            )
        ) or 0

        pending_calls = db.scalar(
            select(func.count())
            .select_from(ServiceCall)
            .where(
                ServiceCall.table_session_id == active_session.id,
                ServiceCall.status == "OPEN",
            )
        ) or 0

        check = db.scalar(
            select(Check)
            .where(Check.table_session_id == active_session.id)
            .order_by(Check.created_at.desc())
        )
        if check:
            check_status = check.status

    return TableCard(
        table_id=table.id,
        code=table.code,
        status=table.status,
        session_id=session_id,
        open_rounds=open_rounds,
        pending_calls=pending_calls,
        check_status=check_status,
    )


@router.get("/api/waiter/tables/{table_id}/session", response_model=TableSessionDetail)
def get_table_session_detail(
    table_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> TableSessionDetail:
    """
    Get detailed session information for a table.

    Returns the active session with:
    - All diners
    - All rounds with items (including diner info per item)
    - Check status and totals

    Requires WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    # Find the table
    table = db.scalar(select(Table).where(Table.id == table_id))

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table {table_id} not found",
        )

    require_branch(ctx, table.branch_id)

    # Find active session
    session = db.scalar(
        select(TableSession)
        .where(
            TableSession.table_id == table.id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
        .order_by(TableSession.opened_at.desc())
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active session for table {table_id}",
        )

    # Get diners
    diners = db.execute(
        select(Diner)
        .where(Diner.session_id == session.id)
        .order_by(Diner.joined_at)
    ).scalars().all()

    diner_map = {d.id: d for d in diners}

    diners_output = [
        DinerOutput(
            id=d.id,
            session_id=d.session_id,
            name=d.name,
            color=d.color,
            local_id=d.local_id,
            joined_at=d.joined_at,
        )
        for d in diners
    ]

    # Get rounds with items
    rounds = db.execute(
        select(Round)
        .where(
            Round.table_session_id == session.id,
            Round.status != "DRAFT",  # Only submitted rounds
        )
        .order_by(Round.round_number)
    ).scalars().all()

    rounds_output = []
    for round_obj in rounds:
        # Get items for this round with product names
        items = db.execute(
            select(RoundItem, Product.name)
            .join(Product, RoundItem.product_id == Product.id)
            .where(RoundItem.round_id == round_obj.id)
            .order_by(RoundItem.id)
        ).all()

        items_output = []
        for item, product_name in items:
            diner = diner_map.get(item.diner_id) if item.diner_id else None
            items_output.append(
                RoundItemDetail(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=product_name,
                    qty=item.qty,
                    unit_price_cents=item.unit_price_cents,
                    notes=item.notes,
                    diner_id=item.diner_id,
                    diner_name=diner.name if diner else None,
                    diner_color=diner.color if diner else None,
                )
            )

        rounds_output.append(
            RoundDetail(
                id=round_obj.id,
                round_number=round_obj.round_number,
                status=round_obj.status,
                created_at=round_obj.created_at,
                submitted_at=round_obj.submitted_at,
                items=items_output,
            )
        )

    # Get check info
    check = db.scalar(
        select(Check)
        .where(Check.table_session_id == session.id)
        .order_by(Check.created_at.desc())
    )

    check_status = check.status if check else None
    total_cents = check.total_cents if check else 0
    paid_cents = check.paid_cents if check else 0

    # If no check yet, calculate total from rounds
    if not check:
        total_cents = db.scalar(
            select(func.sum(RoundItem.unit_price_cents * RoundItem.qty))
            .join(Round, RoundItem.round_id == Round.id)
            .where(
                Round.table_session_id == session.id,
                Round.status != "CANCELED",
            )
        ) or 0

    return TableSessionDetail(
        session_id=session.id,
        table_id=table.id,
        table_code=table.code,
        status=session.status,
        opened_at=session.opened_at,
        diners=diners_output,
        rounds=rounds_output,
        check_status=check_status,
        total_cents=total_cents,
        paid_cents=paid_cents,
    )
