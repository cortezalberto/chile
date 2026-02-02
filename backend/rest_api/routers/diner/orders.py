"""
Diner router.
Handles operations performed by diners (customers) at tables.
Uses table token authentication instead of JWT.
"""

from datetime import datetime, timezone
from typing import Any  # Used in return type annotations

from fastapi import APIRouter, Depends, HTTPException, status, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from shared.infrastructure.db import get_db
from shared.security.rate_limit import limiter
from rest_api.models import (
    Table,
    TableSession,
    Round,
    RoundItem,
    Product,
    BranchProduct,
    ServiceCall,
    Check,
    Payment,
    Diner,
    Branch,
    CartItem,
)
from shared.security.auth import current_table_context
from shared.utils.schemas import (
    SubmitRoundRequest,
    SubmitRoundResponse,
    RoundOutput,
    RoundItemOutput,
    CreateServiceCallRequest,
    ServiceCallOutput,
    CheckDetailOutput,
    CheckItemOutput,
    PaymentOutput,
    RegisterDinerRequest,
    DinerOutput,
    DeviceHistoryOutput,
    DeviceVisitOutput,
    UpdatePreferencesRequest,
    UpdatePreferencesResponse,
    DevicePreferencesOutput,
    ImplicitPreferencesData,
)
import json
from fastapi import Header
from shared.config.logging import diner_logger as logger
from shared.infrastructure.events import (
    get_redis_client,
    publish_round_event,
    publish_service_call_event,
    publish_cart_event,
    ROUND_PENDING,
    SERVICE_CALL_CREATED,
    CART_CLEARED,
)


router = APIRouter(prefix="/api/diner", tags=["diner"])


# =============================================================================
# Diner Registration (Phase 2)
# =============================================================================


@router.post("/register", response_model=DinerOutput)
@limiter.limit("20/minute")
def register_diner(
    request: Request,
    body: RegisterDinerRequest,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> DinerOutput:
    """
    Register a diner at a table session.

    Creates a persistent Diner entity that can be linked to orders and payments.
    If a diner with the same local_id already exists for this session, returns the existing diner.

    Requires X-Table-Token header with valid table token.
    """
    session_id = table_ctx["session_id"]
    branch_id = table_ctx["branch_id"]
    tenant_id = table_ctx["tenant_id"]

    # Verify session exists and is open
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active or does not exist",
        )

    # Check if diner with same local_id already exists (idempotency)
    if body.local_id:
        existing_diner = db.scalar(
            select(Diner).where(
                Diner.session_id == session_id,
                Diner.local_id == body.local_id,
            )
        )
        if existing_diner:
            # FASE 1: Update device_id if provided and not already set
            # HIGH-DINER-03 FIX: Added error handling for commit
            if body.device_id and not existing_diner.device_id:
                existing_diner.device_id = body.device_id
                existing_diner.device_fingerprint = body.device_fingerprint
                try:
                    db.commit()
                    db.refresh(existing_diner)
                except Exception as e:
                    db.rollback()
                    logger.error("Failed to update device_id", error=str(e))
                    # Continue anyway - diner exists, just device_id update failed
            return DinerOutput(
                id=existing_diner.id,
                session_id=existing_diner.session_id,
                name=existing_diner.name,
                color=existing_diner.color,
                local_id=existing_diner.local_id,
                joined_at=existing_diner.joined_at,
                device_id=existing_diner.device_id,
            )

    # Create new diner
    # FASE 1: Include device tracking fields for cross-session recognition
    new_diner = Diner(
        tenant_id=tenant_id,
        branch_id=branch_id,
        session_id=session_id,
        name=body.name,
        color=body.color,
        local_id=body.local_id,
        device_id=body.device_id,
        device_fingerprint=body.device_fingerprint,
    )
    db.add(new_diner)

    # AUDIT FIX: Wrap commit in try-except to handle DB errors
    try:
        db.commit()
        db.refresh(new_diner)
    except Exception as e:
        db.rollback()
        logger.error("Failed to register diner", session_id=session_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register diner - please try again",
        )

    return DinerOutput(
        id=new_diner.id,
        session_id=new_diner.session_id,
        name=new_diner.name,
        color=new_diner.color,
        local_id=new_diner.local_id,
        joined_at=new_diner.joined_at,
        device_id=new_diner.device_id,
    )


