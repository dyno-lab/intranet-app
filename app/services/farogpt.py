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
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import distinct, func, select

from app.core.residential_scope import has_global_residential_access
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential
from app.services.participant_courses import MONTHS
from app.services import farogpt_reports

URL = '/ui/farogpt'
TITLES = {'people': 'Participantes únicos', 'duplicates': 'Participaciones (duplicados)',
          'activities': 'Actividades / servicios'}
DEFINITIONS = {
    'people': 'Cada persona se cuenta una sola vez en el período, entre las propuestas seleccionadas.',
    'duplicates': 'Se cuenta cada participación confirmada, incluida la primera de cada persona.',
    'activities': 'Se cuenta cada sesión registrada una sola vez, tenga o no participaciones confirmadas.',
}
HELP = ('Puedo consultar No Duplicado, Duplicados, ADM, notas, embarazo, deserción, visitas, '
        'referidos, cursos, Bonafide, Certificación, VCA, Cotejo, programas, productividad y el informe completo. '
        'Indica el mes y año, un residencial o «global» y, si deseas, una propuesta. '
        'Ejemplo: «Informe administrativo global de octubre 2026».')


class QueryContext(BaseModel):
    model_config = ConfigDict(extra='forbid')
    metric: Literal['people', 'duplicates', 'activities', 'no_duplicado', 'duplicado',
                    'adm', 'notes', 'pregnancy', 'dropout', 'visits', 'courses', 'bonafide',
                    'certification', 'vca', 'cotejo', 'programs', 'productivity', 'complete'] | None = None
    field: str | None = Field(default=None, max_length=80)
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    residential_id: int | None = Field(default=None, gt=0)
    proposal_id: int | None = Field(default=None, gt=0)


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
        return QueryContext.model_validate(value).model_dump()
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


def _dataset(db, user, context, proposals):
    ids = [context['proposal_id']] if context['proposal_id'] else [p.proposal_id for p in proposals]
    if context['metric'] not in TITLES:
        return farogpt_reports.build(context['metric'], db, user, ids, context['month'],
                                     context['year'], context['residential_id'])
    return _attendance_dataset(db, context, ids)


def summary(db, user, context):
    """Recalculate the selected source report with its own reporting definitions."""
    residentials, proposals = catalogs(db, user)
    context = _authorized_context(context, user, residentials, proposals)
    metric, year, month = (context[k] for k in ('metric', 'year', 'month'))
    if metric is None or year is None or month is None:
        raise HTTPException(422, 'Indica el indicador, el mes y el año.')
    return _result(context, residentials, proposals, _dataset(db, user, context, proposals))


