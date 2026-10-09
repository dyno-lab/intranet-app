"""Monthly course assignments; attendance remains the source of eligibility."""
from calendar import monthrange
from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.period_guard import is_future_reporting_period, is_proposal_period_locked
from app.core.proposal_guard import is_proposal_finalized
from app.core.roles import ADMIN_ROLE, SUPERVISOR_ROLE, USER_ROLE
from app.helpers.report_context import base_reports_context, resolve_reporting_scope
from app.helpers.report_proposals import proposal_ids as normalize_proposals
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.participant_monthly_course import ParticipantMonthlyCourse
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential

ACTIVITY_CODE = '2.b.5'
COURSE_EDITOR_ROLES = frozenset({ADMIN_ROLE, SUPERVISOR_ROLE, USER_ROLE})
AVAILABLE_COURSES = {'reposteria': 'Repostería', 'charcuteria': 'Charcutería'}
# Retain retired labels for saved reports and recognizing historical selections.
COURSES = {**AVAILABLE_COURSES,
           'campo_laboral': 'Preparación para el campo Laboral'}
MONTHS = [(1, 'Enero'), (2, 'Febrero'), (3, 'Marzo'), (4, 'Abril'), (5, 'Mayo'), (6, 'Junio'),
          (7, 'Julio'), (8, 'Agosto'), (9, 'Septiembre'), (10, 'Octubre'), (11, 'Noviembre'), (12, 'Diciembre')]


def _period(month, year, period_type, start_date, end_date):
    try:
        if period_type == 'monthly':
            year, month = int(year), int(month)
            start, end = date(year, month, 1), date(year, month, monthrange(year, month)[1])
            label = f'{dict(MONTHS)[month]} {year}'
        elif period_type == 'custom':
            start, end = date.fromisoformat(str(start_date)), date.fromisoformat(str(end_date))
            label = f'{start:%d/%m/%Y} al {end:%d/%m/%Y}'
        else:
            raise ValueError
        count = (end.year - start.year) * 12 + end.month - start.month + 1
        if start > end or start.year < 2000 or end.year > 2100 or count > 120:
            raise ValueError
    except (ValueError, TypeError, OverflowError) as exc:
        raise HTTPException(422, 'Selecciona un período válido de hasta 120 meses, entre 2000 y 2100.') from exc
    months = []
    for offset in range(count):
        y, m = divmod(start.year * 12 + start.month - 1 + offset, 12)
        months.append({'year': y, 'month': m + 1, 'key': f'{y:04d}-{m + 1:02d}', 'label': f'{dict(MONTHS)[m + 1]} {y}'})
    return start, end, label, months


def _attendance(start, end):
    return (select(Attendance.participant_id, ActivitySession.session_date, ActivitySession.residential_id,
                   ActivitySession.proposal_id)
            .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
            .join(ActivityCode, ActivityCode.activity_code_id == ActivitySession.activity_code_id)
            .where(Attendance.attended == True, ActivityCode.code == ACTIVITY_CODE,  # noqa: E712
                   ActivitySession.session_date >= start, ActivitySession.session_date <= end,
                   Attendance.participant_id.is_not(None)))


