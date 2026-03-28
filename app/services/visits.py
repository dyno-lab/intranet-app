from __future__ import annotations

from datetime import date
from typing import Callable, Any

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.visit_activity_mapping import VisitActivityMapping


ScopeResolver = Callable[[Any | None], str]


def resolve_visit_activity_ids(db: Session, proposal_id: int | None) -> list[int]:
    if not proposal_id:
        return []
    return db.execute(
        select(VisitActivityMapping.activity_code_id)
        .where(
            VisitActivityMapping.proposal_id == proposal_id,
            VisitActivityMapping.is_active == True,
        )
    ).scalars().all()  # noqa: E712


def query_visit_sessions(
    db: Session,
    proposal_id: int,
    mapped_activity_ids: list[int],
    period: dict,
    apply_period_filter: Callable,
    *,
    is_global: bool,
    selected_user_id: int | None,
):
    if not proposal_id or not mapped_activity_ids:
        return []

    stmt = (
        select(
            ActivitySession.session_id,
            ActivitySession.employee_id,
            Employee.full_name,
            func.coalesce(ActivitySession.hours, 0).label("hours"),
            ActivitySession.created_by_user_id,
        )
        .join(Employee, Employee.employee_id == ActivitySession.employee_id)
        .where(
            ActivitySession.proposal_id == proposal_id,
            ActivitySession.activity_code_id.in_(mapped_activity_ids),
        )
        .order_by(Employee.full_name)
    )
    stmt = apply_period_filter(stmt, period)

    if not is_global and selected_user_id:
        stmt = stmt.where(ActivitySession.created_by_user_id == selected_user_id)

    return db.execute(stmt).all()


def build_visit_attendance_map(db: Session, session_ids: list[int]) -> dict[int, int]:
    if not session_ids:
        return {}

    attendance_stmt = (
        select(
            Attendance.session_id,
            func.count(Attendance.attendance_id).label("attendances"),
        )
        .where(
            Attendance.attended == True,
            Attendance.session_id.in_(session_ids),
        )
        .group_by(Attendance.session_id)
    )  # noqa: E712

    return {
        session_id: int(attendance_count or 0)
        for session_id, attendance_count in db.execute(attendance_stmt).all()
    }


def calculate_visits_rows_and_summary(
    session_rows,
    attendance_map: dict[int, int],
    *,
    is_global: bool,
    user_residential_map: dict[int, str],
):
    employee_summary: dict[tuple, dict] = {}

    for session_id, employee_id_value, employee_name, hours, created_by_user_id in session_rows:
        residential_label = user_residential_map.get(created_by_user_id, "Sin residencial") if is_global else ""
        summary_key = (employee_id_value, residential_label if is_global else "")
        bucket = employee_summary.setdefault(
            summary_key,
            {
                "employee_id": employee_id_value,
                "employee_name": employee_name,
                "residential_name": residential_label if is_global else "",
                "visits": 0,
                "attendances": 0,
                "hours": 0.0,
            },
        )
        bucket["visits"] += 1
        bucket["attendances"] += attendance_map.get(session_id, 0)
        bucket["hours"] += float(hours or 0)

    rows = sorted(employee_summary.values(), key=lambda row: row["employee_name"])
    for row in rows:
        row["hours"] = round(row["hours"], 2)

    summary = {
        "visits": sum(row["visits"] for row in rows),
        "attendances": sum(row["attendances"] for row in rows),
        "hours": round(sum(row["hours"] for row in rows), 2),
    }

    return rows, summary
