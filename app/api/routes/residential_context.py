from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.platform_permissions import ACCESS_FARO, require_platform_permission
from app.core.residential_scope import (
    assigned_residentials,
    resolve_active_residential,
    set_active_residential,
)
from app.models.user import User


router = APIRouter(prefix="/ui/context/residential", tags=["residential-context"])
templates = Jinja2Templates(directory="app/templates")
_CSRF_SESSION_KEY = "residential_context_csrf_token"
_FARO_PERMISSION_DEPENDENCY = require_platform_permission(ACCESS_FARO)


def _safe_next_path(value: str | None) -> str:
    candidate = (value or "").strip()
    if not candidate.startswith("/ui") or candidate.startswith("//"):
        return "/ui"
    return candidate


def _csrf_token(request: Request) -> str:
    token = request.session.get(_CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[_CSRF_SESSION_KEY] = token
    return token


def _validate_csrf(request: Request, submitted_token: str) -> None:
    expected = request.session.get(_CSRF_SESSION_KEY)
    if (
        not isinstance(expected, str)
        or not expected
        or not secrets.compare_digest(expected, submitted_token)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solicitud inválida.")


@router.get("", response_class=HTMLResponse)
def residential_context_page(
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_FARO_PERMISSION_DEPENDENCY),
):
    next_path = _safe_next_path(next_path)
    active_residential, residentials = resolve_active_residential(request, db, current_user)
    if len(residentials) == 1:
        return RedirectResponse(next_path, status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request=request,
        name="ui/residential_context.html",
        context={
            "request": request,
            "current_user": current_user,
            "residentials": residentials,
            "active_residential": active_residential,
            "next_path": next_path,
            "csrf_token": _csrf_token(request),
        },
    )


@router.post("")
def select_residential_context(
    request: Request,
    residential_id: int = Form(...),
    next_path: str | None = Form(default=None, alias="next"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(_FARO_PERMISSION_DEPENDENCY),
):
    _validate_csrf(request, csrf_token)
    residential = next(
        (
            candidate
            for candidate in assigned_residentials(db, current_user)
            if candidate.residential_id == residential_id
        ),
        None,
    )
    if residential is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El residencial seleccionado no está asignado o activo.",
        )

    set_active_residential(request.session, residential)
    return RedirectResponse(_safe_next_path(next_path), status_code=status.HTTP_303_SEE_OTHER)
