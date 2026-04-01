from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, extract, func, distinct
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.user import User
from app.models.residential import Residential
from app.models.activity_code import ActivityCode
from app.models.employee import Employee
from app.models.vca_column import VCAColumn
from app.models.vca_column_activity_code import VCAColumnActivityCode
from app.models.school_dropout_report import SchoolDropoutReport
from app.models.school_dropout_report_item import SchoolDropoutReportItem
from app.models.pregnancy_report import PregnancyReport
from app.models.pregnancy_report_item import PregnancyReportItem
from app.models.school_grade_report import SchoolGradeReport
from app.models.school_grade_report_item import SchoolGradeReportItem
from app.models.visit_activity_mapping import VisitActivityMapping
from app.models.visit_report import VisitReport
from app.models.visit_report_referral import VisitReportReferral
from app.models.proposal_report_program import ProposalReportProgram
from app.models.proposal_report_program_activity import ProposalReportProgramActivity
from app.models.proposal_report_program_activity_code import ProposalReportProgramActivityCode
from app.models.proposal_report_program_population import ProposalReportProgramPopulation
from app.models.proposal_report_program_population_activity_code import ProposalReportProgramPopulationActivityCode
from app.helpers.report_context import (
    base_reports_context as _base_reports_context,
    municipality_from_user as _municipality_from_user,
    residential_from_user as _residential_from_user,
    resolve_reporting_location as _resolve_reporting_location,
    resolve_reporting_scope as _resolve_reporting_scope,
    rq_from_user as _rq_from_user,
)
from app.helpers.reports import (
    AGE_BUCKETS,
    build_percentage_breakdown as _build_percentage_breakdown,
    build_period_filter as _build_period_filter,
    calc_age as _calc_age,
    chunk_rows as _chunk_rows,
    describe_period as _describe_period,
    get_age_bucket as _get_age_bucket,
    grade_letter_from_average as _grade_letter_from_average,
    normalize_text as _normalize_text,
    notes_age_bucket as _notes_age_bucket,
    parse_optional_date as _parse_optional_date,
    parse_optional_int as _parse_optional_int,
    period_filename_suffix as _period_filename_suffix,
    summarize_participants_by_age_and_gender as _summarize_participants_by_age_and_gender,
)
from app.services.report_programs import (
    program_display_name as _program_report_display_name,
    program_uses_population_structure as _program_uses_population_structure,
    resolve_effective_program_activity_code_ids as _resolve_effective_program_activity_code_ids,
    resolve_effective_program_population_blocks as _resolve_effective_program_population_blocks,
)
from app.services.visits import (
    resolve_report_scope,
    get_or_create_visit_report,
    replace_visit_report_referrals,
    delete_visit_reports_and_referrals,
    delete_visit_referrals_only,
    get_visit_report,
    get_visit_reports,
    build_visits_report_payload,
)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

MONTH_OPTIONS = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]

FIXED_SIGNATURES = [
    {"name": "Karla Santiago Pérez", "title": "Coordinadora Educativa"},
    {"name": "Alice E. Beard García", "title": "Coordinadora Prevención"},
    {"name": "Annjellyn Arroyo Pagán", "title": "Coordinadora de Arte, Cultura y Recreación"},
    {"name": "Josmary Cosme", "title": "Coordinadora Desarrollo Económico y Servicio al Residente"},
]

ROWS_PER_BONAFIDE_PAGE = 26

def _apply_session_period_filter(stmt, period: dict):
    if period["is_custom"]:
        return stmt.where(
            ActivitySession.session_date >= period["start_date"],
            ActivitySession.session_date <= period["end_date"],
        )
    if period["month"] and period["year"]:
        return stmt.where(
            extract("month", ActivitySession.session_date) == period["month"],
            extract("year", ActivitySession.session_date) == period["year"],
        )
    return stmt


def _build_bonafide_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)

    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    proposals = base_context["proposals"]
    report_users = base_context["report_users"]
    year_options = base_context["year_options"]
    month_lookup = base_context["month_lookup"]
    user_residential_map = base_context["user_residential_map"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    rows = []
    municipality = None
    residential_name = None
    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        if is_global:
            residential_name = "Global"
            municipality = "Todos"
        else:
            residential_name = _residential_from_user(selected_user)
            municipality = _municipality_from_user(selected_user)

        stmt = (
            select(Participant)
            .join(Attendance, Attendance.participant_id == Participant.participant_id)
            .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
            .where(
                Attendance.attended == True,  # noqa: E712
                ActivitySession.proposal_id == proposal_id,
            )
        )
        stmt = _apply_session_period_filter(stmt, period)
        stmt = stmt.distinct().order_by(Participant.edificio, Participant.apart, Participant.apellido_paterno, Participant.nombre)
        if not is_global:
            stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
        participants = db.execute(stmt).scalars().all()

        for idx, participant in enumerate(participants, start=1):
            gender = _normalize_text(participant.genero).upper()
            first_time = _normalize_text(getattr(participant, "primera_vez", None)).upper()
            display_name = f"{participant.nombre} {participant.apellido_paterno} {participant.apellido_materno or ''}".strip()
            if first_time == "SI":
                display_name = f"{display_name} *"
            rows.append({
                "index": idx,
                "expediente": participant.expediente_num,
                "nombre": display_name,
                "f": "X" if gender.startswith("F") else "",
                "m": "X" if gender.startswith("M") else "",
                "edad": _calc_age(participant.fecha_nacimiento) or "",
                "edificio": participant.edificio or "",
                "apartamento": participant.apart or "",
            })

    return {
        "proposals": proposals,
        "report_users": report_users,
        "user_residential_map": user_residential_map,
        "month_options": MONTH_OPTIONS,
        "month_lookup": month_lookup,
        "year_options": year_options,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "municipality": municipality,
        "rows": rows,
        "pages": _chunk_rows(rows, ROWS_PER_BONAFIDE_PAGE),
        "rows_per_page": ROWS_PER_BONAFIDE_PAGE,
        "signatures": FIXED_SIGNATURES,
    }


REPORT_OPTIONS = [
    {"value": "bonafide", "label": "Bonafide"},
    {"value": "no-duplicado", "label": "No Duplicado"},
    {"value": "duplicados", "label": "Duplicados"},
    {"value": "desercion-escolar", "label": "Deserción Escolar"},
    {"value": "embarazo", "label": "Embarazo"},
    {"value": "notas", "label": "Notas"},
    {"value": "visitas", "label": "Visitas"},
    {"value": "por-programa", "label": "Informes por programa"},
    {"value": "hoja-cotejo", "label": "Hoja de Cotejo"},
    {"value": "vca", "label": "Informe VCA"},
    {"value": "todos", "label": "Todos"},
]

PERIOD_TYPE_OPTIONS = [
    {"value": "monthly", "label": "Mensual"},
    {"value": "quarterly", "label": "Trimestral"},
    {"value": "annual", "label": "Anual"},
    {"value": "custom", "label": "Personalizado"},
]


@router.get("/", response_class=HTMLResponse)
def reports_home(
    request: Request,
    report_key: str = "bonafide",
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    output: str = "screen",
    period_type: str = "monthly",
    authorized_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    context.update(
        {
            "request": request,
            "current_user": current_user,
            "report_options": REPORT_OPTIONS,
            "period_type_options": PERIOD_TYPE_OPTIONS,
            "selected_report_key": report_key,
            "selected_proposal_id": proposal_id,
            "selected_month": month,
            "selected_year": year,
            "selected_employee_id": employee_id,
            "selected_output": output,
            "selected_period_type": period_type,
            "authorized_name": (authorized_name or "").strip(),
            "selected_start_date": start_date or "",
            "selected_end_date": end_date or "",
        }
    )
    return templates.TemplateResponse("ui/reports/index.html", context)


@router.get("/run")
def reports_run(
    report_key: str,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    output: str = "screen",
    period_type: str = "monthly",
    authorized_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    month_value = int(month) if (month or "").strip() else None
    year_value = int(year) if (year or "").strip() else None
    period_query = f"&period_type={period_type}&start_date={start_date or ''}&end_date={end_date or ''}"

    if report_key == "bonafide":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/bonafide/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/bonafide/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/bonafide?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    if report_key == "no-duplicado":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/no-duplicado/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/no-duplicado/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/no-duplicado?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
            status_code=303,
        )

    if report_key == "duplicados":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/duplicado/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/duplicado/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/duplicado?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
            status_code=303,
        )

    if report_key == "vca":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/vca/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/vca/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/vca?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    if report_key == "por-programa":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/por-programa/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/por-programa/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/por-programa?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
            status_code=303,
        )

    if report_key == "hoja-cotejo":
        return RedirectResponse(
            f"/ui/reports/hoja-cotejo?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    if report_key == "desercion-escolar":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/desercion-escolar/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/desercion-escolar/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/desercion-escolar?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    if report_key == "embarazo":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/embarazo/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/embarazo/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/embarazo?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    if report_key == "notas":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/notas/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/notas/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/notas?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    if report_key == "visitas":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/visitas/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/visitas/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/visitas?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
            status_code=303,
        )

    return RedirectResponse(
        f"/ui/reports/?report_key={report_key}&proposal_id={proposal_id or ''}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id or ''}&output={output}&period_type={period_type}&authorized_name={authorized_name or ''}&start_date={start_date or ''}&end_date={end_date or ''}",
        status_code=303,
    )


