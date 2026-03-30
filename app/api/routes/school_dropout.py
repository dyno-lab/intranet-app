from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.school_dropout_report import SchoolDropoutReport
from app.models.school_dropout_report_item import SchoolDropoutReportItem
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
def school_dropout_reports_index(
    request: Request,
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = (
        select(
            SchoolDropoutReport,
            Proposal.code.label("proposal_code"),
            Proposal.name.label("proposal_name"),
            User.username.label("created_by_username"),
            Residential.name.label("created_by_residential"),
        )
        .join(Proposal, SchoolDropoutReport.proposal_id == Proposal.proposal_id)
        .join(User, SchoolDropoutReport.created_by_user_id == User.user_id)
        .outerjoin(Residential, User.residential_id == Residential.residential_id)
        .order_by(SchoolDropoutReport.report_year.desc(), SchoolDropoutReport.report_month.desc(), SchoolDropoutReport.report_id.desc())
    )

    if current_user.role != "admin":
        stmt = stmt.where(SchoolDropoutReport.created_by_user_id == current_user.user_id)
    if proposal_id:
        stmt = stmt.where(SchoolDropoutReport.proposal_id == proposal_id)
    if month:
        stmt = stmt.where(SchoolDropoutReport.report_month == month)
    if year:
        stmt = stmt.where(SchoolDropoutReport.report_year == year)

    reports = db.execute(stmt).all()
    proposals = db.execute(select(Proposal).where(Proposal.is_active == True).order_by(Proposal.code)).scalars().all()  # noqa: E712

    month_options = [
        (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
        (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
        (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
    ]
    current_year = date.today().year
    year_options = list(range(current_year - 2, current_year + 3))
    month_lookup = dict(month_options)

    return templates.TemplateResponse(
        "ui/school_dropout/index.html",
        {
            "request": request,
            "current_user": current_user,
            "reports": reports,
            "proposals": proposals,
            "month_options": month_options,
            "month_lookup": month_lookup,
            "year_options": year_options,
            "selected_proposal_id": proposal_id,
            "selected_month": month,
            "selected_year": year,
            "msg": msg,
        },
    )


@router.post("/create")
def create_school_dropout_report(
    proposal_id: int = Form(...),
    report_month: int = Form(...),
    report_year: int = Form(...),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.execute(
        select(SchoolDropoutReport).where(
            SchoolDropoutReport.proposal_id == proposal_id,
            SchoolDropoutReport.report_month == report_month,
            SchoolDropoutReport.report_year == report_year,
            SchoolDropoutReport.created_by_user_id == current_user.user_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            f"/ui/school-dropout?proposal_id={proposal_id}&month={report_month}&year={report_year}&msg=Error: Ya existe un informe para esa propuesta, mes y año.",
            status_code=303,
        )

    report = SchoolDropoutReport(
        proposal_id=proposal_id,
        report_month=report_month,
        report_year=report_year,
        notes=(notes or "").strip() or None,
        created_by_user_id=current_user.user_id,
    )
    db.add(report)
    db.commit()

    return RedirectResponse(
        f"/ui/school-dropout/{report.report_id}?msg=Informe de deserción escolar creado exitosamente.",
        status_code=303,
    )


@router.get("/{report_id}", response_class=HTMLResponse)
def school_dropout_report_detail(
    report_id: int,
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolDropoutReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este informe.")

    proposal = db.get(Proposal, report.proposal_id)

    participant_stmt = (
        select(Participant)
        .where(Participant.is_active == True)  # noqa: E712
        .order_by(Participant.apellido_paterno, Participant.nombre)
    )
    if current_user.role != "admin":
        participant_stmt = participant_stmt.where(Participant.created_by_user_id == report.created_by_user_id)

    participants = db.execute(participant_stmt).scalars().all()

    eligible_rows = []
    age_map = {}
    for participant in participants:
        age = _calc_age(participant.fecha_nacimiento)
        if age is None or age < 0 or age > 21:
            continue
        eligible_rows.append({"p": participant, "age": age})
        age_map[participant.participant_id] = age

    report_items = db.execute(
        select(SchoolDropoutReportItem, Participant)
        .join(Participant, SchoolDropoutReportItem.participant_id == Participant.participant_id)
        .where(SchoolDropoutReportItem.report_id == report_id)
        .order_by(Participant.apellido_paterno, Participant.nombre)
    ).all()

    existing_participant_ids = {row[0].participant_id for row in report_items}

    return templates.TemplateResponse(
        "ui/school_dropout/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "report": report,
            "proposal": proposal,
            "eligible_rows": eligible_rows,
            "report_items": report_items,
            "existing_participant_ids": existing_participant_ids,
            "grade_options": GRADE_OPTIONS,
            "age_map": age_map,
            "msg": msg,
        },
    )


@router.post("/{report_id}/participants/add")
def add_participant_to_school_dropout_report(
    report_id: int,
    participant_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolDropoutReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")

    participant = db.get(Participant, participant_id)
    if not participant:
        return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Error: Participante no encontrado.", status_code=303)
    if current_user.role != "admin" and participant.created_by_user_id != report.created_by_user_id:
        return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Error: No tienes permiso para usar ese participante.", status_code=303)

    age = _calc_age(participant.fecha_nacimiento)
    if age is None or age < 0 or age > 21:
        return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Error: El participante no está dentro del rango 0-21 años.", status_code=303)
    if not participant.is_active:
        return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Error: El participante está inactivo.", status_code=303)

    existing = db.execute(
        select(SchoolDropoutReportItem).where(
            SchoolDropoutReportItem.report_id == report_id,
            SchoolDropoutReportItem.participant_id == participant_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Error: El participante ya fue añadido al informe.", status_code=303)

    item = SchoolDropoutReportItem(report_id=report_id, participant_id=participant_id)
    db.add(item)
    db.commit()

    return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Participante añadido al informe.", status_code=303)


@router.post("/{report_id}/items/{report_item_id}/edit")
def edit_school_dropout_report_item(
    report_id: int,
    report_item_id: int,
    attended_tutoring: str | None = Form(default=None),
    current_grade: str | None = Form(default=None),
    attended_school: str | None = Form(default=None),
    report_10_weeks: str | None = Form(default=None),
    report_20_weeks: str | None = Form(default=None),
    report_30_weeks: str | None = Form(default=None),
    report_40_weeks: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolDropoutReport, report_id)
    if not report:
        return RedirectResponse("/ui/school-dropout?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")

    item = db.get(SchoolDropoutReportItem, report_item_id)
    if not item or item.report_id != report_id:
        return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Error: Registro no encontrado.", status_code=303)

    item.attended_tutoring = attended_tutoring == "on"
    item.current_grade = (current_grade or "").strip() or None
    item.attended_school = attended_school == "on"
    item.report_10_weeks = report_10_weeks == "on"
    item.report_20_weeks = report_20_weeks == "on"
    item.report_30_weeks = report_30_weeks == "on"
    item.report_40_weeks = report_40_weeks == "on"

    db.add(item)
    db.commit()

    return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Registro actualizado exitosamente.", status_code=303)


@router.post("/{report_id}/delete")
def delete_school_dropout_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolDropoutReport, report_id)
    if not report:
        return RedirectResponse("/ui/school-dropout?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para borrar este informe.")

    db.execute(
        delete(SchoolDropoutReportItem).where(SchoolDropoutReportItem.report_id == report_id)
    )
    db.delete(report)
    db.commit()

    return RedirectResponse("/ui/school-dropout?msg=Informe de deserción escolar eliminado exitosamente.", status_code=303)


@router.post("/{report_id}/items/{report_item_id}/delete")
def delete_school_dropout_report_item(
    report_id: int,
    report_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolDropoutReport, report_id)
    if not report:
        return RedirectResponse("/ui/school-dropout?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")

    item = db.get(SchoolDropoutReportItem, report_item_id)
    if not item or item.report_id != report_id:
        return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Error: Registro no encontrado.", status_code=303)

    db.delete(item)
    db.commit()

    return RedirectResponse(f"/ui/school-dropout/{report_id}?msg=Participante removido del informe.", status_code=303)