@router.get("/session/{session_id}/diners", response_model=list[DinerOutput])
def get_session_diners(
    session_id: int,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> list[DinerOutput]:
    """
    Get all diners for a session.

    Returns the list of registered diners with their backend IDs.
    """
    # Verify session matches token
    if table_ctx["session_id"] != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not match token",
        )

    diners = db.execute(
        select(Diner)
        .where(Diner.session_id == session_id)
        .order_by(Diner.joined_at)
    ).scalars().all()

    return [
        DinerOutput(
            id=diner.id,
            session_id=diner.session_id,
            name=diner.name,
            color=diner.color,
            local_id=diner.local_id,
            joined_at=diner.joined_at,
            device_id=diner.device_id,
        )
        for diner in diners
    ]


# =============================================================================
# Round Submission
# =============================================================================


# Helper wrapper for background task execution
async def _bg_publish_round_event(**kwargs):
    """Background task to publish round event."""
    try:
        redis = await get_redis_client()
        await publish_round_event(redis_client=redis, **kwargs)
        logger.info("ROUND_PENDING published (bg)", round_id=kwargs.get("round_id"))
    except Exception as e:
        logger.error("Failed to publish ROUND_PENDING event (bg)", error=str(e))

async def _bg_publish_service_call_event(**kwargs):
    """Background task to publish service call event."""
    try:
        redis = await get_redis_client()
        await publish_service_call_event(redis_client=redis, **kwargs)
        logger.info("SERVICE_CALL_CREATED published (bg)", call_id=kwargs.get("call_id"))
    except Exception as e:
        logger.error("Failed to publish SERVICE_CALL_CREATED event (bg)", error=str(e))


async def _bg_publish_cart_cleared(**kwargs):
    """Background task to publish cart cleared event after round submission."""
    try:
        redis = await get_redis_client()
        await publish_cart_event(
            redis_client=redis,
            event_type=CART_CLEARED,
            **kwargs
        )
        logger.info("CART_CLEARED published (bg)", session_id=kwargs.get("session_id"))
    except Exception as e:
        logger.error("Failed to publish CART_CLEARED event (bg)", error=str(e))


