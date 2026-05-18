from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import date

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.core.proposal_guard import require_proposal_id_not_finalized
from app.core.session_rules import require_activity_code_allowed_for_proposal
from app.models.activity_session import ActivitySession
from app.models.activity_code import ActivityCode
from app.models.employee import Employee
from app.models.proposal import Proposal
from app.models.user import User
from app.schemas.session import SessionCreate, SessionOut

router = APIRouter()

@router.get("", response_model=list[SessionOut])
def list_sessions(from_date: date | None = None, to_date: date | None = None, db: Session = Depends(get_db)):
    stmt = select(ActivitySession)
    if from_date:
        stmt = stmt.where(ActivitySession.session_date >= from_date)
    if to_date:
        stmt = stmt.where(ActivitySession.session_date <= to_date)
    stmt = stmt.order_by(ActivitySession.session_date.desc())
    return list(db.execute(stmt).scalars().all())

@router.post("", response_model=SessionOut)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validar FKs
    code = db.get(ActivityCode, payload.activity_code_id)
    if not code:
        raise HTTPException(status_code=404, detail="activity_code_id no existe")

    emp = db.get(Employee, payload.employee_id)
    if not emp:
        raise HTTPException(status_code=404, detail="employee_id no existe")

    if payload.proposal_id:
        proposal = db.get(Proposal, payload.proposal_id)
        if not proposal:
            raise HTTPException(status_code=404, detail="proposal_id no existe")
        require_proposal_id_not_finalized(
            db,
            payload.proposal_id,
            message="La propuesta está finalizada y no permite crear sesiones.",
        )

    require_activity_code_allowed_for_proposal(
        code,
        payload.proposal_id,
        message="La actividad no pertenece a la propuesta seleccionada",
    )

    obj = ActivitySession(
        **payload.model_dump(),
        created_by_user_id=current_user.user_id,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
