from __future__ import annotations

from datetime import date, datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete, func, or_
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

from app.core.auth import get_current_user, require_admin
from app.core.config import settings
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
    if user.role == "admin":
        return
    if p.created_by_user_id != user.user_id:
        raise HTTPException(status_code=403)


def _check_session_access(s: ActivitySession, user: User):
    if user.role == "admin":
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
        stmt = stmt.where(
            or_(
                ActivityCode.proposal_id.is_(None),
                ActivityCode.proposal_id == proposal_id,
            )
        )

    stmt = stmt.order_by(ActivityCode.code)
    return db.execute(stmt).scalars().all()


def _load_catalog_options(db: Session, key: str):
    catalog_type = db.execute(
        select(CatalogType).where(CatalogType.key == key, CatalogType.is_active == True)  # noqa: E712
    ).scalar_one_or_none()
    if not catalog_type:
        return []

    return db.execute(
        select(CatalogOption)
        .where(
            CatalogOption.catalog_type_id == catalog_type.catalog_type_id,
            CatalogOption.is_active == True,  # noqa: E712
        )
        .order_by(CatalogOption.sort_order, CatalogOption.label)
    ).scalars().all()


def _participant_form_catalogs(db: Session):
    return {
        "composicion_familiar_options": _load_catalog_options(db, "composicion_familiar"),
        "grupo_familiar_options": _load_catalog_options(db, "grupo_familiar"),
        "fuente_ingreso_principal_options": _load_catalog_options(db, "fuente_ingreso_principal"),
        "rango_ingreso_options": _load_catalog_options(db, "rango_ingreso"),
        "estatus_options": _load_catalog_options(db, "estatus_participante"),
    }


# ============================================================
# HOME
# ============================================================

@router.get("/", response_class=HTMLResponse)
def ui_home(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "ui/home.html",
        {
            "request": request,
            "current_user": current_user,
            "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
            "years": list(range(date.today().year - 2, date.today().year + 3)),
        },
    )


# ============================================================
# NEW LIST
# ============================================================