def build_course_report(db, user, *, proposal_ids, month=None, year=None, employee_id=None,
                        period_type='monthly', start_date=None, end_date=None):
    from app.api.routes.reports import _report_participant_views

    ids = normalize_proposals(proposal_ids)
    if not ids or len(ids) > 50:
        raise HTTPException(422, 'Selecciona entre una y 50 propuestas.')
    start, end, period_label, months = _period(month, year, period_type, start_date, end_date)
    with db.no_autoflush:
        proposals = db.scalars(select(Proposal).where(Proposal.proposal_id.in_(ids)).order_by(Proposal.code)).all()
        if len(proposals) != len(ids):
            raise HTTPException(422, 'Una de las propuestas seleccionadas no existe.')
        scope = resolve_reporting_scope(user, employee_id, db)
        if not scope['is_global'] and not scope['selected_residential']:
            raise HTTPException(403, 'Selecciona un residencial autorizado.')
        stmt = _attendance(start, end).where(ActivitySession.proposal_id.in_(ids))
        if not scope['is_global']:
            stmt = stmt.where(ActivitySession.residential_id == scope['residential_id'])
        eligible = stmt.distinct().subquery()
        matches = db.execute(select(eligible)).all()
        people_ids = select(eligible.c.participant_id).distinct()
        pairs = db.execute(select(Participant, ProposalParticipant).select_from(Participant)
            .join(eligible, eligible.c.participant_id == Participant.participant_id)
            .outerjoin(Person, Person.legacy_participant_id == Participant.participant_id)
            .outerjoin(ProposalParticipant, and_(ProposalParticipant.person_id == Person.person_id,
                                                ProposalParticipant.proposal_id == eligible.c.proposal_id)).distinct()).all()
        # Reuse the exact identity/snapshot rule used by current consolidated reports.
        participants = {p.participant_id: p for p in _report_participant_views(pairs, ids)}
        saved = db.scalars(select(ParticipantMonthlyCourse).where(
            ParticipantMonthlyCourse.participant_id.in_(people_ids),
            ParticipantMonthlyCourse.report_year * 12 + ParticipantMonthlyCourse.report_month >= start.year * 12 + start.month,
            ParticipantMonthlyCourse.report_year * 12 + ParticipantMonthlyCourse.report_month <= end.year * 12 + end.month)).all()
        saved_map = {(p.participant_id, p.report_year, p.report_month): p for p in saved}
        residentials = {r.residential_id: r.name for r in db.scalars(select(Residential)).all()}
        attended, locations, locks = set(), {}, {}
        for pid, day, rid, _proposal in matches:
            attended.add((pid, day.year, day.month))
            locations.setdefault(pid, set()).add(residentials.get(rid, 'Sin residencial'))
        # A monthly choice is shared across selected proposals. A closed source
        # cannot be bypassed by choosing a different proposal or a partial month.
        lock_rows = db.execute(_attendance(start.replace(day=1), end.replace(day=monthrange(end.year, end.month)[1]))
            .with_only_columns(Attendance.participant_id, ActivitySession.session_date, Proposal)
            .join(Proposal, Proposal.proposal_id == ActivitySession.proposal_id)
            .where(Attendance.participant_id.in_(people_ids)).distinct()).all()
        for pid, day, proposal in lock_rows:
            if is_proposal_finalized(proposal) or is_proposal_period_locked(proposal, day.month, day.year):
                locks[(pid, day.year, day.month)] = 'Mes cerrado o propuesta finalizada.'
        can_edit = user.role in COURSE_EDITOR_ROLES
        rows = []
        for pid, person in participants.items():
            name = ' '.join(str(getattr(person, field, '') or '').strip() for field in
                            ('nombre', 'inicial', 'apellido_paterno', 'apellido_materno')).strip()
            cells = []
            for item in months:
                key = (pid, item['year'], item['month'])
                present = key in attended
                record = saved_map.get(key) if present else None
                reason = locks.get(key, '')
                if is_future_reporting_period(item['month'], item['year']):
                    reason = 'Mes futuro: solo consulta.'
                code = (record.course_code or '') if record else ''
                cells.append({**item, 'attended': present, 'course': code,
                              'label': COURSES.get(code, 'Pendiente de seleccionar') if present else 'Sin asistencia en 2.b.5',
                              'revision': record.revision if record else 0,
                              'editable': can_edit and present and not reason, 'lock_reason': reason})
            rows.append({'participant_id': pid, 'name': name, 'expediente_num': person.expediente_num or '',
                         'residential_name': '; '.join(sorted(locations.get(pid, set()))), 'cells': cells})
        rows.sort(key=lambda row: (row['name'].casefold(), row['participant_id']))
        base = base_reports_context(db, user, MONTHS)
    # Include selected historical proposals even if no longer in the active picker.
    choices = {p.proposal_id: p for p in base['proposals']}
    choices.update({p.proposal_id: p for p in proposals})
    return {**base, 'proposals': sorted(choices.values(), key=lambda p: p.code),
            'selected_proposal_ids': ids, 'selected_proposal_id': ids[0],
            'proposal_label': '; '.join(f'{p.code} - {p.name}' for p in proposals),
            'selected_month': int(month) if period_type == 'monthly' else start.month,
            'selected_year': int(year) if period_type == 'monthly' else start.year,
            'selected_period_type': period_type, 'selected_start_date': start.isoformat(), 'selected_end_date': end.isoformat(),
            'selected_employee_id': scope['employee_id'], 'is_global': scope['is_global'],
            'residential_name': 'Global' if scope['is_global'] else scope['selected_residential'].name,
            'months': months, 'period_label': period_label, 'rows': rows, 'total': len(rows),
            'courses': AVAILABLE_COURSES, 'can_edit': can_edit,
            'pending': sum(c['attended'] and not c['course'] for r in rows for c in r['cells']),
            'year_options': sorted(set(base['year_options']) | {start.year, end.year})}


