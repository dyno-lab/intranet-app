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


def page(request,db,user,filters,*,error=None,status_code=200):
    view=service.review(db,user,**filters)
    query=request.query_params
    kind=query.get('kind','all') or 'all'; state=query.get('status','open') or 'open'
    if kind not in {'all',*service.KIND} or state not in {'all','open',*service.STATUS}:
        raise HTTPException(422,'Tipo o estado de hallazgo inválido.')
    screen=query.get('view','findings')
    if screen not in {'findings','residentials'}:screen='findings'
    items=[r for r in view['findings'] if (kind=='all' or kind==r['kind']) and
           (state=='all' or (r['status'] in service.OPEN if state=='open' else r['status']==state))]
    try: number=max(1,int(query.get('page','1') or 1))
    except ValueError as exc:raise HTTPException(422,'Página inválida.') from exc
    pages=max(1,ceil(len(items)/25));number=min(number,pages)
    rows=items[(number-1)*25:number*25]
    extra=dict(kind=kind,status=state,view=screen,page=number)
    def link(**changes):return url_for(filters,**{**extra,**changes})
    detail=None;events=[]
    finding=query.get('finding')
    if finding:
        detail=next((r for r in view['findings'] if r['key']==finding),None)
        if detail is None:raise HTTPException(404,'Hallazgo no encontrado en el alcance autorizado.')
        events=list(db.scalars(select(DataValidationEvent).where(DataValidationEvent.issue_key==finding)
                              .order_by(DataValidationEvent.event_id.desc()).limit(50)))
    rid=service.scope_id(user)
    res_query=select(Residential).order_by(Residential.name)
    if rid is not None:res_query=res_query.where(Residential.residential_id==rid)
    return templates.TemplateResponse(request=request,name='automation/data_validation.html',context={
        'current_user':user,'view':view,'rows':rows,'total':len(items),'page_number':number,'pages':pages,
        'filters':filters,'kind':kind,'state':state,'screen':screen,'link':link,'base_url':service.URL,
        'detail':detail,'events':events,'labels':service.STATUS,'kinds':service.KIND,'open_statuses':service.OPEN,
        'proposals':list(db.scalars(select(Proposal).order_by(Proposal.is_active.desc(),Proposal.name))),
        'residentials':list(db.scalars(res_query)),'scope_id':rid,'months':MONTHS,
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
    try:
        due=date.fromisoformat(str(form.get('due_on',''))) if action=='assign' else None
        service.mutate(db,user,action,filters,targets=form.getlist('targets'),
            assignee=str(form.get('assignee','')),due_on=due,note=str(form.get('note','')))
        db.commit()
    except (ValueError,HTTPException) as exc:
        db.rollback()
        # Preserve authorization failures and avoid rendering data after a rejected scope.
        if isinstance(exc,HTTPException) and exc.status_code in {403,404}:raise
        return page(request,db,user,filters,error=exc.detail if isinstance(exc,HTTPException) else 'Fecha límite inválida.',
                    status_code=exc.status_code if isinstance(exc,HTTPException) else 422)
    except Exception:
        db.rollback();raise
    result={'assign':'assigned','justify':'justified','revalidate':'revalidated'}[action]
    return RedirectResponse(url_for(filters,result=result),status_code=303,headers=HEADERS)
