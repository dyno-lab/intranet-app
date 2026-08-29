from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.core.config import settings
from app.core.record_identifiers import build_expediente_number, normalized_residential_code
from app.core.participant_household import require_head_of_household_allowed
from app.core.residential_scope import (
    has_global_residential_access,
    require_record_residential_id,
    require_write_residential_id,
)
from app.models.participant import Participant
from app.models.residential import Residential
from app.models.user import User
from app.schemas.participant import ParticipantCreate, ParticipantOut

router = APIRouter()

# LIMITACIÓN TEMPORAL FASE 1:
# Participant todavía funciona como listado operativo global y aún no está separado
# en Person / ProposalParticipant. Por eso, el cierre por propuesta no puede
# bloquear creación/edición de participantes con precisión total en esta fase.

@router.post("", response_model=ParticipantOut)
def create_participant(
    payload: ParticipantCreate,
    request: Request,
    residential_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record_residential_id = require_write_residential_id(
        request,
        current_user,
        db,
        residential_id,
    )
    residential = db.get(Residential, record_residential_id)
    if residential is None or not residential.is_active:
        raise HTTPException(status_code=409, detail="El residencial activo no está disponible.")

    payload_data = payload.model_dump()
    if settings.PHASE2_EXPEDIENTE_ENABLED:
        if payload.exp_year is None:
            raise HTTPException(status_code=422, detail="exp_year es requerido")
        residential_code = normalized_residential_code(residential.code)
        if not residential_code:
            raise HTTPException(status_code=409, detail="El residencial activo no tiene un código válido.")
        seq4 = (payload.exp_seq4 or "").strip()
        if len(seq4) != 4 or not seq4.isdigit():
            raise HTTPException(status_code=422, detail="exp_seq4 debe contener exactamente 4 dígitos")
        used_seq = db.execute(
            select(Participant).where(
                Participant.residential_id == record_residential_id,
                Participant.exp_seq4 == seq4,
            )
        ).scalar_one_or_none()
        if used_seq:
            raise HTTPException(status_code=409, detail="exp_seq4 ya existe para este residencial")
        payload_data["exp_employee_initials"] = residential_code
        payload_data["exp_seq4"] = seq4
        payload_data["expediente_num"] = build_expediente_number(
            year=payload.exp_year,
            residential_code=residential_code,
            sequence=seq4,
        )
    else:
        payload_data["expediente_num"] = (payload.expediente_num or "").strip()
        if not payload_data["expediente_num"]:
            raise HTTPException(status_code=422, detail="expediente_num es requerido")

    existing = db.execute(
        select(Participant).where(Participant.expediente_num == payload_data["expediente_num"])
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="expediente_num ya existe")
    marked_as_head = bool(payload_data.get("is_head_of_household"))
    if marked_as_head:
        require_head_of_household_allowed(
            db,
            residential_id=record_residential_id,
            edificio=payload_data.get("edificio"),
            apart=payload_data.get("apart"),
        )

    p = Participant(
        **payload_data,
        residential_id=record_residential_id,
        created_by_user_id=current_user.user_id,
    )
    db.add(p)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="El expediente o la secuencia ya existe para este residencial.",
        )
    db.refresh(p)
    return p

@router.get("", response_model=list[ParticipantOut])
def list_participants(
    request: Request,
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Participant)
    if not has_global_residential_access(current_user):
        residential_id = require_record_residential_id(request, current_user)
        stmt = stmt.where(Participant.residential_id == residential_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (Participant.expediente_num.like(like)) |
            (Participant.nombre.like(like)) |
            (Participant.apellido_paterno.like(like))
        )
    return list(db.execute(stmt).scalars().all())
