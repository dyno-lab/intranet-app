"""Read-only fiscal lists with batch-loaded changes and independent pagination."""
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import HTTPException
from sqlalchemy import select

from app.models.community import CPFiscalYear, CPParticipant, CPParticipantProgram, CPProgram
from app.models.community_catalog import CPProfileField, CPProfileValue
from app.models.community_fiscal import CPFiscalParticipant
from app.services.community_fiscal import build_participant_snapshot, fiscal_history_ids, snapshot_changes
from app.services.community_participants import _integer, participant_query, participant_search


def fiscal_participant_lists(db, context, fiscal_year_id, params):
    program_id = _integer(params, 'program_id', minimum=1, maximum=2147483647)
    if program_id is not None and program_id not in context.visible_program_ids:
        raise HTTPException(403, 'Programa no autorizado en este contexto de Comunidad.')
    filters = {'q': params.get('q', '').strip()[:150], 'program_id': program_id,
               'available_filter': params.get('available_filter', 'pending'),
               'sync_filter': params.get('sync_filter', 'pending')}
    if filters['available_filter'] not in {'pending', 'never'} or filters['sync_filter'] not in {'pending', 'all'}:
        raise HTTPException(422, 'Seleccione filtros de participantes válidos.')
    query = participant_query(context)
    if program_id is not None:
        query = query.where(select(CPParticipantProgram.participant_id).where(
            CPParticipantProgram.participant_id == CPParticipant.participant_id,
            CPParticipantProgram.program_id == program_id).exists())
    if filters['q']:
        query = query.where(participant_search(filters['q']))
    ids = query.with_only_columns(CPParticipant.participant_id)
    people = db.scalars(query.order_by(CPParticipant.apellido_paterno, CPParticipant.apellido_materno,
                                     CPParticipant.nombre, CPParticipant.participant_id)).all()
    associations, visible_programs, profiles, other_years = (defaultdict(list) for _ in range(4))
    labels = {}
    for link, program in db.execute(select(CPParticipantProgram, CPProgram).join(
        CPProgram, CPProgram.program_id == CPParticipantProgram.program_id).where(
        CPParticipantProgram.participant_id.in_(ids)).order_by(CPProgram.code)):
        associations[link.participant_id].append(link)
        labels[program.program_id] = f'{program.code} · {program.name}'
        if program.program_id in context.visible_program_ids:
            visible_programs[link.participant_id].append(program.code)
    for field, value in db.execute(select(CPProfileField, CPProfileValue).join(
        CPProfileValue, CPProfileValue.field_id == CPProfileField.field_id).where(CPProfileValue.participant_id.in_(ids))):
        profiles[value.participant_id].append((field, value))
    snapshots = {}
    for row, code in db.execute(select(CPFiscalParticipant, CPFiscalYear.code).join(
        CPFiscalYear, CPFiscalYear.fiscal_year_id == CPFiscalParticipant.fiscal_year_id).where(
        CPFiscalParticipant.participant_id.in_(ids)).order_by(CPFiscalYear.start_date)):
        other_years[row.participant_id].append(code)
        if row.fiscal_year_id == fiscal_year_id:
            snapshots[row.participant_id] = row
    used = fiscal_history_ids(db, fiscal_year_id, ids) if fiscal_year_id else set()
    available, assigned = [], []
    counts = {'assigned': 0, 'pending': 0, 'available': 0, 'never': 0}
    for participant in people:
        pid = participant.participant_id
        row = {'participant': participant, 'programs': visible_programs[pid], 'years': other_years[pid]}
        snapshot = snapshots.get(pid)
        if snapshot is None:
            counts['available'] += 1
            if not other_years[pid]:
                counts['never'] += 1
            if filters['available_filter'] != 'never' or not other_years[pid]:
                available.append(row)
            continue
        current = build_participant_snapshot(db, participant, profile_rows=profiles[pid], program_rows=associations[pid])
        changes = snapshot_changes(snapshot, current, associations[pid], labels)
        counts['assigned'] += 1
        counts['pending'] += bool(changes)
        reason = ('Tiene historial en este año fiscal; gestione la baja del programa.' if pid in used else
                  'Cambie a Administración general para gestionar todos los programas del expediente.'
                  if not {p.program_id for p in associations[pid]}.issubset(context.visible_program_ids) else None)
        row.update(snapshot=snapshot, changes=changes, remove_reason=reason)
        if filters['sync_filter'] != 'pending' or changes:
            assigned.append(row)
    result = {'filters': filters, 'counts': counts}
    query_values = {'fiscal_year_id': fiscal_year_id or '', **{k: v for k, v in filters.items() if v is not None}}
    for key, rows in (('available', available), ('assigned', assigned)):
        pages = max(1, (len(rows) + 49) // 50)
        # Honor the old page parameter for links to the former single table.
        page = min(_integer(params, key + '_page', default=_integer(params, 'page', default=1, minimum=1,
                   maximum=2147483647), minimum=1, maximum=2147483647), pages)
        result.update({key + '_rows': rows[(page-1)*50:page*50], key + '_total': len(rows),
                       key + '_page': page, key + '_pages': pages})
        query_values[key + '_page'] = page
    result['return_query'] = urlencode(query_values)
    result['page_links'] = {key: {direction: '/community/fiscal-participants?' + urlencode({
        **query_values, key + '_page': number}) + '#' + key + '-participants'
        for direction, number in (('prev', max(1, result[key + '_page']-1)),
                                  ('next', min(result[key + '_pages'], result[key + '_page']+1)))}
        for key in ('available', 'assigned')}
    return result
