from __future__ import annotations

import secrets
import time
from datetime import date

from fastapi import APIRouter, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core.config import settings


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_FARO_AUTHORIZED_AT_KEY = "institutional_report_faro_authorized_at"
_FARO_FAILED_ATTEMPTS_KEY = "institutional_report_faro_failed_attempts"
_FARO_LOCKED_UNTIL_KEY = "institutional_report_faro_locked_until"

_AUTHORIZATION_IDLE_TIMEOUT_SECONDS = 30 * 60
_FAILED_ATTEMPT_LIMIT = 5
_FAILED_ATTEMPT_LOCK_SECONDS = 5 * 60


def _current_timestamp() -> int:
    return int(time.time())


def _configured_faro_pin() -> str | None:
    configured_pin = settings.FARO_INSTITUTIONAL_REPORT_PIN
    if configured_pin is None:
        return None
    normalized_pin = configured_pin.strip()
    return normalized_pin or None


def _session_integer(request: Request, key: str) -> int:
    try:
        return int(request.session.get(key, 0))
    except (TypeError, ValueError):
        return 0


def _clear_faro_authorization(request: Request) -> None:
    request.session.pop(_FARO_AUTHORIZED_AT_KEY, None)


def _clear_failed_attempts(request: Request) -> None:
    request.session.pop(_FARO_FAILED_ATTEMPTS_KEY, None)
    request.session.pop(_FARO_LOCKED_UNTIL_KEY, None)


def _is_temporarily_locked(request: Request, now: int) -> bool:
    locked_until = _session_integer(request, _FARO_LOCKED_UNTIL_KEY)
    if locked_until > now:
        return True
    if locked_until:
        _clear_failed_attempts(request)
    return False


def _has_valid_faro_authorization(request: Request, now: int) -> bool:
    authorized_at = _session_integer(request, _FARO_AUTHORIZED_AT_KEY)
    elapsed = now - authorized_at
    if authorized_at <= 0 or elapsed < 0 or elapsed > _AUTHORIZATION_IDLE_TIMEOUT_SECONDS:
        _clear_faro_authorization(request)
        return False

    request.session[_FARO_AUTHORIZED_AT_KEY] = now
    return True


def _pin_page_response(
    request: Request,
    *,
    error: str | None = None,
    status_code: int = status.HTTP_200_OK,
) -> HTMLResponse:
    configuration_error = _configured_faro_pin() is None
    if configuration_error:
        error = "El reporte no está disponible en este momento. Comuníquese con el administrador."
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    response = templates.TemplateResponse(
        request=request,
        name="institutional_reports/faro_pin.html",
        context={
            "current_year": date.today().year,
            "error": error,
            "configuration_error": configuration_error,
        },
        status_code=status_code,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@router.get("/reporteinstitucionales", response_class=HTMLResponse)
def institutional_reports_index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="institutional_reports/index.html",
        context={
            "current_year": date.today().year,
        },
    )


@router.get("/reporteinstitucionales/farodeesperanza", response_class=HTMLResponse)
def faro_institutional_report(request: Request):
    now = _current_timestamp()
    if _configured_faro_pin() is None:
        _clear_faro_authorization(request)
        return _pin_page_response(request)

    if not _has_valid_faro_authorization(request, now):
        error = None
        status_code = status.HTTP_200_OK
        if _is_temporarily_locked(request, now):
            error = "Demasiados intentos. Intente nuevamente más tarde."
            status_code = status.HTTP_429_TOO_MANY_REQUESTS
        return _pin_page_response(request, error=error, status_code=status_code)

    response = templates.TemplateResponse(
        request=request,
        name="institutional_reports/faro_dashboard.html",
        context={
            "current_year": date.today().year,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@router.post("/reporteinstitucionales/farodeesperanza/pin")
def faro_institutional_report_pin(
    request: Request,
    pin: str = Form(...),
):
    now = _current_timestamp()
    if _is_temporarily_locked(request, now):
        return _pin_page_response(
            request,
            error="Demasiados intentos. Intente nuevamente más tarde.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    configured_pin = _configured_faro_pin()
    if configured_pin is None:
        return _pin_page_response(request)

    submitted_pin = pin.strip()
    if secrets.compare_digest(submitted_pin, configured_pin):
        request.session[_FARO_AUTHORIZED_AT_KEY] = now
        _clear_failed_attempts(request)
        return RedirectResponse(
            "/reporteinstitucionales/farodeesperanza",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    failed_attempts = _session_integer(request, _FARO_FAILED_ATTEMPTS_KEY) + 1
    request.session[_FARO_FAILED_ATTEMPTS_KEY] = failed_attempts
    if failed_attempts >= _FAILED_ATTEMPT_LIMIT:
        request.session[_FARO_LOCKED_UNTIL_KEY] = now + _FAILED_ATTEMPT_LOCK_SECONDS
        return _pin_page_response(
            request,
            error="Demasiados intentos. Intente nuevamente más tarde.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    return _pin_page_response(
        request,
        error="PIN incorrecto. Intente nuevamente.",
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@router.post("/reporteinstitucionales/farodeesperanza/logout")
def faro_institutional_report_logout(request: Request):
    _clear_faro_authorization(request)
    return RedirectResponse(
        "/reporteinstitucionales/farodeesperanza",
        status_code=status.HTTP_303_SEE_OTHER,
    )
