from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
from urllib.parse import quote_plus
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import require_admin
from app.core.security import hash_password
from app.models.user import User
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.employee import Employee
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.vca_column import VCAColumn
from app.models.vca_column_activity_code import VCAColumnActivityCode
from app.models.visit_activity_mapping import VisitActivityMapping
from app.models.proposal_report_program import ProposalReportProgram
from app.models.proposal_population_group import ProposalPopulationGroup

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

VALID_USER_ROLES = {"admin", "supervisor", "user"}
DEFAULT_POPULATION_GROUP_OPTIONS = [
    ("ninos", "Niños", 0, 12, 1),
    ("jovenes", "Jóvenes", 13, 17, 2),
    ("adultos", "Adultos", 18, 59, 3),
    ("adulto_mayor", "Adulto Mayor", 60, None, 4),
]


def _redirect_with_msg(url: str, msg: str):
    separator = "&" if "?" in url else "?"
    return RedirectResponse(f"{url}{separator}msg={quote_plus(msg)}", status_code=303)


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
        return _redirect_with_msg("/ui/admin/users", "Error: El nombre de usuario ya está en uso.")

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
        return _redirect_with_msg("/ui/admin/residentials", "Error: El código ya existe.")

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
        return _redirect_with_msg("/ui/admin/residentials", "Error: El código ya está en uso.")

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
# Configura qué actividades por propuesta cuentan como visitas.
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
            f"/ui/admin/visits?proposal_id={proposal_id}&msg=Error: Esa actividad ya está marcada como visita.",
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
        return _redirect_with_msg(f"/ui/admin/visits?proposal_id={proposal_id}", "Error: Configuración no encontrada.")

    db.delete(mapping)
    db.commit()

    return _redirect_with_msg(f"/ui/admin/visits?proposal_id={proposal_id}", "Actividad de visita eliminada exitosamente.")


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

    column = VCAColumn(proposal_id=proposal_id, name=name.strip(), sort_order=sort_order)
    db.add(column)
    db.commit()
    return _redirect_with_msg(f"/ui/admin/vca?proposal_id={proposal_id}", "Columna VCA creada exitosamente.")


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
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: Esa actividad ya está asignada a una columna VCA.", status_code=303)

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
        return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Error: Asignación no encontrada.", status_code=303)
    db.delete(mapping)
    db.commit()
    return RedirectResponse(f"/ui/admin/vca?proposal_id={proposal_id}&msg=Asignación removida exitosamente.", status_code=303)


# ============================================================
# ACTIVITY CODE MANAGEMENT
# ============================================================

@router.get("/activity-codes", response_class=HTMLResponse)
def admin_activity_codes(
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    codes = db.execute(
        select(ActivityCode, Proposal.code.label("proposal_code"), Proposal.name.label("proposal_name"))
        .outerjoin(Proposal, ActivityCode.proposal_id == Proposal.proposal_id)
        .order_by(ActivityCode.code)
    ).all()
    proposals = db.execute(select(Proposal).order_by(Proposal.code)).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/activity_codes.html",
        {
            "request": request,
            "current_user": current_user,
            "codes": codes,
            "proposals": proposals,
            "msg": msg,
        },
    )