def _build_vca_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)
    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    month_lookup = base_context["month_lookup"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    columns = []
    rows = []
    residential_name = None
    total_people = 0

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        proposal = db.get(Proposal, proposal_id)
        if proposal:
            columns = db.execute(
                select(VCAColumn)
                .where(VCAColumn.proposal_id == proposal_id, VCAColumn.is_active == True)  # noqa: E712
                .order_by(VCAColumn.sort_order, VCAColumn.name)
            ).scalars().all()

            mapping_rows = db.execute(
                select(VCAColumnActivityCode, ActivityCode, VCAColumn)
                .join(ActivityCode, ActivityCode.activity_code_id == VCAColumnActivityCode.activity_code_id)
                .join(VCAColumn, VCAColumn.vca_column_id == VCAColumnActivityCode.vca_column_id)
                .where(VCAColumn.proposal_id == proposal_id, VCAColumn.is_active == True)  # noqa: E712
            ).all()
            activity_to_column = {activity.activity_code_id: column.vca_column_id for _, activity, column in mapping_rows}

            participant_stmt = (
                select(Participant)
                .join(Attendance, Attendance.participant_id == Participant.participant_id)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                    func.upper(func.ltrim(func.rtrim(func.isnull(Participant.vca, "")))) == "SI",
                )
            )
            participant_stmt = _apply_session_period_filter(participant_stmt, period)
            if is_global:
                residential_name = "Global"
            else:
                participant_stmt = participant_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
                residential_name = _residential_from_user(selected_user)
            participants = participant_stmt.distinct().order_by(Participant.apellido_paterno, Participant.nombre)
            participant_rows = db.execute(participants).scalars().all()

            attendance_stmt = (
                select(Attendance.participant_id, ActivitySession.activity_code_id)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                )
            )
            attendance_stmt = _apply_session_period_filter(attendance_stmt, period)
            if not is_global:
                attendance_stmt = attendance_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
            attendance_rows = db.execute(attendance_stmt).all()

            counts: dict[int, dict[int, int]] = {}
            for participant_id, activity_code_id in attendance_rows:
                column_id = activity_to_column.get(activity_code_id)
                if not column_id:
                    continue
                counts.setdefault(participant_id, {})
                counts[participant_id][column_id] = counts[participant_id].get(column_id, 0) + 1

            for participant in participant_rows:
                row_values = {column.vca_column_id: counts.get(participant.participant_id, {}).get(column.vca_column_id, "") for column in columns}
                if not any(value != "" for value in row_values.values()):
                    continue
                rows.append({
                    "participant_id": participant.participant_id,
                    "expediente": participant.expediente_num or "",
                    "nombre": f"{participant.nombre} {participant.apellido_paterno} {participant.apellido_materno or ''}".strip(),
                    "genero": participant.genero or "",
                    "edad": _calc_age(participant.fecha_nacimiento) or "",
                    "column_values": row_values,
                })
            total_people = len(rows)

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "columns": columns,
        "rows": rows,
        "total_people": total_people,
    }


