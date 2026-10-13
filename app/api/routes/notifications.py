import hmac
import secrets
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.residential_scope import require_faro_access
from app.models.notification import FaroAnnouncement
from app.models.residential import Residential
from app.models.user import User
from app.services.notifications import (
    ANNOUNCEMENT_ROLES, admin_announcements, create_announcement,
    mark_announcement_read, notification_feed, residential_scope,
)

router = APIRouter(prefix="/ui")
templates = Jinja2Templates(directory="app/templates")
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


def token(request):
    return request.session.setdefault("notification_token", secrets.token_urlsafe(32))


def check_token(request, supplied):
    expected = request.session.get("notification_token", "")
    if not expected or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(403, "Vuelve a abrir las notificaciones antes de continuar.")


def admin(user: User = Depends(require_faro_access)):
    if user.role != "admin":
        raise HTTPException(403, "Solo el administrador puede gestionar anuncios.")
    return user


@router.get("/notifications")
def feed(request: Request, db: Session = Depends(get_db), user: User = Depends(require_faro_access)):
    data = notification_feed(db, user)
    data["csrf_token"] = token(request)
    data["context_key"] = f"{user.user_id}:{residential_scope(user) or 'global'}:{data['csrf_token']}"
    return JSONResponse(data, headers=HEADERS)


@router.post("/notifications/read")
def read(request: Request, announcement_id: int = Form(...), db: Session = Depends(get_db),
         user: User = Depends(require_faro_access)):
    check_token(request, request.headers.get("X-CSRF-Token", ""))
    mark_announcement_read(db, user, announcement_id)
    return JSONResponse({"read": True}, headers=HEADERS)


def admin_page(request, db, user, *, error=None, values=None, status_code=200):
    return templates.TemplateResponse(request=request, name="ui/admin/notifications.html", context={
        "current_user": user, "notification_token": token(request), "error": error,
        "values": values or {"starts_on": date.today().isoformat(), "role_scope": "all", "residential_scope": "all"},
        "roles": ANNOUNCEMENT_ROLES, "today": date.today(), "announcements": admin_announcements(db),
        "residentials": db.scalars(select(Residential).where(Residential.is_active == True).order_by(Residential.name)).all(),  # noqa: E712
        "msg": {"published": "Anuncio publicado. Se mostrará a sus destinatarios durante la vigencia indicada.",
                "deactivated": "Anuncio retirado."}.get(request.query_params.get("result")),
    }, status_code=status_code, headers=HEADERS)


@router.get("/admin/notifications", response_class=HTMLResponse)
def manage(request: Request, db: Session = Depends(get_db), user: User = Depends(admin)):
    return admin_page(request, db, user)


@router.post("/admin/notifications", response_class=HTMLResponse)
def publish(request: Request, title: str = Form(""), message: str = Form(""), starts_on: str = Form(""),
            ends_on: str = Form(""), role_scope: str = Form(""), residential_scope: str = Form(""),
            roles: list[str] = Form([]), residential_ids: list[str] = Form([]), csrf_token: str = Form(""),
            db: Session = Depends(get_db), user: User = Depends(admin)):
    check_token(request, csrf_token)
    values = dict(title=title, message=message, starts_on=starts_on, ends_on=ends_on, role_scope=role_scope,
                  residential_scope=residential_scope, roles=roles, residential_ids=residential_ids)
    try:
        create_announcement(db, user, values)
    except HTTPException as exc:
        if exc.status_code != 422:
            raise
        return admin_page(request, db, user, error=exc.detail, values=values, status_code=422)
    return RedirectResponse("/ui/admin/notifications?result=published", status_code=303, headers=HEADERS)


@router.post("/admin/notifications/{announcement_id}/deactivate")
def deactivate(request: Request, announcement_id: int, csrf_token: str = Form(""),
               db: Session = Depends(get_db), user: User = Depends(admin)):
    check_token(request, csrf_token)
    announcement = db.get(FaroAnnouncement, announcement_id)
    if announcement is None:
        raise HTTPException(404, "Anuncio no encontrado.")
    announcement.is_active = False
    db.commit()
    return RedirectResponse("/ui/admin/notifications?result=deactivated", status_code=303, headers=HEADERS)
