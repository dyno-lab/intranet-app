from __future__ import annotations

from datetime import date, datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, extract, func, distinct
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.user import User
from app.models.residential import Residential
from app.models.activity_code import ActivityCode
from app.models.activity_productivity_goal import ActivityProductivityGoal
from app.models.employee import Employee
from app.models.vca_column import VCAColumn
from app.models.vca_column_activity_code import VCAColumnActivityCode
from app.models.adm_service_type import ADMServiceType
from app.models.adm_service_type_activity_code import ADMServiceTypeActivityCode
from app.models.school_dropout_report import SchoolDropoutReport
from app.models.catalog_type import CatalogType
from app.models.catalog_option import CatalogOption
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
from app.services.report_excel_builders import (
    make_workbook,
    build_adm_sheet,
    build_bonafide_sheet,
    build_desercion_sheet,
    build_embarazo_sheet,
    build_hoja_cotejo_sheet,
    build_no_duplicado_sheet,
    build_notas_sheet,
    build_por_programa_sheet,
    build_vca_sheet,
    build_visitas_sheet,
    workbook_to_bytes,
)
from app.services.report_programs import (
    program_display_name as _program_report_display_name,
    program_uses_population_structure as _program_uses_population_structure,
    resolve_effective_program_activity_code_ids as _resolve_effective_program_activity_code_ids,
    resolve_effective_program_population_blocks as _resolve_effective_program_population_blocks,
)
from app.services.report_pdf import (
    PDFBackendUnavailableError,
    PDFRenderError,
    build_zip_bytes,
    render_template_to_pdf_bytes,
)
from app.services.notes_chart_svg import build_notes_pdf_chart_images
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


ADM_AGE_BUCKETS = [
    ("0_5", "0-5"),
    ("6_11", "6-11"),
    ("12_17", "12-17"),
    ("18_21", "18-21"),
    ("22_25", "22-25"),
    ("26_45", "26-45"),
    ("46_59", "46-59"),
    ("60_74", "60-74"),
    ("75_plus", "75+"),
]


def _get_adm_age_bucket(age: int | None) -> str | None:
    if age is None:
        return None
    if 0 <= age <= 5:
        return "0_5"
    if 6 <= age <= 11:
        return "6_11"
    if 12 <= age <= 17:
        return "12_17"
    if 18 <= age <= 21:
        return "18_21"
    if 22 <= age <= 25:
        return "22_25"
    if 26 <= age <= 45:
        return "26_45"
    if 46 <= age <= 59:
        return "46_59"
    if 60 <= age <= 74:
        return "60_74"
    if age >= 75:
        return "75_plus"
    return None


REPORT_OPTIONS = [
    {"value": "bonafide", "label": "Bonafide"},
    {"value": "productividad", "label": "Productividad"},
    {"value": "no-duplicado", "label": "No Duplicado"},
    {"value": "duplicados", "label": "Duplicados"},
    {"value": "desercion-escolar", "label": "Deserción Escolar"},
    {"value": "embarazo", "label": "Embarazo"},
    {"value": "notas", "label": "Notas"},
    {"value": "visitas", "label": "Visitas"},
    {"value": "por-programa", "label": "Informes por programa"},
    {"value": "hoja-cotejo", "label": "Hoja de Cotejo"},
    {"value": "vca", "label": "Informe VCA"},
    {"value": "adm", "label": "Informe ADM"},
    {"value": "todos", "label": "Todos"},
]

