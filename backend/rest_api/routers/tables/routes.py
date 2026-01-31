"""
Tables router.
Handles table management and session creation.

SECTOR-FILTER FIX: Waiters only see tables in their assigned sectors.
SESSION-DETAIL: Added category_name to RoundItemDetail for Dashboard ordering.
"""

from datetime import datetime, timezone, date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from shared.infrastructure.db import get_db
from shared.security.rate_limit import limiter
from rest_api.models import (
    Branch,
    Table,
    TableSession,
    Round,
    RoundItem,
    ServiceCall,
    Check,
    Diner,
    Product,
    Category,
    WaiterSectorAssignment,
)
from shared.security.auth import (
    current_user_context,
    sign_table_token,
    require_roles,
    require_branch,
)
from shared.utils.schemas import (
    TableCard,
    TableSessionResponse,
    TableSessionDetail,
    RoundDetail,
    RoundItemDetail,
    DinerOutput,
)
from shared.infrastructure.events import (
    get_redis_client,
    publish_table_event,
    TABLE_SESSION_STARTED,
)
from shared.config.logging import rest_api_logger as logger


router = APIRouter(tags=["tables"])


@router.get("/api/waiter/tables", response_model=list[TableCard])
def get_waiter_tables(
    branch_id: int = Query(None, description="Filter by specific branch ID"),
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[TableCard]:
    """
    Get tables for the waiter based on their sector assignments.

    SECTOR-FILTER FIX:
    - ADMIN/MANAGER: See all tables in the branch
    - WAITER: Only see tables in their assigned sectors for today

    If branch_id is provided, returns only tables for that branch
    (must be in user's branch_ids). Otherwise returns tables for ALL user's branches.

    Returns a summary of each table including:
    - Current status
    - Active session ID (if any)
    - Number of open rounds
    - Number of pending service calls
    - Check status (if any)

    Requires WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    user_id = int(ctx.get("sub", 0))
    user_roles = ctx.get("roles", [])
    user_branch_ids = ctx.get("branch_ids", [])
    is_admin_or_manager = "ADMIN" in user_roles or "MANAGER" in user_roles

    # SECTOR-FILTER FIX: Log for debugging
    logger.info(
        "SECTOR-FILTER: get_waiter_tables called",
        branch_id=branch_id,
        user_id=user_id,
        user_branch_ids=user_branch_ids,
        is_admin_or_manager=is_admin_or_manager,
    )

    if not user_branch_ids:
        return []

    # Validate branch access
    if branch_id is not None:
        if branch_id not in user_branch_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"No access to branch {branch_id}",
            )
        target_branch_ids = [branch_id]
    else:
        target_branch_ids = user_branch_ids

    # SECTOR-FILTER FIX: For WAITER role (not ADMIN/MANAGER), filter by assigned sectors
    assigned_sector_ids: list[int] | None = None
    if not is_admin_or_manager:
        today = date.today()
        # Get waiter's sector assignments for today
        assignments = db.execute(
            select(WaiterSectorAssignment.sector_id)
            .where(
                WaiterSectorAssignment.waiter_id == user_id,
                WaiterSectorAssignment.branch_id.in_(target_branch_ids),
                WaiterSectorAssignment.assignment_date == today,
                WaiterSectorAssignment.is_active.is_(True),
            )
        ).scalars().all()
        assigned_sector_ids = list(assignments) if assignments else []

        logger.info(
            "SECTOR-FILTER: Waiter sector assignments for today",
            waiter_id=user_id,
            today=str(today),
            assigned_sector_ids=assigned_sector_ids,
        )

        # If waiter has no sector assignments, return empty list
        if not assigned_sector_ids:
            logger.info(
                "Waiter has no sector assignments for today",
                waiter_id=user_id,
                branch_ids=target_branch_ids,
            )
            return []

    # Build query for tables with eager loading of sector_rel for grouping
    query = (
        select(Table)
        .options(joinedload(Table.sector_rel))
        .where(
            Table.branch_id.in_(target_branch_ids),
            Table.is_active.is_(True),
        )
    )

    # SECTOR-FILTER FIX: If waiter (not admin/manager), filter by assigned sectors
    if assigned_sector_ids is not None:
        query = query.where(Table.sector_id.in_(assigned_sector_ids))

    tables = db.execute(query.order_by(Table.branch_id, Table.code)).scalars().unique().all()

    logger.info("SECTOR-FILTER: Tables found", count=len(tables), is_admin_or_manager=is_admin_or_manager)

    if not tables:
        return []

    # RTR-HIGH-01 FIX: Batch queries to eliminate N+1 pattern
    # Instead of 4 queries per table, we do 4 queries total

    table_ids = [t.id for t in tables]

    # 1. Batch fetch all active sessions for these tables
    sessions_query = db.execute(
        select(TableSession)
        .where(
            TableSession.table_id.in_(table_ids),
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    ).scalars().all()

    # Build lookup: table_id -> session (most recent if multiple)
    session_by_table: dict[int, TableSession] = {}
    for session in sessions_query:
        existing = session_by_table.get(session.table_id)
        if existing is None or session.opened_at > existing.opened_at:
            session_by_table[session.table_id] = session

    active_session_ids = [s.id for s in session_by_table.values()]

    # 2. Batch count open rounds per session
    # QA-FIX: Include PENDING rounds in count (waiters need to see pending orders!)
    # FIX: Include CONFIRMED status - rounds verified by waiter but not yet sent to kitchen
    rounds_count_by_session: dict[int, int] = {}
    if active_session_ids:
        rounds_query = db.execute(
            select(Round.table_session_id, func.count().label("cnt"))
            .where(
                Round.table_session_id.in_(active_session_ids),
                Round.status.in_(["PENDING", "CONFIRMED", "SUBMITTED", "IN_KITCHEN", "READY"]),
                Round.is_active.is_(True),
            )
            .group_by(Round.table_session_id)
        ).all()
        for row in rounds_query:
            rounds_count_by_session[row[0]] = row[1]

    # 3. Batch fetch pending service calls per session (IDs, not just count)
    # This allows the frontend to call resolve on specific call IDs
    calls_by_session: dict[int, list[int]] = {}
    if active_session_ids:
        calls_query = db.execute(
            select(ServiceCall.id, ServiceCall.table_session_id)
            .where(
                ServiceCall.table_session_id.in_(active_session_ids),
                ServiceCall.status == "OPEN",
                ServiceCall.is_active.is_(True),
            )
        ).all()
        for call_id, session_id in calls_query:
            if session_id not in calls_by_session:
                calls_by_session[session_id] = []
            calls_by_session[session_id].append(call_id)

    # 4. Batch fetch most recent check per session
    # RTR-LOW-06 FIX: Added explanatory comments for deduplication strategy
    check_status_by_session: dict[int, str] = {}
    if active_session_ids:
        # Deduplication strategy: Order by session_id and created_at DESC,
        # then iterate and keep only the first (most recent) check per session.
        # This is more efficient than a subquery for small result sets and avoids
        # complex window functions that may not be optimized in all databases.
        checks_query = db.execute(
            select(Check)
            .where(Check.table_session_id.in_(active_session_ids))
            .order_by(Check.table_session_id, Check.created_at.desc())
        ).scalars().all()
        # Keep only the most recent check per session (first seen due to DESC ordering)
        for check in checks_query:
            if check.table_session_id not in check_status_by_session:
                check_status_by_session[check.table_session_id] = check.status

    # Build result using pre-fetched data
    result = []
    for table in tables:
        session = session_by_table.get(table.id)
        session_id = session.id if session else None
        open_rounds = rounds_count_by_session.get(session_id, 0) if session_id else 0
        active_call_ids = calls_by_session.get(session_id, []) if session_id else []
        pending_calls = len(active_call_ids)
        check_status = check_status_by_session.get(session_id) if session_id else None

        result.append(
            TableCard(
                table_id=table.id,
                code=table.code,
                status=table.status,
                session_id=session_id,
                open_rounds=open_rounds,
                pending_calls=pending_calls,
                check_status=check_status,
                active_service_call_ids=active_call_ids,
                sector_id=table.sector_id,
                sector_name=table.sector_rel.name if table.sector_rel else None,
            )
        )

    return result


@router.post("/api/tables/code/{table_code}/session", response_model=TableSessionResponse)
@limiter.limit("30/minute")
async def create_or_get_session_by_code(
    request: Request,
    table_code: str,
    branch_slug: str | None = None,
    db: Session = Depends(get_db),
) -> TableSessionResponse:
    """
    Create a new session for a table by its code, or return the existing active session.

    This endpoint allows diners to join a table using the alphanumeric code
    (e.g., "INT-01", "TER-02") instead of the numeric ID.

    IMPORTANT: Table codes are NOT unique across branches. Each branch can have
    its own "INT-01". The branch_slug parameter is required to identify the
    correct table when multiple branches exist.

    Args:
        table_code: The alphanumeric table code (e.g., "INT-01")
        branch_slug: The branch slug to identify which branch's table (e.g., "suc-centro")
    """
    # Build query for table by code
    query = select(Table).where(
        Table.code == table_code,
        Table.is_active.is_(True),
    )

    # Filter by branch if slug provided
    if branch_slug:
        query = query.join(Branch, Table.branch_id == Branch.id).where(
            Branch.slug == branch_slug,
            Branch.is_active.is_(True),
        )

    table = db.scalar(query)

    if not table:
        detail = f"Table with code '{table_code}' not found"
        if branch_slug:
            detail += f" in branch '{branch_slug}'"
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=detail,
        )

    # Delegate to the ID-based endpoint logic
    return await create_or_get_session(request, table.id, db)


@router.post("/api/tables/{table_id}/session", response_model=TableSessionResponse)
@limiter.limit("30/minute")
async def create_or_get_session(
    request: Request,
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
    # CRIT-RACE-01 FIX: Use SELECT FOR UPDATE to prevent race condition
    # when multiple diners scan QR simultaneously
    table = db.scalar(
        select(Table)
        .where(
            Table.id == table_id,
            Table.is_active.is_(True),
        )
        .with_for_update()  # Lock the row until transaction completes
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

    # Check for existing active session (also with lock to be safe)
    existing_session = db.scalar(
        select(TableSession)
        .where(
            TableSession.table_id == table.id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
        .order_by(TableSession.opened_at.desc())
        .with_for_update()  # Lock existing session row if found
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
    # HIGH-EVENT-01 FIX: Include sector_id for sector-based waiter notifications
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
            sector_id=table.sector_id,  # HIGH-EVENT-01 FIX: Include sector for waiter routing
        )
        logger.info("TABLE_SESSION_STARTED published", table_id=table.id, session_id=new_session.id, sector_id=table.sector_id)
    except Exception as e:
        # Log but don't fail the request
        logger.error("Failed to publish TABLE_SESSION_STARTED", table_id=table.id, error=str(e))
    # Note: Don't close pooled Redis connection - pool manages lifecycle

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

        # ROUTER-HIGH-06 FIX: Added is_active filter
        # FIX: Include PENDING and CONFIRMED status - all rounds not yet served
        open_rounds = db.scalar(
            select(func.count())
            .select_from(Round)
            .where(
                Round.table_session_id == active_session.id,
                Round.status.in_(["PENDING", "CONFIRMED", "SUBMITTED", "IN_KITCHEN", "READY"]),
                Round.is_active.is_(True),
            )
        ) or 0

        # ROUTER-HIGH-06 FIX: Added is_active filter
        pending_calls = db.scalar(
            select(func.count())
            .select_from(ServiceCall)
            .where(
                ServiceCall.table_session_id == active_session.id,
                ServiceCall.status == "OPEN",
                ServiceCall.is_active.is_(True),
            )
        ) or 0

        check = db.scalar(
            select(Check)
            .where(Check.table_session_id == active_session.id, Check.is_active.is_(True))
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
        # Get items for this round with product names and category names
        items = db.execute(
            select(RoundItem, Product.name, Category.name)
            .join(Product, RoundItem.product_id == Product.id)
            .join(Category, Product.category_id == Category.id)
            .where(RoundItem.round_id == round_obj.id)
            .order_by(RoundItem.id)
        ).all()

        items_output = []
        for item, product_name, category_name in items:
            diner = diner_map.get(item.diner_id) if item.diner_id else None
            items_output.append(
                RoundItemDetail(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=product_name,
                    category_name=category_name,
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
