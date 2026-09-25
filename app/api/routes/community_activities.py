"""Community administration: activities and fiscal-year/program ADM configuration."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.community_access import CommunityContext, csrf_token, require_community_admin, require_programs, validate_csrf
from app.models.community import CPFiscalYear
from app.models.community_activity import CPActivity, CPFiscalActivity, CPADMServiceActivity, CPADMServiceType
from app.models.community_operations import CPActivitySession
from app.services.community_activity import (
    assign_adm_activity, associate_activity, create_activity, create_adm_service_type,
    set_activity_active, unassign_adm_activity, update_adm_service_type,
    GOAL_TYPE_OPTIONS, format_goal, update_activity, update_activity_year, unassociate_activity, delete_activity,
)

router = APIRouter(prefix="/community", tags=["community-configuration"])
templates = Jinja2Templates(directory="app/templates")


def _render(request: Request, name: str, context: CommunityContext, **values):
    return templates.TemplateResponse(request=request, name=f"community/{name}.html", context={
        "request": request, "current_user": context.user, "cp": context,
        "csrf_token": csrf_token(request), "today": date.today(),
        "message": request.query_params.get("msg"), "error": request.query_params.get("error"), **values,
    })


def _redirect(page: str, program_id: int, fiscal_year_id: int, *, message: str | None = None, error: str | None = None):
    query = {"program_id": program_id, "fiscal_year_id": fiscal_year_id}
    query["error" if error else "msg"] = error or message or "Configuración guardada."
    return RedirectResponse(f"/community/{page}?{urlencode(query)}", status_code=303)


def _selection(db: Session, context: CommunityContext, program_id: int | None, fiscal_year_id: int | None):
    years = db.scalars(select(CPFiscalYear).order_by(CPFiscalYear.start_date.desc())).all()
    if program_id is None:
        program_id = context.selected_program_id
    if program_id is not None:
        require_programs(context, [program_id])
    year = next((row for row in years if row.fiscal_year_id == fiscal_year_id), None)
    if fiscal_year_id is not None and year is None:
        raise HTTPException(404, "Año fiscal no encontrado.")
    return years, program_id, year


def _save(db: Session, action, *, page: str, program_id: int, fiscal_year_id: int, message: str):
    try:
        action()
        db.commit()
    except ValueError as exc:
        db.rollback()
        return _redirect(page, program_id, fiscal_year_id, error=str(exc))
    except IntegrityError:
        db.rollback()
        return _redirect(page, program_id, fiscal_year_id,
                         error="La configuración entra en conflicto con un registro existente. Recargue y revise los datos.")
    return _redirect(page, program_id, fiscal_year_id, message=message)


@router.get("/activities")
def activities(request: Request, program_id: int | None = None, fiscal_year_id: int | None = None,
               db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    years, program_id, year = _selection(db, context, program_id, fiscal_year_id or None)
    rows, available = [], []
    if program_id is not None:
        program_activities = db.scalars(select(CPActivity).where(CPActivity.program_id == program_id)
                                        .order_by(CPActivity.code)).all()
        associations = db.scalars(select(CPFiscalActivity).where(CPFiscalActivity.program_id == program_id)).all()
        by_activity = {}
        for association in associations:
            by_activity.setdefault(association.activity_id, {})[association.fiscal_year_id] = association
        used = set()
        for model in (CPActivitySession, CPADMServiceActivity):
            used.update(tuple(row) for row in db.execute(select(model.activity_id, model.fiscal_year_id)
                                                         .where(model.program_id == program_id).distinct()))
        for activity in program_activities:
            linked = by_activity.get(activity.activity_id, {})
            selected = linked.get(year.fiscal_year_id) if year else None
            if year and selected is None:
                if activity.is_active:
                    available.append(activity)
                continue
            links = [{"year": fiscal, "association": linked[fiscal.fiscal_year_id],
                      "editable": fiscal.is_active and fiscal.status == "active",
                      "used": (activity.activity_id, fiscal.fiscal_year_id) in used}
                     for fiscal in years if fiscal.fiscal_year_id in linked]
            shared_editable = all(link["editable"] for link in links)
            rows.append({"activity": activity, "association": selected, "links": links,
                         "shared_editable": shared_editable,
                         "can_delete": shared_editable and not any(link["used"] for link in links),
                         "unassigned_years": [fiscal for fiscal in years if fiscal.fiscal_year_id not in linked
                                              and fiscal.is_active and fiscal.status == "active"]})
    return _render(request, "activities", context, years=years, program_id=program_id, year=year,
                   rows=rows, available=available, goal_options=GOAL_TYPE_OPTIONS, format_goal=format_goal,
                   editable=not year or bool(year.is_active and year.status == "active"),
                   open_years=[fiscal for fiscal in years if fiscal.is_active and fiscal.status == "active"])


@router.post("/activities")
async def add_activity(request: Request, db: Session = Depends(get_db),
                       context: CommunityContext = Depends(require_community_admin)):
    form = await request.form()
    validate_csrf(request, str(form.get("token", "")))
    try:
        program_id = int(str(form.get("program_id", "")))
        year_ids = [int(str(value)) for value in form.getlist("fiscal_year_ids")]
        fiscal_year_id = int(str(form.get("fiscal_year_id", "0")))
    except (TypeError, ValueError):
        raise HTTPException(422, "Seleccione un programa y años fiscales válidos.") from None
    require_programs(context, [program_id])
    if fiscal_year_id and fiscal_year_id not in year_ids:
        return _redirect("activities", program_id, fiscal_year_id, error="Incluya el año fiscal seleccionado entre los años de la actividad.")
    return _save(db, lambda: create_activity(db, program_id=program_id, code=str(form.get("code", "")),
                                             description=str(form.get("description", "")), fiscal_year_ids=year_ids,
                                             goal_type=str(form.get("goal_type", "none")),
                                             goal_value=str(form.get("goal_value", "")),
                                             period_goal_value=str(form.get("period_goal_value", "")),
                                             goal_is_active=form.get("goal_is_active") in ("on", "true", "1")),
                 page="activities", program_id=program_id, fiscal_year_id=fiscal_year_id,
                 message="Actividad creada y asociada a los años fiscales seleccionados.")


@router.post("/activities/associate")
def add_activity_year(request: Request, token: str = Form(...), program_id: int = Form(...),
                      fiscal_year_id: int = Form(...), activity_id: int = Form(...),
                      db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: associate_activity(db, activity_id=activity_id, program_id=program_id, fiscal_year_id=fiscal_year_id),
                 page="activities", program_id=program_id, fiscal_year_id=fiscal_year_id,
                 message="Actividad asociada al año fiscal.")


@router.post("/activities/{activity_id}/state")
def change_activity_state(request: Request, activity_id: int, token: str = Form(...), program_id: int = Form(...),
                          fiscal_year_id: int = Form(...), active: bool = Form(...),
                          db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: set_activity_active(db, activity_id=activity_id, program_id=program_id,
                                                fiscal_year_id=fiscal_year_id, active=active),
                 page="activities", program_id=program_id, fiscal_year_id=fiscal_year_id,
                 message="Disponibilidad de la actividad actualizada para este año fiscal.")


@router.post("/activities/{activity_id}/edit")
def edit_activity(request: Request, activity_id: int, token: str = Form(...), program_id: int = Form(...),
                  fiscal_year_id: int = Form(0), code: str = Form(...), description: str = Form(""),
                  active: bool = Form(False), db: Session = Depends(get_db),
                  context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: update_activity(db, activity_id=activity_id, program_id=program_id,
                                           code=code, description=description, active=active),
                 page="activities", program_id=program_id, fiscal_year_id=fiscal_year_id,
                 message="Datos generales de la actividad actualizados.")


@router.post("/activities/{activity_id}/year")
def edit_activity_year(request: Request, activity_id: int, token: str = Form(...), program_id: int = Form(...),
                       fiscal_year_id: int = Form(...), active: bool = Form(False), goal_type: str = Form("none"),
                       goal_value: str = Form(""), period_goal_value: str = Form(""), goal_is_active: bool = Form(False),
                       db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: update_activity_year(db, activity_id=activity_id, program_id=program_id,
                                                fiscal_year_id=fiscal_year_id, active=active, goal_type=goal_type,
                                                goal_value=goal_value, period_goal_value=period_goal_value,
                                                goal_is_active=goal_is_active),
                 page="activities", program_id=program_id, fiscal_year_id=fiscal_year_id,
                 message="Estado y meta productiva actualizados para este año fiscal.")


@router.post("/activities/{activity_id}/unassociate")
def remove_activity_year(request: Request, activity_id: int, token: str = Form(...), program_id: int = Form(...),
                         fiscal_year_id: int = Form(...), db: Session = Depends(get_db),
                         context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: unassociate_activity(db, activity_id=activity_id, program_id=program_id,
                                                 fiscal_year_id=fiscal_year_id),
                 page="activities", program_id=program_id, fiscal_year_id=fiscal_year_id,
                 message="Actividad retirada del año fiscal. Se conservan las demás asociaciones.")


@router.post("/activities/{activity_id}/delete")
def remove_activity(request: Request, activity_id: int, token: str = Form(...), program_id: int = Form(...),
                    fiscal_year_id: int = Form(0), db: Session = Depends(get_db),
                    context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: delete_activity(db, activity_id=activity_id, program_id=program_id),
                 page="activities", program_id=program_id, fiscal_year_id=fiscal_year_id,
                 message="Actividad sin historial eliminada.")


@router.get("/adm")
def adm(request: Request, program_id: int | None = None, fiscal_year_id: int | None = None,
        db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    years, program_id, year = _selection(db, context, program_id, fiscal_year_id)
    services, activities, mappings = [], [], {}
    assigned_ids = set()
    if program_id is not None and year is not None:
        services = db.scalars(select(CPADMServiceType).where(
            CPADMServiceType.program_id == program_id, CPADMServiceType.fiscal_year_id == year.fiscal_year_id,
        ).order_by(CPADMServiceType.sort_order, CPADMServiceType.name)).all()
        rows = db.execute(select(CPADMServiceActivity, CPActivity).join(
            CPActivity, CPActivity.activity_id == CPADMServiceActivity.activity_id,
        ).where(CPADMServiceActivity.program_id == program_id, CPADMServiceActivity.fiscal_year_id == year.fiscal_year_id,
                CPADMServiceActivity.is_active == True).order_by(CPActivity.code)).all()  # noqa: E712
        for mapping, activity in rows:
            mappings.setdefault(mapping.adm_service_type_id, []).append(activity)
            assigned_ids.add(activity.activity_id)
        activities = db.scalars(select(CPActivity).join(
            CPFiscalActivity, CPFiscalActivity.activity_id == CPActivity.activity_id,
        ).where(CPActivity.program_id == program_id, CPFiscalActivity.fiscal_year_id == year.fiscal_year_id,
                CPActivity.is_active == True, CPFiscalActivity.is_active == True,  # noqa: E712
                CPActivity.activity_id.not_in(assigned_ids)).order_by(CPActivity.code)).all()
    return _render(request, "adm", context, years=years, program_id=program_id, year=year,
                   services=services, activities=activities, mappings=mappings,
                   editable=bool(year and year.is_active and year.status == "active"))


@router.post("/adm/service-types")
def add_adm_type(request: Request, token: str = Form(...), program_id: int = Form(...), fiscal_year_id: int = Form(...),
                 name: str = Form(...), sort_order: int = Form(0), db: Session = Depends(get_db),
                 context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: create_adm_service_type(db, program_id=program_id, fiscal_year_id=fiscal_year_id,
                                                   name=name, sort_order=sort_order),
                 page="adm", program_id=program_id, fiscal_year_id=fiscal_year_id, message="Tipo de servicio ADM creado.")


@router.post("/adm/service-types/{service_type_id}/edit")
def edit_adm_type(request: Request, service_type_id: int, token: str = Form(...), program_id: int = Form(...),
                  fiscal_year_id: int = Form(...), name: str = Form(...), sort_order: int = Form(0), active: bool = Form(False),
                  db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: update_adm_service_type(db, service_type_id=service_type_id, program_id=program_id,
                                                   fiscal_year_id=fiscal_year_id, name=name, sort_order=sort_order, active=active),
                 page="adm", program_id=program_id, fiscal_year_id=fiscal_year_id, message="Tipo de servicio ADM actualizado.")


@router.post("/adm/service-types/{service_type_id}/activities")
def add_adm_activity(request: Request, service_type_id: int, token: str = Form(...), program_id: int = Form(...),
                     fiscal_year_id: int = Form(...), activity_id: int = Form(...), db: Session = Depends(get_db),
                     context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: assign_adm_activity(db, service_type_id=service_type_id, program_id=program_id,
                                               fiscal_year_id=fiscal_year_id, activity_id=activity_id),
                 page="adm", program_id=program_id, fiscal_year_id=fiscal_year_id, message="Actividad asociada al tipo de servicio.")


@router.post("/adm/service-types/{service_type_id}/activities/{activity_id}/remove")
def remove_adm_activity(request: Request, service_type_id: int, activity_id: int, token: str = Form(...),
                        program_id: int = Form(...), fiscal_year_id: int = Form(...), db: Session = Depends(get_db),
                        context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    require_programs(context, [program_id])
    return _save(db, lambda: unassign_adm_activity(db, service_type_id=service_type_id, program_id=program_id,
                                                 fiscal_year_id=fiscal_year_id, activity_id=activity_id),
                 page="adm", program_id=program_id, fiscal_year_id=fiscal_year_id, message="Asociación ADM desactivada.")
