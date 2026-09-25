"""Operational writes validate fiscal history and flush; routes authorize and commit."""
from __future__ import annotations

from calendar import monthrange
from datetime import date
import math
from typing import Any, Iterable, Mapping

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.community import CPFiscalYear, CPProgram
from app.models.community_activity import CPActivity, CPFiscalActivity
from app.models.community_fiscal import CPFiscalEnrollment, CPEnrollmentPeriod
from app.models.community_operations import CPActivitySession, CPAttendance, CPGradeReport, CPGradeItem, GRADE_FIELDS
from app.services.community import _date, _text, _validate_actor
from app.services.community_fiscal import require_fiscal_writable, snapshot_for_participant

GRADE_OPTIONS = ("EE", "K", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12")
GRADE_LABELS = ("Español", "Inglés", "Matemáticas", "Ciencias", "Estudios sociales", "Electiva 1", "Electiva 2", "Electiva 3", "Electiva 4")


def _program(db: Session, program_id: int) -> CPProgram:
    program = db.get(CPProgram, program_id)
    if program is None or not program.is_active:
        raise ValueError("El programa no existe o está inactivo.")
    return program


def _activity_context(db: Session, fiscal_year_id: int, program_id: int, activity_id: int) -> None:
    _program(db, program_id)
    activity = db.get(CPActivity, activity_id)
    fiscal_activity = db.get(CPFiscalActivity, (activity_id, fiscal_year_id))
    if (activity is None or not activity.is_active or activity.program_id != program_id
            or fiscal_activity is None or not fiscal_activity.is_active or fiscal_activity.program_id != program_id):
        raise ValueError("Seleccione una actividad activa del programa y año fiscal.")


def enrolled_participant_ids(db: Session, fiscal_year_id: int, program_id: int,
                             start_date: date, end_date: date | None = None) -> list[int]:
    """Historical interval intersection; deliberately does not use current status."""
    year = db.get(CPFiscalYear, fiscal_year_id)
    if year is None:
        return []
    start_date, end_date = max(start_date, year.start_date), min(end_date or start_date, year.end_date)
    if end_date < start_date:
        return []
    return list(db.scalars(select(CPFiscalEnrollment.participant_id).join(
        CPEnrollmentPeriod, CPEnrollmentPeriod.enrollment_id == CPFiscalEnrollment.enrollment_id
    ).where(
        CPFiscalEnrollment.fiscal_year_id == fiscal_year_id, CPFiscalEnrollment.program_id == program_id,
        CPEnrollmentPeriod.start_date <= end_date,
        or_(CPEnrollmentPeriod.end_date.is_(None), CPEnrollmentPeriod.end_date > start_date),
        or_(CPEnrollmentPeriod.end_date.is_(None), CPEnrollmentPeriod.end_date > CPEnrollmentPeriod.start_date),
    ).distinct().order_by(CPFiscalEnrollment.participant_id)).all())


def parse_duration_minutes(value) -> int | None:
    if value is None or value == "":
        return None
    raw = str(value)
    if isinstance(value, bool) or not raw.isascii() or not raw.isdigit() or len(raw) > 10:
        raise ValueError("La duración debe expresarse en minutos enteros, en intervalos de 5.")
    minutes = int(raw)
    if not 5 <= minutes <= 2147483647 or minutes % 5:
        raise ValueError("La duración debe ser positiva y un múltiplo de 5 minutos.")
    return minutes


def create_activity_session(db: Session, *, fiscal_year_id: int, program_id: int, activity_id: int,
                            session_date: date, actor_user_id: int, notes: str | None = None,
                            duration_minutes: int | str | None = None) -> CPActivitySession:
    _validate_actor(actor_user_id)
    minutes = parse_duration_minutes(duration_minutes)
    session_date = _date(session_date, "Fecha de actividad")
    require_fiscal_writable(db, fiscal_year_id, session_date)
    _activity_context(db, fiscal_year_id, program_id, activity_id)
    row = CPActivitySession(fiscal_year_id=fiscal_year_id, program_id=program_id,
                            activity_id=activity_id, session_date=session_date,
                            notes=_text(notes, "Observaciones", 500), created_by_user_id=actor_user_id,
                            duration_minutes=minutes)
    db.add(row)
    db.flush()
    return row


def writable_session(db: Session, session_id: int, *, target_fiscal_year_id: int | None = None) -> CPActivitySession:
    session = db.get(CPActivitySession, session_id)
    if session is None:
        raise ValueError("La sesión de actividad no existe.")
    original = (session.fiscal_year_id, session.program_id, session.session_date, session.activity_id)
    # Lock fiscal rows in ID order before locking a session, including moves of empty sessions.
    for year_id in sorted({session.fiscal_year_id, target_fiscal_year_id or session.fiscal_year_id}):
        require_fiscal_writable(db, year_id)
    session = db.scalar(select(CPActivitySession).where(CPActivitySession.session_id == session_id)
                         .with_hint(CPActivitySession, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
                         .execution_options(populate_existing=True))
    if session is None or (session.fiscal_year_id, session.program_id, session.session_date, session.activity_id) != original:
        raise ValueError("La sesión cambió. Recargue la página antes de guardar.")
    require_fiscal_writable(db, session.fiscal_year_id, session.session_date)
    return session


def set_session_attendance(db: Session, *, session_id: int, present_participant_ids: Iterable[int]) -> CPActivitySession:
    session = writable_session(db, session_id)
    _activity_context(db, session.fiscal_year_id, session.program_id, session.activity_id)
    submitted = tuple(present_participant_ids)
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in submitted):
        raise ValueError("Seleccione participantes válidos.")
    present = set(submitted)
    eligible = set(enrolled_participant_ids(db, session.fiscal_year_id, session.program_id, session.session_date))
    if not present.issubset(eligible):
        raise ValueError("Solo pueden asistir participantes con matrícula activa en el programa y fecha de la actividad.")
    existing = {row.participant_id: row for row in db.scalars(select(CPAttendance).where(CPAttendance.session_id == session_id)).all()}
    for participant_id in eligible | set(existing):
        row = existing.get(participant_id)
        if participant_id not in eligible:
            continue  # Disabled historical rows must not be erased by a normal form submission.
        if row is None:
            row = CPAttendance(session_id=session_id, participant_id=participant_id)
            db.add(row)
        row.is_present = participant_id in present
    db.flush()
    return session


def grade_period(db: Session, fiscal_year_id: int, report_year: int, report_month: int) -> tuple[date, date]:
    if isinstance(report_month, bool) or isinstance(report_year, bool):
        raise ValueError("Seleccione mes y año válidos.")
    try:
        first = date(report_year, report_month, 1)
        last = date(report_year, report_month, monthrange(report_year, report_month)[1])
    except (TypeError, ValueError):
        raise ValueError("Seleccione mes y año válidos.") from None
    year = db.get(CPFiscalYear, fiscal_year_id)
    if year is None:
        raise ValueError("El año fiscal no existe.")
    first, last = max(first, year.start_date), min(last, year.end_date)
    if first > last:
        raise ValueError("El mes del informe debe pertenecer al año fiscal.")
    return first, last


def create_grade_report(db: Session, *, fiscal_year_id: int, program_id: int,
                        report_year: int, report_month: int, actor_user_id: int,
                        notes: str | None = None) -> CPGradeReport:
    _validate_actor(actor_user_id)
    first, _ = grade_period(db, fiscal_year_id, report_year, report_month)
    require_fiscal_writable(db, fiscal_year_id, first)
    _program(db, program_id)
    existing = db.scalar(select(CPGradeReport.report_id).where(
        CPGradeReport.fiscal_year_id == fiscal_year_id, CPGradeReport.program_id == program_id,
        CPGradeReport.report_year == report_year, CPGradeReport.report_month == report_month,
    ))
    if existing is not None:
        raise ValueError("Ya existe un informe de notas para este programa, año fiscal y mes.")
    row = CPGradeReport(fiscal_year_id=fiscal_year_id, program_id=program_id,
                        report_year=report_year, report_month=report_month,
                        notes=_text(notes, "Observaciones", 500), created_by_user_id=actor_user_id)
    db.add(row)
    db.flush()
    return row


def _parse_grade(value: Any) -> float | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError("Las notas deben ser números entre 0 y 100.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Las notas deben ser números entre 0 y 100.") from None
    if not math.isfinite(number) or not 0 <= number <= 100:
        raise ValueError("Las notas deben estar entre 0 y 100.")
    return number


def grade_letter(average: float | None) -> str:
    if average is None:
        return ""
    for limit, letter in ((90, "A"), (80, "B"), (70, "C"), (60, "D")):
        if average >= limit:
            return letter
    return "F"


def grade_participant_ids(db: Session, report: CPGradeReport) -> list[int]:
    first, last = grade_period(db, report.fiscal_year_id, report.report_year, report.report_month)
    enrolled = enrolled_participant_ids(db, report.fiscal_year_id, report.program_id, first, min(last, date.today()))
    return [participant_id for participant_id in enrolled
            if (age := school_grade_age(db, participant_id, report.fiscal_year_id)) is not None and 0 <= age <= 21]


def school_grade_age(db: Session, participant_id: int, fiscal_year_id: int) -> int | None:
    snapshot = snapshot_for_participant(db, participant_id, fiscal_year_id)
    if not snapshot or not snapshot.get("fecha_nacimiento"):
        return None
    born = _date(snapshot["fecha_nacimiento"], "Fecha de nacimiento")
    today = date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def save_grade_item(db: Session, *, report_id: int, participant_id: int,
                    fields: Mapping[str, Any]) -> CPGradeItem:
    report = db.get(CPGradeReport, report_id)
    if report is None:
        raise ValueError("El informe de notas no existe.")
    first, last = grade_period(db, report.fiscal_year_id, report.report_year, report.report_month)
    require_fiscal_writable(db, report.fiscal_year_id, first)
    _program(db, report.program_id)
    if participant_id not in enrolled_participant_ids(db, report.fiscal_year_id, report.program_id, first, min(last, date.today())):
        raise ValueError("El participante no tiene matrícula activa durante el período del informe.")
    if set(fields) - {*GRADE_FIELDS, "grade_level", "is_content_room"}:
        raise ValueError("El formulario contiene campos de notas no permitidos.")
    row = db.get(CPGradeItem, (report_id, participant_id))
    if row is None:
        age = school_grade_age(db, participant_id, report.fiscal_year_id)
        if age is None or not 0 <= age <= 21:
            raise ValueError("El participante debe tener entre 0 y 21 años de edad actual para añadirlo al informe, como en Faro.")
    current = {field: getattr(row, field) if row is not None else None for field in GRADE_FIELDS}
    current.update(grade_level=row.grade_level if row else None, is_content_room=row.is_content_room if row else False)
    current.update(fields)
    level = _text(current["grade_level"], "Grado escolar", 20)
    if level is not None and level not in GRADE_OPTIONS:
        raise ValueError("Seleccione un grado escolar de EE, K o 1 a 12.")
    if not isinstance(current["is_content_room"], bool):
        raise ValueError("Salón contenido: valor inválido.")
    grades = {field: _parse_grade(current[field]) for field in GRADE_FIELDS}
    supplied = [value for value in grades.values() if value is not None]
    average = round(sum(supplied) / len(supplied), 2) if supplied else None
    if row is None:
        row = CPGradeItem(report_id=report_id, participant_id=participant_id)
        db.add(row)
    for field, value in grades.items():
        setattr(row, field, value)
    row.grade_level, row.is_content_room, row.average_grade = level, current["is_content_room"], average
    db.flush()
    return row


def has_participation_on_or_after(db: Session, participant_id: int, program_id: int,
                                 fiscal_year_id: int, on_date: date) -> bool:
    """Protect recorded participation from retroactive discharge, including grades."""
    on_date = _date(on_date, "Fecha de baja")
    attendance = db.scalar(select(CPAttendance.participant_id).join(
        CPActivitySession, CPActivitySession.session_id == CPAttendance.session_id
    ).where(
        CPAttendance.participant_id == participant_id, CPAttendance.is_present == True,  # noqa: E712
        CPActivitySession.program_id == program_id, CPActivitySession.fiscal_year_id == fiscal_year_id,
        CPActivitySession.session_date >= on_date,
    ).limit(1))
    if attendance is not None:
        return True
    # A grade has a month, not a specific day: protect the entire recorded month.
    return db.scalar(select(CPGradeItem.participant_id).join(
        CPGradeReport, CPGradeReport.report_id == CPGradeItem.report_id
    ).where(
        CPGradeItem.participant_id == participant_id,
        CPGradeReport.program_id == program_id, CPGradeReport.fiscal_year_id == fiscal_year_id,
        or_(CPGradeReport.report_year > on_date.year,
            (CPGradeReport.report_year == on_date.year) & (CPGradeReport.report_month >= on_date.month)),
    ).limit(1)) is not None