@router.post("/rounds/submit", response_model=SubmitRoundResponse)
@limiter.limit("10/minute")
def submit_round(
    request: Request,
    body: SubmitRoundRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
    x_idempotency_key: str | None = Header(None),
) -> SubmitRoundResponse:
    """
    Submit a new round of orders.
    
    Creates a new round with the specified items and schedules a 
    ROUND_PENDING event to be published in the background.

    Requires X-Table-Token header with valid table token.
    """
    session_id = table_ctx["session_id"]
    table_id = table_ctx["table_id"]
    branch_id = table_ctx["branch_id"]
    tenant_id = table_ctx["tenant_id"]

    # CRIT-IDEMP-01 FIX: Check for existing round with same idempotency key
    if x_idempotency_key:
        existing_round = db.scalar(
            select(Round).where(
                Round.table_session_id == session_id,
                Round.idempotency_key == x_idempotency_key,
                Round.status != "CANCELED",
            )
        )
        if existing_round:
            logger.info("Idempotent round submission detected",
                       session_id=session_id,
                       round_id=existing_round.id,
                       idempotency_key=x_idempotency_key[:8] + "...")
            return SubmitRoundResponse(
                session_id=session_id,
                round_id=existing_round.id,
                round_number=existing_round.round_number,
                status=existing_round.status,
            )

    # DEF-HIGH-01 FIX: Allow round submission in both OPEN and PAYING states
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active or does not exist",
        )

    # FIX: Get table's sector_id for targeted waiter notifications
    table = db.scalar(select(Table).where(Table.id == table_id))
    sector_id = table.sector_id if table else None

    # CRIT-29-01 FIX: Use SELECT FOR UPDATE to prevent race condition
    locked_session = db.scalar(
        select(TableSession)
        .where(TableSession.id == session_id)
        .with_for_update()
    )
    if not locked_session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session not found",
        )

    # Get next round number
    max_round = db.scalar(
        select(func.max(Round.round_number))
        .where(Round.table_session_id == session_id)
    ) or 0
    next_round_number = max_round + 1

    # Create the round with PENDING status
    new_round = Round(
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_session_id=session_id,
        round_number=next_round_number,
        status="PENDING",
        submitted_at=datetime.now(timezone.utc),
        idempotency_key=x_idempotency_key,
    )
    db.add(new_round)
    db.flush()

    # REC-03 FIX: Batch fetch all products and branch prices
    product_ids = [item.product_id for item in body.items]

    products_query = db.execute(
        select(Product, BranchProduct)
        .join(BranchProduct, Product.id == BranchProduct.product_id)
        .where(
            Product.id.in_(product_ids),
            Product.is_active.is_(True),
            BranchProduct.branch_id == branch_id,
            BranchProduct.is_available == True,
        )
    ).all()

    # Build lookup dict
    product_lookup: dict[int, tuple] = {
        product.id: (product, branch_product)
        for product, branch_product in products_query
    }

    # Validate all products are available
    for item in body.items:
        if item.product_id not in product_lookup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product {item.product_id} not available in this branch",
            )

    # REC-03 FIX: Batch create all round items
    round_items_to_add = []
    for item in body.items:
        product, branch_product = product_lookup[item.product_id]

        round_item = RoundItem(
            tenant_id=tenant_id,
            branch_id=branch_id,
            round_id=new_round.id,
            product_id=product.id,
            qty=item.qty,
            unit_price_cents=branch_product.price_cents,
            notes=item.notes,
        )
        round_items_to_add.append(round_item)

    db.add_all(round_items_to_add)

    # SHARED-CART: Clear cart_items after creating round
    db.execute(
        CartItem.__table__.delete().where(CartItem.session_id == session_id)
    )

    # AUDIT FIX: Wrap commit in try-except
    try:
        db.commit()
        db.refresh(new_round)
    except Exception as e:
        db.rollback()
        logger.error("Failed to submit round", session_id=session_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit order - please try again",
        )

    # Schedule event publication in background
    background_tasks.add_task(
        _bg_publish_round_event,
        event_type=ROUND_PENDING,
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_id=table_id,
        session_id=session_id,
        round_id=new_round.id,
        round_number=next_round_number,
        actor_user_id=None,
        actor_role="DINER",
        sector_id=sector_id,
    )

    # SHARED-CART: Notify all diners that cart was cleared
    background_tasks.add_task(
        _bg_publish_cart_cleared,
        tenant_id=tenant_id,
        branch_id=branch_id,
        session_id=session_id,
        entity={"cleared": True},
    )

    return SubmitRoundResponse(
        session_id=session_id,
        round_id=new_round.id,
        round_number=next_round_number,
        status=new_round.status,
    )


