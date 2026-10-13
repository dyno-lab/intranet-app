"""Monthly referral requirements, independent of the configurable visits summary."""
from datetime import date
from urllib.parse import urlencode

from sqlalchemy import extract, func, select

from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.visit_report import VisitReport
from app.models.visit_report_referral import VisitReportReferral
from app.core.period_guard import MONTH_LABELS


REFERRAL_ACTIVITY_CODES = (
    "1.a.3", "1.b.3", "1.c.3", "1.a.10", "1.b.10", "1.c.10",
    "2.a.3", "2.b.3", "2.c.3", "2.e.3",
    "3.a.3", "3.b.3", "3.c.3", "3.d.3",
    "3.a.11", "3.b.11", "3.c.11", "3.d.11",
    "3.a.21", "3.b.21", "3.c.21", "3.d.21", "3.e.21", "3.f.21", "3.g.21",
    "4.a.3", "4.b.3", "4.c.3", "4.d.3", "4.e.3", "4.f.3", "4.g.3",
)
REFERRAL_TYPES = ("Interno", "Externo", "Visita Agencia")
MAX_REFERRAL_ROWS = 20


def _trimmed(column):
    value = func.coalesce(column, "")
    for char in ("\t", "\r", "\n"):
        value = func.replace(value, char, " ")
    return func.ltrim(func.rtrim(value))


def pending_referral_groups(db, *, residential_id=None, proposal_ids=None, month=None, year=None, today=None):
    """One pending report per proposal/residential/month with confirmed attendance.

    A complete existing referral of any supported type resolves that report.
    Empty reports and partial legacy rows never resolve it. No report is created
    just by reading notifications; the existing visits editor owns writes.
    """
    today = today or date.today()
    report_year = extract("year", ActivitySession.session_date)
    report_month = extract("month", ActivitySession.session_date)
    confirmed = select(Attendance.attendance_id).where(
        Attendance.session_id == ActivitySession.session_id,
        Attendance.attended == True, Attendance.participant_id.is_not(None),  # noqa: E712
    ).correlate(ActivitySession).exists()
    complete_referral = select(VisitReportReferral.referral_id).join(
        VisitReport, VisitReport.report_id == VisitReportReferral.report_id).where(
        VisitReport.proposal_id == ActivitySession.proposal_id,
        VisitReport.residential_id == ActivitySession.residential_id,
        VisitReport.report_year == report_year, VisitReport.report_month == report_month,
        func.lower(_trimmed(VisitReportReferral.referral_type)).in_([kind.lower() for kind in REFERRAL_TYPES]),
        _trimmed(VisitReportReferral.agency) != "",
        _trimmed(VisitReportReferral.reference_or_purpose) != "",
    ).correlate(ActivitySession).exists()
    statement = select(
        Residential.residential_id, Residential.name.label("residential"), ActivitySession.proposal_id,
        Proposal.code.label("proposal_code"), Proposal.name.label("proposal_name"),
        report_year.label("year"), report_month.label("month"), func.lower(ActivityCode.code).label("activity_code"),
    ).select_from(ActivitySession).join(ActivityCode, ActivityCode.activity_code_id == ActivitySession.activity_code_id).join(
        Residential, Residential.residential_id == ActivitySession.residential_id).outerjoin(
        Proposal, Proposal.proposal_id == ActivitySession.proposal_id).where(
        Residential.is_active == True,  # noqa: E712
        func.lower(ActivityCode.code).in_(REFERRAL_ACTIVITY_CODES), ActivitySession.session_date <= today,
        confirmed, ~complete_referral,
    ).distinct()
    if residential_id is not None:
        statement = statement.where(Residential.residential_id == residential_id)
    if proposal_ids is not None:
        statement = statement.where(ActivitySession.proposal_id.in_(proposal_ids))
    if month is not None:
        statement = statement.where(report_month == month)
    if year is not None:
        statement = statement.where(report_year == year)
    groups = {}
    for row in db.execute(statement):
        key = (row.residential_id, row.proposal_id, int(row.year), int(row.month))
        if key not in groups:
            proposal_label = f"{row.proposal_code} - {row.proposal_name}" if row.proposal_id else "Sin propuesta"
            groups[key] = dict(residential_id=key[0], proposal_id=key[1], year=key[2], month=key[3],
                               residential=row.residential, proposal=proposal_label,
                               period=f"{MONTH_LABELS[key[3]].capitalize()} {key[2]}",
                               pending_count=1, activity_codes=[])
        groups[key]["activity_codes"].append(row.activity_code)
    result = sorted(groups.values(), key=lambda g: (-g["year"], -g["month"], g["residential"].casefold(), g["proposal"]))
    for group in result:
        group["activity_codes"].sort()
        group["context"] = f"Propuesta: {group['proposal']} · Actividades: {', '.join(group['activity_codes'])}"
        group["needs_proposal"] = group["proposal_id"] is None
        group["actions"] = [{"label": "Revisar asistencias sin propuesta", "url": "/ui/listado"}] if group["needs_proposal"] else [{
            "label": "Completar referidos",
            "url": "/ui/reports/visitas?" + urlencode({"proposal_id": group["proposal_id"],
                "employee_id": -group["residential_id"], "month": group["month"], "year": group["year"],
                "period_type": "monthly"}) + "#visit-referrals",
        }]
    return result
