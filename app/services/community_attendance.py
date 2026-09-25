"""Community session search, fiscal rosters and corrections; callers own transactions."""
from datetime import date, timedelta
import json

from sqlalchemy import String, cast, delete, extract, func, literal, select
from sqlalchemy.orm import Session

from app.models.community import CPFiscalYear, CPProgram
from app.models.community_activity import CPActivity, CPFiscalActivity
from app.models.community_fiscal import CPFiscalEnrollment, CPFiscalParticipant, CPFiscalState
from app.models.community_operations import CPActivitySession, CPAttendance
from app.models.user import User
from app.services.community import _date, _text
from app.services.community_fiscal import require_fiscal_writable
from app.services.community_operations import _activity_context, enrolled_participant_ids, parse_duration_minutes, writable_session
from app.services.community_reports import age_at

MONTHS = tuple(enumerate(("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"), 1))


def session_filters(params, context) -> dict:
    def number(key, low, high):
        raw = (params.get(key) or "").strip()
        if raw in ("", "0"):
            return None
        try:
            value = int(raw)
        except ValueError:
            raise ValueError("Los filtros numéricos no son válidos.") from None
        if not low <= value <= high:
            raise ValueError("Los filtros numéricos están fuera de rango.")
        return value

    result = {"fiscal_year_id": number("fiscal_year_id", 1, 2147483647),
              "program_id": number("program_id", 1, 2147483647) or context.selected_program_id,
              "month": number("month", 1, 12), "year": number("year", 1000, 9999),
              "control_number": (params.get("control_number") or "").strip()[:64]}
    for key in ("from_date", "to_date"):
        raw = params.get(key) or ""
        try:
            result[key] = date.fromisoformat(raw) if raw else None
        except ValueError:
            raise ValueError("Seleccione fechas de filtro válidas.") from None
    if result["from_date"] and result["to_date"] and result["from_date"] > result["to_date"]:
        raise ValueError("La fecha Desde no puede ser posterior a Hasta.")
    return result


def filtered_sessions(context, filters):
    query = select(CPActivitySession.session_id).where(CPActivitySession.program_id.in_(context.visible_program_ids))
    for name in ("fiscal_year_id", "program_id"):
        if filters[name] is not None:
            query = query.where(getattr(CPActivitySession, name) == filters[name])
    for name in ("month", "year"):
        if filters[name] is not None:
            query = query.where(extract(name, CPActivitySession.session_date) == filters[name])
    if filters["from_date"]:
        query = query.where(CPActivitySession.session_date >= filters["from_date"])
    if filters["to_date"]:
        query = query.where(CPActivitySession.session_date <= filters["to_date"])
    if filters["control_number"]:
        control = literal("CP-") + cast(CPActivitySession.session_id, String(20))
        query = query.where(control.contains(filters["control_number"], autoescape=True))
    return query


def session_rows(query):
    counts = select(CPAttendance.session_id, func.count().label("participations")).where(
        CPAttendance.is_present == True,  # noqa: E712
    ).group_by(CPAttendance.session_id).subquery()
    return select(CPActivitySession, CPProgram, CPActivity, CPFiscalYear, User.username,
                  func.coalesce(counts.c.participations, 0).label("participations")).join(
        CPProgram, CPProgram.program_id == CPActivitySession.program_id
    ).join(CPActivity, CPActivity.activity_id == CPActivitySession.activity_id).join(
        CPFiscalYear, CPFiscalYear.fiscal_year_id == CPActivitySession.fiscal_year_id
    ).join(User, User.user_id == CPActivitySession.created_by_user_id).outerjoin(
        counts, counts.c.session_id == CPActivitySession.session_id
    ).where(CPActivitySession.session_id.in_(query)).order_by(CPActivitySession.session_date.desc(), CPActivitySession.session_id.desc())


def session_metrics(db, query) -> dict:
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    participations, unique = db.execute(select(func.count(), func.count(func.distinct(CPAttendance.participant_id)))
                                        .where(CPAttendance.session_id.in_(query), CPAttendance.is_present == True)).one()  # noqa: E712
    return dict(total_activities=total, total_participations=participations, unique_participants=unique)