def save_course_assignments(db, user, filters, changes):
    if user.role not in COURSE_EDITOR_ROLES:
        raise HTTPException(403, 'Solo administradores, supervisores y usuarios de su residencial pueden guardar cursos.')
    if not isinstance(changes, list) or not 1 <= len(changes) <= 5000:
        raise HTTPException(422, 'Envía entre una y 5000 selecciones modificadas.')
    context = build_course_report(db, user, **filters)
    cells = {(r['participant_id'], c['year'], c['month']): c for r in context['rows'] for c in r['cells']}
    checked, seen = [], set()
    for change in changes:
        if not isinstance(change, dict) or any(type(change.get(k)) is not int for k in ('participant_id', 'year', 'month', 'revision')):
            raise HTTPException(422, 'Selección de curso inválida.')
        key = (change['participant_id'], change['year'], change['month'])
        course = change.get('course')
        if key in seen or not isinstance(course, str) or course not in {'', *AVAILABLE_COURSES} or change['revision'] < 0:
            raise HTTPException(422, 'Selecciona un solo curso válido por participante y mes.')
        seen.add(key)
        cell = cells.get(key)
        if not cell or not cell['attended']:
            raise HTTPException(403, 'El participante no tiene asistencia autorizada a 2.b.5 en ese mes y período.')
        if not cell['editable']:
            raise HTTPException(409, cell['lock_reason'] or 'Esta selección es de solo lectura.')
        if cell['revision'] != change['revision']:
            raise HTTPException(409, 'Otra persona modificó los cursos. Vuelve a consultar antes de guardar.')
        checked.append((key, course or None, change['revision']))
    results = []
    try:
        for (pid, year, month), course, revision in checked:
            values = dict(course_code=course, revision=revision + 1, updated_by_user_id=user.user_id,
                          updated_at=datetime.now(timezone.utc))
            if revision:
                result = db.execute(update(ParticipantMonthlyCourse).where(
                    ParticipantMonthlyCourse.participant_id == pid, ParticipantMonthlyCourse.report_year == year,
                    ParticipantMonthlyCourse.report_month == month, ParticipantMonthlyCourse.revision == revision).values(**values))
                if result.rowcount != 1:
                    raise HTTPException(409, 'Otra persona modificó los cursos. Vuelve a consultar antes de guardar.')
            else:
                db.add(ParticipantMonthlyCourse(participant_id=pid, report_year=year, report_month=month, **values))
                # One insert at a time keeps every statement within SQL Server's parameter budget.
                db.flush()
            results.append(dict(participant_id=pid, year=year, month=month, revision=revision + 1))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, 'Otra persona guardó cursos para ese mes. Vuelve a consultar.') from exc
    except Exception:
        db.rollback()
        raise
    return results
