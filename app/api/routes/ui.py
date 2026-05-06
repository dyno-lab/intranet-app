from __future__ import annotations

import csv
import io
import unicodedata
from datetime import date, datetime
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete, func, or_, case
from math import ceil
from sqlalchemy.orm import Session

from app.models.participant import Participant
from app.models.activity_session import ActivitySession
from app.models.activity_code import ActivityCode
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.proposal import Proposal
from app.models.user import User
from app.models.catalog_type import CatalogType
from app.models.catalog_option import CatalogOption
from app.models.residential import Residential
from app.models.person import Person
from app.models.proposal_participant import ProposalParticipant

from app.core.auth import get_current_user, require_admin, is_admin_or_supervisor
from app.core.config import settings
from app.core.proposal_guard import (
    is_proposal_finalized,
    require_session_proposal_not_finalized,
)
from app.api.deps import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# HELPERS
# ============================================================

def _parse_date(value: str | None):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _calc_age(dob: date | None):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )


def _check_participant_access(p: Participant, user: User):
    if is_admin_or_supervisor(user):
        return
    if p.created_by_user_id != user.user_id:
        raise HTTPException(status_code=403)


def _check_session_access(s: ActivitySession, user: User):
    if is_admin_or_supervisor(user):
        return
    if s.created_by_user_id != user.user_id:
        raise HTTPException(status_code=403)


def _is_participant_active(participant: Participant) -> bool:
    return bool(getattr(participant, "is_active", False))


def _activity_code_allowed_for_proposal(activity_code: ActivityCode, proposal_id: int | None) -> bool:
    return activity_code.proposal_id is None or activity_code.proposal_id == proposal_id


def _load_activity_codes_for_proposal(db: Session, proposal_id: int | None, active_only: bool = True):
    stmt = select(ActivityCode)
    if active_only:
        stmt = stmt.where(ActivityCode.is_active == True)  # noqa: E712

    if proposal_id is None:
        stmt = stmt.where(ActivityCode.proposal_id.is_(None))
    else:
        stmt = stmt.where(ActivityCode.proposal_id == proposal_id)

    stmt = stmt.order_by(ActivityCode.code)
    return db.execute(stmt).scalars().all()


def _redirect_if_proposal_finalized(proposal: Proposal | None, redirect_url: str, message: str):
    if is_proposal_finalized(proposal):
        return _redirect_with_msg(redirect_url, message)
    return None


def _normalize_catalog_key(value: str | None) -> str:
    text = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "_".join(part for part in text.split("_") if part)


def _load_catalog_options(db: Session, key: str):
    normalized_key = _normalize_catalog_key(key)
    catalog_types = db.execute(
        select(CatalogType).where(CatalogType.is_active == True)  # noqa: E712
    ).scalars().all()

    matching_type_ids = [
        ct.catalog_type_id
        for ct in catalog_types
        if _normalize_catalog_key(ct.key) == normalized_key
    ]
    if not matching_type_ids:
        return []

    return db.execute(
        select(CatalogOption)
        .where(
            CatalogOption.catalog_type_id.in_(matching_type_ids),
            CatalogOption.is_active == True,  # noqa: E712
        )
        .order_by(CatalogOption.sort_order, CatalogOption.label)
    ).scalars().all()


def _participant_form_catalogs(db: Session):
    return {
        "escolaridad_participante_options": _load_catalog_options(db, "escolaridad_participante"),
        "composicion_familiar_options": _load_catalog_options(db, "composicion_familiar"),
        "grupo_familiar_options": _load_catalog_options(db, "grupo_familiar"),
        "fuente_ingreso_principal_options": _load_catalog_options(db, "fuente_ingreso_principal"),
        "rango_ingreso_options": _load_catalog_options(db, "rango_ingreso"),
        "estatus_options": _load_catalog_options(db, "estatus_participante"),
    }


ATTENDANCE_AGE_RANGE_OPTIONS = [
    {"value": "lt5", "label": "Menos de 5 años", "min": None, "max": 4},
    {"value": "6_7", "label": "6 – 7 años", "min": 6, "max": 7},
    {"value": "8_10", "label": "8 – 10 años", "min": 8, "max": 10},
    {"value": "11_15", "label": "11 – 15 años", "min": 11, "max": 15},
    {"value": "16_21", "label": "16 – 21 años", "min": 16, "max": 21},
    {"value": "22_59", "label": "22 – 59 años", "min": 22, "max": 59},
    {"value": "60_plus", "label": "60 años en adelante", "min": 60, "max": None},
]


