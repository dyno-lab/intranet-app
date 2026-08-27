from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, extract, func, select
from sqlalchemy.orm import Session, aliased

from app.api.deps import get_db
from app.models.adm_service_type import ADMServiceType
from app.models.adm_service_type_activity_code import ADMServiceTypeActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.catalog_option import CatalogOption
from app.models.catalog_type import CatalogType
from app.models.participant import Participant
from app.models.person import Person
from app.models.pregnancy_report import PregnancyReport
from app.models.pregnancy_report_item import PregnancyReportItem
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential
from app.models.school_grade_report import SchoolGradeReport
from app.models.school_grade_report_item import SchoolGradeReportItem


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


_FARO_REAL_METRICS = [
    "activities",
    "people",
    "duplicates",
    "towns",
    "age",
    "household_heads",
    "education",
    "grades",
    "pregnancy",
    "towns_by_municipality",
    "adm",
]
_FARO_DEMO_METRICS = []
_ADM_AGE_BUCKETS = (
    ("0_5", "0-5"),
    ("6_11", "6-11"),
    ("12_17", "12-17"),
    ("18_21", "18-21"),
    ("22_25", "22-25"),
    ("26_45", "26-45"),
    ("46_59", "46-59"),
    ("60_74", "60-74"),
    ("75_plus", "75+"),
)
_FARO_AGE_BUCKETS = ("0 a 12", "13 a 18", "19 a 59", "60 o más", "No informado")
_FARO_GRADE_SUBJECTS = ("Español", "Matemáticas", "Ciencias", "Inglés")


def _current_date() -> date:
    return date.today()


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
    int,
    dict[str, int],
]:
    birth_dates_by_person: dict[int, date | None] = {}
    education_by_person: dict[int, str | None] = {}
    municipality_by_person: dict[int, str | None] = {}
    household_head_person_ids: set[int] = set()
    for person_id, birth_date, education, is_head_of_household, municipality in person_rows:
        if person_id not in birth_dates_by_person:
            birth_dates_by_person[person_id] = birth_date
            education_by_person[person_id] = None
            municipality_by_person[person_id] = None
        if is_head_of_household:
            household_head_person_ids.add(person_id)
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
        len(household_head_person_ids),
        towns_count,
        ordered_municipality_buckets,
    )


def _empty_faro_adm() -> dict:
    return {
        "summary": {
            "services": 0,
            "duplicates": 0,
            "unique_participants": 0,
            "service_types": 0,
        },
        "service_rows": [],
        "sociodemographic_rows": [],
        "sociodemographic_total": {"f": 0, "m": 0, "total": 0, "vca": 0},
        "family_rows": [],
        "family_total": 0,
    }


def _adm_age_bucket(age: int | None) -> str | None:
    if age is None or age < 0:
        return None
    if age <= 5:
        return "0_5"
    if age <= 11:
        return "6_11"
    if age <= 17:
        return "12_17"
    if age <= 21:
        return "18_21"
    if age <= 25:
        return "22_25"
    if age <= 45:
        return "26_45"
    if age <= 59:
        return "46_59"
    if age <= 74:
        return "60_74"
    return "75_plus"


