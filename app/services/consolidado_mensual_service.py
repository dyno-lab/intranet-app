from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.helpers.reports import build_period_filter, describe_period
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.proposal_report_program import ProposalReportProgram
from app.models.residential import Residential
from app.models.user import User
from app.services.report_programs import (
    program_display_name,
    resolve_effective_program_activity_code_ids,
)


AGE_BUCKETS = [
    ("under_5", "Menos de 5 años", lambda age: age is not None and age < 5),
    ("6_7", "6 - 7 años", lambda age: age is not None and 6 <= age <= 7),
    ("8_10", "8 - 10 años", lambda age: age is not None and 8 <= age <= 10),
    ("11_15", "11 - 15 años", lambda age: age is not None and 11 <= age <= 15),
    ("16_21", "16 - 21 años", lambda age: age is not None and 16 <= age <= 21),
    ("22_59", "22 - 59 años", lambda age: age is not None and 22 <= age <= 59),
    ("60_plus", "60 años en adelante", lambda age: age is not None and age >= 60),
]

DEFAULT_PROGRAMS = [
    {"code": "1-A", "label": "Programa 1-A", "tokens": ("1A", "1-A")},
    {"code": "2-B", "label": "Programa 2-B", "tokens": ("2B", "2-B")},
    {"code": "3-C", "label": "Programa 3-C", "tokens": ("3C", "3-C")},
    {"code": "4-D", "label": "Programa 4-D", "tokens": ("4D", "4-D")},
]

OFFICIAL_RESIDENTIAL_ORDER = [
    "aristides chavier",
    "pedro j. rosaly",
    "juan ponce de leon",
    "ernesto ramos antonini",
    "rafael lopez nussa",
    "la ceiba",
    "leonardo santiago",
    "villa del parque",
    "brisas del mar",
    "bella vista",
    "valles de guayama",
    "jardines de guamani",
    "fernando calimano",
    "san antonio carioca",
    "el carmen",
    "manuel hernandez rosa",
    "rafael hernandez",
    "columbus landing",
]

OFFICIAL_MUNICIPALITY_ORDER = ["Ponce", "Juana Díaz", "Salinas", "Guayama", "Mayaguez"]

