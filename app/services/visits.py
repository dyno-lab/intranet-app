from __future__ import annotations

from datetime import date
from typing import Callable, Any

from app.models.user import User

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.employee import Employee
from app.models.visit_activity_mapping import VisitActivityMapping
from app.models.visit_report import VisitReport
from app.models.visit_report_referral import VisitReportReferral


ScopeResolver = Callable[[Any | None], str]


def resolve_report_scope(current_user: User, employee_id: int | None, db: Session):
    selected_user = None
    is_global = False
    resolved_employee_id = employee_id

    if current_user.role in {"admin", "supervisor"}:
        if employee_id == 0:
            is_global = True
        elif employee_id:
            selected_user = db.get(User, employee_id)
    else:
        selected_user = current_user
        resolved_employee_id = current_user.user_id

    return {
        "selected_user": selected_user,
        "is_global": is_global,
        "employee_id": resolved_employee_id,
    }


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


def get_visit_report(
    db: Session,
    *,
    proposal_id: int,
    report_month: int,
    report_year: int,
    created_by_user_id: int | None,
):
    stmt = select(VisitReport).where(
        VisitReport.proposal_id == proposal_id,
        VisitReport.report_month == report_month,
        VisitReport.report_year == report_year,
    )
    if created_by_user_id is None:
        stmt = stmt.where(VisitReport.created_by_user_id.is_(None))
    else:
        stmt = stmt.where(VisitReport.created_by_user_id == created_by_user_id)
    return db.execute(stmt).scalar_one_or_none()


def get_visit_reports(
    db: Session,
    *,
    proposal_id: int,
    report_month: int,
    report_year: int,
):
    return db.execute(
        select(VisitReport).where(
            VisitReport.proposal_id == proposal_id,
            VisitReport.report_month == report_month,
            VisitReport.report_year == report_year,
        )
    ).scalars().all()


def get_visit_referrals(db: Session, report_id: int):
    return db.execute(
        select(VisitReportReferral)
        .where(VisitReportReferral.report_id == report_id)
        .order_by(VisitReportReferral.sort_order, VisitReportReferral.referral_id)
    ).scalars().all()


def get_visit_referrals_for_reports(db: Session, report_ids: list[int]):
    if not report_ids:
        return []
    return db.execute(
        select(VisitReportReferral)
        .where(VisitReportReferral.report_id.in_(report_ids))
        .order_by(VisitReportReferral.report_id, VisitReportReferral.sort_order, VisitReportReferral.referral_id)
    ).scalars().all()


def get_or_create_visit_report(
    db: Session,
    *,
    proposal_id: int,
    report_month: int,
    report_year: int,
    created_by_user_id: int | None,
):
    visit_report = get_visit_report(
        db,
        proposal_id=proposal_id,
        report_month=report_month,
        report_year=report_year,
        created_by_user_id=created_by_user_id,
    )
    if visit_report:
        return visit_report

    visit_report = VisitReport(
        proposal_id=proposal_id,
        report_month=report_month,
        report_year=report_year,
        created_by_user_id=created_by_user_id,
    )
    db.add(visit_report)
    db.flush()
    return visit_report


def replace_visit_report_referrals(db: Session, report_id: int, referral_payloads: list[dict]):
    existing_referrals = db.execute(
        select(VisitReportReferral).where(VisitReportReferral.report_id == report_id)
    ).scalars().all()
    for referral in existing_referrals:
        db.delete(referral)
    db.flush()

    for idx, payload in enumerate(referral_payloads):
        referral_type = (payload.get("referral_type") or "").strip()
        agency = (payload.get("agency") or "").strip()
        reference_or_purpose = (payload.get("reference_or_purpose") or "").strip()

        if not referral_type and not agency and not reference_or_purpose:
            continue

        description = " | ".join(part for part in [agency, reference_or_purpose] if part).strip() or referral_type or "Referido"
        referral = VisitReportReferral(
            report_id=report_id,
            referral_type=referral_type or "Externo",
            description=description,
            agency=agency or None,
            reference_or_purpose=reference_or_purpose or None,
            sort_order=idx,
        )
        db.add(referral)