def _attendance_dataset(db, context, ids):
    year, month = context['year'], context['month']
    start = date(year, month, 1)
    end = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    conditions = [ActivitySession.proposal_id.in_(ids), ActivitySession.session_date >= start,
                  ActivitySession.session_date < end]
    if context['residential_id'] is not None:
        conditions.append(ActivitySession.residential_id == context['residential_id'])
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
    return {'title': TITLES[context['metric']], 'primary': context['metric'],
            'metrics': [{'key': k, 'label': TITLES[k], 'value': value, 'definition': DEFINITIONS[k],
                         'aliases': []} for k, value in metrics.items()], 'tables': [],
            'source_title': 'Conteo general de actividades y participaciones',
            'note': ('El residencial corresponde al lugar de la actividad. '
                     'Participantes únicos usa la identidad de persona vinculada a la propuesta. ' +
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
    previous = date(year, month, 1) - timedelta(days=1)
    params = {k: v for k, v in context.items() if v is not None}
    return {
        'type': 'result', 'title': primary['label'] if context['field'] else data['title'],
        'value': primary['value'], 'unit': primary.get('unit', ''),
        'metrics': {m['key']: m['value'] for m in data['metrics']},
        'cards': [primary] if context['field'] else data['metrics'],
        'tables': [] if context['field'] else data['tables'],
        'source_title': data.get('source_title', data['title']), 'source_url': data.get('source_url'),
        'definition': primary['definition'], 'context': context,
        'period': f'{dict(MONTHS)[month]} {year}', 'residential': residential, 'proposal': proposal,
        'proposal_names': [p.name for p in proposals if p.proposal_id in ids],
        'report_url': URL + '/informe?' + urlencode(params),
        'suggestions': [f'Comparar con {dict(MONTHS)[previous.month].lower()} de {previous.year}'],
        'note': data.get('note'),
    }


def _normalize(value):
    value = ''.join(c for c in unicodedata.normalize('NFKD', value.lower()) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+', value))


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
    selected = dict(original)
    text = _normalize(question)
    if not text or len(question) > 800:
        return _clarify(HELP)
    if text in {'hola', 'ayuda', 'que puedes hacer', 'buenos dias', 'buenas tardes'}:
        return _clarify(HELP, original)
    reports = _report_in_question(text)
    if len(reports) > 1:
        return _clarify('Consulta un reporte a la vez. ' + HELP, original)
    if reports:
        selected.update(metric=reports[0], field=None)
    compare = bool(re.search(r'\b(compara|comparar|comparame|comparalo)\b', text))
    if re.search(r'\bpor (?:cada )?(?:residencial|propuesta|mes)\b', text):
        return _clarify('Por ahora puedo consultar el total de un residencial o de todos, para un mes. '
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
    proposal, text, ambiguous = _entity(text, proposals, 'propuesta')
    if ambiguous:
        return _clarify('Indica una sola propuesta por nombre o código, o escribe «todas las propuestas».', original)
    if proposal:
        selected['proposal_id'] = proposal.proposal_id
    if _phrase(text, 'todas las propuestas'):
        selected['proposal_id'] = None
        text = _remove(text, 'todas las propuestas')
    elif not proposal and _phrase(text, 'propuesta'):
        return _clarify('Indica el nombre o código de la propuesta, o escribe «todas las propuestas».', original)
    months = []
    for number, name in MONTHS:
        normalized = _normalize(name)
        if _phrase(text, normalized):
            months.append(number)
            text = _remove(text, normalized)
    years = re.findall(r'\b(?:20\d{2}|2100)\b', text)
    if len(set(months)) > 1 or len(set(years)) > 1:
        return _clarify('Indica un mes y un año por consulta. Después puedes pedir «comparar con» otro mes.', original)
    if months:
        selected['month'] = months[0]
    if years:
        selected['year'] = int(years[0])
        text = _remove(text, years[0])
    relative_period = False
    for phrase in ('mes anterior', 'mes pasado', 'este mes', 'mes actual'):
        if _phrase(text, phrase):
            relative_period = True
            base = date(original['year'], original['month'], 1) if compare and original['year'] and original['month'] else today.replace(day=1)
            target = base - timedelta(days=1) if phrase in {'mes anterior', 'mes pasado'} else base
            if months or years:
                return _clarify('Usa un mes concreto o un período relativo, por ejemplo «mes anterior».', original)
            selected.update(year=target.year, month=target.month)
            text = _remove(text, phrase)
    if not selected['metric']:
        return _clarify(HELP, selected)
    if not selected['year'] or not selected['month']:
        return _clarify('¿Qué mes y año quieres consultar? Por ejemplo: «marzo de 2026».', selected)
    selected = _authorized_context(selected, user, residentials, proposals)
    try:
        data = _dataset(db, user, selected, proposals)
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        return _clarify(str(exc.detail), original)
    if selected['metric'] in {'no_duplicado', 'duplicado'}:
        for phrase in farogpt_reports.ALIASES[selected['metric']]:
            text = _remove(text, phrase)
    fields, text = _fields(text, data, farogpt_reports.ALIASES[selected['metric']])
    if len(fields) > 1:
        return _clarify('Indica un campo a la vez o pide el resumen del reporte para ver todos sus indicadores.', original)
    if fields:
        selected['field'] = fields.pop()
    for phrase in farogpt_reports.ALIASES[selected['metric']]:
        text = _remove(text, phrase)
    if any(_phrase(text, phrase) for phrase in ('resumen', 'todos los campos', 'todos los indicadores')):
        selected['field'] = None
        for phrase in ('resumen', 'todos los campos', 'todos los indicadores'):
            text = _remove(text, phrase)
    # An unsupported qualifier (day range, unknown residential, etc.)
    # must not disappear into a plausible but unfiltered number.
    words = set(text.split())
    allowed = set('cuantos cuantas hubo hay fueron tenemos tuvo tuvo total cantidad numero de del el la los las '
                  'en para por durante y con al un una me puedes puede dime dame saber quiero quisiera '
                  'consulta consultar muestra mostrar indicame residencial propuesta mes ano faro '
                  'compara comparar comparame comparalo favor por favor registrados registradas '
                  'atendidos atendidas este ese fueron se atendieron participaron informe reporte '
                  'datos informacion resultado resultados seguimiento cual cuales es son las los'.split())
    if words - allowed:
        return _clarify('No pude identificar todos los campos o filtros. Puedes pedir el resumen o un campo del reporte.',
                        original, [f'Resumen de {data["title"]} {dict(MONTHS)[selected["month"]]} {selected["year"]}'])
    if compare:
        if not months and not years and not relative_period:
            return _clarify('¿Con qué mes y año quieres comparar la consulta anterior?', original)
        if not all(original[k] for k in ('metric', 'year', 'month')):
            return _clarify('Consulta primero un mes y después pide compararlo con otro.', selected)
        if any(selected[k] != original[k] for k in ('metric', 'field', 'residential_id', 'proposal_id')):
            return _clarify('Para comparar meses conservaré el indicador, el residencial y la propuesta de la consulta anterior.', original)
        result = summary(db, user, original)
        other = _result(selected, residentials, proposals, data)
        result['comparison'] = {'period': other['period'], 'value': other['value'],
                                'difference': result['value'] - other['value'], 'report_url': other['report_url']}
        return result
    return _result(selected, residentials, proposals, data)
