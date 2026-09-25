from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.community_access import (
    CONTEXT_KEY, CommunityContext, csrf_token, require_community_access,
    require_community_admin, require_community_context, require_community_writer, require_community_supervisor,
    require_programs, validate_csrf,
)
from app.models.community import CPFiscalYear, CPParticipant, CPParticipantProgram, CPProgram
from app.models.community_catalog import CPProfileField, CPProfileValue
from app.services.community import associate_participant_programs, create_fiscal_year, create_participant, create_program, update_participant
from app.services.community_catalog import form_catalogs, save_profile_values, validate_categories
from app.services.community_activity import copy_fiscal_configuration
from app.services.community_identity import has_identity_link, identity_review_url, pending_identity_review

router = APIRouter(prefix="/community", tags=["community"])
templates = Jinja2Templates(directory="app/templates")
PERSONAL_FIELDS = (
    "nombre", "inicial", "apellido_paterno", "apellido_materno", "genero",
    "fecha_nacimiento", "primera_vez", "vca", "escolaridad_participante",
    "composicion_familiar", "grupo_familiar", "fuente_ingreso_principal",
    "rango_ingreso", "relacion_familiar", "estatus", "direccion_fisica",
    "pueblo", "telefono", "email",
)


def _render(request: Request, name: str, context: CommunityContext, **values):
    return templates.TemplateResponse(request=request, name=f"community/{name}.html", context={
        "request": request, "current_user": context.user, "cp": context,
        "csrf_token": csrf_token(request), "message": request.query_params.get("msg"),
        "error": request.query_params.get("error"), "today": date.today(), **values,
    })


def _redirect(path: str, *, message: str | None = None, error: str | None = None):
    query = urlencode({"error": error} if error else {"msg": message})
    return RedirectResponse(f"{path}?{query}", status_code=303)


def _participant_form_response(request, context, db, **values):
    participant = values.get("participant")
    catalogs = form_catalogs(db, participant.participant_id if participant else None)
    for field in catalogs["profile_fields"]:
        key = f"profile_{field.field_id}"
        if key in values.get("values", {}):
            catalogs["profile_values"][field.field_id] = values["values"][key]
    return _render(request, "participant_form", context, **catalogs, **values)


def _participant_query(context: CommunityContext):
    return select(CPParticipant).where(
        select(CPParticipantProgram.participant_id).where(
            CPParticipantProgram.participant_id == CPParticipant.participant_id,
            CPParticipantProgram.program_id.in_(context.visible_program_ids),
        ).exists()
    )


@router.get("/login")
def entry(request: Request, access: CommunityContext = Depends(require_community_access)):
    return _render(request, "entry", access)


@router.post("/context")
def choose_context(request: Request, program: str = Form(...), token: str = Form(...),
                   access: CommunityContext = Depends(require_community_access)):
    validate_csrf(request, token)
    if program == "all":
        request.session[CONTEXT_KEY] = "all"
    else:
        try:
            program_id = int(program)
        except ValueError:
            raise HTTPException(403, "Programa no autorizado.")
        if program_id not in access.program_ids:
            raise HTTPException(403, "Programa no autorizado.")
        request.session[CONTEXT_KEY] = program_id
    return RedirectResponse("/community", status_code=303)


@router.get("")
def home(request: Request, db: Session = Depends(get_db),
         context: CommunityContext = Depends(require_community_context)):
    count = db.scalar(select(func.count()).select_from(_participant_query(context).subquery())) or 0
    return _render(request, "home", context, participant_count=count)


@router.get("/programs")
def programs(request: Request, context: CommunityContext = Depends(require_community_admin)):
    return _render(request, "programs", context)


