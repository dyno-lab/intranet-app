"""Community alerts use Community permissions, never Faro roles or residentials."""
from dataclasses import replace
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.api.routes.community import _render
from app.core.community_access import (
    CommunityContext, require_community_context, require_community_admin, validate_csrf, csrf_token,
)
from app.models.community import CPParticipant, CPFiscalYear
from app.models.community_alerts import CPAnnouncementRead
from app.services.community_alerts import (
    ROLE_LABELS, alert_feed, create_announcement, get_announcement, managed_announcements,
    mark_read, pending_groups, withdraw_announcement, dialog_feed,
)
from app.services.community_participants import participant_query, _integer

router = APIRouter(prefix="/community/alerts", tags=["community-alerts"])
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def filtered_context(context, program_id):
    if program_id is None:
        return context
    if program_id not in context.visible_program_ids:
        raise HTTPException(403, "Programa no disponible en su selección.")
    return replace(context, selected_program_id=program_id)


@router.get("/summary")
def summary(db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_context)):
    feed = alert_feed(db, context)
    return JSONResponse({"attention_count": feed["attention_count"]}, headers=HEADERS)


@router.get("/feed")
def notification_feed(request: Request, db: Session = Depends(get_db),
                      context: CommunityContext = Depends(require_community_context)):
    data = dialog_feed(db, context)
    data['csrf_token'] = csrf_token(request)
    scope = ','.join(str(pid) for pid in sorted(context.visible_program_ids))
    data['context_key'] = f"{context.user.user_id}:{context.role}:{context.selected_program_id or 'all'}:{scope}:{data['csrf_token']}"
    return JSONResponse(data, headers=HEADERS)


@router.get("")
def alerts(request: Request, view: str = "pending", page: int = Query(1, ge=1, le=2147483647),
           db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_context)):
    if view not in {"pending", "notices"}:
        raise HTTPException(422, "Seleccione Pendientes o Avisos.")
    program_id = _integer(request.query_params, 'program_id', minimum=1, maximum=2147483647)
    fiscal_year_id = _integer(request.query_params, 'fiscal_year_id', minimum=1, maximum=2147483647)
    selected = filtered_context(context, program_id)
    feed = alert_feed(db, context)
    filtered = feed if selected == context else alert_feed(db, selected)
    years = list(db.scalars(select(CPFiscalYear).where(CPFiscalYear.is_active == True)
                           .order_by(CPFiscalYear.start_date.desc())))
    if fiscal_year_id is not None and not any(y.fiscal_year_id == fiscal_year_id for y in years):
        raise HTTPException(422, "Año fiscal no disponible.")
    items = filtered["tasks"] if view == "pending" else filtered["notices"]
    if view == "pending" and fiscal_year_id is not None:
        items = [item for item in items if item["fiscal_year_id"] == fiscal_year_id]
    total = len(items)
    pages = max(1, (total + 19) // 20)
    page = min(page, pages)
    query = {"view": view}
    if program_id is not None:
        query["program_id"] = program_id
    if fiscal_year_id is not None and view == "pending":
        query["fiscal_year_id"] = fiscal_year_id
    response = _render(request, "alerts", context, feed=feed, alert_count=feed["attention_count"],
        view=view, items=items[(page-1)*20:page*20], total=total, page=page, pages=pages,
        selected_program=program_id, selected_fiscal=fiscal_year_id, years=years,
        pagination_query=urlencode(query))
    response.headers.update(HEADERS)
    return response


@router.get("/pending")
def pending(request: Request, kind: str, program_id: int = Query(..., ge=1),
            fiscal_year_id: int | None = Query(None, ge=1), page: int = Query(1, ge=1, le=2147483647),
            db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_context)):
    if kind not in {"sync", "unassigned"} or (kind == "sync" and fiscal_year_id is None) or (kind == "unassigned" and fiscal_year_id is not None):
        raise HTTPException(422, "Pendiente inválido.")
    selected = filtered_context(context, program_id)
    group = next((group for group in pending_groups(db, selected)
                  if group["kind"] == kind and group["fiscal_year_id"] == fiscal_year_id), None)
    pages = max(1, ((group["count"] if group else 0) + 49) // 50)
    page = min(page, pages)
    ids = sorted(group["participant_ids"])[(page-1)*50:page*50] if group else []
    rows = list(db.scalars(participant_query(selected).where(CPParticipant.participant_id.in_(ids))
                           .order_by(CPParticipant.participant_id)))
    query = {"kind": kind, "program_id": program_id}
    if fiscal_year_id is not None:
        query["fiscal_year_id"] = fiscal_year_id
    response = _render(request, "alert_pending", context, group=group, rows=rows,
                       page=page, pages=pages, pagination_query=urlencode(query))
    response.headers.update(HEADERS)
    return response


@router.get("/notices/{announcement_id}")
def notice(request: Request, announcement_id: int, db: Session = Depends(get_db),
           context: CommunityContext = Depends(require_community_context)):
    announcement = get_announcement(db, context, announcement_id)
    read = db.get(CPAnnouncementRead, (announcement_id, context.user.user_id))
    response = _render(request, "alert_notice", context, announcement=announcement, read=read)
    response.headers.update(HEADERS)
    return response


@router.post("/notices/{announcement_id}/read")
def read_notice(request: Request, announcement_id: int, token: str = Form(...),
                db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_context)):
    validate_csrf(request, token)
    mark_read(db, context, announcement_id)
    if 'application/json' in request.headers.get('accept', ''):
        return JSONResponse({'read': True}, headers=HEADERS)
    return RedirectResponse(f"/community/alerts/notices/{announcement_id}?msg=Aviso+marcado+como+leído", status_code=303)


def management_page(request, db, context, *, values=None, error=None, status_code=200, page=1):
    response = _render(request, "alert_manage", context, values=values or {
        "starts_on": date.today().isoformat(), "ends_on": "", "role_scope": "all",
        "program_scope": "all", "roles": [], "program_ids": []}, error=error,
        role_labels=ROLE_LABELS, **managed_announcements(db, page=page))
    response.status_code = status_code
    response.headers.update(HEADERS)
    return response


@router.get("/manage")
def manage(request: Request, page: int = Query(1, ge=1, le=2147483647),
           db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    return management_page(request, db, context, page=page)


@router.post("/manage")
def publish(request: Request, token: str = Form(...), title: str = Form(""), message: str = Form(""),
            starts_on: str = Form(""), ends_on: str = Form(""), role_scope: str = Form("all"),
            program_scope: str = Form("all"), roles: list[str] = Form(default=[]),
            program_ids: list[str] = Form(default=[]), db: Session = Depends(get_db),
            context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    values = {"title": title, "message": message, "starts_on": starts_on, "ends_on": ends_on,
              "role_scope": role_scope, "program_scope": program_scope, "roles": roles, "program_ids": program_ids}
    try:
        create_announcement(db, context, values)
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        return management_page(request, db, context, values=values, error=exc.detail, status_code=422)
    return RedirectResponse("/community/alerts/manage?msg=Aviso+publicado", status_code=303)


@router.post("/manage/{announcement_id}/withdraw")
def withdraw(request: Request, announcement_id: int, token: str = Form(...),
             db: Session = Depends(get_db), context: CommunityContext = Depends(require_community_admin)):
    validate_csrf(request, token)
    withdraw_announcement(db, context, announcement_id)
    return RedirectResponse("/community/alerts/manage?msg=Aviso+retirado", status_code=303)