@router.get("/new-list", response_class=HTMLResponse)
def new_list(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = select(Participant).order_by(
        Participant.apellido_paterno,
        Participant.nombre
    )

    if current_user.role != "admin":
        stmt = stmt.where(
            Participant.created_by_user_id == current_user.user_id
        )

    participants = db.execute(stmt).scalars().all()

    rows = [
        {"p": p, "age": _calc_age(p.fecha_nacimiento), "is_active": _is_participant_active(p)}
        for p in participants
    ]

    return templates.TemplateResponse(
        "ui/new_list.html",
        {
            "request": request,
            "rows": rows,
            "current_user": current_user,
            "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
            "years": list(range(date.today().year - 2, date.today().year + 3)),
        },
    )


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
    composicion_familiar: str | None = Form(default=None),
    grupo_familiar: str | None = Form(default=None),
    fuente_ingreso_principal: str | None = Form(default=None),
    rango_ingreso: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if settings.PHASE2_EXPEDIENTE_ENABLED:
        if exp_year is None:
            raise HTTPException(status_code=400, detail="Selecciona el año del expediente.")

        initials = (exp_employee_initials or "").strip().upper()
        if not initials or len(initials) < 2 or len(initials) > 10:
            raise HTTPException(status_code=400, detail="Las siglas del empleado son requeridas (2-10 caracteres).")

        seq4 = (exp_seq4 or "").strip()
        if not (len(seq4) == 4 and seq4.isdigit()):
            raise HTTPException(status_code=400, detail="Los 4 dígitos deben ser exactamente 4 números (ej. 0001).")

        used_seq = db.execute(
            select(Participant).where(
                Participant.created_by_user_id == current_user.user_id,
                Participant.exp_seq4 == seq4,
            )
        ).scalar_one_or_none()
        if used_seq:
            raise HTTPException(
                status_code=400,
                detail=f"El número {seq4} ya fue utilizado por usted anteriormente. Debe escoger otro.",
            )

        expediente_num = f"FE-{exp_year}-{initials}-{seq4}"
    else:
        expediente_num = (expediente_num or "").strip()
        if not expediente_num:
            raise HTTPException(status_code=400, detail="Número de expediente es requerido.")

    exists = db.execute(
        select(Participant).where(Participant.expediente_num == expediente_num)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Expediente ya existe.")

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

    return RedirectResponse("/ui/new-list", status_code=303)


@router.post("/new-list/{participant_id}/delete")
def delete_participant(
    participant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    db.execute(delete(Attendance).where(Attendance.participant_id == participant_id))
    db.execute(delete(Participant).where(Participant.participant_id == participant_id))
    db.commit()

    return RedirectResponse("/ui/new-list", status_code=303)


# ============================================================
# EDIT PARTICIPANT (FASE 1 + FASE 2)
# ============================================================

@router.get("/new-list/{participant_id}/edit", response_class=HTMLResponse)
def edit_participant_form(
    participant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = db.execute(
        select(Participant).where(Participant.participant_id == participant_id)
    ).scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="Participante no existe.")

    _check_participant_access(p, current_user)

    return templates.TemplateResponse(
        "ui/edit_participant.html",
        {
            "request": request,
            "p": p,
            "current_user": current_user,
            "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
            "years": list(range(date.today().year - 2, date.today().year + 3)),
        },
    )


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
            raise HTTPException(status_code=400, detail="Selecciona el año del expediente.")

        initials = (exp_employee_initials or "").strip().upper()
        if not initials or len(initials) < 2 or len(initials) > 10:
            raise HTTPException(status_code=400, detail="Las siglas del empleado son requeridas (2-10 caracteres).")

        seq4 = (exp_seq4 or "").strip()
        if not (len(seq4) == 4 and seq4.isdigit()):
            raise HTTPException(status_code=400, detail="Los 4 dígitos deben ser exactamente 4 números (ej. 0001).")

        used_seq = db.execute(
            select(Participant).where(
                Participant.created_by_user_id == p.created_by_user_id,
                Participant.exp_seq4 == seq4,
                Participant.participant_id != p.participant_id,
            )
        ).scalar_one_or_none()
        if used_seq:
            raise HTTPException(
                status_code=400,
                detail=f"El número {seq4} ya fue utilizado por este empleado anteriormente. Debe escoger otro.",
            )

        expediente_num_final = f"FE-{exp_year}-{initials}-{seq4}"
    else:
        expediente_num_final = (expediente_num or "").strip()
        if not expediente_num_final:
            raise HTTPException(status_code=400, detail="Número de expediente es requerido.")

    exists = db.execute(
        select(Participant).where(
            Participant.expediente_num == expediente_num_final,
            Participant.participant_id != p.participant_id,
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Expediente ya existe.")

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

    return RedirectResponse("/ui/new-list", status_code=303)


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
            ActivityCode.code,
            ActivityCode.description,
            Employee.employee_code,
            Employee.full_name,
            ActivitySession.hours,
            Proposal.code.label("proposal_code"),
            Proposal.name.label("proposal_name"),
        )
        .join(ActivityCode, ActivitySession.activity_code_id == ActivityCode.activity_code_id)
        .join(Employee, ActivitySession.employee_id == Employee.employee_id)
        .outerjoin(Proposal, ActivitySession.proposal_id == Proposal.proposal_id)
        .order_by(ActivitySession.session_date.desc(), ActivitySession.session_id.desc())
    )

    if current_user.role != "admin":
        stmt = stmt.where(ActivitySession.created_by_user_id == current_user.user_id)

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

    sessions = db.execute(stmt).all()

    activity_codes = _load_activity_codes_for_proposal(db, proposal_id_int, active_only=True)
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
        },
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
            raise HTTPException(status_code=400, detail="La propuesta seleccionada no existe.")

    activity_code = db.get(ActivityCode, activity_code_id)
    if not activity_code:
        raise HTTPException(status_code=400, detail="El código de actividad seleccionado no existe.")
    if not _activity_code_allowed_for_proposal(activity_code, proposal_id):
        raise HTTPException(status_code=400, detail="La actividad no pertenece a la propuesta seleccionada.")

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

    return RedirectResponse(f"/ui/listado/{s.session_id}", status_code=303)


# ============================================================
# LISTADO - OPEN SESSION (mark attendance)
# ============================================================

@router.get("/listado/{session_id}", response_class=HTMLResponse)
def open_session(
    session_id: int,
    request: Request,
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

    activity_codes = _load_activity_codes_for_proposal(db, s.proposal_id, active_only=True)
    employees = db.execute(
        select(Employee).where(Employee.is_active == True).order_by(Employee.full_name)  # noqa: E712
    ).scalars().all()
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()

    stmt = select(Participant).order_by(
        Participant.apellido_paterno,
        Participant.nombre,
    )
    if current_user.role != "admin":
        stmt = stmt.where(
            Participant.created_by_user_id == current_user.user_id
        )
    participants = db.execute(stmt).scalars().all()
    participant_status_map = {
        p.participant_id: _is_participant_active(p)
        for p in participants
    }

    att_stmt = select(Attendance.participant_id).where(
        Attendance.session_id == session_id,
        Attendance.attended == True,
    )
    attended_ids = set(db.execute(att_stmt).scalars().all())

    return templates.TemplateResponse(
        "ui/listado.html",
        {
            "request": request,
            "session": s,
            "activity_code": activity_code,
            "employee": employee,
            "proposal": proposal,
            "activity_codes": activity_codes,
            "employees": employees,
            "proposals": proposals,
            "participants": participants,
            "participant_status_map": participant_status_map,
            "attended_ids": attended_ids,
            "current_user": current_user,
            "phase2_expediente_enabled": settings.PHASE2_EXPEDIENTE_ENABLED,
            "years": list(range(date.today().year - 2, date.today().year + 3)),
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

    form = await request.form()
    present = [int(v) for v in form.getlist("present")]

    if present:
        participant_stmt = select(Participant).where(Participant.participant_id.in_(present))
        if current_user.role != "admin":
            participant_stmt = participant_stmt.where(Participant.created_by_user_id == current_user.user_id)
        selected_participants = db.execute(participant_stmt).scalars().all()
        selected_map = {p.participant_id: p for p in selected_participants}

        missing_ids = [pid for pid in present if pid not in selected_map]
        if missing_ids:
            raise HTTPException(status_code=403, detail="No tienes permiso para registrar asistencia para uno o más participantes.")

        inactive_ids = [pid for pid, participant in selected_map.items() if not _is_participant_active(participant)]
        if inactive_ids:
            raise HTTPException(status_code=400, detail="No se puede registrar asistencia para participantes inactivos.")

    db.execute(
        delete(Attendance).where(Attendance.session_id == session_id)
    )

    for pid in present:
        att = Attendance(
            participant_id=pid,
            session_id=session_id,
            attended=True,
            marked_by=current_user.username,
        )
        db.add(att)

    db.commit()

    return RedirectResponse(f"/ui/listado/{session_id}", status_code=303)


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

    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal:
            raise HTTPException(status_code=400, detail="La propuesta seleccionada no existe.")
        s.proposal_id = proposal.proposal_id
    else:
        s.proposal_id = None

    activity_code = db.get(ActivityCode, activity_code_id)
    if not activity_code:
        raise HTTPException(status_code=400, detail="El código de actividad seleccionado no existe.")
    if not _activity_code_allowed_for_proposal(activity_code, s.proposal_id):
        raise HTTPException(status_code=400, detail="La actividad no pertenece a la propuesta seleccionada.")

    s.session_date = _parse_date(session_date)
    s.activity_code_id = activity_code_id
    s.employee_id = employee_id
    s.hours = hours

    db.add(s)
    db.commit()

    return RedirectResponse(f"/ui/listado/{session_id}", status_code=303)


@router.post("/listado/{session_id}/delete")
def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = db.get(ActivitySession, session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    _check_session_access(s, current_user)

    db.execute(
        delete(Attendance).where(Attendance.session_id == session_id)
    )
    db.execute(
        delete(ActivitySession).where(ActivitySession.session_id == session_id)
    )

    db.commit()

    return RedirectResponse("/ui/listado", status_code=303)
