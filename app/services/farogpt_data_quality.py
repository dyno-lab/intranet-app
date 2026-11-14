"""Read-only projections of existing validation findings for FaroGPT supervision."""
from collections import defaultdict
from datetime import date
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import extract, select

from app.core.platform_permissions import ACCESS_AUTOMATION, user_has_platform_permission
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.services import data_validation as validation

REPORTS = frozenset({'record_issues', 'session_issues'})


def require_access(db, user):
    if user.role not in {'admin', 'supervisor'}:
        raise HTTPException(403, 'La consulta requiere administración o supervisión.')
    if not user_has_platform_permission(db, user, ACCESS_AUTOMATION):
        raise HTTPException(403, 'Necesitas acceso a Automatizaciones para consultar Validación de datos en FaroGPT.')


def _metric(key, label, value, definition):
    return dict(key=key, label=label, value=value, definition=definition, aliases=[])


def build(report, db, user, proposal_ids, months, year, residential_id, *, issue_filter=None, today=None):
    today = today or date.today()
    if report not in REPORTS or issue_filter not in {None, 'hours', 'no_participations'}:
        raise HTTPException(422, 'Selecciona una consulta de validación disponible.')
    with db.no_autoflush:
        require_access(db, user)
        scoped = validation.scope_id(user)
        if scoped is not None and residential_id not in {None, scoped}:
            raise HTTPException(403, 'El residencial no corresponde a tu contexto autorizado.')
        residential_id = scoped if scoped is not None else residential_id
        ids = set(proposal_ids)
        filters = dict(proposal_id=next(iter(ids)) if len(ids) == 1 else None,
                       residential_id=residential_id, year=year, months=months)
        view = validation.review(db, user, **filters, today=today)
        kind = 'record' if report == 'record_issues' else 'attendance'
        opened = [r for r in view['findings'] if r['proposal_id'] in ids and
                  r['kind'] == kind and r['status'] in validation.OPEN]
        screen = 'records' if kind == 'record' else 'activities'

        def link(finding=None):
            params = dict(filters, kind=kind, view=screen, status='open')
            if finding:
                params['finding'] = finding['key']
            return validation.URL + '?' + urlencode({k:v for k,v in params.items() if v is not None}, doseq=True)

        grouped = defaultdict(list)
        for row in opened:
            key = ((row['records'][0]['person_id'], row['records'][0]['expediente'].strip().casefold())
                   if kind == 'record' else row['session_id'])
            grouped[key].append(row)
        if kind == 'attendance' and issue_filter:
            grouped = {key: rows for key, rows in grouped.items() if any(r['rule'] == issue_filter for r in rows)}
        findings = [r for rows in grouped.values() for r in rows]

        def joined(rows, key):
            return ' / '.join(dict.fromkeys(r[key] for r in rows))

        def pending_text(rows):
            return '; '.join(dict.fromkeys(r['title'] +
                (' (histórico)' if r['records'] and r['records'][0]['historical'] else '') for r in rows))

        def states(rows):
            return ' / '.join(dict.fromkeys(validation.STATUS[r['status']] if r['source_present'] else
                                           'Por revalidar' for r in rows))

        if kind == 'record':
            rows = [[{'text': items[0]['records'][0]['expediente'], 'url': link(items[0])},
                     joined(items, 'residential_name'), joined(items, 'proposal_name'), pending_text(items), states(items)]
                    for items in grouped.values()]
            metrics = [
                _metric('records', 'Expedientes con datos incompletos o inconsistentes', len(grouped),
                        'Expedientes distintos con hallazgos abiertos de integridad. Se agrupan por persona y número, incluso entre propuestas.'),
                _metric('people', 'Personas afectadas', len({r['records'][0]['person_id'] for r in findings}),
                        'Personas únicas con alguno de estos expedientes.'),
                _metric('findings', 'Datos por revisar', len(findings), 'Hallazgos abiertos de estos expedientes, según Validación de datos.'),
            ]
            table = dict(title='Expedientes por revisar', columns=['Expediente', 'Residencial', 'Propuesta', 'Pendientes', 'Estado'], rows=rows)
            result = dict(title='Expedientes incompletos', primary='records', period_label='Expediente · revisión completa')
            note = ('Se revisan todas las inscripciones de la propuesta, incluidas las históricas, sin corte mensual. '
                    'Relación familiar está excluida. Las coincidencias entre personas se consultan aparte en Validación de datos.')
        else:
            query = (select(ActivitySession.session_id, ActivityCode.code)
                .outerjoin(ActivityCode, ActivityCode.activity_code_id == ActivitySession.activity_code_id)
                .where(ActivitySession.proposal_id.in_(ids), ActivitySession.session_date <= today,
                       extract('year', ActivitySession.session_date) == year,
                       extract('month', ActivitySession.session_date).in_(months)))
            if residential_id is not None:
                query = query.where(ActivitySession.residential_id == residential_id)
            codes = dict(db.execute(query).all())
            rows = [[{'text': items[0]['record_label'], 'url': link(items[0])}, items[0]['session_date'],
                     codes.get(items[0]['session_id']) or 'No disponible', joined(items, 'residential_name'),
                     joined(items, 'proposal_name'), pending_text(items), states(items)] for items in grouped.values()]
            metrics = [
                _metric('sessions', 'Actividades por revisar', len(grouped),
                        'Sesiones distintas con hallazgos abiertos de asistencia u horas. Una sesión con ambos problemas cuenta una vez.'),
                _metric('no_participations', 'Sin participaciones confirmadas',
                        len({r['session_id'] for r in findings if r['rule']=='no_participations'}),
                        'Sesiones señaladas por no tener participaciones confirmadas vinculadas a un participante o inscripción.'),
                _metric('hours', 'Horas faltantes o inválidas', len({r['session_id'] for r in findings if r['rule']=='hours'}),
                        'Sesiones señaladas por horas vacías, no finitas, menores o iguales a cero o mayores de 24.'),
            ]
            table = dict(title='Actividades por revisar', columns=['Actividad', 'Fecha', 'Código', 'Residencial', 'Propuesta', 'Pendientes', 'Estado'], rows=rows)
            label = {'hours':'Actividades con horas faltantes o inválidas', 'no_participations':'Actividades sin participaciones confirmadas'}
            result = dict(title=label.get(issue_filter, 'Actividades sin asistencias u horas'), primary='sessions')
            note = 'Se revisan sesiones hasta la fecha de consulta, dentro de los meses seleccionados. Las sesiones futuras no se analizan.'
        stale = sum(not r['source_present'] for r in findings)
        if stale:
            note += f' Hay {stale} hallazgos por revalidar: su problema ya no se detecta, pero su seguimiento sigue abierto.'
        result.update(metrics=metrics, tables=[table], source_title='Validación de datos de Faro',
                      source_url=link(), source_label='Abrir Validación de datos', show_details=True, suggestions=[],
                      note=note + ' Las excepciones justificadas y los hallazgos resueltos quedan fuera. La consulta no cambia el seguimiento.')
        if issue_filter:
            result['note'] += ' El enlace al módulo muestra todos los hallazgos de actividades del mismo período y residencial.'
        return result