PERIOD_TYPE_OPTIONS = [
    {"value": "monthly", "label": "Mensual"},
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
    dashboard_context = _build_current_month_dashboard_cards(db, current_user)
    productivity_only_screen = report_key == "productividad"
    if productivity_only_screen and output != "screen":
        output = "screen"

    context.update(
        {
            "request": request,
            "current_user": current_user,
            "report_options": REPORT_OPTIONS,
            "period_type_options": PERIOD_TYPE_OPTIONS,
            "productivity_only_screen": productivity_only_screen,
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
            **dashboard_context,
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

    if report_key == "productividad":
        return RedirectResponse(
            f"/ui/reports/productividad?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id or ''}&period_type={period_type}&start_date={start_date or ''}&end_date={end_date or ''}",
            status_code=303,
        )

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

    if report_key == "adm":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/adm/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/adm/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/adm?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
            status_code=303,
        )

    if report_key == "todos":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/todos/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/todos/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}&authorized_name={authorized_name or ''}",
                status_code=303,
            )
        employee_id_param = "" if employee_id is None else employee_id
        return RedirectResponse(
            f"/ui/reports/?report_key=todos&proposal_id={proposal_id or ''}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id_param}&output={output}&period_type={period_type}&authorized_name={authorized_name or ''}&start_date={start_date or ''}&end_date={end_date or ''}",
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


def _build_productivity_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    view_mode: str = "activity",
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    month_lookup = base_context["month_lookup"]
    user_residential_map = base_context["user_residential_map"]

    period = _build_period_filter(period_type, month, year, start_date, end_date)
    normalized_month = period["month"]
    normalized_year = period["year"]

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]

    rows = []
    summary_rows = []
    residential_summary_rows = []
    warning_messages = []
    residential_name = "Global" if is_global else _residential_from_user(selected_user)
    normalized_view_mode = view_mode if view_mode in {"activity", "residential"} else "activity"
    dashboard_cards = []
    global_progress = {"percentage": 0, "cumple": 0, "total": 0}
    compliance_distribution = []
    top_activities = []
    bottom_activities = []
    residential_ranking = []
    selected_residential_dashboard = None

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]):
        proposal = db.get(Proposal, proposal_id)
        if proposal:
            goal_rows = db.execute(
                select(
                    ActivityProductivityGoal,
                    Proposal.code.label("proposal_code"),
                    Proposal.name.label("proposal_name"),
                    ActivityCode.code.label("activity_code"),
                    ActivityCode.description.label("activity_description"),
                )
                .join(Proposal, Proposal.proposal_id == ActivityProductivityGoal.proposal_id)
                .join(ActivityCode, ActivityCode.activity_code_id == ActivityProductivityGoal.activity_code_id)
                .where(
                    ActivityProductivityGoal.proposal_id == proposal_id,
                    ActivityProductivityGoal.is_active == True,  # noqa: E712
                )
                .order_by(ActivityCode.code)
            ).all()

            counts_stmt = (
                select(
                    ActivitySession.proposal_id,
                    ActivitySession.activity_code_id,
                    User.user_id.label("owner_user_id"),
                    Residential.name.label("residential_name"),
                    func.count(ActivitySession.session_id).label("executed_count"),
                )
                .select_from(ActivitySession)
                .outerjoin(User, User.user_id == ActivitySession.created_by_user_id)
                .outerjoin(Residential, Residential.residential_id == User.residential_id)
                .where(ActivitySession.proposal_id == proposal_id)
                .group_by(
                    ActivitySession.proposal_id,
                    ActivitySession.activity_code_id,
                    User.user_id,
                    Residential.name,
                )
            )

            counts_stmt = _apply_session_period_filter(counts_stmt, period)

            if not is_global and selected_user:
                counts_stmt = counts_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)

            count_rows = db.execute(counts_stmt).all()

            period_counts_stmt = (
                select(
                    ActivitySession.proposal_id,
                    ActivitySession.activity_code_id,
                    func.count(ActivitySession.session_id).label("executed_count"),
                )
                .select_from(ActivitySession)
                .where(ActivitySession.proposal_id == proposal_id)
                .group_by(ActivitySession.proposal_id, ActivitySession.activity_code_id)
            )

            if period["is_custom"]:
                period_counts_stmt = _apply_session_period_filter(period_counts_stmt, period)

            if not is_global and selected_user:
                period_counts_stmt = period_counts_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)

            period_count_rows = db.execute(period_counts_stmt).all()
            period_counts_by_activity = {
                (row.proposal_id, row.activity_code_id): int(row.executed_count or 0)
                for row in period_count_rows
            }

            counts_by_activity: dict[tuple[int, int], list[dict]] = {}
            for count_row in count_rows:
                key = (count_row.proposal_id, count_row.activity_code_id)
                derived_residential_name = count_row.residential_name or user_residential_map.get(count_row.owner_user_id) or "Sin residencial"
                counts_by_activity.setdefault(key, []).append({
                    "owner_user_id": count_row.owner_user_id,
                    "residential_name": derived_residential_name,
                    "executed": int(count_row.executed_count or 0),
                })

            month_label = month_lookup.get(normalized_month, str(normalized_month))

            residential_rollup: dict[str, dict] = {}

            for goal, proposal_code, proposal_name, activity_code, activity_description in goal_rows:
                activity_key = (goal.proposal_id, goal.activity_code_id)
                residential_counts = counts_by_activity.get(activity_key, [])
                global_executed = sum(item["executed"] for item in residential_counts)

                goal_type = goal.goal_type
                goal_value = goal.goal_value
                period_goal_value = goal.period_goal_value
                period_executed = period_counts_by_activity.get(activity_key, 0)
                goal_label = "Sin meta"
                compliance_label = "No aplica"
                compliance_badge = "secondary"
                global_goal = None
                detailed_rows = []
                per_residential_results: list[bool] = []
                period_compliance_label = None
                period_compliance_badge = None
                period_missing = None
                period_percentage = None

                if goal_type == "per_residential_min_1":
                    goal_label = "Según necesidad"
                elif goal_type == "per_residential_fixed":
                    goal_label = f"{goal_value} / residencial / mes"
                elif goal_type == "global_fixed":
                    goal_label = f"{goal_value} global / mes"
                    global_goal = goal_value

                if period_goal_value:
                    goal_label = f"{goal_label} + {period_goal_value} global / período" if goal_label != "Sin meta" else f"{period_goal_value} global / período"

                for residential_row in residential_counts:
                    executed = residential_row["executed"]
                    target_value = None
                    status = "Informativo"
                    status_badge = "secondary"
                    met_for_rollup = None

                    if goal_type == "per_residential_min_1":
                        target_value = 1
                        met = executed >= 1
                        met_for_rollup = met
                        status = "Cumple" if met else "No cumple"
                        status_badge = "success" if met else "danger"
                        per_residential_results.append(met)
                    elif goal_type == "per_residential_fixed":
                        target_value = int(goal_value or 0)
                        met = executed >= target_value
                        met_for_rollup = met
                        status = "Cumple" if met else "No cumple"
                        status_badge = "success" if met else "danger"
                        per_residential_results.append(met)
                    elif goal_type == "global_fixed":
                        met = global_executed >= int(goal_value or 0)
                        met_for_rollup = met
                        status = "Informativo"
                        status_badge = "secondary"

                    detailed_row = {
                        "proposal_code": proposal_code,
                        "proposal_name": proposal_name,
                        "activity_code": activity_code,
                        "activity_description": activity_description,
                        "residential_name": residential_row["residential_name"],
                        "month_label": month_label,
                        "executed": executed,
                        "goal": target_value if target_value is not None else global_goal,
                        "goal_type": goal_type,
                        "status": status,
                        "status_badge": status_badge,
                    }
                    detailed_rows.append(detailed_row)
                    rows.append(detailed_row)

                    residential_bucket = residential_rollup.setdefault(
                        residential_row["residential_name"],
                        {
                            "residential_name": residential_row["residential_name"],
                            "total_activities": 0,
                            "cumple": 0,
                            "no_cumple": 0,
                            "details": [],
                        },
                    )
                    residential_bucket["total_activities"] += 1
                    if met_for_rollup is True:
                        residential_bucket["cumple"] += 1
                    elif met_for_rollup is False:
                        residential_bucket["no_cumple"] += 1
                    residential_bucket["details"].append({
                        "proposal_code": proposal_code,
                        "proposal_name": proposal_name,
                        "activity_code": activity_code,
                        "activity_description": activity_description,
                        "goal_label": goal_label,
                        "executed": executed,
                        "goal": target_value if target_value is not None else global_goal,
                        "status": status,
                        "status_badge": status_badge,
                    })

                if goal_type == "per_residential_min_1":
                    all_met = global_executed >= 1 if is_global else (bool(per_residential_results) and all(per_residential_results))
                    compliance_label = "Cumple" if all_met else "No cumple"
                    compliance_badge = "success" if all_met else "danger"
                elif goal_type == "per_residential_fixed":
                    all_met = bool(per_residential_results) and all(per_residential_results)
                    compliance_label = "Cumple" if all_met else "No cumple"
                    compliance_badge = "success" if all_met else "danger"
                elif goal_type == "global_fixed":
                    all_met = global_executed >= int(goal_value or 0)
                    compliance_label = "Cumple" if all_met else "No cumple"
                    compliance_badge = "success" if all_met else "danger"

                if period_goal_value:
                    period_met = period_executed >= int(period_goal_value or 0)
                    period_compliance_label = "Cumple" if period_met else "No cumple"
                    period_compliance_badge = "success" if period_met else "danger"
                    period_missing = max(int(period_goal_value or 0) - period_executed, 0)
                    period_percentage = round((period_executed / int(period_goal_value or 0)) * 100, 2) if int(period_goal_value or 0) else 0

                summary_rows.append({
                    "proposal_code": proposal_code,
                    "proposal_name": proposal_name,
                    "activity_code": activity_code,
                    "activity_description": activity_description,
                    "month_label": month_label,
                    "goal_label": goal_label,
                    "goal_type": goal_type,
                    "global_executed": global_executed,
                    "global_goal": global_goal,
                    "period_executed": period_executed,
                    "period_goal": period_goal_value,
                    "period_missing": period_missing,
                    "period_percentage": period_percentage,
                    "period_compliance_label": period_compliance_label,
                    "period_compliance_badge": period_compliance_badge,
                    "compliance_label": compliance_label,
                    "compliance_badge": compliance_badge,
                    "residential_rows": detailed_rows,
                })

            for residential_bucket in residential_rollup.values():
                total_activities = residential_bucket["total_activities"]
                cumple = residential_bucket["cumple"]
                no_cumple = residential_bucket["no_cumple"]
                percentage = round((cumple / total_activities) * 100, 2) if total_activities else 0
                residential_summary_rows.append({
                    **residential_bucket,
                    "percentage": percentage,
                })

            residential_summary_rows.sort(key=lambda item: item["percentage"], reverse=True)

            total_activities_evaluated = len(summary_rows)
            compliance_metric_key = "period_compliance_label" if is_global else "compliance_label"
            total_compliant = sum(1 for item in summary_rows if item.get(compliance_metric_key) == "Cumple")
            total_non_compliant = sum(1 for item in summary_rows if item.get(compliance_metric_key) == "No cumple")
            global_percentage = round((total_compliant / total_activities_evaluated) * 100, 2) if total_activities_evaluated else 0
            residentials_evaluated = len(residential_summary_rows)
            residentials_high = sum(1 for item in residential_summary_rows if item["percentage"] >= 80)
            residentials_medium = sum(1 for item in residential_summary_rows if 50 <= item["percentage"] < 80)
            residentials_low = sum(1 for item in residential_summary_rows if item["percentage"] < 50)

            if is_global:
                total_period_executed = sum(int(item.get("period_executed") or 0) for item in summary_rows)
                total_period_goal = sum(int(item.get("period_goal") or 0) for item in summary_rows if item.get("period_goal"))
                total_period_missing = max(total_period_goal - total_period_executed, 0)
                total_period_percentage = round((total_period_executed / total_period_goal) * 100, 2) if total_period_goal else 0
                dashboard_cards = [
                    {"label": "Actividades evaluadas", "value": total_activities_evaluated, "tone": "primary", "subtitle": "Metas activas evaluadas"},
                    {"label": "Cumplen período", "value": total_compliant, "tone": "success", "subtitle": "Actividades en cumplimiento del período"},
                    {"label": "No cumplen período", "value": total_non_compliant, "tone": "danger", "subtitle": "Actividades rezagadas del período"},
                    {"label": "Actividades realizadas en el período", "value": total_period_executed, "tone": "info", "subtitle": "Total acumulado registrado dentro del período consultado"},
                    {"label": "Meta período", "value": total_period_goal, "tone": "secondary", "subtitle": "Meta global de actividades"},
                    {"label": "% avance período", "value": f"{total_period_percentage}%", "tone": "dark", "subtitle": f"Faltante: {total_period_missing}"},
                ]
                global_progress = {
                    "percentage": total_period_percentage,
                    "cumple": total_period_executed,
                    "total": total_period_goal,
                    "missing": total_period_missing,
                    "mode": "period",
                }
            else:
                dashboard_cards = [
                    {"label": "Actividades evaluadas", "value": total_activities_evaluated, "tone": "primary", "subtitle": "Metas activas evaluadas este mes"},
                    {"label": "Cumplen", "value": total_compliant, "tone": "success", "subtitle": "Actividades en cumplimiento mensual"},
                    {"label": "No cumplen", "value": total_non_compliant, "tone": "danger", "subtitle": "Actividades rezagadas este mes"},
                    {"label": "% cumplimiento global", "value": f"{global_percentage}%", "tone": "info", "subtitle": "Avance mensual del programa"},
                    {"label": "Residenciales evaluados", "value": residentials_evaluated, "tone": "secondary", "subtitle": "Residenciales con actividad evaluada"},
                    {"label": "Residenciales alto/medio/bajo", "value": f"{residentials_high}/{residentials_medium}/{residentials_low}", "tone": "dark", "subtitle": "Segmentación por desempeño"},
                ]

                global_progress = {
                    "percentage": global_percentage,
                    "cumple": total_compliant,
                    "total": total_activities_evaluated,
                    "mode": "monthly",
                }

            compliance_distribution = [
                {"label": "Cumplen", "value": total_compliant, "percentage": global_percentage, "tone": "success"},
                {"label": "No cumplen", "value": total_non_compliant, "percentage": round((total_non_compliant / total_activities_evaluated) * 100, 2) if total_activities_evaluated else 0, "tone": "danger"},
            ]

            ranked_activities = []
            for item in summary_rows:
                if item["goal_type"] == "global_fixed":
                    target = int(item["global_goal"] or 0)
                elif item["goal_type"] == "per_residential_min_1":
                    target = len(item["residential_rows"])
                elif item["goal_type"] == "per_residential_fixed":
                    target = len(item["residential_rows"]) * max(1, int(next((goal.goal_value for goal, pc, pn, ac, ad in goal_rows if ac == item["activity_code"] and pc == item["proposal_code"]), 0) or 0))
                else:
                    target = 0

                progress_percentage = round((item["global_executed"] / target) * 100, 2) if target else 0
                ranked_activities.append({
                    **item,
                    "target": target,
                    "progress_percentage": progress_percentage,
                })

            top_activities = [item for item in sorted(ranked_activities, key=lambda item: item["progress_percentage"], reverse=True) if item["global_executed"] > 0][:5]
            bottom_activities = [item for item in sorted(ranked_activities, key=lambda item: (item["global_executed"], item["progress_percentage"])) if item["global_executed"] == 0][:5]
            residential_ranking = residential_summary_rows[:5] if is_global else []

            if not is_global and residential_name:
                selected_residential_dashboard = next(
                    (item for item in residential_summary_rows if item["residential_name"] == residential_name),
                    None,
                )
                if selected_residential_dashboard:
                    detail_rows = selected_residential_dashboard.get("details", [])
                    detail_rows_with_progress = []
                    for detail in detail_rows:
                        goal_value = detail.get("goal")
                        executed = int(detail.get("executed") or 0)
                        if goal_value:
                            progress_percentage = round((executed / int(goal_value)) * 100, 2)
                        else:
                            progress_percentage = 0
                        detail_rows_with_progress.append({
                            **detail,
                            "progress_percentage": progress_percentage,
                        })

                    top_activities = [item for item in sorted(detail_rows_with_progress, key=lambda item: item["progress_percentage"], reverse=True) if int(item.get("executed") or 0) > 0][:5]
                    bottom_activities = [item for item in sorted(detail_rows_with_progress, key=lambda item: (int(item.get("executed") or 0), item["progress_percentage"])) if int(item.get("executed") or 0) == 0][:5]
            elif residential_summary_rows:
                selected_residential_dashboard = residential_summary_rows[0]

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": normalized_month,
        "selected_year": normalized_year,
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "rows": rows,
        "summary_rows": summary_rows,
        "residential_summary_rows": residential_summary_rows,
        "selected_view_mode": normalized_view_mode,
        "dashboard_cards": dashboard_cards,
        "global_progress": global_progress,
        "compliance_distribution": compliance_distribution,
        "top_activities": top_activities,
        "bottom_activities": bottom_activities,
        "residential_ranking": residential_ranking,
        "selected_residential_dashboard": selected_residential_dashboard,
        "warning_messages": warning_messages,
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
    }


