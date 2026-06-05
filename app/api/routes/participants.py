from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db
from app.core.auth import get_current_user, is_admin_or_supervisor
from app.core.participant_household import require_head_of_household_allowed
from app.models.participant import Participant
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.execute(select(Participant).where(Participant.expediente_num == payload.expediente_num)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="expediente_num ya existe")

    payload_data = payload.model_dump()
    marked_as_head = bool(payload_data.get("is_head_of_household"))
    if marked_as_head:
        require_head_of_household_allowed(
            db,
            residential_id=getattr(current_user, "residential_id", None),
            edificio=payload_data.get("edificio"),
            apart=payload_data.get("apart"),
        )

    p = Participant(
        **payload_data,
        created_by_user_id=current_user.user_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p

@router.get("", response_model=list[ParticipantOut])
def list_participants(
    search: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Participant)
    if not is_admin_or_supervisor(current_user):
        stmt = stmt.where(Participant.created_by_user_id == current_user.user_id)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (Participant.expediente_num.like(like)) |
            (Participant.nombre.like(like)) |
            (Participant.apellido_paterno.like(like))
        )
    return list(db.execute(stmt).scalars().all())