def _load_session_proposal_participants(db: Session, session: ActivitySession, current_user: User):
    if not session.proposal_id:
        return []

    stmt = (
        select(ProposalParticipant, Person)
        .join(Person, Person.person_id == ProposalParticipant.person_id)
        .where(ProposalParticipant.proposal_id == session.proposal_id)
        .order_by(Person.apellido_paterno, Person.apellido_materno, Person.nombre)
    )

    if not is_admin_or_supervisor(current_user):
        stmt = stmt.where(ProposalParticipant.created_by_user_id == current_user.user_id)

    rows = db.execute(stmt).all()
    result = []
    for proposal_participant, person in rows:
        result.append({
            "proposal_participant": proposal_participant,
            "person": person,
            "is_active": bool(getattr(proposal_participant, "is_active", False)),
            "age": _calc_age(person.fecha_nacimiento),
        })
    return result


def _csv_response(filename: str, headers: list[str], rows: list[list[object]]):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    content = "\ufeff" + buffer.getvalue()

    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _redirect_with_msg(url: str, msg: str):
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}msg={msg}", status_code=303)


def _build_sessions_stmt(current_user: User):
    stmt = (
        select(
            ActivitySession.session_id,
            ActivitySession.session_date,
            ActivityCode.code,
            ActivityCode.description,
            Employee.employee_code,
            Employee.full_name,
            ActivitySession.hours,
            Proposal.code.label("proposal_code"),
            Proposal.name.label("proposal_name"),
            Proposal.status.label("proposal_status"),
            User.username.label("created_by_username"),
            Residential.name.label("created_by_residential"),
        )
        .join(ActivityCode, ActivitySession.activity_code_id == ActivityCode.activity_code_id)
        .join(Employee, ActivitySession.employee_id == Employee.employee_id)
        .outerjoin(Proposal, ActivitySession.proposal_id == Proposal.proposal_id)
        .outerjoin(User, ActivitySession.created_by_user_id == User.user_id)
        .outerjoin(Residential, User.residential_id == Residential.residential_id)
        .order_by(
            case((Proposal.code.is_(None), 1), else_=0),
            Proposal.code.asc(),
            ActivitySession.session_date.desc(),
            ActivitySession.session_id.desc(),
        )
    )

    if not is_admin_or_supervisor(current_user):
        stmt = stmt.where(ActivitySession.created_by_user_id == current_user.user_id)

    return stmt


def _apply_session_filters(stmt, fd, td, proposal_id_int, month_int, year_int):
    if fd:
        stmt = stmt.where(ActivitySession.session_date >= fd)
    if td:
        stmt = stmt.where(ActivitySession.session_date <= td)
    if proposal_id_int:
        stmt = stmt.where(ActivitySession.proposal_id == proposal_id_int)
    if month_int:
        stmt = stmt.where(func.month(ActivitySession.session_date) == month_int)
    if year_int:
        stmt = stmt.where(func.year(ActivitySession.session_date) == year_int)
    return stmt


def _paginate(total_items: int, page: int, per_page: int):
    safe_per_page = max(1, per_page)
    total_pages = max(1, ceil(total_items / safe_per_page)) if total_items else 1
    safe_page = min(max(1, page), total_pages)
    offset = (safe_page - 1) * safe_per_page
    return {
        "page": safe_page,
        "per_page": safe_per_page,
        "total_items": total_items,
        "total_pages": total_pages,
        "offset": offset,
        "has_prev": safe_page > 1,
        "has_next": safe_page < total_pages,
        "prev_page": safe_page - 1 if safe_page > 1 else None,
        "next_page": safe_page + 1 if safe_page < total_pages else None,
    }


# ============================================================
# HOME
# ============================================================

@router.get("/", response_class=HTMLResponse)
def ui_home(
    request: Request,
    msg: str | None = None,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "ui/home.html",
        {
            "request": request,
            "current_user": current_user,
            "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
            "years": list(range(date.today().year - 2, date.today().year + 3)),
            "msg": msg,
        },
    )


# ============================================================
# NEW LIST
# ============================================================