def available_activities(db, fiscal_year_id: int, program_id: int):
    return db.scalars(select(CPActivity).join(CPFiscalActivity, CPFiscalActivity.activity_id == CPActivity.activity_id)
                      .where(CPFiscalActivity.fiscal_year_id == fiscal_year_id,
                             CPFiscalActivity.program_id == program_id, CPActivity.program_id == program_id,
                             CPFiscalActivity.is_active == True, CPActivity.is_active == True)  # noqa: E712
                      .order_by(CPActivity.code)).all()


def fiscal_date_options(db, years):
    states = {state.fiscal_year_id: state for state in db.scalars(select(CPFiscalState))}
    result = {}
    for year in years:
        first, last = year.start_date, min(year.end_date, date.today())
        state = states.get(year.fiscal_year_id)
        fully_locked = bool(state and state.locked_through and state.locked_through >= year.end_date)
        if state and state.locked_through and not fully_locked:
            first = max(first, state.locked_through + timedelta(days=1))
        result[year.fiscal_year_id] = dict(min=first, max=last,
                                         closed=not year.is_active or year.status != "active" or fully_locked or first > last)
    return result


def session_roster(db, session):
    enrolled = select(CPFiscalEnrollment.participant_id).where(
        CPFiscalEnrollment.fiscal_year_id == session.fiscal_year_id, CPFiscalEnrollment.program_id == session.program_id)
    saved = select(CPAttendance.participant_id).where(CPAttendance.session_id == session.session_id)
    eligible = set(enrolled_participant_ids(db, session.fiscal_year_id, session.program_id, session.session_date))
    rows = db.scalars(select(CPFiscalParticipant).where(CPFiscalParticipant.fiscal_year_id == session.fiscal_year_id,
                                                       CPFiscalParticipant.participant_id.in_(enrolled.union(saved)))).all()
    participants = []
    for row in rows:
        data = json.loads(row.snapshot_json)
        participants.append({**data, "participant_id": row.participant_id,
                             "age": age_at(data.get("fecha_nacimiento"), date.today()),
                             "eligible": row.participant_id in eligible})
    participants.sort(key=lambda row: (row.get("apellido_paterno", ""), row.get("nombre", ""), row["participant_id"]))
    return participants, eligible


def edit_session(db: Session, *, session_id: int, fiscal_year_id: int, program_id: int, activity_id: int,
                 session_date: date, duration_minutes=None, notes: str | None = None):
    session = writable_session(db, session_id, target_fiscal_year_id=fiscal_year_id)
    day = _date(session_date, "Fecha de actividad")
    minutes = parse_duration_minutes(duration_minutes)
    notes = _text(notes, "Observaciones", 500)
    require_fiscal_writable(db, fiscal_year_id, day)
    attendance = db.scalars(select(CPAttendance).where(CPAttendance.session_id == session_id)).all()
    if attendance and (program_id, fiscal_year_id) != (session.program_id, session.fiscal_year_id):
        raise ValueError("Una sesión con asistencias guardadas conserva su programa y año fiscal.")
    _activity_context(db, fiscal_year_id, program_id, activity_id)
    present = {row.participant_id for row in attendance if row.is_present}
    eligible = set(enrolled_participant_ids(db, fiscal_year_id, program_id, day))
    if not present.issubset(eligible):
        raise ValueError("La fecha dejaría participantes con asistencia fuera de su período de matrícula. Deben seguir siendo elegibles.")
    # Core UPDATE avoids SQL Server driver's -1 rowcount being mistaken for a stale ORM row.
    table = CPActivitySession.__table__
    db.execute(table.update().where(table.c.session_id == session_id).values(
        fiscal_year_id=fiscal_year_id, program_id=program_id, activity_id=activity_id,
        session_date=day, duration_minutes=minutes, notes=notes))
    db.expire(session)
    return session


def clear_session(db: Session, *, session_id: int, delete_session: bool = False):
    session = writable_session(db, session_id)
    db.execute(delete(CPAttendance).where(CPAttendance.session_id == session_id))
    if delete_session:
        db.execute(delete(CPActivitySession).where(CPActivitySession.session_id == session_id))
    db.flush()
    return session