@router.get("/session/{session_id}/rounds", response_model=list[RoundOutput])
def get_session_rounds(
    session_id: int,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> list[RoundOutput]:
    """
    Get all rounds for a session.

    Returns the history of orders with their current status.

    AUDIT FIX: Uses batch loading to prevent N+1 queries.
    """
    # Verify session matches token
    if table_ctx["session_id"] != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not match token",
        )

    rounds = db.execute(
        select(Round)
        .where(Round.table_session_id == session_id)
        .order_by(Round.round_number)
    ).scalars().all()

    if not rounds:
        return []

    # AUDIT FIX: Batch load all items and products at once instead of per-round
    round_ids = [r.id for r in rounds]

    # Single query to get all items with their products
    all_items = db.execute(
        select(RoundItem, Product)
        .join(Product, RoundItem.product_id == Product.id)
        .where(RoundItem.round_id.in_(round_ids))
    ).all()

    # Group items by round_id
    items_by_round: dict[int, list[tuple]] = {rid: [] for rid in round_ids}
    for item, product in all_items:
        items_by_round[item.round_id].append((item, product))

    result = []
    for round_obj in rounds:
        items = items_by_round.get(round_obj.id, [])

        item_outputs = [
            RoundItemOutput(
                id=item.id,
                product_id=item.product_id,
                product_name=product.name,
                qty=item.qty,
                unit_price_cents=item.unit_price_cents,
                notes=item.notes,
            )
            for item, product in items
        ]

        result.append(
            RoundOutput(
                id=round_obj.id,
                round_number=round_obj.round_number,
                status=round_obj.status,
                items=item_outputs,
                created_at=round_obj.created_at,
            )
        )

    return result


@router.post("/service-call", response_model=ServiceCallOutput)
@limiter.limit("10/minute")
def create_service_call(
    request: Request,
    body: CreateServiceCallRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> ServiceCallOutput:
    """
    Create a service call (call waiter or request payment help).

    Publishes a SERVICE_CALL_CREATED event for waiters in background.
    """
    session_id = table_ctx["session_id"]
    table_id = table_ctx["table_id"]
    branch_id = table_ctx["branch_id"]
    tenant_id = table_ctx["tenant_id"]

    # Verify session is active
    session = db.scalar(
        select(TableSession).where(
            TableSession.id == session_id,
            TableSession.status.in_(["OPEN", "PAYING"]),
        )
    )

    if not session:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not active",
        )

    # SECTOR-DISPATCH FIX: Get table's sector_id
    table = db.scalar(select(Table).where(Table.id == table_id))
    sector_id = table.sector_id if table else None

    # HIGH-04 FIX: Check for existing open call (idempotency)
    existing_call = db.scalar(
        select(ServiceCall).where(
            ServiceCall.table_session_id == session_id,
            ServiceCall.type == body.type,
            ServiceCall.status == "OPEN",
        )
    )

    if existing_call:
        # QA-FIX: Still publish event for existing call (reminder notification)
        # This ensures waiter gets sound/notification even for repeated calls
        # without creating duplicate records in the database
        background_tasks.add_task(
            _bg_publish_service_call_event,
            event_type=SERVICE_CALL_CREATED,
            tenant_id=tenant_id,
            branch_id=branch_id,
            table_id=table_id,
            session_id=session_id,
            call_id=existing_call.id,
            call_type=body.type,
            actor_user_id=None,
            actor_role="DINER",
            sector_id=sector_id,
        )
        logger.info(
            "Service call reminder sent (existing call)",
            call_id=existing_call.id,
            session_id=session_id,
        )
        return ServiceCallOutput(
            id=existing_call.id,
            type=existing_call.type,
            status=existing_call.status,
            created_at=existing_call.created_at,
            acked_by_user_id=existing_call.acked_by_user_id,
            table_id=table_id,
            table_code=table.code if table else None,
            session_id=session_id,
        )

    # Create new service call
    service_call = ServiceCall(
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_session_id=session_id,
        type=body.type,
        status="OPEN",
    )
    db.add(service_call)

    # AUDIT FIX: Wrap commit in try-except
    try:
        db.commit()
        db.refresh(service_call)
    except Exception as e:
        db.rollback()
        logger.error("Failed to create service call", session_id=session_id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create service call - please try again",
        )

    # Schedule event publication in background
    background_tasks.add_task(
        _bg_publish_service_call_event,
        event_type=SERVICE_CALL_CREATED,
        tenant_id=tenant_id,
        branch_id=branch_id,
        table_id=table_id,
        session_id=session_id,
        call_id=service_call.id,
        call_type=body.type,
        actor_user_id=None,
        actor_role="DINER",
        sector_id=sector_id,
    )

    return ServiceCallOutput(
        id=service_call.id,
        type=service_call.type,
        status=service_call.status,
        created_at=service_call.created_at,
        acked_by_user_id=service_call.acked_by_user_id,
        table_id=table_id,
        table_code=table.code if table else None,
        session_id=session_id,
    )


