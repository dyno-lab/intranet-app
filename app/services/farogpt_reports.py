"""Report catalog and aggregate projections for FaroGPT, never participant rows."""
from urllib.parse import urlencode

from fastapi import HTTPException

from app.core.residential_scope import has_global_residential_access
from app.services import farogpt_report_followups, farogpt_report_operations


# These phrases identify a report. Field aliases are owned by each projection.
ALIASES = {
    'adm': ('informe administrativo', 'reporte administrativo', 'administrativo', 'adm'),
    'notes': ('notas escolares', 'notas', 'calificaciones'),
    'pregnancy': ('embarazos', 'embarazo', 'embarazadas'),
    'dropout': ('desercion escolar', 'desercion'),
    'visits': ('visitas a agencias', 'visitas', 'referidos'),
    'courses': ('cursos', 'curso'),
    'bonafide': ('hoja bonafide', 'bonafide'),
    'certification': ('certificacion',),
    'cotejo': ('hoja de cotejo', 'hoja cotejo', 'cotejo'),
    'programs': ('informe por programa', 'reporte por programa', 'por programa', 'programas'),
    'productivity': ('productividad',),
    'complete': ('informe mensual completo', 'informe completo', 'reporte completo'),
    'vca': ('vca', 'victimas de crimen'),
    'no_duplicado': ('no duplicados', 'no duplicadas', 'no duplicado'),
    'duplicado': ('duplicados', 'duplicadas', 'duplicado'),
    'people': ('participantes unicos', 'personas unicas', 'personas atendidas', 'participantes', 'personas'),
    'duplicates': ('participaciones',),
    'activities': ('actividades', 'servicios'),
}

FIELD_ALIASES = {
    'f': ('femenino', 'femeninas', 'mujeres'),
    'm': ('masculino', 'masculinos', 'hombres'),
    'services': ('servicios', 'actividades'),
    'duplicates': ('duplicados', 'participaciones'),
    'people': ('no duplicados', 'personas unicas', 'participantes unicos'),
    'hours': ('horas', 'horas contacto', 'horas de contacto'),
    'total': ('total',),
    'referrals_internal': ('referidos internos',),
    'referrals_external': ('referidos externos',),
    'referrals_agency': ('visitas a agencias', 'referidos a agencias'),
}


def _complete(db, user, ids, month, year, rid):
    # The complete report intentionally removes residential scope internally.
    # Never call it from a scoped session or for a residential-only question.
    if not has_global_residential_access(user) or rid is not None:
        raise HTTPException(422, 'El informe mensual completo es global. Consulta un reporte individual para este residencial.')
    from app.services.full_monthly_report_data import build_full_monthly_report_data
    data = build_full_monthly_report_data(db, user, ids, month, year)
    metrics = [
        {'key': 'people', 'label': 'No duplicados', 'value': data['no_duplicado']['total_all'],
         'definition': 'Total global del reporte No Duplicado; no se suman los únicos de cada residencial.'},
        {'key': 'duplicates', 'label': 'Duplicados', 'value': data['duplicado']['total_all'],
         'definition': 'Total global del reporte Duplicados.'},
        {'key': 'hours', 'label': 'Horas de contacto', 'value': data['total_contact_hours'], 'unit': 'h',
         'definition': 'Horas de contacto consolidadas de la Hoja de Cotejo.'},
        {'key': 'visits', 'label': 'Asistencias en certificación de visitas', 'value': data['visit_certification']['total'],
         'definition': 'Asistencias confirmadas de los códigos de visita aprobados en el informe completo.'},
    ]
    return {'title': 'Informe mensual completo', 'primary': 'people', 'metrics': metrics,
            'tables': [
                {'title': 'Totales por residencial', 'columns': ['Residencial', 'No duplicados', 'Duplicados'],
                 'rows': [[r['residential_name'], r['no_duplicado']['total_all'], r['duplicado']['total_all']]
                          for r in data['residentials']]},
                {'title': 'Horas por programa', 'columns': ['Programa', 'Horas de contacto'],
                 'rows': [[r['program_display_name'], r['contact_hours']] for r in data['program_hours']]},
            ], 'source_path': '/ui/reports/completo',
            'note': 'Resumen calculado del informe completo. Los anexos, metas y textos que se completan manualmente se consultan en el informe original.'}


def build(report, db, user, ids, month, year, rid):
    with db.no_autoflush:
        if report in farogpt_report_operations.REPORTS:
            result = farogpt_report_operations.build(report, db, user, ids, month, year, rid)
        elif report in farogpt_report_followups.REPORTS:
            result = farogpt_report_followups.build(report, db, user, ids, month, year, rid)
        elif report == 'complete':
            result = _complete(db, user, ids, month, year, rid)
        else:
            raise HTTPException(422, 'Selecciona un reporte disponible.')
    for metric in result['metrics']:
        common_aliases = () if report == 'pregnancy' and metric['key'] in {'f', 'm'} else FIELD_ALIASES.get(metric['key'], ())
        metric['aliases'] = list(dict.fromkeys([
            metric['label'], *metric.get('aliases', []), *common_aliases,
        ]))
    result.setdefault('primary', result['metrics'][0]['key'])
    result['source_url'] = result['source_path'] + '?' + urlencode({
        'proposal_id': ids, 'month': month, 'year': year, 'employee_id': -rid if rid else 0,
        'period_type': 'monthly',
    }, doseq=True)
    return result
