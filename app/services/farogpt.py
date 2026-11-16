"""Read-only, bounded Spanish queries over FARO's actual reporting records.

No model, external service, generated SQL or stored conversation is involved.
Unrecognized filters require clarification instead of silently broadening a query.
"""
import re
import unicodedata
from datetime import date, timedelta
from typing import Literal
from urllib.parse import urlencode

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import distinct, func, or_, select

from app.core.residential_scope import has_global_residential_access
from app.models.activity_code import ActivityCode
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential
from app.services.participant_courses import MONTHS
from app.services import farogpt_reports, farogpt_spelling, farogpt_report_operations
from app.services import farogpt_data_quality, farogpt_monthly_pending

URL = '/ui/farogpt'
ACTIVITY_CODE_PATTERN = re.compile(r'(?<!\w)(\d{1,2})\s*([a-z])\s*(\d{1,3})(?!\w)')
ACTIVITY_WORDS = {'act', 'acts', 'actividadss', 'actididades', 'actvidades', 'atividades', 'actividaes', 'activdades'}
SUMMARY_PHRASES = ('resumen', 'todos los campos', 'todos los indicadores')
QUERY_WORDS = frozenset(('cuantos cuantas hubo hay fueron tengo tenemos tuvo total cantidad numero de del el la los las '
    'en para por durante y con al un una me puedes puede dime dame saber quiero quisiera '
    'consulta consultar muestra mostrar indicame residencial propuesta mes meses ano faro '
    'compara comparar comparame comparalo favor registrados registradas '
    'atendidos atendidas este ese se atendieron participaron informe reporte '
    'datos informacion resultado resultados seguimiento cual cuales es son '
    'codigo hicieron realizo realizaron realizada realizado realizadas realizados ejecutaron ejecutadas ejecutados '
    'ofrecieron registraron impartieron').split())
SUPERVISION_REPORTS = frozenset({'attendance_pending', 'record_issues', 'session_issues'})
TITLES = {'people': 'Participantes únicos', 'duplicates': 'Participaciones (duplicados)',
          'activities': 'Actividades / servicios'}
DEFINITIONS = {
    'people': 'Cada persona se cuenta una sola vez en el período, entre las propuestas seleccionadas.',
    'duplicates': 'Se cuenta cada participación confirmada, incluida la primera de cada persona.',
    'activities': 'Se cuenta cada sesión registrada una sola vez, tenga o no participaciones confirmadas.',
}
HELP = ('Puedo consultar No Duplicado, Duplicados, ADM, notas, embarazo, deserción, visitas, '
        'referidos, cursos, Bonafide, Certificación, VCA, Cotejo, programas, productividad y el informe completo. '
        'Indica el mes o los meses y el año, un residencial o «global» y, si deseas, una propuesta. '
        'Si omites la propuesta usaré la vigente; si hay varias te pediré elegir. '
        'También puedo contar actividades por código y consultar confirmaciones mensuales pendientes, '
        'expedientes incompletos y actividades sin asistencias u horas. Los expedientes se revisan completos, sin corte mensual.')


class QueryContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    metric: Literal['people', 'duplicates', 'activities', 'no_duplicado', 'duplicado',
                    'adm', 'notes', 'pregnancy', 'dropout', 'visits', 'courses', 'bonafide',
                    'certification', 'vca', 'cotejo', 'programs', 'productivity', 'complete',
                    'attendance_pending', 'record_issues', 'session_issues'] | None = None
    field: str | None = Field(default=None, max_length=80)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    months: list[int] | None = Field(default=None, min_length=1, max_length=12)
    residential_id: int | None = Field(default=None, gt=0)
    proposal_id: int | None = Field(default=None, gt=0)
    proposal_scope: Literal['auto', 'all'] = 'auto'
    activity_code: str | None = Field(default=None, max_length=20)
    pending_terms: str | None = Field(default=None, max_length=800)
    issue_filter: Literal['hours', 'no_participations'] | None = None

    @field_validator('months')
    @classmethod
    def validate_months(cls, value):
        if value is not None:
            if any(month < 1 or month > 12 for month in value):
                raise ValueError('Los meses deben estar entre 1 y 12.')
            return sorted(set(value))
        return value

    @field_validator('activity_code')
    @classmethod
    def validate_activity_code(cls, value):
        if value is None:
            return None
        canonical = _canonical_activity_code(value)
        if canonical is None:
            raise ValueError('Usa un código de actividad completo, por ejemplo 2.b.5.')
        return canonical


