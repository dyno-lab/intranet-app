"""Read-only source validation with separately audited, optimistic follow-up writes."""
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from itertools import combinations
import json
import math
import unicodedata

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, func, extract
from app.core.roles import can_read_globally
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.data_validation import DataValidationIssue, DataValidationEvent
from app.models.participant import Participant
from app.models.participant_transfer import ParticipantTransfer
from app.models.participant_profile_field import ParticipantProfileField
from app.models.participant_profile_field_value import ParticipantProfileFieldValue
from app.models.person import Person
from app.models.proposal import Proposal
from app.models.proposal_participant import ProposalParticipant
from app.models.residential import Residential

OPEN = {'pending', 'review'}
STATUS = {'pending': 'Pendiente', 'review': 'En revisión', 'resolved': 'Resuelto', 'justified': 'Justificado'}
KIND = {'record': 'Expedientes', 'attendance': 'Asistencias', 'duplicate': 'Posibles duplicados'}
URL = '/automatizaciones/faro/validacion'


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'))


def _digest(value):
    return sha256(_json(value).encode()).hexdigest()


def _text(value):
    return str(value or '').strip()


def normalized_name(value):
    return ' '.join(''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                           if not unicodedata.combining(c)).split())


def scope_id(user):
    rid = getattr(user, '_active_residential_id', None)
    if rid is None and not can_read_globally(user):
        raise HTTPException(403, 'Selecciona un residencial autorizado de Faro.')
    return rid


def _validate_scope(db, user, proposal_id, residential_id, year, months):
    rid = scope_id(user)
    if not 2000 <= year <= 2100 or not months or any(m not in range(1, 13) for m in months):
        raise HTTPException(422, 'Selecciona un año válido y al menos un mes entre enero y diciembre.')
    if proposal_id is not None and db.get(Proposal, proposal_id) is None:
        raise HTTPException(404, 'Propuesta no encontrada.')
    if residential_id is not None:
        if rid is not None and residential_id != rid:
            raise HTTPException(403, 'El residencial no corresponde a tu contexto autorizado.')
        if db.get(Residential, residential_id) is None:
            raise HTTPException(404, 'Residencial no encontrado.')
    return rid


def _scope_query(statement, model, proposal_id, rid):
    if proposal_id is not None:
        statement = statement.where(model.proposal_id == proposal_id)
    if rid is not None:
        statement = statement.where(model.residential_id == rid)
    return statement


def _in_filter(item, residential_id):
    return residential_id is None or residential_id in (item['residential_id'], item.get('other_residential_id'))


