"""Authenticated Faro validation screens and CSRF-protected tracking actions."""
import hmac
import secrets
from datetime import date, timedelta
from math import ceil
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.platform_permissions import ACCESS_AUTOMATION, require_platform_permission
from app.core.residential_scope import require_faro_access
from app.models.user import User
from app.models.proposal import Proposal
from app.models.person import Person
from app.models.participant import Participant
from app.models.residential import Residential
from app.models.data_validation import DataValidationEvent
from app.services import data_validation as service
from app.services.participant_courses import MONTHS

router=APIRouter(prefix=service.URL,dependencies=[Depends(require_platform_permission(ACCESS_AUTOMATION))])
templates=Jinja2Templates(directory='app/templates')
HEADERS={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}
RESULTS={'assigned':'Seguimiento guardado. El hallazgo permanece abierto hasta corregir y revalidar.',
         'justified':'Excepción documentada. Se conservará el historial de la revisión.',
         'revalidated':'Revalidación completada. Los hallazgos corregidos se actualizaron y las inconsistencias continúan abiertas.'}


def filters_from(values):
    def integer(name,default=None):
        value=str(values.get(name,'')).strip()
        try:
            return int(value) if value else default
        except ValueError as exc:
            raise HTTPException(422,'Filtro numérico inválido: '+name) from exc
    previous=date.today().replace(day=1)-timedelta(days=1)
    try:
        raw=values.getlist('months') or values.getlist('month')
        months=tuple(sorted({int(str(v).strip()) for v in raw if str(v).strip()})) or (previous.month,)
    except ValueError as exc:
        raise HTTPException(422,'Selecciona meses válidos.') from exc
    return dict(proposal_id=integer('proposal_id'),residential_id=integer('residential_id'),
                year=integer('year',previous.year),months=months)


def url_for(filters,**extra):
    params={key:value for key,value in {**filters,**extra}.items() if value is not None and value!=''}
    return service.URL+'?'+urlencode(params,doseq=True)


def navigation_from(values):
    kind=values.get('kind','all') or 'all'; state=values.get('status','open') or 'open'
    if kind not in {'all',*service.KIND} or state not in {'all','open',*service.STATUS}:
        raise HTTPException(422,'Tipo o estado de hallazgo inválido.')
    screen=values.get('view','')
    # Preserve old links while separating session findings from participant files.
    if screen not in {'records','activities','residentials'}:
        screen='activities' if kind=='attendance' else 'records'
    if screen=='activities':kind='attendance'
    elif screen=='records' and kind=='attendance':kind='all'
    try:number=max(1,int(values.get('page','1') or 1))
    except ValueError as exc:raise HTTPException(422,'Página inválida.') from exc
    return dict(kind=kind,status=state,view=screen,page=number)


def record_identity(record):
    # Current enrollments share the person's file even if a proposal kept an old number.
    # Closed stays remain separate from the current file and from other residentials.
    if record['historical']:
        return 'historical', record['person_id'], record['residential_id'], record['expediente'].strip().casefold()
    return 'current', record['person_id'], record['residential_id']


def decorate_findings(db, user, items, proposals):
    """Display current identifiers without changing saved evidence or file identity."""
    proposal_by_id = {p.proposal_id: p for p in proposals}
    person_ids = sorted({r['person_id'] for item in items for r in item['records']})
    current_files = {}
    rid = service.scope_id(user)
    # Bound parameters stay below SQL Server's limit, even for global reviews.
    for start in range(0, len(person_ids), 500):
        query = (select(Person.person_id, Participant.expediente_num, Participant.nombre,
                        Participant.inicial, Participant.apellido_paterno, Participant.apellido_materno)
                 .join(Participant, Participant.participant_id == Person.legacy_participant_id)
                 .where(Person.person_id.in_(person_ids[start:start + 500])))
        if rid is not None:
            query = query.where(Participant.residential_id == rid)
        for person_id, number, *names in db.execute(query):
            name = ' '.join(' '.join(str(value or '').split()) for value in names if str(value or '').strip())
            current_files[person_id] = (number or '', name)
    for item in items:
        proposal = proposal_by_id.get(item['proposal_id'])
        finalized = proposal is not None and proposal.status == 'finalized'
        item['proposal_finalized'] = finalized
        item['proposal_state_label'] = ('Estado de propuesta no disponible' if proposal is None else
            'Propuesta finalizada' if finalized else
            'Propuesta activa' if proposal.is_active and proposal.status == 'active' else 'Propuesta inactiva')
        for record in item['records']:
            # None means no authorized current link, not an inferred historical number.
            current = current_files.get(record['person_id'])
            record['current_expediente'] = current[0] if current is not None else None
            record['current_name'] = current[1] if current is not None else None
            record['proposal_name_differs'] = (current is not None and
                current[1].casefold() != ' '.join(record['name'].split()).casefold())


def group_findings(items):
    """One row per file or session; individual issue keys and source stays survive."""
    groups = {}
    for item in items:
        record = item['records'][0] if item['kind'] == 'record' else None
        key = (('record', record_identity(record)) if record else
               ('session', item['session_id']) if item['kind']=='attendance' else ('finding', item['key']))
        group = groups.setdefault(key, {'record': record, 'first': item, 'findings': []})
        group['findings'].append(item)
        if record and group['record']['historical'] and not record['historical']:
            group['record'], group['first'] = record, item
    for group in groups.values():
        group['proposals'] = list(dict.fromkeys(r['proposal_name'] for r in group['findings']))
        group['proposal_details'] = list({r['proposal_id']: r for r in group['findings']}.values())
        group['residentials'] = list(dict.fromkeys(r['residential_name'] for r in group['findings']))
        historical = {p['historical'] for r in group['findings'] for p in r['records']}
        group['stay_label'] = ('Vigente e histórico' if len(historical) > 1 else
                               'Histórico · solo consulta' if historical == {True} else 'Inscripción por propuesta')
    return list(groups.values())


