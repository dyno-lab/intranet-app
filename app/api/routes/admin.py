from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form, File, UploadFile
from datetime import date
import json
import re
import zipfile
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from urllib.parse import quote_plus
from fastapi.responses import HTMLResponse, RedirectResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, delete
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import require_admin, require_admin_or_supervisor, is_admin_or_supervisor
from app.core.proposal_guard import is_proposal_finalized
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.models.activity_code import ActivityCode
from app.models.activity_productivity_goal import ActivityProductivityGoal
from app.models.adm_service_type import ADMServiceType
from app.models.adm_service_type_activity_code import ADMServiceTypeActivityCode
from app.models.activity_session import ActivitySession
from app.models.employee import Employee
from app.models.proposal import Proposal
from app.models.participant import Participant
from app.models.person import Person
from app.models.proposal_participant import ProposalParticipant
from app.models.proposal_population_group import ProposalPopulationGroup
from app.models.proposal_report_program import ProposalReportProgram
from app.models.residential import Residential
from app.models.vca_column import VCAColumn
from app.models.visit_activity_mapping import VisitActivityMapping
from app.models.visit_report import VisitReport
from app.models.visit_report_referral import VisitReportReferral
from app.services.visits import delete_visit_reports_and_referrals
from app.models.pregnancy_report import PregnancyReport
from app.models.school_grade_report import SchoolGradeReport
from app.models.school_dropout_report import SchoolDropoutReport
from app.models.vca_column import VCAColumn
from app.models.vca_column_activity_code import VCAColumnActivityCode
from app.models.visit_activity_mapping import VisitActivityMapping
from app.models.proposal_report_program import ProposalReportProgram
from app.models.proposal_population_group import ProposalPopulationGroup
from app.models.proposal_report_program_activity import ProposalReportProgramActivity
from app.models.proposal_report_program_activity_code import ProposalReportProgramActivityCode
from app.models.proposal_report_program_population import ProposalReportProgramPopulation
from app.models.proposal_report_program_population_activity_code import ProposalReportProgramPopulationActivityCode
from app.models.report_template import ProposalReportTemplate, ReportTemplate, ReportTemplateVersion
from app.services.report_programs import (
    activity_code_is_assigned_anywhere_in_proposal as _activity_code_is_assigned_anywhere_in_proposal,
)
from app.services.hoja_cotejo_admin_service import build_hoja_cotejo_admin_context

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_USER_ROLES = {"admin", "supervisor", "user"}
DEFAULT_POPULATION_GROUP_OPTIONS = [
    ("ninos", "NiÃ±os", 0, 12, 1),
    ("jovenes", "JÃ³venes", 13, 17, 2),
    ("adultos", "Adultos", 18, 59, 3),
    ("adulto_mayor", "Adulto Mayor", 60, None, 4),
]

PRODUCTIVITY_GOAL_TYPE_OPTIONS = [
    ("none", "Sin meta productiva"),
    ("per_residential_min_1", "SegÃºn Necesidad"),
    ("per_residential_fixed", "Cantidad fija por residencial por mes"),
    ("per_residential_period_fixed", "Acumulada por perÃ­odo"),
]

VALID_PRODUCTIVITY_GOAL_TYPES = {value for value, _ in PRODUCTIVITY_GOAL_TYPE_OPTIONS}


def _redirect_with_msg(url: str, msg: str):
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}msg={quote_plus(msg)}", status_code=303)


def _redirect_if_proposal_finalized(proposal: Proposal | None, redirect_url: str, message: str):
    if is_proposal_finalized(proposal):
        return _redirect_with_msg(redirect_url, message)
    return None


def _calc_age(dob: date | None):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - (((today.month, today.day) < (dob.month, dob.day)))


def _normalized_sync_value(value):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _values_differ_for_sync(current_value, source_value) -> bool:
    return _normalized_sync_value(current_value) != _normalized_sync_value(source_value)


def _sync_proposal_participant_from_source(
    proposal_participant: ProposalParticipant,
    person: Person,
    participant: Participant,
) -> None:
    person.nombre = participant.nombre
    person.inicial = participant.inicial
    person.apellido_paterno = participant.apellido_paterno
    person.apellido_materno = participant.apellido_materno
    person.genero = participant.genero
    person.fecha_nacimiento = participant.fecha_nacimiento

    proposal_participant.created_by_user_id = participant.created_by_user_id
    proposal_participant.exp_year = participant.exp_year
    proposal_participant.exp_employee_initials = participant.exp_employee_initials
    proposal_participant.exp_seq4 = participant.exp_seq4
    proposal_participant.expediente_num = participant.expediente_num
    proposal_participant.edificio = participant.edificio
    proposal_participant.apart = participant.apart
    proposal_participant.vca = participant.vca
    proposal_participant.primera_vez = participant.primera_vez
    proposal_participant.composicion_familiar = participant.composicion_familiar
    proposal_participant.estatus = participant.estatus
    proposal_participant.grupo_familiar = participant.grupo_familiar
    proposal_participant.fuente_ingreso_principal = participant.fuente_ingreso_principal
    proposal_participant.rango_ingreso = participant.rango_ingreso
    proposal_participant.is_active = bool(getattr(participant, "is_active", False))


def _normalize_activity_productivity_goal(
    goal_type: str | None,
    goal_value_raw: str | None,
    period_goal_value_raw: str | None,
    proposal_id: int | None,
) -> tuple[str, int | None, int | None]:
    normalized_goal_type = (goal_type or "none").strip()
    if normalized_goal_type not in VALID_PRODUCTIVITY_GOAL_TYPES:
        raise ValueError("Error: Tipo de meta productiva invÃ¡lido.")

    if proposal_id is None:
        return "none", None, None

    if normalized_goal_type == "none":
        return "none", None, None

    normalized_period_goal_value = None
    raw_period_value = (period_goal_value_raw or "").strip()
    if raw_period_value:
        try:
            normalized_period_goal_value = int(raw_period_value)
        except ValueError as exc:
            raise ValueError("Error: La meta global del perÃ­odo debe ser un nÃºmero entero.") from exc

        if normalized_period_goal_value < 1:
            raise ValueError("Error: La meta global del perÃ­odo debe ser mayor o igual a 1.")

    if normalized_goal_type == "per_residential_min_1":
        return "per_residential_min_1", 1, normalized_period_goal_value

    if normalized_goal_type == "per_residential_period_fixed" and normalized_period_goal_value is None:
        raise ValueError("Error: La meta global del perÃ­odo es requerida para actividades acumuladas por perÃ­odo.")

    raw_value = (goal_value_raw or "").strip()
    if not raw_value:
        raise ValueError("Error: Debe indicar un valor para la meta productiva seleccionada.")

    try:
        goal_value = int(raw_value)
    except ValueError as exc:
        raise ValueError("Error: El valor de la meta productiva debe ser un nÃºmero entero.") from exc

    if goal_value < 1:
        raise ValueError("Error: El valor de la meta productiva debe ser mayor o igual a 1.")

    return normalized_goal_type, goal_value, normalized_period_goal_value


def _format_activity_productivity_goal_summary(goal: ActivityProductivityGoal | None) -> str:
    if not goal or not goal.is_active:
        return "Sin meta productiva"

    parts: list[str] = []

    if goal.goal_type == "per_residential_min_1":
        parts.append("SegÃºn Necesidad")
    elif goal.goal_type == "per_residential_fixed":
        parts.append(f"{goal.goal_value} / residencial / mes")
    elif goal.goal_type == "global_fixed":
        parts.append(f"{goal.goal_value} global / mes")
    elif goal.goal_type == "per_residential_period_fixed":
        parts.append(f"{goal.goal_value} / residencial / perÃ­odo")

    if goal.period_goal_value:
        parts.append(f"{goal.period_goal_value} global / perÃ­odo")

    return " + ".join(parts) if parts else "Sin meta productiva"


def _upsert_activity_productivity_goal(
    db: Session,
    activity_code: ActivityCode,
    goal_type: str,
    goal_value: int | None,
    period_goal_value: int | None,
    is_active: bool,
):
    existing_goal = db.execute(
        select(ActivityProductivityGoal).where(
            ActivityProductivityGoal.activity_code_id == activity_code.activity_code_id,
            ActivityProductivityGoal.proposal_id == activity_code.proposal_id,
        )
    ).scalar_one_or_none()

    if activity_code.proposal_id is None:
        if existing_goal:
            db.delete(existing_goal)
        return

    if not existing_goal:
        existing_goal = ActivityProductivityGoal(
            proposal_id=activity_code.proposal_id,
            activity_code_id=activity_code.activity_code_id,
        )

    existing_goal.proposal_id = activity_code.proposal_id
    existing_goal.activity_code_id = activity_code.activity_code_id
    existing_goal.goal_type = goal_type
    existing_goal.goal_value = goal_value
    existing_goal.period_goal_value = period_goal_value
    existing_goal.is_active = is_active
    db.add(existing_goal)


def _program_uses_population_structure(db: Session, program_id: int) -> bool:
    count = db.execute(
        select(func.count()).select_from(ProposalReportProgramPopulation).where(
            ProposalReportProgramPopulation.program_id == program_id,
            ProposalReportProgramPopulation.is_active == True,  # noqa: E712
        )
    ).scalar()
    return bool(count and count > 0)


def _resolve_effective_activity_code_ids_for_program(db: Session, program_id: int) -> set[int]:
    if _program_uses_population_structure(db, program_id):
        rows = db.execute(
            select(ProposalReportProgramPopulationActivityCode.activity_code_id)
            .join(
                ProposalReportProgramPopulation,
                ProposalReportProgramPopulation.program_population_id
                == ProposalReportProgramPopulationActivityCode.program_population_id,
            )
            .where(
                ProposalReportProgramPopulation.program_id == program_id,
                ProposalReportProgramPopulation.is_active == True,  # noqa: E712
            )
        ).all()
        return {activity_code_id for (activity_code_id,) in rows}

    rows = db.execute(
        select(ProposalReportProgramActivityCode.activity_code_id)
        .join(
            ProposalReportProgramActivity,
            ProposalReportProgramActivity.program_activity_id
            == ProposalReportProgramActivityCode.program_activity_id,
        )
        .where(ProposalReportProgramActivity.program_id == program_id)
    ).all()
    return {activity_code_id for (activity_code_id,) in rows}


# ============================================================
# USER MANAGEMENT
# ============================================================

@router.get("/users", response_class=HTMLResponse)
def admin_users(
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    users = db.execute(
        select(User).order_by(User.created_at.desc())
    ).scalars().all()
    residentials = db.execute(
        select(Residential).where(Residential.is_active == True).order_by(Residential.code)  # noqa: E712
    ).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "residentials": residentials,
            "msg": msg,
        },
    )


@router.post("/users/create")
def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    residential_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg("/ui/admin/users", "Error: El usuario ya existe.")

    normalized_role = role if role in VALID_USER_ROLES else "user"
    if normalized_role == "user" and not residential_id:
        return _redirect_with_msg("/ui/admin/users", "Error: Debe seleccionar un residencial para usuarios con rol user.")

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=normalized_role,
        residential_id=residential_id or None,
    )
    db.add(user)
    db.commit()

    return _redirect_with_msg("/ui/admin/users", "Usuario creado exitosamente.")