def require_supervision(user):
    if getattr(user, 'role', None) not in {'admin', 'supervisor'}:
        raise HTTPException(403, 'FaroGPT está disponible para administración y supervisión.')


def catalogs(db, user):
    require_supervision(user)
    query = select(Residential)
    if not has_global_residential_access(user):
        rid = getattr(user, '_active_residential_id', None)
        if not rid:
            raise HTTPException(403, 'Selecciona un residencial autorizado.')
        query = query.where(Residential.residential_id == rid)
    return (list(db.scalars(query.order_by(Residential.name))),
            list(db.scalars(select(Proposal).order_by(Proposal.name))))


def _context(value):
    try:
        result = QueryContext.model_validate(value).model_dump()
        if result['months']:
            if result['month'] is not None and result['month'] != result['months'][0]:
                raise HTTPException(422, 'El mes inicial no coincide con los meses seleccionados.')
            result['month'] = result['months'][0]
        if result['proposal_scope'] == 'all' and result['proposal_id'] is not None:
            raise HTTPException(422, 'Selecciona una propuesta o todas las propuestas.')
        if result['issue_filter'] and result['metric'] != 'session_issues':
            raise HTTPException(422, 'El filtro de incidencias solo aplica a la validación de actividades.')
        if result['metric'] in SUPERVISION_REPORTS and result['field'] is not None:
            raise HTTPException(422, 'Consulta el resumen de seguimiento con sus pendientes.')
        return result
    except ValidationError as exc:
        raise HTTPException(422, 'Los filtros de la consulta no son válidos.') from exc


def _authorized_context(context, user, residentials, proposals):
    result = _context(context)
    rid, pid = result['residential_id'], result['proposal_id']
    if rid is not None and rid not in {r.residential_id for r in residentials}:
        raise HTTPException(403, 'El residencial no está disponible en tu contexto de acceso.')
    if not has_global_residential_access(user):
        result['residential_id'] = getattr(user, '_active_residential_id', None)
    if pid is not None and pid not in {p.proposal_id for p in proposals}:
        raise HTTPException(422, 'La propuesta no está disponible.')
    return result


def _default_proposal(context, proposals):
    if context['proposal_id'] is not None or context['proposal_scope'] == 'all':
        return None
    active = [p for p in proposals if p.is_active and (p.status or '').strip().lower() == 'active']
    if len(active) == 1:
        context['proposal_id'] = active[0].proposal_id
        return None
    if active:
        message = 'Hay varias propuestas vigentes. ¿Cuál quieres consultar? ' + ', '.join(p.name for p in active) + '.'
        choices = active
    else:
        message = 'No hay una propuesta vigente. Indica la propuesta histórica que quieres consultar o «todas las propuestas».'
        choices = proposals
    return {'message': message, 'suggestions': [f'Propuesta {p.name}' for p in choices[:3]]}


def _months(context):
    return context['months'] or ([context['month']] if context['month'] else [])


def _period_label(context):
    names = [dict(MONTHS)[m] for m in _months(context)]
    return (', '.join(names[:-1]) + ' y ' + names[-1] if len(names) > 1 else names[0]) + f' {context["year"]}'


def _dataset(db, user, context, proposals, *, today=None):
    ids = [context['proposal_id']] if context['proposal_id'] else [p.proposal_id for p in proposals]
    if context['metric'] not in TITLES:
        if context['activity_code']:
            raise HTTPException(422, 'El filtro por código está disponible para actividades, participaciones '
                                'y participantes únicos. Indica uno de esos indicadores para esta actividad.')
        if context['metric'] == 'attendance_pending':
            return farogpt_monthly_pending.build(db, user, ids, _months(context), context['year'],
                                                context['residential_id'], today=today)
        if context['metric'] in farogpt_data_quality.REPORTS:
            reference = today or date.today()
            return farogpt_data_quality.build(context['metric'], db, user, ids, _months(context) or [reference.month],
                context['year'] or reference.year, context['residential_id'], issue_filter=context['issue_filter'], today=today)
        months = _months(context)
        if len(months) > 1 and context['metric'] == 'complete':
            raise HTTPException(422, 'El informe mensual completo se consulta un mes a la vez. Indica cuál de los meses quieres abrir.')
        data = [farogpt_reports.build(context['metric'], db, user, ids, month,
                                     context['year'], context['residential_id']) for month in months]
        if len(data) == 1:
            return data[0]
        return {**data[0], 'monthly_data': list(zip(months, data))}
    return _attendance_dataset(db, context, ids)


