"""Monthly confirmation, scoped follow-up and transactional invalidation.

GETs compute pending rows without changing attendance or creating confirmations.
All writers lock the same proposal/month before changing sessions or attendance.
"""
import hashlib
import hmac
import json
from datetime import date, timedelta, timezone
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import and_, inspect, select, text
from sqlalchemy.orm.attributes import set_committed_value

from app.core.period_guard import format_reporting_period, is_proposal_period_locked, next_period_start, normalize_reporting_period
from app.core.proposal_guard import is_proposal_finalized
from app.core.residential_scope import has_global_residential_access
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.monthly_attendance import AttendanceMonth, AttendanceMonthEvent, AttendanceMonthResidential, utcnow
from app.models.notification import FaroAnnouncement, FaroAnnouncementResidential, FaroAnnouncementRole
from app.models.proposal import Proposal
from app.models.residential import Residential


def default_due_date(year, month):
    return next_period_start(month, year).replace(day=10)


def previous_month(today=None):
    day = (today or date.today()).replace(day=1) - timedelta(days=1)
    return day.year, day.month


def scope_id(user):
    if has_global_residential_access(user):
        return None
    residential_id = getattr(user, '_active_residential_id', None)
    if not residential_id:
        raise HTTPException(403, 'Debe seleccionar un residencial autorizado.')
    return residential_id


def can_supervise(user):
    return user.role in {'admin', 'supervisor'} and has_global_residential_access(user)


def month_url(proposal_id, year, month):
    return '/ui/monthly-attendance?' + urlencode(dict(proposal_id=proposal_id, year=year, month=month))


def _where(model, proposal_id, year, month):
    return and_(model.proposal_id == proposal_id, model.report_year == year, model.report_month == month)


def lock_month(db, proposal_id, year, month):
    """Transaction-owned lock also protects first confirmation before rows exist."""
    if db.get_bind().dialect.name == 'mssql':
        result = db.execute(text('''DECLARE @result INT;
            EXEC @result = sys.sp_getapplock @Resource=:resource, @LockMode='Exclusive',
                @LockOwner='Transaction', @LockTimeout=15000;
            SELECT @result;'''), {'resource': f'faro:attendance-month:{proposal_id}:{year}:{month}'}).scalar()
        if result is None or result < 0:
            raise HTTPException(409, 'Otro usuario está actualizando el mes. Intenta nuevamente.')


def _proposal(db, proposal_id, year, month, *, today=None, write=False):
    normalize_reporting_period(month, year)
    proposal = db.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(404, 'Propuesta no encontrada.')
    today = today or date.today()
    if write and (not proposal.is_active or is_proposal_finalized(proposal) or is_proposal_period_locked(proposal, month, year)):
        raise HTTPException(409, 'La propuesta o el período están cerrados. El seguimiento es de consulta.')
    if write and (year, month) > (today.year, today.month):
        raise HTTPException(409, 'No se pueden confirmar o gestionar meses futuros.')
    return proposal


def _period(db, proposal_id, year, month):
    return db.scalar(select(AttendanceMonth).where(_where(AttendanceMonth, proposal_id, year, month))
                     .execution_options(populate_existing=True))


def _records(db, proposal_id, year, month):
    return {row.residential_id: row for row in db.scalars(select(AttendanceMonthResidential)
        .where(_where(AttendanceMonthResidential, proposal_id, year, month)).execution_options(populate_existing=True))}


