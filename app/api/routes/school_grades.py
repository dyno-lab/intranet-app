from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.proposal import Proposal
from app.models.school_grade_report import SchoolGradeReport
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
def school_grade_reports_index(
    request: Request,
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(SchoolGradeReport, Proposal.code.label("proposal_code"), Proposal.name.label("proposal_name"))
        .join(Proposal, SchoolGradeReport.proposal_id == Proposal.proposal_id)
        .order_by(SchoolGradeReport.report_year.desc(), SchoolGradeReport.report_month.desc(), SchoolGradeReport.report_id.desc())
    )

    if proposal_id:
        stmt = stmt.where(SchoolGradeReport.proposal_id == proposal_id)
    if month:
        stmt = stmt.where(SchoolGradeReport.report_month == month)
    if year:
        stmt = stmt.where(SchoolGradeReport.report_year == year)

    reports = db.execute(stmt).all()
    proposals = db.execute(select(Proposal).where(Proposal.is_active == True).order_by(Proposal.code)).scalars().all()  # noqa: E712

    month_options = [
        (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
        (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
        (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
    ]
    current_year = date.today().year
    year_options = list(range(current_year - 2, current_year + 3))

    return templates.TemplateResponse(
        "ui/school_grades/index.html",
        {
            "request": request,
            "current_user": current_user,
            "reports": reports,
            "proposals": proposals,
            "month_options": month_options,
            "year_options": year_options,
            "selected_proposal_id": proposal_id,
            "selected_month": month,
            "selected_year": year,
            "msg": msg,
        },
    )


@router.post("/create")
def create_school_grade_report(
    proposal_id: int = Form(...),
    report_month: int = Form(...),
    report_year: int = Form(...),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.execute(
        select(SchoolGradeReport).where(
            SchoolGradeReport.proposal_id == proposal_id,
            SchoolGradeReport.report_month == report_month,
            SchoolGradeReport.report_year == report_year,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            f"/ui/school-grades?proposal_id={proposal_id}&month={report_month}&year={report_year}&msg=Error: Ya existe un informe para esa propuesta, mes y año.",
            status_code=303,
        )

    report = SchoolGradeReport(
        proposal_id=proposal_id,
        report_month=report_month,
        report_year=report_year,
        notes=(notes or "").strip() or None,
        created_by_user_id=current_user.user_id,
    )
    db.add(report)
    db.commit()

    return RedirectResponse(
        "/ui/school-grades?msg=Informe de notas creado exitosamente.",
        status_code=303,
    )