MONTH_NAMES = {
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


@dataclass(frozen=True)
class ProgramDefinition:
    code: str
    label: str
    activity_code_ids: set[int]
    tokens: tuple[str, ...] = ()


def _empty_gender_counts() -> dict[str, int]:
    return {"F": 0, "M": 0, "total": 0}


def _empty_bucket_rows() -> dict[str, dict[str, Any]]:
    return {
        key: {"key": key, "label": label, "F": 0, "M": 0, "total": 0}
        for key, label, _ in AGE_BUCKETS
    }


def _calc_age_at(dob: date | None, reference_date: date) -> int | None:
    if not dob:
        return None
    return reference_date.year - dob.year - ((reference_date.month, reference_date.day) < (dob.month, dob.day))


def _bucket_key_for_age(age: int | None) -> str | None:
    for key, _label, predicate in AGE_BUCKETS:
        if predicate(age):
            return key
    return None


def _normalize_gender(value: str | None) -> str:
    normalized = (value or "").strip().upper()
    if normalized.startswith("F"):
        return "F"
    if normalized.startswith("M"):
        return "M"
    return ""


def _sort_key_text(value: str | None) -> str:
    replacements = str.maketrans("áéíóúÁÉÍÓÚñÑ", "aeiouAEIOUnN")
    return (value or "").translate(replacements).strip().lower()


def _official_residential_sort_key(residential: Residential) -> tuple[int, str]:
    normalized_name = _sort_key_text(residential.name)
    try:
        return (OFFICIAL_RESIDENTIAL_ORDER.index(normalized_name), normalized_name)
    except ValueError:
        return (999, normalized_name)


def _program_definitions(db: Session, proposal_id: int | None) -> list[ProgramDefinition]:
    definitions: list[ProgramDefinition] = []

    if proposal_id:
        programs = db.execute(
            select(ProposalReportProgram)
            .where(
                ProposalReportProgram.proposal_id == proposal_id,
                ProposalReportProgram.is_active == True,  # noqa: E712
            )
            .order_by(ProposalReportProgram.sort_order, ProposalReportProgram.code)
        ).scalars().all()
        for program in programs:
            definitions.append(
                ProgramDefinition(
                    code=program.code,
                    label=program_display_name(program),
                    activity_code_ids=resolve_effective_program_activity_code_ids(db, program.program_id),
                )
            )

    if definitions:
        return definitions

    return [
        ProgramDefinition(
            code=item["code"],
            label=item["label"],
            activity_code_ids=set(),
            tokens=item["tokens"],
        )
        for item in DEFAULT_PROGRAMS
    ]


def _resolve_program_key(
    activity_code_id: int | None,
    activity_code: str | None,
    definitions: list[ProgramDefinition],
) -> str:
    for definition in definitions:
        if activity_code_id in definition.activity_code_ids:
            return definition.code

    normalized_code = (activity_code or "").upper().replace(" ", "")
    for definition in definitions:
        for token in definition.tokens:
            if token.upper().replace(" ", "") in normalized_code:
                return definition.code
    return "SIN_PROGRAMA"


def _display_rq_code(value: str | None) -> str:
    text = (value or "").strip()
    return text[2:].strip() if text.upper().startswith("RQ") else text


def _selected_residentials(db: Session, residential_id: int | None) -> list[Residential]:
    stmt = select(Residential).where(Residential.is_active == True).order_by(Residential.municipality, Residential.name)  # noqa: E712
    if residential_id:
        stmt = stmt.where(Residential.residential_id == residential_id)
    return sorted(db.execute(stmt).scalars().all(), key=_official_residential_sort_key)


def build_consolidado_mensual_global(
    db: Session,
    *,
    month: int | None,
    year: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    proposal_id: int | None = None,
    residential_id: int | None = None,
    current_user: User | None = None,
) -> dict[str, Any]:
    """Build the monthly global consolidated report from SQL Server data only.

    The legacy Excel/PDF is intentionally not read here; it is only a visual
    reference for templates and future audit comparisons.
    """
    period = build_period_filter(period_type, month, year, start_date, end_date)
    proposal = db.get(Proposal, proposal_id) if proposal_id else None
    # Preparado para formatos futuros por propuesta sin cambiar el contrato del reporte.
    # Si más adelante se agrega una columna/atributo en Proposal, este valor podrá
    # seleccionar otra plantilla PDF sin reescribir el cálculo SQL.
    report_format_key = getattr(proposal, "consolidado_format_key", None) or "avp_2025_2026"
    residentials = _selected_residentials(db, residential_id)
    residential_by_id = {residential.residential_id: residential for residential in residentials}
    programs = _program_definitions(db, proposal_id)
    program_labels = {program.code: program.label for program in programs}
    program_order = [program.code for program in programs] + ["SIN_PROGRAMA"]
    program_labels.setdefault("SIN_PROGRAMA", "Sin programa configurado")

    rows_by_residential: dict[int, dict[str, Any]] = {}
    for residential in residentials:
        rows_by_residential[residential.residential_id] = {
            "residential_id": residential.residential_id,
            "code": residential.code,
            "residential_name": residential.name,
            "municipality": residential.municipality,
            "rq_code": _display_rq_code(residential.rq_code),
            "programs": {
                code: {
                    "code": code,
                    "label": program_labels[code],
                    "unique_participants": 0,
                    "attendances": 0,
                    "gender": _empty_gender_counts(),
                    "age_rows": _empty_bucket_rows(),
                    "_unique_ids": set(),
                }
                for code in program_order
            },
            "age_rows": _empty_bucket_rows(),
            "gender": _empty_gender_counts(),
            "attendance_age_rows": _empty_bucket_rows(),
            "attendance_gender": _empty_gender_counts(),
            "unique_participants": 0,
            "attendances": 0,
            "_unique_ids": set(),
        }

    stmt = (
        select(ActivitySession, Attendance, Participant, ActivityCode, User, Residential)
        .join(Attendance, Attendance.session_id == ActivitySession.session_id)
        .join(Participant, Participant.participant_id == Attendance.participant_id)
        .join(ActivityCode, ActivityCode.activity_code_id == ActivitySession.activity_code_id)
        .outerjoin(User, User.user_id == ActivitySession.created_by_user_id)
        .outerjoin(Residential, Residential.residential_id == User.residential_id)
        .where(
            Attendance.attended == True,  # noqa: E712
        )
    )
    if period["is_custom"]:
        stmt = stmt.where(
            ActivitySession.session_date >= period["start_date"],
            ActivitySession.session_date <= period["end_date"],
        )
    else:
        stmt = stmt.where(
            extract("month", ActivitySession.session_date) == period["month"],
            extract("year", ActivitySession.session_date) == period["year"],
        )
    if proposal_id:
        stmt = stmt.where(ActivitySession.proposal_id == proposal_id)
    if residential_id:
        stmt = stmt.where(Residential.residential_id == residential_id)

    for session, attendance, participant, activity_code, owner, residential in db.execute(stmt).all():
        if not residential or residential.residential_id not in rows_by_residential:
            continue
        residential_row = rows_by_residential[residential.residential_id]
        program_key = _resolve_program_key(session.activity_code_id, activity_code.code, programs)
        program_row = residential_row["programs"].setdefault(
            program_key,
            {
                "code": program_key,
                "label": program_labels.get(program_key, program_key),
                "unique_participants": 0,
                "attendances": 0,
                "gender": _empty_gender_counts(),
                "age_rows": _empty_bucket_rows(),
                "_unique_ids": set(),
            },
        )

        gender = _normalize_gender(participant.genero)
        age = _calc_age_at(participant.fecha_nacimiento, session.session_date) if participant.fecha_nacimiento else None
        bucket_key = _bucket_key_for_age(age)

        residential_row["attendances"] += 1
        program_row["attendances"] += 1
        if gender:
            residential_row["attendance_gender"][gender] += 1
            residential_row["attendance_gender"]["total"] += 1
        if bucket_key and gender:
            residential_row["attendance_age_rows"][bucket_key][gender] += 1
            residential_row["attendance_age_rows"][bucket_key]["total"] += 1

        if participant.participant_id not in residential_row["_unique_ids"]:
            residential_row["_unique_ids"].add(participant.participant_id)
            residential_row["unique_participants"] += 1
            if gender:
                residential_row["gender"][gender] += 1
                residential_row["gender"]["total"] += 1
            if bucket_key and gender:
                residential_row["age_rows"][bucket_key][gender] += 1
                residential_row["age_rows"][bucket_key]["total"] += 1

        if participant.participant_id not in program_row["_unique_ids"]:
            program_row["_unique_ids"].add(participant.participant_id)
            program_row["unique_participants"] += 1
            if gender:
                program_row["gender"][gender] += 1
                program_row["gender"]["total"] += 1
            if bucket_key and gender:
                program_row["age_rows"][bucket_key][gender] += 1
                program_row["age_rows"][bucket_key]["total"] += 1

    global_totals = {
        "unique_participants": 0,
        "attendances": 0,
        "gender": _empty_gender_counts(),
        "attendance_gender": _empty_gender_counts(),
        "age_rows": _empty_bucket_rows(),
        "attendance_age_rows": _empty_bucket_rows(),
        "programs": {
            code: {
                "code": code,
                "label": program_labels[code],
                "unique_participants": 0,
                "attendances": 0,
                "gender": _empty_gender_counts(),
            }
            for code in program_order
        },
    }

    report_rows = []
    for row in rows_by_residential.values():
        row["programs"] = [program for program in row["programs"].values() if program["unique_participants"] or program["attendances"] or program["code"] != "SIN_PROGRAMA"]
        for program in row["programs"]:
            program.pop("_unique_ids", None)
        row["age_rows"] = list(row["age_rows"].values())
        row["attendance_age_rows"] = list(row["attendance_age_rows"].values())
        row.pop("_unique_ids", None)
        report_rows.append(row)

        global_totals["unique_participants"] += row["unique_participants"]
        global_totals["attendances"] += row["attendances"]
        for gender in ("F", "M", "total"):
            global_totals["gender"][gender] += row["gender"].get(gender, 0)
            global_totals["attendance_gender"][gender] += row["attendance_gender"].get(gender, 0)
        for age_row in row["age_rows"]:
            global_age_row = global_totals["age_rows"][age_row["key"]]
            global_age_row["F"] += age_row["F"]
            global_age_row["M"] += age_row["M"]
            global_age_row["total"] += age_row["total"]
        for age_row in row["attendance_age_rows"]:
            global_age_row = global_totals["attendance_age_rows"][age_row["key"]]
            global_age_row["F"] += age_row["F"]
            global_age_row["M"] += age_row["M"]
            global_age_row["total"] += age_row["total"]
        for program in row["programs"]:
            total_program = global_totals["programs"].setdefault(
                program["code"],
                {
                    "code": program["code"],
                    "label": program["label"],
                    "unique_participants": 0,
                    "attendances": 0,
                    "gender": _empty_gender_counts(),
                },
            )
            total_program["unique_participants"] += program["unique_participants"]
            total_program["attendances"] += program["attendances"]
            for gender in ("F", "M", "total"):
                total_program["gender"][gender] += program["gender"].get(gender, 0)

    global_totals["age_rows"] = list(global_totals["age_rows"].values())
    global_totals["attendance_age_rows"] = list(global_totals["attendance_age_rows"].values())
    global_totals["programs"] = list(global_totals["programs"].values())

    municipality_names_raw = {row["municipality"] for row in report_rows if row.get("municipality")}
    municipality_names = [name for name in OFFICIAL_MUNICIPALITY_ORDER if name in municipality_names_raw]
    municipality_names.extend(sorted(municipality_names_raw - set(municipality_names)))
    residential_names = [row["residential_name"] for row in report_rows if row.get("residential_name")]

    return {
        "title": "Consolidado Mensual Global",
        "month": period["month"],
        "year": period["year"],
        "month_label": MONTH_NAMES.get(period["month"], str(period["month"] or "")),
        "period_label": describe_period(period, MONTH_NAMES),
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "proposal": proposal,
        "report_format_key": report_format_key,
        "pdf_template_name": "ui/admin/consolidado_mensual_global_pdf.html",
        "selected_proposal_id": proposal_id,
        "selected_residential_id": residential_id,
        "is_all_residentials": residential_id is None,
        "generated_on": date.today(),
        "generated_by": current_user.username if current_user else "",
        "authorized_name": "Christian X. Ramírez Morales",
        "global_residential_names": ", ".join(residential_names),
        "global_municipalities": ", ".join(municipality_names),
        "revision_label": "Rev.15/agosto/2019 CRM",
        "rows": report_rows,
        "totals": global_totals,
        "program_labels": program_labels,
        "legacy_reference_note": "Calculado desde SQL Server; no usa archivos .xlsm ni Excel como motor de cálculo.",
    }


def build_validation_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in context.get("rows", []):
        rows.append({
            "residential_name": row["residential_name"],
            "municipality": row["municipality"],
            "rq_code": row["rq_code"],
            "legacy_total": None,
            "intranet_total": row["unique_participants"],
            "difference": None,
            "observations": "Pendiente cargar valor histórico del Excel/PDF anterior.",
        })
    return rows
