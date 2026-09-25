"""Program-scoped attendance and school-grade screens."""
from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.community_access import CommunityContext, csrf_token, require_community_context, require_community_writer, require_programs, validate_csrf
from app.models.community import CPFiscalYear, CPProgram
from app.models.community_activity import CPActivity, CPFiscalActivity
from app.models.community_operations import CPActivitySession, CPAttendance, CPGradeReport, CPGradeItem, GRADE_FIELDS
from app.services.community_fiscal import require_fiscal_writable, snapshot_for_participant
from app.services.community_operations import (
    create_activity_session, set_session_attendance, enrolled_participant_ids,
    create_grade_report, save_grade_item, grade_period, grade_participant_ids,
    grade_letter, GRADE_OPTIONS, GRADE_LABELS,
)

router = APIRouter(prefix="/community", tags=["community-operations"])
templates = Jinja2Templates(directory="app/templates")


def _render(request: Request, name: str, cp: CommunityContext, **values):
    return templates.TemplateResponse(request=request, name=f"community/{name}.html", context={
        "request": request, "current_user": cp.user, "cp": cp, "csrf_token": csrf_token(request),
        "message": request.query_params.get("msg"), "error": request.query_params.get("error"),
        "today": date.today(), **values,
    })


def _redirect(path: str, *, message: str | None = None, error: str | None = None):
    separator = "&" if "?" in path else "?"
    return RedirectResponse(path + separator + urlencode({"error": error} if error else {"msg": message}), status_code=303)


def _row(db: Session, model, row_id: int, cp: CommunityContext):
    row = db.get(model, row_id)
    if row is None or row.program_id not in cp.visible_program_ids:
        raise HTTPException(404, "Registro no disponible en sus programas.")
    return row


def _snapshots(db: Session, fiscal_year_id: int, participant_ids):
    rows = []
    for participant_id in participant_ids:
        snapshot = snapshot_for_participant(db, participant_id, fiscal_year_id)
        if snapshot is not None:
            rows.append({**snapshot, "participant_id": participant_id})
    return sorted(rows, key=lambda item: (item.get("apellido_paterno", ""), item.get("nombre", ""), item["participant_id"]))


def _filters(db: Session, cp: CommunityContext, fiscal_year_id: int | None, program_id: int | None):
    if program_id is not None:
        require_programs(cp, [program_id])
    years = db.scalars(select(CPFiscalYear).order_by(CPFiscalYear.start_date.desc())).all()
    if fiscal_year_id is not None and not any(year.fiscal_year_id == fiscal_year_id for year in years):
        raise HTTPException(404, "Año fiscal no disponible.")
    return years


def _lock_message(db: Session, fiscal_year_id: int, event_date: date) -> str | None:
    try:
        require_fiscal_writable(db, fiscal_year_id, event_date)
    except ValueError as exc:
        return str(exc)
    return None


def _page_links(path: str, page: int, has_next: bool, fiscal_year_id: int | None, program_id: int | None):
    filters = {key: value for key, value in {"fiscal_year_id": fiscal_year_id, "program_id": program_id}.items() if value is not None}
    return {
        "page": page,
        "previous_url": path + "?" + urlencode({**filters, "page": page - 1}) if page > 1 else None,
        "next_url": path + "?" + urlencode({**filters, "page": page + 1}) if has_next else None,
    }


