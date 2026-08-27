from __future__ import annotations

import secrets
from collections.abc import Mapping

import httpx
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from joserfc.errors import JoseError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.core.google_oauth import (
    GOOGLE_NONCE_SESSION_KEY,
    GoogleIdentityError,
    GoogleOAuthConfigurationError,
    clear_google_oauth_session,
    create_google_oauth_client,
    get_google_oauth_configuration,
    new_google_nonce,
    validate_google_identity,
)
from app.core.platform_permissions import (
    ACCESS_FARO,
    get_optional_current_user,
    user_has_platform_permission,
)
from app.core.residential_scope import (
    ACTIVE_RESIDENTIAL_SESSION_KEY,
    AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY,
    assigned_residentials,
    clear_active_residential,
    set_active_residential,
)
from app.core.security import verify_password
from app.core.session_security import establish_authenticated_session
from app.models.platform_user_audit import PlatformUserAudit
from app.models.residential import Residential
from app.models.user import User


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
_FARO_LOGIN_CSRF_SESSION_KEY = "faro_login_csrf_token"
_DEFAULT_FARO_NEXT_PATH = "/ui/new-list"


def _safe_faro_next_path(value: str | None) -> str:
    candidate = (value or "").strip()
    path = candidate.split("?", 1)[0].rstrip("/") or "/"
    if (
        not candidate
        or candidate.startswith("//")
        or "\\" in candidate
        or (path != "/ui" and not path.startswith("/ui/"))
        or path == "/ui/context/residential"
    ):
        return _DEFAULT_FARO_NEXT_PATH
    return candidate


def _faro_login_csrf_token(request: Request) -> str:
    token = request.session.get(_FARO_LOGIN_CSRF_SESSION_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_urlsafe(32)
        request.session[_FARO_LOGIN_CSRF_SESSION_KEY] = token
    return token


def _validate_faro_login_csrf(request: Request, submitted_token: str) -> None:
    expected_token = request.session.get(_FARO_LOGIN_CSRF_SESSION_KEY)
    if (
        not isinstance(expected_token, str)
        or not expected_token
        or not secrets.compare_digest(expected_token, submitted_token)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Solicitud inválida.")


def _login_context(
    request: Request,
    *,
    error: str | None = None,
    current_user: User | None = None,
    can_access_faro: bool = False,
    residentials: list[Residential] | None = None,
    next_path: str = _DEFAULT_FARO_NEXT_PATH,
) -> dict[str, object]:
    try:
        active_residential_id = int(request.session.get(ACTIVE_RESIDENTIAL_SESSION_KEY))
    except (TypeError, ValueError):
        active_residential_id = None
    return {
        "request": request,
        "error": error,
        "current_user": current_user,
        "can_access_faro": can_access_faro,
        "residentials": residentials or [],
        "active_residential_id": active_residential_id,
        "next_path": next_path,
        "csrf_token": _faro_login_csrf_token(request) if current_user and can_access_faro else None,
    }


def _authenticated_login_context(
    request: Request,
    db: Session,
    current_user: User,
    *,
    next_path: str,
) -> dict[str, object]:
    can_access_faro = user_has_platform_permission(db, current_user, ACCESS_FARO)
    residentials = []
    if can_access_faro and current_user.role not in {"admin", "supervisor"}:
        residentials = assigned_residentials(db, current_user)
    return _login_context(
        request,
        current_user=current_user,
        can_access_faro=can_access_faro,
        residentials=residentials,
        next_path=next_path,
    )


def _oauth_error_response(request: Request, status_code: int = 403):
    clear_google_oauth_session(request.session)
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context=_login_context(
            request,
            error="No se pudo completar el acceso con Google. Verifica tu cuenta institucional.",
        ),
        status_code=status_code,
    )


def _require_google_oauth_enabled():
    if not settings.GOOGLE_OAUTH_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    try:
        return get_google_oauth_configuration()
    except GoogleOAuthConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El acceso con Google no está disponible temporalmente.",
        ) from exc


@router.get("/login", response_class=HTMLResponse)
def login_page(
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    db: Session = Depends(get_db),
):
    safe_next_path = _safe_faro_next_path(next_path)
    current_user = get_optional_current_user(request, db)
    context = _login_context(request, next_path=safe_next_path)
    if current_user is not None:
        context = _authenticated_login_context(
            request,
            db,
            current_user,
            next_path=safe_next_path,
        )
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context=context,
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()

    if (
        not user
        or not user.is_active
        or not user.local_login_enabled
        or not verify_password(password, user.password_hash)
    ):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context=_login_context(request, error="Credenciales incorrectas"),
        )

    establish_authenticated_session(request.session, user)

    return RedirectResponse("/home", status_code=303)


