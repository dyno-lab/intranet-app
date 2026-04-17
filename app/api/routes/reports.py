from __future__ import annotations

from datetime import date, datetime, timedelta
from io import BytesIO
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, Response, RedirectResponse
from fastapi.templating import Jinja2Templates
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import select, func, case, or_, and_
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
from app.models.vca_column import VCAColumn
from app.models.vca_column_activity_code import VCAColumnActivityCode
from app.models.school_dropout_report import SchoolDropoutReport
from app.models.school_dropout_report_item import SchoolDropoutReportItem
from app.models.pregnancy_report import PregnancyReport
from app.models.pregnancy_report_item import PregnancyReportItem
from app.models.school_grade_report import SchoolGradeReport
from app.models.school_grade_report_item import SchoolGradeReportItem
from app.models.adm_service_type import ADMServiceType
from app.models.adm_service_type_activity_code import ADMServiceTypeActivityCode
from app.models.visit_report import VisitReport
from app.models.visit_report_referral import VisitReportReferral
from app.models.proposal_report_program import ProposalReportProgram
from app.models.proposal_report_program_activity import ProposalReportProgramActivity
from app.models.proposal_report_program_activity_code import ProposalReportProgramActivityCode
from app.models.proposal_report_program_population import ProposalReportProgramPopulation
from app.models.proposal_report_program_population_activity_code import ProposalReportProgramPopulationActivityCode
from app.models.proposal_population_group import ProposalPopulationGroup
from app.models.person import Person
from app.helpers.report_context import base_reports_context
from app.services.report_programs import resolve_effective_program_population_blocks as _resolve_effective_program_population_blocks

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

MONTH_OPTIONS = [
    (1, "Enero"),
    (2, "Febrero"),
    (3, "Marzo"),
    (4, "Abril"),
    (5, "Mayo"),
    (6, "Junio"),
    (7, "Julio"),
    (8, "Agosto"),
    (9, "Septiembre"),
    (10, "Octubre"),
    (11, "Noviembre"),
    (12, "Diciembre"),
]


def _base_reports_context(db: Session, current_user: User, month_options: list[tuple[int, str]]):
    return base_reports_context(db, current_user, month_options)