@router.get("/session/{session_id}/total")
def get_session_total(
    session_id: int,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> dict[str, Any]:
    """
    Get the total amount for a session.

    Calculates total from all rounds (excluding CANCELED).
    """
    if table_ctx["session_id"] != session_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session does not match token",
        )

    # Calculate total from all round items
    total_cents = db.scalar(
        select(func.sum(RoundItem.unit_price_cents * RoundItem.qty))
        .join(Round, RoundItem.round_id == Round.id)
        .where(
            Round.table_session_id == session_id,
            Round.status != "CANCELED",
        )
    ) or 0

    # Check if there's an active check
    check = db.scalar(
        select(Check)
        .where(Check.table_session_id == session_id)
        .order_by(Check.created_at.desc())
    )

    return {
        "session_id": session_id,
        "total_cents": total_cents,
        "paid_cents": check.paid_cents if check else 0,
        "check_id": check.id if check else None,
        "check_status": check.status if check else None,
    }


@router.get("/check", response_model=CheckDetailOutput)
def get_diner_check(
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> CheckDetailOutput:
    """
    Get the current check detail for the diner's session.

    Returns full breakdown of items and payments.
    Used by diner to see their bill before/during payment.
    """
    session_id = table_ctx["session_id"]
    table_id = table_ctx["table_id"]

    # Get the check for this session
    check = db.scalar(
        select(Check)
        .where(Check.table_session_id == session_id)
        .order_by(Check.created_at.desc())
    )

    if not check:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check found for this session. Request check first.",
        )

    # Get table code
    table = db.scalar(select(Table).where(Table.id == table_id))

    # Get all items from all rounds (non-canceled)
    items_query = db.execute(
        select(RoundItem, Product, Round.round_number)
        .join(Product, RoundItem.product_id == Product.id)
        .join(Round, RoundItem.round_id == Round.id)
        .where(
            Round.table_session_id == session_id,
            Round.status != "CANCELED",
        )
        .order_by(Round.round_number, RoundItem.id)
    ).all()

    items = [
        CheckItemOutput(
            product_name=product.name,
            qty=item.qty,
            unit_price_cents=item.unit_price_cents,
            subtotal_cents=item.qty * item.unit_price_cents,
            notes=item.notes,
            round_number=round_number,
        )
        for item, product, round_number in items_query
    ]

    # Get payments
    payments = db.execute(
        select(Payment)
        .where(Payment.check_id == check.id)
        .order_by(Payment.created_at)
    ).scalars().all()

    payment_outputs = [
        PaymentOutput(
            id=p.id,
            provider=p.provider,
            status=p.status,
            amount_cents=p.amount_cents,
            created_at=p.created_at,
        )
        for p in payments
    ]

    return CheckDetailOutput(
        id=check.id,
        status=check.status,
        total_cents=check.total_cents,
        paid_cents=check.paid_cents,
        remaining_cents=max(0, check.total_cents - check.paid_cents),
        items=items,
        payments=payment_outputs,
        created_at=check.created_at,
        table_code=table.code if table else None,
    )


# =============================================================================
# Device History (FASE 1: Fidelización)
# =============================================================================