@router.post("/activity-codes/create")
def admin_create_activity_code(
    code: str = Form(...),
    description: str | None = Form(default=None),
    proposal_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.execute(
        select(ActivityCode).where(ActivityCode.code == code)
    ).scalar_one_or_none()
    if existing:
        return _redirect_with_msg("/ui/admin/activity-codes", "Error: El código ya existe.")

    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal:
            return _redirect_with_msg("/ui/admin/activity-codes", "Error: La propuesta seleccionada no existe.")

    ac = ActivityCode(
        code=code.strip(),
        description=description,
        proposal_id=proposal_id if proposal_id else None,
    )
    db.add(ac)
    db.commit()

    return _redirect_with_msg("/ui/admin/activity-codes", "Código de actividad creado exitosamente.")


@router.post("/activity-codes/{activity_code_id}/edit")
def admin_edit_activity_code(
    activity_code_id: int,
    code: str = Form(...),
    description: str | None = Form(default=None),
    proposal_id: int | None = Form(default=None),
    is_active: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    ac = db.get(ActivityCode, activity_code_id)
    if not ac:
        return RedirectResponse(
            "/ui/admin/activity-codes?msg=Error: Código no encontrado.",
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
            "/ui/admin/activity-codes?msg=Error: El código ya está en uso.",
            status_code=303,
        )

    if proposal_id:
        proposal = db.get(Proposal, proposal_id)
        if not proposal:
            return RedirectResponse(
                "/ui/admin/activity-codes?msg=Error: La propuesta seleccionada no existe.",
                status_code=303,
            )

    ac.code = code.strip()
    ac.description = description
    ac.proposal_id = proposal_id if proposal_id else None
    ac.is_active = is_active == "on"

    db.add(ac)
    db.commit()

    return RedirectResponse(
        "/ui/admin/activity-codes?msg=Código de actividad actualizado exitosamente.",
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
            "/ui/admin/activity-codes?msg=Error: No se puede eliminar, tiene sesiones asociadas. Desactívelo en su lugar.",
            status_code=303,
        )

    ac = db.get(ActivityCode, activity_code_id)
    if not ac:
        return RedirectResponse(
            "/ui/admin/activity-codes?msg=Error: Código no encontrado.",
            status_code=303,
        )

    db.delete(ac)
    db.commit()

    return RedirectResponse(
        "/ui/admin/activity-codes?msg=Código de actividad eliminado exitosamente.",
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
            return _redirect_with_msg("/ui/admin/employees", "Error: El código de empleado ya existe.")

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
                "/ui/admin/employees?msg=Error: El código de empleado ya está en uso.",
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
            "/ui/admin/employees?msg=Error: No se puede eliminar, tiene sesiones asociadas. Desactívelo en su lugar.",
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

    return templates.TemplateResponse(
        "ui/admin/proposals.html",
        {
            "request": request,
            "current_user": current_user,
            "proposals": proposals,
            "msg": msg,
        },
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
        return _redirect_with_msg("/ui/admin/proposals", "Error: El código de propuesta ya existe.")

    proposal = Proposal(code=code, name=name, description=description)
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
            "/ui/admin/proposals?msg=Error: El código de propuesta ya está en uso.",
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
            "Error: Ya existe una categoría poblacional con ese código en la propuesta.",
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
        "Categoría poblacional creada exitosamente.",
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
            "Error: Categoría poblacional no encontrada.",
        )

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
            "Error: Ya existe otra categoría poblacional con ese código en la propuesta.",
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
        "Categoría poblacional actualizada exitosamente.",
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

    if selected_proposal:
        population_groups = db.execute(
            select(ProposalPopulationGroup)
            .where(ProposalPopulationGroup.proposal_id == selected_proposal.proposal_id)
            .order_by(ProposalPopulationGroup.sort_order, ProposalPopulationGroup.code)
        ).scalars().all()
        group_map = {group.population_group_id: group for group in population_groups}

        programs = db.execute(
            select(ProposalReportProgram)
            .where(ProposalReportProgram.proposal_id == selected_proposal.proposal_id)
            .order_by(ProposalReportProgram.sort_order, ProposalReportProgram.code)
        ).scalars().all()
        for program in programs:
            setattr(program, "population_group_obj", group_map.get(program.population_group_id))

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
        },
    )


@router.post("/report-programs/create")
def admin_create_report_program(
    proposal_id: int = Form(...),
    code: str = Form(...),
    name: str = Form(...),
    population_group_id: int = Form(...),
    sort_order: int = Form(0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return _redirect_with_msg("/ui/admin/report-programs", "Error: La propuesta seleccionada no existe.")

    population_group = db.get(ProposalPopulationGroup, population_group_id)
    if not population_group or population_group.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Debe seleccionar una categoría poblacional válida para la propuesta.",
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
            "Error: Ya existe un programa con ese código en la propuesta seleccionada.",
        )

    program = ProposalReportProgram(
        proposal_id=proposal_id,
        code=normalized_code,
        name=name.strip(),
        population_group_id=population_group_id,
        sort_order=sort_order,
        is_active=True,
    )
    db.add(program)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Programa creado exitosamente.",
    )


@router.post("/report-programs/{program_id}/edit")
def admin_edit_report_program(
    program_id: int,
    proposal_id: int = Form(...),
    code: str = Form(...),
    name: str = Form(...),
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

    population_group = db.get(ProposalPopulationGroup, population_group_id)
    if not population_group or population_group.proposal_id != proposal_id:
        return _redirect_with_msg(
            f"/ui/admin/report-programs?proposal_id={proposal_id}",
            "Error: Debe seleccionar una categoría poblacional válida para la propuesta.",
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
            "Error: Ya existe otro programa con ese código en la propuesta seleccionada.",
        )

    program.code = normalized_code
    program.name = name.strip()
    program.population_group_id = population_group_id
    program.sort_order = sort_order
    program.is_active = is_active == "on"
    db.add(program)
    db.commit()

    return _redirect_with_msg(
        f"/ui/admin/report-programs?proposal_id={proposal_id}",
        "Programa actualizado exitosamente.",
    )
