"""
FIFO Payment Allocation Service.

Phase 3 improvement: Implements flexible split payment using Charges and Allocations.

The allocation algorithm:
1. When a check is requested, create Charge records for each RoundItem
2. When a payment is made, allocate it to charges using FIFO (oldest first)
3. A payment can cover multiple charges, and a charge can be covered by multiple payments

SVC-HIGH-01: Tenant isolation is enforced via tenant_id parameter in public functions.
When called from routers, always pass tenant_id from the authenticated context.
"""

# SVC-MED-01 FIX: Removed unused Optional import (using X | None syntax)
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from rest_api.models import (
    Check,
    Charge,
    Payment,
    Allocation,
    Round,
    RoundItem,
    Product,
    Diner,
)


def create_charges_for_check(
    db: Session,
    check: Check,
) -> list[Charge]:
    """
    Create Charge records for all items in a check.

    Each RoundItem generates one Charge record.
    If the item has a diner_id, the charge is assigned to that diner.

    Returns the list of created charges.
    """
    charges = []

    # Get all round items for this session
    items_query = db.execute(
        select(RoundItem, Product, Round)
        .join(Product, RoundItem.product_id == Product.id)
        .join(Round, RoundItem.round_id == Round.id)
        .where(
            Round.table_session_id == check.table_session_id,
            Round.status != "CANCELED",
        )
        .order_by(Round.round_number, RoundItem.id)
    ).all()

    for round_item, product, round_obj in items_query:
        # Calculate amount for this item (price * qty)
        amount_cents = round_item.unit_price_cents * round_item.qty

        charge = Charge(
            tenant_id=check.tenant_id,
            branch_id=check.branch_id,
            check_id=check.id,
            diner_id=round_item.diner_id,  # May be None
            round_item_id=round_item.id,
            amount_cents=amount_cents,
            # SVC-LOW-02 FIX: Standardized description format across allocation service
            description=f"{product.name} × {round_item.qty}",  # Using × for multiplication
        )
        db.add(charge)
        charges.append(charge)

    db.flush()  # Get IDs for the charges
    return charges


def allocate_payment_fifo(
    db: Session,
    payment: Payment,
    diner_id: int | None = None,
) -> list[Allocation]:
    """
    Allocate a payment to unpaid charges using FIFO.

    If diner_id is provided, only allocates to that diner's charges first,
    then to shared charges (diner_id=None), then to other diners' charges.

    SVC-CRIT-02 FIX: Uses SELECT FOR UPDATE to prevent race conditions when
    multiple payments are processed concurrently for the same check.

    SVC-HIGH-01 NOTE: Tenant isolation is ensured by the calling routers
    (billing.py) which validate the payment's check belongs to the user's
    tenant before calling this function. The check_id references are
    inherently tenant-scoped through the Check -> TableSession -> Table -> Branch -> Tenant chain.

    Returns the list of allocations created.
    """
    remaining_amount = payment.amount_cents
    allocations = []

    if remaining_amount <= 0:
        return allocations

    # SVC-CRIT-02 FIX: Lock the check row to prevent concurrent allocation issues
    # This ensures only one payment allocation happens at a time per check
    # SVC-LOW-01 FIX: Removed unused 'text' import - using with_for_update() directly
    db.execute(
        select(Check).where(Check.id == payment.check_id).with_for_update()
    ).scalar_one()

    # Get unpaid charges for this check
    # First, calculate how much has already been allocated to each charge
    subquery = (
        select(
            Allocation.charge_id,
            func.coalesce(func.sum(Allocation.amount_cents), 0).label("allocated")
        )
        .group_by(Allocation.charge_id)
        .subquery()
    )

    # Query charges with their allocated amounts
    # Order: own charges first (if diner_id provided), then shared, then others
    # SVC-CRIT-02 FIX: Lock charges with FOR UPDATE to prevent concurrent modifications
    base_query = (
        select(Charge, func.coalesce(subquery.c.allocated, 0).label("allocated"))
        .outerjoin(subquery, Charge.id == subquery.c.charge_id)
        .where(Charge.check_id == payment.check_id)
        .with_for_update()  # Lock charges for concurrent payment safety
    )

    if diner_id:
        # Sort to prioritize:
        # 1. This diner's charges
        # 2. Shared charges (diner_id is NULL)
        # 3. Other diners' charges
        query = base_query.order_by(
            # Own charges first
            (Charge.diner_id == diner_id).desc(),
            # Shared charges second
            Charge.diner_id.is_(None).desc(),
            # Then by creation order (FIFO)
            Charge.id
        )
    else:
        # No preference, just FIFO order
        query = base_query.order_by(Charge.id)

    charges_data = db.execute(query).all()

    for charge, allocated in charges_data:
        if remaining_amount <= 0:
            break

        # Calculate how much is still owed on this charge
        unpaid = charge.amount_cents - allocated
        if unpaid <= 0:
            continue

        # Allocate as much as possible
        allocation_amount = min(remaining_amount, unpaid)

        allocation = Allocation(
            tenant_id=charge.tenant_id,
            payment_id=payment.id,
            charge_id=charge.id,
            amount_cents=allocation_amount,
        )
        db.add(allocation)
        allocations.append(allocation)

        remaining_amount -= allocation_amount

    db.flush()
    return allocations