@router.get("/device/{device_id}/history", response_model=DeviceHistoryOutput)
def get_device_history(
    device_id: str,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> DeviceHistoryOutput:
    """
    Get visit history for a device.

    FASE 1: Device tracking for cross-session recognition.
    Returns all visits associated with the device_id for the tenant.
    Only returns data for the same tenant as the current session.

    Requires X-Table-Token header with valid table token.
    """
    tenant_id = table_ctx["tenant_id"]

    # Get all diners with this device_id for the tenant
    diners_with_sessions = db.execute(
        select(Diner, TableSession, Branch)
        .join(TableSession, Diner.session_id == TableSession.id)
        .join(Branch, Diner.branch_id == Branch.id)
        .where(
            Diner.device_id == device_id,
            Diner.tenant_id == tenant_id,
        )
        .order_by(Diner.joined_at.desc())
    ).all()

    if not diners_with_sessions:
        return DeviceHistoryOutput(
            device_id=device_id,
            total_visits=0,
            total_spent_cents=0,
            visits=[],
        )

    # RTR-MED-01 FIX: Batch queries to avoid N+1 pattern
    # Collect all session IDs and diner IDs for batch queries
    session_ids = [session.id for _, session, _ in diners_with_sessions]
    diner_ids = [diner.id for diner, _, _ in diners_with_sessions]

    # Batch query 1: Get spent per diner across all sessions
    spent_by_diner = dict(db.execute(
        select(RoundItem.diner_id, func.sum(RoundItem.unit_price_cents * RoundItem.qty))
        .join(Round, RoundItem.round_id == Round.id)
        .where(
            Round.table_session_id.in_(session_ids),
            Round.status != "CANCELED",
            RoundItem.diner_id.in_(diner_ids),
        )
        .group_by(RoundItem.diner_id)
    ).all())

    # Batch query 2: Get total spent per session (for fallback calculation)
    spent_by_session = dict(db.execute(
        select(Round.table_session_id, func.sum(RoundItem.unit_price_cents * RoundItem.qty))
        .join(RoundItem, Round.id == RoundItem.round_id)
        .where(
            Round.table_session_id.in_(session_ids),
            Round.status != "CANCELED",
        )
        .group_by(Round.table_session_id)
    ).all())

    # Batch query 3: Get diner count per session
    diners_per_session = dict(db.execute(
        select(Diner.session_id, func.count(Diner.id))
        .where(Diner.session_id.in_(session_ids))
        .group_by(Diner.session_id)
    ).all())

    # Batch query 4: Get item count per session
    items_per_session = dict(db.execute(
        select(Round.table_session_id, func.count(RoundItem.id))
        .join(RoundItem, Round.id == RoundItem.round_id)
        .where(
            Round.table_session_id.in_(session_ids),
            Round.status != "CANCELED",
        )
        .group_by(Round.table_session_id)
    ).all())

    visits: list[DeviceVisitOutput] = []
    total_spent = 0

    # RTR-LOW-04 FIX: Named constant for default diner count
    DEFAULT_DINER_COUNT = 1  # Fallback when no diners found (shouldn't happen)

    for diner, session, branch in diners_with_sessions:
        # Use pre-fetched data instead of individual queries
        session_spent = spent_by_diner.get(diner.id, 0)

        # If no diner_id on items, calculate total session spent / diners
        if session_spent == 0:
            total_session = spent_by_session.get(session.id, 0)
            diner_count = diners_per_session.get(session.id, DEFAULT_DINER_COUNT)
            session_spent = total_session // diner_count if diner_count > 0 else 0

        items_count = items_per_session.get(session.id, 0)

        visits.append(DeviceVisitOutput(
            session_id=session.id,
            diner_id=diner.id,
            diner_name=diner.name,
            branch_id=branch.id,
            branch_name=branch.name,
            visited_at=diner.joined_at,
            total_spent_cents=session_spent,
            items_ordered=items_count,
        ))
        total_spent += session_spent

    return DeviceHistoryOutput(
        device_id=device_id,
        total_visits=len(visits),
        total_spent_cents=total_spent,
        first_visit=visits[-1].visited_at if visits else None,
        last_visit=visits[0].visited_at if visits else None,
        visits=visits,
    )


# =============================================================================
# Implicit Preferences (FASE 2: Fidelización)
# =============================================================================


@router.patch("/preferences", response_model=UpdatePreferencesResponse)
def update_diner_preferences(
    body: UpdatePreferencesRequest,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> UpdatePreferencesResponse:
    """
    FASE 2: Update implicit preferences for the current diner.

    Syncs filter settings (allergens, dietary, cooking methods) from
    the frontend to the backend for cross-session persistence.

    Requires X-Table-Token header with valid table token.
    """
    session_id = table_ctx["session_id"]

    # Get the most recent diner for this session (current user)
    diner = db.scalar(
        select(Diner)
        .where(Diner.session_id == session_id)
        .order_by(Diner.joined_at.desc())
    )

    if not diner:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No diner found for this session",
        )

    # Serialize preferences to JSON
    prefs_json = json.dumps({
        "excluded_allergen_ids": body.implicit_preferences.excluded_allergen_ids,
        "dietary_preferences": body.implicit_preferences.dietary_preferences,
        "excluded_cooking_methods": body.implicit_preferences.excluded_cooking_methods,
        "cross_reactions_enabled": body.implicit_preferences.cross_reactions_enabled,
        "strictness": body.implicit_preferences.strictness,
    })

    diner.implicit_preferences = prefs_json

    try:
        db.commit()
        db.refresh(diner)
    except Exception as e:
        db.rollback()
        logger.error("Failed to update preferences", diner_id=diner.id, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save preferences",
        )

    logger.info("Preferences updated", diner_id=diner.id, device_id=diner.device_id)

    return UpdatePreferencesResponse(
        diner_id=diner.id,
        device_id=diner.device_id,
        implicit_preferences=body.implicit_preferences,
        updated_at=datetime.now(timezone.utc),
    )


@router.get("/device/{device_id}/preferences", response_model=DevicePreferencesOutput)
def get_device_preferences(
    device_id: str,
    db: Session = Depends(get_db),
    table_ctx: dict[str, int] = Depends(current_table_context),
) -> DevicePreferencesOutput:
    """
    FASE 2: Get the most recent preferences for a device.

    Used on app start to pre-fill filter settings for returning visitors.
    Returns the preferences from the most recent visit by this device.

    Requires X-Table-Token header with valid table token.
    """
    tenant_id = table_ctx["tenant_id"]

    # Find the most recent diner with this device_id that has preferences
    diner = db.scalar(
        select(Diner)
        .where(
            Diner.device_id == device_id,
            Diner.tenant_id == tenant_id,
            Diner.implicit_preferences.isnot(None),
        )
        .order_by(Diner.joined_at.desc())
    )

    # Count total visits for this device
    visit_count = db.scalar(
        select(func.count(Diner.id))
        .where(
            Diner.device_id == device_id,
            Diner.tenant_id == tenant_id,
        )
    ) or 0

    if not diner or not diner.implicit_preferences:
        return DevicePreferencesOutput(
            device_id=device_id,
            has_preferences=False,
            visit_count=visit_count,
        )

    # Parse stored preferences
    try:
        prefs_data = json.loads(diner.implicit_preferences)
        preferences = ImplicitPreferencesData(
            excluded_allergen_ids=prefs_data.get("excluded_allergen_ids", []),
            dietary_preferences=prefs_data.get("dietary_preferences", []),
            excluded_cooking_methods=prefs_data.get("excluded_cooking_methods", []),
            cross_reactions_enabled=prefs_data.get("cross_reactions_enabled", False),
            strictness=prefs_data.get("strictness", "strict"),
        )
    except (json.JSONDecodeError, TypeError):
        return DevicePreferencesOutput(
            device_id=device_id,
            has_preferences=False,
            visit_count=visit_count,
        )

    return DevicePreferencesOutput(
        device_id=device_id,
        has_preferences=True,
        implicit_preferences=preferences,
        last_updated=diner.joined_at,
        visit_count=visit_count,
    )
