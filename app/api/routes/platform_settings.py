from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.platform_permissions import (
    MANAGE_PLATFORM_SETTINGS,
    require_platform_permission,
)
from app.core.security import hash_password
from app.core.session_security import SESSION_VERSION_KEY
from app.models.platform_permission import PlatformPermission
from app.models.platform_user_audit import PlatformUserAudit
from app.models.residential import Residential
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission
from app.models.user_residential import UserResidential


router = APIRouter(prefix="/platform/settings", tags=["platform-settings"])
templates = Jinja2Templates(directory="app/templates")
_CSRF_SESSION_KEY = "platform_settings_csrf_token"
_ALLOWED_EMAIL_DOMAIN = "csifpr.org"
_VALID_USER_ROLES = {"admin", "supervisor", "user"}
_VALID_USER_SECTIONS = {"general", "permissions", "residentials"}
_MIN_LOCAL_PASSWORD_LENGTH = 12


def _csrf_token(request: Request) -> str:
    token = request.session.get(_CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[_CSRF_SESSION_KEY] = token
    return token


def _validate_csrf_token(request: Request, submitted_token: str) -> None:
    expected_token = request.session.get(_CSRF_SESSION_KEY)
    if (
        not isinstance(expected_token, str)
        or not expected_token
        or not secrets.compare_digest(expected_token, submitted_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La solicitud no pudo validarse. Recargue la página e intente nuevamente.",
        )


def _settings_redirect(
    *,
    message: str | None = None,
    error: str | None = None,
    path: str = "/platform/settings",
    section: str | None = None,
) -> RedirectResponse:
    parameters: dict[str, str] = {}
    if section:
        parameters["section"] = section
    if message:
        parameters["msg"] = message
    if error:
        parameters["error"] = error
    suffix = f"?{urlencode(parameters)}" if parameters else ""
    return RedirectResponse(f"{path}{suffix}", status_code=status.HTTP_303_SEE_OTHER)


def _user_settings_redirect(
    user_id: int,
    *,
    section: str,
    message: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    return _settings_redirect(
        message=message,
        error=error,
        path=f"/platform/settings/users/{user_id}",
        section=section,
    )


def _normalized_authorized_email(email: str) -> str | None:
    normalized = email.strip().lower()
    local_part, separator, domain = normalized.rpartition("@")
    if (
        separator != "@"
        or not local_part
        or "@" in local_part
        or any(character.isspace() for character in normalized)
        or domain != _ALLOWED_EMAIL_DOMAIN
        or len(normalized) > 255
    ):
        return None
    return normalized


def _active_permission(db: Session, permission_key: str) -> PlatformPermission:
    permission = db.execute(
        select(PlatformPermission).where(
            PlatformPermission.key == permission_key,
            PlatformPermission.is_active == True,  # noqa: E712
        )
    ).scalar_one_or_none()
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Permiso activo no encontrado.",
        )
    return permission


@router.get("", response_class=HTMLResponse)
def platform_settings_index(
    request: Request,
    msg: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    permissions = db.execute(
        select(PlatformPermission).order_by(
            PlatformPermission.sort_order,
            PlatformPermission.key,
        )
    ).scalars().all()
    users = db.execute(select(User).order_by(User.username)).scalars().all()
    assignment_rows = db.execute(
        select(UserPlatformPermission.user_id, PlatformPermission.key)
        .join(
            PlatformPermission,
            PlatformPermission.permission_id == UserPlatformPermission.permission_id,
        )
    ).all()
    residentials = db.execute(
        select(Residential)
        .where(Residential.is_active == True)  # noqa: E712
        .order_by(Residential.code, Residential.name)
    ).scalars().all()
    residential_assignment_rows = db.execute(
        select(UserResidential.user_id, UserResidential.residential_id).where(
            UserResidential.is_active == True  # noqa: E712
        )
    ).all()

    permissions_by_user: dict[int, set[str]] = {user.user_id: set() for user in users}
    for user_id, permission_key in assignment_rows:
        permissions_by_user.setdefault(user_id, set()).add(permission_key)
    residential_ids_by_user: dict[int, set[int]] = {user.user_id: set() for user in users}
    for user_id, residential_id in residential_assignment_rows:
        residential_ids_by_user.setdefault(user_id, set()).add(residential_id)
    residentials_by_id = {
        residential.residential_id: residential for residential in residentials
    }

    return templates.TemplateResponse(
        request=request,
        name="platform_settings/index.html",
        context={
            "request": request,
            "current_user": current_user,
            "permissions": permissions,
            "users": users,
            "permissions_by_user": permissions_by_user,
            "residentials": residentials,
            "residentials_by_id": residentials_by_id,
            "residential_ids_by_user": residential_ids_by_user,
            "active_user_count": sum(1 for user in users if user.is_active),
            "manage_platform_settings_key": MANAGE_PLATFORM_SETTINGS,
            "csrf_token": _csrf_token(request),
            "message": msg,
            "error": error,
        },
    )


@router.get("/users/new", response_class=HTMLResponse)
def platform_new_user(
    request: Request,
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    residentials = db.execute(
        select(Residential)
        .where(Residential.is_active == True)  # noqa: E712
        .order_by(Residential.code, Residential.name)
    ).scalars().all()
    return templates.TemplateResponse(
        request=request,
        name="platform_settings/user_new.html",
        context={
            "request": request,
            "current_user": current_user,
            "residentials": residentials,
            "csrf_token": _csrf_token(request),
            "error": error,
            "minimum_local_password_length": _MIN_LOCAL_PASSWORD_LENGTH,
        },
    )


@router.post("/users/create")
def create_platform_user(
    request: Request,
    email: str = Form(...),
    password: str | None = Form(default=None),
    local_login_enabled: str | None = Form(default=None),
    role: str = Form("user"),
    residential_id: int | None = Form(default=None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    _validate_csrf_token(request, csrf_token)
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")

    redirect_path = "/platform/settings/users/new"
    normalized_email = _normalized_authorized_email(email)
    if normalized_email is None:
        return _settings_redirect(
            path=redirect_path,
            error="Debe usar un correo institucional @csifpr.org válido.",
        )
    if len(normalized_email) > 100:
        return _settings_redirect(
            path=redirect_path,
            error="El correo institucional excede el máximo de 100 caracteres permitido para el usuario.",
        )
    if role not in _VALID_USER_ROLES:
        return _settings_redirect(path=redirect_path, error="El rol seleccionado no es válido.")
    if role == "user" and residential_id is None:
        return _settings_redirect(
            path=redirect_path,
            error="Debe seleccionar un residencial para usuarios con rol user.",
        )

    selected_residential = (
        db.get(Residential, residential_id) if residential_id is not None else None
    )
    if residential_id is not None and (
        selected_residential is None or not selected_residential.is_active
    ):
        return _settings_redirect(
            path=redirect_path,
            error="El residencial seleccionado no está activo.",
        )

    existing = db.execute(
        select(User).where(
            or_(
                func.lower(func.ltrim(func.rtrim(User.email))) == normalized_email,
                func.lower(func.ltrim(func.rtrim(User.username))) == normalized_email,
            )
        )
    ).scalars().first()
    if existing is not None:
        return _settings_redirect(
            path=redirect_path,
            error="El correo institucional ya está asignado a otra cuenta.",
        )

    local_enabled = local_login_enabled == "on"
    normalized_password = (password or "").strip()
    if local_enabled and len(normalized_password) < _MIN_LOCAL_PASSWORD_LENGTH:
        return _settings_redirect(
            path=redirect_path,
            error=f"La contraseña local debe tener al menos {_MIN_LOCAL_PASSWORD_LENGTH} caracteres.",
        )
    if local_enabled and len(normalized_password.encode("utf-8")) > 72:
        return _settings_redirect(
            path=redirect_path,
            error="La contraseña local no puede exceder 72 bytes.",
        )

    password_to_hash = normalized_password if local_enabled else secrets.token_urlsafe(48)
    user = User(
        username=normalized_email,
        email=normalized_email,
        google_sub=None,
        password_hash=hash_password(password_to_hash),
        local_login_enabled=local_enabled,
        session_version=1,
        role=role,
        residential_id=residential_id,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
        if residential_id is not None:
            db.add(
                UserResidential(
                    user_id=user.user_id,
                    residential_id=residential_id,
                    assigned_by_user_id=current_user.user_id,
                    is_active=True,
                )
            )
        db.add(
            PlatformUserAudit(
                actor_user_id=current_user.user_id,
                target_user_id=user.user_id,
                action="user_created",
                details=(
                    f"role={role}; residential_id="
                    f"{residential_id if residential_id is not None else 'none'}; "
                    f"local_login={local_enabled}"
                ),
            )
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        return _settings_redirect(
            path=redirect_path,
            error="El correo institucional ya está asignado a otra cuenta.",
        )

    return _user_settings_redirect(
        user.user_id,
        section="general",
        message="Usuario creado correctamente. Configure sus permisos y residenciales.",
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
def platform_user_settings(
    request: Request,
    user_id: int,
    section: str = Query(default="general"),
    msg: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    target_user = db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    selected_section = section if section in _VALID_USER_SECTIONS else "general"

    permissions = db.execute(
        select(PlatformPermission).order_by(
            PlatformPermission.sort_order,
            PlatformPermission.key,
        )
    ).scalars().all()
    assigned_permission_keys = set(
        db.execute(
            select(PlatformPermission.key)
            .join(
                UserPlatformPermission,
                UserPlatformPermission.permission_id == PlatformPermission.permission_id,
            )
            .where(UserPlatformPermission.user_id == target_user.user_id)
        ).scalars().all()
    )
    residentials = db.execute(
        select(Residential)
        .where(Residential.is_active == True)  # noqa: E712
        .order_by(Residential.code, Residential.name)
    ).scalars().all()
    assigned_residential_ids = set(
        db.execute(
            select(UserResidential.residential_id)
            .join(
                Residential,
                Residential.residential_id == UserResidential.residential_id,
            )
            .where(
                UserResidential.user_id == target_user.user_id,
                UserResidential.is_active == True,  # noqa: E712
                Residential.is_active == True,  # noqa: E712
            )
        ).scalars().all()
    )

    return templates.TemplateResponse(
        request=request,
        name="platform_settings/user_detail.html",
        context={
            "request": request,
            "current_user": current_user,
            "target_user": target_user,
            "section": selected_section,
            "permissions": permissions,
            "assigned_permission_keys": assigned_permission_keys,
            "residentials": residentials,
            "assigned_residential_ids": assigned_residential_ids,
            "manage_platform_settings_key": MANAGE_PLATFORM_SETTINGS,
            "csrf_token": _csrf_token(request),
            "message": msg,
            "error": error,
        },
    )


@router.post("/users/{user_id}/general")
def update_user_general(
    request: Request,
    user_id: int,
    email: str = Form(...),
    role: str = Form(...),
    is_active: str | None = Form(default=None),
    local_login_enabled: str | None = Form(default=None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    _validate_csrf_token(request, csrf_token)
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    target_user = db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    normalized_email = _normalized_authorized_email(email)
    if normalized_email is None:
        return _user_settings_redirect(
            user_id,
            section="general",
            error="Debe usar un correo institucional @csifpr.org válido.",
        )
    if role not in _VALID_USER_ROLES:
        return _user_settings_redirect(
            user_id,
            section="general",
            error="El rol seleccionado no es válido.",
        )

    requested_active = is_active == "on"
    requested_local_login = local_login_enabled == "on"
    if target_user.user_id == current_user.user_id and not requested_active:
        return _user_settings_redirect(
            user_id,
            section="general",
            error="No puede desactivar su propia cuenta.",
        )
    if target_user.role == "admin" and (role != "admin" or not requested_active):
        return _user_settings_redirect(
            user_id,
            section="general",
            error="Las cuentas admin no pueden degradarse o desactivarse desde esta pantalla.",
        )

    current_email = (target_user.email or "").strip().lower()
    if (target_user.google_sub or target_user.google_linked_at) and normalized_email != current_email:
        return _user_settings_redirect(
            user_id,
            section="general",
            error="El correo de una cuenta vinculada con Google no puede cambiarse.",
        )
    if (
        target_user.user_id == current_user.user_id
        and not requested_local_login
        and not target_user.google_sub
    ):
        return _user_settings_redirect(
            user_id,
            section="general",
            error="Vincule Google antes de deshabilitar su propio acceso local.",
        )

    duplicate_email = db.execute(
        select(User).where(
            User.user_id != target_user.user_id,
            func.lower(func.ltrim(func.rtrim(User.email))) == normalized_email,
        )
    ).scalars().first()
    if duplicate_email is not None:
        return _user_settings_redirect(
            user_id,
            section="general",
            error="El correo institucional ya está asignado a otra cuenta.",
        )

    if role == "user":
        has_residential = db.execute(
            select(UserResidential.user_residential_id).where(
                UserResidential.user_id == target_user.user_id,
                UserResidential.is_active == True,  # noqa: E712
            )
        ).scalars().first()
        if has_residential is None:
            return _user_settings_redirect(
                user_id,
                section="general",
                error="Asigne al menos un residencial antes de usar el rol user.",
            )

    changed_fields: list[str] = []
    updates = {
        "email": normalized_email,
        "role": role,
        "is_active": requested_active,
        "local_login_enabled": requested_local_login,
    }
    for field_name, value in updates.items():
        if getattr(target_user, field_name) != value:
            setattr(target_user, field_name, value)
            changed_fields.append(field_name)

    if not changed_fields:
        return _user_settings_redirect(
            user_id,
            section="general",
            message="La cuenta no tenía cambios.",
        )

    target_user.session_version = User.session_version + 1
    db.add(
        PlatformUserAudit(
            actor_user_id=current_user.user_id,
            target_user_id=target_user.user_id,
            action="user_updated",
            details="changed=" + ",".join(changed_fields),
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _user_settings_redirect(
            user_id,
            section="general",
            error="No se pudo actualizar la cuenta.",
        )
    return _user_settings_redirect(
        user_id,
        section="general",
        message="Cuenta actualizada correctamente.",
    )


@router.post("/users/{user_id}/residentials")
def update_user_residentials(
    request: Request,
    user_id: int,
    residential_ids: list[int] = Form(default=[]),
    primary_residential_id: int | None = Form(default=None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    _validate_csrf_token(request, csrf_token)
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")
    target_user = db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")

    selected_ids = set(residential_ids)
    if target_user.role == "user" and not selected_ids:
        return _user_settings_redirect(
            user_id,
            section="residentials",
            error="Los usuarios con rol user requieren al menos un residencial.",
        )

    active_residential_ids: set[int] = set()
    if selected_ids:
        active_residential_ids = set(
            db.execute(
                select(Residential.residential_id).where(
                    Residential.residential_id.in_(selected_ids),
                    Residential.is_active == True,  # noqa: E712
                )
            ).scalars().all()
        )
    if active_residential_ids != selected_ids:
        return _user_settings_redirect(
            user_id,
            section="residentials",
            error="Uno o más residenciales seleccionados no están activos.",
        )

    if primary_residential_id is not None and primary_residential_id not in selected_ids:
        return _user_settings_redirect(
            user_id,
            section="residentials",
            error="El residencial primario debe estar entre los asignados.",
        )
    if primary_residential_id is None:
        if target_user.residential_id in selected_ids:
            primary_residential_id = target_user.residential_id
        elif selected_ids:
            primary_residential_id = min(selected_ids)

    assignments = db.execute(
        select(UserResidential).where(UserResidential.user_id == target_user.user_id)
    ).scalars().all()
    assignments_by_residential = {
        assignment.residential_id: assignment for assignment in assignments
    }
    changed = target_user.residential_id != primary_residential_id

    for residential_id, assignment in assignments_by_residential.items():
        should_be_active = residential_id in selected_ids
        if assignment.is_active != should_be_active:
            assignment.is_active = should_be_active
            if should_be_active:
                assignment.assigned_by_user_id = current_user.user_id
                assignment.assigned_at = func.sysutcdatetime()
            changed = True

    for residential_id in selected_ids - assignments_by_residential.keys():
        db.add(
            UserResidential(
                user_id=target_user.user_id,
                residential_id=residential_id,
                assigned_by_user_id=current_user.user_id,
                is_active=True,
            )
        )
        changed = True

    if not changed:
        return _user_settings_redirect(
            user_id,
            section="residentials",
            message="Las asignaciones no tenían cambios.",
        )

    next_session_version = int(target_user.session_version or 0) + 1
    db.add(
        PlatformUserAudit(
            actor_user_id=current_user.user_id,
            target_user_id=target_user.user_id,
            action="residential_assignments_updated",
            details=(
                "residential_ids="
                + ",".join(str(value) for value in sorted(selected_ids))
                + f"; primary_residential_id={primary_residential_id or 'none'}"
            ),
        )
    )
    try:
        db.execute(
            update(User)
            .where(User.user_id == target_user.user_id)
            .values(
                residential_id=primary_residential_id,
                session_version=next_session_version,
            )
            .execution_options(synchronize_session=False)
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        return _user_settings_redirect(
            user_id,
            section="residentials",
            error="No se pudieron actualizar las asignaciones residenciales.",
        )

    if target_user.user_id == current_user.user_id:
        request.session[SESSION_VERSION_KEY] = next_session_version
    return _user_settings_redirect(
        user_id,
        section="residentials",
        message="Asignaciones residenciales actualizadas.",
    )


@router.post("/users/{user_id}/permissions/{permission_key}/grant")
def grant_platform_permission(
    request: Request,
    user_id: int,
    permission_key: str,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    _validate_csrf_token(request, csrf_token)
    target_user = db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    permission = _active_permission(db, permission_key)
    if permission.key == MANAGE_PLATFORM_SETTINGS and current_user.role != "admin":
        return _user_settings_redirect(
            user_id,
            section="permissions",
            error="Solo un administrador puede otorgar este permiso.",
        )
    existing = db.execute(
        select(UserPlatformPermission).where(
            UserPlatformPermission.user_id == target_user.user_id,
            UserPlatformPermission.permission_id == permission.permission_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _user_settings_redirect(
            user_id,
            section="permissions",
            message="El permiso ya estaba asignado.",
        )

    db.add(
        UserPlatformPermission(
            user_id=target_user.user_id,
            permission_id=permission.permission_id,
            granted_by_user_id=current_user.user_id,
        )
    )
    db.add(
        PlatformUserAudit(
            actor_user_id=current_user.user_id,
            target_user_id=target_user.user_id,
            action="permission_granted",
            details=f"permission={permission.key}",
        )
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return _user_settings_redirect(
            user_id,
            section="permissions",
            message="El permiso ya estaba asignado.",
        )
    return _user_settings_redirect(
        user_id,
        section="permissions",
        message="Permiso otorgado correctamente.",
    )


@router.post("/users/{user_id}/permissions/{permission_key}/revoke")
def revoke_platform_permission(
    request: Request,
    user_id: int,
    permission_key: str,
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    _validate_csrf_token(request, csrf_token)
    target_user = db.get(User, user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Usuario no encontrado.")
    permission = _active_permission(db, permission_key)

    if permission.key == MANAGE_PLATFORM_SETTINGS and current_user.role != "admin":
        return _user_settings_redirect(
            user_id,
            section="permissions",
            error="Solo un administrador puede revocar este permiso.",
        )
    if (
        permission.key == MANAGE_PLATFORM_SETTINGS
        and target_user.role == "admin"
        and current_user.user_id != target_user.user_id
    ):
        return _user_settings_redirect(
            user_id,
            section="permissions",
            error="El acceso de gestión de una cuenta admin está protegido.",
        )
    if (
        current_user.user_id == target_user.user_id
        and permission.key == MANAGE_PLATFORM_SETTINGS
    ):
        return _user_settings_redirect(
            user_id,
            section="permissions",
            error="No puede quitarse su propio acceso a la configuración de plataforma.",
        )

    existing = db.execute(
        select(UserPlatformPermission).where(
            UserPlatformPermission.user_id == target_user.user_id,
            UserPlatformPermission.permission_id == permission.permission_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        return _user_settings_redirect(
            user_id,
            section="permissions",
            message="El permiso ya no estaba asignado.",
        )

    db.delete(existing)
    db.add(
        PlatformUserAudit(
            actor_user_id=current_user.user_id,
            target_user_id=target_user.user_id,
            action="permission_revoked",
            details=f"permission={permission.key}",
        )
    )
    db.commit()
    return _user_settings_redirect(
        user_id,
        section="permissions",
        message="Permiso revocado correctamente.",
    )