@router.get("/productividad", response_class=HTMLResponse)
def productivity_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: str | None = None,
    view_mode: str = "activity",
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    normalized_employee_id = _parse_optional_int(employee_id)
    context = _build_productivity_context(
        db,
        current_user,
        proposal_id,
        month,
        year,
        normalized_employee_id,
        view_mode=view_mode,
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
    )
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/productividad.html", context)


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


def _build_adm_context(
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

    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    residential_name = None
    rows = []
    sociodemographic_rows = []
    sociodemographic_total = {"f": 0, "m": 0, "total": 0, "vca": 0}
    family_rows = []
    family_total = 0

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        proposal = db.get(Proposal, proposal_id)
        if proposal:
            service_types = db.execute(
                select(ADMServiceType)
                .where(ADMServiceType.proposal_id == proposal_id, ADMServiceType.is_active == True)  # noqa: E712
                .order_by(ADMServiceType.sort_order, ADMServiceType.name)
            ).scalars().all()

            mapping_rows = db.execute(
                select(ADMServiceTypeActivityCode, ActivityCode, ADMServiceType)
                .join(ActivityCode, ActivityCode.activity_code_id == ADMServiceTypeActivityCode.activity_code_id)
                .join(ADMServiceType, ADMServiceType.adm_service_type_id == ADMServiceTypeActivityCode.adm_service_type_id)
                .where(ADMServiceType.proposal_id == proposal_id, ADMServiceType.is_active == True)  # noqa: E712
            ).all()
            activity_to_service_type = {activity.activity_code_id: service_type.adm_service_type_id for _, activity, service_type in mapping_rows}

            session_stmt = (
                select(ActivitySession.session_id, ActivitySession.activity_code_id)
                .where(ActivitySession.proposal_id == proposal_id)
            )
            session_stmt = _apply_session_period_filter(session_stmt, period)
            if is_global:
                residential_name = "Global"
            else:
                session_stmt = session_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
                residential_name = _residential_from_user(selected_user)
            session_rows = db.execute(session_stmt).all()

            sessions_by_service_type: dict[int, set[int]] = {}
            session_ids = []
            for session_id, activity_code_id in session_rows:
                service_type_id = activity_to_service_type.get(activity_code_id)
                if not service_type_id:
                    continue
                sessions_by_service_type.setdefault(service_type_id, set()).add(session_id)
                session_ids.append(session_id)

            attendance_by_service_type: dict[int, int] = {}
            unique_participants_by_service_type: dict[int, set[int]] = {}
            if session_ids:
                attendance_stmt = (
                    select(Attendance.session_id, Attendance.participant_id, ActivitySession.activity_code_id)
                    .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                    .where(
                        Attendance.attended == True,  # noqa: E712
                        Attendance.session_id.in_(session_ids),
                    )
                )
                if not is_global:
                    attendance_stmt = attendance_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
                attendance_rows = db.execute(attendance_stmt).all()
                for session_id, participant_id, activity_code_id in attendance_rows:
                    service_type_id = activity_to_service_type.get(activity_code_id)
                    if not service_type_id:
                        continue
                    attendance_by_service_type[service_type_id] = attendance_by_service_type.get(service_type_id, 0) + 1
                    if participant_id:
                        unique_participants_by_service_type.setdefault(service_type_id, set()).add(participant_id)

            unique_participant_ids = set()
            for participant_ids in unique_participants_by_service_type.values():
                unique_participant_ids.update(participant_ids)

            participant_rows = []
            if unique_participant_ids:
                participant_stmt = select(Participant).where(Participant.participant_id.in_(unique_participant_ids))
                participant_rows = db.execute(participant_stmt).scalars().all()

            sociodemographic_summary = {
                key: {"label": label, "f": 0, "m": 0, "total": 0, "vca": 0}
                for key, label in ADM_AGE_BUCKETS
            }
            family_summary: dict[str, int] = {}
            family_catalog_options = db.execute(
                select(CatalogOption)
                .join(CatalogType, CatalogType.catalog_type_id == CatalogOption.catalog_type_id)
                .where(
                    CatalogType.key == "composicion_familiar",
                    CatalogOption.is_active == True,  # noqa: E712
                )
                .order_by(CatalogOption.sort_order, CatalogOption.label)
            ).scalars().all()

            for option in family_catalog_options:
                family_summary[option.label] = 0

            for participant in participant_rows:
                age = _calc_age(participant.fecha_nacimiento)
                bucket = _get_adm_age_bucket(age)
                if bucket:
                    gender = _normalize_text(participant.genero).upper()
                    if gender.startswith("F"):
                        sociodemographic_summary[bucket]["f"] += 1
                    elif gender.startswith("M"):
                        sociodemographic_summary[bucket]["m"] += 1
                    sociodemographic_summary[bucket]["total"] += 1
                    if _normalize_text(participant.vca).upper() == "SI":
                        sociodemographic_summary[bucket]["vca"] += 1

                family_key = (participant.composicion_familiar or "No especificado").strip() or "No especificado"
                family_summary[family_key] = family_summary.get(family_key, 0) + 1

            total_unique_people = len(participant_rows)
            for key, label in ADM_AGE_BUCKETS:
                row = sociodemographic_summary[key]
                percent = round((row["total"] / total_unique_people) * 100, 2) if total_unique_people else 0
                sociodemographic_rows.append({
                    "label": label,
                    "f": row["f"],
                    "m": row["m"],
                    "total": row["total"],
                    "percent": percent,
                    "vca": row["vca"],
                })
                sociodemographic_total["f"] += row["f"]
                sociodemographic_total["m"] += row["m"]
                sociodemographic_total["total"] += row["total"]
                sociodemographic_total["vca"] += row["vca"]

            for family_label in sorted(family_summary.keys()):
                family_rows.append({
                    "label": family_label,
                    "count": family_summary[family_label],
                })
            family_total = sum(family_summary.values())

            for service_type in service_types:
                rows.append({
                    "service_type_name": service_type.name,
                    "services_count": len(sessions_by_service_type.get(service_type.adm_service_type_id, set())),
                    "duplicados": attendance_by_service_type.get(service_type.adm_service_type_id, 0),
                    "no_duplicados": len(unique_participants_by_service_type.get(service_type.adm_service_type_id, set())),
                })

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
        "sociodemographic_rows": sociodemographic_rows,
        "sociodemographic_total": sociodemographic_total,
        "family_rows": family_rows,
        "family_total": family_total,
        "authorized_name": authorized_name or "",
    }


