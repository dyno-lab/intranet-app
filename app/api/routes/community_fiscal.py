from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.community_access import (CommunityContext, csrf_token, require_community_admin,
    require_community_context, require_community_writer, require_programs, validate_csrf)
from app.models.community import CPFiscalYear, CPParticipant, CPParticipantProgram, CPProgram
from app.models.community_fiscal import CPFiscalEnrollment, CPFiscalParticipant, CPFiscalState, CPEnrollmentPeriod
from app.services.community_fiscal import (build_participant_snapshot, discharge_participant, enroll_participant,
    reactivate_participant, set_fiscal_lock, set_fiscal_status, set_snapshot_freeze, snapshot_for_participant, sync_participants)

router = APIRouter(prefix="/community", tags=["community-fiscal"])
templates = Jinja2Templates(directory="app/templates")


def _supervisor(context: CommunityContext = Depends(require_community_context)) -> CommunityContext:
    if context.role not in {"admin", "supervisor"}:
        raise HTTPException(403, "La sincronización requiere Supervisor o Administrador de Comunidad.")
    return context


def _render(request, name, context, **values):
    return templates.TemplateResponse(request=request, name=f"community/{name}.html", context={
        "request": request, "current_user": context.user, "cp": context,
        "csrf_token": csrf_token(request), "today": date.today(),
        "message": request.query_params.get("msg"), "error": request.query_params.get("error"), **values,
    })


def _redirect(path, fiscal_year_id, *, message=None, error=None):
    return RedirectResponse(path + "?" + urlencode({"fiscal_year_id": fiscal_year_id,
                            **({"error": error} if error else {"msg": message})}), status_code=303)


def _years(db, fiscal_year_id):
    years = db.scalars(select(CPFiscalYear).where(CPFiscalYear.is_active == True)  # noqa: E712
                      .order_by(CPFiscalYear.start_date.desc())).all()
    selected = next((year for year in years if year.fiscal_year_id == fiscal_year_id), None)
    if fiscal_year_id is not None and selected is None:
        raise HTTPException(404, "Año fiscal no disponible.")
    return years, selected or (years[0] if years else None)


def _participant_query(context):
    return select(CPParticipant).where(select(CPParticipantProgram.participant_id).where(
        CPParticipantProgram.participant_id == CPParticipant.participant_id,
        CPParticipantProgram.program_id.in_(context.visible_program_ids),
    ).exists())


def _visible_participant(db, context, participant_id):
    participant = db.scalar(_participant_query(context).where(CPParticipant.participant_id == participant_id))
    if participant is None:
        raise HTTPException(404, "Expediente no disponible en sus programas.")
    return participant


@router.get("/fiscal-participants")
def fiscal_participants(request: Request, fiscal_year_id: int | None = None, q: str = "", page: int = 1,
                        db: Session = Depends(get_db), context: CommunityContext = Depends(_supervisor)):
    years, selected = _years(db, fiscal_year_id)
    page = max(1, page)
    query = _participant_query(context)
    term = q.strip()[:150]
    if term:
        query = query.where(or_(*[field.contains(term, autoescape=True) for field in (
            CPParticipant.expediente_num, CPParticipant.nombre, CPParticipant.apellido_paterno,
            CPParticipant.apellido_materno)]))
    participants = db.scalars(query.order_by(CPParticipant.participant_id).offset((page - 1) * 50).limit(51)).all()
    rows = []
    for participant in participants[:50] if selected else []:
        snapshot = snapshot_for_participant(db, participant.participant_id, selected.fiscal_year_id)
        status = "Sin sincronizar" if snapshot is None else (
            "Cambios pendientes" if snapshot != build_participant_snapshot(db, participant) else "Sincronizado")
        rows.append((participant, status))
    state = db.get(CPFiscalState, selected.fiscal_year_id) if selected else None
    return _render(request, "fiscal_participants", context, years=years, selected_year=selected,
                   state=state, rows=rows, q=term, page=page, has_next=len(participants) > 50,
                   query_base={"fiscal_year_id": selected.fiscal_year_id if selected else "", "q": term},
                   urlencode=urlencode)


@router.post("/fiscal-participants/sync")
def synchronize(request: Request, fiscal_year_id: int = Form(...), participant_ids: list[int] = Form(default=[]),
                token: str = Form(...), db: Session = Depends(get_db),
                context: CommunityContext = Depends(_supervisor)):
    validate_csrf(request, token)
    if len(set(participant_ids)) > 100:
        raise HTTPException(422, "Seleccione hasta 100 expedientes por operación.")
    allowed = set(db.scalars(_participant_query(context).with_only_columns(CPParticipant.participant_id)
                            .where(CPParticipant.participant_id.in_(participant_ids))).all())
    if set(participant_ids) != allowed:
        raise HTTPException(403, "Uno o más expedientes no están disponibles en su contexto.")
    try:
        count = sync_participants(db, fiscal_year_id, participant_ids, actor_user_id=context.user.user_id)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect("/community/fiscal-participants", fiscal_year_id,
                         error=str(exc) if isinstance(exc, ValueError) else "No se pudo sincronizar. Recargue e intente nuevamente.")
    return _redirect("/community/fiscal-participants", fiscal_year_id, message=f"Se sincronizaron {count} expedientes.")