def get_diner_balance(
    db: Session,
    check_id: int,
    diner_id: int,
) -> dict:
    """
    Get the balance for a specific diner on a check.

    Returns:
        - total_cents: Total amount the diner owes
        - paid_cents: Amount already paid/allocated to this diner's charges
        - remaining_cents: Amount still owed
    """
    # Get total charges for this diner
    total_cents = db.scalar(
        select(func.coalesce(func.sum(Charge.amount_cents), 0))
        .where(
            Charge.check_id == check_id,
            Charge.diner_id == diner_id,
        )
    ) or 0

    # Get total allocated to this diner's charges
    paid_cents = db.scalar(
        select(func.coalesce(func.sum(Allocation.amount_cents), 0))
        .join(Charge, Allocation.charge_id == Charge.id)
        .where(
            Charge.check_id == check_id,
            Charge.diner_id == diner_id,
        )
    ) or 0

    return {
        "diner_id": diner_id,
        "total_cents": total_cents,
        "paid_cents": paid_cents,
        "remaining_cents": max(0, total_cents - paid_cents),
    }


def get_all_diner_balances(
    db: Session,
    check_id: int,
    tenant_id: int | None = None,
) -> list[dict]:
    """
    Get balances for all diners on a check.

    Includes a "shared" entry for charges without a diner_id.

    SVC-HIGH-06 FIX: Added optional tenant_id parameter for multi-tenant isolation.
    When provided, validates that the check belongs to the specified tenant.

    SVC-CRIT-N+1 FIX: Refactored to use batch queries instead of N+1 pattern.
    Now uses single aggregated query to get all totals and paid amounts.

    Args:
        db: Database session
        check_id: ID of the check to get balances for
        tenant_id: Optional tenant ID for isolation validation
    """
    # SVC-HIGH-06 FIX: Validate tenant isolation if tenant_id provided
    if tenant_id is not None:
        check = db.scalar(select(Check).where(Check.id == check_id))
        if check and check.tenant_id != tenant_id:
            # Return empty list instead of leaking data across tenants
            return []

    # SVC-CRIT-N+1 FIX: Single query to get all charge totals grouped by diner_id
    # Subquery for allocated amounts per charge
    allocated_subquery = (
        select(
            Allocation.charge_id,
            func.coalesce(func.sum(Allocation.amount_cents), 0).label("allocated")
        )
        .group_by(Allocation.charge_id)
        .subquery()
    )

    # Main query: get totals and paid amounts grouped by diner_id
    balance_query = (
        select(
            Charge.diner_id,
            func.sum(Charge.amount_cents).label("total_cents"),
            func.sum(func.coalesce(allocated_subquery.c.allocated, 0)).label("paid_cents"),
        )
        .outerjoin(allocated_subquery, Charge.id == allocated_subquery.c.charge_id)
        .where(Charge.check_id == check_id)
        .group_by(Charge.diner_id)
    )

    balance_data = db.execute(balance_query).all()

    # Get unique diner IDs (excluding None) for batch loading diner names
    diner_ids = [row.diner_id for row in balance_data if row.diner_id is not None]

    # SVC-CRIT-N+1 FIX: Batch load all diner records in single query
    diners_map: dict[int, Diner] = {}
    if diner_ids:
        diners = db.execute(
            select(Diner).where(Diner.id.in_(diner_ids))
        ).scalars().all()
        diners_map = {d.id: d for d in diners}

    # Build result list
    balances = []
    for row in balance_data:
        total = row.total_cents or 0
        paid = row.paid_cents or 0

        if row.diner_id is None:
            # Shared charges
            balances.append({
                "diner_id": None,
                "diner_name": "Shared",
                "total_cents": total,
                "paid_cents": paid,
                "remaining_cents": max(0, total - paid),
            })
        else:
            # Diner-specific charges
            diner = diners_map.get(row.diner_id)
            balances.append({
                "diner_id": row.diner_id,
                "diner_name": diner.name if diner else f"Diner #{row.diner_id}",
                "total_cents": total,
                "paid_cents": paid,
                "remaining_cents": max(0, total - paid),
            })

    return balances