@router.get("/new-list", response_class=HTMLResponse)
def new_list(
    request: Request,
    page: int = 1,
    per_page: int = 25,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    base_stmt = select(Participant)

    if not is_admin_or_supervisor(current_user):
        base_stmt = base_stmt.where(
            Participant.created_by_user_id == current_user.user_id
        )

    total_items = db.execute(
        select(func.count()).select_from(base_stmt.subquery())
    ).scalar_one()
    pagination = _paginate(total_items=total_items, page=page, per_page=per_page)

    stmt = base_stmt.order_by(
        Participant.apellido_paterno,
        Participant.nombre
    ).offset(pagination["offset"]).limit(pagination["per_page"])

    participants = db.execute(stmt).scalars().all()

    rows = [
        {"p": p, "age": _calc_age(p.fecha_nacimiento), "is_active": _is_participant_active(p)}
        for p in participants
    ]

    context = {
        "request": request,
        "rows": rows,
        "current_user": current_user,
        "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
        "years": list(range(date.today().year - 2, date.today().year + 3)),
        "pagination": pagination,
        "msg": msg,
    }
    context.update(_participant_form_catalogs(db))

    return templates.TemplateResponse("ui/new_list.html", context)


@router.post("/new-list/create")
def create_participant(
    expediente_num: str | None = Form(default=None),
    exp_year: int | None = Form(default=None),
    exp_employee_initials: str | None = Form(default=None),
    exp_seq4: str | None = Form(default=None),
    nombre: str = Form(...),
    inicial: str | None = Form(default=None),
    apellido_paterno: str = Form(...),
    apellido_materno: str | None = Form(default=None),
    fecha_nacimiento: str | None = Form(default=None),
    genero: str | None = Form(default=None),
    edificio: str | None = Form(default=None),
    apart: str | None = Form(default=None),
    estatus: str | None = Form(default=None),
    vca: str | None = Form(default=None),
    primera_vez: str | None = Form(default=None),
    escolaridad_participante: str | None = Form(default=None),
    composicion_familiar: str | None = Form(default=None),
    grupo_familiar: str | None = Form(default=None),
    fuente_ingreso_principal: str | None = Form(default=None),
    rango_ingreso: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if settings.PHASE2_EXPEDIENTE_ENABLED:
        if exp_year is None:
            return _redirect_with_msg("/ui/new-list", "Error: Selecciona el año del expediente.")

        initials = (exp_employee_initials or "").strip().upper()
        if not initials or len(initials) < 2 or len(initials) > 10:
            return _redirect_with_msg("/ui/new-list", "Error: Las siglas del empleado son requeridas (2-10 caracteres).")

        seq4 = (exp_seq4 or "").strip()
        if not (len(seq4) == 4 and seq4.isdigit()):
            return _redirect_with_msg("/ui/new-list", "Error: Los 4 dígitos deben ser exactamente 4 números (ej. 0001).")

        used_seq = db.execute(
            select(Participant).where(
                Participant.created_by_user_id == current_user.user_id,
                Participant.exp_seq4 == seq4,
            )
        ).scalar_one_or_none()
        if used_seq:
            return _redirect_with_msg(
                "/ui/new-list",
                f"Error: El número {seq4} ya fue utilizado por usted anteriormente. Debe escoger otro.",
            )

        expediente_num = f"FE-{exp_year}-{initials}-{seq4}"
    else:
        expediente_num = (expediente_num or "").strip()
        if not expediente_num:
            return _redirect_with_msg("/ui/new-list", "Error: Número de expediente es requerido.")

    exists = db.execute(
        select(Participant).where(Participant.expediente_num == expediente_num)
    ).scalar_one_or_none()
    if exists:
        return _redirect_with_msg("/ui/new-list", "Error: El expediente ya existe.")

    normalized_estatus = (estatus or "").strip()
    participant_is_active = normalized_estatus.lower() in {"activo", "active"}

    p = Participant(
        expediente_num=expediente_num,
        nombre=nombre,
        inicial=inicial,
        apellido_paterno=apellido_paterno,
        apellido_materno=apellido_materno,
        fecha_nacimiento=_parse_date(fecha_nacimiento),
        genero=genero,
        edificio=edificio,
        apart=apart,
        estatus=normalized_estatus or None,
        vca=vca,
        primera_vez=primera_vez,
        escolaridad_participante=escolaridad_participante,
        composicion_familiar=composicion_familiar,
        grupo_familiar=grupo_familiar,
        fuente_ingreso_principal=fuente_ingreso_principal,
        rango_ingreso=rango_ingreso,
        is_active=participant_is_active,
        created_by_user_id=current_user.user_id,
    )

    if settings.PHASE2_EXPEDIENTE_ENABLED:
        p.exp_year = exp_year
        p.exp_employee_initials = initials
        p.exp_seq4 = seq4

    db.add(p)
    db.commit()

    return _redirect_with_msg("/ui/new-list", "Participante creado exitosamente.")


@router.post("/new-list/{participant_id}/delete")
def delete_participant(
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin_or_supervisor(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado.")

    db.execute(delete(Attendance).where(Attendance.participant_id == participant_id))
    db.execute(delete(Participant).where(Participant.participant_id == participant_id))
    db.commit()

    return _redirect_with_msg("/ui/new-list", "Participante eliminado exitosamente.")


@router.get("/new-list/export.csv")
def export_participants_csv(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Participant).order_by(
        Participant.apellido_paterno,
        Participant.apellido_materno,
        Participant.nombre,
    )

    if not is_admin_or_supervisor(current_user):
        stmt = stmt.where(Participant.created_by_user_id == current_user.user_id)

    participants = db.execute(stmt).scalars().all()

    rows = []
    for p in participants:
        rows.append([
            p.participant_id,
            p.expediente_num or "",
            p.nombre or "",
            p.inicial or "",
            p.apellido_paterno or "",
            p.apellido_materno or "",
            p.fecha_nacimiento.isoformat() if p.fecha_nacimiento else "",
            _calc_age(p.fecha_nacimiento) if p.fecha_nacimiento else "",
            p.genero or "",
            p.estatus or "",
            "Activo" if _is_participant_active(p) else "Inactivo",
            p.vca or "",
            p.primera_vez or "",
            p.escolaridad_participante or "",
            p.composicion_familiar or "",
            p.grupo_familiar or "",
            p.fuente_ingreso_principal or "",
            p.rango_ingreso or "",
            p.edificio or "",
            p.apart or "",
        ])

    return _csv_response(
        filename=f"participantes_{date.today().isoformat()}.csv",
        headers=[
            "participant_id",
            "expediente_num",
            "nombre",
            "inicial",
            "apellido_paterno",
            "apellido_materno",
            "fecha_nacimiento",
            "edad",
            "genero",
            "estatus",
            "estado",
            "vca",
            "primera_vez",
            "escolaridad_participante",
            "composicion_familiar",
            "grupo_familiar",
            "fuente_ingreso_principal",
            "rango_ingreso",
            "edificio",
            "apart",
        ],
        rows=rows,
    )


# ============================================================
# EDIT PARTICIPANT (FASE 1 + FASE 2)
# ============================================================

@router.get("/new-list/{participant_id}/edit", response_class=HTMLResponse)
def edit_participant_form(
    participant_id: int,
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.execute(
        select(Participant).where(Participant.participant_id == participant_id)
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Participante no existe.")

    _check_participant_access(p, current_user)

    context = {
        "request": request,
        "p": p,
        "current_user": current_user,
        "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
        "years": list(range(date.today().year - 2, date.today().year + 3)),
        "msg": msg,
    }
    context.update(_participant_form_catalogs(db))

    return templates.TemplateResponse("ui/edit_participant.html", context)


@router.post("/new-list/{participant_id}/edit")
def edit_participant_save(
    participant_id: int,
    expediente_num: str | None = Form(default=None),
    exp_year: int | None = Form(default=None),
    exp_employee_initials: str | None = Form(default=None),
    exp_seq4: str | None = Form(default=None),
    nombre: str = Form(...),
    inicial: str | None = Form(default=None),
    apellido_paterno: str = Form(...),
    apellido_materno: str | None = Form(default=None),
    fecha_nacimiento: str | None = Form(default=None),
    genero: str | None = Form(default=None),
    edificio: str | None = Form(default=None),
    apart: str | None = Form(default=None),
    estatus: str | None = Form(default=None),
    vca: str | None = Form(default=None),
    primera_vez: str | None = Form(default=None),
    escolaridad_participante: str | None = Form(default=None),
    composicion_familiar: str | None = Form(default=None),
    grupo_familiar: str | None = Form(default=None),
    fuente_ingreso_principal: str | None = Form(default=None),
    rango_ingreso: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.execute(
        select(Participant).where(Participant.participant_id == participant_id)
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Participante no existe.")

    _check_participant_access(p, current_user)

    if settings.PHASE2_EXPEDIENTE_ENABLED:
        if exp_year is None:
            return _redirect_with_msg(f"/ui/new-list/{participant_id}/edit", "Error: Selecciona el año del expediente.")

        initials = (exp_employee_initials or "").strip().upper()
        if not initials or len(initials) < 2 or len(initials) > 10:
            return _redirect_with_msg(f"/ui/new-list/{participant_id}/edit", "Error: Las siglas del empleado son requeridas (2-10 caracteres).")

        seq4 = (exp_seq4 or "").strip()
        if not (len(seq4) == 4 and seq4.isdigit()):
            return _redirect_with_msg(f"/ui/new-list/{participant_id}/edit", "Error: Los 4 dígitos deben ser exactamente 4 números (ej. 0001).")

        used_seq = db.execute(
            select(Participant).where(
                Participant.created_by_user_id == p.created_by_user_id,
                Participant.exp_seq4 == seq4,
                Participant.participant_id != p.participant_id,
            )
        ).scalar_one_or_none()
        if used_seq:
            return _redirect_with_msg(
                f"/ui/new-list/{participant_id}/edit",
                f"Error: El número {seq4} ya fue utilizado por este empleado anteriormente. Debe escoger otro.",
            )

        expediente_num_final = f"FE-{exp_year}-{initials}-{seq4}"
    else:
        expediente_num_final = (expediente_num or "").strip()
        if not expediente_num_final:
            return _redirect_with_msg(f"/ui/new-list/{participant_id}/edit", "Error: Número de expediente es requerido.")

    exists = db.execute(
        select(Participant).where(
            Participant.expediente_num == expediente_num_final,
            Participant.participant_id != p.participant_id,
        )
    ).scalar_one_or_none()
    if exists:
        return _redirect_with_msg(f"/ui/new-list/{participant_id}/edit", "Error: El expediente ya existe.")

    normalized_estatus = (estatus or "").strip()
    participant_is_active = normalized_estatus.lower() in {"activo", "active"}

    p.expediente_num = expediente_num_final
    p.nombre = nombre
    p.inicial = inicial
    p.apellido_paterno = apellido_paterno
    p.apellido_materno = apellido_materno
    p.fecha_nacimiento = _parse_date(fecha_nacimiento)
    p.genero = genero
    p.edificio = edificio
    p.apart = apart
    p.estatus = normalized_estatus or None
    p.is_active = participant_is_active
    p.vca = vca
    p.primera_vez = primera_vez
    p.escolaridad_participante = escolaridad_participante
    p.composicion_familiar = composicion_familiar
    p.grupo_familiar = grupo_familiar
    p.fuente_ingreso_principal = fuente_ingreso_principal
    p.rango_ingreso = rango_ingreso

    if settings.PHASE2_EXPEDIENTE_ENABLED:
        p.exp_year = exp_year
        p.exp_employee_initials = initials
        p.exp_seq4 = seq4

    db.add(p)
    db.commit()

    return _redirect_with_msg("/ui/new-list", "Participante actualizado exitosamente.")


# ============================================================
# LISTADO - SESIONES
# ============================================================

@router.get("/listado", response_class=HTMLResponse)
def listado_selector(
    request: Request,
    from_date: str | None = None,
    to_date: str | None = None,
    proposal_id: str | None = None,
    month: str | None = None,
    year: str | None = None,
    page: int = 1,
    per_page: int = 25,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fd = _parse_date(from_date) if from_date else None
    td = _parse_date(to_date) if to_date else None
    proposal_id_int = int(proposal_id) if proposal_id and proposal_id.strip() else None
    month_int = int(month) if month and month.strip() else None
    year_int = int(year) if year and year.strip() else None

    base_stmt = _build_sessions_stmt(current_user)
    base_stmt = _apply_session_filters(base_stmt, fd, td, proposal_id_int, month_int, year_int)

    total_items = db.execute(
        select(func.count()).select_from(base_stmt.order_by(None).subquery())
    ).scalar_one()
    pagination = _paginate(total_items=total_items, page=page, per_page=per_page)

    stmt = base_stmt.offset(pagination["offset"]).limit(pagination["per_page"])
    sessions = db.execute(stmt).all()

    activity_codes = db.execute(
        select(ActivityCode).where(ActivityCode.is_active == True).order_by(ActivityCode.code)  # noqa: E712
    ).scalars().all()
    employees = db.execute(
        select(Employee).where(Employee.is_active == True).order_by(Employee.full_name)  # noqa: E712
    ).scalars().all()
    proposals = db.execute(
        select(Proposal).order_by(Proposal.code)
    ).scalars().all()

    month_options = [
        (1, "Enero"),
        (2, "Febrero"),
        (3, "Marzo"),
        (4, "Abril"),
        (5, "Mayo"),
        (6, "Junio"),
        (7, "Julio"),
        (8, "Agosto"),
        (9, "Septiembre"),
        (10, "Octubre"),
        (11, "Noviembre"),
        (12, "Diciembre"),
    ]
    current_year = date.today().year
    filter_years = list(range(current_year - 2, current_year + 3))

    return templates.TemplateResponse(
        "ui/select_session.html",
        {
            "request": request,
            "sessions": sessions,
            "activity_codes": activity_codes,
            "employees": employees,
            "proposals": proposals,
            "selected_proposal_id": proposal_id_int,
            "selected_month": month_int,
            "selected_year": year_int,
            "month_options": month_options,
            "filter_years": filter_years,
            "from_date": fd,
            "to_date": td,
            "current_user": current_user,
            "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
            "years": list(range(date.today().year - 2, date.today().year + 3)),
            "pagination": pagination,
            "is_admin_or_supervisor_view": is_admin_or_supervisor(current_user),
            "msg": msg,
        },
    )


@router.get("/listado/export.csv")
def export_sessions_csv(
    from_date: str | None = None,
    to_date: str | None = None,
    proposal_id: str | None = None,
    month: str | None = None,
    year: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fd = _parse_date(from_date) if from_date else None
    td = _parse_date(to_date) if to_date else None
    proposal_id_int = int(proposal_id) if proposal_id and proposal_id.strip() else None
    month_int = int(month) if month and month.strip() else None
    year_int = int(year) if year and year.strip() else None

    stmt = _build_sessions_stmt(current_user)
    stmt = _apply_session_filters(stmt, fd, td, proposal_id_int, month_int, year_int)
    sessions = db.execute(stmt).all()

    rows = []
    for s in sessions:
        rows.append([
            s.session_id,
            s.session_date.isoformat() if s.session_date else "",
            s.proposal_code or "",
            s.proposal_name or "",
            s.code or "",
            s.description or "",
            s.employee_code or "",
            s.full_name or "",
            s.hours or "",
        ])

    return _csv_response(
        filename=f"sesiones_{date.today().isoformat()}.csv",
        headers=[
            "session_id",
            "fecha",
            "propuesta_codigo",
            "propuesta_nombre",
            "actividad_codigo",
            "actividad_descripcion",
            "empleado_codigo",
            "empleado_nombre",
            "horas",
        ],
        rows=rows,
    )


@router.get("/listado/export-attendance.csv")
def export_attendance_csv(
    from_date: str | None = None,
    to_date: str | None = None,
    proposal_id: str | None = None,
    month: str | None = None,
    year: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fd = _parse_date(from_date) if from_date else None
    td = _parse_date(to_date) if to_date else None
    proposal_id_int = int(proposal_id) if proposal_id and proposal_id.strip() else None
    month_int = int(month) if month and month.strip() else None
    year_int = int(year) if year and year.strip() else None

    stmt = (
        select(
            ActivitySession.session_id,
            ActivitySession.session_date,
            Proposal.code.label("proposal_code"),
            Proposal.name.label("proposal_name"),
            ActivityCode.code.label("activity_code"),
            ActivityCode.description.label("activity_description"),
            Employee.employee_code,
            Employee.full_name.label("employee_name"),
            Participant.participant_id,
            Participant.expediente_num,
            Participant.nombre,
            Participant.apellido_paterno,
            Participant.apellido_materno,
            Participant.genero,
            Participant.estatus,
            Attendance.attended,
        )
        .join(Attendance, Attendance.session_id == ActivitySession.session_id)
        .join(Participant, Participant.participant_id == Attendance.participant_id)
        .join(ActivityCode, ActivitySession.activity_code_id == ActivityCode.activity_code_id)
        .join(Employee, ActivitySession.employee_id == Employee.employee_id)
        .outerjoin(Proposal, ActivitySession.proposal_id == Proposal.proposal_id)
        .where(Attendance.attended == True)  # noqa: E712
        .order_by(
            ActivitySession.session_date.desc(),
            ActivitySession.session_id.desc(),
            Participant.apellido_paterno,
            Participant.nombre,
        )
    )

    if not is_admin_or_supervisor(current_user):
        stmt = stmt.where(ActivitySession.created_by_user_id == current_user.user_id)

    stmt = _apply_session_filters(stmt, fd, td, proposal_id_int, month_int, year_int)
    attendance_rows = db.execute(stmt).all()

    rows = []
    for row in attendance_rows:
        rows.append([
            row.session_id,
            row.session_date.isoformat() if row.session_date else "",
            row.proposal_code or "",
            row.proposal_name or "",
            row.activity_code or "",
            row.activity_description or "",
            row.employee_code or "",
            row.employee_name or "",
            row.participant_id,
            row.expediente_num or "",
            row.nombre or "",
            row.apellido_paterno or "",
            row.apellido_materno or "",
            row.genero or "",
            row.estatus or "",
            "Sí" if row.attended else "No",
        ])

    return _csv_response(
        filename=f"asistencias_{date.today().isoformat()}.csv",
        headers=[
            "session_id",
            "fecha",
            "propuesta_codigo",
            "propuesta_nombre",
            "actividad_codigo",
            "actividad_descripcion",
            "empleado_codigo",
            "empleado_nombre",
            "participant_id",
            "expediente_num",
            "nombre",
            "apellido_paterno",
            "apellido_materno",
            "genero",
            "estatus",
            "asistio",
        ],
        rows=rows,
    )


@router.post("/listado/create-session")
def create_session_ui(
    session_date: str = Form(...),
    activity_code_id: int = Form(...),
    employee_id: int = Form(...),
    proposal_id: int | None = Form(default=None),
    hours: float | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = None
    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal:
            return _redirect_with_msg("/ui/listado", "Error: La propuesta seleccionada no existe.")
        redirect = _redirect_if_proposal_finalized(
            proposal,
            "/ui/listado",
            "Error: La propuesta seleccionada está finalizada y no permite crear sesiones.",
        )
        if redirect:
            return redirect

    activity_code = db.get(ActivityCode, activity_code_id)
    if not activity_code:
        return _redirect_with_msg("/ui/listado", "Error: El código de actividad seleccionado no existe.")
    if not _activity_code_allowed_for_proposal(activity_code, proposal_id):
        return _redirect_with_msg("/ui/listado", "Error: La actividad no pertenece a la propuesta seleccionada.")

    s = ActivitySession(
        session_date=_parse_date(session_date),
        activity_code_id=activity_code_id,
        employee_id=employee_id,
        proposal_id=proposal.proposal_id if proposal else None,
        hours=hours,
        created_by_user_id=current_user.user_id,
    )

    db.add(s)
    db.commit()
    db.refresh(s)

    return _redirect_with_msg(f"/ui/listado/{s.session_id}", "Sesión creada exitosamente.")


# ============================================================
# LISTADO - OPEN SESSION (mark attendance)
# ============================================================

@router.get("/listado/{session_id}", response_class=HTMLResponse)
def open_session(
    session_id: int,
    request: Request,
    from_date: str | None = None,
    to_date: str | None = None,
    proposal_id: str | None = None,
    month: str | None = None,
    year: str | None = None,
    page: int | None = None,
    per_page: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    _check_session_access(s, current_user)

    activity_code = db.get(ActivityCode, s.activity_code_id)
    employee = db.get(Employee, s.employee_id)
    proposal = db.get(Proposal, s.proposal_id) if s.proposal_id else None
    proposal_is_finalized = is_proposal_finalized(proposal)

    activity_codes = _load_activity_codes_for_proposal(db, s.proposal_id, active_only=True)
    employees = db.execute(
        select(Employee).where(Employee.is_active == True).order_by(Employee.full_name)  # noqa: E712
    ).scalars().all()
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()

    proposal_participant_rows = _load_session_proposal_participants(db, s, current_user)

    att_stmt = select(Attendance.proposal_participant_id).where(
        Attendance.session_id == session_id,
        Attendance.attended == True,
        Attendance.proposal_participant_id.is_not(None),
    )
    attended_ids = set(db.execute(att_stmt).scalars().all())

    list_query_params = {
        "proposal_id": proposal_id or "",
        "month": month or "",
        "year": year or "",
        "from_date": from_date or "",
        "to_date": to_date or "",
        "page": page or "",
        "per_page": per_page or "",
    }
    list_query_string = urlencode({k: v for k, v in list_query_params.items() if v not in (None, "")})
    back_to_list_url = f"/ui/listado?{list_query_string}" if list_query_string else "/ui/listado"

    return templates.TemplateResponse(
        "ui/listado.html",
        {
            "request": request,
            "session": s,
            "activity_code": activity_code,
            "employee": employee,
            "proposal": proposal,
            "proposal_is_finalized": proposal_is_finalized,
            "activity_codes": activity_codes,
            "employees": employees,
            "proposals": proposals,
            "proposal_participant_rows": proposal_participant_rows,
            "attendance_age_range_options": ATTENDANCE_AGE_RANGE_OPTIONS,
            "attended_ids": attended_ids,
            "current_user": current_user,
            "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
            "years": list(range(date.today().year - 2, date.today().year + 3)),
            "msg": msg,
            "back_to_list_url": back_to_list_url,
        },
    )


@router.post("/listado/{session_id}")
async def save_attendance(
    session_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    _check_session_access(s, current_user)

    try:
        require_session_proposal_not_finalized(
            db,
            s,
            message="Error: La propuesta de esta sesión está finalizada y no permite modificar asistencias.",
        )
    except HTTPException as exc:
        return _redirect_with_msg(f"/ui/listado/{session_id}", str(exc.detail))

    if not s.proposal_id:
        return _redirect_with_msg(
            f"/ui/listado/{session_id}",
            "Error: Esta fase solo permite guardar asistencias nuevas usando participantes operativos de sesiones con propuesta.",
        )

    form = await request.form()
    present = [int(v) for v in form.getlist("present")]

    if present:
        pp_stmt = select(ProposalParticipant).where(
            ProposalParticipant.proposal_participant_id.in_(present)
        )
        if not is_admin_or_supervisor(current_user):
            pp_stmt = pp_stmt.where(ProposalParticipant.created_by_user_id == current_user.user_id)

        selected_participants = db.execute(pp_stmt).scalars().all()
        selected_map = {
            p.proposal_participant_id: p
            for p in selected_participants
        }

        missing_ids = [pid for pid in present if pid not in selected_map]
        if missing_ids:
            return _redirect_with_msg(
                f"/ui/listado/{session_id}",
                "Error: No tienes permiso para registrar asistencia para uno o más participantes operativos.",
            )

        invalid_proposal_ids = [
            pid for pid, proposal_participant in selected_map.items()
            if proposal_participant.proposal_id != s.proposal_id
        ]
        if invalid_proposal_ids:
            return _redirect_with_msg(
                f"/ui/listado/{session_id}",
                "Error: Uno o más participantes operativos no pertenecen a la propuesta de esta sesión.",
            )

        inactive_ids = [
            pid for pid, proposal_participant in selected_map.items()
            if not bool(getattr(proposal_participant, "is_active", False))
        ]
        if inactive_ids:
            return _redirect_with_msg(
                f"/ui/listado/{session_id}",
                "Error: No se puede registrar asistencia para participantes operativos inactivos.",
            )

    db.execute(
        delete(Attendance).where(Attendance.session_id == session_id)
    )

    legacy_participant_map: dict[int, int | None] = {}
    if present:
        person_rows = db.execute(
            select(ProposalParticipant.proposal_participant_id, Person.legacy_participant_id)
            .join(Person, Person.person_id == ProposalParticipant.person_id)
            .where(ProposalParticipant.proposal_participant_id.in_(present))
        ).all()
        legacy_participant_map = {
            proposal_participant_id: legacy_participant_id
            for proposal_participant_id, legacy_participant_id in person_rows
        }

    for proposal_participant_id in present:
        att = Attendance(
            participant_id=legacy_participant_map.get(proposal_participant_id),
            proposal_participant_id=proposal_participant_id,
            session_id=session_id,
            attended=True,
            marked_by=current_user.username,
        )
        db.add(att)

    db.commit()

    return _redirect_with_msg(f"/ui/listado/{session_id}", "Asistencia guardada exitosamente.")


@router.post("/listado/{session_id}/clear-attendance")
def clear_attendance(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    if not is_admin_or_supervisor(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado.")

    _check_session_access(s, current_user)

    try:
        require_session_proposal_not_finalized(
            db,
            s,
            message="Error: La propuesta de esta sesión está finalizada y no permite eliminar asistencias.",
        )
    except HTTPException as exc:
        return _redirect_with_msg(f"/ui/listado/{session_id}", str(exc.detail))

    db.execute(
        delete(Attendance).where(Attendance.session_id == session_id)
    )
    db.commit()

    return _redirect_with_msg(f"/ui/listado/{session_id}", "Asistencias eliminadas exitosamente.")


@router.post("/listado/{session_id}/edit")
def edit_session(
    session_id: int,
    session_date: str = Form(...),
    activity_code_id: int = Form(...),
    employee_id: int = Form(...),
    proposal_id: int | None = Form(default=None),
    hours: float | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    _check_session_access(s, current_user)

    try:
        require_session_proposal_not_finalized(
            db,
            s,
            message="Error: La propuesta de esta sesión está finalizada y no permite editar la sesión.",
        )
    except HTTPException as exc:
        return _redirect_with_msg(f"/ui/listado/{session_id}", str(exc.detail))

    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal:
            return _redirect_with_msg(f"/ui/listado/{session_id}", "Error: La propuesta seleccionada no existe.")
        redirect = _redirect_if_proposal_finalized(
            proposal,
            f"/ui/listado/{session_id}",
            "Error: La propuesta seleccionada está finalizada y no permite editar sesiones.",
        )
        if redirect:
            return redirect
        s.proposal_id = proposal.proposal_id
    else:
        s.proposal_id = None

    activity_code = db.get(ActivityCode, activity_code_id)
    if not activity_code:
        return _redirect_with_msg(f"/ui/listado/{session_id}", "Error: El código de actividad seleccionado no existe.")
    if not _activity_code_allowed_for_proposal(activity_code, s.proposal_id):
        return _redirect_with_msg(f"/ui/listado/{session_id}", "Error: La actividad no pertenece a la propuesta seleccionada.")

    s.session_date = _parse_date(session_date)
    s.activity_code_id = activity_code_id
    s.employee_id = employee_id
    s.hours = hours

    db.add(s)
    db.commit()

    return _redirect_with_msg(f"/ui/listado/{session_id}", "Sesión actualizada exitosamente.")


@router.post("/listado/{session_id}/delete")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not is_admin_or_supervisor(current_user):
        raise HTTPException(status_code=403, detail="Acceso denegado.")

    s = db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    _check_session_access(s, current_user)

    try:
        require_session_proposal_not_finalized(
            db,
            s,
            message="Error: La propuesta de esta sesión está finalizada y no permite eliminar la sesión.",
        )
    except HTTPException as exc:
        return _redirect_with_msg("/ui/listado", str(exc.detail))

    db.execute(
        delete(Attendance).where(Attendance.session_id == session_id)
    )
    db.execute(
        delete(ActivitySession).where(ActivitySession.session_id == session_id)
    )

    db.commit()

    return _redirect_with_msg("/ui/listado", "Sesión eliminada exitosamente.")