def scan(db, user, *, proposal_id, residential_id, year, months, today):
    """No source writes. Authorization precedes grouping, including duplicate comparisons."""
    rid = _validate_scope(db, user, proposal_id, residential_id, year, months)
    base = _scope_query(select(ProposalParticipant, Person, Participant)
        .join(Person, Person.person_id == ProposalParticipant.person_id)
        .outerjoin(Participant, Participant.participant_id == Person.legacy_participant_id),
        ProposalParticipant, proposal_id, rid)
    enrollments = db.execute(base.order_by(ProposalParticipant.proposal_participant_id)).all()
    # SQL subqueries avoid SQL Server's 2,100-parameter limit for large proposals.
    linked_ids = base.with_only_columns(Person.legacy_participant_id).order_by(None)
    values = {(v.participant_id, v.participant_profile_field_id): v.value for v in db.scalars(
        select(ParticipantProfileFieldValue).where(ParticipantProfileFieldValue.participant_id.in_(linked_ids)))}
    fields = list(db.scalars(select(ParticipantProfileField).where(
        ParticipantProfileField.is_active == True, ParticipantProfileField.applies_to_new_list == True,
        ParticipantProfileField.is_required == True)))
    transfers = {(t.participant_id, t.from_residential_id, t.effective_date): t for t in db.scalars(
        select(ParticipantTransfer).where(ParticipantTransfer.participant_id.in_(linked_ids)))}
    found, representatives = {}, {}

    def add(rule, title, actual, expected, *, records=(), session=None, priority='Alta', action=None):
        if session is not None:
            pid, residential, other = session.proposal_id, session.residential_id, None
            kind, identity, day = 'attendance', session.session_id, session.session_date
        else:
            pid, residential = records[0]['proposal_id'], records[0]['residential_id']
            other = records[1]['residential_id'] if len(records) > 1 else None
            kind = 'duplicate' if len(records) > 1 else 'record'
            identity = sorted(r['person_id'] for r in records) if kind == 'duplicate' else records[0]['id']
            day = None
        key = _digest([pid, rule, identity])
        payload = dict(key=key, proposal_id=pid, residential_id=residential, other_residential_id=other,
            kind=kind, rule=rule, title=title, priority=priority, actual=actual, expected=expected,
            records=list(records), session_id=session.session_id if session else None,
            session_date=day.isoformat() if day else None,
            record_label=(session.control_number or 'Sesión '+str(session.session_id)) if session else
                         ' / '.join(r['expediente'] for r in records),
            source_url='/ui/listado/'+str(session.session_id) if session else None,
            action=action or ('Corregir la sesión original y volver a revalidar.' if session else
                'Revisar el expediente original y volver a revalidar. El historial de traslados se conserva.'))
        # Display-only links and calculated ages are excluded from evidence fingerprints.
        fingerprint_expected = 'Nacimiento no posterior a la referencia' if rule == 'birth_future' else expected
        payload['fingerprint'] = _digest([rule, actual, fingerprint_expected, pid, residential, other,
            [(r['id'], r['person_id'], r['name'], r['dob'], r['historical']) for r in records]])
        if _in_filter(payload, residential_id):
            found[key] = payload

    for record, person, participant in enrollments:
        historical = record.valid_until is not None
        audit = transfers.get((person.legacy_participant_id, record.residential_id, record.valid_until)) if historical else None
        source_url = None
        if audit:
            source_url = f'/ui/new-list/{audit.participant_id}/history/{audit.transfer_id}'
        elif participant and participant.residential_id == record.residential_id:
            source_url = f'/ui/new-list/{participant.participant_id}/expediente'
        cutoff = record.valid_until - timedelta(days=1) if historical else today
        dob = record.fecha_nacimiento
        age = cutoff.year-dob.year-((cutoff.month,cutoff.day)<(dob.month,dob.day)) if dob else None
        info = dict(id=record.proposal_participant_id, person_id=record.person_id,
            proposal_id=record.proposal_id, residential_id=record.residential_id,
            expediente=record.expediente_num or 'Sin número de expediente',
            name=' '.join(_text(getattr(record,f)) for f in ('nombre','inicial','apellido_paterno','apellido_materno') if _text(getattr(record,f))),
            dob=dob.isoformat() if dob else None, age=age, age_date=cutoff.isoformat(),
            historical=historical, source_url=source_url)
        current = representatives.get((record.proposal_id, record.person_id))
        rank = (not historical, record.proposal_participant_id)
        if current is None or rank > current[0]:
            representatives[(record.proposal_id,record.person_id)] = (rank, record, info)
        for field, label in (('expediente_num','Número de expediente'),('nombre','Nombre'),
                             ('apellido_paterno','Primer apellido'),('genero','Género')):
            if not _text(getattr(record,field)):
                add('missing_'+field, label+' sin registrar', 'Sin registrar', label+' completo', records=[info])
        if record.genero and _text(record.genero).upper() not in {'F','M'}:
            add('gender_invalid','Género fuera del catálogo',record.genero,'F o M, según el catálogo de Faro',records=[info])
        if dob is None:
            add('birth_missing','Fecha de nacimiento sin registrar','Sin registrar','Fecha de nacimiento válida',records=[info])
        elif dob > cutoff:
            add('birth_future','Nacimiento posterior a la fecha de referencia',str(dob),
                'Nacimiento en o antes de '+str(cutoff),records=[info])
        elif age > 120:
            add('age_unusual','Edad inusual: revisar nacimiento',str(dob),'Nacimiento verificado; edad calculada mayor de 120 años',
                records=[info],priority='Revisión')
        saved = json.loads(audit.profile_snapshot_json).get('fields',[]) if audit and audit.profile_snapshot_json else None
        historical_values = {v['key']:v.get('value') for v in saved} if saved is not None else None
        for field in fields:
            if historical:
                # Do not invent missing historical fields or apply fields introduced after departure.
                created = field.created_at.date() if field.created_at else today
                if historical_values is None or created > cutoff:
                    continue
                value = historical_values.get(field.field_key)
            elif participant:
                value = values.get((participant.participant_id,field.participant_profile_field_id))
            else:
                value = None
            if not _text(value):
                add('profile_'+str(field.participant_profile_field_id),field.label+' sin registrar',
                    'Sin registrar','Campo adicional obligatorio: '+field.label,records=[info],priority='Media')

    groups = defaultdict(list)
    for _, record, info in representatives.values():
        if record.fecha_nacimiento and _text(record.nombre) and _text(record.apellido_paterno):
            groups[(record.proposal_id,normalized_name(info['name']),record.fecha_nacimiento)].append(info)
    for members in groups.values():
        # Stable pairs cannot turn a transferred stay or a second proposal into another person.
        for pair in combinations(sorted(members,key=lambda r:r['person_id']),2):
            add('duplicate','Nombre y nacimiento coinciden','Coincidencia de nombre completo y nacimiento',
                'Comprobar si son personas distintas',records=pair,priority='Revisión',
                action='Comparar ambos expedientes. No se unen ni se eliminan automáticamente. '
                       'Documentar una excepción si son personas distintas; preservar todas las participaciones.')

    attended = (select(Attendance.session_id,func.count().label('total')).where(Attendance.attended == True,
        or_(Attendance.participant_id.is_not(None),Attendance.proposal_participant_id.is_not(None)))
        .group_by(Attendance.session_id).subquery())
    sessions = _scope_query(select(ActivitySession,func.coalesce(attended.c.total,0))
        .outerjoin(attended,attended.c.session_id==ActivitySession.session_id),ActivitySession,proposal_id,rid)
    sessions = sessions.where(ActivitySession.proposal_id.is_not(None),ActivitySession.session_date<=today,
        extract('year',ActivitySession.session_date)==year,extract('month',ActivitySession.session_date).in_(months))
    if residential_id is not None:
        sessions=sessions.where(ActivitySession.residential_id==residential_id)
    for session, count in db.execute(sessions):
        if count == 0:
            add('no_participations','Sesión sin participaciones confirmadas',0,'Al menos una participación confirmada',session=session)
        if session.hours is None or not math.isfinite(session.hours) or session.hours <= 0 or session.hours > 24:
            add('hours','Horas de sesión faltantes o inválidas',str(session.hours) if session.hours is not None else 'Sin registrar',
                'Horas mayores que 0 y no mayores que 24',session=session)
    return found