def _parse_optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _coerce_to_date(value: date | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _build_period_filter(period_type: str, month, year, start_date, end_date):
    normalized_month = _parse_optional_int(month)
    normalized_year = _parse_optional_int(year)
    normalized_start = _coerce_to_date(start_date)
    normalized_end = _coerce_to_date(end_date)

    if period_type == "custom" and normalized_start and normalized_end and normalized_start <= normalized_end:
        return {
            "period_type": "custom",
            "month": normalized_month,
            "year": normalized_year,
            "start_date": normalized_start,
            "end_date": normalized_end,
            "is_custom": True,
        }

    return {
        "period_type": "monthly",
        "month": normalized_month,
        "year": normalized_year,
        "start_date": None,
        "end_date": None,
        "is_custom": False,
    }


def _apply_session_period_filter(stmt, period: dict):
    if period["is_custom"] and period["start_date"] and period["end_date"]:
        return stmt.where(
            ActivitySession.session_date >= period["start_date"],
            ActivitySession.session_date <= period["end_date"],
        )
    if period["month"] and period["year"]:
        return stmt.where(
            func.month(ActivitySession.session_date) == period["month"],
            func.year(ActivitySession.session_date) == period["year"],
        )
    return stmt


def _describe_period(period: dict, month_lookup: dict[int, str]) -> str | None:
    if period["is_custom"] and period["start_date"] and period["end_date"]:
        return f"{period['start_date'].strftime('%d/%m/%Y')} - {period['end_date'].strftime('%d/%m/%Y')}"
    if period["month"] and period["year"]:
        return f"{month_lookup.get(period['month'], period['month'])} {period['year']}"
    return None


def _resolve_reporting_scope(current_user: User, employee_id: int | None, db: Session):
    is_admin_scope = current_user.role in ["admin", "supervisor"]
    selected_user = None
    is_global = False

    if is_admin_scope:
        if employee_id == 0:
            is_global = True
        elif employee_id:
            selected_user = db.get(User, employee_id)
    else:
        selected_user = current_user

    return {
        "selected_user": selected_user,
        "is_global": is_global,
        "employee_id": employee_id,
    }


def _residential_from_user(user: User | None) -> str | None:
    if not user:
        return None
    residential = getattr(user, "residential", None)
    if residential and getattr(residential, "name", None):
        return residential.name
    return None


def _goal_type_display_label(goal_type: str | None) -> str:
    mapping = {
        "none": "Sin meta",
        "per_residential_min_1": "Según necesidad",
        "per_residential_fixed": "Cantidad fija mensual por residencial",
        "global_fixed": "Cantidad global mensual",
        "per_residential_period_fixed": "Acumulada por período",
    }
    return mapping.get(goal_type or "none", "Sin meta")


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
    global_progress = {"percentage": 0, "cumple": 0, "total": 0, "missing": 0, "mode": "monthly"}
    compliance_distribution = []
    top_activities = []
    bottom_activities = []
    residential_ranking = []
    selected_residential_dashboard = None
    has_period_accumulated_goals = False

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]):
        proposal = db.get(Proposal, proposal_id)
        if proposal:
            proposal_period_start = _coerce_to_date(getattr(proposal, "start_date", None))
            proposal_period_end = _coerce_to_date(getattr(proposal, "end_date", None))
            proposal_period = {
                "period_type": "proposal",
                "month": None,
                "year": None,
                "start_date": proposal_period_start,
                "end_date": proposal_period_end,
                "is_custom": bool(proposal_period_start and proposal_period_end and proposal_period_start <= proposal_period_end),
            }

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
                    ActivityProductivityGoal.is_active == True,
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

            proposal_period_counts_stmt = (
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
            if proposal_period["is_custom"]:
                proposal_period_counts_stmt = _apply_session_period_filter(proposal_period_counts_stmt, proposal_period)
            if not is_global and selected_user:
                proposal_period_counts_stmt = proposal_period_counts_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
            proposal_period_count_rows = db.execute(proposal_period_counts_stmt).all()

            proposal_period_totals_stmt = (
                select(
                    ActivitySession.proposal_id,
                    ActivitySession.activity_code_id,
                    func.count(ActivitySession.session_id).label("executed_count"),
                )
                .select_from(ActivitySession)
                .where(ActivitySession.proposal_id == proposal_id)
                .group_by(ActivitySession.proposal_id, ActivitySession.activity_code_id)
            )
            if proposal_period["is_custom"]:
                proposal_period_totals_stmt = _apply_session_period_filter(proposal_period_totals_stmt, proposal_period)
            if not is_global and selected_user:
                proposal_period_totals_stmt = proposal_period_totals_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
            proposal_period_total_rows = db.execute(proposal_period_totals_stmt).all()
            proposal_period_counts_by_activity = {
                (row.proposal_id, row.activity_code_id): int(row.executed_count or 0)
                for row in proposal_period_total_rows
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

            proposal_period_counts_by_residential: dict[tuple[int, int], list[dict]] = {}
            for count_row in proposal_period_count_rows:
                key = (count_row.proposal_id, count_row.activity_code_id)
                derived_residential_name = count_row.residential_name or user_residential_map.get(count_row.owner_user_id) or "Sin residencial"
                proposal_period_counts_by_residential.setdefault(key, []).append({
                    "owner_user_id": count_row.owner_user_id,
                    "residential_name": derived_residential_name,
                    "executed": int(count_row.executed_count or 0),
                })

            month_label = month_lookup.get(normalized_month, str(normalized_month or "Período"))
            residential_rollup: dict[str, dict] = {}

            for goal, proposal_code, proposal_name, activity_code, activity_description in goal_rows:
                activity_key = (goal.proposal_id, goal.activity_code_id)
                monthly_residential_counts = counts_by_activity.get(activity_key, [])
                period_residential_counts = proposal_period_counts_by_residential.get(activity_key, [])
                global_executed = sum(item["executed"] for item in monthly_residential_counts)
                period_global_executed = proposal_period_counts_by_activity.get(activity_key, 0)

                goal_type = goal.goal_type
                goal_value = goal.goal_value
                period_goal_value = goal.period_goal_value
                is_period_accumulated = goal_type == "per_residential_period_fixed"
                has_period_accumulated_goals = has_period_accumulated_goals or is_period_accumulated

                display_residential_counts = period_residential_counts if is_period_accumulated else monthly_residential_counts
                displayed_executed_total = period_global_executed if is_period_accumulated else global_executed

                goal_label = _goal_type_display_label(goal_type)
                compliance_label = "No aplica"
                compliance_badge = "secondary"
                global_goal = None
                detailed_rows = []
                per_residential_results: list[bool] = []
                period_compliance_label = None
                period_compliance_badge = None
                period_missing = None
                period_percentage = None
                evaluation_scope = "period" if is_period_accumulated else ("period" if is_global else "monthly")

                if goal_type == "per_residential_min_1":
                    goal_label = "Según necesidad"
                elif goal_type == "per_residential_fixed":
                    goal_label = f"{goal_value} / residencial / mes"
                elif goal_type == "global_fixed":
                    goal_label = f"{goal_value} global / mes"
                    global_goal = goal_value
                elif goal_type == "per_residential_period_fixed":
                    goal_label = f"{goal_value} / residencial / período"

                if period_goal_value:
                    suffix = f"{period_goal_value} global / período"
                    goal_label = f"{goal_label} + {suffix}" if goal_label != "Sin meta" else suffix

                for residential_row in display_residential_counts:
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
                    elif goal_type == "per_residential_period_fixed":
                        target_value = int(goal_value or 0)
                        met = executed >= target_value
                        met_for_rollup = met
                        status = "Cumple" if met else "No cumple"
                        status_badge = "success" if met else "danger"
                        per_residential_results.append(met)

                    detailed_row = {
                        "proposal_code": proposal_code,
                        "proposal_name": proposal_name,
                        "activity_code": activity_code,
                        "activity_description": activity_description,
                        "residential_name": residential_row["residential_name"],
                        "month_label": "Período propuesta" if is_period_accumulated else month_label,
                        "executed": executed,
                        "goal": target_value if target_value is not None else global_goal,
                        "goal_type": goal_type,
                        "status": status,
                        "status_badge": status_badge,
                        "evaluation_scope": "period" if is_period_accumulated else "monthly",
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
                        "goal_type": goal_type,
                        "evaluation_scope": "period" if is_period_accumulated else "monthly",
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
                elif goal_type == "per_residential_period_fixed":
                    all_met = bool(per_residential_results) and all(per_residential_results)
                    compliance_label = "Cumple" if all_met else "No cumple"
                    compliance_badge = "success" if all_met else "danger"

                if period_goal_value:
                    base_period_executed = period_global_executed if is_period_accumulated else period_counts_by_activity.get(activity_key, 0)
                    period_met = base_period_executed >= int(period_goal_value or 0)
                    period_compliance_label = "Cumple" if period_met else "No cumple"
                    period_compliance_badge = "success" if period_met else "danger"
                    period_missing = max(int(period_goal_value or 0) - base_period_executed, 0)
                    period_percentage = round((base_period_executed / int(period_goal_value or 0)) * 100, 2) if int(period_goal_value or 0) else 0
                else:
                    base_period_executed = period_global_executed if is_period_accumulated else period_counts_by_activity.get(activity_key, 0)

                summary_rows.append({
                    "proposal_code": proposal_code,
                    "proposal_name": proposal_name,
                    "activity_code": activity_code,
                    "activity_description": activity_description,
                    "month_label": "Período propuesta" if is_period_accumulated else month_label,
                    "goal_label": goal_label,
                    "goal_type": goal_type,
                    "goal_type_label": _goal_type_display_label(goal_type),
                    "global_executed": global_executed,
                    "display_executed": displayed_executed_total,
                    "global_goal": global_goal,
                    "period_executed": base_period_executed,
                    "period_goal": period_goal_value,
                    "period_missing": period_missing,
                    "period_percentage": period_percentage,
                    "period_compliance_label": period_compliance_label,
                    "period_compliance_badge": period_compliance_badge,
                    "compliance_label": compliance_label,
                    "compliance_badge": compliance_badge,
                    "residential_rows": detailed_rows,
                    "evaluation_scope": evaluation_scope,
                    "is_period_accumulated": is_period_accumulated,
                })

            for residential_bucket in residential_rollup.values():
                total_activities = residential_bucket["total_activities"]
                cumple = residential_bucket["cumple"]
                percentage = round((cumple / total_activities) * 100, 2) if total_activities else 0
                residential_summary_rows.append({
                    **residential_bucket,
                    "percentage": percentage,
                })

            residential_summary_rows.sort(key=lambda item: item["percentage"], reverse=True)

            total_activities_evaluated = len(summary_rows)
            if is_global:
                total_compliant = sum(
                    1
                    for item in summary_rows
                    if (item.get("period_compliance_label") if item.get("period_goal") is not None or item.get("is_period_accumulated") else item.get("compliance_label")) == "Cumple"
                )
                total_non_compliant = sum(
                    1
                    for item in summary_rows
                    if (item.get("period_compliance_label") if item.get("period_goal") is not None or item.get("is_period_accumulated") else item.get("compliance_label")) == "No cumple"
                )
            else:
                total_compliant = sum(1 for item in summary_rows if item.get("compliance_label") == "Cumple")
                total_non_compliant = sum(1 for item in summary_rows if item.get("compliance_label") == "No cumple")

            global_percentage = round((total_compliant / total_activities_evaluated) * 100, 2) if total_activities_evaluated else 0
            residentials_evaluated = len(residential_summary_rows)
            residentials_high = sum(1 for item in residential_summary_rows if item["percentage"] >= 80)
            residentials_medium = sum(1 for item in residential_summary_rows if 50 <= item["percentage"] < 80)
            residentials_low = sum(1 for item in residential_summary_rows if item["percentage"] < 50)

            if is_global:
                total_period_executed = sum(int(item.get("period_executed") or 0) for item in summary_rows if item.get("period_goal") is not None or item.get("is_period_accumulated"))
                total_period_goal = sum(int(item.get("period_goal") or 0) for item in summary_rows if item.get("period_goal"))
                total_period_missing = max(total_period_goal - total_period_executed, 0)
                total_period_percentage = round((total_period_executed / total_period_goal) * 100, 2) if total_period_goal else 0
                dashboard_cards = [
                    {"label": "Actividades evaluadas", "value": total_activities_evaluated, "tone": "primary", "subtitle": "Metas activas evaluadas"},
                    {"label": "Cumplen período", "value": total_compliant, "tone": "success", "subtitle": "Actividades en cumplimiento del período"},
                    {"label": "No cumplen período", "value": total_non_compliant, "tone": "danger", "subtitle": "Actividades rezagadas del período"},
                    {"label": "Ejecutado global acumulado", "value": total_period_executed, "tone": "info", "subtitle": "Total acumulado dentro del período aplicable"},
                    {"label": "Meta global del período", "value": total_period_goal, "tone": "secondary", "subtitle": "Meta acumulada configurada"},
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
                monthly_or_period_subtitle = "Incluye actividades acumuladas por período cuando aplique" if has_period_accumulated_goals else "Metas activas evaluadas este mes"
                dashboard_cards = [
                    {"label": "Actividades evaluadas", "value": total_activities_evaluated, "tone": "primary", "subtitle": monthly_or_period_subtitle},
                    {"label": "Cumplen", "value": total_compliant, "tone": "success", "subtitle": "Sin penalizar meses en acumuladas por período"},
                    {"label": "No cumplen", "value": total_non_compliant, "tone": "danger", "subtitle": "Solo según la lógica aplicable a cada modalidad"},
                    {"label": "% cumplimiento global", "value": f"{global_percentage}%", "tone": "info", "subtitle": "Avance consolidado de actividades"},
                    {"label": "Residenciales evaluados", "value": residentials_evaluated, "tone": "secondary", "subtitle": "Residenciales con actividad evaluada"},
                    {"label": "Residenciales alto/medio/bajo", "value": f"{residentials_high}/{residentials_medium}/{residentials_low}", "tone": "dark", "subtitle": "Segmentación por desempeño"},
                ]
                global_progress = {
                    "percentage": global_percentage,
                    "cumple": total_compliant,
                    "total": total_activities_evaluated,
                    "missing": max(total_activities_evaluated - total_compliant, 0),
                    "mode": "mixed" if has_period_accumulated_goals else "monthly",
                }

            compliance_distribution = [
                {"label": "Cumplen", "value": total_compliant, "percentage": global_percentage, "tone": "success"},
                {"label": "No cumplen", "value": total_non_compliant, "percentage": round((total_non_compliant / total_activities_evaluated) * 100, 2) if total_activities_evaluated else 0, "tone": "danger"},
            ]

            ranked_activities = []
            for item in summary_rows:
                if item["goal_type"] == "global_fixed":
                    target = int(item["global_goal"] or 0)
                    executed_for_progress = int(item.get("global_executed") or 0)
                elif item["goal_type"] == "per_residential_min_1":
                    target = len(item["residential_rows"])
                    executed_for_progress = int(item.get("global_executed") or 0)
                elif item["goal_type"] == "per_residential_fixed":
                    per_res_target = 0
                    if item["residential_rows"]:
                        per_res_target = max(int(item["residential_rows"][0].get("goal") or 0), 0)
                    target = len(item["residential_rows"]) * per_res_target
                    executed_for_progress = int(item.get("global_executed") or 0)
                elif item["goal_type"] == "per_residential_period_fixed":
                    per_res_target = 0
                    if item["residential_rows"]:
                        per_res_target = max(int(item["residential_rows"][0].get("goal") or 0), 0)
                    target = len(item["residential_rows"]) * per_res_target
                    executed_for_progress = int(item.get("display_executed") or 0)
                else:
                    target = 0
                    executed_for_progress = int(item.get("global_executed") or 0)

                progress_percentage = round((executed_for_progress / target) * 100, 2) if target else 0
                ranked_activities.append({
                    **item,
                    "target": target,
                    "progress_percentage": progress_percentage,
                })

            top_activities = [item for item in sorted(ranked_activities, key=lambda item: item["progress_percentage"], reverse=True) if int(item.get("display_executed") or item.get("global_executed") or 0) > 0][:5]
            bottom_activities = [item for item in sorted(ranked_activities, key=lambda item: (int(item.get("display_executed") or item.get("global_executed") or 0), item["progress_percentage"])) if int(item.get("display_executed") or item.get("global_executed") or 0) == 0][:5]
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
                        progress_percentage = round((executed / int(goal_value)) * 100, 2) if goal_value else 0
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
        "has_period_accumulated_goals": has_period_accumulated_goals,
        "proposal_period_label": _describe_period(proposal_period, month_lookup) if proposal_id and 'proposal_period' in locals() else None,
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
