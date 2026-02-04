"""
Diner Domain Service.

CRIT-01 FIX: Handles diner registration and history.
"""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from shared.config.logging import get_logger
from shared.infrastructure.db import safe_commit
from rest_api.models import (
    Diner,
    TableSession,
    Branch,
)
from shared.utils.schemas import (
    RegisterDinerRequest,
    DinerOutput,
    DeviceHistoryOutput,
    DeviceVisitOutput,
)

logger = get_logger(__name__)


class SessionNotActiveError(Exception):
    """Session is not active."""
    pass


class DinerService:
    """
    Domain service for Diner operations.
    
    CRIT-01 FIX: Extracted from diner/orders.py router.
    """
    
    def __init__(self, db: Session):
        self._db = db
    
    def validate_session(self, session_id: int) -> TableSession:
        """Validate session is active."""
        session = self._db.scalar(
            select(TableSession).where(
                TableSession.id == session_id,
                TableSession.status.in_(["OPEN", "PAYING"]),
            )
        )
        if not session:
            raise SessionNotActiveError("Session is not active or does not exist")
        return session
    
    def register_diner(
        self,
        tenant_id: int,
        branch_id: int,
        session_id: int,
        request: RegisterDinerRequest,
    ) -> tuple[Diner, bool]:
        """
        Register a diner at a table session.
        
        Returns (diner, is_new) tuple.
        If diner with same local_id exists, returns existing diner.
        """
        # Validate session
        self.validate_session(session_id)
        
        # Check for existing diner (idempotency)
        if request.local_id:
            existing = self._db.scalar(
                select(Diner).where(
                    Diner.session_id == session_id,
                    Diner.local_id == request.local_id,
                )
            )
            if existing:
                # Update device_id if provided
                if request.device_id and not existing.device_id:
                    existing.device_id = request.device_id
                    existing.device_fingerprint = request.device_fingerprint
                    try:
                        safe_commit(self._db)
                        self._db.refresh(existing)
                    except Exception as e:
                        logger.warning("Failed to update device_id", error=str(e))
                
                return existing, False
        
        # Create new diner
        diner = Diner(
            tenant_id=tenant_id,
            branch_id=branch_id,
            session_id=session_id,
            name=request.name,
            color=request.color,
            local_id=request.local_id,
            device_id=request.device_id,
            device_fingerprint=request.device_fingerprint,
        )
        self._db.add(diner)
        safe_commit(self._db)
        self._db.refresh(diner)
        
        logger.info(
            "Diner registered",
            diner_id=diner.id,
            session_id=session_id,
        )
        
        return diner, True
    
    def get_session_diners(self, session_id: int) -> list[DinerOutput]:
        """Get all diners for a session."""
        diners = self._db.execute(
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
    
    def get_device_history(
        self,
        device_id: str,
        tenant_id: int,
    ) -> DeviceHistoryOutput:
        """
        Get visit history for a device.
        
        FASE 1: Device tracking for cross-session recognition.
        """
        # Get all diners with this device_id
        diners_with_sessions = self._db.execute(
            select(Diner, TableSession, Branch)
            .join(TableSession, Diner.session_id == TableSession.id)
            .join(Branch, Diner.branch_id == Branch.id)
            .where(
                Diner.device_id == device_id,
                Diner.tenant_id == tenant_id,
            )
            .order_by(TableSession.opened_at.desc())
        ).all()
        
        visits = [
            DeviceVisitOutput(
                session_id=session.id,
                branch_id=branch.id,
                branch_name=branch.name,
                visited_at=session.opened_at,
                table_code=None,  # Could be added if needed
            )
            for diner, session, branch in diners_with_sessions
        ]
        
        return DeviceHistoryOutput(
            device_id=device_id,
            visit_count=len(visits),
            first_visit=visits[-1].visited_at if visits else None,
            last_visit=visits[0].visited_at if visits else None,
            visits=visits[:10],  # Last 10 visits
        )