def _saved(db,user,proposal_id,residential_id,year,months):
    query=_scope_query(select(DataValidationIssue),DataValidationIssue,proposal_id,scope_id(user))
    rid=scope_id(user)
    if rid is not None:
        query=query.where(or_(DataValidationIssue.kind!='duplicate',DataValidationIssue.other_residential_id==rid))
    if residential_id is not None:
        query=query.where(or_(DataValidationIssue.residential_id==residential_id,DataValidationIssue.other_residential_id==residential_id))
    query=query.where(or_(DataValidationIssue.session_date.is_(None),and_(
        extract('year',DataValidationIssue.session_date)==year,extract('month',DataValidationIssue.session_date).in_(months))))
    return {r.issue_key:r for r in db.scalars(query)}


def review(db,user,proposal_id=None,residential_id=None,year=None,months=(),today=None):
    today=today or date.today()
    current=scan(db,user,proposal_id=proposal_id,residential_id=residential_id,year=year,months=months,today=today)
    saved=_saved(db,user,proposal_id,residential_id,year,months)
    result=[]
    for key in sorted(set(current)|set(saved)):
        stored=saved.get(key)
        live=current.get(key)
        item=dict(live or json.loads(stored.evidence_json))
        changed=stored and live and (stored.fingerprint!=live['fingerprint'] or stored.status=='resolved')
        item.update(status='pending' if changed or stored is None else stored.status,
            revision=stored.revision if stored else 0, assignee=stored.assignee if stored else None,
            due_on=stored.due_on if stored else None,
            justification=stored.justification if stored and not changed else None,
            checked_at=stored.checked_at if stored else None,source_present=live is not None)
        item['token']=key+'.'+item['fingerprint']+'.'+str(item['revision'])
        item['overdue']=item['status'] in OPEN and item['due_on'] is not None and item['due_on']<today
        # A disappeared source retains evidence until explicit revalidation; no stale edit links.
        if not live:
            item['source_url']=None
            item['records']=[{**r,'source_url':None} for r in item['records']]
        result.append(item)
    result.sort(key=lambda r:(r['status'] not in OPEN,not r['overdue'],r['kind'],r['record_label'],r['rule']))
    opened=[r for r in result if r['status'] in OPEN]
    resmap={r.residential_id:r for r in db.scalars(select(Residential))}
    proposalmap={r.proposal_id:r for r in db.scalars(select(Proposal))}
    def names(row):
        return ' / '.join(resmap[rid].name if rid in resmap else 'Sin residencial' for rid in
            dict.fromkeys([row['residential_id']]+([row['other_residential_id']] if row['other_residential_id'] is not None else [])))
    for row in result:
        row['residential_name']=names(row)
        row['proposal_name']=proposalmap[row['proposal_id']].name if row['proposal_id'] in proposalmap else 'Propuesta no disponible'
        row['assignee_name']=('Supervisión' if row['assignee']=='supervision' else 'Facilitador · '+names(row)) if row['assignee'] else 'Sin asignar'
    residential_rows=[]
    # Shared duplicate pairs are displayed in each affected residential; global counters deduplicate.
    ids=set(r['residential_id'] for r in opened)|{r['other_residential_id'] for r in opened if r['other_residential_id'] is not None}
    if residential_id is not None:
        ids.intersection_update({residential_id})
    for rid in sorted(ids,key=lambda n:(n is None,n or 0)):
        group=[r for r in opened if rid==r['residential_id'] or (rid is not None and rid==r['other_residential_id'])]
        residential_rows.append(dict(id=rid,name=resmap[rid].name if rid in resmap else 'Sin residencial',open=len(group),
            record=sum(r['kind']=='record' for r in group),attendance=sum(r['kind']=='attendance' for r in group),
            duplicate=sum(r['kind']=='duplicate' for r in group),unassigned=sum(not r['assignee'] for r in group),
            overdue=sum(r['overdue'] for r in group)))
    counts=dict(open=len(opened),records=len({p['person_id'] for r in opened for p in r['records']}),
        attendance=len({r['session_id'] for r in opened if r['session_id'] is not None}),residentials=len(ids))
    return dict(findings=result,counts=counts,residential_rows=residential_rows,today=today)


