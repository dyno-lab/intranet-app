from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_db
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


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/home", response_class=HTMLResponse)
def portal_home(request: Request, db: Session = Depends(get_db)):
    current_user = get_optional_current_user(request, db)
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
        )

    permission_keys = user_permission_keys(db, current_user)
    can_manage_platform_settings = MANAGE_PLATFORM_SETTINGS in permission_keys
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
            "current_user": current_user,
            "can_manage_platform_settings": can_manage_platform_settings,
            "can_access_faro": ACCESS_FARO in permission_keys,
            "can_access_institutional_reports": ACCESS_INSTITUTIONAL_REPORTS in permission_keys,
            "can_access_automation": ACCESS_AUTOMATION in permission_keys,
            "can_access_new_programs": ACCESS_NEW_PROGRAMS in permission_keys,
        },
    )