@router.post("/programs")
def add_program(request: Request, code: str = Form(...), name: str = Form(...),
                token: str = Form(...), db: Session = Depends(get_db),
                context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    try:
        create_program(db, code, name)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _redirect("/community/programs", error=str(exc))
    except IntegrityError:
        db.rollback()
        return _redirect("/community/programs", error="Ya existe un programa con ese código.")
    return _redirect("/community/programs", message="Programa creado correctamente.")


@router.get("/fiscal-years")
def fiscal_years(request: Request, db: Session = Depends(get_db),
                 context: CommunityContext = Depends(require_community_admin)):
    years = db.scalars(select(CPFiscalYear).order_by(CPFiscalYear.start_date.desc())).all()
    return _render(request, "fiscal_years", context, years=years)


@router.post("/fiscal-years")
def add_fiscal_year(request: Request, code: str = Form(...), name: str = Form(...),
                    start_date: date = Form(...), end_date: date = Form(...),
                    copy_from: str = Form(""),
                    token: str = Form(...), db: Session = Depends(get_db),
                    context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    try:
        fiscal = create_fiscal_year(db, code, name, start_date, end_date)
        if copy_from:
            copy_fiscal_configuration(db, int(copy_from), fiscal.fiscal_year_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _redirect("/community/fiscal-years", error=str(exc))
    except IntegrityError:
        db.rollback()
        return _redirect("/community/fiscal-years", error="Ya existe un año fiscal con ese código.")
    return _redirect("/community/fiscal-years", message="Año fiscal creado para todos los programas de Comunidad.")


@router.get("/participants")
def participants(request: Request, q: str = "", page: int = 1, db: Session = Depends(get_db),
                 context: CommunityContext = Depends(require_community_context)):
    page = max(1, page)
    query = _participant_query(context)
    if q.strip():
        term = q.strip()[:150]
        query = query.where(or_(*[
            field.contains(term, autoescape=True) for field in (
                CPParticipant.expediente_num, CPParticipant.nombre,
                CPParticipant.apellido_paterno, CPParticipant.apellido_materno,
            )
        ]))
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(CPParticipant.participant_id.desc()).offset((page - 1) * 50).limit(50)).all()
    return _render(request, "participants", context, participants=rows, q=q, page=page,
                   total=total, next_query=urlencode({"q": q, "page": page + 1}))


@router.get("/participants/new")
def participant_form(request: Request, db: Session = Depends(get_db),
                     context: CommunityContext = Depends(require_community_writer)):
    return _participant_form_response(request, context, db, values={}, form_error=None)


@router.post("/participants")
async def add_participant(request: Request, db: Session = Depends(get_db),
                          context: CommunityContext = Depends(require_community_writer)):
    form = await request.form()
    validate_csrf(request, str(form.get("token", "")))
    values = dict(form)
    try:
        program_ids = [int(value) for value in form.getlist("program_ids")]
        require_programs(context, program_ids)
        exp_year = int(form.get("exp_year", ""))
    except (TypeError, ValueError):
        return _participant_form_response(request, context, db, values=values,
                       form_error="Revise el año de expediente y los programas seleccionados.")
    values["program_ids"] = program_ids
    fields = {key: form.get(key) for key in PERSONAL_FIELDS}
    fields["is_head_of_household"] = form.get("is_head_of_household") == "on"
    try:
        validate_categories(db, fields)
        participant = create_participant(db, actor_user_id=context.user.user_id,
                                         exp_year=exp_year, program_ids=program_ids, fields=fields)
        save_profile_values(db, participant.participant_id, form)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _participant_form_response(request, context, db, values=values, form_error=str(exc))
    except IntegrityError:
        db.rollback()
        return _participant_form_response(request, context, db, values=values,
                       form_error="No se pudo guardar el expediente. Revise los datos e intente nuevamente.")
    if pending_identity_review(db, "community", participant.participant_id):
        return RedirectResponse(identity_review_url("community", participant.participant_id), status_code=303)
    return _redirect(f"/community/participants/{participant.participant_id}", message="Expediente creado correctamente.")


@router.get("/participants/lookup")
def participant_lookup(request: Request, q: str = "", db: Session = Depends(get_db),
                       context: CommunityContext = Depends(require_community_writer)):
    rows = []
    term = q.strip()[:150]
    if len(term) >= 3:
        # Explicitly return only identity fields, never contact data or other programs.
        rows = db.execute(select(CPParticipant.participant_id, CPParticipant.expediente_num,
                                 CPParticipant.nombre, CPParticipant.inicial, CPParticipant.apellido_paterno,
                                 CPParticipant.apellido_materno, CPParticipant.fecha_nacimiento).where(or_(*[
            field.contains(term, autoescape=True) for field in (
                CPParticipant.expediente_num, CPParticipant.nombre,
                CPParticipant.apellido_paterno, CPParticipant.apellido_materno,
            )
        ])).order_by(CPParticipant.apellido_paterno, CPParticipant.nombre).limit(50)).all()
    return _render(request, "participant_lookup", context, matches=rows, q=term)


@router.get("/participants/{participant_id}/edit")
def edit_participant_form(request: Request, participant_id: int, db: Session = Depends(get_db),
                          context: CommunityContext = Depends(require_community_supervisor)):
    participant = db.scalar(_participant_query(context).where(CPParticipant.participant_id == participant_id))
    if participant is None:
        raise HTTPException(404, "Expediente no disponible.")
    values = {key: getattr(participant, key) for key in PERSONAL_FIELDS}
    values.update(exp_year=participant.exp_year, is_head_of_household="on" if participant.is_head_of_household else "")
    return _participant_form_response(request, context, db, participant=participant, values=values, form_error=None)


@router.post("/participants/{participant_id}/edit")
async def edit_participant(request: Request, participant_id: int, db: Session = Depends(get_db),
                           context: CommunityContext = Depends(require_community_supervisor)):
    form = await request.form()
    validate_csrf(request, str(form.get("token", "")))
    participant = db.scalar(_participant_query(context).where(CPParticipant.participant_id == participant_id))
    if participant is None:
        raise HTTPException(404, "Expediente no disponible.")
    fields = {key: form.get(key) for key in PERSONAL_FIELDS}
    fields["is_head_of_household"] = form.get("is_head_of_household") == "on"
    try:
        validate_categories(db, fields, participant)
        update_participant(db, participant_id=participant_id, fields=fields)
        save_profile_values(db, participant_id, form)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _participant_form_response(request, context, db, participant=participant,
                       values={**dict(form), "exp_year": participant.exp_year}, form_error=str(exc))
    return _redirect(f"/community/participants/{participant_id}", message="Datos personales actualizados.")


@router.post("/participants/{participant_id}/programs")
def associate_programs(request: Request, participant_id: int, token: str = Form(...),
                       program_ids: list[int] = Form(default=[]), db: Session = Depends(get_db),
                       context: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    require_programs(context, program_ids)
    try:
        associate_participant_programs(db, participant_id=participant_id,
                                      actor_user_id=context.user.user_id, program_ids=program_ids)
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _redirect("/community/participants/lookup", error=str(exc))
    except IntegrityError:
        db.rollback()
        return _redirect("/community/participants/lookup", error="No se pudo guardar la asociación. Vuelva a consultar el expediente.")
    return _redirect(f"/community/participants/{participant_id}", message="Programas asociados al expediente existente.")


@router.get("/participants/{participant_id}")
def participant_detail(request: Request, participant_id: int, db: Session = Depends(get_db),
                       context: CommunityContext = Depends(require_community_context)):
    participant = db.scalar(_participant_query(context).where(CPParticipant.participant_id == participant_id))
    if participant is None:
        raise HTTPException(404, "Expediente no disponible.")
    associations = db.execute(select(CPParticipantProgram, CPProgram).join(
        CPProgram, CPProgram.program_id == CPParticipantProgram.program_id
    ).where(CPParticipantProgram.participant_id == participant_id,
            CPParticipantProgram.program_id.in_(context.visible_program_ids)).order_by(CPProgram.code)).all()
    profile = db.execute(select(CPProfileField.label, CPProfileValue.value).join(
        CPProfileValue, CPProfileValue.field_id == CPProfileField.field_id
    ).where(CPProfileValue.participant_id == participant_id).order_by(CPProfileField.sort_order)).all()
    return _render(request, "participant_detail", context, participant=participant,
                   associations=associations, profile=profile,
                   identity_linked=has_identity_link(db, "community", participant_id),
                   identity_pending=context.role != "viewer" and pending_identity_review(db, "community", participant_id))
