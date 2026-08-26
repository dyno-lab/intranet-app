from __future__ import annotations

from collections.abc import Mapping

import httpx
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from joserfc.errors import JoseError
from sqlalchemy import func, select
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
    google_oauth_is_available,
    new_google_nonce,
    validate_google_identity,
)
from app.core.security import verify_password
from app.models.user import User


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _login_context(request: Request, *, error: str | None = None) -> dict:
    return {
        "request": request,
        "error": error,
        "google_oauth_available": google_oauth_is_available(),
    }


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
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context=_login_context(request),
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

    if not user or not user.is_active or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request=request,
            name="auth/login.html",
            context=_login_context(request, error="Credenciales incorrectas"),
        )

    request.session.clear()
    request.session["user_id"] = user.user_id

    return RedirectResponse("/ui/new-list", status_code=303)


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

        if not user.google_sub:
            user.google_sub = google_sub
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                return _oauth_error_response(request)

    request.session.clear()
    request.session["user_id"] = user.user_id
    return RedirectResponse("/ui/new-list", status_code=303)


@router.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
