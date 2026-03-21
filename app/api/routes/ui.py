from __future__ import annotations

from datetime import date, datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.participant import Participant
from app.models.activity_session import ActivitySession
from app.models.activity_code import ActivityCode
from app.models.employee import Employee
from app.models.attendance import Attendance
from app.models.user import User

from app.core.auth import get_current_user, require_admin
from app.core.config import settings

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


# ============================================================
# DB
# ============================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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
        {"p": p, "age": _calc_age(p.fecha_nacimiento)}
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
    # FASE 1 (estable): expediente_num manual
    expediente_num: str | None = Form(default=None),

    # FASE 2: FE-YYYY-XX-#### (generado)
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
    # ==========================
    # Determinar expediente_num
    # ==========================
    if settings.PHASE2_EXPEDIENTE_ENABLED:
        # Validaciones básicas
        if exp_year is None:
            raise HTTPException(status_code=400, detail="Selecciona el año del expediente.")

        initials = (exp_employee_initials or "").strip().upper()
        if not initials or len(initials) < 2 or len(initials) > 10:
            raise HTTPException(status_code=400, detail="Las siglas del empleado son requeridas (2-10 caracteres).")

        seq4 = (exp_seq4 or "").strip()
        if not (len(seq4) == 4 and seq4.isdigit()):
            raise HTTPException(status_code=400, detail="Los 4 dígitos deben ser exactamente 4 números (ej. 0001).")

        # Regla: seq4 es único por empleado (created_by_user_id), sin importar el año
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
        # FASE 1 (estable)
        expediente_num = (expediente_num or "").strip()
        if not expediente_num:
            raise HTTPException(status_code=400, detail="Número de expediente es requerido.")

    # Unicidad del expediente completo (siempre)
    exists = db.execute(
        select(Participant).where(Participant.expediente_num == expediente_num)
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Expediente ya existe.")

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
        estatus=estatus,

        # Campos extra “New List”
        vca=vca,
        primera_vez=primera_vez,
        composicion_familiar=composicion_familiar,
        grupo_familiar=grupo_familiar,
        fuente_ingreso_principal=fuente_ingreso_principal,
        rango_ingreso=rango_ingreso,

        # Ownership
        created_by_user_id=current_user.user_id,
    )

    # Guardar componentes del expediente (FASE 2)
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
# LISTADO - SESIONES
# ============================================================


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

    # FASE 1 (estable): expediente manual
    expediente_num: str | None = Form(default=None),

    # FASE 2: FE-YYYY-XX-####
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

    # ==========================
    # Determinar expediente_num
    # ==========================
    if settings.PHASE2_EXPEDIENTE_ENABLED:
        if exp_year is None:
            raise HTTPException(status_code=400, detail="Selecciona el año del expediente.")

        initials = (exp_employee_initials or "").strip().upper()
        if not initials or len(initials) < 2 or len(initials) > 10:
            raise HTTPException(status_code=400, detail="Las siglas del empleado son requeridas (2-10 caracteres).")

        seq4 = (exp_seq4 or "").strip()
        if not (len(seq4) == 4 and seq4.isdigit()):
            raise HTTPException(status_code=400, detail="Los 4 dígitos deben ser exactamente 4 números (ej. 0001).")

        # Unicidad por empleado (dueño del participante)
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

    # Unicidad del expediente completo
    exists = db.execute(
        select(Participant).where(
            Participant.expediente_num == expediente_num_final,
            Participant.participant_id != p.participant_id,
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="Expediente ya existe.")

    # Update fields
    p.expediente_num = expediente_num_final
    p.nombre = nombre
    p.inicial = inicial
    p.apellido_paterno = apellido_paterno
    p.apellido_materno = apellido_materno
    p.fecha_nacimiento = _parse_date(fecha_nacimiento)
    p.genero = genero
    p.edificio = edificio
    p.apart = apart
    p.estatus = estatus

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

@router.get("/listado", response_class=HTMLResponse)
def listado_selector(
    request: Request,
    from_date: str | None = None,
    to_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    fd = _parse_date(from_date) if from_date else None
    td = _parse_date(to_date) if to_date else None

    stmt = (
        select(
            ActivitySession.session_id,
            ActivitySession.session_date,
            ActivityCode.code,
            ActivityCode.description,
            Employee.employee_code,
            Employee.full_name,
            ActivitySession.hours,
        )
        .join(ActivityCode, ActivitySession.activity_code_id == ActivityCode.activity_code_id)
        .join(Employee, ActivitySession.employee_id == Employee.employee_id)
        .order_by(ActivitySession.session_date.desc())
    )

    if current_user.role != "admin":
        stmt = stmt.where(ActivitySession.created_by_user_id == current_user.user_id)

    if fd:
        stmt = stmt.where(ActivitySession.session_date >= fd)
    if td:
        stmt = stmt.where(ActivitySession.session_date <= td)

    sessions = db.execute(stmt).all()

    activity_codes = db.execute(select(ActivityCode)).scalars().all()
    employees = db.execute(select(Employee)).scalars().all()

    return templates.TemplateResponse(
        "ui/select_session.html",
        {
            "request": request,
            "sessions": sessions,
            "activity_codes": activity_codes,
            "employees": employees,
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
    hours: float | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = ActivitySession(
        session_date=_parse_date(session_date),
        activity_code_id=activity_code_id,
        employee_id=employee_id,
        hours=hours,
        created_by_user_id=current_user.user_id,
    )

    db.add(s)
    db.commit()
    db.refresh(s)

    return RedirectResponse(f"/ui/listado/{s.session_id}", status_code=303)