@router.get("/adm", response_class=HTMLResponse)
def adm_report(
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
    context = _build_adm_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/adm.html", context)


@router.get("/adm/pdf", response_class=HTMLResponse)
def adm_report_pdf(
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
    context = _build_adm_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/adm_pdf.html", context)


@router.get("/adm/pdf/download")
def adm_report_pdf_download(
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
    context = _build_adm_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"current_user": current_user})
    return _render_report_pdf_response(request, "ui/reports/adm_pdf.html", context, _pdf_download_filename("adm", context))


def _build_all_reports_bundle_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: str | None,
    year: str | None,
    employee_id: int | None,
    authorized_name: str | None,
    period_type: str,
    start_date: str | None,
    end_date: str | None,
):
    return {
        "bonafide": _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date),
        "no_duplicado": _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date),
        "duplicado": _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, duplicated=True, period_type=period_type, start_date=start_date, end_date=end_date),
        "visitas": _build_visits_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date),
        "por_programa": _build_por_programa_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date),
        "hoja_cotejo": _build_hoja_cotejo_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date),
        "desercion": _build_school_dropout_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date),
        "embarazo": _build_pregnancy_summary_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date),
        "notas": _build_notes_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date),
        "vca": _build_vca_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date),
        "adm": _build_adm_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date),
    }