@router.get("/attendance")
def attendance_index(request: Request, fiscal_year_id: int | None = None, program_id: int | None = None,
                     page: int = 1,
                     db: Session = Depends(get_db), cp: CommunityContext = Depends(require_community_context)):
    page = max(1, page)
    years = _filters(db, cp, fiscal_year_id, program_id)
    query = select(CPActivitySession, CPProgram, CPActivity, CPFiscalYear).join(
        CPProgram, CPProgram.program_id == CPActivitySession.program_id
    ).join(CPActivity, CPActivity.activity_id == CPActivitySession.activity_id).join(
        CPFiscalYear, CPFiscalYear.fiscal_year_id == CPActivitySession.fiscal_year_id
    ).where(CPActivitySession.program_id.in_(cp.visible_program_ids))
    if fiscal_year_id is not None:
        query = query.where(CPActivitySession.fiscal_year_id == fiscal_year_id)
    if program_id is not None:
        query = query.where(CPActivitySession.program_id == program_id)
    activities = []
    if fiscal_year_id is not None and program_id is not None:
        activities = db.scalars(select(CPActivity).join(CPFiscalActivity, CPFiscalActivity.activity_id == CPActivity.activity_id).where(
            CPFiscalActivity.fiscal_year_id == fiscal_year_id, CPFiscalActivity.program_id == program_id,
            CPFiscalActivity.is_active == True, CPActivity.is_active == True,  # noqa: E712
            CPActivity.program_id == program_id,
        ).order_by(CPActivity.code)).all()
    rows = db.execute(query.order_by(CPActivitySession.session_date.desc(), CPActivitySession.session_id.desc()).offset((page - 1) * 50).limit(51)).all()
    return _render(request, "attendance", cp, years=years, selected_year=fiscal_year_id,
                   selected_program=program_id, activities=activities, sessions=rows[:50], session=None,
                   **_page_links("/community/attendance", page, len(rows) > 50, fiscal_year_id, program_id))