def snapshots(db, proposal_id, year, month, residential_ids):
    """Batch actual monthly volumes and a digest, including same-count replacements."""
    result = {rid: {'sessions': 0, 'participations': 0, 'empty_sessions': 0, 'payload': [[], []]} for rid in residential_ids}
    if not result:
        return result
    start, end = date(year, month, 1), next_period_start(month, year)
    conditions = [ActivitySession.proposal_id == proposal_id, ActivitySession.session_date >= start,
                  ActivitySession.session_date < end, ActivitySession.residential_id.in_(residential_ids)]
    sessions = db.execute(select(ActivitySession.session_id, ActivitySession.residential_id, ActivitySession.session_date,
        ActivitySession.activity_code_id, ActivitySession.employee_id, ActivitySession.hours)
        .where(*conditions).order_by(ActivitySession.session_id)).all()
    attended_sessions = set()
    for row in sessions:
        result[row.residential_id]['sessions'] += 1
        result[row.residential_id]['payload'][0].append(tuple(row))
    attendance = db.execute(select(ActivitySession.residential_id, Attendance.session_id, Attendance.attendance_id,
        Attendance.participant_id, Attendance.proposal_participant_id, Attendance.attended)
        .join(ActivitySession, ActivitySession.session_id == Attendance.session_id).where(*conditions)
        .order_by(Attendance.attendance_id)).all()
    for row in attendance:
        result[row.residential_id]['payload'][1].append(tuple(row))
        if row.attended:
            result[row.residential_id]['participations'] += 1
            attended_sessions.add(row.session_id)
    for row in sessions:
        if row.session_id not in attended_sessions:
            result[row.residential_id]['empty_sessions'] += 1
    for data in result.values():
        data['digest'] = hashlib.sha256(json.dumps(data.pop('payload'), default=str, separators=(',', ':')).encode()).hexdigest()
    return result


def _signature(record, snapshot):
    return hashlib.sha256(f"{record.revision if record else 0}:{snapshot['digest']}".encode()).hexdigest()


def _status(record, snapshot):
    if not record or record.confirmed_at is None:
        return 'pending'
    if record.revision != record.confirmed_revision or record.fingerprint != snapshot['digest']:
        return 'review'
    return 'done'


def build_month(db, user, proposal_id, year, month, *, today=None):
    today = today or date.today()
    rid = scope_id(user)
    proposal = _proposal(db, proposal_id, year, month, today=today)
    period = _period(db, proposal_id, year, month)
    records = _records(db, proposal_id, year, month) if period else {}
    residential_query = select(Residential).where(
        Residential.residential_id.in_([r.residential_id for r in records.values() if r.is_included])
        if period else Residential.is_active == True)
    if rid is not None:
        residential_query = residential_query.where(Residential.residential_id == rid)
    residentials = list(db.scalars(residential_query.order_by(Residential.code, Residential.name)))
    data = snapshots(db, proposal_id, year, month, [r.residential_id for r in residentials])
    rows = []
    for residential in residentials:
        record = records.get(residential.residential_id)
        snapshot = data[residential.residential_id]
        rows.append({'residential': residential, 'record': record, **snapshot,
                     'status': _status(record, snapshot), 'fingerprint': _signature(record, snapshot)})
    rows.sort(key=lambda row: (row['status'] == 'done', row['residential'].code))
    completed = sum(row['status'] == 'done' for row in rows)
    writable = bool(proposal.is_active and not is_proposal_finalized(proposal)
                    and not is_proposal_period_locked(proposal, month, year) and (year, month) <= (today.year, today.month))
    return {'proposal': proposal, 'year': year, 'month': month, 'period': period,
            'label': format_reporting_period(month, year), 'rows': rows, 'total': len(rows), 'completed': completed,
            'all_done': bool(rows) and completed == len(rows), 'due_on': period.due_on if period else default_due_date(year, month),
            'writable': writable, 'is_global': rid is None, 'can_supervise': can_supervise(user),
            'can_configure': user.role == 'admin' and rid is None,
            'can_confirm': rid is not None and user.role in {'admin', 'supervisor', 'user'} and writable,
            'url': month_url(proposal_id, year, month), 'today': today}


def _ensure_period(db, proposal_id, year, month):
    period = _period(db, proposal_id, year, month)
    if period is None:
        period = AttendanceMonth(proposal_id=proposal_id, report_year=year, report_month=month,
                                 due_on=default_due_date(year, month), revision=0)
        db.add(period)
        db.flush()
        residential_ids = db.scalars(select(Residential.residential_id).where(Residential.is_active == True)).all()
        db.add_all([AttendanceMonthResidential(proposal_id=proposal_id, report_year=year, report_month=month,
                    residential_id=rid, is_included=True, revision=0) for rid in residential_ids])
        db.flush()
    return period


