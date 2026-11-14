"""FaroGPT's authenticated consultation API; no program data writes."""
import hmac
import secrets
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.residential_scope import require_faro_access
from app.models.user import User
from app.services import farogpt as service
from app.services.participant_courses import MONTHS

router = APIRouter(prefix=service.URL)
templates = Jinja2Templates(directory='app/templates')
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}


def supervision(user: User = Depends(require_faro_access)):
    service.require_supervision(user)
    return user


class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question: str = Field(min_length=1, max_length=800)
    context: service.QueryContext = Field(default_factory=service.QueryContext)


@router.get('/inicio')
def bootstrap(request: Request, db: Session = Depends(get_db), user: User = Depends(supervision)):
    residentials, _ = service.catalogs(db, user)
    previous = date.today().replace(day=1) - timedelta(days=1)
    period = f'{dict(MONTHS)[previous.month].lower()} de {previous.year}'
    residential = next((r.name for r in residentials if 'chavier' in r.name.lower()),
                       residentials[0].name if residentials else None)
    scope = f'en {residential}' if residential else 'en todos los residenciales'
    return JSONResponse({
        'csrf_token': request.session.setdefault('farogpt_csrf', secrets.token_urlsafe(32)),
        'message': 'Hola, ¿qué te gustaría consultar?',
        'help': service.HELP,
        'suggestions': [f'¿Cuántos no duplicados hubo {scope} en {period}?',
                        f'¿Cuántas actividades hubo en {period}?',
                        f'¿Cuántas participaciones hubo en {period}?'],
    }, headers=HEADERS)


@router.post('/consulta')
def query(payload: Question, request: Request, db: Session = Depends(get_db), user: User = Depends(supervision)):
    expected = request.session.get('farogpt_csrf')
    actual = request.headers.get('x-farogpt-csrf', '')
    if not expected or not hmac.compare_digest(str(expected).encode(), actual.encode()):
        raise HTTPException(403, 'La sesión cambió. Actualiza la página para continuar.')
    result = service.answer(db, user, payload.question, payload.context.model_dump())
    return JSONResponse(result, headers=HEADERS)


@router.get('/informe')
def report(request: Request, filters: service.QueryContext = Depends(),
           db: Session = Depends(get_db), user: User = Depends(supervision)):
    result = service.summary(db, user, filters.model_dump())
    return templates.TemplateResponse(request=request, name='ui/farogpt_report.html', context={
        'current_user': user, 'result': result, 'titles': service.TITLES,
        'definitions': service.DEFINITIONS, 'consulted_on': date.today(),
    }, headers=HEADERS)