ALL_REPORT_KEYS = [
    "bonafide",
    "no_duplicado",
    "duplicado",
    "visitas",
    "por_programa",
    "hoja_cotejo",
    "desercion",
    "embarazo",
    "notas",
    "vca",
    "adm",
]
# IMPORTANTE:
# Cuando se cree un reporte nuevo, revisar SIEMPRE estos puntos:
# 1) _build_all_reports_bundle_context
# 2) all_reports_excel
# 3) all_reports_pdf
# 4) índice / selector de reportes si aplica
# La meta es que el reporte nuevo también quede contemplado en "Todos".


def _pdf_download_filename(prefix: str, context: dict, extension: str = "pdf") -> str:
    safe_residential = (context.get("residential_name") or prefix).replace(" ", "_")
    return f"{prefix}_{safe_residential}_{_period_filename_suffix(context)}.{extension}"



def _render_report_pdf_response(
    request: Request,
    template_name: str,
    context: dict,
    filename: str,
) -> Response:
    pdf_context = {**context, "request": request}
    try:
        pdf_bytes = render_template_to_pdf_bytes(
            templates=templates,
            template_name=template_name,
            context=pdf_context,
            request=request,
        )
    except PDFBackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PDFRenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/todos/pdf")
def all_reports_pdf(
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
    bundle = _build_all_reports_bundle_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type, start_date, end_date)
    shared_context = {"current_user": current_user, "authorized_name": authorized_name or ""}

    pdf_specs = [
        ("bonafide", "ui/reports/bonafide_pdf.html", {**bundle["bonafide"], **shared_context}, _pdf_download_filename("bonafide", bundle["bonafide"])),
        ("no_duplicado", "ui/reports/no_duplicado_pdf.html", {**bundle["no_duplicado"], **shared_context}, _pdf_download_filename("no_duplicado", bundle["no_duplicado"])),
        ("duplicado", "ui/reports/duplicado_pdf.html", {**bundle["duplicado"], **shared_context}, _pdf_download_filename("duplicado", bundle["duplicado"])),
        ("visitas", "ui/reports/visitas_pdf.html", {**bundle["visitas"], **shared_context}, _pdf_download_filename("visitas", bundle["visitas"])),
        ("por_programa", "ui/reports/por_programa_pdf.html", {**bundle["por_programa"], **shared_context}, _pdf_download_filename("por_programa", bundle["por_programa"])),
        ("hoja_cotejo", "ui/reports/hoja_cotejo_pdf.html", {**bundle["hoja_cotejo"], **shared_context}, _pdf_download_filename("hoja_cotejo", bundle["hoja_cotejo"])),
        ("desercion", "ui/reports/desercion_escolar_pdf.html", {**bundle["desercion"], **shared_context}, _pdf_download_filename("desercion_escolar", bundle["desercion"])),
        ("embarazo", "ui/reports/embarazo_pdf.html", {**bundle["embarazo"], **shared_context}, _pdf_download_filename("embarazo", bundle["embarazo"])),
        ("notas", "ui/reports/notas_pdf.html", {**bundle["notas"], **shared_context, **build_notes_pdf_chart_images(bundle["notas"])}, _pdf_download_filename("notas", bundle["notas"])),
        ("vca", "ui/reports/vca_pdf.html", {**bundle["vca"], **shared_context}, _pdf_download_filename("vca", bundle["vca"])),
        ("adm", "ui/reports/adm_pdf.html", {**bundle["adm"], **shared_context}, _pdf_download_filename("adm", bundle["adm"])),
    ]

    files = []
    try:
        for _, template_name, context, filename in pdf_specs:
            files.append((filename, render_template_to_pdf_bytes(templates=templates, template_name=template_name, context={**context, "request": request}, request=request)))
    except PDFBackendUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except PDFRenderError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    zip_filename = _pdf_download_filename("todos_los_reportes", bundle["bonafide"], extension="zip")
    zip_bytes = build_zip_bytes(files)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