@router.post("/users/{user_id}/edit")
def admin_edit_user(
    user_id: int,
    request: Request,
    username: str = Form(...),
    role: str = Form("user"),
    residential_id: int | None = Form(default=None),
    is_active: str | None = Form(default=None),
    new_password: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        return _redirect_with_msg("/ui/admin/users", "Error: Usuario no encontrado.")

    existing = db.execute(
        select(User).where(User.username == username, User.user_id != user_id)
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg("/ui/admin/users", "Error: El nombre de usuario ya estÃ¡ en uso.")

    normalized_role = role if role in VALID_USER_ROLES else "user"
    if normalized_role == "user" and not residential_id:
        return _redirect_with_msg("/ui/admin/users", "Error: Debe seleccionar un residencial para usuarios con rol user.")

    user.username = username
    user.role = normalized_role
    user.residential_id = residential_id or None
    user.is_active = is_active == "on"

    if new_password and new_password.strip() and len(new_password.strip()) > 0:
        user.password_hash = hash_password(new_password.strip())

    db.add(user)
    db.commit()

    return _redirect_with_msg("/ui/admin/users", "Usuario actualizado exitosamente.")


@router.post("/users/{user_id}/delete")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.user_id:
        return _redirect_with_msg("/ui/admin/users", "Error: No puedes eliminar tu propio usuario.")

    user = db.get(User, user_id)
    if not user:
        return _redirect_with_msg("/ui/admin/users", "Error: Usuario no encontrado.")

    db.delete(user)
    db.commit()

    return _redirect_with_msg("/ui/admin/users", "Usuario eliminado exitosamente.")


# ============================================================
# RESIDENTIAL MANAGEMENT
# ============================================================

@router.get("/residentials", response_class=HTMLResponse)
def admin_residentials(
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    residentials = db.execute(
        select(Residential).order_by(Residential.code)
    ).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/residentials.html",
        {
            "request": request,
            "current_user": current_user,
            "residentials": residentials,
            "msg": msg,
        },
    )


@router.post("/residentials/create")
def admin_create_residential(
    code: str = Form(...),
    name: str = Form(...),
    municipality: str = Form(...),
    rq_code: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    code = code.strip().upper()
    existing = db.execute(select(Residential).where(Residential.code == code)).scalar_one_or_none()
    if existing:
        return _redirect_with_msg("/ui/admin/residentials", "Error: El cÃ³digo ya existe.")

    residential = Residential(
        code=code,
        name=name.strip(),
        municipality=municipality.strip(),
        rq_code=rq_code.strip().upper(),
    )
    db.add(residential)
    db.commit()

    return _redirect_with_msg("/ui/admin/residentials", "Residencial creado exitosamente.")


@router.post("/residentials/{residential_id}/edit")
def admin_edit_residential(
    residential_id: int,
    code: str = Form(...),
    name: str = Form(...),
    municipality: str = Form(...),
    rq_code: str = Form(...),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    residential = db.get(Residential, residential_id)
    if not residential:
        return _redirect_with_msg("/ui/admin/residentials", "Error: Residencial no encontrado.")

    code = code.strip().upper()
    existing = db.execute(
        select(Residential).where(Residential.code == code, Residential.residential_id != residential_id)
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg("/ui/admin/residentials", "Error: El cÃ³digo ya estÃ¡ en uso.")

    residential.code = code
    residential.name = name.strip()
    residential.municipality = municipality.strip()
    residential.rq_code = rq_code.strip().upper()
    residential.is_active = is_active == "on"
    db.add(residential)
    db.commit()

    return _redirect_with_msg("/ui/admin/residentials", "Residencial actualizado exitosamente.")


# ============================================================
# VISITS MANAGEMENT
# Configura quÃ© actividades por propuesta cuentan como visitas.
# Esta pantalla alimenta el futuro reporte de visitas en ui/reports.
# ============================================================

@router.get("/visits", response_class=HTMLResponse)
def admin_visits(
    request: Request,
    proposal_id: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()
    selected_proposal = db.get(Proposal, proposal_id) if proposal_id else None
    activities = []
    mappings = []
    assigned_activity_ids: set[int] = set()

    if selected_proposal:
        activities = db.execute(
            select(ActivityCode)
            .where(ActivityCode.proposal_id == selected_proposal.proposal_id)
            .order_by(ActivityCode.code)
        ).scalars().all()

        mappings = db.execute(
            select(VisitActivityMapping, ActivityCode)
            .join(ActivityCode, ActivityCode.activity_code_id == VisitActivityMapping.activity_code_id)
            .where(VisitActivityMapping.proposal_id == selected_proposal.proposal_id)
            .order_by(ActivityCode.code)
        ).all()
        assigned_activity_ids = {activity.activity_code_id for _, activity in mappings}

    return templates.TemplateResponse(
        "ui/admin/visits.html",
        {
            "request": request,
            "current_user": current_user,
            "msg": msg,
            "proposals": proposals,
            "selected_proposal_id": proposal_id,
            "selected_proposal": selected_proposal,
            "activities": activities,
            "mappings": mappings,
            "assigned_activity_ids": assigned_activity_ids,
        },
    )


@router.post("/visits/mappings/create")
def admin_create_visit_mapping(
    proposal_id: int = Form(...),
    activity_code_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    activity = db.get(ActivityCode, activity_code_id)

    if not proposal or not activity:
        return _redirect_with_msg(f"/ui/admin/visits?proposal_id={proposal_id}", "Error: Propuesta o actividad no encontrada.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/visits?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    if activity.proposal_id != proposal_id:
        return _redirect_with_msg(f"/ui/admin/visits?proposal_id={proposal_id}", "Error: La actividad no pertenece a la propuesta seleccionada.")

    existing = db.execute(
        select(VisitActivityMapping).where(
            VisitActivityMapping.proposal_id == proposal_id,
            VisitActivityMapping.activity_code_id == activity_code_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            f"/ui/admin/visits?proposal_id={proposal_id}&msg=Error: Esa actividad ya estÃ¡ marcada como visita.",
            status_code=303,
        )

    mapping = VisitActivityMapping(
        proposal_id=proposal_id,
        activity_code_id=activity_code_id,
        is_active=True,
    )
    db.add(mapping)
    db.commit()

    return RedirectResponse(
        f"/ui/admin/visits?proposal_id={proposal_id}&msg=Actividad de visita agregada exitosamente.",
        status_code=303,
    )


@router.post("/visits/mappings/{mapping_id}/delete")
def admin_delete_visit_mapping(
    mapping_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    mapping = db.get(VisitActivityMapping, mapping_id)
    if not mapping:
        return _redirect_with_msg(f"/ui/admin/visits?proposal_id={proposal_id}", "Error: ConfiguraciÃ³n no encontrada.")

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/visits?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    db.delete(mapping)
    db.commit()

    return _redirect_with_msg(f"/ui/admin/visits?proposal_id={proposal_id}", "Actividad de visita eliminada exitosamente.")


# ============================================================
# ADM MANAGEMENT
# ============================================================

@router.get("/adm", response_class=HTMLResponse)
def admin_adm(
    request: Request,
    proposal_id: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()
    selected_proposal = db.get(Proposal, proposal_id) if proposal_id else None
    service_types = []
    assigned_activity_ids: set[int] = set()
    activities = []

    if selected_proposal:
        service_types = db.execute(
            select(ADMServiceType)
            .where(ADMServiceType.proposal_id == selected_proposal.proposal_id)
            .order_by(ADMServiceType.sort_order, ADMServiceType.name)
        ).scalars().all()
        mappings = db.execute(
            select(ADMServiceTypeActivityCode, ActivityCode, ADMServiceType)
            .join(ActivityCode, ActivityCode.activity_code_id == ADMServiceTypeActivityCode.activity_code_id)
            .join(ADMServiceType, ADMServiceType.adm_service_type_id == ADMServiceTypeActivityCode.adm_service_type_id)
            .where(ADMServiceType.proposal_id == selected_proposal.proposal_id)
            .order_by(ADMServiceType.adm_service_type_id, ActivityCode.code)
        ).all()
        activity_map: dict[int, list[dict]] = {}
        for mapping, activity, service_type in mappings:
            activity_map.setdefault(service_type.adm_service_type_id, []).append({"mapping_id": mapping.id, "activity": activity})
            assigned_activity_ids.add(activity.activity_code_id)
        for service_type in service_types:
            setattr(service_type, "assigned_activities", activity_map.get(service_type.adm_service_type_id, []))

        activities = db.execute(
            select(ActivityCode)
            .where(ActivityCode.proposal_id == selected_proposal.proposal_id)
            .order_by(ActivityCode.code)
        ).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/adm.html",
        {
            "request": request,
            "current_user": current_user,
            "msg": msg,
            "proposals": proposals,
            "selected_proposal_id": proposal_id,
            "selected_proposal": selected_proposal,
            "service_types": service_types,
            "activities": activities,
            "assigned_activity_ids": assigned_activity_ids,
        },
    )


@router.post("/adm/service-types/create")
def admin_create_adm_service_type(
    proposal_id: int = Form(...),
    name: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/adm", "Error: Propuesta no encontrada.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/adm?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    db.add(ADMServiceType(proposal_id=proposal_id, name=name.strip(), sort_order=sort_order))
    db.commit()
    return _redirect_with_msg(f"/ui/admin/adm?proposal_id={proposal_id}", "Tipo de servicio ADM creado exitosamente.")


@router.post("/adm/service-types/{adm_service_type_id}/edit")
def admin_edit_adm_service_type(
    adm_service_type_id: int,
    proposal_id: int = Form(...),
    name: str = Form(...),
    sort_order: int = Form(0),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    service_type = db.get(ADMServiceType, adm_service_type_id)
    if not service_type:
        return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Error: Tipo de servicio ADM no encontrado.", status_code=303)

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/adm?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    service_type.name = name.strip()
    service_type.sort_order = sort_order
    service_type.is_active = is_active == "on"
    db.add(service_type)
    db.commit()
    return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Tipo de servicio ADM actualizado exitosamente.", status_code=303)


@router.post("/adm/service-types/{adm_service_type_id}/delete")
def admin_delete_adm_service_type(
    adm_service_type_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    service_type = db.get(ADMServiceType, adm_service_type_id)
    if not service_type:
        return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Error: Tipo de servicio ADM no encontrado.", status_code=303)

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/adm?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    db.execute(delete(ADMServiceTypeActivityCode).where(ADMServiceTypeActivityCode.adm_service_type_id == adm_service_type_id))
    db.delete(service_type)
    db.commit()
    return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Tipo de servicio ADM eliminado exitosamente.", status_code=303)


@router.post("/adm/assign")
def admin_assign_activity_to_adm_service_type(
    proposal_id: int = Form(...),
    adm_service_type_id: int = Form(...),
    activity_code_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    service_type = db.get(ADMServiceType, adm_service_type_id)
    activity = db.get(ActivityCode, activity_code_id)
    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/adm?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect
    if not service_type or not activity:
        return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Error: Tipo de servicio o actividad no encontrada.", status_code=303)
    if service_type.proposal_id != proposal_id or activity.proposal_id != proposal_id:
        return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Error: La actividad y el tipo de servicio deben pertenecer a la misma propuesta.", status_code=303)

    existing_assignment = db.execute(
        select(ADMServiceTypeActivityCode)
        .join(ADMServiceType, ADMServiceType.adm_service_type_id == ADMServiceTypeActivityCode.adm_service_type_id)
        .where(
            ADMServiceType.proposal_id == proposal_id,
            ADMServiceTypeActivityCode.activity_code_id == activity_code_id,
        )
    ).scalar_one_or_none()
    if existing_assignment:
        return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Error: Esa actividad ya estÃ¡ asignada a un tipo de servicio ADM.", status_code=303)

    db.add(ADMServiceTypeActivityCode(adm_service_type_id=adm_service_type_id, activity_code_id=activity_code_id))
    db.commit()
    return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Actividad asignada exitosamente.", status_code=303)


@router.post("/adm/unassign")
def admin_unassign_activity_from_adm_service_type(
    proposal_id: int = Form(...),
    mapping_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    mapping = db.get(ADMServiceTypeActivityCode, mapping_id)
    if not mapping:
        return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=Error: AsignaciÃ³n no encontrada.", status_code=303)
    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/adm?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect
    db.delete(mapping)
    db.commit()
    return RedirectResponse(f"/ui/admin/adm?proposal_id={proposal_id}&msg=AsignaciÃ³n removida exitosamente.", status_code=303)


# ============================================================
# VCA MANAGEMENT
# ============================================================

@router.get("/vca", response_class=HTMLResponse)
def admin_vca(
    request: Request,
    proposal_id: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()
    selected_proposal = db.get(Proposal, proposal_id) if proposal_id else None
    columns = []
    assigned_activity_ids: set[int] = set()
    activities = []

    if selected_proposal:
        columns = db.execute(
            select(VCAColumn).where(VCAColumn.proposal_id == selected_proposal.proposal_id).order_by(VCAColumn.sort_order, VCAColumn.name)
        ).scalars().all()
        mappings = db.execute(
            select(VCAColumnActivityCode, ActivityCode)
            .join(ActivityCode, ActivityCode.activity_code_id == VCAColumnActivityCode.activity_code_id)
            .join(VCAColumn, VCAColumn.vca_column_id == VCAColumnActivityCode.vca_column_id)
            .where(VCAColumn.proposal_id == selected_proposal.proposal_id)
            .order_by(VCAColumn.vca_column_id, ActivityCode.code)
        ).all()
        activity_map: dict[int, list[dict]] = {}
        for mapping, activity in mappings:
            activity_map.setdefault(mapping.vca_column_id, []).append({"mapping_id": mapping.id, "activity": activity})
            assigned_activity_ids.add(activity.activity_code_id)
        for column in columns:
            setattr(column, "assigned_activities", activity_map.get(column.vca_column_id, []))

        activities = db.execute(
            select(ActivityCode)
            .where(ActivityCode.proposal_id == selected_proposal.proposal_id)
            .order_by(ActivityCode.code)
        ).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/vca.html",
        {
            "request": request,
            "current_user": current_user,
            "msg": msg,
            "proposals": proposals,
            "selected_proposal_id": proposal_id,
            "selected_proposal": selected_proposal,
            "columns": columns,
            "activities": activities,
            "assigned_activity_ids": assigned_activity_ids,
        },
    )


@router.post("/vca/columns/create")
def admin_create_vca_column(
    proposal_id: int = Form(...),
    name: str = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/vca", "Error: Propuesta no encontrada.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/vca?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    column = VCAColumn(proposal_id=proposal_id, name=name.strip(), sort_order=sort_order)
    db.add(column)
    db.commit()
    return _redirect_with_msg(f"/ui/admin/vca?proposal_id={proposal_id}", "Columna VCA creada exitosamente.")


@router.post("/vca/columns/{vca_column_id}/delete")
def admin_delete_vca_column(
    vca_column_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    column = db.get(VCAColumn, vca_column_id)
    if not column:
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: Columna VCA no encontrada.", status_code=303)

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/vca?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    if column.proposal_id != proposal_id:
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: La columna no pertenece a la propuesta seleccionada.", status_code=303)

    db.execute(
        delete(VCAColumnActivityCode).where(VCAColumnActivityCode.vca_column_id == vca_column_id)
    )
    db.delete(column)
    db.commit()
    return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Columna VCA eliminada exitosamente.", status_code=303)


@router.post("/vca/columns/{vca_column_id}/edit")
def admin_edit_vca_column(
    vca_column_id: int,
    proposal_id: int = Form(...),
    name: str = Form(...),
    sort_order: int = Form(0),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    column = db.get(VCAColumn, vca_column_id)
    if not column:
        return RedirectResponse("/ui/admin/vca?msg=Error: Columna VCA no encontrada.", status_code=303)

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/vca?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    column.name = name.strip()
    column.sort_order = sort_order
    column.is_active = is_active == "on"
    db.add(column)
    db.commit()
    return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Columna VCA actualizada exitosamente.", status_code=303)


@router.post("/vca/assign")
def admin_assign_activity_to_vca_column(
    proposal_id: int = Form(...),
    vca_column_id: int = Form(...),
    activity_code_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    column = db.get(VCAColumn, vca_column_id)
    activity = db.get(ActivityCode, activity_code_id)
    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/vca?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect
    if not column or not activity:
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: Columna o actividad no encontrada.", status_code=303)
    if column.proposal_id != proposal_id or activity.proposal_id != proposal_id:
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: La actividad y la columna deben pertenecer a la misma propuesta.", status_code=303)

    existing_assignment = db.execute(
        select(VCAColumnActivityCode)
        .join(VCAColumn, VCAColumn.vca_column_id == VCAColumnActivityCode.vca_column_id)
        .where(
            VCAColumn.proposal_id == proposal_id,
            VCAColumnActivityCode.activity_code_id == activity_code_id,
        )
    ).scalar_one_or_none()
    if existing_assignment:
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: Esa actividad ya estÃ¡ asignada a una columna VCA.", status_code=303)

    db.add(VCAColumnActivityCode(vca_column_id=vca_column_id, activity_code_id=activity_code_id))
    db.commit()
    return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Actividad asignada exitosamente.", status_code=303)


@router.post("/vca/unassign")
def admin_unassign_activity_from_vca_column(
    proposal_id: int = Form(...),
    mapping_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    mapping = db.get(VCAColumnActivityCode, mapping_id)
    if not mapping:
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: AsignaciÃ³n no encontrada.", status_code=303)
    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/vca?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect
    db.delete(mapping)
    db.commit()
    return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=AsignaciÃ³n removida exitosamente.", status_code=303)


# ============================================================
# ACTIVITY CODE MANAGEMENT
# ============================================================

@router.get("/activity-codes", response_class=HTMLResponse)
def admin_activity_codes(
    request: Request,
    proposal_id: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    codes_stmt = (
        select(
            ActivityCode,
            Proposal.code.label("proposal_code"),
            Proposal.name.label("proposal_name"),
            ActivityProductivityGoal,
        )
        .outerjoin(Proposal, ActivityCode.proposal_id == Proposal.proposal_id)
        .outerjoin(
            ActivityProductivityGoal,
            (ActivityProductivityGoal.activity_code_id == ActivityCode.activity_code_id)
            & (ActivityProductivityGoal.proposal_id == ActivityCode.proposal_id),
        )
    )

    if proposal_id:
        codes_stmt = codes_stmt.where(ActivityCode.proposal_id == proposal_id)

    codes = db.execute(
        codes_stmt.order_by(ActivityCode.code)
    ).all()
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()
    selected_proposal = db.get(Proposal, proposal_id) if proposal_id else None

    return templates.TemplateResponse(
        "ui/admin/activity_codes.html",
        {
            "request": request,
            "current_user": current_user,
            "codes": codes,
            "proposals": proposals,
            "selected_proposal_id": proposal_id,
            "selected_proposal": selected_proposal,
            "msg": msg,
            "productivity_goal_type_options": PRODUCTIVITY_GOAL_TYPE_OPTIONS,
            "format_activity_productivity_goal_summary": _format_activity_productivity_goal_summary,
        },
    )


@router.post("/activity-codes/create")
def admin_create_activity_code(
    code: str = Form(...),
    description: str | None = Form(default=None),
    proposal_id: int | None = Form(default=None),
    productivity_goal_type: str | None = Form(default="none"),
    productivity_goal_value: str | None = Form(default=None),
    productivity_period_goal_value: str | None = Form(default=None),
    productivity_goal_is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.execute(
        select(ActivityCode).where(ActivityCode.code == code)
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg("/ui/admin/activity-codes", "Error: El cÃ³digo ya existe.")

    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal:
            return _redirect_with_msg("/ui/admin/activity-codes", "Error: La propuesta seleccionada no existe.")

    normalized_proposal_id = proposal_id if proposal_id else None

    try:
        normalized_goal_type, normalized_goal_value, normalized_period_goal_value = _normalize_activity_productivity_goal(
            productivity_goal_type,
            productivity_goal_value,
            productivity_period_goal_value,
            normalized_proposal_id,
        )
    except ValueError as exc:
        return _redirect_with_msg("/ui/admin/activity-codes", str(exc))

    ac = ActivityCode(
        code=code.strip(),
        description=description,
        proposal_id=normalized_proposal_id,
    )
    db.add(ac)
    db.flush()

    _upsert_activity_productivity_goal(
        db,
        ac,
        normalized_goal_type,
        normalized_goal_value,
        normalized_period_goal_value,
        productivity_goal_is_active == "on",
    )

    db.commit()

    return _redirect_with_msg("/ui/admin/activity-codes", "CÃ³digo de actividad creado exitosamente.")


@router.post("/activity-codes/{activity_code_id}/edit")
def admin_edit_activity_code(
    activity_code_id: int,
    code: str = Form(...),
    description: str | None = Form(default=None),
    proposal_id: int | None = Form(default=None),
    productivity_goal_type: str | None = Form(default="none"),
    productivity_goal_value: str | None = Form(default=None),
    productivity_period_goal_value: str | None = Form(default=None),
    productivity_goal_is_active: str | None = Form(default=None),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ac = db.get(ActivityCode, activity_code_id)
    if not ac:
        return RedirectResponse(
            "/ui/admin/activity-codes?msg=Error: CÃ³digo no encontrado.",
            status_code=303,
        )

    existing = db.execute(
        select(ActivityCode).where(
            ActivityCode.code == code,
            ActivityCode.activity_code_id != activity_code_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            "/ui/admin/activity-codes?msg=Error: El cÃ³digo ya estÃ¡ en uso.",
            status_code=303,
        )

    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal:
            return RedirectResponse(
                "/ui/admin/activity-codes?msg=Error: La propuesta seleccionada no existe.",
                status_code=303,
            )

    normalized_proposal_id = proposal_id if proposal_id else None

    try:
        normalized_goal_type, normalized_goal_value, normalized_period_goal_value = _normalize_activity_productivity_goal(
            productivity_goal_type,
            productivity_goal_value,
            productivity_period_goal_value,
            normalized_proposal_id,
        )
    except ValueError as exc:
        return RedirectResponse(
            f"/ui/admin/activity-codes?msg={quote_plus(str(exc))}",
            status_code=303,
        )

    ac.code = code.strip()
    ac.description = description
    ac.proposal_id = normalized_proposal_id
    ac.is_active = is_active == "on"

    db.add(ac)
    db.flush()

    _upsert_activity_productivity_goal(
        db,
        ac,
        normalized_goal_type,
        normalized_goal_value,
        normalized_period_goal_value,
        productivity_goal_is_active == "on",
    )

    db.commit()

    return RedirectResponse(
        "/ui/admin/activity-codes?msg=CÃ³digo de actividad actualizado exitosamente.",
        status_code=303,
    )


@router.post("/activity-codes/{activity_code_id}/delete")
def admin_delete_activity_code(
    activity_code_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    session_count = db.execute(
        select(func.count()).select_from(ActivitySession).where(
            ActivitySession.activity_code_id == activity_code_id
        )
    ).scalar()

    if session_count and session_count > 0:
        return RedirectResponse(
            "/ui/admin/activity-codes?msg=Error: No se puede eliminar, tiene sesiones asociadas. DesactÃ­velo en su lugar.",
            status_code=303,
        )

    ac = db.get(ActivityCode, activity_code_id)
    if not ac:
        return RedirectResponse(
            "/ui/admin/activity-codes?msg=Error: CÃ³digo no encontrado.",
            status_code=303,
        )

    db.execute(
        delete(ActivityProductivityGoal).where(
            ActivityProductivityGoal.activity_code_id == activity_code_id
        )
    )
    db.delete(ac)
    db.commit()

    return RedirectResponse(
        "/ui/admin/activity-codes?msg=CÃ³digo de actividad eliminado exitosamente.",
        status_code=303,
    )


# ============================================================
# EMPLOYEE MANAGEMENT
# ============================================================

@router.get("/employees", response_class=HTMLResponse)
def admin_employees(
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    employees = db.execute(
        select(Employee).order_by(Employee.full_name)
    ).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/employees.html",
        {
            "request": request,
            "current_user": current_user,
            "employees": employees,
            "msg": msg,
        },
    )


@router.post("/employees/create")
def admin_create_employee(
    full_name: str = Form(...),
    employee_code: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if employee_code:
        existing = db.execute(
            select(Employee).where(Employee.employee_code == employee_code)
        ).scalar_one_or_none()
        if existing:
            return _redirect_with_msg("/ui/admin/employees", "Error: El cÃ³digo de empleado ya existe.")

    emp = Employee(
        full_name=full_name,
        employee_code=employee_code if employee_code else None,
    )
    db.add(emp)
    db.commit()

    return _redirect_with_msg("/ui/admin/employees", "Empleado creado exitosamente.")


@router.post("/employees/{employee_id}/edit")
def admin_edit_employee(
    employee_id: int,
    full_name: str = Form(...),
    employee_code: str | None = Form(default=None),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    emp = db.get(Employee, employee_id)
    if not emp:
        return RedirectResponse(
            "/ui/admin/employees?msg=Error: Empleado no encontrado.",
            status_code=303,
        )

    if employee_code:
        existing = db.execute(
            select(Employee).where(
                Employee.employee_code == employee_code,
                Employee.employee_id != employee_id,
            )
        ).scalar_one_or_none()
        if existing:
            return RedirectResponse(
                "/ui/admin/employees?msg=Error: El cÃ³digo de empleado ya estÃ¡ en uso.",
                status_code=303,
            )

    emp.full_name = full_name
    emp.employee_code = employee_code if employee_code else None
    emp.is_active = is_active == "on"

    db.add(emp)
    db.commit()

    return RedirectResponse(
        "/ui/admin/employees?msg=Empleado actualizado exitosamente.",
        status_code=303,
    )


@router.post("/employees/{employee_id}/delete")
def admin_delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    session_count = db.execute(
        select(func.count()).select_from(ActivitySession).where(
            ActivitySession.employee_id == employee_id
        )
    ).scalar()

    if session_count and session_count > 0:
        return RedirectResponse(
            "/ui/admin/employees?msg=Error: No se puede eliminar, tiene sesiones asociadas. DesactÃ­velo en su lugar.",
            status_code=303,
        )

    emp = db.get(Employee, employee_id)
    if not emp:
        return RedirectResponse(
            "/ui/admin/employees?msg=Error: Empleado no encontrado.",
            status_code=303,
        )

    db.delete(emp)
    db.commit()

    return RedirectResponse(
        "/ui/admin/employees?msg=Empleado eliminado exitosamente.",
        status_code=303,
    )


# ============================================================
# PROPOSAL MANAGEMENT
# ============================================================

@router.get("/proposals", response_class=HTMLResponse)
def admin_proposals(
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposals = db.execute(
        select(Proposal).order_by(Proposal.code)
    ).scalars().all()

    participant_counts = dict(
        db.execute(
            select(ProposalParticipant.proposal_id, func.count(ProposalParticipant.proposal_participant_id))
            .group_by(ProposalParticipant.proposal_id)
        ).all()
    )

    return templates.TemplateResponse(
        "ui/admin/proposals.html",
        {
            "request": request,
            "current_user": current_user,
            "proposals": proposals,
            "participant_counts": participant_counts,
            "msg": msg,
        },
    )


@router.get("/proposal-participants", response_class=HTMLResponse)
def admin_proposal_participants(
    request: Request,
    proposal_id: int | None = None,
    residential_id: str | None = None,
    status_filter: str | None = "active",
    q: str | None = None,
    only_available: int = 1,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_supervisor),
):
    selected_residential_id = int(residential_id) if residential_id and residential_id.strip() else None

    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()
    residentials = db.execute(
        select(Residential).where(Residential.is_active == True).order_by(Residential.code)  # noqa: E712
    ).scalars().all()
    selected_proposal = db.get(Proposal, proposal_id) if proposal_id else None

    assigned_rows = []
    assigned_person_ids: set[int] = set()
    if selected_proposal:
        assigned_stmt = (
            select(ProposalParticipant, Person, User.username.label("owner_username"), Residential.name.label("residential_name"))
            .join(Person, Person.person_id == ProposalParticipant.person_id)
            .outerjoin(User, User.user_id == ProposalParticipant.created_by_user_id)
            .outerjoin(Residential, Residential.residential_id == User.residential_id)
            .where(ProposalParticipant.proposal_id == selected_proposal.proposal_id)
            .order_by(Person.apellido_paterno, Person.apellido_materno, Person.nombre)
        )
        if not is_admin_or_supervisor(current_user):
            assigned_stmt = assigned_stmt.where(ProposalParticipant.created_by_user_id == current_user.user_id)

        assigned_pairs = db.execute(assigned_stmt).all()
        for proposal_participant, person, owner_username, residential_name in assigned_pairs:
            assigned_person_ids.add(person.person_id)

            source_participant = None
            is_outdated = False
            outdated_fields: list[str] = []
            if person.legacy_participant_id:
                source_participant = db.execute(
                    select(Participant).where(Participant.participant_id == person.legacy_participant_id)
                ).scalar_one_or_none()

            if source_participant:
                comparisons = [
                    ("nombre", person.nombre, source_participant.nombre),
                    ("inicial", person.inicial, source_participant.inicial),
                    ("apellido_paterno", person.apellido_paterno, source_participant.apellido_paterno),
                    ("apellido_materno", person.apellido_materno, source_participant.apellido_materno),
                    ("genero", person.genero, source_participant.genero),
                    ("fecha_nacimiento", person.fecha_nacimiento, source_participant.fecha_nacimiento),
                    ("expediente", proposal_participant.expediente_num, source_participant.expediente_num),
                    ("edificio", proposal_participant.edificio, source_participant.edificio),
                    ("apartamento", proposal_participant.apart, source_participant.apart),
                    ("vca", proposal_participant.vca, source_participant.vca),
                    ("primera_vez", proposal_participant.primera_vez, source_participant.primera_vez),
                    ("composicion_familiar", proposal_participant.composicion_familiar, source_participant.composicion_familiar),
                    ("estatus", proposal_participant.estatus, source_participant.estatus),
                    ("grupo_familiar", proposal_participant.grupo_familiar, source_participant.grupo_familiar),
                    ("fuente_ingreso_principal", proposal_participant.fuente_ingreso_principal, source_participant.fuente_ingreso_principal),
                    ("rango_ingreso", proposal_participant.rango_ingreso, source_participant.rango_ingreso),
                    ("is_active", bool(getattr(proposal_participant, "is_active", False)), bool(getattr(source_participant, "is_active", False))),
                ]
                for field_name, current_value, source_value in comparisons:
                    if _values_differ_for_sync(current_value, source_value):
                        is_outdated = True
                        outdated_fields.append(field_name)

            assigned_rows.append({
                "proposal_participant": proposal_participant,
                "person": person,
                "owner_username": owner_username,
                "residential_name": residential_name,
                "is_active": bool(getattr(proposal_participant, "is_active", False)),
                "is_outdated": is_outdated,
                "outdated_fields": outdated_fields,
                "has_source_participant": source_participant is not None,
            })

    available_rows = []
    q_value = (q or "").strip()
    normalized_status_filter = (status_filter or "all").strip().lower()

    if selected_proposal:
        participant_stmt = (
            select(
                Participant,
                User.username.label("owner_username"),
                User.residential_id.label("owner_residential_id"),
                Residential.name.label("residential_name"),
                Person.person_id.label("person_id"),
            )
            .outerjoin(User, User.user_id == Participant.created_by_user_id)
            .outerjoin(Residential, Residential.residential_id == User.residential_id)
            .outerjoin(Person, Person.legacy_participant_id == Participant.participant_id)
            .order_by(Residential.name, Participant.apellido_paterno, Participant.apellido_materno, Participant.nombre)
        )
        if not is_admin_or_supervisor(current_user):
            participant_stmt = participant_stmt.where(Participant.created_by_user_id == current_user.user_id)

        if selected_residential_id:
            participant_stmt = participant_stmt.where(User.residential_id == selected_residential_id)

        if normalized_status_filter == "active":
            participant_stmt = participant_stmt.where(Participant.is_active == True)  # noqa: E712
        elif normalized_status_filter == "inactive":
            participant_stmt = participant_stmt.where(Participant.is_active == False)  # noqa: E712

        if q_value:
            search = f"%{q_value}%"
            participant_stmt = participant_stmt.where(
                Participant.expediente_num.ilike(search)
                | Participant.nombre.ilike(search)
                | Participant.apellido_paterno.ilike(search)
                | Participant.apellido_materno.ilike(search)
            )

        participant_rows = db.execute(participant_stmt).all()
        for participant, owner_username, owner_residential_id, residential_name, person_id in participant_rows:
            if only_available and person_id in assigned_person_ids:
                continue
            available_rows.append({
                "participant": participant,
                "owner_username": owner_username,
                "owner_residential_id": owner_residential_id,
                "residential_name": residential_name,
                "person_id": person_id,
                "age": _calc_age(participant.fecha_nacimiento),
                "is_active": bool(getattr(participant, "is_active", False)),
            })

    return templates.TemplateResponse(
        "ui/admin/proposal_participants.html",
        {
            "request": request,
            "current_user": current_user,
            "msg": msg,
            "proposals": proposals,
            "residentials": residentials,
            "selected_proposal": selected_proposal,
            "selected_residential_id": selected_residential_id,
            "selected_status_filter": normalized_status_filter,
            "assigned_rows": assigned_rows,
            "available_rows": available_rows,
            "q": q_value,
            "only_available": bool(only_available),
        },
    )


@router.post("/proposal-participants/add")
def admin_add_participants_to_proposal(
    proposal_id: int = Form(...),
    participant_ids: list[int] = Form(default=[]),
    residential_id: int | None = Form(default=None),
    status_filter: str | None = Form(default="active"),
    q: str | None = Form(default=None),
    only_available: int = Form(default=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_supervisor),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/proposal-participants", "Error: Propuesta no encontrada.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y no permite asociar participantes.",
    )
    if redirect:
        return redirect

    if not participant_ids:
        return _redirect_with_msg(
            f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
            "Error: Debe seleccionar al menos un participante.",
        )

    participants = db.execute(
        select(Participant).where(Participant.participant_id.in_(participant_ids))
    ).scalars().all()
    participant_map = {p.participant_id: p for p in participants}

    created_count = 0
    skipped_count = 0

    for participant_id in participant_ids:
        participant = participant_map.get(participant_id)
        if not participant:
            skipped_count += 1
            continue

        if not is_admin_or_supervisor(current_user) and participant.created_by_user_id != current_user.user_id:
            skipped_count += 1
            continue

        person = db.execute(
            select(Person).where(Person.legacy_participant_id == participant.participant_id)
        ).scalar_one_or_none()
        if not person:
            person = Person(
                legacy_participant_id=participant.participant_id,
                nombre=participant.nombre,
                inicial=participant.inicial,
                apellido_paterno=participant.apellido_paterno,
                apellido_materno=participant.apellido_materno,
                genero=participant.genero,
                fecha_nacimiento=participant.fecha_nacimiento,
            )
            db.add(person)
            db.flush()

        exists = db.execute(
            select(ProposalParticipant).where(
                ProposalParticipant.proposal_id == proposal_id,
                ProposalParticipant.person_id == person.person_id,
            )
        ).scalar_one_or_none()
        if exists:
            skipped_count += 1
            continue

        proposal_participant = ProposalParticipant(
            proposal_id=proposal_id,
            person_id=person.person_id,
            created_by_user_id=participant.created_by_user_id,
            exp_year=participant.exp_year,
            exp_employee_initials=participant.exp_employee_initials,
            exp_seq4=participant.exp_seq4,
            expediente_num=participant.expediente_num,
            edificio=participant.edificio,
            apart=participant.apart,
            vca=participant.vca,
            primera_vez=participant.primera_vez,
            composicion_familiar=participant.composicion_familiar,
            estatus=participant.estatus,
            grupo_familiar=participant.grupo_familiar,
            fuente_ingreso_principal=participant.fuente_ingreso_principal,
            rango_ingreso=participant.rango_ingreso,
            is_active=bool(getattr(participant, "is_active", False)),
        )
        db.add(proposal_participant)
        created_count += 1

    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
        f"{created_count} participante(s) asociado(s) exitosamente. {skipped_count} omitido(s).",
    )


@router.post("/proposal-participants/{proposal_participant_id}/sync")
def admin_sync_proposal_participant(
    proposal_participant_id: int,
    proposal_id: int = Form(...),
    residential_id: int | None = Form(default=None),
    status_filter: str | None = Form(default="active"),
    q: str | None = Form(default=None),
    only_available: int = Form(default=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_supervisor),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/proposal-participants", "Error: Propuesta no encontrada.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y no permite sincronizar participantes.",
    )
    if redirect:
        return redirect

    proposal_participant = db.get(ProposalParticipant, proposal_participant_id)
    if not proposal_participant or proposal_participant.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
            "Error: Participante asociado no encontrado.",
        )

    person = db.get(Person, proposal_participant.person_id)
    if not person or not person.legacy_participant_id:
        return _redirect_with_msg(
            f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
            "Error: Este participante asociado no estÃ¡ vinculado a un registro de New-list.",
        )

    participant = db.execute(
        select(Participant).where(Participant.participant_id == person.legacy_participant_id)
    ).scalar_one_or_none()
    if not participant:
        return _redirect_with_msg(
            f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
            "Error: No se encontrÃ³ el participante fuente en New-list.",
        )

    if not is_admin_or_supervisor(current_user) and participant.created_by_user_id != current_user.user_id:
        return _redirect_with_msg(
            f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
            "Error: No tienes permiso para sincronizar este participante.",
        )

    _sync_proposal_participant_from_source(proposal_participant, person, participant)
    db.add(person)
    db.add(proposal_participant)

    sibling_rows = db.execute(
        select(ProposalParticipant, Proposal)
        .join(Proposal, Proposal.proposal_id == ProposalParticipant.proposal_id)
        .where(
            ProposalParticipant.person_id == person.person_id,
            ProposalParticipant.proposal_participant_id != proposal_participant_id,
        )
    ).all()

    synced_count = 1
    for sibling_proposal_participant, sibling_proposal in sibling_rows:
        if is_proposal_finalized(sibling_proposal):
            continue
        _sync_proposal_participant_from_source(sibling_proposal_participant, person, participant)
        db.add(sibling_proposal_participant)
        synced_count += 1

    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
        f"Participante sincronizado desde New-list exitosamente en {synced_count} propuesta(s) activa(s).",
    )


@router.post("/proposal-participants/sync-all")
def admin_sync_all_proposal_participants(
    proposal_id: int = Form(...),
    residential_id: int | None = Form(default=None),
    status_filter: str | None = Form(default="active"),
    q: str | None = Form(default=None),
    only_available: int = Form(default=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_supervisor),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/proposal-participants", "Error: Propuesta no encontrada.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y no permite sincronizar participantes.",
    )
    if redirect:
        return redirect

    stmt = select(ProposalParticipant, Person).join(Person, Person.person_id == ProposalParticipant.person_id).where(
        ProposalParticipant.proposal_id == proposal_id
    )
    if residential_id:
        stmt = stmt.join(User, User.user_id == ProposalParticipant.created_by_user_id).where(User.residential_id == residential_id)
    if not is_admin_or_supervisor(current_user):
        stmt = stmt.where(ProposalParticipant.created_by_user_id == current_user.user_id)

    rows = db.execute(stmt).all()
    synced_count = 0
    skipped_count = 0

    for proposal_participant, person in rows:
        if not person.legacy_participant_id:
            skipped_count += 1
            continue

        participant = db.execute(
            select(Participant).where(Participant.participant_id == person.legacy_participant_id)
        ).scalar_one_or_none()
        if not participant:
            skipped_count += 1
            continue

        if not is_admin_or_supervisor(current_user) and participant.created_by_user_id != current_user.user_id:
            skipped_count += 1
            continue

        normalized_status_filter = (status_filter or "all").strip().lower()
        participant_is_active = bool(getattr(participant, "is_active", False))
        if normalized_status_filter == "active" and not participant_is_active:
            skipped_count += 1
            continue
        if normalized_status_filter == "inactive" and participant_is_active:
            skipped_count += 1
            continue

        q_value = (q or "").strip().lower()
        if q_value:
            haystack = " ".join([
                participant.expediente_num or "",
                participant.nombre or "",
                participant.apellido_paterno or "",
                participant.apellido_materno or "",
            ]).lower()
            if q_value not in haystack:
                skipped_count += 1
                continue

        person.nombre = participant.nombre
        person.inicial = participant.inicial
        person.apellido_paterno = participant.apellido_paterno
        person.apellido_materno = participant.apellido_materno
        person.genero = participant.genero
        person.fecha_nacimiento = participant.fecha_nacimiento

        proposal_participant.created_by_user_id = participant.created_by_user_id
        proposal_participant.exp_year = participant.exp_year
        proposal_participant.exp_employee_initials = participant.exp_employee_initials
        proposal_participant.exp_seq4 = participant.exp_seq4
        proposal_participant.expediente_num = participant.expediente_num
        proposal_participant.edificio = participant.edificio
        proposal_participant.apart = participant.apart
        proposal_participant.vca = participant.vca
        proposal_participant.primera_vez = participant.primera_vez
        proposal_participant.composicion_familiar = participant.composicion_familiar
        proposal_participant.estatus = participant.estatus
        proposal_participant.grupo_familiar = participant.grupo_familiar
        proposal_participant.fuente_ingreso_principal = participant.fuente_ingreso_principal
        proposal_participant.rango_ingreso = participant.rango_ingreso
        proposal_participant.is_active = participant_is_active

        db.add(person)
        db.add(proposal_participant)
        synced_count += 1

    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
        f"SincronizaciÃ³n completada. {synced_count} participante(s) actualizado(s). {skipped_count} omitido(s).",
    )


@router.post("/proposal-participants/{proposal_participant_id}/remove")
def admin_remove_participant_from_proposal(
    proposal_participant_id: int,
    proposal_id: int = Form(...),
    residential_id: int | None = Form(default=None),
    status_filter: str | None = Form(default="active"),
    q: str | None = Form(default=None),
    only_available: int = Form(default=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin_or_supervisor),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/proposal-participants", "Error: Propuesta no encontrada.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y no permite remover participantes.",
    )
    if redirect:
        return redirect

    proposal_participant = db.get(ProposalParticipant, proposal_participant_id)
    if not proposal_participant or proposal_participant.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
            "Error: Participante asociado no encontrado.",
        )

    from app.models.attendance import Attendance

    used_count = db.execute(
        select(func.count()).select_from(Attendance).where(
            Attendance.proposal_participant_id == proposal_participant_id
        )
    ).scalar() or 0

    if used_count > 0:
        return _redirect_with_msg(
            f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
            "Error: No se puede remover porque ya tiene asistencias registradas en esta propuesta.",
        )

    db.delete(proposal_participant)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/proposal-participants?proposal_id={proposal_id}&residential_id={residential_id or ''}&status_filter={quote_plus((status_filter or 'active').strip())}&q={quote_plus((q or '').strip())}&only_available={only_available}",
        "Participante removido de la propuesta exitosamente.",
    )


@router.post("/proposals/create")
def admin_create_proposal(
    code: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    code = code.strip()
    name = name.strip()

    existing = db.execute(
        select(Proposal).where(Proposal.code == code)
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg("/ui/admin/proposals", "Error: El cÃ³digo de propuesta ya existe.")

    proposal = Proposal(code=code, name=name, description=description, status="active")
    db.add(proposal)
    db.commit()

    return _redirect_with_msg("/ui/admin/proposals", "Propuesta creada exitosamente.")


@router.post("/proposals/{proposal_id}/edit")
def admin_edit_proposal(
    proposal_id: int,
    code: str = Form(...),
    name: str = Form(...),
    description: str | None = Form(default=None),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return RedirectResponse(
            "/ui/admin/proposals?msg=Error: Propuesta no encontrada.",
            status_code=303,
        )

    code = code.strip()
    name = name.strip()

    existing = db.execute(
        select(Proposal).where(
            Proposal.code == code,
            Proposal.proposal_id != proposal_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            "/ui/admin/proposals?msg=Error: El cÃ³digo de propuesta ya estÃ¡ en uso.",
            status_code=303,
        )

    if proposal.status == "finalized":
        return RedirectResponse(
            "/ui/admin/proposals?msg=Error: La propuesta estÃ¡ finalizada y no permite ediciÃ³n.",
            status_code=303,
        )

    proposal.code = code
    proposal.name = name
    proposal.description = description
    proposal.is_active = is_active == "on"

    db.add(proposal)
    db.commit()

    return RedirectResponse(
        "/ui/admin/proposals?msg=Propuesta actualizada exitosamente.",
        status_code=303,
    )


@router.post("/proposals/{proposal_id}/visit-reports/delete")
def admin_delete_proposal_visit_reports(
    proposal_id: int,
    admin_password: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/proposals", "Error: Propuesta no encontrada.")

    if not verify_password(admin_password, current_user.password_hash):
        return _redirect_with_msg(
            "/ui/admin/proposals",
            "Error: La contraseÃ±a de administrador no es correcta.",
        )

    reports = db.execute(
        select(VisitReport).where(VisitReport.proposal_id == proposal_id)
    ).scalars().all()

    if not reports:
        return _redirect_with_msg(
            "/ui/admin/proposals",
            "No hay informes de visitas para limpiar en esta propuesta.",
        )

    delete_visit_reports_and_referrals(db, reports)
    db.commit()

    return _redirect_with_msg(
        "/ui/admin/proposals",
        f"Se eliminaron {len(reports)} informe(s) de visitas asociados a la propuesta.",
    )


@router.post("/proposals/{proposal_id}/delete")
def admin_delete_proposal(
    proposal_id: int,
    admin_password: str = Form(...),
    delete_confirmation: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/proposals", "Error: Propuesta no encontrada.")

    if delete_confirmation.strip().upper() != "ELIMINAR":
        return _redirect_with_msg(
            "/ui/admin/proposals",
            "Error: Debe escribir ELIMINAR para confirmar el borrado de la propuesta.",
        )

    if not verify_password(admin_password, current_user.password_hash):
        return _redirect_with_msg(
            "/ui/admin/proposals",
            "Error: La contraseÃ±a de administrador no es correcta.",
        )

    blockers: list[str] = []

    session_count = db.execute(
        select(func.count()).select_from(ActivitySession).where(ActivitySession.proposal_id == proposal_id)
    ).scalar() or 0
    if session_count > 0:
        blockers.append(f"{session_count} sesiÃ³n(es)")

    participant_count = db.execute(
        select(func.count()).select_from(ProposalParticipant).where(ProposalParticipant.proposal_id == proposal_id)
    ).scalar() or 0
    if participant_count > 0:
        blockers.append(f"{participant_count} participante(s) asociados")

    linked_activity_codes = db.execute(
        select(func.count()).select_from(ActivityCode).where(ActivityCode.proposal_id == proposal_id)
    ).scalar() or 0
    if linked_activity_codes > 0:
        blockers.append(f"{linked_activity_codes} actividad(es)")

    vca_column_count = db.execute(
        select(func.count()).select_from(VCAColumn).where(VCAColumn.proposal_id == proposal_id)
    ).scalar() or 0
    if vca_column_count > 0:
        blockers.append(f"{vca_column_count} configuraciÃ³n(es) VCA")

    population_group_count = db.execute(
        select(func.count()).select_from(ProposalPopulationGroup).where(ProposalPopulationGroup.proposal_id == proposal_id)
    ).scalar() or 0
    if population_group_count > 0:
        blockers.append(f"{population_group_count} grupo(s) de poblaciÃ³n")

    report_program_count = db.execute(
        select(func.count()).select_from(ProposalReportProgram).where(ProposalReportProgram.proposal_id == proposal_id)
    ).scalar() or 0
    if report_program_count > 0:
        blockers.append(f"{report_program_count} programa(s) de reporte")

    visit_mapping_count = db.execute(
        select(func.count()).select_from(VisitActivityMapping).where(VisitActivityMapping.proposal_id == proposal_id)
    ).scalar() or 0
    if visit_mapping_count > 0:
        blockers.append(f"{visit_mapping_count} mapeo(s) de visitas")

    visit_report_count = db.execute(
        select(func.count())
        .select_from(VisitReport)
        .join(VisitReportReferral, VisitReportReferral.report_id == VisitReport.report_id)
        .where(VisitReport.proposal_id == proposal_id)
    ).scalar() or 0
    if visit_report_count > 0:
        blockers.append(f"{visit_report_count} reporte(s) de visitas")

    pregnancy_report_count = db.execute(
        select(func.count()).select_from(PregnancyReport).where(PregnancyReport.proposal_id == proposal_id)
    ).scalar() or 0
    if pregnancy_report_count > 0:
        blockers.append(f"{pregnancy_report_count} reporte(s) de embarazo")

    school_grade_report_count = db.execute(
        select(func.count()).select_from(SchoolGradeReport).where(SchoolGradeReport.proposal_id == proposal_id)
    ).scalar() or 0
    if school_grade_report_count > 0:
        blockers.append(f"{school_grade_report_count} reporte(s) de notas")

    school_dropout_report_count = db.execute(
        select(func.count()).select_from(SchoolDropoutReport).where(SchoolDropoutReport.proposal_id == proposal_id)
    ).scalar() or 0
    if school_dropout_report_count > 0:
        blockers.append(f"{school_dropout_report_count} reporte(s) de deserciÃ³n")

    if blockers:
        return _redirect_with_msg(
            "/ui/admin/proposals",
            "Error: No se puede eliminar la propuesta porque todavÃ­a tiene relaciones activas: " + ", ".join(blockers) + ".",
        )

    db.delete(proposal)
    db.commit()

    return _redirect_with_msg(
        "/ui/admin/proposals",
        "Propuesta eliminada exitosamente.",
    )


@router.post("/proposals/{proposal_id}/reopen")
def admin_reopen_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/proposals", "Error: Propuesta no encontrada.")

    proposal.status = "active"
    proposal.is_active = True
    db.add(proposal)
    db.commit()

    return _redirect_with_msg(
        "/ui/admin/proposals",
        "Propuesta reabierta exitosamente. Ya permite operaciÃ³n nuevamente.",
    )


@router.post("/proposals/{proposal_id}/finalize")
def admin_finalize_proposal(
    proposal_id: int,
    finalization_note: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return RedirectResponse(
            "/ui/admin/proposals?msg=Error: Propuesta no encontrada.",
            status_code=303,
        )

    if proposal.status == "finalized":
        return RedirectResponse(
            "/ui/admin/proposals?msg=Error: La propuesta ya estÃ¡ finalizada.",
            status_code=303,
        )

    proposal.status = "finalized"
    proposal.finalized_at = func.sysutcdatetime()
    proposal.finalized_by_user_id = current_user.user_id
    proposal.finalization_note = (finalization_note or "").strip() or None

    db.add(proposal)
    db.commit()

    return RedirectResponse(
        "/ui/admin/proposals?msg=Propuesta finalizada exitosamente. QuedÃ³ en modo solo lectura.",
        status_code=303,
    )


# ============================================================
# PROGRAM REPORT CONFIGURATION
# ============================================================

@router.post("/population-groups/create")
def admin_create_population_group(
    proposal_id: int = Form(...),
    code: str = Form(...),
    label: str = Form(...),
    age_min: int | None = Form(default=None),
    age_max: int | None = Form(default=None),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/report-programs", "Error: La propuesta seleccionada no existe.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    normalized_code = code.strip().lower()
    existing = db.execute(
        select(ProposalPopulationGroup).where(
            ProposalPopulationGroup.proposal_id == proposal_id,
            ProposalPopulationGroup.code == normalized_code,
        )
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Ya existe una categorÃ­a poblacional con ese cÃ³digo en la propuesta.",
        )

    group = ProposalPopulationGroup(
        proposal_id=proposal_id,
        code=normalized_code,
        label=label.strip(),
        age_min=age_min,
        age_max=age_max,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(group)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "CategorÃ­a poblacional creada exitosamente.",
    )


@router.post("/population-groups/{population_group_id}/edit")
def admin_edit_population_group(
    population_group_id: int,
    proposal_id: int = Form(...),
    code: str = Form(...),
    label: str = Form(...),
    age_min: int | None = Form(default=None),
    age_max: int | None = Form(default=None),
    sort_order: int = Form(0),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    group = db.get(ProposalPopulationGroup, population_group_id)
    if not group:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: CategorÃ­a poblacional no encontrada.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    normalized_code = code.strip().lower()
    existing = db.execute(
        select(ProposalPopulationGroup).where(
            ProposalPopulationGroup.proposal_id == proposal_id,
            ProposalPopulationGroup.code == normalized_code,
            ProposalPopulationGroup.population_group_id != population_group_id,
        )
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Ya existe otra categorÃ­a poblacional con ese cÃ³digo en la propuesta.",
        )

    group.code = normalized_code
    group.label = label.strip()
    group.age_min = age_min
    group.age_max = age_max
    group.sort_order = sort_order
    group.is_active = is_active == "on"
    db.add(group)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "CategorÃ­a poblacional actualizada exitosamente.",
    )


@router.post("/population-groups/{population_group_id}/delete")
def admin_delete_population_group(
    population_group_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    group = db.get(ProposalPopulationGroup, population_group_id)
    if not group or group.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: CategorÃ­a poblacional no encontrada.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    related_programs_count = db.execute(
        select(func.count()).select_from(ProposalReportProgram).where(
            ProposalReportProgram.population_group_id == population_group_id
        )
    ).scalar()

    related_program_populations_count = db.execute(
        select(func.count()).select_from(ProposalReportProgramPopulation).where(
            ProposalReportProgramPopulation.population_group_id == population_group_id
        )
    ).scalar()

    if (
        (related_programs_count and related_programs_count > 0)
        or (related_program_populations_count and related_program_populations_count > 0)
    ):
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: No se puede eliminar la categorÃ­a poblacional porque todavÃ­a estÃ¡ asociada a uno o mÃ¡s programas. RemuÃ©vala primero de la configuraciÃ³n correspondiente.",
        )

    db.delete(group)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "CategorÃ­a poblacional eliminada exitosamente.",
    )


@router.get("/report-programs", response_class=HTMLResponse)
def admin_report_programs(
    request: Request,
    proposal_id: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()
    selected_proposal = db.get(Proposal, proposal_id) if proposal_id else None
    programs = []
    population_groups = []
    proposal_activity_codes = []

    if selected_proposal:
        population_groups = db.execute(
            select(ProposalPopulationGroup)
            .where(ProposalPopulationGroup.proposal_id == selected_proposal.proposal_id)
            .order_by(ProposalPopulationGroup.sort_order, ProposalPopulationGroup.code)
        ).scalars().all()
        group_map = {group.population_group_id: group for group in population_groups}

        proposal_activity_codes = db.execute(
            select(ActivityCode)
            .where(
                ActivityCode.proposal_id == selected_proposal.proposal_id,
                ActivityCode.is_active == True,  # noqa: E712
            )
            .order_by(ActivityCode.code)
        ).scalars().all()
        proposal_activity_code_map = {activity.activity_code_id: activity for activity in proposal_activity_codes}

        programs = db.execute(
            select(ProposalReportProgram)
            .where(ProposalReportProgram.proposal_id == selected_proposal.proposal_id)
            .order_by(ProposalReportProgram.sort_order, ProposalReportProgram.code)
        ).scalars().all()

        program_ids = [program.program_id for program in programs]
        synthetic_activity_by_program_id: dict[int, ProposalReportProgramActivity] = {}

        existing_activities = []
        if program_ids:
            existing_activities = db.execute(
                select(ProposalReportProgramActivity)
                .where(ProposalReportProgramActivity.program_id.in_(program_ids))
                .order_by(ProposalReportProgramActivity.program_id, ProposalReportProgramActivity.program_activity_id)
            ).scalars().all()

        for activity in existing_activities:
            synthetic_activity_by_program_id.setdefault(activity.program_id, activity)

        pending_create = False
        for program in programs:
            if program.program_id not in synthetic_activity_by_program_id:
                synthetic_activity = ProposalReportProgramActivity(
                    program_id=program.program_id,
                    code=f"AUTO-{program.code}",
                    label=f"Actividades de {program.name}",
                    sort_order=0,
                    is_active=True,
                )
                db.add(synthetic_activity)
                synthetic_activity_by_program_id[program.program_id] = synthetic_activity
                pending_create = True

        if pending_create:
            db.commit()
            for synthetic_activity in synthetic_activity_by_program_id.values():
                db.refresh(synthetic_activity)

        all_program_activity_ids = [activity.program_activity_id for activity in synthetic_activity_by_program_id.values()]
        assigned_rows = []
        if all_program_activity_ids:
            assigned_rows = db.execute(
                select(ProposalReportProgramActivityCode)
                .where(ProposalReportProgramActivityCode.program_activity_id.in_(all_program_activity_ids))
            ).scalars().all()

        program_populations = []
        if program_ids:
            program_populations = db.execute(
                select(ProposalReportProgramPopulation)
                .where(ProposalReportProgramPopulation.program_id.in_(program_ids))
                .order_by(ProposalReportProgramPopulation.sort_order, ProposalReportProgramPopulation.program_population_id)
            ).scalars().all()

        population_rows_by_program_id: dict[int, list[ProposalReportProgramPopulation]] = {}
        for row in program_populations:
            population_rows_by_program_id.setdefault(row.program_id, []).append(row)

        population_assignment_rows = []
        if program_populations:
            population_assignment_rows = db.execute(
                select(ProposalReportProgramPopulationActivityCode)
                .where(
                    ProposalReportProgramPopulationActivityCode.program_population_id.in_(
                        [row.program_population_id for row in program_populations]
                    )
                )
            ).scalars().all()

        assigned_codes_by_program_id: dict[int, list[ActivityCode]] = {}
        assigned_code_ids_by_program_id: dict[int, set[int]] = {}
        activity_to_program_id = {activity.program_activity_id: activity.program_id for activity in synthetic_activity_by_program_id.values()}

        globally_assigned_activity_code_ids: set[int] = set()
        seen_program_activity_pairs: set[tuple[int, int]] = set()
        for assigned in assigned_rows:
            program_id_for_mapping = activity_to_program_id.get(assigned.program_activity_id)
            activity_code = proposal_activity_code_map.get(assigned.activity_code_id)
            if not program_id_for_mapping or not activity_code:
                continue
            pair_key = (program_id_for_mapping, activity_code.activity_code_id)
            if pair_key in seen_program_activity_pairs:
                continue
            seen_program_activity_pairs.add(pair_key)
            globally_assigned_activity_code_ids.add(activity_code.activity_code_id)
            assigned_codes_by_program_id.setdefault(program_id_for_mapping, []).append(activity_code)
            assigned_code_ids_by_program_id.setdefault(program_id_for_mapping, set()).add(activity_code.activity_code_id)

        population_assignment_map: dict[int, list[ActivityCode]] = {}
        population_assignment_id_map: dict[int, set[int]] = {}
        population_by_id = {row.program_population_id: row for row in program_populations}
        for assigned in population_assignment_rows:
            population_row = population_by_id.get(assigned.program_population_id)
            activity_code = proposal_activity_code_map.get(assigned.activity_code_id)
            if not population_row or not activity_code:
                continue
            globally_assigned_activity_code_ids.add(activity_code.activity_code_id)
            population_assignment_map.setdefault(population_row.program_population_id, []).append(activity_code)
            population_assignment_id_map.setdefault(population_row.program_population_id, set()).add(activity_code.activity_code_id)

        for program in programs:
            setattr(program, "population_group_obj", group_map.get(program.population_group_id))
            assigned_codes = assigned_codes_by_program_id.get(program.program_id, [])
            assigned_codes = sorted(assigned_codes, key=lambda item: (item.code or "", item.description or ""))
            assigned_ids = assigned_code_ids_by_program_id.get(program.program_id, set())
            available_codes = [
                code for code in proposal_activity_codes
                if code.activity_code_id not in globally_assigned_activity_code_ids or code.activity_code_id in assigned_ids
            ]
            setattr(program, "assignment_activity", synthetic_activity_by_program_id.get(program.program_id))
            setattr(program, "assigned_activity_codes", assigned_codes)
            setattr(program, "available_activity_codes", available_codes)
            setattr(program, "uses_population_structure", len(population_rows_by_program_id.get(program.program_id, [])) > 0)

            enriched_population_rows = []
            for population_row in population_rows_by_program_id.get(program.program_id, []):
                group_obj = group_map.get(population_row.population_group_id)
                assigned_population_codes = sorted(
                    population_assignment_map.get(population_row.program_population_id, []),
                    key=lambda item: (item.code or "", item.description or ""),
                )
                assigned_population_ids = population_assignment_id_map.get(population_row.program_population_id, set())
                available_population_codes = [
                    code for code in proposal_activity_codes
                    if code.activity_code_id not in globally_assigned_activity_code_ids or code.activity_code_id in assigned_population_ids
                ]
                setattr(population_row, "population_group_obj", group_obj)
                setattr(population_row, "assigned_activity_codes", assigned_population_codes)
                setattr(population_row, "available_activity_codes", available_population_codes)
                enriched_population_rows.append(population_row)

            setattr(program, "program_populations", enriched_population_rows)

    return templates.TemplateResponse(
        "ui/admin/report_programs.html",
        {
            "request": request,
            "current_user": current_user,
            "msg": msg,
            "proposals": proposals,
            "selected_proposal_id": proposal_id,
            "selected_proposal": selected_proposal,
            "programs": programs,
            "population_groups": population_groups,
            "proposal_activity_codes": proposal_activity_codes,
        },
    )


@router.post("/report-programs/create")
def admin_create_report_program(
    proposal_id: int = Form(...),
    code: str = Form(...),
    name: str = Form(...),
    formal_name: str | None = Form(default=None),
    population_group_id: int = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/report-programs", "Error: La propuesta seleccionada no existe.")

    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    population_group = db.get(ProposalPopulationGroup, population_group_id)
    if not population_group or population_group.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Debe seleccionar una categorÃ­a poblacional vÃ¡lida para la propuesta.",
        )

    normalized_code = code.strip().upper()
    existing = db.execute(
        select(ProposalReportProgram).where(
            ProposalReportProgram.proposal_id == proposal_id,
            ProposalReportProgram.code == normalized_code,
        )
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Ya existe un programa con ese cÃ³digo en la propuesta seleccionada.",
        )

    program = ProposalReportProgram(
        proposal_id=proposal_id,
        code=normalized_code,
        name=name.strip(),
        formal_name=(formal_name or "").strip() or None,
        population_group_id=population_group_id,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(program)
    db.flush()

    existing_program_population = db.execute(
        select(ProposalReportProgramPopulation).where(
            ProposalReportProgramPopulation.program_id == program.program_id,
            ProposalReportProgramPopulation.population_group_id == population_group_id,
        )
    ).scalar_one_or_none()
    if not existing_program_population:
        db.add(
            ProposalReportProgramPopulation(
                program_id=program.program_id,
                population_group_id=population_group_id,
                sort_order=0,
                is_active=True,
            )
        )

    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Programa creado exitosamente con su poblaciÃ³n inicial sincronizada.",
    )


@router.post("/report-programs/{program_id}/edit")
def admin_edit_report_program(
    program_id: int,
    proposal_id: int = Form(...),
    code: str = Form(...),
    name: str = Form(...),
    formal_name: str | None = Form(default=None),
    population_group_id: int = Form(...),
    sort_order: int = Form(0),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    program = db.get(ProposalReportProgram, program_id)
    if not program:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Programa no encontrado.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    population_group = db.get(ProposalPopulationGroup, population_group_id)
    if not population_group or population_group.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Debe seleccionar una categorÃ­a poblacional vÃ¡lida para la propuesta.",
        )

    normalized_code = code.strip().upper()
    existing = db.execute(
        select(ProposalReportProgram).where(
            ProposalReportProgram.proposal_id == proposal_id,
            ProposalReportProgram.code == normalized_code,
            ProposalReportProgram.program_id != program_id,
        )
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Ya existe otro programa con ese cÃ³digo en la propuesta seleccionada.",
        )

    program.code = normalized_code
    program.name = name.strip()
    program.formal_name = (formal_name or "").strip() or None
    program.population_group_id = population_group_id
    program.sort_order = sort_order
    program.is_active = is_active == "on"
    db.add(program)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Programa actualizado exitosamente.",
    )


@router.post("/report-programs/{program_id}/delete")
def admin_delete_report_program(
    program_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    program = db.get(ProposalReportProgram, program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Programa no encontrado.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    related_activities = db.execute(
        select(ProposalReportProgramActivity).where(
            ProposalReportProgramActivity.program_id == program_id
        )
    ).scalars().all()
    activity_ids = [activity.program_activity_id for activity in related_activities]

    related_populations = db.execute(
        select(ProposalReportProgramPopulation).where(
            ProposalReportProgramPopulation.program_id == program_id
        )
    ).scalars().all()
    program_population_ids = [population.program_population_id for population in related_populations]

    linked_legacy_codes_count = 0
    if activity_ids:
        linked_legacy_codes_count = db.execute(
            select(func.count()).select_from(ProposalReportProgramActivityCode).where(
                ProposalReportProgramActivityCode.program_activity_id.in_(activity_ids)
            )
        ).scalar() or 0

    linked_population_codes_count = 0
    if program_population_ids:
        linked_population_codes_count = db.execute(
            select(func.count()).select_from(ProposalReportProgramPopulationActivityCode).where(
                ProposalReportProgramPopulationActivityCode.program_population_id.in_(program_population_ids)
            )
        ).scalar() or 0

    if linked_legacy_codes_count > 0 or linked_population_codes_count > 0:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: No se puede eliminar el programa porque todavÃ­a tiene actividades adjudicadas asociadas. RemuÃ©valas primero o inactÃ­velo.",
        )

    if program_population_ids:
        db.execute(
            delete(ProposalReportProgramPopulationActivityCode).where(
                ProposalReportProgramPopulationActivityCode.program_population_id.in_(program_population_ids)
            )
        )

    if activity_ids:
        db.execute(
            delete(ProposalReportProgramActivityCode).where(
                ProposalReportProgramActivityCode.program_activity_id.in_(activity_ids)
            )
        )

    db.execute(
        delete(ProposalReportProgramPopulation).where(
            ProposalReportProgramPopulation.program_id == program_id
        )
    )

    db.execute(
        delete(ProposalReportProgramActivity).where(
            ProposalReportProgramActivity.program_id == program_id
        )
    )

    db.execute(
        delete(ProposalReportProgram).where(ProposalReportProgram.program_id == program_id)
    )
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Programa eliminado exitosamente.",
    )


@router.post("/report-programs/{program_id}/activities/create")
def admin_create_report_program_activity(
    program_id: int,
    proposal_id: int = Form(...),
    code: str = Form(...),
    label: str = Form(...),
    age_min: int | None = Form(default=None),
    age_max: int | None = Form(default=None),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    program = db.get(ProposalReportProgram, program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Programa no encontrado para crear actividad.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    normalized_code = code.strip().upper()
    if not normalized_code:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El cÃ³digo de la actividad programÃ¡tica es requerido.",
        )

    existing = db.execute(
        select(ProposalReportProgramActivity).where(
            ProposalReportProgramActivity.program_id == program_id,
            ProposalReportProgramActivity.code == normalized_code,
        )
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Ya existe una actividad con ese cÃ³digo dentro del programa seleccionado.",
        )

    activity = ProposalReportProgramActivity(
        program_id=program_id,
        code=normalized_code,
        label=label.strip(),
        age_min=age_min,
        age_max=age_max,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(activity)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Actividad programÃ¡tica creada exitosamente.",
    )


@router.post("/report-programs/activities/{program_activity_id}/edit")
def admin_edit_report_program_activity(
    program_activity_id: int,
    proposal_id: int = Form(...),
    code: str = Form(...),
    label: str = Form(...),
    age_min: int | None = Form(default=None),
    age_max: int | None = Form(default=None),
    sort_order: int = Form(0),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    activity = db.get(ProposalReportProgramActivity, program_activity_id)
    if not activity:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Actividad programÃ¡tica no encontrada.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    program = db.get(ProposalReportProgram, activity.program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El programa asociado a la actividad no es vÃ¡lido para esta propuesta.",
        )

    normalized_code = code.strip().upper()
    if not normalized_code:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El cÃ³digo de la actividad programÃ¡tica es requerido.",
        )

    existing = db.execute(
        select(ProposalReportProgramActivity).where(
            ProposalReportProgramActivity.program_id == activity.program_id,
            ProposalReportProgramActivity.code == normalized_code,
            ProposalReportProgramActivity.program_activity_id != program_activity_id,
        )
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Ya existe otra actividad con ese cÃ³digo dentro del programa seleccionado.",
        )

    activity.code = normalized_code
    activity.label = label.strip()
    activity.age_min = age_min
    activity.age_max = age_max
    activity.sort_order = sort_order
    activity.is_active = is_active == "on"
    db.add(activity)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Actividad programÃ¡tica actualizada exitosamente.",
    )


@router.post("/report-programs/activities/{program_activity_id}/delete")
def admin_delete_report_program_activity(
    program_activity_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    activity = db.get(ProposalReportProgramActivity, program_activity_id)
    if not activity:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Actividad programÃ¡tica no encontrada.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    program = db.get(ProposalReportProgram, activity.program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El programa asociado a la actividad no es vÃ¡lido para esta propuesta.",
        )

    linked_codes_count = db.execute(
        select(func.count()).select_from(ProposalReportProgramActivityCode).where(
            ProposalReportProgramActivityCode.program_activity_id == program_activity_id
        )
    ).scalar()
    if linked_codes_count and linked_codes_count > 0:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: No se puede eliminar la actividad programÃ¡tica porque tiene cÃ³digos de actividad asociados. RemuÃ©valos primero o inactÃ­vela.",
        )

    db.delete(activity)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Actividad programÃ¡tica eliminada exitosamente.",
    )


@router.post("/report-programs/activities/{program_activity_id}/activity-codes/add")
def admin_add_activity_code_to_report_program_activity(
    program_activity_id: int,
    proposal_id: int = Form(...),
    activity_code_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    activity = db.get(ProposalReportProgramActivity, program_activity_id)
    if not activity:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Actividad programÃ¡tica no encontrada.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    program = db.get(ProposalReportProgram, activity.program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El programa asociado a la actividad no es vÃ¡lido para esta propuesta.",
        )

    activity_code = db.get(ActivityCode, activity_code_id)
    if not activity_code or activity_code.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Debe seleccionar un cÃ³digo de actividad vÃ¡lido de la propuesta.",
        )

    proposal_program_ids = db.execute(
        select(ProposalReportProgram.program_id).where(
            ProposalReportProgram.proposal_id == proposal_id
        )
    ).scalars().all()

    proposal_program_activity_ids = []
    if proposal_program_ids:
        proposal_program_activity_ids = db.execute(
            select(ProposalReportProgramActivity.program_activity_id).where(
                ProposalReportProgramActivity.program_id.in_(proposal_program_ids)
            )
        ).scalars().all()

    existing = None
    if proposal_program_activity_ids:
        existing = db.execute(
            select(ProposalReportProgramActivityCode).where(
                ProposalReportProgramActivityCode.program_activity_id.in_(proposal_program_activity_ids),
                ProposalReportProgramActivityCode.activity_code_id == activity_code_id,
            )
        ).scalar_one_or_none()
    if existing or _activity_code_is_assigned_anywhere_in_proposal(
        db,
        proposal_id,
        activity_code_id,
        exclude_program_id=program.program_id,
    ):
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Esa actividad ya estÃ¡ adjudicada a otro programa o poblaciÃ³n dentro de esta propuesta y no puede repetirse.",
        )

    db.add(
        ProposalReportProgramActivityCode(
            program_activity_id=program_activity_id,
            activity_code_id=activity_code_id,
        )
    )
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "CÃ³digo de actividad asociado exitosamente.",
    )


@router.post("/report-programs/activities/{program_activity_id}/activity-codes/{activity_code_id}/remove")
def admin_remove_activity_code_from_report_program_activity(
    program_activity_id: int,
    activity_code_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    activity = db.get(ProposalReportProgramActivity, program_activity_id)
    if not activity:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Actividad programÃ¡tica no encontrada.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    program = db.get(ProposalReportProgram, activity.program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El programa asociado a la actividad no es vÃ¡lido para esta propuesta.",
        )

    mapping = db.execute(
        select(ProposalReportProgramActivityCode).where(
            ProposalReportProgramActivityCode.program_activity_id == program_activity_id,
            ProposalReportProgramActivityCode.activity_code_id == activity_code_id,
        )
    ).scalar_one_or_none()
    if not mapping:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: La asociaciÃ³n solicitada no existe.",
        )

    db.delete(mapping)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "CÃ³digo de actividad removido exitosamente.",
    )


@router.post("/report-programs/{program_id}/populations/create")
def admin_create_report_program_population(
    program_id: int,
    proposal_id: int = Form(...),
    population_group_id: int = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    program = db.get(ProposalReportProgram, program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Programa no encontrado para agregar poblaciÃ³n.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    population_group = db.get(ProposalPopulationGroup, population_group_id)
    if not population_group or population_group.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Debe seleccionar una categorÃ­a poblacional vÃ¡lida.",
        )

    existing = db.execute(
        select(ProposalReportProgramPopulation).where(
            ProposalReportProgramPopulation.program_id == program_id,
            ProposalReportProgramPopulation.population_group_id == population_group_id,
        )
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Esa poblaciÃ³n ya estÃ¡ configurada dentro del programa.",
        )

    db.add(
        ProposalReportProgramPopulation(
            program_id=program_id,
            population_group_id=population_group_id,
            sort_order=sort_order,
            is_active=True,
        )
    )
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "PoblaciÃ³n agregada al programa exitosamente.",
    )


@router.post("/report-programs/populations/{program_population_id}/delete")
def admin_delete_report_program_population(
    program_population_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    program_population = db.get(ProposalReportProgramPopulation, program_population_id)
    if not program_population:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: RelaciÃ³n programa-poblaciÃ³n no encontrada.",
        )

    proposal = db.get(Proposal, proposal_id)
    redirect = _redirect_if_proposal_finalized(
        proposal,
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Error: La propuesta estÃ¡ finalizada y esta configuraciÃ³n es solo lectura.",
    )
    if redirect:
        return redirect

    program = db.get(ProposalReportProgram, program_population.program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El programa asociado no es vÃ¡lido para esta propuesta.",
        )

    linked_count = db.execute(
        select(func.count()).select_from(ProposalReportProgramPopulationActivityCode).where(
            ProposalReportProgramPopulationActivityCode.program_population_id == program_population_id
        )
    ).scalar() or 0
    if linked_count > 0:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: No se puede eliminar la poblaciÃ³n del programa porque todavÃ­a tiene actividades adjudicadas. RemuÃ©valas primero.",
        )

    db.delete(program_population)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "PoblaciÃ³n removida del programa exitosamente.",
    )


@router.post("/report-programs/populations/{program_population_id}/activity-codes/add")
def admin_add_activity_code_to_program_population(
    program_population_id: int,
    proposal_id: int = Form(...),
    activity_code_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    program_population = db.get(ProposalReportProgramPopulation, program_population_id)
    if not program_population:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: ConfiguraciÃ³n programa-poblaciÃ³n no encontrada.",
        )

    program = db.get(ProposalReportProgram, program_population.program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El programa asociado no es vÃ¡lido para esta propuesta.",
        )

    activity_code = db.get(ActivityCode, activity_code_id)
    if not activity_code or activity_code.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Debe seleccionar un cÃ³digo de actividad vÃ¡lido de la propuesta.",
        )

    existing_local = db.execute(
        select(ProposalReportProgramPopulationActivityCode).where(
            ProposalReportProgramPopulationActivityCode.program_population_id == program_population_id,
            ProposalReportProgramPopulationActivityCode.activity_code_id == activity_code_id,
        )
    ).scalar_one_or_none()
    if existing_local or _activity_code_is_assigned_anywhere_in_proposal(
        db,
        proposal_id,
        activity_code_id,
        exclude_program_population_id=program_population_id,
    ):
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Esa actividad ya estÃ¡ adjudicada a otro programa o poblaciÃ³n dentro de esta propuesta y no puede repetirse.",
        )

    db.add(
        ProposalReportProgramPopulationActivityCode(
            program_population_id=program_population_id,
            activity_code_id=activity_code_id,
        )
    )
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "CÃ³digo de actividad asociado a la poblaciÃ³n del programa exitosamente.",
    )


@router.post("/report-programs/populations/{program_population_id}/activity-codes/{activity_code_id}/remove")
def admin_remove_activity_code_from_program_population(
    program_population_id: int,
    activity_code_id: int,
    proposal_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    program_population = db.get(ProposalReportProgramPopulation, program_population_id)
    if not program_population:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: ConfiguraciÃ³n programa-poblaciÃ³n no encontrada.",
        )

    program = db.get(ProposalReportProgram, program_population.program_id)
    if not program or program.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: El programa asociado no es vÃ¡lido para esta propuesta.",
        )

    mapping = db.execute(
        select(ProposalReportProgramPopulationActivityCode).where(
            ProposalReportProgramPopulationActivityCode.program_population_id == program_population_id,
            ProposalReportProgramPopulationActivityCode.activity_code_id == activity_code_id,
        )
    ).scalar_one_or_none()
    if not mapping:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: La asociaciÃ³n solicitada no existe.",
        )

    db.delete(mapping)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "CÃ³digo de actividad removido de la poblaciÃ³n del programa exitosamente.",
    )


REPORT_TEMPLATE_REPORT_OPTIONS = [
    ("bonafide", "Bonafide"),
    ("no_duplicado", "No Duplicado"),
    ("duplicado", "Duplicado"),
    ("por_programa", "Por Programa"),
    ("hoja_cotejo", "Hoja de Cotejo"),
    ("vca", "VCA"),
    ("adm", "ADM"),
    ("visitas", "Visitas"),
    ("desercion", "Desercion Escolar"),
    ("embarazo", "Embarazo"),
    ("notas", "Notas"),
    ("consolidado_mensual_global", "Consolidado Mensual Global"),
    ("plantilla_duplicado", "Plantilla Duplicado"),
    ("hoja_cotejo_admin", "Hoja de Cotejo Admin"),
]


def _report_template_redirect(msg: str, proposal_id: int | None = None):
    url = "/ui/admin/report-templates"
    if proposal_id:
        url = f"{url}?proposal_id={proposal_id}"
    return _redirect_with_msg(url, msg)


@router.get("/report-templates", response_class=HTMLResponse)
def admin_report_templates(
    request: Request,
    proposal_id: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()
    templates_list = db.execute(
        select(ReportTemplate)
        .where(ReportTemplate.is_active == True)  # noqa: E712
        .order_by(ReportTemplate.report_key, ReportTemplate.name)
    ).scalars().all()
    versions = db.execute(
        select(ReportTemplateVersion, ReportTemplate)
        .join(ReportTemplate, ReportTemplate.report_template_id == ReportTemplateVersion.report_template_id)
        .where(
            ReportTemplateVersion.is_active == True,  # noqa: E712
            ReportTemplate.is_active == True,  # noqa: E712
        )
        .order_by(ReportTemplate.report_key, ReportTemplateVersion.version_number.desc())
    ).all()
    active_assignments = db.execute(
        select(ProposalReportTemplate, ReportTemplateVersion, ReportTemplate)
        .join(ReportTemplateVersion, ReportTemplateVersion.report_template_version_id == ProposalReportTemplate.report_template_version_id)
        .join(ReportTemplate, ReportTemplate.report_template_id == ReportTemplateVersion.report_template_id)
        .where(ProposalReportTemplate.is_active == True)  # noqa: E712
        .order_by(ProposalReportTemplate.proposal_id, ProposalReportTemplate.report_key)
    ).all()

    versions_by_report: dict[str, list[tuple[ReportTemplateVersion, ReportTemplate]]] = {
        report_key: [] for report_key, _ in REPORT_TEMPLATE_REPORT_OPTIONS
    }
    for version, template in versions:
        versions_by_report.setdefault(template.report_key, []).append((version, template))

    assignment_map: dict[tuple[int, str], dict] = {}
    version_assignment_counts: dict[int, int] = {}
    for assignment, version, template in active_assignments:
        assignment_map[(assignment.proposal_id, assignment.report_key)] = {
            "assignment": assignment,
            "version": version,
            "template": template,
        }
        version_assignment_counts[version.report_template_version_id] = version_assignment_counts.get(version.report_template_version_id, 0) + 1

    return templates.TemplateResponse(
        "ui/admin/report_templates.html",
        {
            "request": request,
            "current_user": current_user,
            "msg": msg,
            "proposals": proposals,
            "selected_proposal_id": proposal_id,
            "templates_list": templates_list,
            "versions": versions,
            "versions_by_report": versions_by_report,
            "assignment_map": assignment_map,
            "version_assignment_counts": version_assignment_counts,
            "report_options": REPORT_TEMPLATE_REPORT_OPTIONS,
        },
    )


@router.post("/report-templates/assign")
def admin_report_templates_assign(
    proposal_id: int = Form(...),
    report_key: str = Form(...),
    report_template_version_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _report_template_redirect("Error: Propuesta no encontrada.")

    valid_report_keys = {key for key, _ in REPORT_TEMPLATE_REPORT_OPTIONS}
    if report_key not in valid_report_keys:
        return _report_template_redirect("Error: Reporte no reconocido.", proposal_id)

    version = db.get(ReportTemplateVersion, report_template_version_id)
    if not version or not version.is_active:
        return _report_template_redirect("Error: Version de plantilla no encontrada o inactiva.", proposal_id)

    template = db.get(ReportTemplate, version.report_template_id)
    if not template or template.report_key != report_key:
        return _report_template_redirect("Error: La version seleccionada pertenece a otro reporte.", proposal_id)

    existing = db.execute(
        select(ProposalReportTemplate).where(
            ProposalReportTemplate.proposal_id == proposal_id,
            ProposalReportTemplate.report_key == report_key,
            ProposalReportTemplate.is_active == True,  # noqa: E712
        )
    ).scalars().all()
    for assignment in existing:
        assignment.is_active = False
        db.add(assignment)

    db.add(ProposalReportTemplate(
        proposal_id=proposal_id,
        report_key=report_key,
        report_template_version_id=report_template_version_id,
        is_active=True,
    ))
    db.commit()
    return _report_template_redirect("Plantilla asignada exitosamente.", proposal_id)


@router.post("/report-templates/unassign")
def admin_report_templates_unassign(
    proposal_id: int = Form(...),
    report_key: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.execute(
        select(ProposalReportTemplate).where(
            ProposalReportTemplate.proposal_id == proposal_id,
            ProposalReportTemplate.report_key == report_key,
            ProposalReportTemplate.is_active == True,  # noqa: E712
        )
    ).scalars().all()
    for assignment in existing:
        assignment.is_active = False
        db.add(assignment)
    db.commit()
    return _report_template_redirect("Asignacion removida; el reporte usara la plantilla base por defecto.", proposal_id)


def _next_report_template_version_number(db: Session, report_template_id: int) -> int:
    max_version = db.execute(
        select(func.max(ReportTemplateVersion.version_number)).where(
            ReportTemplateVersion.report_template_id == report_template_id,
        )
    ).scalar()
    return int(max_version or 0) + 1


REPORT_TEMPLATE_UPLOAD_ROOT = Path("storage/report_templates")


def _safe_docx_filename(value: str, fallback: str = "plantilla") -> str:
    base = Path(value or fallback).stem
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-_")
    return (base or fallback)[:80]


def _docx_paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pPr><w:pStyle w:val="{escape(style)}"/></w:pPr>' if style else ""
    return f"<w:p>{style_xml}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def _build_word_template_document(template: ReportTemplate, version: ReportTemplateVersion | None = None) -> bytes:
    config: dict = {}
    if version:
        try:
            config = json.loads(version.config_json or "{}")
        except json.JSONDecodeError:
            config = {}

    header = config.get("header", {}) if isinstance(config.get("header"), dict) else {}
    footer = config.get("footer", {}) if isinstance(config.get("footer"), dict) else {}
    columns = config.get("columns", []) if isinstance(config.get("columns"), list) else []
    layout = config.get("layout", {}) if isinstance(config.get("layout"), dict) else {}

    body_parts = [
        _docx_paragraph("Plantilla editable de reporte", "Title"),
        _docx_paragraph(f"Reporte: {template.name} ({template.report_key})"),
        _docx_paragraph(f"Versión base: {version.version_label if version else 'Nueva versión desde Word'}"),
        _docx_paragraph("Instrucciones", "Heading1"),
        _docx_paragraph("Edite este documento en Word y luego súbalo en la pantalla de Plantillas de Reporte como una nueva versión."),
        _docx_paragraph("No borre los marcadores entre llaves dobles si desea que el sistema pueda reemplazarlos en una etapa posterior."),
        _docx_paragraph("Marcadores disponibles", "Heading1"),
        _docx_paragraph("{{proposal_code}}, {{proposal_name}}, {{period_label}}, {{residential_name}}, {{municipality}}, {{generated_at}}"),
        _docx_paragraph("Encabezado", "Heading1"),
        _docx_paragraph(header.get("title") or header.get("line_1") or "{{report_title}}"),
        _docx_paragraph(header.get("subtitle") or header.get("line_2") or "{{report_subtitle}}"),
        _docx_paragraph(header.get("notes") or ""),
        _docx_paragraph("Tabla / columnas", "Heading1"),
    ]

    if columns:
        for col in columns:
            if isinstance(col, dict):
                body_parts.append(_docx_paragraph(f"{{{{{col.get('key', 'campo')}}}}} — {col.get('label', '')}"))
    else:
        body_parts.append(_docx_paragraph("{{table_rows}}"))

    body_parts.extend([
        _docx_paragraph("Footer / certificación", "Heading1"),
        _docx_paragraph(footer.get("text") or "{{footer_text}}"),
        _docx_paragraph("Notas técnicas actuales", "Heading1"),
        _docx_paragraph(f"Márgenes: {layout}" if layout else "Márgenes: usar configuración visual/base del reporte."),
    ])

    document_xml = "".join(body_parts)
    document_xml = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>{document_xml}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="720" w:right="720" w:bottom="720" w:left="720" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr></w:body>
</w:document>'''

    content_types = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>'''
    styles = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
</w:styles>'''

    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("[Content_Types].xml", content_types)
        docx.writestr("_rels/.rels", rels)
        docx.writestr("word/document.xml", document_xml)
        docx.writestr("word/styles.xml", styles)
    return output.getvalue()


@router.get("/report-templates/versions/download-word")
def admin_report_template_versions_download_word(
    report_template_id: int,
    report_template_version_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = db.get(ReportTemplate, report_template_id)
    if not template or not template.is_active:
        return _report_template_redirect("Error: Plantilla base no encontrada o inactiva.")

    version = None
    if report_template_version_id:
        version = db.get(ReportTemplateVersion, report_template_version_id)
        if not version or version.report_template_id != report_template_id:
            return _report_template_redirect("Error: Version de plantilla no encontrada.")

    filename = f"{_safe_docx_filename(template.report_key)}-{_safe_docx_filename(version.version_label if version else 'nueva-version')}.docx"
    return Response(
        content=_build_word_template_document(template, version),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/report-templates/versions/{report_template_version_id}/download-uploaded-file")
def admin_report_template_versions_download_uploaded_file(
    report_template_version_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    version = db.get(ReportTemplateVersion, report_template_version_id)
    if not version or not version.is_active:
        return _report_template_redirect("Error: Version de plantilla no encontrada o inactiva.")
    try:
        config = json.loads(version.config_json or "{}")
    except json.JSONDecodeError:
        config = {}
    file_path = Path(config.get("uploaded_file_path") or config.get("word_file_path") or "")
    if not file_path.exists() or file_path.suffix.lower() not in {".docx", ".pdf"}:
        return _report_template_redirect("Error: Esta version no tiene archivo PDF/Word subido.")
    media_type = "application/pdf" if file_path.suffix.lower() == ".pdf" else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=config.get("original_filename") or file_path.name,
    )


@router.post("/report-templates/versions/upload-file")
async def admin_report_template_versions_upload_file(
    report_template_id: int = Form(...),
    version_label: str = Form(...),
    template_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = db.get(ReportTemplate, report_template_id)
    if not template or not template.is_active:
        return _report_template_redirect("Error: Plantilla base no encontrada o inactiva.")

    normalized_label = (version_label or "").strip()
    if not normalized_label:
        return _report_template_redirect("Error: Debe indicar una etiqueta para la version.")

    original_filename = template_file.filename or ""
    extension = Path(original_filename).suffix.lower()
    if extension not in {".docx", ".pdf"}:
        return _report_template_redirect("Error: Solo se permite subir archivos .docx o .pdf.")

    content = await template_file.read()
    if extension == ".docx" and not content.startswith(b"PK"):
        return _report_template_redirect("Error: El archivo subido no parece ser un DOCX valido.")
    if extension == ".pdf" and not content.startswith(b"%PDF"):
        return _report_template_redirect("Error: El archivo subido no parece ser un PDF valido.")

    version_number = _next_report_template_version_number(db, report_template_id)
    upload_dir = REPORT_TEMPLATE_UPLOAD_ROOT / str(report_template_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"v{version_number:03d}-{_safe_docx_filename(normalized_label)}{extension}"
    file_path = upload_dir / filename
    file_path.write_bytes(content)

    config = {
        "source": "template_file_upload",
        "uploaded_file_path": str(file_path),
        "uploaded_file_type": extension.lstrip("."),
        "original_filename": original_filename,
        "preserve_current_format": True,
        "note": "Version creada desde archivo PDF/Word subido por admin. El archivo queda versionado y asignable por propuesta.",
    }
    db.add(ReportTemplateVersion(
        report_template_id=report_template_id,
        version_number=version_number,
        version_label=normalized_label,
        config_json=json.dumps(config, ensure_ascii=False),
        is_active=True,
    ))
    db.commit()
    return _report_template_redirect("Version PDF/Word subida exitosamente.")


@router.post("/report-templates/versions/{report_template_version_id}/delete")
def admin_report_template_versions_delete(
    report_template_version_id: int,
    proposal_id: int | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    version = db.get(ReportTemplateVersion, report_template_version_id)
    if not version or not version.is_active:
        return _report_template_redirect("Error: Version de plantilla no encontrada o ya inactiva.", proposal_id)

    active_assignment = db.execute(
        select(ProposalReportTemplate).where(
            ProposalReportTemplate.report_template_version_id == report_template_version_id,
            ProposalReportTemplate.is_active == True,  # noqa: E712
        )
    ).scalars().first()
    if active_assignment:
        return _report_template_redirect(
            "Error: No se puede eliminar una version asignada. Primero remueve la asignacion de la propuesta.",
            proposal_id,
        )

    version.is_active = False
    db.add(version)
    db.commit()
    return _report_template_redirect("Version inactivada exitosamente.", proposal_id)


@router.post("/report-templates/versions/create")
def admin_report_template_versions_create(
    report_template_id: int = Form(...),
    version_label: str = Form(...),
    config_json: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = db.get(ReportTemplate, report_template_id)
    if not template or not template.is_active:
        return _report_template_redirect("Error: Plantilla base no encontrada o inactiva.")

    normalized_label = (version_label or "").strip()
    if not normalized_label:
        return _report_template_redirect("Error: Debe indicar una etiqueta para la version.")

    try:
        parsed_config = json.loads(config_json or "{}")
    except json.JSONDecodeError as exc:
        return _report_template_redirect(f"Error: JSON invalido en configuracion ({exc.msg}).")

    db.add(ReportTemplateVersion(
        report_template_id=report_template_id,
        version_number=_next_report_template_version_number(db, report_template_id),
        version_label=normalized_label,
        config_json=json.dumps(parsed_config, ensure_ascii=False),
        is_active=True,
    ))
    db.commit()
    return _report_template_redirect("Version de plantilla creada exitosamente.")

@router.post("/report-templates/versions/create-visual")
def admin_report_template_versions_create_visual(
    report_template_id: int = Form(...),
    version_label: str = Form(...),
    header_image: str | None = Form(None),
    header_title: str | None = Form(None),
    header_subtitle: str | None = Form(None),
    header_notes: str | None = Form(None),
    footer_image: str | None = Form(None),
    footer_text: str | None = Form(None),
    signature_1_label: str | None = Form(None),
    signature_1_title: str | None = Form(None),
    signature_2_label: str | None = Form(None),
    signature_2_title: str | None = Form(None),
    date_label: str | None = Form(None),
    margin_top: str | None = Form(None),
    margin_right: str | None = Form(None),
    margin_bottom: str | None = Form(None),
    margin_left: str | None = Form(None),
    table_spacing: str | None = Form(None),
    rows_per_table: str | None = Form(None),
    columns_text: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = db.get(ReportTemplate, report_template_id)
    if not template or not template.is_active:
        return _report_template_redirect("Error: Plantilla base no encontrada o inactiva.")

    normalized_label = (version_label or "").strip()
    if not normalized_label:
        return _report_template_redirect("Error: Debe indicar una etiqueta para la version.")

    def clean(value: str | None) -> str:
        return (value or "").strip()

    columns = []
    for line in (columns_text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        if "|" in raw:
            key, label = raw.split("|", 1)
        else:
            key, label = raw, raw
        columns.append({"key": key.strip(), "label": label.strip()})

    visual_config = {
        "source": "visual_editor",
        "preserve_current_format": True,
        "header": {
            "image": clean(header_image),
            "title": clean(header_title),
            "subtitle": clean(header_subtitle),
            "notes": clean(header_notes),
        },
        "footer": {
            "image": clean(footer_image),
            "text": clean(footer_text),
        },
        "signatures": [
            {"label": clean(signature_1_label), "title": clean(signature_1_title)},
            {"label": clean(signature_2_label), "title": clean(signature_2_title)},
        ],
        "date": {
            "label": clean(date_label),
        },
        "layout": {
            "margin_top": clean(margin_top),
            "margin_right": clean(margin_right),
            "margin_bottom": clean(margin_bottom),
            "margin_left": clean(margin_left),
            "table_spacing": clean(table_spacing),
            "rows_per_table": clean(rows_per_table),
        },
        "columns": columns,
    }

    db.add(ReportTemplateVersion(
        report_template_id=report_template_id,
        version_number=_next_report_template_version_number(db, report_template_id),
        version_label=normalized_label,
        config_json=json.dumps(visual_config, ensure_ascii=False),
        is_active=True,
    ))
    db.commit()
    return _report_template_redirect("Version visual creada exitosamente.")

@router.post("/report-templates/versions/preview-visual", response_class=HTMLResponse)
def admin_report_template_versions_preview_visual(
    request: Request,
    report_template_id: int = Form(...),
    version_label: str = Form(""),
    header_image: str | None = Form(None),
    header_title: str | None = Form(None),
    header_subtitle: str | None = Form(None),
    header_notes: str | None = Form(None),
    footer_image: str | None = Form(None),
    footer_text: str | None = Form(None),
    signature_1_label: str | None = Form(None),
    signature_1_title: str | None = Form(None),
    signature_2_label: str | None = Form(None),
    signature_2_title: str | None = Form(None),
    date_label: str | None = Form(None),
    margin_top: str | None = Form(None),
    margin_right: str | None = Form(None),
    margin_bottom: str | None = Form(None),
    margin_left: str | None = Form(None),
    table_spacing: str | None = Form(None),
    rows_per_table: str | None = Form(None),
    columns_text: str | None = Form(None),
    preview_proposal_id: int | None = Form(None),
    preview_month: int | None = Form(None),
    preview_year: int | None = Form(None),
    preview_period_type: str = Form("monthly"),
    preview_start_date: str | None = Form(None),
    preview_end_date: str | None = Form(None),
    preview_authorized_name: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template = db.get(ReportTemplate, report_template_id)
    actual_context = None
    if template and template.report_key == "hoja_cotejo_admin" and preview_proposal_id:
        actual_context = build_hoja_cotejo_admin_context(
            db,
            month=preview_month,
            year=preview_year,
            period_type=preview_period_type,
            start_date=preview_start_date,
            end_date=preview_end_date,
            proposal_id=preview_proposal_id,
            authorized_name=preview_authorized_name,
            current_user=current_user,
        )

    columns = []
    for line in (columns_text or "").splitlines():
        raw = line.strip()
        if not raw:
            continue
        if "|" in raw:
            key, label = raw.split("|", 1)
        else:
            key, label = raw, raw
        columns.append({"key": key.strip(), "label": label.strip()})
    if not columns:
        if actual_context and template and template.report_key == "hoja_cotejo_admin":
            columns = [
                {"key": "activity", "label": "Actividad"},
                {"key": "activities_count", "label": "Realizadas"},
                {"key": "duplicados", "label": "Duplicados / Personas impactadas"},
                {"key": "met", "label": "Se logro el 100%"},
                {"key": "yes", "label": "Si"},
                {"key": "no", "label": "No"},
                {"key": "goal_summary", "label": "Frecuencia / Cumplimiento"},
                {"key": "monthly_percent", "label": "% Cumplimiento mensual"},
                {"key": "cumulative_ratio", "label": "Actividades logradas por periodo propuesta"},
                {"key": "percent", "label": "% Logros alcanzados periodo propuesta"},
            ]
        else:
            columns = [
                {"key": "actividad", "label": "Actividad"},
                {"key": "realizadas", "label": "Realizadas"},
                {"key": "duplicados", "label": "Duplicados"},
                {"key": "cumplimiento", "label": "Cumplimiento"},
            ]

    return templates.TemplateResponse(
        "ui/admin/report_template_preview.html",
        {
            "request": request,
            "current_user": current_user,
            "template": template,
            "report_template_id": report_template_id,
            "version_label": (version_label or "Vista previa sin guardar").strip(),
            "header_image": (header_image or "").strip(),
            "header_title": (header_title or (template.name if template else "Titulo del reporte")).strip(),
            "header_subtitle": (header_subtitle or "Subtitulo / periodo / propuesta").strip(),
            "header_notes": (header_notes or "").strip(),
            "footer_image": (footer_image or "").strip(),
            "footer_text": (footer_text or "Texto de certificacion o footer del reporte.").strip(),
            "signature_1_label": (signature_1_label or "Firma del Representante Autorizado").strip(),
            "signature_1_title": (signature_1_title or "Cargo / titulo").strip(),
            "signature_2_label": (signature_2_label or "Firma / Iniciales").strip(),
            "signature_2_title": (signature_2_title or "").strip(),
            "date_label": (date_label or "Fecha").strip(),
            "margin_top": (margin_top or "0.25in").strip(),
            "margin_right": (margin_right or "0.25in").strip(),
            "margin_bottom": (margin_bottom or "0.25in").strip(),
            "margin_left": (margin_left or "0.25in").strip(),
            "table_spacing": (table_spacing or "8px").strip(),
            "rows_per_table": (rows_per_table or "18").strip(),
            "columns_text": (columns_text or "").strip(),
            "columns": columns,
            "actual_context": actual_context,
            "actual_program_blocks": actual_context.get("program_blocks", []) if actual_context else [],
            "actual_period_title": actual_context.get("period_title", "") if actual_context else "",
            "actual_proposal": actual_context.get("proposal") if actual_context else None,
            "actual_residential_names": actual_context.get("residential_names", "") if actual_context else "",
        },
    )