@router.get("/participants/{participant_id}/memberships")
def participant_memberships(request: Request, participant_id: int, fiscal_year_id: int | None = None,
                            db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_context)):
    participant = _visible_participant(db, context, participant_id)
    years, selected = _years(db, fiscal_year_id)
    associations = db.execute(select(CPParticipantProgram, CPProgram).join(
        CPProgram, CPProgram.program_id == CPParticipantProgram.program_id).where(
        CPParticipantProgram.participant_id == participant_id,
        CPParticipantProgram.program_id.in_(context.visible_program_ids)).order_by(CPProgram.code)).all()
    rows = []
    for association, program in associations:
        enrollment = db.scalar(select(CPFiscalEnrollment).where(
            CPFiscalEnrollment.participant_id == participant_id,
            CPFiscalEnrollment.program_id == program.program_id,
            CPFiscalEnrollment.fiscal_year_id == selected.fiscal_year_id)) if selected else None
        periods = db.scalars(select(CPEnrollmentPeriod).where(
            CPEnrollmentPeriod.enrollment_id == enrollment.enrollment_id)
            .order_by(CPEnrollmentPeriod.start_date)).all() if enrollment else []
        rows.append({"association": association, "program": program, "enrollment": enrollment,
                     "periods": periods, "is_active": any(period.end_date is None for period in periods)})
    return _render(request, "participant_memberships", context, participant=participant, years=years,
                   selected_year=selected, rows=rows,
                   state=db.get(CPFiscalState, selected.fiscal_year_id) if selected else None,
                   synchronized=bool(selected and db.get(CPFiscalParticipant, (participant_id, selected.fiscal_year_id))))


@router.post("/participants/{participant_id}/memberships")
def change_membership(request: Request, participant_id: int, fiscal_year_id: int = Form(...),
                      program_id: int = Form(...), action: str = Form(...), effective_date: date = Form(...),
                      reason: str = Form(...), observation: str = Form(""), token: str = Form(...),
                      db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    _visible_participant(db, context, participant_id)
    values = dict(participant_id=participant_id, program_id=program_id, fiscal_year_id=fiscal_year_id,
                  actor_user_id=context.user.user_id, reason=reason, observation=observation)
    try:
        if action == "enroll":
            enroll_participant(db, start_date=effective_date, **values)
        elif action == "discharge":
            discharge_participant(db, end_date=effective_date, **values)
        elif action == "reactivate":
            reactivate_participant(db, start_date=effective_date, **values)
        else:
            raise ValueError("Seleccione una acción válida.")
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect(f"/community/participants/{participant_id}/memberships", fiscal_year_id,
                         error=str(exc) if isinstance(exc, ValueError) else "No se pudo guardar. Recargue el historial e intente nuevamente.")
    return _redirect(f"/community/participants/{participant_id}/memberships", fiscal_year_id,
                     message="Se actualizó el programa seleccionado y se conservó el historial.")


@router.post("/fiscal-years/{fiscal_year_id}/status")
def fiscal_status(request: Request, fiscal_year_id: int, action: str = Form(...), token: str = Form(...),
                  db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    try:
        if action not in {"close", "reopen"}:
            raise ValueError("Seleccione cerrar o reabrir.")
        set_fiscal_status(db, fiscal_year_id, closed=action == "close", actor_user_id=context.user.user_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _redirect("/community/fiscal-participants", fiscal_year_id, error=str(exc))
    return _redirect("/community/fiscal-participants", fiscal_year_id,
                     message="Año cerrado y datos congelados." if action == "close" else
                     "Año reabierto. Los datos demográficos siguen congelados y los cierres mensuales se conservan.")


@router.post("/fiscal-years/{fiscal_year_id}/freeze")
def fiscal_freeze(request: Request, fiscal_year_id: int, action: str = Form(...), token: str = Form(...),
                  db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    try:
        if action not in {"freeze", "unfreeze"}:
            raise ValueError("Seleccione congelar o descongelar.")
        set_snapshot_freeze(db, fiscal_year_id, frozen=action == "freeze", actor_user_id=context.user.user_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _redirect("/community/fiscal-participants", fiscal_year_id, error=str(exc))
    return _redirect("/community/fiscal-participants", fiscal_year_id,
                     message="Datos de participantes congelados." if action == "freeze" else "Datos habilitados para sincronización explícita.")


@router.post("/fiscal-years/{fiscal_year_id}/periods")
def fiscal_periods(request: Request, fiscal_year_id: int, locked_through: str = Form(""), token: str = Form(...),
                   db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    try:
        closing_date = date.fromisoformat(locked_through) if locked_through else None
        set_fiscal_lock(db, fiscal_year_id, locked_through=closing_date, actor_user_id=context.user.user_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _redirect("/community/fiscal-participants", fiscal_year_id, error=str(exc))
    return _redirect("/community/fiscal-participants", fiscal_year_id, message="Cierre de períodos actualizado.")