@router.post("/login/faro")
def enter_faro(
    request: Request,
    residential_id: int | None = Form(default=None),
    next_path: str | None = Form(default=None, alias="next"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
):
    _validate_faro_login_csrf(request, csrf_token)
    current_user = get_optional_current_user(request, db)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/home"},
        )
    if not user_has_platform_permission(db, current_user, ACCESS_FARO):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso denegado.")

    safe_next_path = _safe_faro_next_path(next_path)
    if current_user.role in {"admin", "supervisor"}:
        clear_active_residential(request.session)
        return RedirectResponse(safe_next_path, status_code=status.HTTP_303_SEE_OTHER)

    residentials = assigned_residentials(db, current_user)
    if not residentials:
        clear_active_residential(request.session)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene residenciales activos asignados.",
        )

    selected_residential = residentials[0] if len(residentials) == 1 else next(
        (
            residential
            for residential in residentials
            if residential.residential_id == residential_id
        ),
        None,
    )
    if selected_residential is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Seleccione un residencial asignado y activo.",
        )

    set_active_residential(request.session, selected_residential)
    request.session[AVAILABLE_RESIDENTIAL_COUNT_SESSION_KEY] = len(residentials)
    return RedirectResponse(safe_next_path, status_code=status.HTTP_303_SEE_OTHER)


@router.get("/auth/google")
async def google_login(request: Request):
    configuration = _require_google_oauth_enabled()
    nonce = new_google_nonce()
    clear_google_oauth_session(request.session)
    request.session[GOOGLE_NONCE_SESSION_KEY] = nonce
    client = create_google_oauth_client(configuration)
    try:
        return await client.authorize_redirect(
            request,
            configuration.redirect_uri,
            nonce=nonce,
        )
    except (OAuthError, httpx.HTTPError):
        return _oauth_error_response(request, status_code=503)


@router.get("/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    configuration = _require_google_oauth_enabled()
    expected_nonce = request.session.get(GOOGLE_NONCE_SESSION_KEY)
    if not isinstance(expected_nonce, str) or not expected_nonce:
        return _oauth_error_response(request, status_code=400)

    client = create_google_oauth_client(configuration)
    try:
        token = await client.authorize_access_token(request)
    except (OAuthError, JoseError, httpx.HTTPError):
        return _oauth_error_response(request, status_code=400)

    claims = token.get("userinfo") if isinstance(token, Mapping) else None
    if not isinstance(claims, Mapping):
        return _oauth_error_response(request, status_code=400)

    try:
        google_sub, normalized_email = validate_google_identity(
            claims,
            configuration=configuration,
            expected_nonce=expected_nonce,
        )
    except GoogleIdentityError:
        return _oauth_error_response(request)

    users_by_sub = db.execute(
        select(User).where(User.google_sub == google_sub)
    ).scalars().all()
    if len(users_by_sub) > 1:
        return _oauth_error_response(request)

    if users_by_sub:
        user = users_by_sub[0]
        if not user.is_active:
            return _oauth_error_response(request)
    else:
        users_by_email = db.execute(
            select(User).where(
                func.lower(func.ltrim(func.rtrim(User.email))) == normalized_email
            )
        ).scalars().all()
        if len(users_by_email) != 1:
            return _oauth_error_response(request)

        user = users_by_email[0]
        if not user.is_active:
            return _oauth_error_response(request)
        if user.google_sub and user.google_sub != google_sub:
            return _oauth_error_response(request)
        if user.google_linked_at is not None:
            return _oauth_error_response(request)

        if not user.google_sub:
            link_result = db.execute(
                update(User)
                .where(
                    User.user_id == user.user_id,
                    User.google_sub.is_(None),
                    User.google_linked_at.is_(None),
                    User.is_active == True,  # noqa: E712
                    func.lower(func.ltrim(func.rtrim(User.email))) == normalized_email,
                )
                .values(
                    google_sub=google_sub,
                    google_linked_at=func.sysutcdatetime(),
                    session_version=User.session_version + 1,
                )
            )
            if link_result.rowcount != 1:
                db.rollback()
                return _oauth_error_response(request)
            db.add(
                PlatformUserAudit(
                    actor_user_id=user.user_id,
                    target_user_id=user.user_id,
                    action="google_linked",
                )
            )
            try:
                db.commit()
                db.refresh(user)
            except IntegrityError:
                db.rollback()
                return _oauth_error_response(request)

    establish_authenticated_session(request.session, user)
    return RedirectResponse("/home", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/home", status_code=303)
