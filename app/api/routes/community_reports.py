from calendar import monthrange
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.core.community_access import CommunityContext, require_community_context, require_programs, csrf_token
from app.models.community import CPFiscalYear
from app.services.community_reports import REPORT_TYPES, build_report, excel_bytes, pdf_bytes

router = APIRouter(prefix="/community/reports", tags=["community-reports"])
templates = Jinja2Templates(directory="app/templates")


@router.get("")
def reports(request: Request, fiscal_year_id: int | None = None, program_ids: list[int] = Query(default=[]),
            report_type: str = "no-duplicados", output: str = "screen", period_type: str = "fiscal",
            month: int | None = None, year: int | None = None,
            start_date: date | None = None, end_date: date | None = None,
            db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_context)):
    result = None
    error = None
    if output not in {"screen", "excel", "pdf"}:
        raise HTTPException(422, "Formato inválido.")
    if fiscal_year_id is not None:
        require_programs(context, program_ids)
        fiscal = db.get(CPFiscalYear, fiscal_year_id)
        if fiscal is None:
            raise HTTPException(404, "Año fiscal no encontrado.")
        try:
            if period_type == "fiscal":
                start_date, end_date = fiscal.start_date, fiscal.end_date
            elif period_type == "monthly":
                if not month or not year:
                    raise ValueError("Seleccione mes y año calendario.")
                start_date = max(fiscal.start_date, date(year, month, 1))
                end_date = min(fiscal.end_date, date(year, month, monthrange(year, month)[1]))
            elif period_type != "custom" or start_date is None or end_date is None:
                raise ValueError("Seleccione un período válido.")
            result = build_report(db, report_type=report_type, fiscal_year_id=fiscal_year_id,
                                  program_ids=set(program_ids), start_date=start_date, end_date=end_date)
        except ValueError as exc:
            if output != "screen":
                raise HTTPException(422, str(exc))
            error = str(exc)
        if result and output != "screen":
            payload = excel_bytes(result) if output == "excel" else pdf_bytes(result)
            extension, media = ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") if output == "excel" else ("pdf", "application/pdf")
            return Response(payload, media_type=media, headers={"Content-Disposition": f'attachment; filename="comunidad-{report_type}-{fiscal_year_id}.{extension}"'})
    elif output != "screen":
        raise HTTPException(422, "Seleccione un año fiscal y programas antes de descargar.")
    return templates.TemplateResponse(request=request, name="community/reports.html", context={
        "request": request, "cp": context, "current_user": context.user, "csrf_token": csrf_token(request),
        "error": error, "result": result, "types": REPORT_TYPES,
        "years": db.scalars(select(CPFiscalYear).order_by(CPFiscalYear.start_date.desc())).all(),
        "selected_fiscal": fiscal_year_id, "selected_programs": program_ids, "report_type": report_type,
        "period_type": period_type, "month": month, "year": year or date.today().year,
        "start_date": start_date, "end_date": end_date,
    })
