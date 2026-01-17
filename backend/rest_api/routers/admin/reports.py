"""
Reports endpoints for sales analytics and statistics.
"""

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter

from rest_api.routers.admin._base import (
    Depends, HTTPException, Session, select, func,
    get_db, current_user, Round, RoundItem, Product, Table, TableSession,
    Payment,
)
from rest_api.routers.admin_schemas import (
    ReportsSummaryOutput, DailySalesOutput, TopProductOutput,
)


router = APIRouter(tags=["admin-reports"])


@router.get("/reports/summary", response_model=ReportsSummaryOutput)
def get_reports_summary(
    branch_id: int | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> ReportsSummaryOutput:
    """Get summary statistics for reports."""
    # Get user's branches
    user_branch_ids = user.get("branch_ids", [])
    if branch_id and branch_id not in user_branch_ids:
        raise HTTPException(status_code=403, detail="No access to this branch")
    branch_ids = [branch_id] if branch_id else user_branch_ids

    # Date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Get total revenue from paid payments
    total_revenue = db.scalar(
        select(func.sum(Payment.amount_cents))
        .where(
            Payment.branch_id.in_(branch_ids),
            Payment.status == "APPROVED",
            Payment.created_at >= start_date,
        )
    ) or 0

    # Get total orders (rounds with status != DRAFT, CANCELED)
    total_orders = db.scalar(
        select(func.count(Round.id))
        .where(
            Round.branch_id.in_(branch_ids),
            Round.status.in_(["SUBMITTED", "IN_KITCHEN", "READY", "SERVED"]),
            Round.submitted_at >= start_date,
        )
    ) or 0

    # Calculate average order value
    avg_order = total_revenue // total_orders if total_orders > 0 else 0

    # Get total sessions
    total_sessions = db.scalar(
        select(func.count(TableSession.id))
        .join(Table, TableSession.table_id == Table.id)
        .where(
            Table.branch_id.in_(branch_ids),
            TableSession.opened_at >= start_date,
        )
    ) or 0

    # Get busiest hour (most orders)
    busiest_hour = db.scalar(
        select(func.extract("hour", Round.submitted_at))
        .where(
            Round.branch_id.in_(branch_ids),
            Round.submitted_at >= start_date,
            Round.submitted_at.isnot(None),
        )
        .group_by(func.extract("hour", Round.submitted_at))
        .order_by(func.count().desc())
        .limit(1)
    )

    return ReportsSummaryOutput(
        total_revenue_cents=total_revenue,
        total_orders=total_orders,
        avg_order_value_cents=avg_order,
        total_sessions=total_sessions,
        busiest_hour=int(busiest_hour) if busiest_hour is not None else None,
    )


@router.get("/reports/daily-sales", response_model=list[DailySalesOutput])
def get_daily_sales(
    branch_id: int | None = None,
    days: int = 30,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[DailySalesOutput]:
    """Get daily sales breakdown."""
    # Get user's branches
    user_branch_ids = user.get("branch_ids", [])
    if branch_id and branch_id not in user_branch_ids:
        raise HTTPException(status_code=403, detail="No access to this branch")
    branch_ids = [branch_id] if branch_id else user_branch_ids

    # Date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Get daily totals
    daily_stats = db.execute(
        select(
            func.date(Payment.created_at).label("date"),
            func.sum(Payment.amount_cents).label("total"),
            func.count(Payment.id).label("count"),
        )
        .where(
            Payment.branch_id.in_(branch_ids),
            Payment.status == "APPROVED",
            Payment.created_at >= start_date,
        )
        .group_by(func.date(Payment.created_at))
        .order_by(func.date(Payment.created_at))
    ).all()

    return [
        DailySalesOutput(
            date=str(row.date),
            total_sales_cents=row.total or 0,
            order_count=row.count or 0,
            avg_order_cents=(row.total // row.count) if row.count > 0 else 0,
        )
        for row in daily_stats
    ]


@router.get("/reports/top-products", response_model=list[TopProductOutput])
def get_top_products(
    branch_id: int | None = None,
    days: int = 30,
    limit: int = 10,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
) -> list[TopProductOutput]:
    """Get top selling products."""
    # Get user's branches
    user_branch_ids = user.get("branch_ids", [])
    if branch_id and branch_id not in user_branch_ids:
        raise HTTPException(status_code=403, detail="No access to this branch")
    branch_ids = [branch_id] if branch_id else user_branch_ids

    # Date range
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Get top products by quantity sold
    top_products = db.execute(
        select(
            RoundItem.product_id,
            Product.name.label("product_name"),
            func.sum(RoundItem.qty).label("quantity"),
            func.sum(RoundItem.qty * RoundItem.unit_price_cents).label("revenue"),
        )
        .join(Round, RoundItem.round_id == Round.id)
        .join(Product, RoundItem.product_id == Product.id)
        .where(
            Round.branch_id.in_(branch_ids),
            Round.status.in_(["SUBMITTED", "IN_KITCHEN", "READY", "SERVED"]),
            Round.submitted_at >= start_date,
        )
        .group_by(RoundItem.product_id, Product.name)
        .order_by(func.sum(RoundItem.qty).desc())
        .limit(limit)
    ).all()

    return [
        TopProductOutput(
            product_id=row.product_id,
            product_name=row.product_name,
            quantity_sold=row.quantity or 0,
            total_revenue_cents=row.revenue or 0,
        )
        for row in top_products
    ]
