from __future__ import annotations

from calendar import monthrange
from datetime import date

from fastapi import HTTPException

from app.models.proposal import Proposal

MONTH_LABELS = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def current_reporting_period(today: date | None = None) -> tuple[int, int]:
    today = today or date.today()
    return today.month, today.year


def normalize_reporting_period(month: int, year: int) -> tuple[int, int]:
    if month < 1 or month > 12:
        raise HTTPException(status_code=409, detail="Error: El mes seleccionado no es válido.")
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=409, detail="Error: El año seleccionado no es válido.")
    return month, year


def format_reporting_period(month: int, year: int) -> str:
    normalize_reporting_period(month, year)
    return f"{MONTH_LABELS.get(month, month)} {year}"


def proposal_locked_through_period(proposal: Proposal | None) -> tuple[int, int] | None:
    if not proposal:
        return None
    month = getattr(proposal, "locked_through_month", None)
    year = getattr(proposal, "locked_through_year", None)
    if month is None or year is None:
        return None
    return normalize_reporting_period(int(month), int(year))


def proposal_locked_through_label(proposal: Proposal | None) -> str | None:
    period = proposal_locked_through_period(proposal)
    if not period:
        return None
    month, year = period
    return format_reporting_period(month, year)


def is_future_reporting_period(month: int, year: int, *, today: date | None = None) -> bool:
    month, year = normalize_reporting_period(month, year)
    current_month, current_year = current_reporting_period(today)
    return (year, month) > (current_year, current_month)


def require_reporting_period_not_future(
    month: int,
    year: int,
    *,
    message: str | None = None,
) -> None:
    if is_future_reporting_period(month, year):
        raise HTTPException(
            status_code=409,
            detail=message or "Error: No se permiten periodos futuros.",
        )


def is_proposal_period_locked(proposal: Proposal | None, month: int, year: int) -> bool:
    month, year = normalize_reporting_period(month, year)
    locked_period = proposal_locked_through_period(proposal)
    if not locked_period:
        return False
    locked_month, locked_year = locked_period
    return (year, month) <= (locked_year, locked_month)


def require_proposal_period_open(
    proposal: Proposal | None,
    month: int,
    year: int,
    *,
    message: str | None = None,
) -> None:
    if is_proposal_period_locked(proposal, month, year):
        locked_label = proposal_locked_through_label(proposal)
        raise HTTPException(
            status_code=409,
            detail=message or f"Error: La propuesta tiene periodos cerrados hasta {locked_label}.",
        )


def is_session_date_future(session_date: date, *, today: date | None = None) -> bool:
    today = today or date.today()
    return session_date > today


def require_session_date_not_future(session_date: date, *, message: str | None = None) -> None:
    if is_session_date_future(session_date):
        raise HTTPException(
            status_code=409,
            detail=message or "Error: No se permiten fechas futuras en asistencias o sesiones.",
        )


def is_session_date_in_locked_period(proposal: Proposal | None, session_date: date) -> bool:
    return is_proposal_period_locked(proposal, session_date.month, session_date.year)


def require_session_date_in_open_period(
    proposal: Proposal | None,
    session_date: date,
    *,
    message: str | None = None,
) -> None:
    if is_session_date_in_locked_period(proposal, session_date):
        locked_label = proposal_locked_through_label(proposal)
        raise HTTPException(
            status_code=409,
            detail=message or f"Error: La propuesta tiene periodos cerrados hasta {locked_label}.",
        )


def period_month_has_entry_window(month: int, year: int, *, today: date | None = None) -> bool:
    return not is_future_reporting_period(month, year, today=today)


def next_period_start(month: int, year: int) -> date:
    month, year = normalize_reporting_period(month, year)
    if month == 12:
        return date(year + 1, 1, 1)
    return date(year, month + 1, 1)


def period_end_date(month: int, year: int) -> date:
    month, year = normalize_reporting_period(month, year)
    return date(year, month, monthrange(year, month)[1])