def _build_school_dropout_summary_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)

    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    month_lookup = base_context["month_lookup"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    grade_columns = ["SC", "EE", "K", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
    rows = []
    total = {
        "recruited": 0,
        "f": 0,
        "m": 0,
        "tutoring": 0,
        "school": 0,
        "report_10": 0,
        "report_20": 0,
        "report_30": 0,
        "report_40": 0,
        "grades": {grade: 0 for grade in grade_columns},
    }
    residential_name = None

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        stmt = (
            select(SchoolDropoutReportItem, SchoolDropoutReport, Participant, User, Residential)
            .join(SchoolDropoutReport, SchoolDropoutReport.report_id == SchoolDropoutReportItem.report_id)
            .join(Participant, Participant.participant_id == SchoolDropoutReportItem.participant_id)
            .join(User, User.user_id == SchoolDropoutReport.created_by_user_id)
            .outerjoin(Residential, Residential.residential_id == User.residential_id)
            .where(SchoolDropoutReport.proposal_id == proposal_id)
        )

        if period["is_custom"]:
            stmt = stmt.where(
                func.datefromparts(SchoolDropoutReport.report_year, SchoolDropoutReport.report_month, 1) >= period["start_date"],
                func.datefromparts(SchoolDropoutReport.report_year, SchoolDropoutReport.report_month, 1) <= period["end_date"],
            )
        elif period["month"] and period["year"]:
            stmt = stmt.where(
                SchoolDropoutReport.report_month == period["month"],
                SchoolDropoutReport.report_year == period["year"],
            )

        if is_global:
            residential_name = "Global"
        else:
            stmt = stmt.where(SchoolDropoutReport.created_by_user_id == selected_user.user_id)
            residential_name = _residential_from_user(selected_user)

        grouped: dict[str, dict] = {}
        participant_snapshots: dict[tuple[str, int], dict] = {}

        for item, report, participant, report_user, residential in db.execute(stmt).all():
            residential_label = _normalize_text(residential.name if residential else _residential_from_user(report_user)) or "Sin residencial"
            grouped.setdefault(
                residential_label,
                {
                    "residential_name": residential_label,
                    "recruited": 0,
                    "f": 0,
                    "m": 0,
                    "tutoring": 0,
                    "school": 0,
                    "report_10": 0,
                    "report_20": 0,
                    "report_30": 0,
                    "report_40": 0,
                    "grades": {grade: 0 for grade in grade_columns},
                },
            )

            key = (residential_label, participant.participant_id)
            snapshot = participant_snapshots.get(key)
            report_sort = (report.report_year or 0, report.report_month or 0, report.report_id or 0)

            if not snapshot:
                snapshot = {
                    "residential_name": residential_label,
                    "participant_id": participant.participant_id,
                    "gender": _normalize_text(participant.genero).upper(),
                    "current_grade": _normalize_text(item.current_grade).upper(),
                    "attended_tutoring": bool(item.attended_tutoring),
                    "attended_school": bool(item.attended_school),
                    "report_10": bool(item.report_10_weeks),
                    "report_20": bool(item.report_20_weeks),
                    "report_30": bool(item.report_30_weeks),
                    "report_40": bool(item.report_40_weeks),
                    "latest_sort": report_sort,
                }
                participant_snapshots[key] = snapshot
                continue

            snapshot["attended_tutoring"] = snapshot["attended_tutoring"] or bool(item.attended_tutoring)
            snapshot["attended_school"] = snapshot["attended_school"] or bool(item.attended_school)
            snapshot["report_10"] = snapshot["report_10"] or bool(item.report_10_weeks)
            snapshot["report_20"] = snapshot["report_20"] or bool(item.report_20_weeks)
            snapshot["report_30"] = snapshot["report_30"] or bool(item.report_30_weeks)
            snapshot["report_40"] = snapshot["report_40"] or bool(item.report_40_weeks)

            if report_sort >= snapshot["latest_sort"]:
                latest_grade = _normalize_text(item.current_grade).upper()
                if latest_grade:
                    snapshot["current_grade"] = latest_grade
                snapshot["latest_sort"] = report_sort

        for snapshot in participant_snapshots.values():
            bucket = grouped[snapshot["residential_name"]]
            bucket["recruited"] += 1
            total["recruited"] += 1

            gender = snapshot["gender"]
            if gender.startswith("F"):
                bucket["f"] += 1
                total["f"] += 1
            elif gender.startswith("M"):
                bucket["m"] += 1
                total["m"] += 1

            grade_value = snapshot["current_grade"]
            if grade_value in bucket["grades"]:
                bucket["grades"][grade_value] += 1
                total["grades"][grade_value] += 1

            if snapshot["attended_tutoring"]:
                bucket["tutoring"] += 1
                total["tutoring"] += 1
            if snapshot["attended_school"]:
                bucket["school"] += 1
                total["school"] += 1
            if snapshot["report_10"]:
                bucket["report_10"] += 1
                total["report_10"] += 1
            if snapshot["report_20"]:
                bucket["report_20"] += 1
                total["report_20"] += 1
            if snapshot["report_30"]:
                bucket["report_30"] += 1
                total["report_30"] += 1
            if snapshot["report_40"]:
                bucket["report_40"] += 1
                total["report_40"] += 1

        def with_percentages(row: dict) -> dict:
            recruited = row["recruited"]
            tutoring_pct = round((row["tutoring"] / recruited) * 100, 2) if recruited else 0
            school_pct = round((row["school"] / recruited) * 100, 2) if recruited else 0
            return {
                **row,
                "tutoring_pct": tutoring_pct,
                "school_pct": school_pct,
            }

        rows = [with_percentages(grouped[name]) for name in sorted(grouped.keys())]
        total = with_percentages(total)

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "grade_columns": grade_columns,
        "rows": rows,
        "total": total,
    }


def _build_pregnancy_summary_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)

    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    month_lookup = base_context["month_lookup"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    rows = []
    residential_name = None
    total = {
        "recruited": 0,
        "f": 0,
        "m": 0,
        "pregnant_f": 0,
        "pregnant_m": 0,
        "participation": 0,
        "non_pregnant": 0,
        "prevention_pct": 0,
        "pregnancy_cases": 0,
    }

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        stmt = (
            select(PregnancyReportItem, PregnancyReport, Participant, User, Residential)
            .join(PregnancyReport, PregnancyReport.report_id == PregnancyReportItem.report_id)
            .join(Participant, Participant.participant_id == PregnancyReportItem.participant_id)
            .join(User, User.user_id == PregnancyReport.created_by_user_id)
            .outerjoin(Residential, Residential.residential_id == User.residential_id)
            .where(PregnancyReport.proposal_id == proposal_id)
        )

        if period["is_custom"]:
            stmt = stmt.where(
                func.datefromparts(PregnancyReport.report_year, PregnancyReport.report_month, 1) >= period["start_date"],
                func.datefromparts(PregnancyReport.report_year, PregnancyReport.report_month, 1) <= period["end_date"],
            )
        elif period["month"] and period["year"]:
            stmt = stmt.where(
                PregnancyReport.report_month == period["month"],
                PregnancyReport.report_year == period["year"],
            )

        if is_global:
            residential_name = "Global"
        else:
            stmt = stmt.where(PregnancyReport.created_by_user_id == selected_user.user_id)
            residential_name = _residential_from_user(selected_user)

        grouped: dict[str, dict] = {}
        participant_snapshots: dict[tuple[str, int], dict] = {}

        for item, report, participant, report_user, residential in db.execute(stmt).all():
            residential_label = _normalize_text(residential.name if residential else _residential_from_user(report_user)) or "Sin residencial"
            grouped.setdefault(
                residential_label,
                {
                    "residential_name": residential_label,
                    "recruited": 0,
                    "f": 0,
                    "m": 0,
                    "pregnant_f": 0,
                    "pregnant_m": 0,
                    "participation": 0,
                    "non_pregnant": 0,
                    "prevention_pct": 0,
                    "pregnancy_cases": 0,
                },
            )

            key = (residential_label, participant.participant_id)
            snapshot = participant_snapshots.get(key)
            report_sort = (report.report_year or 0, report.report_month or 0, report.report_id or 0)
            gender = _normalize_text(participant.genero).upper()
            is_female = gender.startswith("F")
            is_male = gender.startswith("M")
            participated = bool(item.participated_workshops)
            pregnant_f = bool(item.is_pregnant and is_female)
            pregnant_m = bool(item.is_pregnant and is_male)

            if not snapshot:
                participant_snapshots[key] = {
                    "residential_name": residential_label,
                    "participant_id": participant.participant_id,
                    "gender": gender,
                    "participated": participated,
                    "pregnant_f": pregnant_f,
                    "pregnant_m": pregnant_m,
                    "latest_sort": report_sort,
                }
                continue

            snapshot["participated"] = snapshot["participated"] or participated
            snapshot["pregnant_f"] = snapshot["pregnant_f"] or pregnant_f
            snapshot["pregnant_m"] = snapshot["pregnant_m"] or pregnant_m
            if report_sort >= snapshot["latest_sort"]:
                snapshot["latest_sort"] = report_sort
                snapshot["gender"] = gender or snapshot["gender"]

        for snapshot in participant_snapshots.values():
            bucket = grouped[snapshot["residential_name"]]
            bucket["recruited"] += 1
            total["recruited"] += 1

            gender = snapshot["gender"]
            if gender.startswith("F"):
                bucket["f"] += 1
                total["f"] += 1
            elif gender.startswith("M"):
                bucket["m"] += 1
                total["m"] += 1

            if snapshot["participated"]:
                bucket["participation"] += 1
                total["participation"] += 1
            if snapshot["pregnant_f"]:
                bucket["pregnant_f"] += 1
                total["pregnant_f"] += 1
            if snapshot["pregnant_m"]:
                bucket["pregnant_m"] += 1
                total["pregnant_m"] += 1

        def finalize(row: dict) -> dict:
            pregnancy_cases = row["pregnant_f"] + row["pregnant_m"]
            participation = row["participation"]
            non_pregnant = max(participation - pregnancy_cases, 0)
            prevention_pct = round((non_pregnant / participation) * 100, 2) if participation else 0
            return {
                **row,
                "pregnancy_cases": pregnancy_cases,
                "non_pregnant": non_pregnant,
                "prevention_pct": prevention_pct,
            }

        rows = [finalize(grouped[name]) for name in sorted(grouped.keys())]
        total = finalize(total)

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "rows": rows,
        "total": total,
        "chart_labels": ["Embarazos", "No embarazos"],
        "chart_values": [total["pregnancy_cases"], total["non_pregnant"]],
    }