@router.get("/todos/excel")
def all_reports_excel(
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
    bundle = _build_all_reports_bundle_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type, start_date, end_date)

    employee_records = db.execute(
        select(Employee)
        .where(Employee.is_active == True)  # noqa: E712
        .order_by(Employee.full_name)
    ).scalars().all()
    visible_employee_names = [employee.full_name.strip() for employee in employee_records]
    existing_by_name = {row.get("employee_name", ""): row for row in bundle["visitas"].get("rows", [])}
    visit_rows = [
        {
            "employee_name": employee_name,
            "visits": existing_by_name.get(employee_name, {}).get("visits", 0),
            "attendances": existing_by_name.get(employee_name, {}).get("attendances", 0),
            "hours": existing_by_name.get(employee_name, {}).get("hours", 0),
        }
        for employee_name in visible_employee_names
    ]
    if not visit_rows:
        visit_rows = bundle["visitas"].get("rows", [])

    wb = make_workbook()
    build_bonafide_sheet(wb, bundle["bonafide"], title="Bonafide")
    build_no_duplicado_sheet(wb, bundle["no_duplicado"], title="No Duplicado")
    build_no_duplicado_sheet(wb, bundle["duplicado"], title="Duplicado", duplicated=True)
    build_visitas_sheet(wb, bundle["visitas"], title="Visitas", rows=visit_rows, include_totals_when_empty=True)
    build_por_programa_sheet(wb, bundle["por_programa"], title="Por Programa")
    build_hoja_cotejo_sheet(wb, bundle["hoja_cotejo"], title="Hoja Cotejo")
    build_desercion_sheet(wb, bundle["desercion"], title="Desercion")
    build_embarazo_sheet(wb, bundle["embarazo"], title="Embarazo")
    build_notas_sheet(wb, bundle["notas"], title="Notas")
    build_vca_sheet(wb, bundle["vca"], title="VCA")
    build_adm_sheet(wb, bundle["adm"], title="ADM")

    output = workbook_to_bytes(wb)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="todos_los_reportes.xlsx"'},
    )