def summary(db, user, context, *, today=None):
    """Recalculate the selected source report with its own reporting definitions."""
    residentials, proposals = catalogs(db, user)
    context = _authorized_context(context, user, residentials, proposals)
    problem = _default_proposal(context, proposals)
    if problem:
        raise HTTPException(422, problem['message'])
    metric, year, month = (context[k] for k in ('metric', 'year', 'month'))
    if metric is None or (metric != 'record_issues' and (year is None or month is None)):
        raise HTTPException(422, 'Indica el indicador, el mes y el año.')
    return _result(context, residentials, proposals, _dataset(db, user, context, proposals, today=today))


def _attendance_dataset(db, context, ids):
    year = context['year']
    months = _months(context)
    # Query the union of selected months: unique people cannot be summed month by month.
    periods = [(ActivitySession.session_date >= date(year, month, 1)) &
               (ActivitySession.session_date < date(year + (month == 12), 1 if month == 12 else month + 1, 1))
               for month in months]
    conditions = [ActivitySession.proposal_id.in_(ids), or_(*periods)]
    if context['residential_id'] is not None:
        conditions.append(ActivitySession.residential_id == context['residential_id'])
    activity = None
    if context['activity_code']:
        # Include historical/inactive codes. Session.proposal_id owns the service;
        # a code can be shared by multiple proposals regardless of its owner today.
        codes = [row for row in db.execute(select(ActivityCode.activity_code_id, ActivityCode.code, ActivityCode.description))
                 if _canonical_activity_code(row.code) == context['activity_code']]
        if not codes:
            raise HTTPException(422, f'No encontré el código {context["activity_code"]} en el catálogo de actividades. Revisa el código.')
        conditions.append(ActivitySession.activity_code_id.in_([row.activity_code_id for row in codes]))
        descriptions = list(dict.fromkeys(row.description for row in codes if row.description))
        activity = context['activity_code'] + (' · ' + ' / '.join(descriptions) if descriptions else '')
    activities = db.scalar(select(func.count()).select_from(ActivitySession).where(*conditions)) or 0
    duplicates = db.scalar(select(func.count(Attendance.attendance_id)).select_from(Attendance)
        .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
        .where(*conditions, Attendance.attended == True)) or 0  # noqa: E712
    # Keep the institutional identity rule: confirmed rows linked to an enrollment
    # in the session's proposal. Never reassign old services to today's address.
    people, linked = db.execute(select(func.count(distinct(Person.person_id)), func.count(Attendance.attendance_id))
        .select_from(Attendance).join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
        .join(ProposalParticipant, ProposalParticipant.proposal_participant_id == Attendance.proposal_participant_id)
        .join(Person, Person.person_id == ProposalParticipant.person_id)
        .where(*conditions, Attendance.attended == True,  # noqa: E712
               ProposalParticipant.proposal_id == ActivitySession.proposal_id)).one()
    metrics = {'people': int(people), 'duplicates': int(duplicates), 'activities': int(activities)}
    tables = []
    if len(months) > 1:
        rows = []
        for month in months:
            monthly = _attendance_dataset(db, dict(context, month=month, months=None), ids)
            values = {m['key']: m['value'] for m in monthly['metrics']}
            rows.append([dict(MONTHS)[month], values['activities'], values['duplicates'], values['people']])
        tables.append({'title': 'Desglose por mes', 'columns': ['Mes', 'Actividades', 'Participaciones', 'Personas únicas del mes'], 'rows': rows})
    return {'title': TITLES[context['metric']] + (f' · {context["activity_code"]}' if activity else ''),
            'activity': activity, 'primary': context['metric'],
            'metrics': [{'key': k, 'label': TITLES[k], 'value': value, 'definition': DEFINITIONS[k],
                         'aliases': []} for k, value in metrics.items()], 'tables': tables,
            'source_title': 'Conteo general de actividades y participaciones',
            'note': ('El residencial corresponde al lugar de la actividad. '
                     'Participantes únicos usa la identidad de persona vinculada a la propuesta. '
                     'Cada persona cuenta una vez en el total de meses seleccionados; los únicos mensuales no se suman. ' +
                     (f'{duplicates - linked} participaciones sin vínculo válido no se incluyen en participantes únicos.'
                      if duplicates > linked else ''))}


