"""
Outbox service for transactional event publishing.

OUTBOX-PATTERN: Provides functions to write events to the outbox table
atomically with business data. The processor then reads and publishes
these events asynchronously.

Usage in endpoints:
    1. Perform business logic (create round, payment, etc.)
    2. Call write_outbox_event() with the same db session
    3. Commit the transaction (both business data and event are atomic)

Example:
    round = Round(...)
    db.add(round)
    write_outbox_event(
        db=db,
        tenant_id=tenant_id,
        event_type=ROUND_SUBMITTED,
        aggregate_type="round",
        aggregate_id=round.id,
        payload={...}
    )
    db.commit()  # Atomic: both round and outbox event are saved together
"""

import json
from typing import Any

from sqlalchemy.orm import Session

from rest_api.models import OutboxEvent, OutboxStatus
from shared.config.logging import get_logger

logger = get_logger(__name__)


def write_outbox_event(
    db: Session,
    tenant_id: int,
    event_type: str,
    aggregate_type: str,
    aggregate_id: int,
    payload: dict[str, Any],
) -> OutboxEvent:
    """
    Write an event to the outbox table.

    MUST be called within the same transaction as the business operation.
    The event will be published by the outbox processor.

    Args:
        db: SQLAlchemy session (same session as business operation)
        tenant_id: Tenant ID for multi-tenant isolation
        event_type: Event type constant (e.g., ROUND_SUBMITTED, CHECK_PAID)
        aggregate_type: Type of aggregate (e.g., "round", "check", "service_call")
        aggregate_id: ID of the aggregate
        payload: Event payload as dict (will be JSON serialized)

    Returns:
        The created OutboxEvent instance

    Example:
        # In endpoint, after business logic:
        write_outbox_event(
            db=db,
            tenant_id=user["tenant_id"],
            event_type=ROUND_SUBMITTED,
            aggregate_type="round",
            aggregate_id=round.id,
            payload={
                "branch_id": round.branch_id,
                "session_id": round.table_session_id,
                "round_number": round.round_number,
                "actor_user_id": user_id,
            }
        )
        db.commit()  # Both business data and event saved atomically
    """
    outbox_event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=json.dumps(payload),
        status=OutboxStatus.PENDING,
        retry_count=0,
    )
    db.add(outbox_event)
    # Don't flush/commit - let the caller control the transaction
    logger.debug(
        "Outbox event queued",
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
    )
    return outbox_event


def write_billing_outbox_event(
    db: Session,
    tenant_id: int,
    event_type: str,
    check_id: int,
    branch_id: int,
    session_id: int,
    table_id: int | None = None,
    extra_data: dict[str, Any] | None = None,
    actor_user_id: int | None = None,
    actor_role: str = "SYSTEM",
) -> OutboxEvent:
    """
    Write a billing event to the outbox.

    Convenience function for billing-related events (CHECK_REQUESTED,
    PAYMENT_APPROVED, PAYMENT_REJECTED, CHECK_PAID).

    Args:
        db: SQLAlchemy session
        tenant_id: Tenant ID
        event_type: Billing event type
        check_id: ID of the check
        branch_id: Branch ID
        session_id: Table session ID
        table_id: Optional table ID
        extra_data: Additional event data (e.g., payment_id, amount_cents)
        actor_user_id: User who triggered the event
        actor_role: Role of the actor (WAITER, DINER, SYSTEM)

    Returns:
        The created OutboxEvent
    """
    payload = {
        "branch_id": branch_id,
        "session_id": session_id,
        "table_id": table_id,
        "check_id": check_id,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
    }
    if extra_data:
        payload.update(extra_data)

    return write_outbox_event(
        db=db,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type="check",
        aggregate_id=check_id,
        payload=payload,
    )


def write_round_outbox_event(
    db: Session,
    tenant_id: int,
    event_type: str,
    round_id: int,
    branch_id: int,
    session_id: int,
    table_id: int | None = None,
    round_number: int = 0,
    sector_id: int | None = None,
    actor_user_id: int | None = None,
    actor_role: str = "DINER",
) -> OutboxEvent:
    """
    Write a round event to the outbox.

    Convenience function for round-related events (ROUND_SUBMITTED, ROUND_READY).

    Args:
        db: SQLAlchemy session
        tenant_id: Tenant ID
        event_type: Round event type
        round_id: ID of the round
        branch_id: Branch ID
        session_id: Table session ID
        table_id: Optional table ID
        round_number: Round number within the session
        sector_id: Optional sector ID for targeted waiter notifications
        actor_user_id: User who triggered the event
        actor_role: Role of the actor (WAITER, KITCHEN, ADMIN, etc.)

    Returns:
        The created OutboxEvent
    """
    return write_outbox_event(
        db=db,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type="round",
        aggregate_id=round_id,
        payload={
            "branch_id": branch_id,
            "session_id": session_id,
            "table_id": table_id,
            "round_number": round_number,
            "sector_id": sector_id,
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
        },
    )


def write_service_call_outbox_event(
    db: Session,
    tenant_id: int,
    event_type: str,
    call_id: int,
    branch_id: int,
    session_id: int,
    table_id: int | None = None,
    call_type: str = "WAITER",
    sector_id: int | None = None,
    actor_user_id: int | None = None,
    actor_role: str = "DINER",
) -> OutboxEvent:
    """
    Write a service call event to the outbox.

    Convenience function for service call events (SERVICE_CALL_CREATED).

    Args:
        db: SQLAlchemy session
        tenant_id: Tenant ID
        event_type: Service call event type
        call_id: ID of the service call
        branch_id: Branch ID
        session_id: Table session ID
        table_id: Optional table ID
        call_type: Type of call (WAITER, PAYMENT_HELP)
        sector_id: Optional sector ID for targeted waiter notifications
        actor_user_id: User who triggered the event
        actor_role: Role of the actor

    Returns:
        The created OutboxEvent
    """
    return write_outbox_event(
        db=db,
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type="service_call",
        aggregate_id=call_id,
        payload={
            "branch_id": branch_id,
            "session_id": session_id,
            "table_id": table_id,
            "call_type": call_type,
            "sector_id": sector_id,
            "actor_user_id": actor_user_id,
            "actor_role": actor_role,
        },
    )
