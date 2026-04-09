from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.activity_session import ActivitySession
from app.models.proposal import Proposal

FINALIZED_STATUS = "finalized"
ACTIVE_STATUS = "active"


def is_proposal_finalized(proposal: Proposal | None) -> bool:
    return bool(proposal and getattr(proposal, "status", ACTIVE_STATUS) == FINALIZED_STATUS)


def get_proposal_or_404(db: Session, proposal_id: int) -> Proposal:
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="Propuesta no encontrada.")
    return proposal


def require_proposal_not_finalized(
    proposal: Proposal | None,
    *,
    message: str = "Error: La propuesta está finalizada y solo permite lectura.",
) -> None:
    if is_proposal_finalized(proposal):
        raise HTTPException(status_code=409, detail=message)


def require_proposal_id_not_finalized(
    db: Session,
    proposal_id: int | None,
    *,
    message: str = "Error: La propuesta está finalizada y solo permite lectura.",
) -> Proposal | None:
    if not proposal_id:
        return None
    proposal = get_proposal_or_404(db, proposal_id)
    require_proposal_not_finalized(proposal, message=message)
    return proposal


def get_session_proposal(db: Session, session: ActivitySession) -> Proposal | None:
    if not session.proposal_id:
        return None
    return db.get(Proposal, session.proposal_id)


def require_session_proposal_not_finalized(
    db: Session,
    session: ActivitySession,
    *,
    message: str = "Error: La propuesta de esta sesión está finalizada y no puede modificarse.",
) -> Proposal | None:
    proposal = get_session_proposal(db, session)
    require_proposal_not_finalized(proposal, message=message)
    return proposal