def _build_notes_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)
    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    month_lookup = base_context["month_lookup"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    rows = []
    age_labels = ["Menos de 5 años", "5 - 7 años", "8 - 10 años", "11 - 15 años", "16 - 21 años"]
    note_letters = ["A", "B", "C", "D", "F"]
    table_rows = {label: {letter: 0 for letter in note_letters} | {"Especial": 0, "K": 0, "TOTAL": 0} for label in age_labels}
    residential_chart_rows = []
    pie_labels = ["A", "B", "C", "D", "F"]
    pie_values = [0, 0, 0, 0, 0]
    subject_chart = {
        "Español": {letter: 0 for letter in note_letters},
        "Inglés": {letter: 0 for letter in note_letters},
        "Matemáticas": {letter: 0 for letter in note_letters},
        "Ciencias": {letter: 0 for letter in note_letters},
    }
    residential_name = None
    total_row = {letter: 0 for letter in note_letters} | {"Especial": 0, "K": 0, "TOTAL": 0}
    general_chart_segments = []
    subject_chart_cards = []

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        stmt = (
            select(SchoolGradeReportItem, SchoolGradeReport, Participant, User, Residential)
            .join(SchoolGradeReport, SchoolGradeReport.report_id == SchoolGradeReportItem.report_id)
            .join(Participant, Participant.participant_id == SchoolGradeReportItem.participant_id)
            .join(User, User.user_id == SchoolGradeReport.created_by_user_id)
            .outerjoin(Residential, Residential.residential_id == User.residential_id)
            .where(SchoolGradeReport.proposal_id == proposal_id)
        )

        if period["is_custom"]:
            stmt = stmt.where(
                func.datefromparts(SchoolGradeReport.report_year, SchoolGradeReport.report_month, 1) >= period["start_date"],
                func.datefromparts(SchoolGradeReport.report_year, SchoolGradeReport.report_month, 1) <= period["end_date"],
            )
        elif period["month"] and period["year"]:
            stmt = stmt.where(
                SchoolGradeReport.report_month == period["month"],
                SchoolGradeReport.report_year == period["year"],
            )

        if is_global:
            residential_name = "Global"
        else:
            stmt = stmt.where(SchoolGradeReport.created_by_user_id == selected_user.user_id)
            residential_name = _residential_from_user(selected_user)

        participant_snapshots: dict[tuple[str, int], dict] = {}
        for item, report, participant, report_user, residential in db.execute(stmt).all():
            residential_label = _normalize_text(residential.name if residential else _residential_from_user(report_user)) or "Sin residencial"
            key = (residential_label, participant.participant_id)
            report_sort = (report.report_year or 0, report.report_month or 0, report.report_id or 0)
            snapshot = participant_snapshots.get(key)
            current_snapshot = {
                "residential_name": residential_label,
                "participant_id": participant.participant_id,
                "age": _calc_age(participant.fecha_nacimiento),
                "grade_level": _normalize_text(item.grade_level).upper(),
                "is_content_room": bool(item.is_content_room),
                "average_grade": float(item.average_grade) if item.average_grade is not None else None,
                "spanish_grade": float(item.spanish_grade) if item.spanish_grade is not None else None,
                "english_grade": float(item.english_grade) if item.english_grade is not None else None,
                "math_grade": float(item.math_grade) if item.math_grade is not None else None,
                "science_grade": float(item.science_grade) if item.science_grade is not None else None,
                "latest_sort": report_sort,
            }
            if not snapshot or report_sort >= snapshot["latest_sort"]:
                participant_snapshots[key] = current_snapshot

        residential_summary: dict[str, dict] = {}
        for snapshot in participant_snapshots.values():
            age_label = _notes_age_bucket(snapshot["age"])
            if age_label:
                letter = _grade_letter_from_average(snapshot["average_grade"])
                if letter in note_letters:
                    table_rows[age_label][letter] += 1
                    total_row[letter] += 1
                    pie_values[note_letters.index(letter)] += 1

                if snapshot["is_content_room"]:
                    table_rows[age_label]["Especial"] += 1
                    total_row["Especial"] += 1

                if snapshot["grade_level"] == "K":
                    table_rows[age_label]["K"] += 1
                    total_row["K"] += 1

                table_rows[age_label]["TOTAL"] += 1
                total_row["TOTAL"] += 1

            residential_bucket = residential_summary.setdefault(snapshot["residential_name"], {letter: 0 for letter in note_letters})
            avg_letter = _grade_letter_from_average(snapshot["average_grade"])
            if avg_letter in note_letters:
                residential_bucket[avg_letter] += 1

            for subject_name, field_name in [("Español", "spanish_grade"), ("Inglés", "english_grade"), ("Matemáticas", "math_grade"), ("Ciencias", "science_grade")]:
                subject_letter = _grade_letter_from_average(snapshot[field_name])
                if subject_letter in note_letters:
                    subject_chart[subject_name][subject_letter] += 1

        residential_chart_rows = [
            {
                "residential_name": name,
                **counts,
                "total": sum(counts.values()),
                "breakdown": _build_percentage_breakdown(counts, note_letters),
            }
            for name, counts in sorted(residential_summary.items())
        ]
        rows = [{"age_label": label, **table_rows[label]} for label in age_labels]

    general_chart_segments = _build_percentage_breakdown(
        {label: value for label, value in zip(pie_labels, pie_values)},
        pie_labels,
    )
    subject_chart_cards = [
        {
            "subject_name": subject_name,
            "counts": counts,
            "segments": _build_percentage_breakdown(counts, note_letters),
        }
        for subject_name, counts in subject_chart.items()
    ]

    proposal_label = next(
        (f"{proposal.code} - {proposal.name}" for proposal in base_context["proposals"] if proposal.proposal_id == proposal_id),
        "",
    )

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "proposal_label": proposal_label,
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "rows": rows,
        "total_row": total_row,
        "pie_labels": pie_labels,
        "pie_values": pie_values,
        "general_chart_segments": general_chart_segments,
        "residential_chart_rows": residential_chart_rows,
        "subject_chart": subject_chart,
        "subject_chart_cards": subject_chart_cards,
    }


def _build_visits_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)
    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    month_lookup = base_context["month_lookup"]
    user_residential_map = base_context["user_residential_map"]

    scope = resolve_report_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]

    payload = build_visits_report_payload(
        db,
        proposal_id=proposal_id,
        period=period,
        selected_user=selected_user,
        is_global=is_global,
        user_residential_map=user_residential_map,
        residential_name_resolver=_residential_from_user,
        apply_period_filter=_apply_session_period_filter,
    )

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": payload["residential_name"],
        "rows": payload["rows"],
        "summary": payload["summary"],
        "mapped_activity_ids": payload["mapped_activity_ids"],
        "authorized_name": authorized_name or "",
        "visit_report": payload["visit_report"],
        "referral_rows": payload["referral_rows"],
        "referral_count": payload["referral_count"],
        "referral_type_options": ["Interno", "Externo", "Visita Agencia"],
    }


@router.get("/visitas", response_class=HTMLResponse)
def visits_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    msg: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_visits_context(db, current_user, proposal_id, month, year, employee_id, authorized_name=authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user, "msg": msg})
    return templates.TemplateResponse("ui/reports/visitas.html", context)


