from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.core.community_access import csrf_token, validate_csrf
from app.core.residential_scope import has_global_residential_access
from app.models.participant import Participant
from app.models.participant_transfer import ParticipantTransfer
from app.models.residential import Residential
from app.models.user import User
from app.services.participant_transfers import preview_transfer, transfer_participant

router = APIRouter(prefix="/ui/new-list")
templates = Jinja2Templates(directory="app/templates")


def _access(user):
    if user.role not in {"admin", "supervisor"} or not has_global_residential_access(user):
        raise HTTPException(403, "Entre como administrador o supervisor con acceso general para realizar un traslado.")


def _render(request, db, user, participant_id, *, values=None, preview=None, error=None, status_code=200):
    participant = db.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(404, "Participante no encontrado.")
    residentials = list(db.scalars(select(Residential).order_by(Residential.name)))
    residential_map = {item.residential_id: item for item in residentials}
    history = db.execute(select(ParticipantTransfer, User.username)
                         .join(User, User.user_id == ParticipantTransfer.created_by_user_id)
                         .where(ParticipantTransfer.participant_id == participant_id)
                         .order_by(ParticipantTransfer.effective_date.desc(), ParticipantTransfer.transfer_id.desc())).all()
    return templates.TemplateResponse(request=request, name="ui/participant_transfer.html", status_code=status_code,
        context={"request": request, "current_user": user, "p": participant,
                 "source": residential_map.get(participant.residential_id), "residential_map": residential_map,
                 "destinations": [r for r in residentials if r.is_active and r.residential_id != participant.residential_id],
                 "values": values or {"effective_date": date.today().isoformat(),
                                       "expected_residential_id": participant.residential_id},
                 "preview": preview, "error": error, "csrf_token": csrf_token(request),
                 "today": date.today().isoformat(), "history": history})


@router.get("/{participant_id}/transfer")
def transfer_form(participant_id: int, request: Request, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    _access(current_user)
    return _render(request, db, current_user, participant_id)


@router.post("/{participant_id}/transfer")
def transfer_submit(participant_id: int, request: Request, destination_id: int = Form(...),
                    expected_residential_id: int = Form(...), effective_date: date = Form(...),
                    reason: str = Form(...), edificio: str = Form(""), apart: str = Form(""),
                    token: str = Form(...), mode: str = Form("preview"),
                    expected_expediente_num: str = Form(""), db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    _access(current_user)
    validate_csrf(request, token)
    values = {"destination_id": destination_id, "expected_residential_id": expected_residential_id,
              "effective_date": effective_date.isoformat(), "reason": reason, "edificio": edificio, "apart": apart}
    arguments = {**values, "effective_date": effective_date, "participant_id": participant_id, "actor": current_user}
    try:
        if mode == "edit":
            return _render(request, db, current_user, participant_id, values=values)
        if mode == "preview":
            preview = preview_transfer(db, **arguments)
            return _render(request, db, current_user, participant_id, values=values, preview=preview)
        if mode != "confirm" or not expected_expediente_num:
            raise HTTPException(422, "Revise el traslado antes de confirmarlo.")
        audit = transfer_participant(db, expected_expediente_num=expected_expediente_num, **arguments)
        new_number = audit.new_expediente_num
        db.commit()
    except HTTPException as exc:
        db.rollback()
        return _render(request, db, current_user, participant_id, values=values, error=str(exc.detail), status_code=exc.status_code)
    except IntegrityError:
        db.rollback()
        return _render(request, db, current_user, participant_id, values=values,
                       error="La inscripción o numeración cambió. Revise nuevamente el traslado.", status_code=409)
    return RedirectResponse(f"/ui/new-list/{participant_id}?" + urlencode({
        "msg": f"Traslado completado. Nuevo expediente: {new_number}. El historial anterior se conserva."}), status_code=303)