def _event(db, user, period, kind, message, residential_id=None, announcement_id=None):
    db.add(AttendanceMonthEvent(proposal_id=period.proposal_id, report_year=period.report_year,
        report_month=period.report_month, residential_id=residential_id, kind=kind,
        actor_user_id=user.user_id, actor_name=user.username, message=message,
        announcement_id=announcement_id))


def _notice(db, user, period, title, message, residential_ids, *, roles=('admin', 'supervisor'), today=None):
    today = today or date.today()
    announcement = FaroAnnouncement(title=title, message=message, starts_on=today,
        ends_on=today + timedelta(days=30), created_by_user_id=user.user_id,
        action_url=month_url(period.proposal_id, period.report_year, period.report_month))
    db.add(announcement)
    db.flush()
    db.add_all([FaroAnnouncementRole(announcement_id=announcement.announcement_id, role=role) for role in roles])
    db.add_all([FaroAnnouncementResidential(announcement_id=announcement.announcement_id, residential_id=rid)
                for rid in set(residential_ids)])
    db.flush()
    return announcement.announcement_id


def _retire(db, announcement_id):
    if announcement_id:
        db.execute(FaroAnnouncement.__table__.update().where(FaroAnnouncement.announcement_id == announcement_id)
                   .values(is_active=False))


def _set(db, record, **values):
    """Locked rows use Core UPDATE, consistent with Faro's SQL Server writers.

    NOCOUNT drivers return -1 for updates, which ORM flush treats as a stale row.
    The month application lock provides serialization; keep the identity map in
    sync without scheduling another ORM update.
    """
    table = record.__table__
    predicate = and_(*(column == getattr(record, column.key) for column in inspect(type(record)).primary_key))
    db.execute(table.update().where(predicate).values(**values))
    for key, value in values.items():
        set_committed_value(record, key, value)


def _check_all_done(db, user, period, *, today=None):
    records = _records(db, period.proposal_id, period.report_year, period.report_month)
    included = [r for r in records.values() if r.is_included]
    data = snapshots(db, period.proposal_id, period.report_year, period.report_month, [r.residential_id for r in included])
    all_done = bool(included) and all(_status(r, data[r.residential_id]) == 'done' for r in included)
    if all_done and not period.all_announcement_id:
        proposal = db.get(Proposal, period.proposal_id)
        label = format_reporting_period(period.report_month, period.report_year)
        announcement_id = _notice(db, user, period, f'Asistencias confirmadas · {label}',
            f'Los {len(included)} residenciales incluidos en la propuesta {proposal.name} confirmaron sus asistencias. '
            'Continúa con la revisión de cursos, referidos y demás datos antes de emitir el informe.',
            [r.residential_id for r in included], today=today)
        _set(db, period, all_announcement_id=announcement_id)
        _event(db, user, period, 'all_confirmed', f'Todos los {len(included)} residenciales incluidos confirmaron.',
               announcement_id=period.all_announcement_id)
    elif not all_done and period.all_announcement_id:
        _retire(db, period.all_announcement_id)
        _set(db, period, all_announcement_id=None)


