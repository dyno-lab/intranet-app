from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.api.deps import get_db
from app.models.participant import Participant
from app.schemas.participant import ParticipantCreate, ParticipantOut

router = APIRouter()

# LIMITACIÓN TEMPORAL FASE 1:
# Participant todavía funciona como listado operativo global y aún no está separado
# en Person / ProposalParticipant. Por eso, el cierre por propuesta no puede
# bloquear creación/edición de participantes con precisión total en esta fase.

@router.post("", response_model=ParticipantOut)
def create_participant(payload: ParticipantCreate, db: Session = Depends(get_db)):
    existing = db.execute(select(Participant).where(Participant.expediente_num == payload.expediente_num)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="expediente_num ya existe")

    p = Participant(**payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p

@router.get("", response_model=list[ParticipantOut])
def list_participants(search: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Participant)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(
            (Participant.expediente_num.like(like)) |
            (Participant.nombre.like(like)) |
            (Participant.apellido_paterno.like(like))
        )
    return list(db.execute(stmt).scalars().all())