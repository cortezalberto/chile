"""
Round Domain Service.

CRIT-01 FIX: Extracted from diner/orders.py for thin controller pattern.
Handles all round-related business logic.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from shared.config.logging import get_logger
from shared.infrastructure.db import safe_commit
from rest_api.models import (
    Table,
    TableSession,
    Round,
    RoundItem,
    Product,
    BranchProduct,
    CartItem,
)
from shared.utils.schemas import (
    SubmitRoundRequest,
    SubmitRoundResponse,
    RoundOutput,
    RoundItemOutput,
)

if TYPE_CHECKING:
    from fastapi import BackgroundTasks

logger = get_logger(__name__)


class RoundNotFoundError(Exception):
    """Round not found."""
    pass


class SessionNotActiveError(Exception):
    """Session is not active."""
    pass


class ProductNotAvailableError(Exception):
    """Product not available in branch."""
    def __init__(self, product_id: int):
        self.product_id = product_id
        super().__init__(f"Product {product_id} not available")


class DuplicateRoundError(Exception):
    """Duplicate round detected (idempotency)."""
    def __init__(self, round_id: int, round_number: int, status: str):
        self.round_id = round_id
        self.round_number = round_number
        self.status = status
        super().__init__(f"Round {round_id} already exists")


class RoundService:
    """
    Domain service for Round operations.
    
    CRIT-01 FIX: Extracted from diner/orders.py router.
    Encapsulates all business logic for round submission and retrieval.
    """
    
    def __init__(self, db: Session):
        self._db = db
    
    def check_idempotency(
        self,
        session_id: int,
        idempotency_key: str | None,
    ) -> Round | None:
        """
        Check if a round with this idempotency key already exists.
        
        Returns the existing round if found, None otherwise.
        """
        if not idempotency_key:
            return None
        
        existing = self._db.scalar(
            select(Round).where(
                Round.table_session_id == session_id,
                Round.idempotency_key == idempotency_key,
                Round.status != "CANCELED",
            )
        )
        return existing
    
    def validate_session(self, session_id: int) -> TableSession:
        """
        Validate session is active.
        
        Raises SessionNotActiveError if not active.
        """
        session = self._db.scalar(
            select(TableSession).where(
                TableSession.id == session_id,
                TableSession.status.in_(["OPEN", "PAYING"]),
            )
        )
        if not session:
            raise SessionNotActiveError("Session is not active or does not exist")
        return session
    
    def get_table_sector_id(self, table_id: int) -> int | None:
        """Get sector_id for a table, for targeted waiter notifications."""
        table = self._db.scalar(select(Table).where(Table.id == table_id))
        return table.sector_id if table else None
    
    def submit_round(
        self,
        tenant_id: int,
        branch_id: int,
        session_id: int,
        table_id: int,
        request: SubmitRoundRequest,
        idempotency_key: str | None = None,
    ) -> tuple[Round, int]:
        """
        Submit a new round of orders.
        
        Returns (round, sector_id) tuple for event publishing.
        Raises:
            DuplicateRoundError: If idempotency check finds existing round
            SessionNotActiveError: If session is not active
            ProductNotAvailableError: If any product is not available
        """
        # Check idempotency
        existing = self.check_idempotency(session_id, idempotency_key)
        if existing:
            raise DuplicateRoundError(
                existing.id,
                existing.round_number,
                existing.status,
            )
        
        # Validate session
        self.validate_session(session_id)
        
        # Get sector for notifications
        sector_id = self.get_table_sector_id(table_id)
        
        # Lock session to prevent race condition
        locked_session = self._db.scalar(
            select(TableSession)
            .where(TableSession.id == session_id)
            .with_for_update()
        )
        if not locked_session:
            raise SessionNotActiveError("Session not found")
        
        # Get next round number
        max_round = self._db.scalar(
            select(func.max(Round.round_number))
            .where(Round.table_session_id == session_id)
        ) or 0
        next_round_number = max_round + 1
        
        # Batch fetch products and prices
        product_ids = [item.product_id for item in request.items]
        products_query = self._db.execute(
            select(Product, BranchProduct)
            .join(BranchProduct, Product.id == BranchProduct.product_id)
            .where(
                Product.id.in_(product_ids),
                Product.is_active.is_(True),
                BranchProduct.branch_id == branch_id,
                BranchProduct.is_available == True,
            )
        ).all()
        
        product_lookup = {
            product.id: (product, branch_product)
            for product, branch_product in products_query
        }
        
        # Validate all products available
        for item in request.items:
            if item.product_id not in product_lookup:
                raise ProductNotAvailableError(item.product_id)
        
        # Create round
        new_round = Round(
            tenant_id=tenant_id,
            branch_id=branch_id,
            table_session_id=session_id,
            round_number=next_round_number,
            status="PENDING",
            submitted_at=datetime.now(timezone.utc),
            idempotency_key=idempotency_key,
        )
        self._db.add(new_round)
        self._db.flush()
        
        # Create round items
        round_items = []
        for item in request.items:
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
            round_items.append(round_item)
        
        self._db.add_all(round_items)
        
        # Clear cart after creating round
        self._db.execute(
            CartItem.__table__.delete().where(CartItem.session_id == session_id)
        )
        
        # Commit
        safe_commit(self._db)
        self._db.refresh(new_round)
        
        logger.info(
            "Round submitted",
            round_id=new_round.id,
            session_id=session_id,
            items_count=len(round_items),
        )
        
        return new_round, sector_id
    
    def get_session_rounds(
        self,
        session_id: int,
    ) -> list[RoundOutput]:
        """
        Get all rounds for a session with batch loading.
        
        Uses batch loading to prevent N+1 queries.
        """
        rounds = self._db.execute(
            select(Round)
            .where(Round.table_session_id == session_id)
            .order_by(Round.round_number)
        ).scalars().all()
        
        if not rounds:
            return []
        
        # Batch load all items with products
        round_ids = [r.id for r in rounds]
        all_items = self._db.execute(
            select(RoundItem, Product)
            .join(Product, RoundItem.product_id == Product.id)
            .where(RoundItem.round_id.in_(round_ids))
        ).all()
        
        # Group by round_id
        items_by_round: dict[int, list[tuple]] = {rid: [] for rid in round_ids}
        for item, product in all_items:
            items_by_round[item.round_id].append((item, product))
        
        # Build output
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
    
    def confirm_round(self, round_id: int, user_id: int) -> Round:
        """
        Confirm a pending round (waiter verification).
        
        Changes status from PENDING to CONFIRMED.
        """
        round_obj = self._db.scalar(
            select(Round).where(Round.id == round_id)
        )
        if not round_obj:
            raise RoundNotFoundError(f"Round {round_id} not found")
        
        if round_obj.status != "PENDING":
            raise ValueError(f"Cannot confirm round with status {round_obj.status}")
        
        round_obj.status = "CONFIRMED"
        round_obj.confirmed_by_user_id = user_id
        round_obj.confirmed_at = datetime.now(timezone.utc)
        
        safe_commit(self._db)
        
        logger.info("Round confirmed", round_id=round_id, user_id=user_id)
        
        return round_obj
    
    def submit_to_kitchen(self, round_id: int, user_id: int) -> Round:
        """
        Submit a confirmed round to kitchen.
        
        Changes status from CONFIRMED to SUBMITTED.
        """
        round_obj = self._db.scalar(
            select(Round).where(Round.id == round_id)
        )
        if not round_obj:
            raise RoundNotFoundError(f"Round {round_id} not found")
        
        if round_obj.status not in ("CONFIRMED", "PENDING"):
            raise ValueError(f"Cannot submit round with status {round_obj.status}")
        
        round_obj.status = "SUBMITTED"
        round_obj.sent_to_kitchen_at = datetime.now(timezone.utc)
        
        safe_commit(self._db)
        
        logger.info("Round submitted to kitchen", round_id=round_id, user_id=user_id)
        
        return round_obj
    
    def cancel_round(self, round_id: int, user_id: int) -> Round:
        """
        Cancel a round.
        
        Only PENDING or CONFIRMED rounds can be canceled.
        """
        round_obj = self._db.scalar(
            select(Round).where(Round.id == round_id)
        )
        if not round_obj:
            raise RoundNotFoundError(f"Round {round_id} not found")
        
        if round_obj.status not in ("PENDING", "CONFIRMED"):
            raise ValueError(f"Cannot cancel round with status {round_obj.status}")
        
        round_obj.status = "CANCELED"
        round_obj.canceled_at = datetime.now(timezone.utc)
        
        safe_commit(self._db)
        
        logger.info("Round canceled", round_id=round_id, user_id=user_id)
        
        return round_obj