def confirm_month(db, user, *, proposal_id, year, month, fingerprint, declared, no_activity=False, note='', today=None):
    rid = scope_id(user)
    if rid is None or user.role not in {'admin', 'supervisor', 'user'}:
        raise HTTPException(403, 'Confirma desde el contexto del residencial que te corresponde.')
    if not declared:
        raise HTTPException(422, 'Debes confirmar que registraste todas las asistencias del mes.')
    note = note.strip()
    if len(note.encode('utf-16-le')) // 2 > 1000:
        raise HTTPException(422, 'La observación admite hasta 1,000 caracteres.')
    lock_month(db, proposal_id, year, month)
    proposal = _proposal(db, proposal_id, year, month, write=True, today=today)
    period = _ensure_period(db, proposal_id, year, month)
    record = _records(db, proposal_id, year, month).get(rid)
    if not record or not record.is_included:
        raise HTTPException(403, 'Tu residencial no está incluido en este período. Consulta con administración.')
    snapshot = snapshots(db, proposal_id, year, month, [rid])[rid]
    if not hmac.compare_digest((fingerprint or '').encode(), _signature(record, snapshot).encode()):
        raise HTTPException(409, 'Las asistencias cambiaron desde que abriste la página. Revisa el mes actualizado y confirma nuevamente.')
    if no_activity != (snapshot['sessions'] == 0) or (no_activity and not note):
        raise HTTPException(422, 'Si no hubo actividades, selecciona «Sin actividad» e indica la justificación. No se puede declarar sin actividad un mes con registros.')
    if _status(record, snapshot) == 'done':
        return record  # An identical retry does not duplicate acknowledgements.
    _retire(db, record.confirmation_announcement_id)
    _retire(db, record.reminder_announcement_id)
    residential = db.get(Residential, rid)
    label = format_reporting_period(month, year)
    announcement_id = _notice(db, user, period, f'{residential.code} completó {label}',
        f'{user.username} confirmó las asistencias de {residential.name}, propuesta {proposal.name}: '
        f"{snapshot['sessions']} actividades y {snapshot['participations']} participaciones."
        + (' Sin actividad: ' + note if no_activity else ''), [rid], today=today)
    _set(db, record, confirmed_at=utcnow(), confirmed_by_user_id=user.user_id,
         confirmed_by_name=user.username, confirmed_revision=record.revision, fingerprint=snapshot['digest'],
         note=note or None, no_activity=no_activity, confirmed_sessions=snapshot['sessions'],
         confirmed_participations=snapshot['participations'], confirmation_announcement_id=announcement_id)
    _event(db, user, period, 'confirmed',
        f"Confirmó {snapshot['sessions']} actividades y {snapshot['participations']} participaciones. {note}".strip(),
        rid, record.confirmation_announcement_id)
    db.flush()
    _check_all_done(db, user, period, today=today)
    db.flush()
    return record


def change_months(db, user, keys, *, reason, today=None):
    """Run BEFORE any session/attendance write, in that same transaction.

    Session moves provide both old and new (proposal, residential, date) keys.
    Changes outside tracking still acquire the lock to serialize first confirmation.
    """
    affected = sorted({(pid, day.year, day.month, rid) for pid, rid, day in keys if pid and rid and day})
    for pid, year, month in sorted({key[:3] for key in affected}):
        lock_month(db, pid, year, month)
    for pid, year, month, rid in affected:
        period = _period(db, pid, year, month)
        if period is None:
            continue
        record = _records(db, pid, year, month).get(rid)
        if not record:
            continue
        was_confirmed = record.confirmed_at is not None and record.confirmed_revision == record.revision
        _set(db, record, revision=record.revision + 1)
        if was_confirmed:
            _retire(db, record.confirmation_announcement_id)
            _retire(db, period.all_announcement_id)
            _set(db, period, all_announcement_id=None)
            residential = db.get(Residential, rid)
            proposal = db.get(Proposal, pid)
            aid = _notice(db, user, period, f'{residential.code}: confirmar nuevamente {format_reporting_period(month, year)}',
                f'Las asistencias de {residential.name}, propuesta {proposal.name}, cambiaron después de la confirmación. '
                f'{reason}. Revisa el período y vuelve a confirmar.', [rid], roles=('admin', 'supervisor', 'user'), today=today)
            _retire(db, record.reminder_announcement_id)
            _set(db, record, reminder_announcement_id=aid)
            _event(db, user, period, 'reopened', reason, rid, aid)
        db.flush()


