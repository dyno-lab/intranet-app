from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.school_grade_report import SchoolGradeReport
from app.models.school_grade_report_item import SchoolGradeReportItem
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


GRADE_OPTIONS = ["EE", "K", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]


def _calc_age(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


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
        f"/ui/school-grades/{report.report_id}?msg=Informe de notas creado exitosamente.",
        status_code=303,
    )


@router.get("/{report_id}", response_class=HTMLResponse)
def school_grade_report_detail(
    report_id: int,
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolGradeReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Informe no encontrado.")

    proposal = db.get(Proposal, report.proposal_id)

    participants = db.execute(
        select(Participant)
        .where(Participant.is_active == True)  # noqa: E712
        .order_by(Participant.apellido_paterno, Participant.nombre)
    ).scalars().all()

    eligible_rows = []
    for participant in participants:
        age = _calc_age(participant.fecha_nacimiento)
        if age is None or age < 0 or age > 21:
            continue
        eligible_rows.append({"p": participant, "age": age})

    report_items = db.execute(
        select(SchoolGradeReportItem, Participant)
        .join(Participant, SchoolGradeReportItem.participant_id == Participant.participant_id)
        .where(SchoolGradeReportItem.report_id == report_id)
        .order_by(Participant.apellido_paterno, Participant.nombre)
    ).all()

    existing_participant_ids = {row[0].participant_id for row in report_items}

    return templates.TemplateResponse(
        "ui/school_grades/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "report": report,
            "proposal": proposal,
            "eligible_rows": eligible_rows,
            "report_items": report_items,
            "existing_participant_ids": existing_participant_ids,
            "grade_options": GRADE_OPTIONS,
            "msg": msg,
        },
    )


@router.post("/{report_id}/participants/add")
def add_participant_to_school_grade_report(
    report_id: int,
    participant_id: int = Form(...),
    grade_level: str | None = Form(default=None),
    is_content_room: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolGradeReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Informe no encontrado.")

    participant = db.get(Participant, participant_id)
    if not participant:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: Participante no encontrado.", status_code=303)

    age = _calc_age(participant.fecha_nacimiento)
    if age is None or age < 0 or age > 21:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: El participante no está dentro del rango 0-21 años.", status_code=303)

    if not participant.is_active:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: El participante está inactivo.", status_code=303)

    existing = db.execute(
        select(SchoolGradeReportItem).where(
            SchoolGradeReportItem.report_id == report_id,
            SchoolGradeReportItem.participant_id == participant_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: El participante ya fue añadido al informe.", status_code=303)

    item = SchoolGradeReportItem(
        report_id=report_id,
        participant_id=participant_id,
        grade_level=(grade_level or "").strip() or None,
        is_content_room=is_content_room == "on",
    )
    db.add(item)
    db.commit()

    return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Participante añadido al informe.", status_code=303)
