from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Form
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

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


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

    return templates.TemplateResponse(
        "ui/admin/users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
            "msg": msg,
        },
    )


@router.post("/users/create")
def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    # Check if username already exists
    existing = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            "/ui/admin/users?msg=Error: El usuario ya existe.",
            status_code=303,
        )

    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role if role in ("admin", "user") else "user",
    )
    db.add(user)
    db.commit()

    return RedirectResponse(
        "/ui/admin/users?msg=Usuario creado exitosamente.",
        status_code=303,
    )


@router.post("/users/{user_id}/edit")
def admin_edit_user(
    user_id: int,
    request: Request,
    username: str = Form(...),
    role: str = Form("user"),
    is_active: str | None = Form(default=None),
    new_password: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if not user:
        return RedirectResponse(
            "/ui/admin/users?msg=Error: Usuario no encontrado.",
            status_code=303,
        )

    # Check username uniqueness (excluding current user)
    existing = db.execute(
        select(User).where(User.username == username, User.user_id != user_id)
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            "/ui/admin/users?msg=Error: El nombre de usuario ya está en uso.",
            status_code=303,
        )

    user.username = username
    user.role = role if role in ("admin", "user") else "user"
    user.is_active = is_active == "on"

    if new_password and new_password.strip() and len(new_password.strip()) > 0:
        user.password_hash = hash_password(new_password.strip())

    db.add(user)
    db.commit()

    return RedirectResponse(
        "/ui/admin/users?msg=Usuario actualizado exitosamente.",
        status_code=303,
    )


@router.post("/users/{user_id}/delete")
def admin_delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if user_id == current_user.user_id:
        return RedirectResponse(
            "/ui/admin/users?msg=Error: No puedes eliminar tu propio usuario.",
            status_code=303,
        )

    user = db.get(User, user_id)
    if not user:
        return RedirectResponse(
            "/ui/admin/users?msg=Error: Usuario no encontrado.",
            status_code=303,
        )

    db.delete(user)
    db.commit()

    return RedirectResponse(
        "/ui/admin/users?msg=Usuario eliminado exitosamente.",
        status_code=303,
    )


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
        select(ActivityCode).order_by(ActivityCode.code)
    ).scalars().all()

    return templates.TemplateResponse(
        "ui/admin/activity_codes.html",
        {
            "request": request,
            "current_user": current_user,
            "codes": codes,
            "msg": msg,
        },
    )


@router.post("/activity-codes/create")
def admin_create_activity_code(
    code: str = Form(...),
    description: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    existing = db.execute(
        select(ActivityCode).where(ActivityCode.code == code)
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            "/ui/admin/activity-codes?msg=Error: El código ya existe.",
            status_code=303,
        )

    ac = ActivityCode(
        code=code,
        description=description,
    )
    db.add(ac)
    db.commit()

    return RedirectResponse(
        "/ui/admin/activity-codes?msg=Código de actividad creado exitosamente.",
        status_code=303,
    )


@router.post("/activity-codes/{activity_code_id}/edit")
def admin_edit_activity_code(
    activity_code_id: int,
    code: str = Form(...),
    description: str | None = Form(default=None),
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

    # Check code uniqueness
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

    ac.code = code
    ac.description = description
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
    # Check if it has associated sessions
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
            return RedirectResponse(
                "/ui/admin/employees?msg=Error: El código de empleado ya existe.",
                status_code=303,
            )

    emp = Employee(
        full_name=full_name,
        employee_code=employee_code if employee_code else None,
    )
    db.add(emp)
    db.commit()

    return RedirectResponse(
        "/ui/admin/employees?msg=Empleado creado exitosamente.",
        status_code=303,
    )


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

    # Check employee_code uniqueness
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
    # Check if it has associated sessions
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