@router.post("/attendance")
def add_activity_session(request: Request, fiscal_year_id: int = Form(...), program_id: int = Form(...),
                         activity_id: int = Form(...), session_date: date = Form(...),
                         token: str = Form(...), notes: str | None = Form(None), db: Session = Depends(get_db),
                         cp: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    require_programs(cp, [program_id])
    path = "/community/attendance?" + urlencode({"fiscal_year_id": fiscal_year_id, "program_id": program_id})
    try:
        row = create_activity_session(db, fiscal_year_id=fiscal_year_id, program_id=program_id,
                                      activity_id=activity_id, session_date=session_date,
                                      actor_user_id=cp.user.user_id, notes=notes)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect(path, error=str(exc) if isinstance(exc, ValueError) else "No se pudo guardar la actividad.")
    return _redirect(f"/community/attendance/{row.session_id}", message="Actividad creada. Registre la asistencia.")


@router.get("/attendance/{session_id}")
def attendance_detail(session_id: int, request: Request, db: Session = Depends(get_db),
                      cp: CommunityContext = Depends(require_community_context)):
    session = _row(db, CPActivitySession, session_id, cp)
    attendance = {row.participant_id: row.is_present for row in db.scalars(select(CPAttendance).where(CPAttendance.session_id == session_id)).all()}
    eligible = set(enrolled_participant_ids(db, session.fiscal_year_id, session.program_id, session.session_date))
    participants = _snapshots(db, session.fiscal_year_id, eligible | set(attendance))
    return _render(request, "attendance", cp, session=session, participants=participants, attendance=attendance,
                   eligible_ids=eligible, program=db.get(CPProgram, session.program_id),
                   activity=db.get(CPActivity, session.activity_id), fiscal_year=db.get(CPFiscalYear, session.fiscal_year_id),
                   lock_message=_lock_message(db, session.fiscal_year_id, session.session_date))


@router.post("/attendance/{session_id}")
async def save_attendance(session_id: int, request: Request, db: Session = Depends(get_db),
                          cp: CommunityContext = Depends(require_community_writer)):
    form = await request.form()
    validate_csrf(request, str(form.get("token", "")))
    _row(db, CPActivitySession, session_id, cp)
    try:
        participant_ids = [int(value) for value in form.getlist("present_participant_ids")]
        set_session_attendance(db, session_id=session_id, present_participant_ids=participant_ids)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect(f"/community/attendance/{session_id}", error=str(exc) if isinstance(exc, ValueError) else "No se pudo guardar la asistencia.")
    return _redirect(f"/community/attendance/{session_id}", message="Asistencia guardada.")


@router.get("/school-grades")
def grades_index(request: Request, fiscal_year_id: int | None = None, program_id: int | None = None,
                 page: int = 1,
                 db: Session = Depends(get_db), cp: CommunityContext = Depends(require_community_context)):
    page = max(1, page)
    years = _filters(db, cp, fiscal_year_id, program_id)
    query = select(CPGradeReport, CPProgram, CPFiscalYear).join(
        CPProgram, CPProgram.program_id == CPGradeReport.program_id
    ).join(CPFiscalYear, CPFiscalYear.fiscal_year_id == CPGradeReport.fiscal_year_id).where(
        CPGradeReport.program_id.in_(cp.visible_program_ids)
    )
    if fiscal_year_id is not None:
        query = query.where(CPGradeReport.fiscal_year_id == fiscal_year_id)
    if program_id is not None:
        query = query.where(CPGradeReport.program_id == program_id)
    reports = db.execute(query.order_by(CPGradeReport.report_year.desc(), CPGradeReport.report_month.desc(), CPGradeReport.report_id.desc()).offset((page - 1) * 50).limit(51)).all()
    return _render(request, "school_grades", cp, years=years, selected_year=fiscal_year_id,
                   selected_program=program_id, reports=reports[:50], report=None,
                   **_page_links("/community/school-grades", page, len(reports) > 50, fiscal_year_id, program_id))


@router.post("/school-grades")
def add_grade_report(request: Request, fiscal_year_id: int = Form(...), program_id: int = Form(...),
                     report_month: int = Form(...), report_year: int = Form(...), token: str = Form(...),
                     notes: str | None = Form(None), db: Session = Depends(get_db),
                     cp: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    require_programs(cp, [program_id])
    path = "/community/school-grades?" + urlencode({"fiscal_year_id": fiscal_year_id, "program_id": program_id})
    try:
        report = create_grade_report(db, fiscal_year_id=fiscal_year_id, program_id=program_id,
                                     report_month=report_month, report_year=report_year,
                                     actor_user_id=cp.user.user_id, notes=notes)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect(path, error=str(exc) if isinstance(exc, ValueError) else "Ya existe un informe en ese período o no se pudo guardar.")
    return _redirect(f"/community/school-grades/{report.report_id}", message="Informe de notas creado.")


@router.get("/school-grades/{report_id}")
def grade_detail(report_id: int, request: Request, db: Session = Depends(get_db),
                  cp: CommunityContext = Depends(require_community_context)):
    report = _row(db, CPGradeReport, report_id, cp)
    first, _ = grade_period(db, report.fiscal_year_id, report.report_year, report.report_month)
    items = db.scalars(select(CPGradeItem).where(CPGradeItem.report_id == report_id).order_by(CPGradeItem.participant_id)).all()
    existing_ids = {item.participant_id for item in items}
    snapshots = {row["participant_id"]: row for row in _snapshots(db, report.fiscal_year_id, existing_ids)}
    eligible = _snapshots(db, report.fiscal_year_id, set(grade_participant_ids(db, report)) - existing_ids)
    return _render(request, "school_grades", cp, report=report, program=db.get(CPProgram, report.program_id),
                   fiscal_year=db.get(CPFiscalYear, report.fiscal_year_id), items=items, snapshots=snapshots,
                   eligible=eligible, grade_options=GRADE_OPTIONS, grade_columns=list(zip(GRADE_FIELDS, GRADE_LABELS)),
                   grade_letter=grade_letter, lock_message=_lock_message(db, report.fiscal_year_id, first))


@router.post("/school-grades/{report_id}/participants")
async def save_grades(report_id: int, request: Request, db: Session = Depends(get_db),
                      cp: CommunityContext = Depends(require_community_writer)):
    form = await request.form()
    validate_csrf(request, str(form.get("token", "")))
    _row(db, CPGradeReport, report_id, cp)
    try:
        participant_id = int(form.get("participant_id", ""))
        fields = {field: form.get(field) for field in (*GRADE_FIELDS, "grade_level")}
        fields["is_content_room"] = form.get("is_content_room") == "on"
        save_grade_item(db, report_id=report_id, participant_id=participant_id, fields=fields)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect(f"/community/school-grades/{report_id}", error=str(exc) if isinstance(exc, ValueError) else "No se pudieron guardar las notas.")
    return _redirect(f"/community/school-grades/{report_id}", message="Notas guardadas.")
