from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.models.activity_code import ActivityCode
from app.models.activity_productivity_goal import ActivityProductivityGoal
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.proposal import Proposal
from app.models.proposal_report_program import ProposalReportProgram
from app.models.residential import Residential
from app.models.user import User
from app.services.consolidado_mensual_service import MONTH_NAMES
from app.services.report_programs import resolve_effective_program_population_blocks


PERIOD_TYPE_OPTIONS = [
    {"value": "monthly", "label": "Mensual"},
    {"value": "custom", "label": "Personalizado"},
]


def month_options() -> list[tuple[int, str]]:
    return [(idx, name.capitalize()) for idx, name in MONTH_NAMES.items()]


def base_context(db: Session) -> dict[str, Any]:
    return {
        "proposals": db.execute(select(Proposal).order_by(Proposal.code)).scalars().all(),
        "month_options": month_options(),
        "period_type_options": PERIOD_TYPE_OPTIONS,
        "year_options": list(range(date.today().year - 2, date.today().year + 3)),
    }


def describe_period(period_type: str, month: int | None, year: int | None, start_date: str | None, end_date: str | None) -> str:
    if period_type == "custom":
        return f"{start_date} a {end_date}" if start_date and end_date else "Periodo personalizado"
    if month and year:
        return f"{MONTH_NAMES.get(month, str(month))} {year}"
    return ""


def period_title(period_type: str, month: int | None, year: int | None, start_date: str | None, end_date: str | None) -> str:
    if period_type == "custom":
        return f"DESDE {start_date or ''} HASTA {end_date or ''}".strip()
    if month and year:
        return f"PARA EL MES DE {MONTH_NAMES.get(month, str(month)).upper()} {year}"
    return ""


def _apply_period(stmt, *, period_type: str, month: int | None, year: int | None, start_date: str | None, end_date: str | None):
    if period_type == "custom" and start_date and end_date:
        return stmt.where(ActivitySession.session_date >= date.fromisoformat(start_date), ActivitySession.session_date <= date.fromisoformat(end_date))
    if month and year:
        return stmt.where(
            func.month(ActivitySession.session_date) == month,
            func.year(ActivitySession.session_date) == year,
        )
    return stmt


def _report_end_date(*, period_type: str, month: int | None, year: int | None, end_date: str | None) -> date | None:
    if period_type == "custom" and end_date:
        return date.fromisoformat(end_date)
    if month and year:
        return date(year, month, monthrange(year, month)[1])
    return None


def _inclusive_months(start: date | None, end: date | None) -> int:
    if not start or not end or start > end:
        return 1
    return max(((end.year - start.year) * 12) + (end.month - start.month) + 1, 1)


def _goal_summary(goal: ActivityProductivityGoal | None) -> str:
    if not goal or not goal.is_active or goal.goal_type == "none":
        return "Sin meta productiva"
    parts: list[str] = []
    if goal.goal_type == "per_residential_min_1":
        parts.append("Según necesidad")
    elif goal.goal_type == "per_residential_fixed":
        parts.append(f"{goal.goal_value} / residencial / mes")
    elif goal.goal_type == "global_fixed":
        parts.append(f"{goal.goal_value} global / mes")
    elif goal.goal_type == "per_residential_period_fixed":
        parts.append(f"{goal.goal_value} / residencial / período")
    if goal.period_goal_value:
        parts.append(f"{goal.period_goal_value} global / período")
    return " + ".join(parts) if parts else "Sin meta productiva"


def _target_for_goal(goal: ActivityProductivityGoal | None, active_residential_count: int) -> int | None:
    if not goal or not goal.is_active or goal.goal_type == "none":
        return None
    if goal.period_goal_value:
        return int(goal.period_goal_value)
    if goal.goal_type == "per_residential_min_1":
        return 1
    if goal.goal_type == "per_residential_fixed":
        return int(goal.goal_value or 0) * active_residential_count
    if goal.goal_type == "global_fixed":
        return int(goal.goal_value or 0)
    if goal.goal_type == "per_residential_period_fixed":
        return int(goal.goal_value or 0) * active_residential_count
    return None


def _cumulative_target_for_goal(goal: ActivityProductivityGoal | None, active_residential_count: int, elapsed_months: int) -> int | None:
    if not goal or not goal.is_active or goal.goal_type == "none":
        return None

    if goal.period_goal_value:
        if goal.goal_type == "per_residential_period_fixed":
            return int(goal.period_goal_value)
        return int(goal.period_goal_value) * max(elapsed_months, 1)

    base_target = _target_for_goal(goal, active_residential_count)
    if base_target is None:
        return None
    return int(base_target) * max(elapsed_months, 1)


