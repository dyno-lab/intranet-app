from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import date

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.core.proposal_guard import require_proposal_id_not_finalized
from app.core.record_identifiers import normalized_residential_code
from app.core.residential_scope import (
    has_global_residential_access,
    require_record_residential_id,
    require_write_residential_id,
)
from app.core.session_rules import require_activity_code_allowed_for_proposal
from app.models.activity_session import ActivitySession
from app.models.activity_code import ActivityCode
from app.models.employee import Employee
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.user import User
from app.schemas.session import SessionCreate, SessionOut
from app.services.session_control_numbers import persist_session_control_number

router = APIRouter()

@router.get("", response_model=list[SessionOut])
def list_sessions(
    request: Request,
    from_date: date | None = None,
    to_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(ActivitySession)
    if not has_global_residential_access(current_user):
        residential_id = require_record_residential_id(request, current_user)
        stmt = stmt.where(ActivitySession.residential_id == residential_id)
    if from_date:
        stmt = stmt.where(ActivitySession.session_date >= from_date)
    if to_date:
        stmt = stmt.where(ActivitySession.session_date <= to_date)
    stmt = stmt.order_by(ActivitySession.session_date.desc())
    return list(db.execute(stmt).scalars().all())

@router.post("", response_model=SessionOut)
def create_session(
    payload: SessionCreate,
    request: Request,
    residential_id: int | None = None,
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
        db,
        code,
        payload.proposal_id,
        message="La actividad no pertenece a la propuesta seleccionada",
    )

    record_residential_id = require_write_residential_id(
        request,
        current_user,
        db,
        residential_id,
    )
    residential = db.get(Residential, record_residential_id)
    residential_code = normalized_residential_code(residential.code if residential else None)
    if not residential or not residential.is_active or not residential_code:
        raise HTTPException(status_code=409, detail="El residencial activo no tiene un código válido.")

    obj = ActivitySession(
        **payload.model_dump(),
        residential_id=record_residential_id,
        created_by_user_id=current_user.user_id,
    )
    db.add(obj)
    db.flush()
    persist_session_control_number(db, obj, residential_code)
    db.commit()
    db.refresh(obj)
    return obj
