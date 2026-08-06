from __future__ import annotations

import secrets
import time
from collections.abc import Sequence
from datetime import date

from fastapi import APIRouter, Depends, Form, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, extract, func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.person import Person
from app.models.pregnancy_report import PregnancyReport
from app.models.pregnancy_report_item import PregnancyReportItem
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential
from app.models.school_grade_report import SchoolGradeReport
from app.models.school_grade_report_item import SchoolGradeReportItem
from app.models.user import User


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

_FARO_AUTHORIZED_AT_KEY = "institutional_report_faro_authorized_at"
_FARO_FAILED_ATTEMPTS_KEY = "institutional_report_faro_failed_attempts"
_FARO_LOCKED_UNTIL_KEY = "institutional_report_faro_locked_until"

_AUTHORIZATION_IDLE_TIMEOUT_SECONDS = 30 * 60
_FAILED_ATTEMPT_LIMIT = 5
_FAILED_ATTEMPT_LOCK_SECONDS = 5 * 60

_FARO_REAL_METRICS = [
    "activities",
    "people",
    "duplicates",
    "towns",
    "age",
    "education",
    "grades",
    "pregnancy",
    "towns_by_municipality",
]
_FARO_DEMO_METRICS = []
_FARO_AGE_BUCKETS = ("0 a 12", "13 a 18", "19 a 59", "60 o más", "No informado")
_FARO_GRADE_SUBJECTS = ("Español", "Matemáticas", "Ciencias", "Inglés")


def _current_timestamp() -> int:
    return int(time.time())


def _current_date() -> date:
    return date.today()


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


def _normalize_proposal_ids(proposal_ids: Sequence[int | str] | None) -> list[int]:
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


def _apply_activity_session_filters(
    statement,
    *,
    proposal_ids: list[int],
    year: int | None,
    start_date: date | None,
    end_date: date | None,
):
    statement = statement.where(ActivitySession.proposal_id.in_(proposal_ids))
    if year is not None:
        statement = statement.where(extract("year", ActivitySession.session_date) == year)
    if start_date is not None:
        statement = statement.where(ActivitySession.session_date >= start_date)
    if end_date is not None:
        statement = statement.where(ActivitySession.session_date <= end_date)
    return statement


def _age_reference_date(end_date: date | None, year: int | None) -> date:
    if end_date is not None:
        return end_date
    if year is not None:
        return date(year, 12, 31)
    return _current_date()


def _age_bucket(birth_date: date | None, reference_date: date) -> str:
    if birth_date is None or birth_date > reference_date:
        return "No informado"

    age = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1

    if age <= 12:
        return "0 a 12"
    if age <= 18:
        return "13 a 18"
    if age <= 59:
        return "19 a 59"
    return "60 o más"