def remind_month(db, user, *, proposal_id, year, month, residential_ids=None, message='', today=None):
    if not can_supervise(user):
        raise HTTPException(403, 'Solo administración y supervisión en acceso institucional pueden enviar recordatorios.')
    message = message.strip() or 'Completa y confirma las asistencias del mes para preparar el informe.'
    if len(message.encode('utf-16-le')) // 2 > 1000:
        raise HTTPException(422, 'El mensaje admite hasta 1,000 caracteres.')
    lock_month(db, proposal_id, year, month)
    _proposal(db, proposal_id, year, month, write=True, today=today)
    period = _ensure_period(db, proposal_id, year, month)
    view = build_month(db, user, proposal_id, year, month, today=today)
    waiting = {r['residential'].residential_id: r for r in view['rows'] if r['status'] != 'done'}
    recipients = set(waiting) if residential_ids is None else set(residential_ids)
    if not recipients or not recipients <= waiting.keys():
        raise HTTPException(409, 'Selecciona residenciales incluidos que sigan pendientes de confirmar.')
    now = utcnow()
    for rid in sorted(recipients):
        record = waiting[rid]['record']
        if record.last_reminded_at:
            stamp = record.last_reminded_at.replace(tzinfo=timezone.utc) if record.last_reminded_at.tzinfo is None else record.last_reminded_at
            if now - stamp < timedelta(minutes=5):
                raise HTTPException(409, 'Ya se envió un recordatorio recientemente. Espera unos minutos antes de repetirlo.')
    for rid in sorted(recipients):
        record = waiting[rid]['record']
        _retire(db, record.reminder_announcement_id)
        announcement_id = _notice(db, user, period,
            f'Confirma las asistencias de {view["label"]}', f'Propuesta {view["proposal"].name}. {message}',
            [rid], roles=('admin', 'supervisor', 'user'), today=today)
        _set(db, record, reminder_announcement_id=announcement_id, last_reminded_at=now)
        _event(db, user, period, 'reminder', message, rid, record.reminder_announcement_id)
    db.flush()
    return len(recipients)


def configure_month(db, user, *, proposal_id, year, month, due_on, residential_ids, revision, reason, today=None):
    if user.role != 'admin' or not has_global_residential_access(user):
        raise HTTPException(403, 'Solo el administrador en acceso institucional puede configurar el período.')
    reason = reason.strip()
    if not reason or len(reason.encode('utf-16-le')) // 2 > 1000:
        raise HTTPException(422, 'Indica el motivo del ajuste (hasta 1,000 caracteres).')
    normalize_reporting_period(month, year)
    if due_on < date(year, month, 1) or due_on > default_due_date(year, month) + timedelta(days=366):
        raise HTTPException(422, 'La fecha límite debe corresponder a este período o al año siguiente.')
    lock_month(db, proposal_id, year, month)
    _proposal(db, proposal_id, year, month, write=True, today=today)
    period = _ensure_period(db, proposal_id, year, month)
    if period.revision != revision:
        raise HTTPException(409, 'La configuración cambió. Vuelve a cargar la página antes de guardar.')
    records = _records(db, proposal_id, year, month)
    available = set(db.scalars(select(Residential.residential_id).where(Residential.is_active == True))) | set(records)
    selected = set(residential_ids)
    if not selected or not selected <= available:
        raise HTTPException(422, 'Selecciona al menos un residencial válido.')
    for rid, record in records.items():
        if record.is_included != (rid in selected):
            _event(db, user, period, 'residential_added' if rid in selected else 'residential_removed',
                ('Se incluyó el residencial. ' if rid in selected else 'Se excluyó el residencial. ') + reason, rid)
        _set(db, record, is_included=rid in selected)
        if not record.is_included:
            _retire(db, record.reminder_announcement_id)
            _retire(db, record.confirmation_announcement_id)
    for rid in selected - records.keys():
        db.add(AttendanceMonthResidential(proposal_id=proposal_id, report_year=year, report_month=month,
            residential_id=rid, is_included=True, revision=0))
        _event(db, user, period, 'residential_added', 'Se incluyó el residencial. ' + reason, rid)
    _set(db, period, due_on=due_on, revision=period.revision + 1)
    _retire(db, period.all_announcement_id)
    _set(db, period, all_announcement_id=None)
    _event(db, user, period, 'configured', f'Fecha límite: {due_on}. {len(selected)} residenciales incluidos. {reason}')
    db.flush()
    _check_all_done(db, user, period, today=today)
    db.flush()
