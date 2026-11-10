"""Faro attendance handoff, with server-authorized scope and CSRF protection."""
import hmac
import secrets
from datetime import date, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.residential_scope import require_faro_access
from app.helpers.query_filters import OptionalQueryInt
from app.models.monthly_attendance import AttendanceMonthEvent, AttendanceMonthResidential
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.user import User
from app.services import monthly_attendance as service
from app.services.participant_courses import MONTHS

router = APIRouter(prefix="/ui/monthly-attendance")
templates = Jinja2Templates(directory="app/templates")
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
RESULTS = {"confirmed": "Mes confirmado. Administración y supervisión pueden consultar tu confirmación.",
           "reminded": "Recordatorio publicado en las notificaciones de los residenciales pendientes.",
           "configured": "Configuración del período guardada."}


def local_stamp(value):
    if not value:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone(timedelta(hours=-4))).strftime("%d/%m/%Y %I:%M %p")


templates.env.filters["monthly_stamp"] = local_stamp


def page(request, db, user, proposal_id=None, year=None, month=None, *, error=None, status_code=200, before_event=None):
    today = date.today()
    previous_year, previous_month = service.previous_month(today)
    year = previous_year if year is None else year
    month = previous_month if month is None else month
    proposals = list(db.scalars(select(Proposal).order_by(Proposal.is_active.desc(), Proposal.code.desc())))
    proposal_id = proposal_id if proposal_id is not None else (proposals[0].proposal_id if proposals else None)
    view = service.build_month(db, user, proposal_id, year, month, today=today) if proposal_id else None
    rid = service.scope_id(user)
    events, residentials, included = [], [], set()
    if view:
        query = select(AttendanceMonthEvent).where(AttendanceMonthEvent.proposal_id == proposal_id,
            AttendanceMonthEvent.report_year == year, AttendanceMonthEvent.report_month == month)
        if rid is not None:
            query = query.where(AttendanceMonthEvent.residential_id == rid)
        if before_event:
            query = query.where(AttendanceMonthEvent.event_id < before_event)
        events = list(db.scalars(query.order_by(AttendanceMonthEvent.event_id.desc()).limit(51)))
        included = {r["residential"].residential_id for r in view["rows"]}
        if view["can_configure"]:
            saved = select(AttendanceMonthResidential.residential_id).where(
                AttendanceMonthResidential.proposal_id == proposal_id,
                AttendanceMonthResidential.report_year == year, AttendanceMonthResidential.report_month == month)
            residentials = list(db.scalars(select(Residential).where(or_(Residential.is_active == True,
                Residential.residential_id.in_(saved))).order_by(Residential.code)))
    return templates.TemplateResponse(request=request, name="ui/monthly_attendance.html", context={
        "current_user": user, "view": view, "proposals": proposals, "months": MONTHS,
        "selected_year": year, "selected_month": month, "selected_proposal_id": proposal_id,
        "csrf_token": request.session.setdefault("monthly_attendance_token", secrets.token_urlsafe(32)),
        "events": events[:50], "older_events": events[49].event_id if len(events) > 50 else None,
        "event_names": dict(db.execute(select(Residential.residential_id, Residential.name).where(
            Residential.residential_id.in_({e.residential_id for e in events if e.residential_id}))).all()) if events else {},
        "residentials": residentials, "included": included, "error": error,
        "msg": RESULTS.get(request.query_params.get("result")),
    }, status_code=status_code, headers=HEADERS)


@router.get("", response_class=HTMLResponse)
def index(request: Request, proposal_id: OptionalQueryInt = None, year: OptionalQueryInt = None,
          month: OptionalQueryInt = None, before_event: OptionalQueryInt = None,
          db: Session = Depends(get_db), user: User = Depends(require_faro_access)):
    return page(request, db, user, proposal_id, year, month, before_event=before_event)


@router.post("/{action}", response_class=HTMLResponse)
async def update(action: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_faro_access)):
    if action not in {"confirm", "remind", "configure"}:
        raise HTTPException(404, "Acción no encontrada.")
    form = await request.form()
    expected = request.session.get("monthly_attendance_token")
    if not expected or not hmac.compare_digest(expected.encode(), str(form.get("csrf_token", "")).encode()):
        raise HTTPException(403, "La sesión cambió. Actualiza la página antes de continuar.")
    try:
        proposal_id, year, month = (int(form.get(name, "")) for name in ("proposal_id", "year", "month"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Selecciona una propuesta y un período válidos.") from exc
    # Validate the route period before rendering errors or parsing dates.
    service.build_month(db, user, proposal_id, year, month)
    values = dict(proposal_id=proposal_id, year=year, month=month)
    try:
        if action == "confirm":
            service.confirm_month(db, user, **values, fingerprint=str(form.get("fingerprint", "")),
                declared=form.get("declared") == "on", no_activity=form.get("no_activity") == "on",
                note=str(form.get("note", "")))
            result = "confirmed"
        elif action == "remind":
            ids = [int(rid) for rid in form.getlist("residential_ids")] or None
            service.remind_month(db, user, **values, residential_ids=ids, message=str(form.get("message", "")))
            result = "reminded"
        else:
            service.configure_month(db, user, **values, due_on=date.fromisoformat(str(form.get("due_on", ""))),
                residential_ids=[int(rid) for rid in form.getlist("residential_ids")],
                revision=int(form.get("revision", "")), reason=str(form.get("reason", "")))
            result = "configured"
        db.commit()
    except (ValueError, HTTPException) as exc:
        db.rollback()
        return page(request, db, user, proposal_id, year, month,
            error=exc.detail if isinstance(exc, HTTPException) else "Revisa la fecha y los residenciales seleccionados.",
            status_code=exc.status_code if isinstance(exc, HTTPException) else 422)
    except Exception:
        db.rollback()
        raise
    return RedirectResponse(service.month_url(proposal_id, year, month) + "&result=" + result, status_code=303, headers=HEADERS)