@router.post("/visitas/referrals/save")
async def visits_report_save_referrals(
    request: Request,
    proposal_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    employee_id: int | None = Form(default=None),
    authorized_name: str | None = Form(default=None),
    referral_count: int = Form(default=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    period_month = month
    period_year = year

    scope = resolve_report_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]

    if not proposal_id or not period_month or not period_year or not (selected_user or is_global):
        return RedirectResponse("/ui/reports/visitas?msg=Error: Debe seleccionar propuesta, periodo y residencial.", status_code=303)

    report_owner_user_id = None if is_global else selected_user.user_id
    visit_report = get_or_create_visit_report(
        db,
        proposal_id=proposal_id,
        report_month=period_month,
        report_year=period_year,
        created_by_user_id=report_owner_user_id,
    )

    form_data = await request.form()
    referral_total = max(0, referral_count)
    referral_payloads = []
    for idx in range(referral_total):
        referral_payloads.append({
            "referral_type": form_data.get(f"referral_type_{idx}"),
            "agency": form_data.get(f"agency_{idx}"),
            "reference_or_purpose": form_data.get(f"reference_or_purpose_{idx}"),
        })

    replace_visit_report_referrals(db, visit_report.report_id, referral_payloads)
    db.commit()

    return RedirectResponse(
        f"/ui/reports/visitas?proposal_id={proposal_id}&month={period_month}&year={period_year}&employee_id={employee_id if employee_id is not None else ''}&authorized_name={authorized_name or ''}&msg=Referidos guardados exitosamente.",
        status_code=303,
    )


@router.post("/visitas/delete")
def visits_report_delete(
    proposal_id: int = Form(...),
    month: int = Form(...),
    year: int = Form(...),
    employee_id: int | None = Form(default=None),
    authorized_name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scope = resolve_report_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]

    if not proposal_id or not month or not year or not (selected_user or is_global):
        return RedirectResponse("/ui/reports/visitas?msg=Error: Contexto inválido para eliminar informe.", status_code=303)

    if is_global:
        reports = get_visit_reports(
            db,
            proposal_id=proposal_id,
            report_month=month,
            report_year=year,
        )
    else:
        report = get_visit_report(
            db,
            proposal_id=proposal_id,
            report_month=month,
            report_year=year,
            created_by_user_id=selected_user.user_id,
        )
        reports = [report] if report else []

    if not reports:
        return RedirectResponse(
            f"/ui/reports/visitas?proposal_id={proposal_id}&month={month}&year={year}&employee_id={employee_id if employee_id is not None else ''}&authorized_name={authorized_name or ''}&msg=Error: No se encontró el informe para eliminar.",
            status_code=303,
        )

    delete_visit_referrals_only(db, reports)
    db.commit()

    return RedirectResponse(
        f"/ui/reports/visitas?proposal_id={proposal_id}&month={month}&year={year}&employee_id={employee_id if employee_id is not None else ''}&authorized_name={authorized_name or ''}&msg=Referidos eliminados exitosamente.",
        status_code=303,
    )


@router.get("/visitas/pdf", response_class=HTMLResponse)
def visits_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_visits_context(db, current_user, proposal_id, month, year, employee_id, authorized_name=authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/visitas_pdf.html", context)


@router.get("/visitas/excel")
def visits_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_visits_context(db, current_user, proposal_id, month, year, employee_id, authorized_name=authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    if not (proposal_id and context["period_label"] and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/visitas", status_code=303)

    proposal_label = next(
        (f"{proposal.code} - {proposal.name}" for proposal in context["proposals"] if proposal.proposal_id == context["selected_proposal_id"]),
        "",
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Visitas"
    ws.freeze_panes = "A6"

    ws["A1"] = "CENTROS SOR ISOLINA FERRÉ"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Reporte de Visitas"
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = "Propuesta"
    ws["B3"] = proposal_label
    ws["D3"] = "Periodo"
    ws["E3"] = context["period_label"]
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["D4"] = "Visitas"
    ws["E4"] = context["summary"]["visits"]
    ws["G4"] = "Asistencias"
    ws["H4"] = context["summary"]["attendances"]
    ws["J4"] = "Horas"
    ws["K4"] = context["summary"]["hours"]

    headers = ["Empleado", "Visitas registradas", "Asistencias acumuladas", "Horas acumuladas"]
    header_row = 6
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_index = header_row + 1
    for row in context["rows"]:
        values = [row["employee_name"], row["visits"], row["attendances"], row["hours"]]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            if col_index == 4:
                cell.number_format = "0.00"
            cell.alignment = Alignment(horizontal="left" if col_index == 1 else "center")
        row_index += 1

    if context["rows"]:
        totals = ["TOTALES", context["summary"]["visits"], context["summary"]["attendances"], context["summary"]["hours"]]
        for col_index, value in enumerate(totals, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.font = Font(bold=True)
            if col_index == 4:
                cell.number_format = "0.00"
            cell.alignment = Alignment(horizontal="center")

    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 18

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    safe_residential = (context["residential_name"] or "visitas").replace(" ", "_")
    filename = f"visitas_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_no_duplicado_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    authorized_name: str | None = None,
    duplicated: bool = False,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)

    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    report_users = base_context["report_users"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    location = _resolve_reporting_location(selected_user, is_global)
    residential_name = location["residential_name"]
    municipality = location["municipality"]
    rq_code = location["rq_code"]
    summary = {key: {"label": label, "f": 0, "m": 0, "total": 0} for key, label in AGE_BUCKETS}

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        if duplicated:
            stmt = (
                select(Attendance, Participant)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .join(Participant, Participant.participant_id == Attendance.participant_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                )
            )
            stmt = _apply_session_period_filter(stmt, period)
            if not is_global:
                stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)

            attendance_rows = db.execute(stmt).all()
            for _, participant in attendance_rows:
                age = _calc_age(participant.fecha_nacimiento)
                bucket = _get_age_bucket(age)
                if not bucket:
                    continue
                gender = _normalize_text(participant.genero).upper()
                if gender.startswith("F"):
                    summary[bucket]["f"] += 1
                elif gender.startswith("M"):
                    summary[bucket]["m"] += 1
                summary[bucket]["total"] += 1
        else:
            stmt = (
                select(Participant)
                .join(Attendance, Attendance.participant_id == Participant.participant_id)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                )
            )
            stmt = _apply_session_period_filter(stmt, period)
            stmt = stmt.distinct()
            if not is_global:
                stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)

            participants = db.execute(stmt).scalars().all()
            for participant in participants:
                age = _calc_age(participant.fecha_nacimiento)
                bucket = _get_age_bucket(age)
                if not bucket:
                    continue
                gender = _normalize_text(participant.genero).upper()
                if gender.startswith("F"):
                    summary[bucket]["f"] += 1
                elif gender.startswith("M"):
                    summary[bucket]["m"] += 1
                summary[bucket]["total"] += 1

    if duplicated:
        rows = []
        total_f = total_m = total_all = 0
        for key, label in AGE_BUCKETS:
            row = summary[key]
            rows.append({"label": label, "f": row["f"], "m": row["m"], "total": row["total"]})
            total_f += row["f"]
            total_m += row["m"]
            total_all += row["total"]
    else:
        participant_summary = _summarize_participants_by_age_and_gender(participants if 'participants' in locals() else [])
        rows = participant_summary["rows"]
        total_f = participant_summary["total_f"]
        total_m = participant_summary["total_m"]
        total_all = participant_summary["total_all"]

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, base_context["month_lookup"]),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "municipality": municipality,
        "rq_code": rq_code,
        "rows": rows,
        "total_f": total_f,
        "total_m": total_m,
        "total_all": total_all,
        "authorized_name": (authorized_name or "").strip(),
    }


@router.get("/notas", response_class=HTMLResponse)
def notes_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_notes_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/notas.html", context)


@router.api_route("/notas/pdf", methods=["GET", "POST"], response_class=HTMLResponse)
def notes_report_pdf(
    request: Request,
    proposal_id: int | None = Form(default=None),
    month: str | None = Form(default=None),
    year: str | None = Form(default=None),
    employee_id: int | None = Form(default=None),
    period_type: str = Form(default="monthly"),
    start_date: str | None = Form(default=None),
    end_date: str | None = Form(default=None),
    general_chart_image: str | None = Form(default=None),
    residential_chart_image: str | None = Form(default=None),
    subject_chart_images: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if request.method == "GET":
        proposal_id = proposal_id or _parse_optional_int(request.query_params.get("proposal_id"))
        month = month or request.query_params.get("month")
        year = year or request.query_params.get("year")
        employee_id = employee_id or _parse_optional_int(request.query_params.get("employee_id"))
        period_type = period_type if period_type != "monthly" else (request.query_params.get("period_type") or "monthly")
        start_date = start_date or request.query_params.get("start_date")
        end_date = end_date or request.query_params.get("end_date")

    context = _build_notes_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    subject_chart_image_list = [img for img in (subject_chart_images or "").split("||") if img]
    subject_chart_sections = [
        {
            "subject_name": subject_card["subject_name"],
            "image": subject_chart_image_list[index] if index < len(subject_chart_image_list) else "",
            "counts": subject_card["counts"],
            "segments": subject_card["segments"],
        }
        for index, subject_card in enumerate(context["subject_chart_cards"])
    ]

    context.update({
        "request": request,
        "current_user": current_user,
        "general_chart_image": general_chart_image or "",
        "residential_chart_image": residential_chart_image or "",
        "subject_chart_images": subject_chart_image_list,
        "subject_chart_sections": subject_chart_sections,
    })
    return templates.TemplateResponse("ui/reports/notas_pdf.html", context)


@router.get("/notas/excel")
def notes_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_notes_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    if not (proposal_id and context["period_label"] and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/notas", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Notas"
    ws.freeze_panes = "A6"

    ws["A1"] = "CENTROS SOR ISOLINA FERRÉ"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Informe de Notas"
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = "Propuesta"
    ws["B3"] = context["proposal_label"]
    ws["D3"] = "Periodo"
    ws["E3"] = context["period_label"]
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["D4"] = "Total evaluados"
    ws["E4"] = context["total_row"]["TOTAL"]

    summary_headers = ["Nota", "Cantidad", "%"]
    summary_row = 6
    for col_index, header in enumerate(summary_headers, start=1):
        cell = ws.cell(row=summary_row, column=col_index, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_index = summary_row + 1
    for segment in context["general_chart_segments"]:
        ws.cell(row=row_index, column=1, value=segment["label"])
        ws.cell(row=row_index, column=2, value=segment["value"])
        pct_cell = ws.cell(row=row_index, column=3, value=segment["percentage"] / 100)
        pct_cell.number_format = "0.00%"
        row_index += 1

    row_index += 1
    table_header_row = row_index
    headers = ["Edad", "A", "B", "C", "D", "F", "Especial", "K", "TOTAL"]
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=table_header_row, column=col_index, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_index = table_header_row + 1
    for row in context["rows"]:
        values = [row["age_label"], row["A"], row["B"], row["C"], row["D"], row["F"], row["Especial"], row["K"], row["TOTAL"]]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.alignment = Alignment(horizontal="left" if col_index == 1 else "center")
        row_index += 1

    total_values = ["TOTALES", context["total_row"]["A"], context["total_row"]["B"], context["total_row"]["C"], context["total_row"]["D"], context["total_row"]["F"], context["total_row"]["Especial"], context["total_row"]["K"], context["total_row"]["TOTAL"]]
    for col_index, value in enumerate(total_values, start=1):
        cell = ws.cell(row=row_index, column=col_index, value=value)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_index += 2
    residential_header_row = row_index
    residential_headers = ["Residencial", "A", "B", "C", "D", "F", "TOTAL"]
    for col_index, header in enumerate(residential_headers, start=1):
        cell = ws.cell(row=residential_header_row, column=col_index, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_index = residential_header_row + 1
    for residential_row in context["residential_chart_rows"]:
        values = [
            residential_row["residential_name"],
            residential_row["A"],
            residential_row["B"],
            residential_row["C"],
            residential_row["D"],
            residential_row["F"],
            residential_row["total"],
        ]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.alignment = Alignment(horizontal="left" if col_index == 1 else "center")
        row_index += 1

    row_index += 2
    subject_header_row = row_index
    subject_headers = ["Materia", "A", "B", "C", "D", "F"]
    for col_index, header in enumerate(subject_headers, start=1):
        cell = ws.cell(row=subject_header_row, column=col_index, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")

    row_index = subject_header_row + 1
    for subject_card in context["subject_chart_cards"]:
        values = [
            subject_card["subject_name"],
            subject_card["counts"]["A"],
            subject_card["counts"]["B"],
            subject_card["counts"]["C"],
            subject_card["counts"]["D"],
            subject_card["counts"]["F"],
        ]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.alignment = Alignment(horizontal="left" if col_index == 1 else "center")
        row_index += 1

    widths = {"A": 24, "B": 16, "C": 12, "D": 16, "E": 16, "F": 12, "G": 12, "H": 12, "I": 12}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    safe_residential = (context["residential_name"] or "notas").replace(" ", "_")
    filename = f"notas_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/embarazo", response_class=HTMLResponse)
def pregnancy_summary_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_pregnancy_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/embarazo.html", context)


@router.get("/embarazo/pdf", response_class=HTMLResponse)
def pregnancy_summary_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_pregnancy_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/embarazo_pdf.html", context)


@router.get("/embarazo/excel")
def pregnancy_summary_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_pregnancy_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    if not (proposal_id and context["period_label"] and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/embarazo", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Embarazo"
    ws.freeze_panes = "A6"

    proposal_label = next((f"{p.code} - {p.name}" for p in context["proposals"] if p.proposal_id == context["selected_proposal_id"]), "")
    ws["A1"] = "CENTROS SOR ISOLINA FERRÉ"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Informe de Embarazo"
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = "Propuesta"
    ws["B3"] = proposal_label
    ws["D3"] = "Periodo"
    ws["E3"] = context["period_label"]
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["D4"] = "Participación total"
    ws["E4"] = context["total"]["participation"]

    headers = [
        "Residencial",
        "Total reclutados",
        "F",
        "M",
        "Participantes femeninas embarazadas",
        "Participantes masculinos que han embarazado",
        "% Prevención",
        "Embarazos",
        "No embarazos",
    ]
    header_row = 6
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_index = header_row + 1
    for row in context["rows"]:
        values = [
            row["residential_name"],
            row["recruited"],
            row["f"],
            row["m"],
            row["pregnant_f"],
            row["pregnant_m"],
            row["prevention_pct"] / 100,
            row["pregnancy_cases"],
            row["non_pregnant"],
        ]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            cell.alignment = Alignment(horizontal="left" if col_index == 1 else "center")
            if col_index == 7:
                cell.number_format = "0.00%"
        row_index += 1

    total_values = [
        "TOTAL",
        context["total"]["recruited"],
        context["total"]["f"],
        context["total"]["m"],
        context["total"]["pregnant_f"],
        context["total"]["pregnant_m"],
        context["total"]["prevention_pct"] / 100,
        context["total"]["pregnancy_cases"],
        context["total"]["non_pregnant"],
    ]
    for col_index, value in enumerate(total_values, start=1):
        cell = ws.cell(row=row_index, column=col_index, value=value)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        if col_index == 7:
            cell.number_format = "0.00%"

    widths = {"A": 28, "B": 15, "C": 8, "D": 8, "E": 22, "F": 24, "G": 14, "H": 12, "I": 14}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    safe_residential = (context["residential_name"] or "embarazo").replace(" ", "_")
    filename = f"embarazo_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/desercion-escolar", response_class=HTMLResponse)
def school_dropout_summary_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_school_dropout_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/desercion_escolar.html", context)


@router.get("/desercion-escolar/pdf", response_class=HTMLResponse)
def school_dropout_summary_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_school_dropout_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/desercion_escolar_pdf.html", context)


@router.get("/desercion-escolar/excel")
def school_dropout_summary_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_school_dropout_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    if not (proposal_id and context["period_label"] and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/desercion-escolar", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Desercion"
    ws.freeze_panes = "B6"

    proposal_label = next((f"{p.code} - {p.name}" for p in context["proposals"] if p.proposal_id == context["selected_proposal_id"]), "")
    ws["A1"] = "CENTROS SOR ISOLINA FERRÉ"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Informe de Deserción Escolar"
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = "Propuesta"
    ws["B3"] = proposal_label
    ws["D3"] = "Periodo"
    ws["E3"] = context["period_label"]
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["D4"] = "Reclutados totales"
    ws["E4"] = context["total"]["recruited"]

    headers = ["Residencial", "Total", "F", "M"] + context["grade_columns"] + ["Tutorías", "% Tutorías", "Escuela", "% Escuela", "10", "20", "30", "40"]
    header_row = 6
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_index = header_row + 1
    for row in context["rows"]:
        values = [
            row["residential_name"],
            row["recruited"],
            row["f"],
            row["m"],
            *[row["grades"].get(grade, 0) for grade in context["grade_columns"]],
            row["tutoring"],
            row["tutoring_pct"] / 100,
            row["school"],
            row["school_pct"] / 100,
            row["report_10"],
            row["report_20"],
            row["report_30"],
            row["report_40"],
        ]
        for col_index, value in enumerate(values, start=1):
            cell = ws.cell(row=row_index, column=col_index, value=value)
            if col_index in {1}:
                cell.alignment = Alignment(horizontal="left")
            else:
                cell.alignment = Alignment(horizontal="center")
            if col_index in {20, 22}:
                cell.number_format = "0.00%"
        row_index += 1

    total_values = [
        "TOTAL",
        context["total"]["recruited"],
        context["total"]["f"],
        context["total"]["m"],
        *[context["total"]["grades"].get(grade, 0) for grade in context["grade_columns"]],
        context["total"]["tutoring"],
        context["total"]["tutoring_pct"] / 100,
        context["total"]["school"],
        context["total"]["school_pct"] / 100,
        context["total"]["report_10"],
        context["total"]["report_20"],
        context["total"]["report_30"],
        context["total"]["report_40"],
    ]
    for col_index, value in enumerate(total_values, start=1):
        cell = ws.cell(row=row_index, column=col_index, value=value)
        cell.font = Font(bold=True)
        cell.alignment = Alignment(horizontal="center")
        if col_index in {20, 22}:
            cell.number_format = "0.00%"

    widths = {
        "A": 26, "B": 10, "C": 8, "D": 8, "E": 6, "F": 6, "G": 6, "H": 6, "I": 6,
        "J": 6, "K": 6, "L": 6, "M": 6, "N": 6, "O": 6, "P": 6, "Q": 6, "R": 6,
        "S": 10, "T": 12, "U": 10, "V": 12, "W": 8, "X": 8, "Y": 8, "Z": 8,
    }
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    safe_residential = (context["residential_name"] or "desercion_escolar").replace(" ", "_")
    filename = f"desercion_escolar_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/duplicado", response_class=HTMLResponse)
def duplicado_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, duplicated=True, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/duplicado.html", context)


@router.get("/duplicado/pdf", response_class=HTMLResponse)
def duplicado_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, duplicated=True, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/duplicado_pdf.html", context)


@router.get("/duplicado/excel")
def duplicado_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, duplicated=True, period_type=period_type, start_date=start_date, end_date=end_date)

    if not (proposal_id and (context["period_label"]) and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/duplicado", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Duplicado"

    ws["A1"] = "Informe mensual de participaciones"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Duplicado por edad y sexo en los proyectos impactados"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["A5"] = "Municipio"
    ws["B5"] = context["municipality"] or ""
    ws["A6"] = "RQ"
    ws["B6"] = context["rq_code"] or ""
    ws["A7"] = "Periodo reportado"
    ws["B7"] = context["period_label"]
    ws["A8"] = "Funcionario autorizado"
    ws["B8"] = context["authorized_name"] or ""

    headers = ["Clasificación", "F", "M", "Total de participaciones"]
    header_row = 10
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    row_index = header_row + 1
    for row in context["rows"]:
        ws.cell(row=row_index, column=1, value=row["label"])
        ws.cell(row=row_index, column=2, value=row["f"])
        ws.cell(row=row_index, column=3, value=row["m"])
        ws.cell(row=row_index, column=4, value=row["total"])
        row_index += 1

    ws.cell(row=row_index, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=row_index, column=2, value=context["total_f"]).font = Font(bold=True)
    ws.cell(row=row_index, column=3, value=context["total_m"]).font = Font(bold=True)
    ws.cell(row=row_index, column=4, value=context["total_all"]).font = Font(bold=True)

    widths = {"A": 35, "B": 10, "C": 10, "D": 20}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    safe_residential = (context["residential_name"] or "duplicado").replace(" ", "_")
    filename = f"duplicado_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/no-duplicado", response_class=HTMLResponse)
def no_duplicado_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/no_duplicado.html", context)


@router.get("/hoja-cotejo", response_class=HTMLResponse)
def hoja_cotejo_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_hoja_cotejo_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/hoja_cotejo.html", context)


@router.get("/hoja-cotejo/pdf", response_class=HTMLResponse)
def hoja_cotejo_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_hoja_cotejo_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/hoja_cotejo_pdf.html", context)


@router.get("/por-programa", response_class=HTMLResponse)
def por_programa_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_por_programa_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/por_programa.html", context)


@router.get("/por-programa/pdf", response_class=HTMLResponse)
def por_programa_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_por_programa_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/por_programa_pdf.html", context)


@router.get("/por-programa/excel")
def por_programa_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_por_programa_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)

    if not (proposal_id and (context["period_label"]) and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/por-programa", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Por Programa"

    ws["A1"] = "Informe mensual de participantes"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Participación no duplicada por programa, edad y sexo en los proyectos impactados"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["A5"] = "Municipio"
    ws["B5"] = context["municipality"] or ""
    ws["A6"] = "RQ"
    ws["B6"] = context["rq_code"] or ""
    ws["A7"] = "Periodo reportado"
    ws["B7"] = context["period_label"]
    ws["A8"] = "Funcionario autorizado"
    ws["B8"] = context["authorized_name"] or ""

    row_index = 10
    for section in context["program_sections"]:
        ws.cell(row=row_index, column=1, value=f"Programa: {section['program_display_name']}").font = Font(bold=True)
        ws.cell(row=row_index + 1, column=1, value="Actividades adjudicadas")
        ws.cell(row=row_index + 1, column=2, value=section["assigned_activity_count"])

        header_row = row_index + 3
        ws.cell(row=header_row, column=1, value="Clasificación").font = Font(bold=True)
        ws.cell(row=header_row, column=2, value="Número de participantes por edad y sexo").font = Font(bold=True)
        ws.cell(row=header_row, column=4, value="Total de participantes").font = Font(bold=True)
        ws.merge_cells(start_row=header_row, start_column=2, end_row=header_row, end_column=3)
        ws.merge_cells(start_row=header_row, start_column=1, end_row=header_row + 1, end_column=1)
        ws.merge_cells(start_row=header_row, start_column=4, end_row=header_row + 1, end_column=4)
        ws.cell(row=header_row + 1, column=2, value="F").font = Font(bold=True)
        ws.cell(row=header_row + 1, column=3, value="M").font = Font(bold=True)

        for col_index in range(1, 5):
            ws.cell(row=header_row, column=col_index).alignment = Alignment(horizontal="center", vertical="center")
            ws.cell(row=header_row + 1, column=col_index).alignment = Alignment(horizontal="center", vertical="center")

        current_row = header_row + 2
        for row in section["rows"]:
            ws.cell(row=current_row, column=1, value=row["label"])
            ws.cell(row=current_row, column=2, value=row["f"])
            ws.cell(row=current_row, column=3, value=row["m"])
            ws.cell(row=current_row, column=4, value=row["total"])
            current_row += 1

        ws.cell(row=current_row, column=1, value="TOTAL").font = Font(bold=True)
        ws.cell(row=current_row, column=2, value=section["total_f"]).font = Font(bold=True)
        ws.cell(row=current_row, column=3, value=section["total_m"]).font = Font(bold=True)
        ws.cell(row=current_row, column=4, value=section["total_all"]).font = Font(bold=True)

        row_index = current_row + 3

    widths = {"A": 40, "B": 14, "C": 14, "D": 22}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    safe_residential = (context["residential_name"] or "por_programa").replace(" ", "_")
    filename = f"por_programa_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/no-duplicado/pdf", response_class=HTMLResponse)
def no_duplicado_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/no_duplicado_pdf.html", context)


@router.get("/no-duplicado/excel")
def no_duplicado_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)

    if not (proposal_id and (context["period_label"]) and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/no-duplicado", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "No Duplicado"

    ws["A1"] = "Informe mensual de participantes"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "No Duplicado por edad y sexo en los proyectos impactados"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["A5"] = "Municipio"
    ws["B5"] = context["municipality"] or ""
    ws["A6"] = "RQ"
    ws["B6"] = context["rq_code"] or ""
    ws["A7"] = "Periodo reportado"
    ws["B7"] = context["period_label"]
    ws["A8"] = "Funcionario autorizado"
    ws["B8"] = context["authorized_name"] or ""

    headers = ["Clasificación", "F", "M", "Total de participantes"]
    header_row = 10
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    row_index = header_row + 1
    for row in context["rows"]:
        ws.cell(row=row_index, column=1, value=row["label"])
        ws.cell(row=row_index, column=2, value=row["f"])
        ws.cell(row=row_index, column=3, value=row["m"])
        ws.cell(row=row_index, column=4, value=row["total"])
        row_index += 1

    ws.cell(row=row_index, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=row_index, column=2, value=context["total_f"]).font = Font(bold=True)
    ws.cell(row=row_index, column=3, value=context["total_m"]).font = Font(bold=True)
    ws.cell(row=row_index, column=4, value=context["total_all"]).font = Font(bold=True)

    widths = {"A": 35, "B": 10, "C": 10, "D": 20}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    safe_residential = (context["residential_name"] or "no_duplicado").replace(" ", "_")
    filename = f"no_duplicado_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _build_hoja_cotejo_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)
    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    proposals = base_context["proposals"]
    report_users = base_context["report_users"]
    year_options = base_context["year_options"]
    month_lookup = base_context["month_lookup"]
    user_residential_map = base_context["user_residential_map"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    location = _resolve_reporting_location(selected_user, is_global)
    residential_name = location["residential_name"]
    municipality = location["municipality"]
    rq_code = location["rq_code"]

    program_blocks = []
    total_contact_hours = 0.0

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        structure_blocks = _resolve_effective_program_population_blocks(db, proposal_id)

        activity_code_ids = sorted({
            row["activity_code_id"]
            for block in structure_blocks
            for population_block in block["population_blocks"]
            for row in population_block["rows"]
        })

        session_metrics_by_activity_code_id = {}
        attendance_metrics_by_activity_code_id = {}

        if activity_code_ids:
            session_stmt = (
                select(
                    ActivitySession.activity_code_id,
                    func.count(distinct(ActivitySession.session_id)).label("activities_count"),
                    func.coalesce(func.sum(ActivitySession.hours), 0).label("contact_hours"),
                )
                .where(
                    ActivitySession.proposal_id == proposal_id,
                    ActivitySession.activity_code_id.in_(activity_code_ids),
                )
                .group_by(ActivitySession.activity_code_id)
            )
            session_stmt = _apply_session_period_filter(session_stmt, period)
            if not is_global:
                session_stmt = session_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
            for activity_code_id_value, activities_count, contact_hours in db.execute(session_stmt).all():
                session_metrics_by_activity_code_id[activity_code_id_value] = {
                    "activities_count": int(activities_count or 0),
                    "contact_hours": float(contact_hours or 0),
                }

            attendance_stmt = (
                select(
                    ActivitySession.activity_code_id,
                    func.count(Attendance.attendance_id).label("duplicados"),
                    func.count(distinct(Attendance.participant_id)).label("unique_participants"),
                )
                .join(Attendance, Attendance.session_id == ActivitySession.session_id)
                .where(
                    ActivitySession.proposal_id == proposal_id,
                    ActivitySession.activity_code_id.in_(activity_code_ids),
                    Attendance.attended == True,  # noqa: E712
                )
                .group_by(ActivitySession.activity_code_id)
            )
            attendance_stmt = _apply_session_period_filter(attendance_stmt, period)
            if not is_global:
                attendance_stmt = attendance_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
            for activity_code_id_value, duplicados, unique_participants in db.execute(attendance_stmt).all():
                attendance_metrics_by_activity_code_id[activity_code_id_value] = {
                    "duplicados": int(duplicados or 0),
                    "unique_participants": int(unique_participants or 0),
                }

        total_contact_hours = sum(
            float(metrics.get("contact_hours", 0) or 0)
            for metrics in session_metrics_by_activity_code_id.values()
        )

        for block in structure_blocks:
            population_blocks = []
            for population_block in block["population_blocks"]:
                rows = []
                for row in population_block["rows"]:
                    session_metrics = session_metrics_by_activity_code_id.get(row["activity_code_id"], {})
                    attendance_metrics = attendance_metrics_by_activity_code_id.get(row["activity_code_id"], {})
                    activities_count = int(session_metrics.get("activities_count", 0))
                    contact_hours = float(session_metrics.get("contact_hours", 0))
                    duplicados = int(attendance_metrics.get("duplicados", 0))
                    unique_participants = int(attendance_metrics.get("unique_participants", 0))
                    rows.append({
                        **row,
                        "activities_count": activities_count,
                        "duplicados": duplicados,
                        "unique_participants": unique_participants,
                        "contact_hours": contact_hours,
                    })
                population_blocks.append({
                    **population_block,
                    "rows": rows,
                })
            program_blocks.append({
                **block,
                "population_blocks": population_blocks,
            })

    return {
        "proposals": proposals,
        "report_users": report_users,
        "user_residential_map": user_residential_map,
        "month_options": MONTH_OPTIONS,
        "month_lookup": month_lookup,
        "year_options": year_options,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "municipality": municipality,
        "rq_code": rq_code,
        "program_blocks": program_blocks,
        "total_contact_hours": total_contact_hours,
    }


def _build_por_programa_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)
    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    location = _resolve_reporting_location(selected_user, is_global)
    residential_name = location["residential_name"]
    municipality = location["municipality"]
    rq_code = location["rq_code"]
    program_sections = []
    overall_total_f = overall_total_m = overall_total_all = 0

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        programs = db.execute(
            select(ProposalReportProgram)
            .where(
                ProposalReportProgram.proposal_id == proposal_id,
                ProposalReportProgram.is_active == True,  # noqa: E712
            )
            .order_by(ProposalReportProgram.sort_order, ProposalReportProgram.code)
        ).scalars().all()

        program_activity_code_ids: dict[int, set[int]] = {}
        for program in programs:
            program_activity_code_ids[program.program_id] = _resolve_effective_program_activity_code_ids(db, program.program_id)

        for program in programs:
            activity_code_ids = program_activity_code_ids.get(program.program_id, set())
            if not activity_code_ids:
                program_sections.append({
                    "program": program,
                    "program_display_name": _program_report_display_name(program),
                    "rows": [{"label": label, "f": 0, "m": 0, "total": 0} for _, label in AGE_BUCKETS],
                    "total_f": 0,
                    "total_m": 0,
                    "total_all": 0,
                    "assigned_activity_count": 0,
                })
                continue

            stmt = (
                select(Participant)
                .join(Attendance, Attendance.participant_id == Participant.participant_id)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                    ActivitySession.activity_code_id.in_(activity_code_ids),
                )
            )
            stmt = _apply_session_period_filter(stmt, period)
            stmt = stmt.distinct()
            if not is_global:
                stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)

            participants = db.execute(stmt).scalars().all()
            participant_summary = _summarize_participants_by_age_and_gender(participants)
            overall_total_f += participant_summary["total_f"]
            overall_total_m += participant_summary["total_m"]
            overall_total_all += participant_summary["total_all"]

            program_sections.append({
                "program": program,
                "program_display_name": _program_report_display_name(program),
                "rows": participant_summary["rows"],
                "total_f": participant_summary["total_f"],
                "total_m": participant_summary["total_m"],
                "total_all": participant_summary["total_all"],
                "assigned_activity_count": len(activity_code_ids),
            })

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, base_context["month_lookup"]),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "municipality": municipality,
        "rq_code": rq_code,
        "authorized_name": (authorized_name or "").strip(),
        "program_sections": program_sections,
        "overall_total_f": overall_total_f,
        "overall_total_m": overall_total_m,
        "overall_total_all": overall_total_all,
    }