def _result(context, residentials, proposals, data):
    metric, year, month = (context[k] for k in ('metric', 'year', 'month'))
    ids = [context['proposal_id']] if context['proposal_id'] else [p.proposal_id for p in proposals]
    field = context['field'] or data['primary']
    primary = next((m for m in data['metrics'] if m['key'] == field), None)
    if primary is None:
        raise HTTPException(422, 'El campo no está disponible en este reporte.')
    residential = next((r.name for r in residentials if r.residential_id == context['residential_id']),
                       'Todos los residenciales autorizados')
    proposal = next((p.name for p in proposals if p.proposal_id == context['proposal_id']), 'Todas las propuestas')
    previous = date(year, month, 1) - timedelta(days=1) if year and month else None
    suggestions = [f'Comparar con {dict(MONTHS)[previous.month].lower()} de {previous.year}'] if previous else []
    params = {k: v for k, v in context.items() if v is not None and k != 'pending_terms'}
    result = {
        'type': 'result', 'title': primary['label'] if context['field'] else data['title'],
        'value': primary['value'], 'unit': primary.get('unit', ''),
        'metrics': {m['key']: m['value'] for m in data['metrics']},
        'cards': [primary] if context['field'] else data['metrics'],
        'tables': [] if context['field'] else data['tables'],
        'source_title': data.get('source_title', data['title']), 'source_url': data.get('source_url'),
        'definition': primary['definition'], 'context': context, 'activity': data.get('activity'),
        'period': data.get('period_label') or _period_label(context), 'residential': residential, 'proposal': proposal,
        'proposal_names': [p.name for p in proposals if p.proposal_id in ids],
        'report_url': URL + '/informe?' + urlencode(params, doseq=True),
        'suggestions': data.get('suggestions', suggestions),
        'note': data.get('note'),
    }
    if context['metric'] in SUPERVISION_REPORTS:
        result.update(show_details=True, details_label='Ver pendientes y seguimiento',
                      source_links=data.get('source_links', []), source_label=data.get('source_label', 'Abrir seguimiento'))
    if data.get('monthly_data'):
        monthly = [_result(dict(context, month=m, months=None), residentials, proposals, dataset)
                   for m, dataset in data['monthly_data']]
        keys = [m['key'] for m in result['cards']]
        columns = ['Mes', *[m['label'] + (f' ({m["unit"]})' if m.get('unit') else '') for m in result['cards']]]
        result.update(type='series', title=data['title'] + ' · por mes', value=None, cards=[], metrics={},
                      source_url=None, definition='Resultados de cada mes según el reporte original. No se suman personas únicas ni porcentajes de meses distintos.',
                      tables=[{'title': 'Resultados por mes', 'columns': columns,
                               'rows': [[r['period'], *[r['metrics'].get(k) for k in keys]] for r in monthly]}],
                      monthly_results=[{k: r[k] for k in ('period', 'report_url', 'source_url')} for r in monthly],
                      suggestions=[])
    return result