def _event(db,issue,user,kind,message):
    db.add(DataValidationEvent(issue_key=issue.issue_key,actor_user_id=user.user_id,actor_name=user.username,
                               kind=kind,message=message[:2000]))


def _store(db,user,payload,stored):
    if stored is None:
        stored=DataValidationIssue(issue_key=payload['key'],status='pending',revision=0)
        db.add(stored)
        kind='detected'
    else:
        kind='reopened' if stored.status in {'resolved','justified'} else 'changed'
    changed=stored.fingerprint!=payload['fingerprint'] or stored.status=='resolved'
    if changed:
        stored.status='pending';stored.justification=None
    for name in ('proposal_id','residential_id','other_residential_id','kind','fingerprint'):
        setattr(stored,name,payload[name])
    stored.session_date=date.fromisoformat(payload['session_date']) if payload['session_date'] else None
    stored.evidence_json=_json(payload)
    stored.checked_at=datetime.now(timezone.utc)
    stored.revision+=1
    db.flush()
    if changed:
        _event(db,stored,user,kind,'Hallazgo detectado.' if kind=='detected' else 'Los datos cambiaron; se requiere nueva revisión.')
    return stored


def mutate(db,user,action,filters,*,targets=(),assignee=None,due_on=None,note=''):
    if user.role not in {'admin','supervisor','user'}:
        raise HTTPException(403,'Acceso de consulta solamente.')
    if action not in {'assign','justify','revalidate'}:
        raise HTTPException(404,'Acción no encontrada.')
    today=filters.get('today') or date.today()
    _validate_scope(db,user,filters.get('proposal_id'),filters.get('residential_id'),filters['year'],filters['months'])
    # Serialize validation writes per proposal; normal source forms retain their existing controls.
    lock=select(Proposal.proposal_id).order_by(Proposal.proposal_id).with_hint(Proposal,'WITH (UPDLOCK, HOLDLOCK)',dialect_name='mssql')
    if filters.get('proposal_id') is not None:
        lock=lock.where(Proposal.proposal_id==filters['proposal_id'])
    db.execute(lock).all()
    current=scan(db,user,**{**filters,'today':today})
    saved=_saved(db,user,filters.get('proposal_id'),filters.get('residential_id'),filters['year'],filters['months'])
    if action=='revalidate':
        closed=0
        for key,payload in current.items():
            _store(db,user,payload,db.get(DataValidationIssue,key))
        for key,issue in saved.items():
            if key not in current and issue.status in OPEN|{'justified'}:
                issue.status='resolved';issue.justification=None;issue.revision+=1;issue.checked_at=datetime.now(timezone.utc)
                _event(db,issue,user,'resolved','Revalidación: el dato cumple la regla o dejó de aplicar al registro de origen.')
                closed+=1
        db.flush()
        return closed
    if not targets or len(targets)>100:
        raise HTTPException(422,'Selecciona entre 1 y 100 hallazgos.')
    note=_text(note)
    if len(note)>1000:
        raise HTTPException(422,'Las indicaciones no pueden superar 1,000 caracteres.')
    if action=='justify' and (user.role not in {'admin','supervisor'} or len(targets)!=1):
        raise HTTPException(403,'Solo supervisión puede justificar un hallazgo individual.')
    if action=='justify' and not note:
        raise HTTPException(422,'Escribe la justificación y evidencia de la revisión.')
    if action=='assign':
        if assignee not in {'residential','supervision'} or (user.role=='user' and assignee!='residential'):
            raise HTTPException(403,'Responsable no autorizado.')
        if not isinstance(due_on,date) or due_on<today or due_on.year>2100:
            raise HTTPException(422,'La fecha límite debe ser hoy o posterior.')
    chosen={}
    for token in targets:
        parts=token.split('.')
        if len(parts)!=3 or parts[0] not in current:
            raise HTTPException(409,'El hallazgo cambió o no está en tu alcance. Revalida y vuelve a seleccionarlo.')
        key,fingerprint,version=parts
        payload=current[key];stored=db.get(DataValidationIssue,key)
        if fingerprint!=payload['fingerprint'] or version!=str(stored.revision if stored else 0):
            raise HTTPException(409,'Otro cambio modificó el hallazgo. Actualiza la página y vuelve a revisarlo.')
        if stored and stored.status=='justified' and stored.fingerprint==fingerprint:
            raise HTTPException(409,'El hallazgo ya tiene una excepción vigente.')
        chosen[key]=(payload,stored)
    for payload,stored in chosen.values():
        issue=_store(db,user,payload,stored)
        if action=='assign':
            cross_residential = payload['kind']=='duplicate' and payload['residential_id']!=payload['other_residential_id']
            issue.status='review';issue.assignee='supervision' if cross_residential else assignee;issue.due_on=due_on
            label='Supervisión' if issue.assignee=='supervision' else 'Facilitador del residencial'
            _event(db,issue,user,'assigned',f'{label} · Fecha límite: {due_on.isoformat()}. '+note)
        else:
            issue.status='justified';issue.justification=note
            _event(db,issue,user,'justified',note)
    db.flush()
    return len(chosen)
