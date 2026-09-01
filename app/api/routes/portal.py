from datetime import date
from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.google_oauth import google_oauth_is_available
from app.core.platform_permissions import (
    ACCESS_AUTOMATION,
    ACCESS_FARO,
    ACCESS_INSTITUTIONAL_REPORTS,
    ACCESS_NEW_PROGRAMS,
    ACCESS_PORTAL_HOME,
    MANAGE_PLATFORM_SETTINGS,
    get_optional_current_user,
    user_permission_keys,
)
from app.core.roles import is_viewer


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
_UI_MODERN_CSS_VERSION = sha256(
    Path("app/static/css/ui-modern.css").read_bytes()
).hexdigest()[:12]


@router.get("/home", response_class=HTMLResponse)
def portal_home(request: Request, db: Session = Depends(get_db)):
    current_user = get_optional_current_user(request, db)
    if current_user is None:
        return templates.TemplateResponse(
            request=request,
            name="portal/home.html",
            context={
                "request": request,
                "current_year": date.today().year,
                "ui_modern_css_version": _UI_MODERN_CSS_VERSION,
                "current_user": None,
                "google_oauth_available": google_oauth_is_available(),
                "can_manage_platform_settings": False,
                "can_access_faro": False,
                "can_access_institutional_reports": False,
                "can_access_automation": False,
                "can_access_new_programs": False,
            },
        )

    permission_keys = user_permission_keys(db, current_user)
    can_manage_platform_settings = (
        not is_viewer(current_user)
        and MANAGE_PLATFORM_SETTINGS in permission_keys
    )
    if ACCESS_PORTAL_HOME not in permission_keys:
        return templates.TemplateResponse(
            request=request,
            name="portal/access_denied.html",
            context={
                "request": request,
                "current_user": current_user,
                "can_manage_platform_settings": can_manage_platform_settings,
            },
            status_code=status.HTTP_403_FORBIDDEN,
        )

    return templates.TemplateResponse(
        request=request,
        name="portal/home.html",
        context={
            "request": request,
            "current_year": date.today().year,
            "ui_modern_css_version": _UI_MODERN_CSS_VERSION,
            "current_user": current_user,
            "google_oauth_available": google_oauth_is_available(),
            "can_manage_platform_settings": can_manage_platform_settings,
            "can_access_faro": ACCESS_FARO in permission_keys,
            "can_access_institutional_reports": ACCESS_INSTITUTIONAL_REPORTS in permission_keys,
            "can_access_automation": ACCESS_AUTOMATION in permission_keys,
            "can_access_new_programs": ACCESS_NEW_PROGRAMS in permission_keys,
        },
    )