def _normalize(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def _query_aliases(text):
    # Correct only this known phrase, never fuzzy-match entities or discard "no".
    text = re.sub(r'\bno\s+dupliaods\b', 'no duplicados', text)
    # "Participantes no duplicados" names one report, not two indicators.
    return re.sub(r'\b(?:participantes|personas)\s+(?=no duplicad(?:os|as|o)\b)', '', text)


def _canonical_activity_code(value):
    match = ACTIVITY_CODE_PATTERN.fullmatch(_normalize(value or ''))
    return '.'.join(match.groups()) if match else None


def _extract_months(text):
    lookup = {_normalize(name): number for number, name in MONTHS}
    matches = list(re.finditer(r'\b(' + '|'.join(lookup) + r')\b', text))
    selected = {lookup[m.group()] for m in matches}
    spans = [(m.start(), m.end()) for m in matches]
    for left, right in zip(matches, matches[1:]):
        connector = text[left.end():right.start()].strip()
        if connector in {'a', 'hasta'}:
            first, last = lookup[left.group()], lookup[right.group()]
            if last < first:
                return [], text, 'Selecciona meses dentro de un mismo año, en orden de inicio a fin.'
            selected.update(range(first, last + 1))
            spans.append((left.end(), right.start()))
    for start, end in sorted(spans, reverse=True):
        text = text[:start] + ' ' + text[end:]
    return sorted(selected), text, None


def _phrase(text, phrase):
    return re.search(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', text)


def _remove(text, phrase):
    return re.sub(r'(?<!\w)' + re.escape(phrase) + r'(?!\w)', ' ', text)


def _entity(text, rows, kind):
    """Prefer exact names, then unambiguous name words; never fuzzy-guess scope."""
    matches = []
    for row in rows:
        name, code = _normalize(row.name or ''), _normalize(row.code or '')
        for candidate in (name, f'{kind} {code}' if code else '', code if len(code) > 1 else ''):
            if candidate and _phrase(text, candidate):
                matches.append((row, candidate))
                break
    if not matches and kind == 'residencial':
        for row in rows:
            words = [w for w in _normalize(row.name).split() if len(w) >= 4 and w not in {'residencial', 'urbanizacion'}]
            found = next((w for w in words if _phrase(text, w)), None)
            if found:
                matches.append((row, found))
    # Names contained in a longer exact name do not create a false ambiguity.
    matches = [(row, candidate) for row, candidate in matches
               if not any(candidate != other and _phrase(other, candidate) for _, other in matches)]
    if len(matches) > 1:
        return None, text, [row.name for row, _ in matches]
    if matches:
        row, candidate = matches[0]
        return row, _remove(text, candidate), []
    return None, text, []


def _clarify(message, context=None, suggestions=None):
    return {'type': 'clarification', 'message': message, 'context': context or {},
            'suggestions': suggestions or []}


def _report_in_question(text):
    matches = [key for key, aliases in farogpt_reports.ALIASES.items()
               if any(_phrase(text, alias) for alias in aliases)]
    # Count words also occur as fields inside a named report (e.g. duplicados ADM).
    specific = [key for key in matches if key not in {'people', 'duplicates', 'activities', 'no_duplicado', 'duplicado'}]
    if 'adm' in specific and 'vca' in specific:
        specific.remove('vca')
    if specific:
        return specific
    if 'no_duplicado' in matches and 'duplicado' in matches:
        matches.remove('duplicado')
    return matches


def _fields(text, data, category_aliases=()):
    candidates = sorted(((m['key'], _normalize(alias)) for m in data['metrics']
                         for alias in m.get('aliases', []) if alias), key=lambda item: len(item[1]), reverse=True)
    matched = {}
    for key, phrase in candidates:
        if _phrase(text, phrase):
            matched.setdefault(key, []).append(phrase)
            text = _remove(text, phrase)
    if len(matched) > 1:
        matched = {key: phrases for key, phrases in matched.items()
                   if not all(phrase in category_aliases for phrase in phrases)}
    return set(matched), text


def answer(db, user, question, context, *, today=None):
    today = today or date.today()
    residentials, proposals = catalogs(db, user)
    original = _authorized_context(context, user, residentials, proposals)
    result = _answer(db, user, question, original, residentials, proposals, today=today)
    if result['type'] != 'clarification':
        return result
    # Never change a successfully parsed query. If clarification is needed,
    # offer spelling proposals without executing any corrected question.
    spelling = farogpt_spelling.propose(question,
        [*QUERY_WORDS, *ACTIVITY_WORDS, *SUMMARY_PHRASES, 'dupliaods',
         *(name for _, name in MONTHS),
         *(phrase for aliases in farogpt_reports.ALIASES.values() for phrase in aliases),
         *(phrase for aliases in farogpt_reports.FIELD_ALIASES.values() for phrase in aliases),
         *(phrase for aliases in farogpt_report_operations.METRIC_ALIASES.values() for phrase in aliases)],
        protected_phrases=[value for row in [*residentials, *proposals]
                           for value in (row.name, row.code) if value])
    if spelling:
        return _clarify('Encontré posibles errores de escritura. Confirma la pregunta que quieres consultar:', original, spelling)
    return result


def _answer(db, user, question, original, residentials, proposals, *, today):
    selected = dict(original)
    text = _query_aliases(_normalize(question))
    if not text or len(question) > 800:
        return _clarify(HELP)
    if text in {'hola', 'ayuda', 'que puedes hacer', 'buenos dias', 'buenas tardes'}:
        return _clarify(HELP, original)
    # A named summary starts a fresh request (including our own suggestions),
    # while retaining the authorized proposal/residential context. A date-only
    # reply must still validate the previous question's unresolved restrictions.
    named_summary = any(_phrase(text, phrase) for phrase in SUMMARY_PHRASES) and bool(_report_in_question(text))
    if original['pending_terms'] and not named_summary:
        text = _query_aliases(original['pending_terms']) + ' ' + text
    text = ' '.join('actividades' if word in ACTIVITY_WORDS else word for word in text.split())
    selected['pending_terms'] = None
    # A day range such as "del 1 a 5" must not become activity code 1.a.5.
    if re.search(r'\b(?:del|desde|entre|de)\s+\d{1,2}\s+(?:a|al|hasta|y)\s+\d{1,2}\b', question, re.I):
        return _clarify('Estas consultas utilizan el mes completo. Indica un mes y año sin rango de días.', original)
    codes = {'.'.join(match.groups()) for match in ACTIVITY_CODE_PATTERN.finditer(text)}
    if len(codes) > 1:
        return _clarify('Indica un solo código de actividad por consulta, por ejemplo «2.b.5».', original)
    # Extract codes before residential/proposal recognition so their digits and
    # letters cannot accidentally become a different scope or a school grade.
    text = ACTIVITY_CODE_PATTERN.sub(' ', text)
    if codes:
        # In "participaciones de la actividad 2.b.5", activity describes the
        # filter, rather than requesting a second indicator alongside attendance.
        text = re.sub(r'\b(?:de|en)\s+(?:(?:la|las)\s+)?actividad(?:es)?\b', ' ', text)
    reports = _report_in_question(text)
    if len(reports) > 1:
        return _clarify('Consulta un reporte a la vez. ' + HELP, original)
    if reports:
        selected.update(metric=reports[0], field=None, issue_filter=None)
        if not codes and reports[0] not in TITLES:
            selected['activity_code'] = None
        if reports[0] == 'session_issues':
            no_attendance = bool(re.search(r'\b(?:(?:sin|no tienen) (?:asistencias|participaciones)|asistencias vacias)\b', text))
            no_hours = bool(re.search(r'\b(?:(?:sin|no tienen|faltan) horas|horas (?:faltantes|invalidas)|[ou] horas)\b', text))
            selected['issue_filter'] = 'no_participations' if no_attendance and not no_hours else 'hours' if no_hours and not no_attendance else None
            if no_attendance:
                # Expand only the supported disjunction; "con horas" remains
                # an unsupported restriction, never a filler word.
                text = re.sub(r'\b([ou]) horas\b', r'\1 sin horas', text)
                if re.search(r'\b(?:asistencias|participaciones)(?: confirmadas)? y (?:sin )?horas\b', text):
                    return _clarify('Puedo listar actividades con alguno de esos problemas: escribe «sin asistencias u horas», o consulta cada problema por separado.', original)
    if codes:
        selected['activity_code'] = codes.pop()
        if not reports and selected['metric'] not in TITLES:
            selected.update(metric='activities', field=None, issue_filter=None)
    clear_code_phrases = ('todas las actividades', 'todos los codigos', 'sin filtro de actividad')
    if any(_phrase(text, phrase) for phrase in clear_code_phrases):
        if selected['activity_code'] and ACTIVITY_CODE_PATTERN.search(_normalize(question)):
            return _clarify('Selecciona un código específico o todas las actividades, sin mezclar ambos filtros.', original)
        selected['activity_code'] = None
        for phrase in clear_code_phrases:
            text = _remove(text, phrase)
    compare = bool(re.search(r'\b(compara|comparar|comparame|comparalo)\b', text))
    if selected['metric'] not in SUPERVISION_REPORTS and re.search(r'\bpor (?:cada )?(?:residencial|propuesta)\b', text):
        return _clarify('Por ahora puedo consultar el total de un residencial o de todos, para los meses seleccionados. '
                        'Indica qué residencial y período quieres consultar.', original)
    residence, text, ambiguous = _entity(text, residentials, 'residencial')
    if ambiguous:
        return _clarify('Hay varios residenciales que coinciden: ' + ', '.join(ambiguous) + '. Escribe el nombre completo.', original)
    if residence:
        selected['residential_id'] = residence.residential_id
    global_phrases = ('todos los residenciales', 'a nivel global', 'a nivel general', 'global', 'globales')
    if any(_phrase(text, phrase) for phrase in global_phrases):
        if residence:
            return _clarify('Selecciona el residencial indicado o el total global, sin mezclar ambos alcances.', original)
        selected['residential_id'] = None
        for phrase in global_phrases:
            text = _remove(text, phrase)
    elif not residence and _phrase(text, 'residencial'):
        return _clarify('Indica el nombre completo del residencial, o escribe «todos los residenciales».', original)
    all_proposals = bool(_phrase(text, 'todas las propuestas'))
    active_phrases = ('propuesta vigente', 'propuesta activa', 'propuesta actual')
    active_proposal = any(_phrase(text, phrase) for phrase in active_phrases)
    if all_proposals and active_proposal:
        return _clarify('Selecciona la propuesta vigente o todas las propuestas.', original)
    if all_proposals:
        selected.update(proposal_id=None, proposal_scope='all')
        text = _remove(text, 'todas las propuestas')
    if active_proposal:
        selected.update(proposal_id=None, proposal_scope='auto')
        for phrase in active_phrases:
            text = _remove(text, phrase)
    proposal, text, ambiguous = _entity(text, proposals, 'propuesta')
    if ambiguous:
        return _clarify('Indica una sola propuesta por nombre o código, o escribe «todas las propuestas».', original)
    if proposal:
        if all_proposals or active_proposal:
            return _clarify('Indica una propuesta específica o la selección general, sin mezclar ambos filtros.', original)
        selected.update(proposal_id=proposal.proposal_id, proposal_scope='auto')
    elif not proposal and _phrase(text, 'propuesta'):
        return _clarify('Indica el nombre o código de la propuesta, o escribe «todas las propuestas».', original)
    months, text, period_error = _extract_months(text)
    if period_error:
        return _clarify(period_error, original)
    for phrase in ('todos los meses', 'todo el ano', 'ano completo'):
        if _phrase(text, phrase):
            if months:
                return _clarify('Selecciona meses específicos o el año completo.', original)
            months = list(range(1, 13))
            text = _remove(text, phrase)
    years = re.findall(r'\b(?:20\d{2}|2100)\b', text)
    if len(set(years)) > 1:
        return _clarify('Selecciona uno o varios meses dentro de un mismo año por consulta.', original)
    if months:
        selected.update(month=months[0], months=months if len(months) > 1 else None)
    if years:
        selected['year'] = int(years[0])
        text = _remove(text, years[0])
    relative_period = False
    for phrase in ('mes anterior', 'mes pasado', 'este mes', 'mes actual'):
        if _phrase(text, phrase):
            relative_period = True
            if compare and len(_months(original)) > 1:
                return _clarify('Indica los meses y el año con los que quieres comparar este conjunto.', original)
            base = date(original['year'], original['month'], 1) if compare and original['year'] and original['month'] else today.replace(day=1)
            target = base - timedelta(days=1) if phrase in {'mes anterior', 'mes pasado'} else base
            if months or years:
                return _clarify('Usa un mes concreto o un período relativo, por ejemplo «mes anterior».', original)
            selected.update(year=target.year, month=target.month, months=None)
            text = _remove(text, phrase)
    # Accept common verb phrases, including "se a realizado", without dropping
    # a standalone A (school grade), a code letter or an unknown qualifier.
    text = re.sub(r'\b(?:se\s+(?:a|ha|han)|ha|han)\s+(?:realizad[oa]s?|hech[oa]s?)\b',
                  'se realizaron', text)
    if not selected['metric']:
        return _clarify(HELP, selected)
    if selected['metric'] in farogpt_data_quality.REPORTS:
        farogpt_data_quality.require_access(db, user)
    proposal_problem = _default_proposal(selected, proposals)
    missing_period = selected['metric'] != 'record_issues' and (not selected['year'] or not selected['month'])
    if missing_period or proposal_problem:
        if len(text) > 800:
            return _clarify('Escribe nuevamente la consulta completa con el período y la propuesta.', original)
        selected['pending_terms'] = text.strip()
        messages = []
        if missing_period:
            if selected['month']:
                messages.append('¿De qué año quieres consultar esos meses?')
            else:
                messages.append('¿Qué mes o meses' + (f' de {selected["year"]} quieres consultar?' if selected['year'] else ' quieres consultar y de qué año?') +
                                ' Por ejemplo: «agosto y septiembre de 2026».')
        if proposal_problem:
            messages.append(proposal_problem['message'])
        else:
            name = next((p.name for p in proposals if p.proposal_id == selected['proposal_id']), 'Todas las propuestas')
            messages.append('Propuesta: ' + name + '.')
        return _clarify(' '.join(messages), selected, proposal_problem['suggestions'] if proposal_problem else [])
    selected = _authorized_context(selected, user, residentials, proposals)
    try:
        data = _dataset(db, user, selected, proposals, today=today)
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        return _clarify(str(exc.detail), original)
    if selected['metric'] in {'no_duplicado', 'duplicado'}:
        for phrase in farogpt_reports.ALIASES[selected['metric']]:
            text = _remove(text, phrase)
    fields, text = (set(), text) if selected['metric'] in SUPERVISION_REPORTS else _fields(text, data, farogpt_reports.ALIASES[selected['metric']])
    if len(fields) > 1:
        return _clarify('Indica un campo a la vez o pide el resumen del reporte para ver todos sus indicadores.', original)
    if fields:
        selected['field'] = fields.pop()
    for phrase in farogpt_reports.ALIASES[selected['metric']]:
        text = _remove(text, phrase)
    if any(_phrase(text, phrase) for phrase in SUMMARY_PHRASES):
        selected['field'] = None
        for phrase in SUMMARY_PHRASES:
            text = _remove(text, phrase)
    # An unsupported qualifier (day range, unknown residential, etc.)
    # must not disappear into a plausible but unfiltered number.
    words = set(text.split())
    allowed = set(QUERY_WORDS)
    if selected['metric'] in SUPERVISION_REPORTS:
        allowed.update('que lista listame'.split())
    if selected['metric'] == 'attendance_pending':
        allowed.add('residenciales')
    if selected['metric'] == 'session_issues':
        allowed.update('actividades sesiones tienen les o u'.split())
    if words - allowed:
        return _clarify('No pude identificar todos los campos o filtros. Puedes pedir el resumen o un campo del reporte.',
                        original, [f'Resumen de {data["title"]}' +
                                   (f' {dict(MONTHS)[selected["month"]]} {selected["year"]}' if selected['month'] and selected['year'] else '')])
    if compare:
        if selected['metric'] == 'record_issues':
            return _clarify('Los expedientes se revisan completos, sin corte mensual. Cambia de propuesta o residencial para consultar otro alcance.', original)
        if not months and not years and not relative_period:
            return _clarify('¿Con qué mes y año quieres comparar la consulta anterior?', original)
        if not all(original[k] for k in ('metric', 'year', 'month')):
            return _clarify('Consulta primero un mes y después pide compararlo con otro.', selected)
        if any(selected[k] != original[k] for k in ('metric', 'field', 'residential_id', 'proposal_id', 'proposal_scope', 'activity_code', 'issue_filter')):
            return _clarify('Para comparar meses conservaré el indicador, el código de actividad, el residencial y la propuesta de la consulta anterior.', original)
        if selected['metric'] not in TITLES and (len(_months(selected)) > 1 or len(_months(original)) > 1):
            return _clarify('Este reporte muestra cada mes por separado. Para una comparación numérica selecciona un mes de cada período.', original)
        result = summary(db, user, original, today=today)
        other = _result(selected, residentials, proposals, data)
        result['comparison'] = {'period': other['period'], 'value': other['value'],
                                'difference': result['value'] - other['value'], 'report_url': other['report_url']}
        return result
    return _result(selected, residentials, proposals, data)