def delete_visit_reports_and_referrals(db: Session, reports: list[VisitReport]):
    if not reports:
        return

    report_ids = [report.report_id for report in reports]
    referrals = get_visit_referrals_for_reports(db, report_ids)
    for referral in referrals:
        db.delete(referral)
    db.flush()
    for report in reports:
        db.delete(report)


def delete_visit_referrals_only(db: Session, reports: list[VisitReport]):
    if not reports:
        return

    report_ids = [report.report_id for report in reports]
    referrals = get_visit_referrals_for_reports(db, report_ids)
    for referral in referrals:
        db.delete(referral)
    db.flush()


def build_visits_report_payload(
    db: Session,
    *,
    proposal_id: int | None,
    period: dict,
    selected_user,
    is_global: bool,
    user_residential_map: dict[int, str],
    residential_name_resolver: Callable,
    apply_period_filter: Callable,
):
    residential_name = None
    rows = []
    summary = {"visits": 0, "attendances": 0, "hours": 0.0}
    mapped_activity_ids: list[int] = []
    visit_report = None
    referral_rows = []
    referral_count = 0

    if not (proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global)):
        return {
            "residential_name": residential_name,
            "rows": rows,
            "summary": summary,
            "mapped_activity_ids": mapped_activity_ids,
            "visit_report": visit_report,
            "referral_rows": referral_rows,
            "referral_count": referral_count,
        }

    mapped_activity_ids = resolve_visit_activity_ids(db, proposal_id)

    if is_global:
        residential_name = "Global"
        visit_reports = get_visit_reports(
            db,
            proposal_id=proposal_id,
            report_month=period["month"],
            report_year=period["year"],
        )
        report_ids = [report.report_id for report in visit_reports]
        if report_ids:
            report_residential_map = {
                report.report_id: user_residential_map.get(report.created_by_user_id, "Global")
                for report in visit_reports
            }
            referrals = get_visit_referrals_for_reports(db, report_ids)
            referral_rows = [
                {
                    "residential_name": report_residential_map.get(referral.report_id, "Global"),
                    "referral_type": referral.referral_type,
                    "agency": referral.agency or "",
                    "reference_or_purpose": referral.reference_or_purpose or "",
                }
                for referral in referrals
            ]
            referral_count = len(referral_rows)
    else:
        residential_name = residential_name_resolver(selected_user)
        report_owner_user_id = selected_user.user_id
        visit_report = get_visit_report(
            db,
            proposal_id=proposal_id,
            report_month=period["month"],
            report_year=period["year"],
            created_by_user_id=report_owner_user_id,
        )
        if visit_report:
            referrals = get_visit_referrals(db, visit_report.report_id)
            referral_rows = [
                {
                    "referral_type": referral.referral_type,
                    "agency": referral.agency or "",
                    "reference_or_purpose": referral.reference_or_purpose or "",
                }
                for referral in referrals
            ]
            referral_count = len(referral_rows)

    if mapped_activity_ids:
        session_rows = query_visit_sessions(
            db,
            proposal_id,
            mapped_activity_ids,
            period,
            apply_period_filter,
            is_global=is_global,
            selected_user_id=selected_user.user_id if selected_user else None,
        )

        session_ids = [row[0] for row in session_rows]
        attendance_map = build_visit_attendance_map(db, session_ids)
        rows, summary = calculate_visits_rows_and_summary(
            session_rows,
            attendance_map,
            is_global=is_global,
            user_residential_map=user_residential_map,
        )

    return {
        "residential_name": residential_name,
        "rows": rows,
        "summary": summary,
        "mapped_activity_ids": mapped_activity_ids,
        "visit_report": visit_report,
        "referral_rows": referral_rows,
        "referral_count": referral_count,
    }
