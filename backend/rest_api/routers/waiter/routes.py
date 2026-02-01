"""
Waiter router.
Handles operations performed by waiters.
PWAW-C001: Service call acknowledge/resolve endpoints.
HU-WAITER-MESA: Waiter-managed table flow (activate, order, payment, close).
"""

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy import select, or_, func


# RTR-MED-05 FIX: Enum for valid shift values
class ShiftType(str, Enum):
    """Valid shift types for waiter assignments."""
    MORNING = "MORNING"
    AFTERNOON = "AFTERNOON"
    NIGHT = "NIGHT"

from shared.infrastructure.db import get_db, safe_commit
from rest_api.models import (
    Allergen,  # RTR-LOW-05 FIX: Moved from inline import
    Branch,
    BranchProduct,
    BranchSector,
    Category,  # RTR-LOW-05 FIX: Moved from inline import
    Check,
    Diner,
    Payment,
    Product,
    ProductAllergen,  # RTR-LOW-05 FIX: Moved from inline import
    Round,
    RoundItem,
    ServiceCall,
    Subcategory,  # RTR-LOW-05 FIX: Moved from inline import
    Table,
    TableSession,
    WaiterSectorAssignment,
)
from shared.security.auth import current_user_context, require_roles
from shared.utils.schemas import (
    ServiceCallOutput,
    WaiterActivateTableRequest,
    WaiterActivateTableResponse,
    WaiterSubmitRoundRequest,
    WaiterSubmitRoundResponse,
    WaiterRequestCheckResponse,
    ManualPaymentRequest,
    ManualPaymentResponse,
    WaiterCloseTableRequest,
    WaiterCloseTableResponse,
    WaiterSessionSummaryOutput,
)
from shared.config.logging import waiter_logger as logger
from shared.infrastructure.events import (
    get_redis_client,
    publish_service_call_event,
    publish_round_event,
    publish_check_event,
    publish_table_event,
    SERVICE_CALL_ACKED,
    SERVICE_CALL_CLOSED,
    ROUND_SUBMITTED,
    CHECK_REQUESTED,
    PAYMENT_APPROVED,
    CHECK_PAID,
    TABLE_SESSION_STARTED,
    TABLE_CLEARED,
)
from rest_api.services.payments.allocation import allocate_payment_fifo


# =============================================================================
# Schemas
# =============================================================================


class SectorAssignmentOutput(BaseModel):
    """Output schema for a sector assignment."""
    sector_id: int
    sector_name: str
    sector_prefix: str
    branch_id: int
    assignment_date: date
    shift: Optional[str] = None


class MyAssignmentsOutput(BaseModel):
    """Output schema for waiter's current assignments."""
    waiter_id: int
    assignment_date: date
    sectors: list[SectorAssignmentOutput]
    sector_ids: list[int]  # Convenience list for filtering


router = APIRouter(prefix="/api/waiter", tags=["waiter"])


# =============================================================================
# Service Calls
# =============================================================================