def _normalize_education(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _count_additional_attendances(attendance_counts: Sequence[int]) -> int:
    return sum(max(int(attendance_count) - 1, 0) for attendance_count in attendance_counts)


def _aggregate_subject_grades(grade_rows) -> dict[str, int]:
    latest_grade_row_by_student: dict[tuple[str, int], tuple] = {}
    for row in grade_rows:
        (
            person_id,
            participant_id,
            report_year,
            report_month,
            report_id,
            spanish_grade,
            math_grade,
            science_grade,
            english_grade,
        ) = row
        student_key = (
            ("person", int(person_id))
            if person_id is not None
            else ("participant", int(participant_id))
        )
        report_order = (int(report_year), int(report_month), int(report_id))
        current_row = latest_grade_row_by_student.get(student_key)
        if current_row is None or report_order > current_row[0]:
            latest_grade_row_by_student[student_key] = (
                report_order,
                (spanish_grade, math_grade, science_grade, english_grade),
            )

    grade_totals = {subject: 0.0 for subject in _FARO_GRADE_SUBJECTS}
    grade_counts = {subject: 0 for subject in _FARO_GRADE_SUBJECTS}
    for _, grades in latest_grade_row_by_student.values():
        for subject, raw_grade in zip(_FARO_GRADE_SUBJECTS, grades, strict=True):
            if raw_grade is None:
                continue
            try:
                grade = float(raw_grade)
            except (TypeError, ValueError, OverflowError):
                continue
            if not 0 <= grade <= 100:
                continue
            grade_totals[subject] += grade
            grade_counts[subject] += 1

    return {
        subject: (
            round(grade_totals[subject] / grade_counts[subject])
            if grade_counts[subject]
            else 0
        )
        for subject in _FARO_GRADE_SUBJECTS
    }


def _aggregate_pregnancy_summary(pregnancy_rows) -> dict[str, int]:
    pregnancy_by_person: dict[tuple[str, int], dict] = {}
    for row in pregnancy_rows:
        (
            participated_workshops,
            is_pregnant,
            report_year,
            report_month,
            report_id,
            participant_id,
            gender,
            person_id,
        ) = row
        person_key = (
            ("person", int(person_id))
            if person_id is not None
            else ("participant", int(participant_id))
        )
        report_order = (int(report_year), int(report_month), int(report_id))
        normalized_gender = str(gender).strip().casefold() if gender is not None else ""
        summary = pregnancy_by_person.setdefault(
            person_key,
            {
                "participated_workshops": False,
                "is_pregnant": False,
                "gender": "",
                "latest_report": None,
            },
        )
        summary["participated_workshops"] = bool(
            summary["participated_workshops"] or participated_workshops
        )
        summary["is_pregnant"] = bool(summary["is_pregnant"] or is_pregnant)
        if summary["latest_report"] is None or report_order >= summary["latest_report"]:
            summary["latest_report"] = report_order
            summary["gender"] = normalized_gender or summary["gender"]

    women = 0
    men = 0
    workshop_participants = 0
    for summary in pregnancy_by_person.values():
        if summary["participated_workshops"]:
            workshop_participants += 1
        if not summary["is_pregnant"]:
            continue
        if summary["gender"].startswith("f"):
            women += 1
        elif summary["gender"].startswith("m"):
            men += 1

    return {
        "women": women,
        "men": men,
        "followups": workshop_participants,
    }


def _aggregate_unique_people(
    person_rows,
    reference_date: date,
) -> tuple[
    int,
    dict[str, int],
    dict[str, int],
    int,
    dict[str, int],
]:
    birth_dates_by_person: dict[int, date | None] = {}
    education_by_person: dict[int, str | None] = {}
    municipality_by_person: dict[int, str | None] = {}
    for person_id, birth_date, education, municipality in person_rows:
        if person_id not in birth_dates_by_person:
            birth_dates_by_person[person_id] = birth_date
            education_by_person[person_id] = None
            municipality_by_person[person_id] = None
        if education_by_person[person_id] is None:
            education_by_person[person_id] = _normalize_education(education)
        if municipality_by_person[person_id] is None:
            municipality_by_person[person_id] = _normalize_education(municipality)

    age_buckets = {label: 0 for label in _FARO_AGE_BUCKETS}
    for birth_date in birth_dates_by_person.values():
        age_buckets[_age_bucket(birth_date, reference_date)] += 1

    education_buckets: dict[str, int] = {}
    for education in education_by_person.values():
        label = education or "No informado"
        education_buckets[label] = education_buckets.get(label, 0) + 1

    ordered_education_buckets = {
        label: education_buckets[label]
        for label in sorted(
            (label for label in education_buckets if label != "No informado"),
            key=str.casefold,
        )
    }
    ordered_education_buckets["No informado"] = education_buckets.get("No informado", 0)

    municipality_buckets: dict[str, int] = {}
    for municipality in municipality_by_person.values():
        label = municipality or "No informado"
        municipality_buckets[label] = municipality_buckets.get(label, 0) + 1

    ordered_municipality_buckets = {
        label: municipality_buckets[label]
        for label in sorted(
            (label for label in municipality_buckets if label != "No informado"),
            key=str.casefold,
        )
    }
    ordered_municipality_buckets["No informado"] = municipality_buckets.get(
        "No informado", 0
    )
    towns_count = sum(
        1
        for label, count in ordered_municipality_buckets.items()
        if label != "No informado" and count > 0
    )

    return (
        len(birth_dates_by_person),
        age_buckets,
        ordered_education_buckets,
        towns_count,
        ordered_municipality_buckets,
    )


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
    """Return aggregate real metrics; proposal_ids uses repeated query parameters."""

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

    activities_stmt = _apply_activity_session_filters(
        select(func.count(distinct(ActivitySession.session_id))),
        proposal_ids=normalized_proposal_ids,
        year=normalized_year,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
    )
    activities_count = int(db.execute(activities_stmt).scalar_one() or 0)

    attendance_counts_stmt = (
        select(func.count(Attendance.attendance_id))
        .select_from(Attendance)
        .join(ActivitySession, Attendance.session_id == ActivitySession.session_id)
        .join(
            ProposalParticipant,
            Attendance.proposal_participant_id == ProposalParticipant.proposal_participant_id,
        )
        .join(Person, ProposalParticipant.person_id == Person.person_id)
        .where(
            Attendance.attended == True,  # noqa: E712
            ProposalParticipant.proposal_id == ActivitySession.proposal_id,
        )
        .group_by(Person.person_id)
    )
    attendance_counts_stmt = _apply_activity_session_filters(
        attendance_counts_stmt,
        proposal_ids=normalized_proposal_ids,
        year=normalized_year,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
    )
    additional_attendances_count = _count_additional_attendances(
        db.execute(attendance_counts_stmt).scalars().all()
    )

    unique_people_stmt = (
        select(
            Person.person_id,
            Person.fecha_nacimiento,
            Participant.escolaridad_participante,
            Residential.municipality,
        )
        .select_from(Attendance)
        .join(ActivitySession, Attendance.session_id == ActivitySession.session_id)
        .join(
            ProposalParticipant,
            Attendance.proposal_participant_id == ProposalParticipant.proposal_participant_id,
        )
        .join(Person, ProposalParticipant.person_id == Person.person_id)
        .outerjoin(Participant, Person.legacy_participant_id == Participant.participant_id)
        .outerjoin(User, Participant.created_by_user_id == User.user_id)
        .outerjoin(Residential, User.residential_id == Residential.residential_id)
        .where(
            Attendance.attended == True,  # noqa: E712
            ProposalParticipant.proposal_id == ActivitySession.proposal_id,
        )
        .distinct()
    )
    unique_people_stmt = _apply_activity_session_filters(
        unique_people_stmt,
        proposal_ids=normalized_proposal_ids,
        year=normalized_year,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
    )
    reference_date = _age_reference_date(normalized_end_date, normalized_year)
    (
        people_count,
        age_buckets,
        education_buckets,
        towns_count,
        towns_by_municipality,
    ) = _aggregate_unique_people(db.execute(unique_people_stmt).all(), reference_date)

    report_date = func.datefromparts(
        SchoolGradeReport.report_year,
        SchoolGradeReport.report_month,
        1,
    )
    grades_stmt = (
        select(
            Person.person_id,
            Participant.participant_id,
            SchoolGradeReport.report_year,
            SchoolGradeReport.report_month,
            SchoolGradeReport.report_id,
            SchoolGradeReportItem.spanish_grade,
            SchoolGradeReportItem.math_grade,
            SchoolGradeReportItem.science_grade,
            SchoolGradeReportItem.english_grade,
        )
        .select_from(SchoolGradeReportItem)
        .join(
            SchoolGradeReport,
            SchoolGradeReport.report_id == SchoolGradeReportItem.report_id,
        )
        .join(
            Participant,
            Participant.participant_id == SchoolGradeReportItem.participant_id,
        )
        .outerjoin(Person, Person.legacy_participant_id == Participant.participant_id)
        .where(SchoolGradeReport.proposal_id.in_(normalized_proposal_ids))
    )
    if normalized_year is not None:
        grades_stmt = grades_stmt.where(SchoolGradeReport.report_year == normalized_year)
    if normalized_start_date is not None:
        grades_stmt = grades_stmt.where(report_date >= normalized_start_date)
    if normalized_end_date is not None:
        grades_stmt = grades_stmt.where(report_date <= normalized_end_date)
    subject_grade_averages = _aggregate_subject_grades(db.execute(grades_stmt).all())

    pregnancy_report_date = func.datefromparts(
        PregnancyReport.report_year,
        PregnancyReport.report_month,
        1,
    )
    pregnancy_stmt = (
        select(
            PregnancyReportItem.participated_workshops,
            PregnancyReportItem.is_pregnant,
            PregnancyReport.report_year,
            PregnancyReport.report_month,
            PregnancyReport.report_id,
            Participant.participant_id,
            Participant.genero,
            Person.person_id,
        )
        .select_from(PregnancyReportItem)
        .join(
            PregnancyReport,
            PregnancyReport.report_id == PregnancyReportItem.report_id,
        )
        .join(
            Participant,
            Participant.participant_id == PregnancyReportItem.participant_id,
        )
        .outerjoin(Person, Person.legacy_participant_id == Participant.participant_id)
        .where(PregnancyReport.proposal_id.in_(normalized_proposal_ids))
    )
    if normalized_year is not None:
        pregnancy_stmt = pregnancy_stmt.where(PregnancyReport.report_year == normalized_year)
    if normalized_start_date is not None:
        pregnancy_stmt = pregnancy_stmt.where(
            pregnancy_report_date >= normalized_start_date
        )
    if normalized_end_date is not None:
        pregnancy_stmt = pregnancy_stmt.where(pregnancy_report_date <= normalized_end_date)
    pregnancy_summary = _aggregate_pregnancy_summary(db.execute(pregnancy_stmt).all())

    return _no_store_json(
        {
            "real": {
                "activities": activities_count,
                "people": people_count,
                "duplicates": additional_attendances_count,
                "towns": towns_count,
                "age": age_buckets,
                "education": education_buckets,
                "grades": subject_grade_averages,
                "pregnancy": pregnancy_summary,
                "towns_by_municipality": towns_by_municipality,
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
                "age_reference_date": reference_date.isoformat(),
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
