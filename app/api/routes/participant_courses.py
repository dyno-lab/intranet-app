import hmac
import json
import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.user import User
from app.services.participant_courses import build_course_report, save_course_assignments
from app.services.participant_courses_exports import course_report_excel, course_report_pdf

router = APIRouter()
templates = Jinja2Templates(directory='app/templates')
HEADERS = {'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'}


def filters_from_query(request):
    values = request.query_params
    try:
        scope = int(values['employee_id']) if values.get('employee_id') not in (None, '', 'None') else None
    except ValueError as exc:
        raise HTTPException(422, 'Residencial inválido.') from exc
    return dict(proposal_ids=values.getlist('proposal_id'), month=values.get('month'), year=values.get('year'),
                employee_id=scope, period_type=values.get('period_type', 'monthly'),
                start_date=values.get('start_date'), end_date=values.get('end_date'))


def _query(data):
    return urlencode([('proposal_id', pid) for pid in data['selected_proposal_ids']] + [
        ('employee_id', data['selected_employee_id']), ('month', data['selected_month']),
        ('year', data['selected_year']), ('period_type', data['selected_period_type']),
        ('start_date', data['selected_start_date']), ('end_date', data['selected_end_date'])])


@router.get('/cursos', response_class=HTMLResponse)
def courses_screen(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    data = build_course_report(db, user, **filters_from_query(request))
    token = request.session.setdefault('course_report_token', secrets.token_urlsafe(32))
    return templates.TemplateResponse(request=request, name='ui/reports/cursos.html', context={
        **data, 'request': request, 'current_user': user, 'course_token': token, 'report_query': _query(data),
    }, headers=HEADERS)


@router.post('/cursos/save')
async def courses_save(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.role not in {'admin', 'user'}:
        raise HTTPException(403, 'No tienes permiso para guardar cursos.')
    token, expected = request.headers.get('X-CSRF-Token', ''), request.session.get('course_report_token', '')
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        raise HTTPException(403, 'Vuelve a abrir el reporte antes de guardar.')
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 1024 * 1024:
            raise HTTPException(413, 'El envío supera el tamaño permitido.')
    try:
        changes = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, 'Selecciones inválidas.') from exc
    result = await run_in_threadpool(save_course_assignments, db, user, filters_from_query(request), changes)
    return Response(json.dumps({'saved': result}), media_type='application/json', headers=HEADERS)


def _export(request, db, user, kind, disposition):
    data = build_course_report(db, user, **filters_from_query(request))
    payload = course_report_pdf(data) if kind == 'pdf' else course_report_excel(data)
    media = 'application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    suffix = f"{data['selected_start_date']}_a_{data['selected_end_date']}"
    return Response(payload, media_type=media, headers={**HEADERS,
        'Content-Disposition': f'{disposition}; filename="cursos_2_b_5_{suffix}.{kind}"'})


@router.get('/cursos/pdf')
def courses_print(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _export(request, db, user, 'pdf', 'inline')


@router.get('/cursos/pdf/download')
def courses_pdf(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _export(request, db, user, 'pdf', 'attachment')


@router.get('/cursos/excel')
def courses_excel(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _export(request, db, user, 'xlsx', 'attachment')
