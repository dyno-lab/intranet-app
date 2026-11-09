"""Confirmed participations by configured program, preserving residential history."""
from calendar import monthrange
from collections import defaultdict
from datetime import date
import re

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.residential_scope import has_global_residential_access
from app.core.roles import report_authorized_name
from app.helpers.report_context import base_reports_context, resolve_reporting_scope, resolve_reporting_location
from app.helpers.report_proposals import proposal_ids
from app.helpers.reports import build_period_filter, calc_age, describe_period, normalize_text, bonafide_participant_sort_key
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.person import Person
from app.models.proposal_participant import ProposalParticipant
from app.models.proposal_report_program import ProposalReportProgram
from app.models.residential import Residential
from app.services.participant_residency import session_snapshot_join
from app.services.proposal_participant_snapshots import participant_snapshot_view
from app.services.report_programs import effective_program_activity_code_select

PROGRAMS = ('1A', '2B', '3C', '4D')
MONTHS = tuple(enumerate(('Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio',
                          'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'), 1))


def _period(period_type, month, year, start_date, end_date):
    try:
        if period_type not in ('monthly', 'custom'):
            raise ValueError('Tipo de período inválido.')
        result = build_period_filter(period_type, month, year, start_date, end_date)
        if result['month'] is not None and not 1 <= result['month'] <= 12:
            raise ValueError('Mes inválido.')
        if result['year'] is not None and not 2000 <= result['year'] <= 9999:
            raise ValueError('Año inválido.')
        start = end = None
        if period_type == 'custom':
            start, end = result['start_date'], result['end_date']
            if start and end and start > end:
                raise ValueError('La fecha inicial no puede ser posterior a la final.')
        elif result['month'] and result['year']:
            y, m = result['year'], result['month']
            start, end = date(y, m, 1), date(y, m, monthrange(y, m)[1])
        return result, start, end
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, 'Seleccione un período válido para la certificación.') from exc


def _totals(rows):
    return {**{program: sum(row['counts'][program] for row in rows) for program in PROGRAMS},
            'total': sum(row['total'] for row in rows), 'vca': sum(bool(row['vca']) for row in rows),
            'unclassified': sum(row['unclassified'] for row in rows)}


