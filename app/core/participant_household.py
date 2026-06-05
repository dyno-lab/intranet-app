from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.participant import Participant
from app.models.user import User


def _normalized_address_value(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def require_head_of_household_allowed(
    db: Session,
    *,
    residential_id: int | None,
    edificio: str | None,
    apart: str | None,
    exclude_participant_id: int | None = None,
) -> None:
    if residential_id is None:
        raise HTTPException(
            status_code=409,
            detail="Error: No se puede marcar jefe de familia porque el participante no tiene un residencial asociado.",
        )

    normalized_edificio = _normalized_address_value(edificio)
    normalized_apart = _normalized_address_value(apart)
    if not normalized_edificio or not normalized_apart:
        raise HTTPException(
            status_code=409,
            detail="Error: Para marcar jefe de familia debe indicar edificio y apartamento.",
        )

    stmt = (
        select(Participant)
        .join(User, User.user_id == Participant.created_by_user_id)
        .where(
            User.residential_id == residential_id,
            Participant.is_head_of_household == True,  # noqa: E712
        )
    )
    if exclude_participant_id is not None:
        stmt = stmt.where(Participant.participant_id != exclude_participant_id)

    candidates = db.execute(stmt).scalars().all()
    for participant in candidates:
        if (
            _normalized_address_value(participant.edificio) == normalized_edificio
            and _normalized_address_value(participant.apart) == normalized_apart
        ):
            raise HTTPException(
                status_code=409,
                detail="Error: Ya existe un jefe de familia marcado para ese residencial, edificio y apartamento.",
            )