def _age_on_date(birth_date: date | None, reference_date: date) -> int | None:
    if birth_date is None or birth_date > reference_date:
        return None
    age = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def _faro_adm_summary(
    db: Session,
    *,
    proposal_ids: list[int],
    year: int | None,
    start_date: date | None,
    end_date: date | None,
    reference_date: date,
) -> dict:
    service_types = list(
        db.execute(
            select(ADMServiceType)
            .where(
                ADMServiceType.proposal_id.in_(proposal_ids),
                ADMServiceType.is_active == True,  # noqa: E712
            )
            .order_by(
                ADMServiceType.proposal_id,
                ADMServiceType.sort_order,
                ADMServiceType.name,
            )
        ).scalars().all()
    )
    if not service_types:
        return _empty_faro_adm()

    session_stmt = _apply_activity_session_filters(
        select(
            ActivitySession.session_id,
            ADMServiceType.adm_service_type_id,
        )
        .select_from(ActivitySession)
        .join(
            ADMServiceTypeActivityCode,
            ADMServiceTypeActivityCode.activity_code_id
            == ActivitySession.activity_code_id,
        )
        .join(
            ADMServiceType,
            ADMServiceType.adm_service_type_id
            == ADMServiceTypeActivityCode.adm_service_type_id,
        )
        .where(
            ADMServiceType.is_active == True,  # noqa: E712
            ADMServiceType.proposal_id == ActivitySession.proposal_id,
        ),
        proposal_ids=proposal_ids,
        year=year,
        start_date=start_date,
        end_date=end_date,
    )
    session_rows = db.execute(session_stmt).all()
    sessions_by_service_type: dict[int, set[int]] = {}
    for session_id, service_type_id in session_rows:
        sessions_by_service_type.setdefault(int(service_type_id), set()).add(
            int(session_id)
        )

    attendance_participant = aliased(Participant, name="attendance_participant")
    legacy_participant = aliased(Participant, name="legacy_participant")
    attendance_stmt = (
        select(
            Attendance.session_id,
            Attendance.participant_id,
            ProposalParticipant.person_id,
            Person.legacy_participant_id,
            ADMServiceType.adm_service_type_id,
            attendance_participant.participant_id,
            attendance_participant.fecha_nacimiento,
            attendance_participant.genero,
            attendance_participant.vca,
            attendance_participant.composicion_familiar,
            legacy_participant.participant_id,
            legacy_participant.fecha_nacimiento,
            legacy_participant.genero,
            legacy_participant.vca,
            legacy_participant.composicion_familiar,
        )
        .select_from(Attendance)
        .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
        .join(
            ADMServiceTypeActivityCode,
            ADMServiceTypeActivityCode.activity_code_id
            == ActivitySession.activity_code_id,
        )
        .join(
            ADMServiceType,
            ADMServiceType.adm_service_type_id
            == ADMServiceTypeActivityCode.adm_service_type_id,
        )
        .outerjoin(
            ProposalParticipant,
            Attendance.proposal_participant_id
            == ProposalParticipant.proposal_participant_id,
        )
        .outerjoin(Person, ProposalParticipant.person_id == Person.person_id)
        .outerjoin(
            attendance_participant,
            Attendance.participant_id == attendance_participant.participant_id,
        )
        .outerjoin(
            legacy_participant,
            Person.legacy_participant_id == legacy_participant.participant_id,
        )
        .where(
            Attendance.attended == True,  # noqa: E712
            ADMServiceType.is_active == True,  # noqa: E712
            ADMServiceType.proposal_id == ActivitySession.proposal_id,
        )
    )
    attendance_stmt = _apply_activity_session_filters(
        attendance_stmt,
        proposal_ids=proposal_ids,
        year=year,
        start_date=start_date,
        end_date=end_date,
    )
    attendance_rows = db.execute(attendance_stmt).all()

    attendance_by_service_type: dict[int, int] = {}
    unique_people_by_service_type: dict[int, set[tuple[str, int]]] = {}
    participant_profiles: dict[int, tuple[date | None, str | None, str | None, str | None]] = {}
    for attendance_row in attendance_rows:
        (
            _,
            participant_id,
            person_id,
            legacy_participant_id,
            service_type_id,
            attendance_profile_id,
            attendance_birth_date,
            attendance_gender,
            attendance_vca,
            attendance_family_composition,
            legacy_profile_id,
            legacy_birth_date,
            legacy_gender,
            legacy_vca,
            legacy_family_composition,
        ) = attendance_row
        normalized_service_type_id = int(service_type_id)
        identity: tuple[str, int] | None = None
        if participant_id is not None:
            identity = ("participant", int(participant_id))
        elif legacy_participant_id is not None:
            identity = ("participant", int(legacy_participant_id))
        elif person_id is not None:
            identity = ("person", int(person_id))

        attendance_by_service_type[normalized_service_type_id] = (
            attendance_by_service_type.get(normalized_service_type_id, 0) + 1
        )
        if identity is not None:
            unique_people_by_service_type.setdefault(
                normalized_service_type_id,
                set(),
            ).add(identity)

        if attendance_profile_id is not None:
            participant_profiles[int(attendance_profile_id)] = (
                attendance_birth_date,
                attendance_gender,
                attendance_vca,
                attendance_family_composition,
            )
        elif legacy_profile_id is not None:
            participant_profiles.setdefault(
                int(legacy_profile_id),
                (
                    legacy_birth_date,
                    legacy_gender,
                    legacy_vca,
                    legacy_family_composition,
                ),
            )

    sociodemographic_summary = {
        key: {"label": label, "f": 0, "m": 0, "total": 0, "vca": 0}
        for key, label in _ADM_AGE_BUCKETS
    }
    raw_family_catalog_labels = db.execute(
        select(CatalogOption.label)
        .join(
            CatalogType,
            CatalogType.catalog_type_id == CatalogOption.catalog_type_id,
        )
        .where(
            CatalogType.key == "composicion_familiar",
            CatalogOption.is_active == True,  # noqa: E712
        )
        .order_by(CatalogOption.sort_order, CatalogOption.label)
    ).scalars().all()
    family_catalog_labels = []
    for raw_label in raw_family_catalog_labels:
        label = str(raw_label).strip()
        if label and label not in family_catalog_labels:
            family_catalog_labels.append(label)
    family_counts = {label: 0 for label in family_catalog_labels}

    for birth_date, gender, vca, family_composition in participant_profiles.values():
        bucket = _adm_age_bucket(_age_on_date(birth_date, reference_date))
        if bucket is not None:
            normalized_gender = str(gender).strip().upper() if gender is not None else ""
            normalized_vca = str(vca).strip().upper() if vca is not None else ""
            if normalized_gender.startswith("F"):
                sociodemographic_summary[bucket]["f"] += 1
            elif normalized_gender.startswith("M"):
                sociodemographic_summary[bucket]["m"] += 1
            sociodemographic_summary[bucket]["total"] += 1
            if normalized_vca == "SI":
                sociodemographic_summary[bucket]["vca"] += 1

        family_label = (
            str(family_composition).strip()
            if family_composition is not None
            else ""
        ) or "No especificado"
        family_counts[family_label] = family_counts.get(family_label, 0) + 1

    total_unique_people = len(participant_profiles)
    sociodemographic_rows = []
    sociodemographic_total = {"f": 0, "m": 0, "total": 0, "vca": 0}
    for key, label in _ADM_AGE_BUCKETS:
        summary = sociodemographic_summary[key]
        sociodemographic_rows.append(
            {
                "label": label,
                "f": summary["f"],
                "m": summary["m"],
                "total": summary["total"],
                "percent": (
                    round((summary["total"] / total_unique_people) * 100, 2)
                    if total_unique_people
                    else 0
                ),
                "vca": summary["vca"],
            }
        )
        for field in sociodemographic_total:
            sociodemographic_total[field] += summary[field]

    catalog_label_set = set(family_catalog_labels)
    additional_family_labels = sorted(
        (label for label in family_counts if label not in catalog_label_set),
        key=str.casefold,
    )
    family_rows = [
        {"label": label, "count": family_counts[label]}
        for label in [*family_catalog_labels, *additional_family_labels]
    ]

    service_rows = []
    for service_type in service_types:
        service_type_id = int(service_type.adm_service_type_id)
        service_rows.append(
            {
                "service_type_name": str(service_type.name).strip() or "Sin nombre",
                "services_count": len(sessions_by_service_type.get(service_type_id, set())),
                "duplicates": attendance_by_service_type.get(service_type_id, 0),
                "unique_participants": len(
                    unique_people_by_service_type.get(service_type_id, set())
                ),
            }
        )

    return {
        "summary": {
            "services": sum(row["services_count"] for row in service_rows),
            "duplicates": sum(row["duplicates"] for row in service_rows),
            "unique_participants": sum(
                row["unique_participants"] for row in service_rows
            ),
            "service_types": len(service_rows),
        },
        "service_rows": service_rows,
        "sociodemographic_rows": sociodemographic_rows,
        "sociodemographic_total": sociodemographic_total,
        "family_rows": family_rows,
        "family_total": sum(family_counts.values()),
    }


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
            Participant.is_head_of_household,
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
        .outerjoin(Residential, Participant.residential_id == Residential.residential_id)
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
        household_heads_count,
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
    adm_summary = _faro_adm_summary(
        db,
        proposal_ids=normalized_proposal_ids,
        year=normalized_year,
        start_date=normalized_start_date,
        end_date=normalized_end_date,
        reference_date=reference_date,
    )

    return _no_store_json(
        {
            "real": {
                "activities": activities_count,
                "people": people_count,
                "duplicates": additional_attendances_count,
                "towns": towns_count,
                "age": age_buckets,
                "household_heads": household_heads_count,
                "education": education_buckets,
                "grades": subject_grade_averages,
                "pregnancy": pregnancy_summary,
                "towns_by_municipality": towns_by_municipality,
                "adm": adm_summary,
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
