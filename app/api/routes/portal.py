from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/home", response_class=HTMLResponse)
def portal_home(request: Request):
    return templates.TemplateResponse(
        "portal/home.html",
        {
            "request": request,
            "current_year": date.today().year,
        },
    )
