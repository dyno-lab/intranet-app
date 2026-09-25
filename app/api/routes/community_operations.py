"""Program-scoped attendance and school-grade screens."""
from __future__ import annotations

from datetime import date
import csv
import io
import json
from urllib.parse import urlencode, parse_qsl

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.community_access import CommunityContext, csrf_token, require_community_context, require_community_writer, require_programs, validate_csrf
from app.models.community import CPFiscalYear, CPProgram
from app.models.community_activity import CPActivity
from app.models.community_operations import CPActivitySession, CPAttendance, CPGradeReport, CPGradeItem, GRADE_FIELDS
from app.models.community_fiscal import CPFiscalParticipant
from app.services import community_attendance as attendance_service
from app.services.community_participants import AGE_RANGES
from app.services.community_fiscal import require_fiscal_writable, snapshot_for_participant
from app.services.community_operations import (
    create_activity_session, set_session_attendance,
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


def _attendance_selection(request, db, cp):
    try:
        filters = attendance_service.session_filters(request.query_params, cp)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    years = _filters(db, cp, filters["fiscal_year_id"], filters["program_id"])
    return filters, years


def _attendance_query(filters, **extra):
    return urlencode({key: value for key, value in {**filters, **extra}.items() if value is not None and value != ""})


def _attendance_return(request, session=None):
    allowed = {"fiscal_year_id", "program_id", "month", "year", "control_number", "from_date", "to_date", "page", "per_page"}
    query = dict((key, value) for key, value in parse_qsl(request.query_params.get("return_query", "")[:2000]) if key in allowed)
    if not query and session:
        query = {"fiscal_year_id": session.fiscal_year_id, "program_id": session.program_id}
    return urlencode(query)


def _attendance_index_response(request, db, cp, *, create_form=None, form_error=None):
    filters, years = _attendance_selection(request, db, cp)
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        per_page = int(request.query_params.get("per_page", 50))
    except ValueError:
        raise HTTPException(422, "Paginación inválida.") from None
    if per_page not in (25, 50, 100):
        per_page = 50
    query = attendance_service.filtered_sessions(cp, filters)
    metrics = attendance_service.session_metrics(db, query)
    pages = max(1, (metrics["total_activities"] + per_page - 1) // per_page)
    page = min(page, pages)
    rows = db.execute(attendance_service.session_rows(query).offset((page - 1) * per_page).limit(per_page)).all()
    form = create_form if create_form is not None else {
        "fiscal_year_id": filters["fiscal_year_id"], "program_id": filters["program_id"],
    }
    activities = []
    if form.get("fiscal_year_id") and form.get("program_id"):
        require_programs(cp, [form["program_id"]])
        activities = attendance_service.available_activities(db, form["fiscal_year_id"], form["program_id"])
    query_string = _attendance_query(filters, page=page, per_page=per_page)
    states = attendance_service.fiscal_date_options(db, years)
    return _render(request, "attendance", cp, years=years, filters=filters, sessions=rows,
                   metrics=metrics, session=None, create_form=form, form_error=form_error,
                   activities=activities, fiscal_options=states, month_options=attendance_service.MONTHS,
                   filter_years=list(range(min([year.start_date.year for year in years] + [date.today().year]), date.today().year + 1)),
                   page=page, per_page=per_page, total_pages=pages, query_string=query_string,
                   export_query=_attendance_query(filters),
                   page_url=lambda number: "/community/attendance?" + _attendance_query(filters, page=number, per_page=per_page),
                   detail_url=lambda number: f"/community/attendance/{number}?" + urlencode({"return_query": query_string}))


@router.get("/attendance")
def attendance_index(request: Request, db: Session = Depends(get_db),
                     cp: CommunityContext = Depends(require_community_context)):
    return _attendance_index_response(request, db, cp)


@router.get("/attendance/activities")
def attendance_activity_options(fiscal_year_id: int, program_id: int, db: Session = Depends(get_db),
                                cp: CommunityContext = Depends(require_community_context)):
    _filters(db, cp, fiscal_year_id, program_id)
    return {"activities": [{"id": row.activity_id, "label": f"{row.code} · {row.description or ''}"}
                           for row in attendance_service.available_activities(db, fiscal_year_id, program_id)]}


def _attendance_csv(rows, filename):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    for row in rows:
        safe = []
        for value in row:
            cell = str(value) if value is not None else ""
            safe.append("'" + cell if cell.lstrip().startswith(("=", "+", "-", "@")) or cell.startswith(("\t", "\r", "\n")) else cell)
        writer.writerow(safe)
    return Response(output.getvalue().encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/attendance/export.csv")
def export_community_sessions(request: Request, db: Session = Depends(get_db),
                              cp: CommunityContext = Depends(require_community_context)):
    filters, _ = _attendance_selection(request, db, cp)
    query = attendance_service.filtered_sessions(cp, filters)
    rows = [["Control", "Fecha", "Año fiscal", "Programa", "Actividad", "Descripción", "Participaciones", "Creado por", "Minutos"]]
    for session, program, activity, year, creator, count in db.execute(attendance_service.session_rows(query)):
        rows.append([session.control_number, session.session_date, year.code, program.code, activity.code,
                     activity.description, count, creator, session.duration_minutes])
    return _attendance_csv(rows, "sesiones_comunidad.csv")


@router.get("/attendance/export-attendance.csv")
def export_community_attendance(request: Request, db: Session = Depends(get_db),
                                cp: CommunityContext = Depends(require_community_context)):
    filters, _ = _attendance_selection(request, db, cp)
    selected = attendance_service.filtered_sessions(cp, filters)
    query = select(CPActivitySession, CPProgram.code, CPActivity.code, CPFiscalYear.code, CPFiscalParticipant.snapshot_json).join(
        CPAttendance, CPAttendance.session_id == CPActivitySession.session_id
    ).join(CPFiscalParticipant, (CPFiscalParticipant.participant_id == CPAttendance.participant_id) &
           (CPFiscalParticipant.fiscal_year_id == CPActivitySession.fiscal_year_id)
    ).join(CPProgram, CPProgram.program_id == CPActivitySession.program_id).join(
        CPActivity, CPActivity.activity_id == CPActivitySession.activity_id
    ).join(CPFiscalYear, CPFiscalYear.fiscal_year_id == CPActivitySession.fiscal_year_id).where(
        CPActivitySession.session_id.in_(selected), CPAttendance.is_present == True,  # noqa: E712
    ).order_by(CPActivitySession.session_date.desc(), CPActivitySession.session_id.desc(), CPAttendance.participant_id)
    rows = [["Control", "Fecha", "Año fiscal", "Programa", "Actividad", "Expediente", "Nombre",
             "Inicial", "Apellido paterno", "Apellido materno", "Género", "Asistió"]]
    for session, program, activity, year, raw in db.execute(query):
        snapshot = json.loads(raw)
        rows.append([session.control_number, session.session_date, year, program, activity,
                     *[snapshot.get(key, "") for key in ("expediente_num", "nombre", "inicial", "apellido_paterno", "apellido_materno", "genero")], "Sí"])
    return _attendance_csv(rows, "asistencias_comunidad.csv")


@router.post("/attendance")
def add_activity_session(request: Request, fiscal_year_id: int = Form(...), program_id: int = Form(...),
                         activity_id: int = Form(...), session_date: date = Form(...),
                         token: str = Form(...), notes: str | None = Form(None), duration_minutes: str = Form(""),
                         db: Session = Depends(get_db), cp: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    require_programs(cp, [program_id])
    form = dict(fiscal_year_id=fiscal_year_id, program_id=program_id, activity_id=activity_id,
                session_date=session_date, notes=notes, duration_minutes=duration_minutes)
    try:
        row = create_activity_session(db, actor_user_id=cp.user.user_id, **form)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _attendance_index_response(request, db, cp, create_form=form,
                                          form_error=str(exc) if isinstance(exc, ValueError) else "No se pudo guardar la actividad.")
    return _redirect(f"/community/attendance/{row.session_id}", message="Sesión creada. Registre la asistencia.")


def _attendance_detail_response(request, db, cp, session_id, *, edit_form=None, form_error=None):
    session = _row(db, CPActivitySession, session_id, cp)
    attendance = {row.participant_id: row.is_present for row in db.scalars(select(CPAttendance).where(CPAttendance.session_id == session_id))}
    participants, eligible = attendance_service.session_roster(db, session)
    years = _filters(db, cp, session.fiscal_year_id, session.program_id)
    form = edit_form if edit_form is not None else {
        "fiscal_year_id": session.fiscal_year_id, "program_id": session.program_id,
        "activity_id": session.activity_id, "session_date": session.session_date,
        "duration_minutes": session.duration_minutes, "notes": session.notes,
    }
    activities = attendance_service.available_activities(db, form["fiscal_year_id"], form["program_id"])
    return_query = _attendance_return(request, session)
    return _render(request, "attendance", cp, session=session, participants=participants, attendance=attendance,
                   eligible_ids=eligible, program=db.get(CPProgram, session.program_id),
                   activity=db.get(CPActivity, session.activity_id), fiscal_year=db.get(CPFiscalYear, session.fiscal_year_id),
                   lock_message=_lock_message(db, session.fiscal_year_id, session.session_date),
                   years=years, activities=activities, edit_form=form, form_error=form_error,
                   open_edit=edit_form is not None, has_attendance=bool(attendance),
                   fiscal_options=attendance_service.fiscal_date_options(db, years), age_ranges=AGE_RANGES,
                   return_query=return_query, back_url="/community/attendance?" + return_query,
                   detail_path=f"/community/attendance/{session_id}?" + urlencode({"return_query": return_query}))


@router.get("/attendance/{session_id}")
def attendance_detail(session_id: int, request: Request, db: Session = Depends(get_db),
                      cp: CommunityContext = Depends(require_community_context)):
    return _attendance_detail_response(request, db, cp, session_id)


@router.post("/attendance/{session_id}")
async def save_attendance(session_id: int, request: Request, db: Session = Depends(get_db),
                          cp: CommunityContext = Depends(require_community_writer)):
    form = await request.form()
    validate_csrf(request, str(form.get("token", "")))
    session = _row(db, CPActivitySession, session_id, cp)
    path = f"/community/attendance/{session_id}?" + urlencode({"return_query": _attendance_return(request, session)})
    try:
        participant_ids = [int(value) for value in form.getlist("present_participant_ids")]
        set_session_attendance(db, session_id=session_id, present_participant_ids=participant_ids)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect(path, error=str(exc) if isinstance(exc, ValueError) else "No se pudo guardar la asistencia.")
    return _redirect(path, message="Asistencia guardada.")


@router.post("/attendance/{session_id}/edit")
def edit_attendance_session(session_id: int, request: Request, token: str = Form(...),
                            fiscal_year_id: int = Form(...), program_id: int = Form(...), activity_id: int = Form(...),
                            session_date: date = Form(...), duration_minutes: str = Form(""), notes: str = Form(""),
                            db: Session = Depends(get_db), cp: CommunityContext = Depends(require_community_writer)):
    validate_csrf(request, token)
    _row(db, CPActivitySession, session_id, cp)
    require_programs(cp, [program_id])
    form = dict(fiscal_year_id=fiscal_year_id, program_id=program_id, activity_id=activity_id,
                session_date=session_date, duration_minutes=duration_minutes, notes=notes)
    try:
        attendance_service.edit_session(db, session_id=session_id, **form)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _attendance_detail_response(request, db, cp, session_id, edit_form=form,
                                           form_error=str(exc) if isinstance(exc, ValueError) else "No se pudo actualizar la sesión.")
    path = f"/community/attendance/{session_id}?" + urlencode({"return_query": _attendance_return(request)})
    return _redirect(path, message="Sesión actualizada.")


def _remove_attendance(request, db, cp, session_id, token, *, remove_session):
    validate_csrf(request, token)
    session = _row(db, CPActivitySession, session_id, cp)
    return_query = _attendance_return(request, session)
    detail_path = f"/community/attendance/{session_id}?" + urlencode({"return_query": return_query})
    try:
        attendance_service.clear_session(db, session_id=session_id, delete_session=remove_session)
        db.commit()
    except (ValueError, IntegrityError) as exc:
        db.rollback()
        return _redirect(detail_path, error=str(exc) if isinstance(exc, ValueError) else "No se pudo eliminar: existen datos asociados.")
    return _redirect("/community/attendance?" + return_query if remove_session else detail_path,
                     message="Sesión y asistencias eliminadas." if remove_session else "Asistencias eliminadas.")


def _attendance_manager(cp: CommunityContext = Depends(require_community_context)):
    if cp.role not in {"admin", "supervisor"}:
        raise HTTPException(403, "Eliminar sesiones o asistencias requiere Supervisor o Administrador de Comunidad.")
    return cp


@router.post("/attendance/{session_id}/clear-attendance")
def clear_attendance_session(session_id: int, request: Request, token: str = Form(...),
                             db: Session = Depends(get_db), cp: CommunityContext = Depends(_attendance_manager)):
    return _remove_attendance(request, db, cp, session_id, token, remove_session=False)


@router.post("/attendance/{session_id}/delete")
def delete_attendance_session(session_id: int, request: Request, token: str = Form(...),
                              db: Session = Depends(get_db), cp: CommunityContext = Depends(_attendance_manager)):
    return _remove_attendance(request, db, cp, session_id, token, remove_session=True)


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