@router.get("/service-calls", response_model=list[ServiceCallOutput])
def get_pending_service_calls(
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[ServiceCallOutput]:
    """
    Get all pending service calls for the waiter's branches.

    Returns service calls with status OPEN or ACKED.
    PWAW-A003: List endpoint for service calls.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    branch_ids = ctx.get("branch_ids", [])
    if not branch_ids:
        return []

    # Get pending service calls with eager loading to avoid N+1 queries
    # - joinedload for session->table chain (many-to-one relationships)
    # QA-BACK-HIGH-01 FIX: Added is_active filter for soft delete compatibility
    calls = db.execute(
        select(ServiceCall)
        .options(
            joinedload(ServiceCall.session).joinedload(TableSession.table),
        )
        .where(
            ServiceCall.branch_id.in_(branch_ids),
            ServiceCall.status.in_(["OPEN", "ACKED"]),
            ServiceCall.is_active.is_(True),
        )
        .order_by(ServiceCall.created_at.asc())
    ).scalars().unique().all()

    result = []
    for call in calls:
        # Access pre-loaded relationships (no additional queries)
        session = call.session
        table = session.table if session else None

        result.append(
            ServiceCallOutput(
                id=call.id,
                type=call.type,
                status=call.status,
                created_at=call.created_at,
                acked_at=call.acked_at if hasattr(call, 'acked_at') else None,
                acked_by_user_id=call.acked_by_user_id,
                table_id=table.id if table else None,
                table_code=table.code if table else None,
                session_id=call.table_session_id,
            )
        )

    return result


@router.post("/service-calls/{call_id}/acknowledge", response_model=ServiceCallOutput)
async def acknowledge_service_call(
    call_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ServiceCallOutput:
    """
    Acknowledge a service call.

    Changes status from OPEN to ACKED, indicating waiter is aware
    and will attend to the table.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    # Find the service call with eager loading for session and table
    # QA-BACK-HIGH-01 FIX: Added is_active filter for soft delete compatibility
    call = db.scalar(
        select(ServiceCall)
        .options(
            joinedload(ServiceCall.session).joinedload(TableSession.table),
        )
        .where(
            ServiceCall.id == call_id,
            ServiceCall.is_active.is_(True),
        )
    )

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service call {call_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if call.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Verify status
    if call.status != "OPEN":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot acknowledge call with status {call.status}",
        )

    # Update status
    user_id = int(ctx["sub"])
    # ROUTER-HIGH-07 FIX: Use getattr with default for safe attribute access
    call.status = "ACKED"
    call.acked_by_user_id = user_id
    # Set acked_at if the attribute exists (uses AuditMixin pattern)
    try:
        call.acked_at = datetime.now(timezone.utc)
    except AttributeError:
        pass  # Model doesn't have acked_at field

    db.commit()
    db.refresh(call)

    # Access pre-loaded relationships (no additional queries)
    session = call.session
    table = session.table if session else None

    # SECTOR-DISPATCH FIX: Get sector_id for targeted notifications
    sector_id = table.sector_id if table else None

    # Publish event
    redis = None
    try:
        redis = await get_redis_client()
        await publish_service_call_event(
            redis_client=redis,
            event_type=SERVICE_CALL_ACKED,
            tenant_id=call.tenant_id,
            branch_id=call.branch_id,
            table_id=table.id if table else 0,
            session_id=call.table_session_id,
            call_id=call.id,
            call_type=call.type,
            actor_user_id=user_id,
            actor_role="WAITER",
            sector_id=sector_id,  # SECTOR-DISPATCH FIX
        )
        logger.info("Service call acknowledged", call_id=call_id, user_id=user_id, sector_id=sector_id)
    except Exception as e:
        logger.error("Failed to publish SERVICE_CALL_ACKED event", call_id=call_id, error=str(e))
    # Note: Don't close pooled Redis connection - pool manages lifecycle

    return ServiceCallOutput(
        id=call.id,
        type=call.type,
        status=call.status,
        created_at=call.created_at,
        acked_at=call.acked_at if hasattr(call, 'acked_at') else None,
        acked_by_user_id=call.acked_by_user_id,
        table_id=table.id if table else None,
        table_code=table.code if table else None,
        session_id=call.table_session_id,
    )


@router.post("/service-calls/{call_id}/resolve", response_model=ServiceCallOutput)
async def resolve_service_call(
    call_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ServiceCallOutput:
    """
    Resolve a service call.

    Changes status to CLOSED, indicating the request has been fulfilled.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    # Find the service call with eager loading for session and table
    # QA-BACK-HIGH-01 FIX: Added is_active filter for soft delete compatibility
    call = db.scalar(
        select(ServiceCall)
        .options(
            joinedload(ServiceCall.session).joinedload(TableSession.table),
        )
        .where(
            ServiceCall.id == call_id,
            ServiceCall.is_active.is_(True),
        )
    )

    if not call:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service call {call_id} not found",
        )

    # Verify branch access
    branch_ids = ctx.get("branch_ids", [])
    if call.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Verify status (can resolve from OPEN or ACKED)
    if call.status not in ["OPEN", "ACKED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot resolve call with status {call.status}",
        )

    # Update status
    # ROUTER-HIGH-07 FIX: Use try-except for safe attribute access
    user_id = int(ctx["sub"])
    call.status = "CLOSED"
    try:
        call.resolved_at = datetime.now(timezone.utc)
    except AttributeError:
        pass
    try:
        call.resolved_by_user_id = user_id
    except AttributeError:
        pass

    db.commit()
    db.refresh(call)

    # Access pre-loaded relationships (no additional queries)
    session = call.session
    table = session.table if session else None

    # SECTOR-DISPATCH FIX: Get sector_id for targeted notifications
    sector_id = table.sector_id if table else None

    # Publish event
    redis = None
    try:
        redis = await get_redis_client()
        await publish_service_call_event(
            redis_client=redis,
            event_type=SERVICE_CALL_CLOSED,
            tenant_id=call.tenant_id,
            branch_id=call.branch_id,
            table_id=table.id if table else 0,
            session_id=call.table_session_id,
            call_id=call.id,
            call_type=call.type,
            actor_user_id=user_id,
            actor_role="WAITER",
            sector_id=sector_id,  # SECTOR-DISPATCH FIX
        )
        logger.info("Service call resolved", call_id=call_id, user_id=user_id, sector_id=sector_id)
    except Exception as e:
        logger.error("Failed to publish SERVICE_CALL_CLOSED event", call_id=call_id, error=str(e))
    # Note: Don't close pooled Redis connection - pool manages lifecycle

    return ServiceCallOutput(
        id=call.id,
        type=call.type,
        status=call.status,
        created_at=call.created_at,
        acked_at=call.acked_at if hasattr(call, 'acked_at') else None,
        acked_by_user_id=call.acked_by_user_id,
        table_id=table.id if table else None,
        table_code=table.code if table else None,
        session_id=call.table_session_id,
    )


# =============================================================================
# Sector Assignments
# =============================================================================


@router.get("/my-assignments", response_model=MyAssignmentsOutput)
def get_my_sector_assignments(
    assignment_date: date = Query(default=None, description="Date for assignments (defaults to today)"),
    # RTR-MED-05 FIX: Use ShiftType enum for validation instead of any string
    shift: ShiftType | None = Query(default=None, description="Filter by shift: MORNING, AFTERNOON, NIGHT"),
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> MyAssignmentsOutput:
    """
    Get the current waiter's sector assignments for today (or specified date).

    Returns all sectors the waiter is assigned to, along with their IDs
    for use in WebSocket filtering.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    target_date = assignment_date or date.today()

    # Query assignments for this waiter on this date
    query = (
        select(WaiterSectorAssignment)
        .options(joinedload(WaiterSectorAssignment.sector))
        .where(
            WaiterSectorAssignment.waiter_id == waiter_id,
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.assignment_date == target_date,
            WaiterSectorAssignment.is_active.is_(True),
        )
    )

    if shift:
        # Include assignments for specific shift OR all-day (NULL shift)
        # RTR-MED-05 FIX: Use .value to extract string from enum
        query = query.where(
            or_(
                WaiterSectorAssignment.shift == shift.value,
                WaiterSectorAssignment.shift.is_(None),
            )
        )

    assignments = db.execute(query).scalars().unique().all()

    sectors = []
    sector_ids = []

    for assignment in assignments:
        sector = assignment.sector
        if sector and sector.is_active:
            sectors.append(
                SectorAssignmentOutput(
                    sector_id=sector.id,
                    sector_name=sector.name,
                    sector_prefix=sector.prefix,
                    branch_id=assignment.branch_id,
                    assignment_date=assignment.assignment_date,
                    shift=assignment.shift,
                )
            )
            if sector.id not in sector_ids:
                sector_ids.append(sector.id)

    return MyAssignmentsOutput(
        waiter_id=waiter_id,
        assignment_date=target_date,
        sectors=sectors,
        sector_ids=sector_ids,
    )


class BranchAssignmentVerifyOutput(BaseModel):
    """Output for branch assignment verification."""
    is_assigned: bool
    branch_id: int
    branch_name: str | None = None
    assignment_date: date
    sectors: list[SectorAssignmentOutput] = []
    message: str


@router.get("/verify-branch-assignment", response_model=BranchAssignmentVerifyOutput)
def verify_branch_assignment(
    branch_id: int = Query(..., description="Branch ID to verify assignment for"),
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> BranchAssignmentVerifyOutput:
    """
    Verify if the current waiter is assigned to work at a specific branch today.

    Returns whether the waiter has any sector assignments for today at the given branch.
    Used by pwaWaiter to validate branch selection before showing tables.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    user_branch_ids = ctx.get("branch_ids", [])
    today = date.today()

    # First check if user has access to this branch at all
    if branch_id not in user_branch_ids:
        return BranchAssignmentVerifyOutput(
            is_assigned=False,
            branch_id=branch_id,
            branch_name=None,
            assignment_date=today,
            sectors=[],
            message="No tienes acceso a esta sucursal",
        )

    # Get branch name
    branch = db.scalar(select(Branch).where(Branch.id == branch_id))
    branch_name = branch.name if branch else None

    # Query assignments for this waiter at this branch today
    assignments = db.execute(
        select(WaiterSectorAssignment)
        .options(joinedload(WaiterSectorAssignment.sector))
        .where(
            WaiterSectorAssignment.waiter_id == waiter_id,
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.branch_id == branch_id,
            WaiterSectorAssignment.assignment_date == today,
            WaiterSectorAssignment.is_active.is_(True),
        )
    ).scalars().unique().all()

    if not assignments:
        return BranchAssignmentVerifyOutput(
            is_assigned=False,
            branch_id=branch_id,
            branch_name=branch_name,
            assignment_date=today,
            sectors=[],
            message=f"No estás asignado a {branch_name or 'esta sucursal'} hoy",
        )

    # Build sector list
    sectors = []
    for assignment in assignments:
        sector = assignment.sector
        if sector and sector.is_active:
            sectors.append(
                SectorAssignmentOutput(
                    sector_id=sector.id,
                    sector_name=sector.name,
                    sector_prefix=sector.prefix,
                    branch_id=branch_id,
                    assignment_date=today,
                    shift=assignment.shift,
                )
            )

    return BranchAssignmentVerifyOutput(
        is_assigned=True,
        branch_id=branch_id,
        branch_name=branch_name,
        assignment_date=today,
        sectors=sectors,
        message=f"Asignado a {branch_name} - {len(sectors)} sector(es)",
    )


@router.get("/my-tables", response_model=list[dict])
def get_my_assigned_tables(
    assignment_date: date = Query(default=None, description="Date for assignments (defaults to today)"),
    shift: Optional[str] = Query(default=None, description="Filter by shift"),
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> list[dict]:
    """
    Get all tables in the sectors the waiter is assigned to.

    Useful for filtering which tables to show in the waiter's UI.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])
    target_date = assignment_date or date.today()

    # Get assigned sector IDs
    query = (
        select(WaiterSectorAssignment.sector_id)
        .where(
            WaiterSectorAssignment.waiter_id == waiter_id,
            WaiterSectorAssignment.tenant_id == tenant_id,
            WaiterSectorAssignment.assignment_date == target_date,
            WaiterSectorAssignment.is_active.is_(True),
        )
    )

    if shift:
        query = query.where(
            or_(
                WaiterSectorAssignment.shift == shift,
                WaiterSectorAssignment.shift.is_(None),
            )
        )

    sector_ids = db.execute(query).scalars().all()

    if not sector_ids:
        # No assignments - return all tables in branches (fallback behavior)
        tables = db.execute(
            select(Table)
            .where(
                Table.branch_id.in_(branch_ids),
                Table.is_active.is_(True),
            )
            .order_by(Table.branch_id, Table.code)
        ).scalars().all()
    else:
        # Return only tables in assigned sectors
        tables = db.execute(
            select(Table)
            .options(joinedload(Table.sector_rel))
            .where(
                Table.sector_id.in_(sector_ids),
                Table.is_active.is_(True),
            )
            .order_by(Table.branch_id, Table.code)
        ).scalars().unique().all()

    return [
        {
            "id": t.id,
            "code": t.code,
            "capacity": t.capacity,
            "status": t.status,
            "branch_id": t.branch_id,
            "sector_id": t.sector_id,
            "sector_name": t.sector_rel.name if t.sector_rel else t.sector,
        }
        for t in tables
    ]


# =============================================================================
# Waiter-Managed Table Flow (HU-WAITER-MESA)
# =============================================================================


@router.post("/tables/{table_id}/activate", response_model=WaiterActivateTableResponse)
async def activate_table(
    table_id: int,
    body: WaiterActivateTableRequest,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> WaiterActivateTableResponse:
    """
    HU-WAITER-MESA CA-01: Waiter manually activates a table.

    This creates a new table session with opened_by="WAITER" to track
    that this is a waiter-managed flow (no pwaMenu usage by customers).
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Find the table
    table = db.scalar(
        select(Table)
        .where(
            Table.id == table_id,
            Table.tenant_id == tenant_id,
            Table.is_active.is_(True),
        )
    )

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table {table_id} not found",
        )

    # Verify branch access
    if table.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Check if table is already occupied
    if table.status != "FREE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table is already {table.status}. Cannot activate.",
        )

    # Check for existing open session (defensive)
    existing_session = db.scalar(
        select(TableSession)
        .where(
            TableSession.table_id == table_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )
    if existing_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table already has an active session (ID: {existing_session.id})",
        )

    # Create new session with waiter traceability
    now = datetime.now(timezone.utc)
    session = TableSession(
        tenant_id=tenant_id,
        branch_id=table.branch_id,
        table_id=table.id,
        status="OPEN",
        assigned_waiter_id=waiter_id,
        opened_at=now,
        opened_by="WAITER",
        opened_by_waiter_id=waiter_id,
    )
    db.add(session)

    # Update table status
    table.status = "ACTIVE"

    safe_commit(db)
    db.refresh(session)
    db.refresh(table)

    # Publish TABLE_SESSION_STARTED event
    try:
        redis = await get_redis_client()
        await publish_table_event(
            redis_client=redis,
            event_type=TABLE_SESSION_STARTED,
            tenant_id=tenant_id,
            branch_id=table.branch_id,
            table_id=table.id,
            session_id=session.id,
            table_code=table.code,
            table_status=table.status,
            actor_user_id=waiter_id,
            actor_role="WAITER",
            sector_id=table.sector_id,
        )
        logger.info("Table activated by waiter", table_id=table_id, session_id=session.id, waiter_id=waiter_id)
    except Exception as e:
        logger.error("Failed to publish TABLE_SESSION_STARTED event", error=str(e))

    return WaiterActivateTableResponse(
        session_id=session.id,
        table_id=table.id,
        table_code=table.code,
        status=session.status,
        opened_at=session.opened_at,
        opened_by=session.opened_by,
        opened_by_waiter_id=waiter_id,
        diner_count=body.diner_count,
    )


@router.post("/sessions/{session_id}/rounds", response_model=WaiterSubmitRoundResponse)
async def submit_round_for_session(
    session_id: int,
    body: WaiterSubmitRoundRequest,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> WaiterSubmitRoundResponse:
    """
    HU-WAITER-MESA CA-03: Waiter submits a round of orders for a session.

    This creates a new round with submitted_by="WAITER" to track that
    the order was taken verbally by the waiter (not via pwaMenu).
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Find the session with table info using SELECT FOR UPDATE to prevent race conditions
    session = db.scalar(
        select(TableSession)
        .options(joinedload(TableSession.table))
        .where(
            TableSession.id == session_id,
            TableSession.tenant_id == tenant_id,
            TableSession.status == "OPEN",
        )
        .with_for_update()
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active session {session_id} not found",
        )

    # Verify branch access
    if session.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Validate products and get pricing - batch query to avoid N+1
    product_ids = [item.product_id for item in body.items]
    products_query = db.execute(
        select(Product, BranchProduct)
        .join(BranchProduct, Product.id == BranchProduct.product_id)
        .where(
            Product.id.in_(product_ids),
            Product.tenant_id == tenant_id,
            Product.is_active.is_(True),
            BranchProduct.branch_id == session.branch_id,
        )
    ).all()

    product_lookup = {p.id: (p, bp) for p, bp in products_query}

    # Validate all products exist and are available
    for item in body.items:
        if item.product_id not in product_lookup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {item.product_id} not available at this branch",
            )

    # Calculate next round number
    max_round = db.scalar(
        select(func.max(Round.round_number))
        .where(Round.table_session_id == session_id)
    ) or 0
    next_round_number = max_round + 1

    # Create the round with waiter traceability
    # Status is PENDING - admin/manager must advance to send to kitchen
    now = datetime.now(timezone.utc)
    new_round = Round(
        tenant_id=tenant_id,
        branch_id=session.branch_id,
        table_session_id=session_id,
        round_number=next_round_number,
        status="PENDING",  # Changed from SUBMITTED - admin must advance to send to kitchen
        submitted_at=now,
        submitted_by="WAITER",
        submitted_by_waiter_id=waiter_id,
    )
    db.add(new_round)
    db.flush()  # Get round ID

    # Create round items in batch
    total_cents = 0
    round_items = []
    for item in body.items:
        product, branch_product = product_lookup[item.product_id]
        unit_price = branch_product.price_cents

        round_item = RoundItem(
            tenant_id=tenant_id,
            round_id=new_round.id,
            product_id=item.product_id,
            qty=item.qty,
            unit_price_cents=unit_price,
            notes=item.notes,
        )
        round_items.append(round_item)
        total_cents += unit_price * item.qty

    db.add_all(round_items)
    safe_commit(db)
    db.refresh(new_round)

    # Publish ROUND_SUBMITTED event
    table = session.table
    try:
        redis = await get_redis_client()
        await publish_round_event(
            redis_client=redis,
            event_type=ROUND_SUBMITTED,
            tenant_id=tenant_id,
            branch_id=session.branch_id,
            table_id=table.id if table else 0,
            session_id=session_id,
            round_id=new_round.id,
            round_number=new_round.round_number,
            actor_user_id=waiter_id,
            actor_role="WAITER",
            sector_id=table.sector_id if table else None,
        )
        logger.info(
            "Round submitted by waiter",
            session_id=session_id,
            round_id=new_round.id,
            waiter_id=waiter_id,
            items_count=len(body.items),
        )
    except Exception as e:
        logger.error("Failed to publish ROUND_SUBMITTED event", error=str(e))

    return WaiterSubmitRoundResponse(
        session_id=session_id,
        round_id=new_round.id,
        round_number=new_round.round_number,
        status=new_round.status,
        submitted_by=new_round.submitted_by,
        submitted_by_waiter_id=waiter_id,
        items_count=len(body.items),
        total_cents=total_cents,
    )


@router.post("/sessions/{session_id}/check", response_model=WaiterRequestCheckResponse)
async def request_check_for_session(
    session_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> WaiterRequestCheckResponse:
    """
    HU-WAITER-MESA CA-05: Waiter requests the check for a session.

    Creates or retrieves the check for the session, aggregating all
    submitted rounds into a single bill.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Find the session with table and rounds
    session = db.scalar(
        select(TableSession)
        .options(
            joinedload(TableSession.table),
            selectinload(TableSession.rounds).selectinload(Round.items),
        )
        .where(
            TableSession.id == session_id,
            TableSession.tenant_id == tenant_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Active session {session_id} not found",
        )

    # Verify branch access
    if session.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Check for existing check
    # QA-BACK-CRIT-02 FIX: Added tenant_id validation for defense in depth
    existing_check = db.scalar(
        select(Check)
        .where(
            Check.table_session_id == session_id,
            Check.tenant_id == tenant_id,
            Check.is_active.is_(True),
        )
    )

    if existing_check:
        # Return existing check info
        items_count = sum(
            item.qty
            for r in session.rounds
            if r.status not in ["DRAFT", "CANCELED"]
            for item in r.items
        )
        return WaiterRequestCheckResponse(
            check_id=existing_check.id,
            session_id=session_id,
            total_cents=existing_check.total_cents,
            paid_cents=existing_check.paid_cents,
            status=existing_check.status,
            items_count=items_count,
        )

    # Calculate total from all submitted rounds
    total_cents = 0
    items_count = 0
    for round_obj in session.rounds:
        if round_obj.status not in ["DRAFT", "CANCELED"]:
            for item in round_obj.items:
                total_cents += item.unit_price_cents * item.qty
                items_count += item.qty

    if total_cents == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No items to bill. Submit at least one round first.",
        )

    # Create the check
    new_check = Check(
        tenant_id=tenant_id,
        branch_id=session.branch_id,
        table_session_id=session_id,
        status="REQUESTED",
        total_cents=total_cents,
        paid_cents=0,
    )
    db.add(new_check)

    # Update session status to PAYING
    session.status = "PAYING"

    safe_commit(db)
    db.refresh(new_check)

    # Publish CHECK_REQUESTED event
    table = session.table
    try:
        redis = await get_redis_client()
        await publish_check_event(
            redis_client=redis,
            event_type=CHECK_REQUESTED,
            tenant_id=tenant_id,
            branch_id=session.branch_id,
            table_id=table.id if table else 0,
            session_id=session_id,
            check_id=new_check.id,
            total_cents=new_check.total_cents,
            paid_cents=0,
            actor_user_id=waiter_id,
            actor_role="WAITER",
            sector_id=table.sector_id if table else None,
        )
        logger.info(
            "Check requested by waiter",
            session_id=session_id,
            check_id=new_check.id,
            total_cents=total_cents,
            waiter_id=waiter_id,
        )
    except Exception as e:
        logger.error("Failed to publish CHECK_REQUESTED event", error=str(e))

    return WaiterRequestCheckResponse(
        check_id=new_check.id,
        session_id=session_id,
        total_cents=new_check.total_cents,
        paid_cents=new_check.paid_cents,
        status=new_check.status,
        items_count=items_count,
    )


@router.post("/payments/manual", response_model=ManualPaymentResponse)
async def register_manual_payment(
    body: ManualPaymentRequest,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> ManualPaymentResponse:
    """
    HU-WAITER-MESA CA-06: Waiter registers a manual payment.

    CRITICAL: This endpoint does NOT integrate with Mercado Pago or any
    digital payment provider. The waiter physically receives the payment
    (cash, physical card, or bank transfer) and registers it in the system.

    The payment is immediately marked as APPROVED since the waiter confirms
    having received it.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Find the check with session info
    check = db.scalar(
        select(Check)
        .options(joinedload(Check.session).joinedload(TableSession.table))
        .where(
            Check.id == body.check_id,
            Check.tenant_id == tenant_id,
            Check.is_active.is_(True),
        )
        .with_for_update()  # Lock to prevent race conditions
    )

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check {body.check_id} not found",
        )

    # Verify branch access
    if check.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Validate check status - can only pay REQUESTED or IN_PAYMENT checks
    if check.status not in ["REQUESTED", "IN_PAYMENT"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot pay check with status {check.status}",
        )

    # Calculate remaining amount
    remaining = check.total_cents - check.paid_cents

    if body.amount_cents > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Payment amount ({body.amount_cents}) exceeds remaining balance ({remaining})",
        )

    # Create the manual payment - immediately APPROVED since waiter confirms receipt
    payment = Payment(
        tenant_id=tenant_id,
        branch_id=check.branch_id,
        check_id=check.id,
        provider="CASH" if body.manual_method == "CASH" else "CARD_PHYSICAL",
        status="APPROVED",
        amount_cents=body.amount_cents,
        payment_category="MANUAL",
        registered_by="WAITER",
        registered_by_waiter_id=waiter_id,
        manual_method=body.manual_method,
        manual_notes=body.notes,
    )
    db.add(payment)

    # Update check paid amount
    check.paid_cents += body.amount_cents

    # Update check status
    if check.paid_cents >= check.total_cents:
        check.status = "PAID"
    else:
        check.status = "IN_PAYMENT"

    safe_commit(db)
    db.refresh(payment)
    db.refresh(check)

    # Allocate payment to charges (FIFO)
    try:
        allocate_payment_fifo(db, payment)
    except Exception as e:
        logger.warning("Payment allocation failed", payment_id=payment.id, error=str(e))

    # Publish payment event
    session = check.session
    table = session.table if session else None
    try:
        redis = await get_redis_client()

        # Always publish PAYMENT_APPROVED
        await publish_check_event(
            redis_client=redis,
            event_type=PAYMENT_APPROVED,
            tenant_id=tenant_id,
            branch_id=check.branch_id,
            table_id=table.id if table else 0,
            session_id=session.id if session else 0,
            check_id=check.id,
            total_cents=check.total_cents,
            paid_cents=check.paid_cents,
            actor_user_id=waiter_id,
            actor_role="WAITER",
            sector_id=table.sector_id if table else None,
        )

        # If fully paid, also publish CHECK_PAID
        if check.status == "PAID":
            await publish_check_event(
                redis_client=redis,
                event_type=CHECK_PAID,
                tenant_id=tenant_id,
                branch_id=check.branch_id,
                table_id=table.id if table else 0,
                session_id=session.id if session else 0,
                check_id=check.id,
                total_cents=check.total_cents,
                paid_cents=check.paid_cents,
                actor_user_id=waiter_id,
                actor_role="WAITER",
                sector_id=table.sector_id if table else None,
            )

        logger.info(
            "Manual payment registered",
            check_id=check.id,
            payment_id=payment.id,
            amount_cents=body.amount_cents,
            method=body.manual_method,
            waiter_id=waiter_id,
            check_status=check.status,
        )
    except Exception as e:
        logger.error("Failed to publish payment event", error=str(e))

    return ManualPaymentResponse(
        payment_id=payment.id,
        check_id=check.id,
        amount_cents=payment.amount_cents,
        manual_method=body.manual_method,
        status=payment.status,
        payment_category=payment.payment_category,
        registered_by=payment.registered_by,
        registered_by_waiter_id=waiter_id,
        check_status=check.status,
        check_total_cents=check.total_cents,
        check_paid_cents=check.paid_cents,
        check_remaining_cents=check.total_cents - check.paid_cents,
    )


@router.post("/tables/{table_id}/close", response_model=WaiterCloseTableResponse)
async def close_table(
    table_id: int,
    body: WaiterCloseTableRequest = WaiterCloseTableRequest(),
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> WaiterCloseTableResponse:
    """
    HU-WAITER-MESA CA-07: Waiter closes a table after payment is complete.

    This closes the session, updates the table status to FREE, and records
    the closure time. Normally requires the check to be fully paid, unless
    force=True (requires ADMIN role).
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])
    user_roles = ctx.get("roles", [])

    # Find the table with active session
    table = db.scalar(
        select(Table)
        .where(
            Table.id == table_id,
            Table.tenant_id == tenant_id,
            Table.is_active.is_(True),
        )
    )

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table {table_id} not found",
        )

    # Verify branch access
    if table.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Find active session
    session = db.scalar(
        select(TableSession)
        .where(
            TableSession.table_id == table_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Table {table_id} has no active session to close",
        )

    # Find check if exists
    # QA-BACK-CRIT-02 FIX: Added tenant_id validation for defense in depth
    check = db.scalar(
        select(Check)
        .where(
            Check.table_session_id == session.id,
            Check.tenant_id == tenant_id,
            Check.is_active.is_(True),
        )
    )

    total_cents = check.total_cents if check else 0
    paid_cents = check.paid_cents if check else 0

    # Validate payment status (unless force close)
    if check and check.status != "PAID" and not body.force:
        remaining = check.total_cents - check.paid_cents
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Check not fully paid. Remaining: {remaining} cents. Use force=true to close anyway (ADMIN only).",
        )

    # Force close requires ADMIN
    if body.force and "ADMIN" not in user_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Force close requires ADMIN role",
        )

    # Close the session
    now = datetime.now(timezone.utc)
    session.status = "CLOSED"
    session.closed_at = now

    # Update table status
    table.status = "FREE"

    safe_commit(db)
    db.refresh(session)
    db.refresh(table)

    # Publish TABLE_CLEARED event
    try:
        redis = await get_redis_client()
        await publish_table_event(
            redis_client=redis,
            event_type=TABLE_CLEARED,
            tenant_id=tenant_id,
            branch_id=table.branch_id,
            table_id=table.id,
            session_id=session.id,
            table_code=table.code,
            table_status=table.status,
            actor_user_id=waiter_id,
            actor_role="WAITER",
            sector_id=table.sector_id,
        )
        logger.info(
            "Table closed by waiter",
            table_id=table_id,
            session_id=session.id,
            waiter_id=waiter_id,
            total_cents=total_cents,
            paid_cents=paid_cents,
        )
    except Exception as e:
        logger.error("Failed to publish TABLE_CLEARED event", error=str(e))

    return WaiterCloseTableResponse(
        table_id=table.id,
        table_code=table.code,
        table_status=table.status,
        session_id=session.id,
        session_status=session.status,
        total_cents=total_cents,
        paid_cents=paid_cents,
        closed_at=now,
    )


# =============================================================================
# Table Session Detail (Dashboard Integration)
# =============================================================================


class RoundItemDetailOutput(BaseModel):
    """Detailed round item info for Dashboard TableSessionModal."""
    id: int
    product_id: int
    product_name: str
    category_name: Optional[str] = None
    qty: int
    unit_price_cents: int
    notes: Optional[str] = None
    diner_id: Optional[int] = None
    diner_name: Optional[str] = None
    diner_color: Optional[str] = None


class RoundDetailOutput(BaseModel):
    """Detailed round info for Dashboard TableSessionModal."""
    id: int
    round_number: int
    status: str
    created_at: datetime
    submitted_at: Optional[datetime] = None
    items: list[RoundItemDetailOutput] = []


class DinerDetailOutput(BaseModel):
    """Diner info for Dashboard TableSessionModal."""
    id: int
    session_id: int
    name: str
    color: str
    local_id: Optional[str] = None
    joined_at: datetime
    device_id: Optional[str] = None


class TableSessionDetailOutput(BaseModel):
    """Complete session detail for Dashboard TableSessionModal."""
    session_id: int
    table_id: int
    table_code: str
    status: str
    opened_at: datetime
    diners: list[DinerDetailOutput] = []
    rounds: list[RoundDetailOutput] = []
    check_status: Optional[str] = None
    total_cents: int = 0
    paid_cents: int = 0


@router.get("/tables/{table_id}/session", response_model=TableSessionDetailOutput)
def get_table_session_detail(
    table_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> TableSessionDetailOutput:
    """
    Get detailed session info for a table (Dashboard TableSessionModal).

    Returns the active session with diners, rounds, and items.
    Used by Dashboard to show session details when clicking on a table.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Find the table
    table = db.scalar(
        select(Table)
        .where(
            Table.id == table_id,
            Table.tenant_id == tenant_id,
            Table.is_active.is_(True),
        )
    )

    if not table:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Table {table_id} not found",
        )

    # Verify branch access
    if table.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Find active session with all related data
    session = db.scalar(
        select(TableSession)
        .options(
            selectinload(TableSession.diners),
            selectinload(TableSession.rounds)
            .selectinload(Round.items)
            .joinedload(RoundItem.product)
            .joinedload(Product.category),
        )
        .where(
            TableSession.table_id == table_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active session for table {table_id}",
        )

    # Get check info if exists
    check = db.scalar(
        select(Check)
        .where(
            Check.table_session_id == session.id,
            Check.tenant_id == tenant_id,
            Check.is_active.is_(True),
        )
    )

    # Build diner lookup for round items
    diner_lookup = {d.id: d for d in (session.diners or [])}

    # Build diners output
    diners_output = [
        DinerDetailOutput(
            id=d.id,
            session_id=d.session_id,
            name=d.name,
            color=d.color or "#666",
            local_id=d.local_id,
            joined_at=d.joined_at,
            device_id=d.device_id,
        )
        for d in (session.diners or [])
    ]

    # Build rounds output with items
    rounds_output = []
    total_cents = 0

    for round_obj in sorted(session.rounds or [], key=lambda r: r.round_number):
        items_output = []
        for item in (round_obj.items or []):
            diner = diner_lookup.get(item.diner_id) if item.diner_id else None
            product = item.product
            category = product.category if product else None

            items_output.append(
                RoundItemDetailOutput(
                    id=item.id,
                    product_id=item.product_id,
                    product_name=product.name if product else "Unknown",
                    category_name=category.name if category else None,
                    qty=item.qty,
                    unit_price_cents=item.unit_price_cents,
                    notes=item.notes,
                    diner_id=item.diner_id,
                    diner_name=diner.name if diner else None,
                    diner_color=diner.color if diner else None,
                )
            )

            # Sum total from non-canceled rounds
            if round_obj.status not in ["DRAFT", "CANCELED"]:
                total_cents += item.unit_price_cents * item.qty

        rounds_output.append(
            RoundDetailOutput(
                id=round_obj.id,
                round_number=round_obj.round_number,
                status=round_obj.status,
                created_at=round_obj.created_at,
                submitted_at=round_obj.submitted_at,
                items=items_output,
            )
        )

    return TableSessionDetailOutput(
        session_id=session.id,
        table_id=table.id,
        table_code=table.code,
        status=session.status,
        opened_at=session.opened_at,
        diners=diners_output,
        rounds=rounds_output,
        check_status=check.status if check else None,
        total_cents=check.total_cents if check else total_cents,
        paid_cents=check.paid_cents if check else 0,
    )


# =============================================================================
# Comanda Rápida - Menu for Waiter
# =============================================================================


class ProductCompactOutput(BaseModel):
    """Compact product info for waiter comanda (no images)."""
    id: int
    name: str
    description: Optional[str] = None
    price_cents: int
    category_id: int
    category_name: str
    subcategory_id: Optional[int] = None
    subcategory_name: Optional[str] = None
    allergen_icons: list[str] = []
    is_available: bool = True


class CategoryCompactOutput(BaseModel):
    """Category with its products for comanda view."""
    id: int
    name: str
    products: list[ProductCompactOutput] = []


class MenuCompactOutput(BaseModel):
    """Compact menu structure for waiter comanda."""
    branch_id: int
    branch_name: str
    categories: list[CategoryCompactOutput] = []
    total_products: int = 0


@router.get("/branches/{branch_id}/menu", response_model=MenuCompactOutput)
def get_branch_menu_compact(
    branch_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> MenuCompactOutput:
    """
    COMANDA RÁPIDA: Get compact menu for a branch.

    Returns products organized by category, without images, optimized for
    quick waiter order entry. Includes allergen icons for quick reference.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Verify branch access
    if branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Get branch info
    branch = db.scalar(
        select(Branch).where(
            Branch.id == branch_id,
            Branch.tenant_id == tenant_id,
            Branch.is_active.is_(True),
        )
    )

    if not branch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Branch {branch_id} not found",
        )

    # Get all categories for this branch's tenant
    # RTR-LOW-05 FIX: Removed inline import - moved to top of file
    categories = db.execute(
        select(Category)
        .where(
            Category.tenant_id == tenant_id,
            Category.is_active.is_(True),
        )
        .order_by(Category.display_order, Category.name)
    ).scalars().all()

    # Get all products with branch pricing in a single query
    products_query = db.execute(
        select(Product, BranchProduct, Subcategory, Category)
        .join(BranchProduct, Product.id == BranchProduct.product_id)
        .outerjoin(Subcategory, Product.subcategory_id == Subcategory.id)
        .join(Category, Product.category_id == Category.id)
        .where(
            Product.tenant_id == tenant_id,
            Product.is_active.is_(True),
            BranchProduct.branch_id == branch_id,
            BranchProduct.is_available == True,
        )
        .order_by(Category.display_order, Category.name, Product.name)
    ).all()

    # Get allergen info for all products in batch
    product_ids = [p.id for p, bp, sc, c in products_query]
    allergen_query = db.execute(
        select(ProductAllergen, Allergen)
        .join(Allergen, ProductAllergen.allergen_id == Allergen.id)
        .where(
            ProductAllergen.product_id.in_(product_ids),
            ProductAllergen.presence_type == "contains",
        )
    ).all() if product_ids else []

    # Build allergen lookup: product_id -> list of icons
    allergen_lookup: dict[int, list[str]] = {}
    for pa, allergen in allergen_query:
        if pa.product_id not in allergen_lookup:
            allergen_lookup[pa.product_id] = []
        if allergen.icon:
            allergen_lookup[pa.product_id].append(allergen.icon)

    # Group products by category
    category_products: dict[int, list[ProductCompactOutput]] = {c.id: [] for c in categories}

    for product, branch_product, subcategory, category in products_query:
        if category.id in category_products:
            category_products[category.id].append(
                ProductCompactOutput(
                    id=product.id,
                    name=product.name,
                    description=product.description,
                    price_cents=branch_product.price_cents,
                    category_id=category.id,
                    category_name=category.name,
                    subcategory_id=subcategory.id if subcategory else None,
                    subcategory_name=subcategory.name if subcategory else None,
                    allergen_icons=allergen_lookup.get(product.id, []),
                    is_available=branch_product.is_available,
                )
            )

    # Build response
    result_categories = []
    total_products = 0

    for category in categories:
        products = category_products.get(category.id, [])
        if products:  # Only include categories with available products
            result_categories.append(
                CategoryCompactOutput(
                    id=category.id,
                    name=category.name,
                    products=products,
                )
            )
            total_products += len(products)

    return MenuCompactOutput(
        branch_id=branch.id,
        branch_name=branch.name,
        categories=result_categories,
        total_products=total_products,
    )


# =============================================================================
# Round Item Management
# =============================================================================


class DeleteRoundItemResponse(BaseModel):
    """Response for deleting a round item."""
    success: bool
    round_id: int
    item_id: int
    remaining_items: int
    round_deleted: bool = False  # True if round was deleted because it became empty
    message: str


@router.delete("/rounds/{round_id}/items/{item_id}", response_model=DeleteRoundItemResponse)
async def delete_round_item(
    round_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> DeleteRoundItemResponse:
    """
    Delete an item from a round.

    Only allowed for rounds in PENDING or CONFIRMED status (before being sent to kitchen).
    If the round becomes empty after deletion, the entire round is deleted.

    Requires WAITER, MANAGER, or ADMIN role.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    waiter_id = int(ctx["sub"])
    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Find the round with items and table info
    round_obj = db.scalar(
        select(Round)
        .options(
            selectinload(Round.items),
            joinedload(Round.session).joinedload(TableSession.table),
        )
        .where(
            Round.id == round_id,
            Round.tenant_id == tenant_id,
        )
    )

    if not round_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ronda {round_id} no encontrada",
        )

    # Verify branch access
    if round_obj.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a esta sucursal",
        )

    # Only allow deletion for PENDING or CONFIRMED rounds
    if round_obj.status not in ["PENDING", "CONFIRMED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"No se puede eliminar items de una ronda en estado {round_obj.status}. Solo se permite en PENDING o CONFIRMED.",
        )

    # Find the item
    item = next((i for i in round_obj.items if i.id == item_id), None)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item {item_id} no encontrado en la ronda {round_id}",
        )

    # SYNC FIX: Capture product_id before deletion for frontend sync
    deleted_product_id = item.product_id

    # Delete the item
    db.delete(item)

    # Check remaining items
    remaining_items = len([i for i in round_obj.items if i.id != item_id])
    round_deleted = False

    # If round is now empty, delete it
    if remaining_items == 0:
        db.delete(round_obj)
        round_deleted = True
        logger.info(
            "Round deleted (no items remaining)",
            round_id=round_id,
            waiter_id=waiter_id,
        )

    from shared.infrastructure.db import safe_commit
    safe_commit(db)

    # Publish event for real-time UI updates
    session = round_obj.session
    table = session.table if session else None
    sector_id = table.sector_id if table else None

    try:
        redis = await get_redis_client()
        # Use a custom event type for item deletion
        from shared.infrastructure.events import publish_event, Event
        event = Event(
            type="ROUND_ITEM_DELETED",
            tenant_id=tenant_id,
            branch_id=round_obj.branch_id,
            table_id=table.id if table else 0,
            session_id=round_obj.table_session_id,
            round_id=round_id,
            item_id=item_id,
            product_id=deleted_product_id,  # SYNC FIX: For frontend cart sync
            round_deleted=round_deleted,
            actor_user_id=waiter_id,
            actor_role="WAITER",
            sector_id=sector_id,
        )
        # Publish to admin, waiter, and diner channels
        from shared.infrastructure.events import channel_branch_admin, channel_branch_waiters, channel_table_session
        await publish_event(redis, channel_branch_admin(round_obj.branch_id), event)
        await publish_event(redis, channel_branch_waiters(round_obj.branch_id), event)
        # SYNC FIX: Also notify diners so their cart updates in real-time
        await publish_event(redis, channel_table_session(round_obj.table_session_id), event)
        logger.info(
            "Round item deleted",
            round_id=round_id,
            item_id=item_id,
            waiter_id=waiter_id,
            remaining_items=remaining_items,
            round_deleted=round_deleted,
        )
    except Exception as e:
        logger.error("Failed to publish ROUND_ITEM_DELETED event", error=str(e))

    message = "Ronda eliminada (sin items)" if round_deleted else "Item eliminado correctamente"

    return DeleteRoundItemResponse(
        success=True,
        round_id=round_id,
        item_id=item_id,
        remaining_items=remaining_items,
        round_deleted=round_deleted,
        message=message,
    )


@router.get("/sessions/{session_id}/summary", response_model=WaiterSessionSummaryOutput)
def get_session_summary(
    session_id: int,
    db: Session = Depends(get_db),
    ctx: dict[str, Any] = Depends(current_user_context),
) -> WaiterSessionSummaryOutput:
    """
    HU-WAITER-MESA CA-09: Get summary of a session for waiter view.

    Returns session details including traceability info (who opened it,
    who submitted orders) and whether it's a hybrid flow.
    """
    require_roles(ctx, ["WAITER", "MANAGER", "ADMIN"])

    tenant_id = ctx.get("tenant_id")
    branch_ids = ctx.get("branch_ids", [])

    # Find session with related data
    session = db.scalar(
        select(TableSession)
        .options(
            joinedload(TableSession.table),
            selectinload(TableSession.rounds),
            selectinload(TableSession.diners),
        )
        .where(
            TableSession.id == session_id,
            TableSession.tenant_id == tenant_id,
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session {session_id} not found",
        )

    # Verify branch access
    if session.branch_id not in branch_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to this branch",
        )

    # Get check info if exists
    # QA-BACK-CRIT-02 FIX: Added tenant_id validation for defense in depth
    check = db.scalar(
        select(Check)
        .where(
            Check.table_session_id == session_id,
            Check.tenant_id == tenant_id,
            Check.is_active.is_(True),
        )
    )

    # HIGH-N+1-01 FIX: Calculate totals from rounds using single aggregated query
    # Instead of N+1 queries (one per round), we use a single JOIN query with SUM
    valid_round_ids = [
        r.id for r in session.rounds
        if r.status not in ["DRAFT", "CANCELED"]
    ]
    total_cents = 0
    if valid_round_ids:
        total_cents = db.scalar(
            select(func.coalesce(func.sum(RoundItem.unit_price_cents * RoundItem.qty), 0))
            .where(RoundItem.round_id.in_(valid_round_ids))
        ) or 0

    # Check for hybrid flow (both waiter and diner-submitted rounds)
    has_waiter_rounds = any(r.submitted_by == "WAITER" for r in session.rounds)
    has_diner_rounds = any(r.submitted_by == "DINER" for r in session.rounds)
    is_hybrid = has_waiter_rounds and has_diner_rounds

    table = session.table
    diner_count = len(session.diners) if session.diners else 0

    return WaiterSessionSummaryOutput(
        session_id=session.id,
        table_id=table.id if table else 0,
        table_code=table.code if table else "",
        status=session.status,
        opened_at=session.opened_at,
        opened_by=session.opened_by,
        opened_by_waiter_id=session.opened_by_waiter_id,
        assigned_waiter_id=session.assigned_waiter_id,
        diner_count=diner_count,
        rounds_count=len(session.rounds),
        total_cents=check.total_cents if check else total_cents,
        paid_cents=check.paid_cents if check else 0,
        check_status=check.status if check else None,
        is_hybrid=is_hybrid,
    )