def _percent(executed: int, target: int | None) -> int | None:
    if target is None:
        return None
    if target <= 0:
        return 0
    return min(round((executed / target) * 100), 100)


def _format_achievement_text(activities_count: int, duplicados: int) -> str:
    if activities_count == 1:
        return f"Se realizó 1 actividad con una asistencia global de {duplicados} participantes."
    return f"Se realizaron {activities_count} actividades con una asistencia global de {duplicados} participantes."


def _format_cumulative_ratio(numerator: int, denominator: int | None) -> str:
    if denominator is None:
        return f"{numerator}"
    return f"{numerator}/{denominator}"


def build_hoja_cotejo_admin_context(
    db: Session,
    *,
    month: int | None,
    year: int | None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    proposal_id: int | None = None,
    authorized_name: str | None = None,
    current_user: User | None = None,
) -> dict[str, Any]:
    proposal = db.get(Proposal, proposal_id) if proposal_id else None
    active_residentials = db.execute(
        select(Residential)
        .where(Residential.is_active == True)  # noqa: E712
        .order_by(Residential.municipality, Residential.name)
    ).scalars().all()
    active_residential_count = max(len(active_residentials), 1)
    residential_names = ", ".join(residential.name for residential in active_residentials)

    program_blocks: list[dict[str, Any]] = []
    totals = {"activities_count": 0, "duplicados": 0, "met": 0, "not_met": 0, "rows": 0}
    report_end = _report_end_date(period_type=period_type, month=month, year=year, end_date=end_date)
    first_attendance_date: date | None = None
    elapsed_months = 1

    if proposal:
        structure_blocks = resolve_effective_program_population_blocks(db, proposal.proposal_id)
        activity_ids = sorted({
            row["activity_code_id"]
            for block in structure_blocks
            for population_block in block.get("population_blocks", [])
            for row in population_block.get("rows", [])
        })

        sessions_by_activity: dict[int, int] = {}
        attendance_by_activity: dict[int, int] = {}
        unique_by_activity: dict[int, int] = {}
        cumulative_sessions_by_activity: dict[int, int] = {}
        goals_by_activity: dict[int, ActivityProductivityGoal] = {}

        if activity_ids:
            first_attendance_stmt = (
                select(func.min(ActivitySession.session_date))
                .join(Attendance, Attendance.session_id == ActivitySession.session_id)
                .where(
                    ActivitySession.proposal_id == proposal.proposal_id,
                    Attendance.attended == True,  # noqa: E712
                )
            )
            if report_end:
                first_attendance_stmt = first_attendance_stmt.where(ActivitySession.session_date <= report_end)
            first_attendance_date = db.execute(first_attendance_stmt).scalar_one_or_none()
            elapsed_months = _inclusive_months(first_attendance_date, report_end)

            session_stmt = (
                select(ActivitySession.activity_code_id, func.count(distinct(ActivitySession.session_id)))
                .where(ActivitySession.proposal_id == proposal.proposal_id, ActivitySession.activity_code_id.in_(activity_ids))
                .group_by(ActivitySession.activity_code_id)
            )
            session_stmt = _apply_period(session_stmt, period_type=period_type, month=month, year=year, start_date=start_date, end_date=end_date)
            sessions_by_activity = {activity_id: int(count or 0) for activity_id, count in db.execute(session_stmt).all()}

            attendance_stmt = (
                select(
                    ActivitySession.activity_code_id,
                    func.count(Attendance.attendance_id),
                    func.count(distinct(func.coalesce(Attendance.proposal_participant_id, Attendance.participant_id))),
                )
                .join(Attendance, Attendance.session_id == ActivitySession.session_id)
                .where(
                    ActivitySession.proposal_id == proposal.proposal_id,
                    ActivitySession.activity_code_id.in_(activity_ids),
                    Attendance.attended == True,  # noqa: E712
                )
                .group_by(ActivitySession.activity_code_id)
            )
            attendance_stmt = _apply_period(attendance_stmt, period_type=period_type, month=month, year=year, start_date=start_date, end_date=end_date)
            for activity_id, duplicados, unique_count in db.execute(attendance_stmt).all():
                attendance_by_activity[activity_id] = int(duplicados or 0)
                unique_by_activity[activity_id] = int(unique_count or 0)

            cumulative_stmt = (
                select(ActivitySession.activity_code_id, func.count(distinct(ActivitySession.session_id)))
                .join(Attendance, Attendance.session_id == ActivitySession.session_id)
                .where(
                    ActivitySession.proposal_id == proposal.proposal_id,
                    ActivitySession.activity_code_id.in_(activity_ids),
                    Attendance.attended == True,  # noqa: E712
                )
                .group_by(ActivitySession.activity_code_id)
            )
            if first_attendance_date:
                cumulative_stmt = cumulative_stmt.where(ActivitySession.session_date >= first_attendance_date)
            if report_end:
                cumulative_stmt = cumulative_stmt.where(ActivitySession.session_date <= report_end)
            cumulative_sessions_by_activity = {activity_id: int(count or 0) for activity_id, count in db.execute(cumulative_stmt).all()}

            goal_rows = db.execute(
                select(ActivityProductivityGoal).where(
                    ActivityProductivityGoal.proposal_id == proposal.proposal_id,
                    ActivityProductivityGoal.activity_code_id.in_(activity_ids),
                    ActivityProductivityGoal.is_active == True,  # noqa: E712
                )
            ).scalars().all()
            goals_by_activity = {goal.activity_code_id: goal for goal in goal_rows}

        for block in structure_blocks:
            program: ProposalReportProgram = block["program"]
            rows: list[dict[str, Any]] = []
            seen_activity_ids: set[int] = set()
            for population_block in block.get("population_blocks", []):
                for row in population_block.get("rows", []):
                    activity_id = int(row["activity_code_id"])
                    if activity_id in seen_activity_ids:
                        continue
                    seen_activity_ids.add(activity_id)
                    activities_count = sessions_by_activity.get(activity_id, 0)
                    duplicados = attendance_by_activity.get(activity_id, 0)
                    unique_participants = unique_by_activity.get(activity_id, 0)
                    goal = goals_by_activity.get(activity_id)
                    target = _target_for_goal(goal, active_residential_count)
                    cumulative_activities = cumulative_sessions_by_activity.get(activity_id, 0)
                    cumulative_target = _cumulative_target_for_goal(goal, active_residential_count, elapsed_months)
                    monthly_percent = _percent(activities_count, target)
                    percent = _percent(cumulative_activities, cumulative_target)
                    met = bool(cumulative_target is not None and cumulative_activities >= cumulative_target)
                    rows.append({
                        "activity_code_id": activity_id,
                        "activity_code": row.get("activity_code", ""),
                        "activity_description": row.get("activity_description", ""),
                        "achievement_text": _format_achievement_text(activities_count, duplicados),
                        "activities_count": activities_count,
                        "duplicados": duplicados,
                        "unique_participants": unique_participants,
                        "goal_summary": _goal_summary(goal),
                        "goal_target": target,
                        "monthly_percent": monthly_percent,
                        "cumulative_activities": cumulative_activities,
                        "cumulative_target": cumulative_target,
                        "cumulative_ratio": _format_cumulative_ratio(cumulative_activities, cumulative_target),
                        "percent": percent,
                        "met": met,
                    })
                    totals["activities_count"] += activities_count
                    totals["duplicados"] += duplicados
                    totals["rows"] += 1
                    if target is not None:
                        totals["met" if met else "not_met"] += 1

            program_blocks.append({
                "program": program,
                "program_display_name": (getattr(program, "name", None) or getattr(program, "code", "")).strip(),
                "program_code": program.code,
                "rows": rows,
                "program_activities_count": sum(int(row["activities_count"] or 0) for row in rows),
                "program_duplicados": sum(int(row["duplicados"] or 0) for row in rows),
            })

    context = {
        **base_context(db),
        "title": "Hoja de Cotejo",
        "proposal": proposal,
        "selected_proposal_id": proposal_id,
        "selected_month": month,
        "selected_year": year,
        "month": month,
        "year": year,
        "selected_period_type": period_type,
        "selected_start_date": start_date or "",
        "selected_end_date": end_date or "",
        "period_label": describe_period(period_type, month, year, start_date, end_date),
        "period_title": period_title(period_type, month, year, start_date, end_date),
        "authorized_name": (authorized_name or "").strip(),
        "current_user": current_user,
        "msg": None,
        "program_blocks": program_blocks,
        "residential_names": residential_names,
        "active_residential_count": active_residential_count,
        "first_attendance_date": first_attendance_date,
        "elapsed_months": elapsed_months,
        "totals": totals,
        "pdf_template_name": "ui/admin/hoja_cotejo_pdf.html",
    }
    return context
