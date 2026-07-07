from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.activity_code import ActivityCode
from app.services.activity_proposals import activity_code_allowed_for_proposal as _activity_code_allowed_for_proposal


def activity_code_allowed_for_proposal(db: Session, activity_code: ActivityCode, proposal_id: int | None) -> bool:
    return _activity_code_allowed_for_proposal(db, activity_code, proposal_id)


def require_activity_code_allowed_for_proposal(
    db: Session,
    activity_code: ActivityCode,
    proposal_id: int | None,
    *,
    message: str = "La actividad no pertenece a la propuesta seleccionada.",
) -> None:
    if not activity_code_allowed_for_proposal(db, activity_code, proposal_id):
        raise HTTPException(status_code=409, detail=message)
