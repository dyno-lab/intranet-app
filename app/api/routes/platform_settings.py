from __future__ import annotations

import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.platform_permissions import (
    MANAGE_PLATFORM_SETTINGS,
    require_platform_permission,
)
from app.models.platform_permission import PlatformPermission
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission


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

    permissions_by_user: dict[int, set[str]] = {user.user_id: set() for user in users}
    for user_id, permission_key in assignment_rows:
        permissions_by_user.setdefault(user_id, set()).add(permission_key)

    return templates.TemplateResponse(
        request=request,
        name="platform_settings/index.html",
        context={
            "request": request,
            "current_user": current_user,
            "permissions": permissions,
            "users": users,
            "permissions_by_user": permissions_by_user,
            "manage_platform_settings_key": MANAGE_PLATFORM_SETTINGS,
            "csrf_token": _csrf_token(request),
            "message": msg,
            "error": error,
        },
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
    db.commit()
    return _settings_redirect(message="Permiso revocado correctamente.")