@router.get("/vca", response_class=HTMLResponse)
def vca_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_vca_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/vca.html", context)


@router.get("/vca/pdf", response_class=HTMLResponse)
def vca_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_vca_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/vca_pdf.html", context)


@router.get("/vca/excel")
def vca_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_vca_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    if not (proposal_id and context["period_label"] and context["columns"]):
        return RedirectResponse("/ui/reports/vca", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "VCA"
    ws.freeze_panes = "A9"
    ws.sheet_view.showGridLines = False
    ws["A1"] = "ÁREA DE PROGRAMAS COMUNALES Y DE RESIDENTES"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "INFORME VCA"
    ws["A2"].font = Font(bold=True, size=12)
    ws["A3"] = "Propuesta"
    ws["B3"] = next((f"{p.code} - {p.name}" for p in context["proposals"] if p.proposal_id == context["selected_proposal_id"]), "")
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["A5"] = "Periodo reportado"
    ws["B5"] = context["period_label"]
    ws["A6"] = "Total personas con impedimentos"
    ws["B6"] = context["total_people"]

    headers = ["Expediente", "Nombre", "Género", "Edad"] + [column.name for column in context["columns"]]
    header_row = 8
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    for row_index, row in enumerate(context["rows"], start=header_row + 1):
        ws.cell(row=row_index, column=1, value=row["expediente"])
        ws.cell(row=row_index, column=2, value=row["nombre"])
        ws.cell(row=row_index, column=3, value=row["genero"])
        ws.cell(row=row_index, column=4, value=row["edad"])
        for offset, column in enumerate(context["columns"], start=5):
            ws.cell(row=row_index, column=offset, value=row["column_values"].get(column.vca_column_id, ""))

    ws.column_dimensions["A"].width = 20
    ws.column_dimensions["B"].width = 35
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 10
    for index in range(len(context["columns"])):
        ws.column_dimensions[chr(69 + index)].width = 28

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    safe_residential = (context["residential_name"] or "vca").replace(" ", "_")
    filename = f"vca_{safe_residential}_{_period_filename_suffix(context)}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bonafide", response_class=HTMLResponse)