def build_certification_report(db, user, *, selected_proposals=None, month=None, year=None,
                               employee_id=None, period_type='monthly', start_date=None,
                               end_date=None, authorized_name=None):
    ids = proposal_ids(selected_proposals)
    period, start, end = _period(period_type, month, year, start_date, end_date)
    base = base_reports_context(db, user, MONTHS)
    scope = resolve_reporting_scope(user, employee_id, db)
    location = resolve_reporting_location(scope['selected_user'], scope['is_global'])
    selected = bool(ids and start and end and (scope['selected_user'] or scope['is_global']))
    data = {**base, **scope, **location, 'selected_proposal_ids': ids,
            'selected_proposal_id': ids[0] if ids else None, 'selected_month': period['month'],
            'selected_year': period['year'], 'selected_period_type': period_type,
            'selected_start_date': period['start_date'].isoformat() if period['start_date'] else '',
            'selected_end_date': period['end_date'].isoformat() if period['end_date'] else '',
            'selected_employee_id': scope['employee_id'], 'period_label': describe_period(period, dict(MONTHS)),
            'has_selection': selected, 'can_choose_scope': has_global_residential_access(user),
            'authorized_name': report_authorized_name(user, authorized_name),
            'programs': PROGRAMS, 'sections': [], 'rows': [], 'issues': [], 'people_count': 0,
            'totals': _totals([]), 'proposal_label': '; '.join(f'{p.code} - {p.name}' for p in base['proposals'] if p.proposal_id in ids)}
    if not selected:
        return data

    conditions = [Attendance.attended == True, ActivitySession.proposal_id.in_(ids),  # noqa: E712
                  ActivitySession.session_date >= start, ActivitySession.session_date <= end]
    if not scope['is_global']:
        conditions.append(ActivitySession.residential_id == scope['residential_id'])

    # Count directly from attendance, without joining configurable program tables:
    # repeated assignments or several proposals must never multiply participations.
    counts = db.execute(select(Attendance.participant_id, ActivitySession.residential_id,
                               ActivitySession.proposal_id, ActivitySession.activity_code_id,
                               func.count(Attendance.attendance_id))
        .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
        .join(Participant, Participant.participant_id == Attendance.participant_id)
        .where(*conditions).group_by(Attendance.participant_id, ActivitySession.residential_id,
                                    ActivitySession.proposal_id, ActivitySession.activity_code_id)).all()
    if not counts:
        return data
    assignments = defaultdict(set)
    configured = db.scalars(select(ProposalReportProgram).where(ProposalReportProgram.proposal_id.in_(ids),
                                                              ProposalReportProgram.is_active == True)).all()
    for program in configured:
        key = re.sub(r'[^A-Z0-9]', '', program.code.upper())
        if key not in PROGRAMS:
            continue
        for code_id in db.scalars(effective_program_activity_code_select(program.program_id)):
            assignments[program.proposal_id, code_id].add(key)

    snapshots = db.execute(select(Participant, ProposalParticipant, ActivitySession.residential_id)
        .join(Attendance, Attendance.participant_id == Participant.participant_id)
        .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
        .outerjoin(Person, Person.legacy_participant_id == Participant.participant_id)
        .outerjoin(ProposalParticipant, session_snapshot_join())
        .where(*conditions).distinct()).all()
    snapshots.sort(key=lambda row: (getattr(row[1], 'proposal_id', 0) or 0,
                                    getattr(row[1], 'valid_from', None) or date.min,
                                    getattr(row[1], 'proposal_participant_id', 0) or 0))
    views = {(p.participant_id, residential): participant_snapshot_view(p, snapshot)
             for p, snapshot, residential in snapshots}
    records = {}
    for key, person in views.items():
        initial = normalize_text(person.inicial)
        if len(initial) == 1:
            initial += '.'
        name = ' '.join(part for part in (person.nombre, initial, person.apellido_paterno, person.apellido_materno) if part)
        if normalize_text(person.primera_vez).upper() in ('SI', 'SÍ'):
            name += ' *'
        gender = normalize_text(person.genero).upper()
        age = calc_age(person.fecha_nacimiento)
        records[key] = {'participant_id': key[0], 'residential_id': key[1], 'expediente': person.expediente_num or '',
                        'nombre': name, 'f': 'X' if gender.startswith('F') else '', 'm': 'X' if gender.startswith('M') else '',
                        'edad': age if age is not None else '', 'edificio': person.edificio or '',
                        'apartamento': person.apart or '', 'vca': normalize_text(person.vca).upper() in ('SI', 'SÍ'),
                        'counts': dict.fromkeys(PROGRAMS, 0), 'total': 0, 'unclassified': 0}
    issue_counts = defaultdict(int)
    for participant_id, residential_id, proposal_id, code_id, count in counts:
        record = records[participant_id, residential_id]
        record['total'] += count
        mapped = assignments[proposal_id, code_id]
        if len(mapped) == 1:
            record['counts'][next(iter(mapped))] += count
        else:
            record['unclassified'] += count
            issue_counts[proposal_id, code_id, 'multiple' if mapped else 'missing'] += count
    if issue_counts:
        code_names = dict(db.execute(select(ActivityCode.activity_code_id, ActivityCode.code)).all())
        data['issues'] = [{'proposal_id': proposal_id, 'activity_code': code_names.get(code_id, str(code_id)),
                           'reason': reason, 'count': count}
                          for (proposal_id, code_id, reason), count in sorted(issue_counts.items())]

    # A move during the period produces one row in each residential, with each
    # site's historical profile/number and only its own participations.
    residentials = {r.residential_id: r for r in db.scalars(select(Residential))}
    grouped = defaultdict(list)
    for key, record in records.items():
        grouped[key[1]].append(record)
    for residential_id in sorted(grouped, key=lambda key: (getattr(residentials.get(key), 'code', ''), key or 0)):
        residential = residentials.get(residential_id)
        rows = grouped[residential_id]
        rows.sort(key=lambda row: bonafide_participant_sort_key(views[row['participant_id'], residential_id]))
        for index, row in enumerate(rows, 1):
            row['index'] = index
            row['residential_name'] = residential.name if residential else 'Sin residencial'
        data['sections'].append({'residential_id': residential_id,
            'residential_name': residential.name if residential else 'Sin residencial',
            'municipality': (residential.municipality or '') if residential else '',
            'rows': rows, 'totals': _totals(rows)})
        data['rows'].extend(rows)
    data['totals'] = _totals(data['rows'])
    data['people_count'] = len({row['participant_id'] for row in data['rows']})
    return data


def require_exportable(data):
    if not data['has_selection']:
        raise HTTPException(422, 'Seleccione propuesta, período y residencial antes de exportar.')
    if data['issues']:
        raise HTTPException(409, 'Hay asistencias sin un único programa 1A, 2B, 3C o 4D. Revise la clasificación indicada en la vista previa antes de emitir la certificación.')
    if not data['rows']:
        raise HTTPException(404, 'No hay participaciones confirmadas para los filtros seleccionados.')
