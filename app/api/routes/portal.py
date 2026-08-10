from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.platform_permissions import (
    MANAGE_PLATFORM_SETTINGS,
    get_optional_current_user,
    user_has_platform_permission,
)


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/home", response_class=HTMLResponse)
def portal_home(request: Request, db: Session = Depends(get_db)):
    current_user = get_optional_current_user(request, db)
    can_manage_platform_settings = bool(
        current_user
        and user_has_platform_permission(db, current_user, MANAGE_PLATFORM_SETTINGS)
    )
    return templates.TemplateResponse(
        request=request,
        name="portal/home.html",
        context={
            "request": request,
            "current_year": date.today().year,
            "current_user": current_user,
            "can_manage_platform_settings": can_manage_platform_settings,
        },
    )
