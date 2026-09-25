"""Manage Community roles without changing a user's Faro role."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.platform_settings import _csrf_token, _validate_csrf_token
from app.core.community_access import COMMUNITY_ROLES
from app.core.config import settings
from app.core.platform_permissions import ACCESS_COMMUNITY, MANAGE_PLATFORM_SETTINGS, require_platform_permission
from app.models.community import CPProgram, CPUserAccess, CPUserProgram
from app.models.platform_permission import PlatformPermission
from app.models.platform_user_audit import PlatformUserAudit
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission

router = APIRouter(prefix="/platform/settings", tags=["community-settings"])
templates = Jinja2Templates(directory="app/templates")


def _check_enabled():
    if not settings.COMMUNITY_ENABLED:
        raise HTTPException(404, "Módulo no disponible.")


@router.get("/users/{user_id}/community")
def community_user_settings(request: Request, user_id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS))):
    _check_enabled()
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Usuario no encontrado.")
    access = db.get(CPUserAccess, user_id)
    assigned = set(db.scalars(select(CPUserProgram.program_id).where(CPUserProgram.user_id == user_id)).all())
    enabled = db.scalar(select(UserPlatformPermission.user_platform_permission_id).join(
        PlatformPermission, PlatformPermission.permission_id == UserPlatformPermission.permission_id
    ).where(UserPlatformPermission.user_id == user_id, PlatformPermission.key == ACCESS_COMMUNITY,
            PlatformPermission.is_active == True)) is not None  # noqa: E712
    return templates.TemplateResponse(request=request, name="community/settings.html", context={
        "request": request, "current_user": current_user, "target_user": target,
        "community_role": access.role if access else "user", "enabled": enabled,
        "programs": db.scalars(select(CPProgram).where(CPProgram.is_active == True).order_by(CPProgram.code)).all(),
        "assigned_ids": assigned, "csrf_token": _csrf_token(request),
        "saved": request.query_params.get("saved") == "1",
    })


@router.post("/users/{user_id}/community")
def save_community_user_settings(
    request: Request, user_id: int, role: str = Form(...), token: str = Form(...),
    program_ids: list[int] = Form(default=[]), enabled: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_platform_permission(MANAGE_PLATFORM_SETTINGS)),
):
    _check_enabled()
    _validate_csrf_token(request, token)
    if current_user.role != "admin":
        raise HTTPException(403, "Solo administración de plataforma puede modificar estas asignaciones.")
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "Usuario no encontrado.")
    if role not in COMMUNITY_ROLES:
        raise HTTPException(422, "Rol de Comunidad inválido.")
    requested = set(program_ids)
    available = set(db.scalars(select(CPProgram.program_id).where(
        CPProgram.is_active == True, CPProgram.program_id.in_(requested),  # noqa: E712
    )).all())
    if requested != available:
        raise HTTPException(422, "Hay programas inexistentes o inactivos en la selección.")
    if enabled == "on" and role == "user" and not requested:
        raise HTTPException(422, "Asigne al menos un programa para habilitar un User de Comunidad.")
    permission = db.scalar(select(PlatformPermission).where(PlatformPermission.key == ACCESS_COMMUNITY))
    if permission is None or not permission.is_active:
        raise HTTPException(409, "El permiso de Comunidad no está disponible.")
    access = db.get(CPUserAccess, user_id)
    if access is None:
        access = CPUserAccess(user_id=user_id, role=role)
        db.add(access)
    else:
        access.role = role
    db.execute(delete(CPUserProgram).where(CPUserProgram.user_id == user_id))
    for program_id in sorted(requested):
        db.add(CPUserProgram(user_id=user_id, program_id=program_id))
    assignment = db.scalar(select(UserPlatformPermission).where(
        UserPlatformPermission.user_id == user_id,
        UserPlatformPermission.permission_id == permission.permission_id,
    ))
    if enabled == "on" and assignment is None:
        db.add(UserPlatformPermission(user_id=user_id, permission_id=permission.permission_id,
                                      granted_by_user_id=current_user.user_id))
    elif enabled != "on" and assignment is not None:
        db.delete(assignment)
    db.add(PlatformUserAudit(actor_user_id=current_user.user_id, target_user_id=user_id,
                            action="community_access_updated",
                            details=f"role={role}; enabled={enabled == 'on'}; programs={','.join(map(str, sorted(requested)))}"))
    db.commit()
    return RedirectResponse(f"/platform/settings/users/{user_id}/community?saved=1", status_code=303)
