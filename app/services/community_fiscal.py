"""Fiscal services flush only; callers authorize, commit, and roll back failures."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
import json
from typing import Iterable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.community import CPFiscalYear, CPParticipant, CPParticipantProgram, CPProgram, _utcnow
from app.models.community_fiscal import CPFiscalEnrollment, CPFiscalParticipant, CPFiscalState, CPEnrollmentPeriod
from app.services.community import _date, _text, _validate_actor


SNAPSHOT_FIELDS = tuple(column.key for column in CPParticipant.__table__.columns
                        if column.key not in {"created_at", "updated_at", "created_by_user_id"})


def _fiscal_year(db: Session, fiscal_year_id: int) -> CPFiscalYear:
    # Serializes a fiscal mutation with closing/freezing the year, and concurrent
    # enrollment interval changes. The caller holds this lock until commit.
    year = db.scalar(select(CPFiscalYear).where(CPFiscalYear.fiscal_year_id == fiscal_year_id)
                     .with_hint(CPFiscalYear, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
                     .execution_options(populate_existing=True))
    if year is None or not year.is_active:
        raise ValueError("El año fiscal no existe o no está disponible.")
    return year


def require_fiscal_writable(db: Session, fy_id: int, event_date: date | None = None,
                            snapshots: bool = False) -> CPFiscalYear:
    year = _fiscal_year(db, fy_id)
    if year.status != "active":
        raise ValueError("El año fiscal está cerrado. Debe reabrirse antes de modificarlo.")
    state = db.get(CPFiscalState, fy_id, populate_existing=True)
    if snapshots and state and state.snapshots_frozen:
        raise ValueError("Los datos de participantes están congelados. Descongélelos antes de sincronizar.")
    if event_date is not None:
        event_date = _date(event_date, "Fecha efectiva")
        if event_date > date.today():
            raise ValueError("No se permiten fechas futuras en las operaciones del año fiscal.")
        if not year.start_date <= event_date <= year.end_date:
            raise ValueError("La fecha debe estar dentro del inicio y fin del año fiscal.")
        if state and state.locked_through and event_date <= state.locked_through:
            raise ValueError(f"Los períodos están cerrados hasta {state.locked_through:%d/%m/%Y}.")
    return year


def _state(db: Session, fiscal_year_id: int, actor_user_id: int) -> CPFiscalState:
    _validate_actor(actor_user_id)
    state = db.get(CPFiscalState, fiscal_year_id)
    if state is None:
        state = CPFiscalState(fiscal_year_id=fiscal_year_id, updated_by_user_id=actor_user_id)
        db.add(state)
    state.updated_by_user_id = actor_user_id
    state.updated_at = _utcnow()
    return state


def set_snapshot_freeze(db: Session, fiscal_year_id: int, *, frozen: bool, actor_user_id: int) -> CPFiscalState:
    year = _fiscal_year(db, fiscal_year_id)
    if not frozen and year.status != "active":
        raise ValueError("Reabra el año fiscal antes de descongelar sus datos.")
    state = _state(db, fiscal_year_id, actor_user_id)
    state.snapshots_frozen = frozen
    db.flush()
    return state


def set_fiscal_status(db: Session, fiscal_year_id: int, *, closed: bool, actor_user_id: int) -> CPFiscalYear:
    year = _fiscal_year(db, fiscal_year_id)
    state = _state(db, fiscal_year_id, actor_user_id)
    year.status = "closed" if closed else "active"
    if closed:
        state.snapshots_frozen = True
    # Reopening deliberately retains both demographic freeze and month locks.
    db.flush()
    return year


def set_fiscal_lock(db: Session, fiscal_year_id: int, *, locked_through: date | None,
                    actor_user_id: int) -> CPFiscalState:
    year = require_fiscal_writable(db, fiscal_year_id)
    if locked_through is not None:
        locked_through = _date(locked_through, "Cierre mensual")
        last_day = date(locked_through.year, locked_through.month,
                        monthrange(locked_through.year, locked_through.month)[1])
        if locked_through != min(last_day, year.end_date):
            raise ValueError("El cierre debe ser el último día del mes o el fin del año fiscal.")
        if not year.start_date <= locked_through <= year.end_date:
            raise ValueError("El período de cierre debe pertenecer al año fiscal.")
        if locked_through > date.today():
            raise ValueError("No se pueden cerrar períodos con fechas futuras.")
    state = _state(db, fiscal_year_id, actor_user_id)
    state.locked_through = locked_through
    db.flush()
    return state


def build_participant_snapshot(db: Session, participant: CPParticipant) -> dict:
    from app.models.community_catalog import CPProfileField, CPProfileValue

    values = {}
    for field in SNAPSHOT_FIELDS:
        value = getattr(participant, field)
        values[field] = value.isoformat() if isinstance(value, (date, datetime)) else value
    # Include inactive definitions too: disabling a field never erases history.
    profile = db.execute(select(CPProfileField, CPProfileValue).join(
        CPProfileValue, CPProfileValue.field_id == CPProfileField.field_id
    ).where(CPProfileValue.participant_id == participant.participant_id)).all()
    values["profile_fields"] = {field.field_key: {"label": field.label, "value": value.value}
                                 for field, value in profile}
    return values


def snapshot_for_participant(db: Session, participant_id: int, fiscal_year_id: int) -> dict | None:
    row = db.get(CPFiscalParticipant, (participant_id, fiscal_year_id))
    return json.loads(row.snapshot_json) if row else None


def sync_participants(db: Session, fiscal_year_id: int, participant_ids: Iterable[int],
                      *, actor_user_id: int) -> int:
    require_fiscal_writable(db, fiscal_year_id, snapshots=True)
    _validate_actor(actor_user_id)
    ids = sorted(set(participant_ids))
    if not ids:
        raise ValueError("Seleccione participantes para sincronizar.")
    participants = db.scalars(select(CPParticipant).where(CPParticipant.participant_id.in_(ids))
                              .order_by(CPParticipant.participant_id)
                              .with_hint(CPParticipant, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
                              .execution_options(populate_existing=True)).all()
    if len(participants) != len(ids):
        raise ValueError("Uno o más expedientes seleccionados no existen.")
    for participant in participants:
        snapshot_json = json.dumps(build_participant_snapshot(db, participant), ensure_ascii=False, sort_keys=True)
        row = db.get(CPFiscalParticipant, (participant.participant_id, fiscal_year_id))
        if row is None:
            row = CPFiscalParticipant(participant_id=participant.participant_id, fiscal_year_id=fiscal_year_id)
            db.add(row)
        row.snapshot_json = snapshot_json
        row.updated_by_user_id = actor_user_id
        row.updated_at = _utcnow()
    db.flush()
    return len(participants)


def _enrollment(db: Session, participant_id: int, program_id: int, fiscal_year_id: int) -> CPFiscalEnrollment | None:
    return db.scalar(select(CPFiscalEnrollment).where(
        CPFiscalEnrollment.participant_id == participant_id,
        CPFiscalEnrollment.program_id == program_id,
        CPFiscalEnrollment.fiscal_year_id == fiscal_year_id,
    ))


def is_enrolled_on(db: Session, participant_id: int, program_id: int,
                   fiscal_year_id: int, on_date: date) -> bool:
    # This read intentionally ignores today's enrollment status and year locks.
    # Historical attendance remains valid after discharge or fiscal closure.
    return db.scalar(select(CPEnrollmentPeriod.period_id).join(
        CPFiscalEnrollment, CPFiscalEnrollment.enrollment_id == CPEnrollmentPeriod.enrollment_id
    ).join(CPFiscalYear, CPFiscalYear.fiscal_year_id == CPFiscalEnrollment.fiscal_year_id).where(
        CPFiscalEnrollment.participant_id == participant_id,
        CPFiscalEnrollment.program_id == program_id,
        CPFiscalEnrollment.fiscal_year_id == fiscal_year_id,
        CPFiscalYear.start_date <= on_date, CPFiscalYear.end_date >= on_date,
        CPEnrollmentPeriod.start_date <= on_date,
        or_(CPEnrollmentPeriod.end_date.is_(None), CPEnrollmentPeriod.end_date > on_date),
    ).limit(1)) is not None


def _membership_context(db: Session, participant_id: int, program_id: int, fiscal_year_id: int,
                         event_date: date, actor_user_id: int) -> None:
    _validate_actor(actor_user_id)
    require_fiscal_writable(db, fiscal_year_id, event_date)
    program = db.get(CPProgram, program_id)
    if program is None or not program.is_active:
        raise ValueError("El programa no existe o está inactivo.")
    if db.get(CPParticipantProgram, (participant_id, program_id)) is None:
        raise ValueError("Primero asocie el expediente al programa.")
    if db.get(CPFiscalParticipant, (participant_id, fiscal_year_id)) is None:
        raise ValueError("Un Supervisor o Administrador debe sincronizar el expediente al año fiscal antes del alta.")


def _period(db: Session, enrollment: CPFiscalEnrollment, *, start_date: date, actor_user_id: int,
            reason: str, observation: str | None) -> CPEnrollmentPeriod:
    period = CPEnrollmentPeriod(enrollment_id=enrollment.enrollment_id, start_date=start_date,
                                reason=_text(reason, "Motivo", 250, required=True),
                                observation=_text(observation, "Observación", 1000),
                                created_by_user_id=actor_user_id)
    db.add(period)
    db.flush()
    return period


def enroll_participant(db: Session, *, participant_id: int, program_id: int, fiscal_year_id: int,
                        start_date: date, actor_user_id: int, reason: str = "Alta inicial",
                        observation: str | None = None) -> CPFiscalEnrollment:
    start_date = _date(start_date, "Fecha de alta")
    _membership_context(db, participant_id, program_id, fiscal_year_id, start_date, actor_user_id)
    if _enrollment(db, participant_id, program_id, fiscal_year_id) is not None:
        raise ValueError("Ya existe una matrícula en este programa y año fiscal. Utilice Reactivar si está de baja.")
    enrollment = CPFiscalEnrollment(participant_id=participant_id, program_id=program_id,
                                    fiscal_year_id=fiscal_year_id, created_by_user_id=actor_user_id)
    db.add(enrollment)
    db.flush()
    _period(db, enrollment, start_date=start_date, actor_user_id=actor_user_id,
            reason=reason, observation=observation)
    return enrollment


def discharge_participant(db: Session, *, participant_id: int, program_id: int, fiscal_year_id: int,
                          end_date: date, actor_user_id: int, reason: str,
                          observation: str | None = None) -> CPEnrollmentPeriod:
    end_date = _date(end_date, "Fecha de baja")
    _membership_context(db, participant_id, program_id, fiscal_year_id, end_date, actor_user_id)
    enrollment = _enrollment(db, participant_id, program_id, fiscal_year_id)
    period = db.scalar(select(CPEnrollmentPeriod).where(
        CPEnrollmentPeriod.enrollment_id == enrollment.enrollment_id,
        CPEnrollmentPeriod.end_date.is_(None),
    )) if enrollment else None
    if period is None:
        raise ValueError("El participante no tiene un período activo en este programa y año fiscal.")
    if end_date < period.start_date:
        raise ValueError("La baja no puede ser anterior al inicio del período activo.")
    _require_discharge_without_records(db, participant_id, program_id, fiscal_year_id, end_date)
    period.end_date = end_date
    period.end_reason = _text(reason, "Motivo de baja", 250, required=True)
    period.end_observation = _text(observation, "Observación", 1000)
    period.ended_by_user_id = actor_user_id
    period.ended_at = _utcnow()
    db.flush()
    return period


def reactivate_participant(db: Session, *, participant_id: int, program_id: int, fiscal_year_id: int,
                           start_date: date, actor_user_id: int, reason: str,
                           observation: str | None = None) -> CPEnrollmentPeriod:
    start_date = _date(start_date, "Fecha de reactivación")
    _membership_context(db, participant_id, program_id, fiscal_year_id, start_date, actor_user_id)
    enrollment = _enrollment(db, participant_id, program_id, fiscal_year_id)
    if enrollment is None:
        raise ValueError("No existe matrícula previa. Registre primero el alta en el programa y año fiscal.")
    periods = db.scalars(select(CPEnrollmentPeriod).where(
        CPEnrollmentPeriod.enrollment_id == enrollment.enrollment_id,
    ).order_by(CPEnrollmentPeriod.start_date)).all()
    if any(period.end_date is None for period in periods):
        raise ValueError("El participante ya está activo en este programa y año fiscal.")
    if periods and (start_date < periods[-1].end_date or start_date <= periods[-1].start_date):
        raise ValueError("La reactivación debe comenzar después del inicio anterior y no antes de la última baja.")
    return _period(db, enrollment, start_date=start_date, actor_user_id=actor_user_id,
                   reason=reason, observation=observation)


def _require_discharge_without_records(db: Session, participant_id: int, program_id: int,
                                       fiscal_year_id: int, end_date: date) -> None:
    """Operational implementation is supplied with the attendance model contract."""
    # Membership history is not deleted or rewritten. Existing attendance must
    # never be placed outside its valid interval by a retroactive discharge.
    from app.services.community_operations import has_participation_on_or_after
    if has_participation_on_or_after(db, participant_id, program_id, fiscal_year_id, end_date):
        raise ValueError("Existen asistencias o notas desde esa fecha. Revise los registros antes de aplicar una baja retroactiva.")
