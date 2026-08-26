from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.platform_permissions import (
    MANAGE_PLATFORM_SETTINGS,
    require_platform_permission,
)
from app.models.platform_permission import PlatformPermission
from app.models.platform_user_audit import PlatformUserAudit
from app.models.residential import Residential
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission
from app.models.user_residential import UserResidential


router = APIRouter(prefix="/platform/settings", tags=["platform-settings"])
templates = Jinja2Templates(directory="app/templates")
_CSRF_SESSION_KEY = "platform_settings_csrf_token"


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


def _settings_redirect(*, message: str | None = None, error: str | None = None) -> RedirectResponse:
    parameters: dict[str, str] = {}
    if message:
        parameters["msg"] = message
    if error:
        parameters["error"] = error
    suffix = f"?{urlencode(parameters)}" if parameters else ""
    return RedirectResponse(f"/platform/settings{suffix}", status_code=status.HTTP_303_SEE_OTHER)


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
            "residential_ids_by_user": residential_ids_by_user,
            "manage_platform_settings_key": MANAGE_PLATFORM_SETTINGS,
            "csrf_token": _csrf_token(request),
            "message": msg,
            "error": error,
        },
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
        return _settings_redirect(error="Los usuarios con rol user requieren al menos un residencial.")

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
        return _settings_redirect(error="Uno o más residenciales seleccionados no están activos.")

    if primary_residential_id is not None and primary_residential_id not in selected_ids:
        return _settings_redirect(error="El residencial primario debe estar entre los asignados.")
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
        return _settings_redirect(message="Las asignaciones no tenían cambios.")

    target_user.residential_id = primary_residential_id
    target_user.session_version = User.session_version + 1
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
        db.commit()
    except IntegrityError:
        db.rollback()
        return _settings_redirect(error="No se pudieron actualizar las asignaciones residenciales.")
    return _settings_redirect(message="Asignaciones residenciales actualizadas.")


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
        return _settings_redirect(error="Solo un administrador puede otorgar este permiso.")
    existing = db.execute(
        select(UserPlatformPermission).where(
            UserPlatformPermission.user_id == target_user.user_id,
            UserPlatformPermission.permission_id == permission.permission_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _settings_redirect(message="El permiso ya estaba asignado.")

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
        return _settings_redirect(message="El permiso ya estaba asignado.")
    return _settings_redirect(message="Permiso otorgado correctamente.")


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
        return _settings_redirect(error="Solo un administrador puede revocar este permiso.")
    if (
        permission.key == MANAGE_PLATFORM_SETTINGS
        and target_user.role == "admin"
        and current_user.user_id != target_user.user_id
    ):
        return _settings_redirect(
            error="El acceso de gestión de una cuenta admin está protegido.",
        )
    if (
        current_user.user_id == target_user.user_id
        and permission.key == MANAGE_PLATFORM_SETTINGS
    ):
        return _settings_redirect(
            error="No puede quitarse su propio acceso a la configuración de plataforma.",
        )

    existing = db.execute(
        select(UserPlatformPermission).where(
            UserPlatformPermission.user_id == target_user.user_id,
            UserPlatformPermission.permission_id == permission.permission_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        return _settings_redirect(message="El permiso ya no estaba asignado.")

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
    return _settings_redirect(message="Permiso revocado correctamente.")
