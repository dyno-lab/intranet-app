from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.core.period_guard import (
    is_proposal_period_locked,
    proposal_locked_through_label,
    require_proposal_period_open,
    require_reporting_period_not_future,
)
from app.core.proposal_guard import is_proposal_finalized
from app.models.participant import Participant
from app.helpers.report_context import MIN_REPORTING_YEAR
from app.models.pregnancy_report import PregnancyReport
from app.models.pregnancy_report_item import PregnancyReportItem
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _calc_age(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _report_is_locked(proposal: Proposal | None, report: PregnancyReport) -> bool:
    return bool(
        proposal
        and (
            is_proposal_finalized(proposal)
            or is_proposal_period_locked(proposal, report.report_month, report.report_year)
        )
    )


def _ensure_report_editable(proposal: Proposal | None, report: PregnancyReport, action: str) -> None:
    if proposal and is_proposal_finalized(proposal):
        raise HTTPException(status_code=409, detail=f"Error: La propuesta está finalizada y no permite {action} este informe.")
    if proposal and is_proposal_period_locked(proposal, report.report_month, report.report_year):
        raise HTTPException(
            status_code=409,
            detail=f"Error: La propuesta tiene periodos cerrados hasta {proposal_locked_through_label(proposal)} y no permite {action} este informe.",
        )


@router.get("", response_class=HTMLResponse)
def pregnancy_reports_index(
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
            PregnancyReport,
            Proposal.code.label("proposal_code"),
            Proposal.name.label("proposal_name"),
            User.username.label("created_by_username"),
            Residential.name.label("created_by_residential"),
        )
        .join(Proposal, PregnancyReport.proposal_id == Proposal.proposal_id)
        .join(User, PregnancyReport.created_by_user_id == User.user_id)
        .outerjoin(Residential, User.residential_id == Residential.residential_id)
        .order_by(PregnancyReport.report_year.desc(), PregnancyReport.report_month.desc(), PregnancyReport.report_id.desc())
    )

    if current_user.role != "admin":
        stmt = stmt.where(PregnancyReport.created_by_user_id == current_user.user_id)
    if proposal_id:
        stmt = stmt.where(PregnancyReport.proposal_id == proposal_id)
    if month:
        stmt = stmt.where(PregnancyReport.report_month == month)
    if year:
        stmt = stmt.where(PregnancyReport.report_year == year)

    reports = db.execute(stmt).all()
    proposals = db.execute(select(Proposal).where(Proposal.is_active == True).order_by(Proposal.code)).scalars().all()  # noqa: E712

    month_options = [
        (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
        (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
        (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
    ]
    current_year = date.today().year
    year_options = list(range(MIN_REPORTING_YEAR, current_year + 1))
    month_lookup = dict(month_options)

    return templates.TemplateResponse(
        "ui/pregnancy/index.html",
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
def create_pregnancy_report(
    proposal_id: int = Form(...),
    report_month: int = Form(...),
    report_year: int = Form(...),
    notes: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposal = db.get(Proposal, proposal_id)
    if not proposal:
        return RedirectResponse("/ui/pregnancy?msg=Error: Propuesta no encontrada.", status_code=303)
    if is_proposal_finalized(proposal):
        return RedirectResponse("/ui/pregnancy?msg=Error: La propuesta está finalizada y no permite crear informes.", status_code=303)
    try:
        require_reporting_period_not_future(report_month, report_year, message="Error: No se permite crear informes en periodos futuros.")
        require_proposal_period_open(
            proposal,
            report_month,
            report_year,
            message=f"Error: La propuesta tiene periodos cerrados hasta {proposal_locked_through_label(proposal)} y no permite crear ese informe.",
        )
    except HTTPException as exc:
        return RedirectResponse(f"/ui/pregnancy?proposal_id={proposal_id}&month={report_month}&year={report_year}&msg={exc.detail}", status_code=303)

    existing = db.execute(
        select(PregnancyReport).where(
            PregnancyReport.proposal_id == proposal_id,
            PregnancyReport.report_month == report_month,
            PregnancyReport.report_year == report_year,
            PregnancyReport.created_by_user_id == current_user.user_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(
            f"/ui/pregnancy?proposal_id={proposal_id}&month={report_month}&year={report_year}&msg=Error: Ya existe un informe para esa propuesta, mes y año.",
            status_code=303,
        )

    report = PregnancyReport(
        proposal_id=proposal_id,
        report_month=report_month,
        report_year=report_year,
        notes=(notes or "").strip() or None,
        created_by_user_id=current_user.user_id,
    )
    db.add(report)
    db.commit()

    return RedirectResponse(
        f"/ui/pregnancy/{report.report_id}?msg=Informe de embarazo creado exitosamente.",
        status_code=303,
    )


@router.get("/{report_id}", response_class=HTMLResponse)
def pregnancy_report_detail(
    report_id: int,
    request: Request,
    msg: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(PregnancyReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este informe.")

    proposal = db.get(Proposal, report.proposal_id)
    report_is_locked = _report_is_locked(proposal, report)

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
        if age is None or age < 8 or age > 19:
            continue
        eligible_rows.append({"p": participant, "age": age})
        age_map[participant.participant_id] = age

    report_items = db.execute(
        select(PregnancyReportItem, Participant)
        .join(Participant, PregnancyReportItem.participant_id == Participant.participant_id)
        .where(PregnancyReportItem.report_id == report_id)
        .order_by(Participant.apellido_paterno, Participant.nombre)
    ).all()

    existing_participant_ids = {row[0].participant_id for row in report_items}

    return templates.TemplateResponse(
        "ui/pregnancy/detail.html",
        {
            "request": request,
            "current_user": current_user,
            "report": report,
            "proposal": proposal,
            "eligible_rows": eligible_rows,
            "report_items": report_items,
            "existing_participant_ids": existing_participant_ids,
            "age_map": age_map,
            "report_is_locked": report_is_locked,
            "report_lock_label": proposal_locked_through_label(proposal),
            "msg": msg,
        },
    )


@router.post("/{report_id}/participants/add")
def add_participant_to_pregnancy_report(
    report_id: int,
    participant_id: int = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(PregnancyReport, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Informe no encontrado.")
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")
    proposal = db.get(Proposal, report.proposal_id)
    try:
        _ensure_report_editable(proposal, report, "editar")
    except HTTPException as exc:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg={exc.detail}", status_code=303)

    participant = db.get(Participant, participant_id)
    if not participant:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Error: Participante no encontrado.", status_code=303)
    if current_user.role != "admin" and participant.created_by_user_id != current_user.user_id:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Error: No tienes permiso para usar ese participante.", status_code=303)

    age = _calc_age(participant.fecha_nacimiento)
    if age is None or age < 8 or age > 19:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Error: El participante no está dentro del rango 8-19 años.", status_code=303)
    if not participant.is_active:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Error: El participante está inactivo.", status_code=303)

    existing = db.execute(
        select(PregnancyReportItem).where(
            PregnancyReportItem.report_id == report_id,
            PregnancyReportItem.participant_id == participant_id,
        )
    ).scalar_one_or_none()
    if existing:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Error: El participante ya fue añadido al informe.", status_code=303)

    item = PregnancyReportItem(report_id=report_id, participant_id=participant_id)
    db.add(item)
    db.commit()

    return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Participante añadido al informe.", status_code=303)


@router.post("/{report_id}/items/{report_item_id}/edit")
def edit_pregnancy_report_item(
    report_id: int,
    report_item_id: int,
    participated_workshops: str | None = Form(default=None),
    is_pregnant: str | None = Form(default=None),
    gestation_time: str | None = Form(default=None),
    has_children: str | None = Form(default=None),
    children_count: int | None = Form(default=None),
    children_ages: str | None = Form(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(PregnancyReport, report_id)
    if not report:
        return RedirectResponse("/ui/pregnancy?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")
    proposal = db.get(Proposal, report.proposal_id)
    try:
        _ensure_report_editable(proposal, report, "editar")
    except HTTPException as exc:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg={exc.detail}", status_code=303)

    item = db.get(PregnancyReportItem, report_item_id)
    if not item or item.report_id != report_id:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Error: Registro no encontrado.", status_code=303)

    item.participated_workshops = participated_workshops == "on"
    item.is_pregnant = is_pregnant == "on"
    item.gestation_time = (gestation_time or "").strip() or None
    item.has_children = has_children == "on"
    item.children_count = children_count
    item.children_ages = (children_ages or "").strip() or None

    db.add(item)
    db.commit()

    return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Registro actualizado exitosamente.", status_code=303)


@router.post("/{report_id}/delete")
def delete_pregnancy_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(PregnancyReport, report_id)
    if not report:
        return RedirectResponse("/ui/pregnancy?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para borrar este informe.")
    proposal = db.get(Proposal, report.proposal_id)
    try:
        _ensure_report_editable(proposal, report, "borrar")
    except HTTPException as exc:
        return RedirectResponse(f"/ui/pregnancy?msg={exc.detail}", status_code=303)

    db.execute(
        delete(PregnancyReportItem).where(PregnancyReportItem.report_id == report_id)
    )
    db.flush()
    db.execute(
        delete(PregnancyReport).where(PregnancyReport.report_id == report_id)
    )
    db.commit()

    return RedirectResponse("/ui/pregnancy?msg=Informe de embarazo eliminado exitosamente.", status_code=303)


@router.post("/{report_id}/items/{report_item_id}/delete")
def delete_pregnancy_report_item(
    report_id: int,
    report_item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    report = db.get(PregnancyReport, report_id)
    if not report:
        return RedirectResponse("/ui/pregnancy?msg=Error: Informe no encontrado.", status_code=303)
    if current_user.role != "admin" and report.created_by_user_id != current_user.user_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para editar este informe.")
    proposal = db.get(Proposal, report.proposal_id)
    try:
        _ensure_report_editable(proposal, report, "editar")
    except HTTPException as exc:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg={exc.detail}", status_code=303)

    item = db.get(PregnancyReportItem, report_item_id)
    if not item or item.report_id != report_id:
        return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Error: Registro no encontrado.", status_code=303)

    db.delete(item)
    db.commit()

    return RedirectResponse(f"/ui/pregnancy/{report_id}?msg=Participante removido del informe.", status_code=303)
