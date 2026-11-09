"""The certification has the same Faro/read scope as Bonafide, on every output."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.helpers.query_filters import OptionalQueryInt
from app.helpers.report_proposals import report_proposal_selection
from app.models.user import User
from app.services.certification_report import build_certification_report, require_exportable
from app.services.certification_exports import certification_pdf, certification_excel

router = APIRouter()
templates = Jinja2Templates(directory='app/templates')
HEADERS = {'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff'}


def certification_context(request: Request, employee_id: OptionalQueryInt = None,
                          db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = request.query_params
    return build_certification_report(db, user, selected_proposals=report_proposal_selection(request),
        month=query.get('month'), year=query.get('year'), employee_id=employee_id,
        period_type=query.get('period_type', 'monthly'), start_date=query.get('start_date'),
        end_date=query.get('end_date'), authorized_name=query.get('authorized_name'))


@router.get('/certificacion', response_class=HTMLResponse)
def certification_screen(request: Request, data=Depends(certification_context), user=Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name='ui/reports/certificacion.html',
                                      context={**data, 'request':request, 'current_user':user}, headers=HEADERS)


def _export(data, kind, disposition):
    require_exportable(data)
    payload = certification_pdf(data) if kind == 'pdf' else certification_excel(data)
    media = 'application/pdf' if kind == 'pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    suffix = f"{data['selected_year']}_{data['selected_month']}" if data['selected_period_type'] == 'monthly' else f"{data['selected_start_date']}_a_{data['selected_end_date']}"
    return Response(payload, media_type=media, headers={**HEADERS,
        'Content-Disposition': f'{disposition}; filename="certificacion_{suffix}.{kind}"'})


@router.get('/certificacion/pdf')
def certification_print(data=Depends(certification_context)):
    return _export(data, 'pdf', 'inline')


@router.get('/certificacion/pdf/download')
def certification_download(data=Depends(certification_context)):
    return _export(data, 'pdf', 'attachment')


@router.get('/certificacion/excel')
def certification_spreadsheet(data=Depends(certification_context)):
    return _export(data, 'xlsx', 'attachment')