def bonafide_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/bonafide.html", context)


@router.get("/bonafide/pdf", response_class=HTMLResponse)
def bonafide_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/bonafide_pdf.html", context)


@router.get("/bonafide/excel")
def bonafide_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)

    if not (proposal_id and (context["period_label"]) and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/bonafide", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Bonafide"

    ws["A1"] = "Programa Faro de Esperanza"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Listado Bonafide"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Periodo"
    ws["B4"] = context["period_label"]
    ws["A5"] = "Residencial"
    ws["B5"] = context["residential_name"] or ""
    ws["A6"] = "Municipio"
    ws["B6"] = context["municipality"] or ""

    headers = ["#", "Expediente", "Nombre", "F", "M", "Edad", "Edif.", "Apto."]
    header_row = 8
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    for row_index, row in enumerate(context["rows"], start=header_row + 1):
        ws.cell(row=row_index, column=1, value=row["index"])
        ws.cell(row=row_index, column=2, value=row["expediente"])
        ws.cell(row=row_index, column=3, value=row["nombre"])
        ws.cell(row=row_index, column=4, value=row["f"])
        ws.cell(row=row_index, column=5, value=row["m"])
        ws.cell(row=row_index, column=6, value=row["edad"])
        ws.cell(row=row_index, column=7, value=row["edificio"])
        ws.cell(row=row_index, column=8, value=row["apartamento"])

    widths = {"A": 6, "B": 20, "C": 40, "D": 6, "E": 6, "F": 8, "G": 12, "H": 12}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    safe_residential = (context["residential_name"] or "bonafide").replace(" ", "_")
    filename = f"bonafide_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

