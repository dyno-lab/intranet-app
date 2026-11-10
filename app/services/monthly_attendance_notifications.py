"""Computed pending confirmations, including residences with no activity.

Read four small tracking/catalog tables, without an attendance query per month.
Transactional revisions invalidate confirmations on every operational writer;
the detailed monthly page additionally verifies the attendance fingerprint.
"""
from datetime import date
from sqlalchemy import select
from app.core.period_guard import format_reporting_period, is_proposal_period_locked, next_period_start
from app.core.proposal_guard import is_proposal_finalized
from app.models.monthly_attendance import AttendanceMonth, AttendanceMonthResidential, MonthlyAttendanceSettings
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.services.monthly_attendance import scope_id, default_due_date, month_url


def monthly_notification(db, user, *, today=None):
    if user.role not in {"admin", "supervisor", "user"}:
        return None
    today = today or date.today()
    rid = scope_id(user)
    settings = db.get(MonthlyAttendanceSettings, 1)
    if settings is None:
        return None
    proposals = list(db.scalars(select(Proposal).where(Proposal.is_active == True)))
    proposals = [p for p in proposals if not is_proposal_finalized(p)]
    ids = [p.proposal_id for p in proposals]
    periods = {(p.proposal_id, p.report_year, p.report_month): p for p in db.scalars(
        select(AttendanceMonth).where(AttendanceMonth.proposal_id.in_(ids)))}
    query = select(AttendanceMonthResidential).where(AttendanceMonthResidential.proposal_id.in_(ids))
    if rid is not None:
        query = query.where(AttendanceMonthResidential.residential_id == rid)
    records = {}
    for record in db.scalars(query):
        records.setdefault((record.proposal_id, record.report_year, record.report_month), {})[record.residential_id] = record
    residential_query = select(Residential)
    if rid is not None:
        residential_query = residential_query.where(Residential.residential_id == rid)
    residentials = {r.residential_id: r for r in db.scalars(residential_query)}
    active_ids = {r.residential_id for r in residentials.values() if r.is_active}
    months = set()
    cursor = settings.first_month
    while cursor < today.replace(day=1):
        months.add((cursor.year, cursor.month))
        cursor = next_period_start(cursor.month, cursor.year)
    details = []
    for proposal in proposals:
        candidates = months | {(y, m) for pid, y, m in periods if pid == proposal.proposal_id and (y, m) <= (today.year, today.month)}
        for year, month in sorted(candidates, reverse=True):
            if is_proposal_period_locked(proposal, month, year):
                continue
            period = periods.get((proposal.proposal_id, year, month))
            rows = records.get((proposal.proposal_id, year, month), {})
            expected = {r.residential_id for r in rows.values() if r.is_included} if period else active_ids
            due = period.due_on if period else default_due_date(year, month)
            for residence in sorted(expected):
                record = rows.get(residence)
                if record and record.confirmed_at and record.confirmed_revision == record.revision:
                    continue
                residential = residentials.get(residence)
                if not residential:
                    continue
                details.append({"residential_id": residence, "residential": residential.name,
                    "year": year, "month": month, "period": format_reporting_period(month, year),
                    "pending_count": 1, "context": f"Propuesta {proposal.code} · Fecha límite {due.strftime('%d/%m/%Y')}"
                        + (" · Plazo vencido" if today > due else "")
                        + (" · Requiere nueva confirmación" if record and record.confirmed_at else ""),
                    "actions": [{"label": "Revisar confirmación mensual", "url": month_url(proposal.proposal_id, year, month)}]})
    if not details:
        return None
    return {"id": "attendance:monthly", "type": "task", "title": "Confirmación mensual de asistencias",
        "message": "Hay residenciales pendientes de confirmar que terminaron de registrar todas las asistencias del mes.",
        "count_label": "confirmación pendiente" if len(details) == 1 else "confirmaciones pendientes",
        "note": "Revisa el período y confirma cuando termines. Los meses sin actividad requieren una declaración y justificación.",
        "unread": True, "pending_count": len(details), "residential_count": len({g["residential_id"] for g in details}),
        "groups": details}
