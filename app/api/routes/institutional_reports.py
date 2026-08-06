from __future__ import annotations

import secrets
import time
from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, extract, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.activity_session import ActivitySession
from app.models.proposal import Proposal


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_FARO_AUTHORIZED_AT_KEY = "institutional_report_faro_authorized_at"
_FARO_FAILED_ATTEMPTS_KEY = "institutional_report_faro_failed_attempts"
_FARO_LOCKED_UNTIL_KEY = "institutional_report_faro_locked_until"

_AUTHORIZATION_IDLE_TIMEOUT_SECONDS = 30 * 60
_FAILED_ATTEMPT_LIMIT = 5
_FAILED_ATTEMPT_LOCK_SECONDS = 5 * 60

_FARO_REAL_METRICS = ["activities"]
_FARO_DEMO_METRICS = [
    "people",
    "duplicates",
    "towns",
    "age",
    "education",
    "grades",
    "pregnancy",
    "towns_by_municipality",
]


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


def _no_store_json(payload: dict, status_code: int = status.HTTP_200_OK) -> JSONResponse:
    response = JSONResponse(payload, status_code=status_code)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


def _normalize_proposal_ids(proposal_ids: list[int | str] | None) -> list[int]:
    normalized: list[int] = []
    for raw_value in proposal_ids or []:
        try:
            proposal_id = int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Los identificadores de propuesta deben ser números enteros.") from exc
        if proposal_id <= 0:
            raise ValueError("Los identificadores de propuesta deben ser mayores que cero.")
        if proposal_id not in normalized:
            normalized.append(proposal_id)
    return normalized


def _parse_optional_year(value: int | str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("El año debe ser un número entero.") from exc
    if year < 1900 or year > 9999:
        raise ValueError("El año debe estar entre 1900 y 9999.")
    return year


def _parse_optional_date(value: date | str | None, label: str) -> date | None:
    if value is None or str(value).strip() == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{label} debe usar el formato AAAA-MM-DD.") from exc


def _active_faro_proposals(db: Session) -> list[Proposal]:
    return list(
        db.execute(
            select(Proposal)
            .where(Proposal.is_active == True)  # noqa: E712
            .order_by(Proposal.code, Proposal.name)
        ).scalars().all()
    )


def _activity_years_for_proposals(db: Session, proposal_ids: list[int]) -> list[int]:
    if not proposal_ids:
        return []

    report_year = extract("year", ActivitySession.session_date).label("report_year")
    rows = db.execute(
        select(report_year)
        .where(ActivitySession.proposal_id.in_(proposal_ids))
        .distinct()
        .order_by(report_year.desc())
    ).scalars().all()
    return [int(value) for value in rows if value is not None]


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
def faro_institutional_report(
    request: Request,
    db: Session = Depends(get_db),
):
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

    proposals = _active_faro_proposals(db)
    proposal_ids = [proposal.proposal_id for proposal in proposals]
    year_options = _activity_years_for_proposals(db, proposal_ids)
    default_year = year_options[0] if year_options else date.today().year

    response = templates.TemplateResponse(
        request=request,
        name="institutional_reports/faro_dashboard.html",
        context={
            "current_year": date.today().year,
            "proposals": proposals,
            "year_options": year_options or [default_year],
            "default_year": default_year,
            "default_start_date": date(default_year, 1, 1).isoformat(),
            "default_end_date": date(default_year, 12, 31).isoformat(),
        },
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response


@router.get("/reporteinstitucionales/farodeesperanza/data")
def faro_institutional_report_data(
    request: Request,
    proposal_ids: list[str] | None = Query(default=None),
    year: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return the real activity KPI; proposal_ids uses repeated query parameters."""

    now = _current_timestamp()
    if _configured_faro_pin() is None:
        _clear_faro_authorization(request)
        return _no_store_json(
            {"detail": "El reporte no está disponible en este momento."},
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if not _has_valid_faro_authorization(request, now):
        return _no_store_json(
            {"detail": "La autorización del reporte expiró o no es válida."},
            status.HTTP_403_FORBIDDEN,
        )

    try:
        normalized_proposal_ids = _normalize_proposal_ids(proposal_ids)
        normalized_year = _parse_optional_year(year)
        normalized_start_date = _parse_optional_date(start_date, "La fecha inicial")
        normalized_end_date = _parse_optional_date(end_date, "La fecha final")
    except ValueError as exc:
        return _no_store_json(
            {"detail": str(exc)},
            status.HTTP_400_BAD_REQUEST,
        )

    if not normalized_proposal_ids:
        return _no_store_json(
            {"detail": "Seleccione al menos una propuesta."},
            status.HTTP_400_BAD_REQUEST,
        )

    if normalized_start_date and normalized_end_date and normalized_start_date > normalized_end_date:
        return _no_store_json(
            {"detail": "La fecha inicial no puede ser posterior a la fecha final."},
            status.HTTP_400_BAD_REQUEST,
        )

    available_proposal_ids = set(
        db.execute(
            select(Proposal.proposal_id).where(
                Proposal.is_active == True,  # noqa: E712
                Proposal.proposal_id.in_(normalized_proposal_ids),
            )
        ).scalars().all()
    )
    if available_proposal_ids != set(normalized_proposal_ids):
        return _no_store_json(
            {"detail": "Una o más propuestas seleccionadas no están disponibles."},
            status.HTTP_400_BAD_REQUEST,
        )

    activities_stmt = select(func.count(distinct(ActivitySession.session_id))).where(
        ActivitySession.proposal_id.in_(normalized_proposal_ids)
    )
    if normalized_year is not None:
        activities_stmt = activities_stmt.where(extract("year", ActivitySession.session_date) == normalized_year)
    if normalized_start_date is not None:
        activities_stmt = activities_stmt.where(ActivitySession.session_date >= normalized_start_date)
    if normalized_end_date is not None:
        activities_stmt = activities_stmt.where(ActivitySession.session_date <= normalized_end_date)

    activities_count = int(db.execute(activities_stmt).scalar_one() or 0)
    return _no_store_json(
        {
            "real": {
                "activities": activities_count,
            },
            "filters": {
                "proposal_ids": normalized_proposal_ids,
                "year": normalized_year,
                "start_date": normalized_start_date.isoformat() if normalized_start_date else None,
                "end_date": normalized_end_date.isoformat() if normalized_end_date else None,
            },
            "meta": {
                "real_metrics": _FARO_REAL_METRICS,
                "demo_metrics": _FARO_DEMO_METRICS,
            },
        }
    )


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