@router.get("/adm/excel")
def adm_report_excel(
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
    context = _build_adm_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    if not (proposal_id and context["period_label"]):
        return RedirectResponse("/ui/reports/adm", status_code=303)

    wb = make_workbook()
    build_adm_sheet(wb, context, title="ADM")
    output = workbook_to_bytes(wb)
    safe_residential = (context["residential_name"] or "adm").replace(" ", "_")
    filename = f"adm_{safe_residential}_{_period_filename_suffix(context)}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



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

    delete_visit_reports_and_referrals(db, reports)
    db.commit()

    return RedirectResponse(
        f"/ui/reports/visitas?proposal_id={proposal_id}&month={month}&year={year}&employee_id={employee_id if employee_id is not None else ''}&authorized_name={authorized_name or ''}&msg=Informe de visitas eliminado exitosamente.",
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

    wb = make_workbook()
    build_visitas_sheet(wb, context, title="Visitas")
    output = workbook_to_bytes(wb)
    safe_residential = (context["residential_name"] or "visitas").replace(" ", "_")
    filename = f"visitas_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



def _calculate_no_duplicado_metric(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    duplicated: bool = False,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)
    scope = _resolve_reporting_scope(current_user, employee_id, db)
    selected_user = scope["selected_user"]
    is_global = scope["is_global"]
    employee_id = scope["employee_id"]
    summary = {key: {"label": label, "f": 0, "m": 0, "total": 0} for key, label in AGE_BUCKETS}
    participants = []

    if (((proposal_id is not None) and ((period["month"] and period["year"]) or period["is_custom"])) or period["is_custom"]) and (selected_user or is_global):
        if duplicated:
            stmt = (
                select(Attendance, Participant)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .join(Participant, Participant.participant_id == Attendance.participant_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                )
            )
            if proposal_id is not None:
                stmt = stmt.where(ActivitySession.proposal_id == proposal_id)
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
                )
            )
            if proposal_id is not None:
                stmt = stmt.where(ActivitySession.proposal_id == proposal_id)
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
        participant_summary = _summarize_participants_by_age_and_gender(participants)
        rows = participant_summary["rows"]
        total_f = participant_summary["total_f"]
        total_m = participant_summary["total_m"]
        total_all = participant_summary["total_all"]

    return {
        "period": period,
        "selected_user": selected_user,
        "is_global": is_global,
        "employee_id": employee_id,
        "rows": rows,
        "total_f": total_f,
        "total_m": total_m,
        "total_all": total_all,
    }