def page(request,db,user,filters,*,navigation=None,error=None,status_code=200):
    view=service.review(db,user,**filters)
    proposals=list(db.scalars(select(Proposal).order_by(Proposal.is_active.desc(),Proposal.name)))
    decorate_findings(db,user,view['findings'],proposals)
    query=request.query_params
    navigation=navigation if navigation is not None else navigation_from(query)
    kind=navigation['kind'];state=navigation['status'];screen=navigation['view']
    detail=None;events=[];record_findings=[];session_findings=[]
    finding=query.get('finding')
    if finding:
        detail=next((r for r in view['findings'] if r['key']==finding),None)
        if detail is None:raise HTTPException(404,'Hallazgo no encontrado en el alcance autorizado.')
        if screen!='residentials' and (detail['kind']=='attendance')!=(screen=='activities'):
            screen='activities' if detail['kind']=='attendance' else 'records'
            kind='attendance' if screen=='activities' else 'all'
    allowed_kinds={'attendance'} if screen=='activities' else {'record','duplicate'}
    items=[r for r in view['findings'] if r['kind'] in allowed_kinds and (kind=='all' or kind==r['kind']) and
           (state=='all' or (r['status'] in service.OPEN if state=='open' else r['status']==state))]
    groups = group_findings(items)
    number=navigation['page']
    pages=max(1,ceil(len(groups)/25));number=min(number,pages)
    rows=groups[(number-1)*25:number*25]
    extra=dict(kind=kind,status=state,view=screen,page=number)
    def link(**changes):return url_for(filters,**{**extra,**changes})
    if detail:
        events=list(db.scalars(select(DataValidationEvent).where(DataValidationEvent.issue_key==finding)
                              .order_by(DataValidationEvent.event_id.desc()).limit(50)))
        for record in detail['records']:
            related = [r for r in view['findings'] if any(record_identity(p) == record_identity(record) for p in r['records'])]
            record_findings.append({'record': record, 'findings': related})
        if detail['kind']=='attendance':
            session_findings=[r for r in view['findings'] if r['kind']=='attendance' and r['session_id']==detail['session_id']]
    rid=service.scope_id(user)
    res_query=select(Residential).order_by(Residential.name)
    if rid is not None:res_query=res_query.where(Residential.residential_id==rid)
    return templates.TemplateResponse(request=request,name='automation/data_validation.html',context={
        'current_user':user,'view':view,'rows':rows,'total':len(items),'group_total':len(groups),'page_number':number,'pages':pages,
        'filters':filters,'kind':kind,'state':state,'screen':screen,'link':link,'base_url':service.URL,
        'detail':detail,'events':events,'record_findings':record_findings,'session_findings':session_findings,
        'labels':service.STATUS,'kinds':service.KIND,'open_statuses':service.OPEN,
        'proposals':proposals,
        'residentials':list(db.scalars(res_query)),'scope_id':rid,'months':MONTHS,'years':range(2000,2101),
        'can_write':user.role in {'admin','supervisor','user'},'can_supervise':user.role in {'admin','supervisor'},
        'csrf_token':request.session.setdefault('data_validation_token',secrets.token_urlsafe(32)),
        'today':view['today'],'default_due':view['today']+timedelta(days=4),
        'error':error,'message':RESULTS.get(query.get('result')),
    },headers=HEADERS,status_code=status_code)


@router.get('',response_class=HTMLResponse)
def index(request:Request,db:Session=Depends(get_db),user:User=Depends(require_faro_access)):
    return page(request,db,user,filters_from(request.query_params))


@router.post('/{action}',response_class=HTMLResponse)
async def update(action:str,request:Request,db:Session=Depends(get_db),user:User=Depends(require_faro_access)):
    form=await request.form()
    expected=request.session.get('data_validation_token')
    if not expected or not hmac.compare_digest(str(expected).encode(),str(form.get('csrf_token','')).encode()):
        raise HTTPException(403,'La sesión cambió. Actualiza la página antes de continuar.')
    filters=filters_from(form)
    navigation=navigation_from(form)
    try:
        due=date.fromisoformat(str(form.get('due_on',''))) if action=='assign' else None
        service.mutate(db,user,action,filters,targets=form.getlist('targets'),
            assignee=str(form.get('assignee','')),due_on=due,note=str(form.get('note','')))
        db.commit()
    except (ValueError,HTTPException) as exc:
        db.rollback()
        # Preserve authorization failures and avoid rendering data after a rejected scope.
        if isinstance(exc,HTTPException) and exc.status_code in {403,404}:raise
        return page(request,db,user,filters,navigation=navigation,error=exc.detail if isinstance(exc,HTTPException) else 'Fecha límite inválida.',
                    status_code=exc.status_code if isinstance(exc,HTTPException) else 422)
    except Exception:
        db.rollback();raise
    result={'assign':'assigned','justify':'justified','revalidate':'revalidated'}[action]
    return RedirectResponse(url_for(filters,**navigation,result=result),status_code=303,headers=HEADERS)
