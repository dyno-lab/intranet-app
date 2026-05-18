from __future__ import annotations

from fastapi import HTTPException

from app.models.activity_code import ActivityCode


def activity_code_allowed_for_proposal(activity_code: ActivityCode, proposal_id: int | None) -> bool:
    return activity_code.proposal_id is None or activity_code.proposal_id == proposal_id


def require_activity_code_allowed_for_proposal(
    activity_code: ActivityCode,
    proposal_id: int | None,
    *,
    message: str = "La actividad no pertenece a la propuesta seleccionada.",
) -> None:
    if not activity_code_allowed_for_proposal(activity_code, proposal_id):
        raise HTTPException(status_code=409, detail=message)