def _build_current_month_dashboard_cards(
    db: Session,
    current_user: User,
):
    today = date.today()
    month_start = today.replace(day=1)
    scope_employee_id = 0 if current_user.role in ["admin", "supervisor"] else current_user.user_id

    no_duplicado_metric = _calculate_no_duplicado_metric(
        db,
        current_user,
        proposal_id=None,
        month=None,
        year=None,
        employee_id=scope_employee_id,
        duplicated=False,
        period_type="custom",
        start_date=month_start,
        end_date=today,
    )
    duplicados_metric = _calculate_no_duplicado_metric(
        db,
        current_user,
        proposal_id=None,
        month=None,
        year=None,
        employee_id=scope_employee_id,
        duplicated=True,
        period_type="custom",
        start_date=month_start,
        end_date=today,
    )

    session_stmt = select(func.count(distinct(ActivitySession.session_id))).where(
        ActivitySession.session_date >= month_start,
        ActivitySession.session_date <= today,
    )
    if current_user.role not in ["admin", "supervisor"]:
        session_stmt = session_stmt.where(ActivitySession.created_by_user_id == current_user.user_id)
    activities_count = db.execute(session_stmt).scalar_one() or 0

    period_label = f"Del {month_start.strftime('%d/%m/%Y')} al {today.strftime('%d/%m/%Y')}"
    scope_label = "Global" if current_user.role in ["admin", "supervisor"] else "Propio"

    return {
        "dashboard_period_label": period_label,
        "dashboard_scope_label": scope_label,
        "dashboard_cards": [
            {
                "key": "no-duplicado",
                "label": "No Duplicado",
                "value": no_duplicado_metric["total_all"],
                "tone": "primary",
                "subtitle": "Participantes únicos acumulados del mes corriente",
            },
            {
                "key": "duplicados",
                "label": "Duplicados",
                "value": duplicados_metric["total_all"],
                "tone": "warning",
                "subtitle": "Participaciones acumuladas del mes corriente",
            },
            {
                "key": "actividades-realizadas",
                "label": "Actividades Realizadas",
                "value": activities_count,
                "tone": "success",
                "subtitle": "Sesiones registradas del mes corriente",
            },
        ],
    }


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
    base_context = _base_reports_context(db, current_user, MONTH_OPTIONS)
    metric = _calculate_no_duplicado_metric(
        db,
        current_user,
        proposal_id,
        month,
        year,
        employee_id,
        duplicated=duplicated,
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
    )
    location = _resolve_reporting_location(metric["selected_user"], metric["is_global"])

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": metric["period"]["month"],
        "selected_year": metric["period"]["year"],
        "selected_period_type": metric["period"]["period_type"],
        "selected_start_date": metric["period"]["start_date"].isoformat() if metric["period"]["start_date"] else "",
        "selected_end_date": metric["period"]["end_date"].isoformat() if metric["period"]["end_date"] else "",
        "period_label": _describe_period(metric["period"], base_context["month_lookup"]),
        "selected_employee_id": metric["employee_id"],
        "selected_user": metric["selected_user"],
        "is_global": metric["is_global"],
        "residential_name": location["residential_name"],
        "municipality": location["municipality"],
        "rq_code": location["rq_code"],
        "rows": metric["rows"],
        "total_f": metric["total_f"],
        "total_m": metric["total_m"],
        "total_all": metric["total_all"],
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
    fallback_chart_images = build_notes_pdf_chart_images(context)
    subject_chart_sections = []
    fallback_sections = fallback_chart_images["subject_chart_sections"]
    for index, subject_card in enumerate(context["subject_chart_cards"]):
        fallback_section = fallback_sections[index] if index < len(fallback_sections) else {
            "subject_name": subject_card["subject_name"],
            "image": "",
            "counts": subject_card["counts"],
            "segments": subject_card["segments"],
        }
        subject_chart_sections.append({
            "subject_name": subject_card["subject_name"],
            "image": subject_chart_image_list[index] if index < len(subject_chart_image_list) and subject_chart_image_list[index] else fallback_section["image"],
            "counts": subject_card["counts"],
            "segments": subject_card["segments"],
        })

    def _looks_like_inline_image(value: str | None) -> bool:
        if not value:
            return False
        return value.startswith("data:image/")

    context.update({
        "request": request,
        "current_user": current_user,
        "general_chart_image": general_chart_image if _looks_like_inline_image(general_chart_image) else fallback_chart_images["general_chart_image"],
        "residential_chart_image": residential_chart_image if _looks_like_inline_image(residential_chart_image) else fallback_chart_images["residential_chart_image"],
        "subject_chart_images": [section["image"] for section in subject_chart_sections],
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

    wb = make_workbook()
    build_notas_sheet(wb, context, title="Notas")
    output = workbook_to_bytes(wb)
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

    wb = make_workbook()
    build_embarazo_sheet(wb, context, title="Embarazo")
    output = workbook_to_bytes(wb)
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

    wb = make_workbook()
    build_desercion_sheet(wb, context, title="Desercion")
    output = workbook_to_bytes(wb)
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

    wb = make_workbook()
    build_no_duplicado_sheet(wb, context, title="Duplicado", duplicated=True)
    output = workbook_to_bytes(wb)
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


@router.get("/hoja-cotejo/excel")
def hoja_cotejo_report_excel(
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

    if not (proposal_id and context["period_label"] and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/hoja-cotejo", status_code=303)

    wb = make_workbook()
    build_hoja_cotejo_sheet(wb, context, title="Hoja de Cotejo")
    output = workbook_to_bytes(wb)
    safe_residential = (context["residential_name"] or "hoja_cotejo").replace(" ", "_")
    filename = f"hoja_cotejo_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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

    wb = make_workbook()
    build_por_programa_sheet(wb, context, title="Por Programa")
    output = workbook_to_bytes(wb)
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

    wb = make_workbook()
    build_no_duplicado_sheet(wb, context, title="No Duplicado")
    output = workbook_to_bytes(wb)
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
            program_contact_hours = 0.0
            seen_program_activity_ids: set[int] = set()
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
                    if row["activity_code_id"] not in seen_program_activity_ids:
                        program_contact_hours += contact_hours
                        seen_program_activity_ids.add(row["activity_code_id"])
                population_blocks.append({
                    **population_block,
                    "rows": rows,
                })
            program_blocks.append({
                **block,
                "population_blocks": population_blocks,
                "program_contact_hours": program_contact_hours,
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

    wb = make_workbook()
    build_vca_sheet(wb, context, title="VCA")
    output = workbook_to_bytes(wb)
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


@router.get("/bonafide/pdf/download")
def bonafide_report_pdf_download(
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
    context.update({"current_user": current_user})
    return _render_report_pdf_response(request, "ui/reports/bonafide_pdf.html", context, _pdf_download_filename("bonafide", context))


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

    wb = make_workbook()
    build_bonafide_sheet(wb, context, title="Bonafide")
    output = workbook_to_bytes(wb)
    safe_residential = (context["residential_name"] or "bonafide").replace(" ", "_")
    filename = f"bonafide_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
