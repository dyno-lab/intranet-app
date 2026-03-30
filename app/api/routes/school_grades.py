from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.school_grade_report import SchoolGradeReport
from app.models.school_grade_report_item import SchoolGradeReportItem
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


GRADE_OPTIONS = ["EE", "K", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]
GRADE_FIELDS = [
    "spanish_grade",
    "english_grade",
    "math_grade",
    "science_grade",
    "social_studies_grade",
    "elective_1_grade",
    "elective_2_grade",
    "elective_3_grade",
    "elective_4_grade",
]


def _calc_age(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _compute_average(values: list[float | None]) -> float | None:
    valid = [float(v) for v in values if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 2)


def _parse_grade_value(value: str | None) -> float | None:
    if value is None:
        return None
    raw = str(value).strip()
    if raw == "":
        return None
    number = float(raw)
    if number < 0 or number > 100:
        raise ValueError("Las notas deben estar entre 0 y 100.")
    return number


def _grade_letter(average: float | None) -> str:
    if average is None:
        return ""
    if average >= 90:
        return "A"
    if average >= 80:
        return "B"
    if average >= 70:
        return "C"
    if average >= 60:
        return "D"
    return "F"


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
        select(
            SchoolGradeReport,
            Proposal.code.label("proposal_code"),
            Proposal.name.label("proposal_name"),
            User.username.label("created_by_username"),
            Residential.name.label("created_by_residential"),
        )
        .join(Proposal, SchoolGradeReport.proposal_id == Proposal.proposal_id)
        .join(User, SchoolGradeReport.created_by_user_id == User.user_id)
        .outerjoin(Residential, User.residential_id == Residential.residential_id)
        .order_by(SchoolGradeReport.report_year.desc(), SchoolGradeReport.report_month.desc(), SchoolGradeReport.report_id.desc())
    )

    if current_user.role not in {"admin", "supervisor"}:
        stmt = stmt.where(SchoolGradeReport.created_by_user_id == current_user.user_id)

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
    month_lookup = dict(month_options)

    return templates.TemplateResponse(
        "ui/school_grades/index.html",
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
            SchoolGradeReport.created_by_user_id == current_user.user_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            f"/ui/school-grades?proposal_id={proposal_id}&month={report_month}&year={report_year}&msg=Error: Ya existe un informe tuyo para esa propuesta, mes y año.",
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

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"/ui/school-grades?proposal_id={proposal_id}&month={report_month}&year={report_year}&msg=Error: Ya existe un informe tuyo para esa propuesta, mes y año.",
            status_code=303,
        )

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
    if current_user.role not in {"admin", "supervisor"} and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este informe.")

    proposal = db.get(Proposal, report.proposal_id)

    participant_stmt = (
        select(Participant)
        .where(Participant.is_active == True)  # noqa: E712
        .order_by(Participant.apellido_paterno, Participant.nombre)
    )
    if current_user.role != "admin":
        participant_stmt = participant_stmt.where(Participant.created_by_user_id == current_user.user_id)

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
            "age_map": age_map,
            "grade_letter": _grade_letter,
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
    if current_user.role not in {"admin", "supervisor"} and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")

    participant = db.get(Participant, participant_id)
    if not participant:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: Participante no encontrado.", status_code=303)

    if current_user.role != "admin" and participant.created_by_user_id != current_user.user_id:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: No tienes permiso para usar ese participante.", status_code=303)

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


@router.post("/{report_id}/items/{report_item_id}/edit")
def edit_school_grade_report_item(
    report_id: int,
    report_item_id: int,
    grade_level: str | None = Form(default=None),
    is_content_room: str | None = Form(default=None),
    spanish_grade: str | None = Form(default=None),
    english_grade: str | None = Form(default=None),
    math_grade: str | None = Form(default=None),
    science_grade: str | None = Form(default=None),
    social_studies_grade: str | None = Form(default=None),
    elective_1_grade: str | None = Form(default=None),
    elective_2_grade: str | None = Form(default=None),
    elective_3_grade: str | None = Form(default=None),
    elective_4_grade: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolGradeReport, report_id)
    if not report:
        return RedirectResponse("/ui/school-grades?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role not in {"admin", "supervisor"} and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")

    item = db.get(SchoolGradeReportItem, report_item_id)
    if not item or item.report_id != report_id:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: Registro no encontrado.", status_code=303)

    try:
        values = {
            "spanish_grade": _parse_grade_value(spanish_grade),
            "english_grade": _parse_grade_value(english_grade),
            "math_grade": _parse_grade_value(math_grade),
            "science_grade": _parse_grade_value(science_grade),
            "social_studies_grade": _parse_grade_value(social_studies_grade),
            "elective_1_grade": _parse_grade_value(elective_1_grade),
            "elective_2_grade": _parse_grade_value(elective_2_grade),
            "elective_3_grade": _parse_grade_value(elective_3_grade),
            "elective_4_grade": _parse_grade_value(elective_4_grade),
        }
    except ValueError as exc:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: {exc}", status_code=303)

    item.grade_level = (grade_level or "").strip() or None
    item.is_content_room = is_content_room == "on"
    for field, value in values.items():
        setattr(item, field, value)

    item.average_grade = _compute_average([values[field] for field in GRADE_FIELDS])

    db.add(item)
    db.commit()

    return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Registro actualizado exitosamente.", status_code=303)


@router.post("/{report_id}/delete")
def delete_school_grade_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolGradeReport, report_id)
    if not report:
        return RedirectResponse("/ui/school-grades?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role not in {"admin", "supervisor"} and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para borrar este informe.")

    db.execute(
        delete(SchoolGradeReportItem).where(SchoolGradeReportItem.report_id == report_id)
    )
    db.flush()
    db.execute(
        delete(SchoolGradeReport).where(SchoolGradeReport.report_id == report_id)
    )
    db.commit()

    return RedirectResponse("/ui/school-grades?msg=Informe de notas eliminado exitosamente.", status_code=303)


@router.post("/{report_id}/items/{report_item_id}/delete")
def delete_school_grade_report_item(
    report_id: int,
    report_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(SchoolGradeReport, report_id)
    if not report:
        return RedirectResponse("/ui/school-grades?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role not in {"admin", "supervisor"} and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")

    item = db.get(SchoolGradeReportItem, report_item_id)
    if not item or item.report_id != report_id:
        return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Error: Registro no encontrado.", status_code=303)

    db.delete(item)
    db.commit()

    return RedirectResponse(f"/ui/school-grades/{report_id}?msg=Participante removido del informe.", status_code=303)
