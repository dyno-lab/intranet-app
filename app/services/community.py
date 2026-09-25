"""Creation services for the first Comunidad delivery.

Services validate and flush, but NEVER commit. The caller owns one transaction
and must roll it back on any failure (including IntegrityError / SQL deadlock).
Authorization is checked by the calling route before invoking these services.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from sqlalchemy import select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.models.community import CPProgram, CPFiscalYear, CPSequence, CPParticipant, CPParticipantProgram


_PROGRAM_CODE = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*")
_PHONE = re.compile(r"\(\d{3}\)-\d{3}-\d{4}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_TEXT_LIMITS = {
    "nombre": 150, "inicial": 12, "apellido_paterno": 150, "apellido_materno": 150,
    "genero": 10, "direccion_fisica": 500, "pueblo": 100, "vca": 5,
    "primera_vez": 5, "escolaridad_participante": 150, "composicion_familiar": 100,
    "relacion_familiar": 100, "estatus": 50, "grupo_familiar": 20,
    "fuente_ingreso_principal": 100, "rango_ingreso": 30, "telefono": 30, "email": 255,
}


def _text(value: Any, label: str, limit: int, *, required: bool = False) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label}: valor de texto inválido.")
    result = (value or "").strip()
    if required and not result:
        raise ValueError(f"{label} es requerido.")
    if len(result) > limit:
        raise ValueError(f"{label} permite hasta {limit} caracteres.")
    return result or None


def _date(value: Any, label: str) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"{label}: utiliza una fecha sin hora.")
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: fecha inválida.") from None


def _validate_actor(actor_user_id: int) -> None:
    if isinstance(actor_user_id, bool) or not isinstance(actor_user_id, int) or actor_user_id <= 0:
        raise ValueError("El empleado creador es requerido.")


def _active_programs(db: Session, program_ids: Iterable[int]) -> list[CPProgram]:
    submitted = tuple(program_ids)
    if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in submitted):
        raise ValueError("Selecciona programas válidos.")
    ids = set(submitted)
    programs = db.scalars(select(CPProgram).where(
        CPProgram.program_id.in_(ids), CPProgram.is_active == True,  # noqa: E712
    ).order_by(CPProgram.program_id)).all() if ids else []
    if len(programs) != len(ids):
        raise ValueError("Uno o más programas no existen o están inactivos.")
    return programs


def create_program(db: Session, code: str, name: str) -> CPProgram:
    code = _text(code, "Código de programa", 20, required=True)
    name = _text(name, "Nombre de programa", 150, required=True)
    if not _PROGRAM_CODE.fullmatch(code):
        raise ValueError("El código del programa debe comenzar con una letra y contener letras, números o guiones.")
    if db.scalar(select(CPProgram.program_id).where(CPProgram.code_key == code.upper())) is not None:
        raise ValueError("Ya existe un programa con ese código.")
    program = CPProgram(code=code, code_key=code.upper(), name=name)
    db.add(program)
    db.flush()
    return program


def create_fiscal_year(db: Session, code: str, name: str, start_date: date, end_date: date) -> CPFiscalYear:
    code = _text(code, "Código de año fiscal", 50, required=True).upper()
    name = _text(name, "Nombre de año fiscal", 150, required=True)
    start_date = _date(start_date, "Fecha de inicio")
    end_date = _date(end_date, "Fecha de fin")
    if end_date < start_date:
        raise ValueError("La fecha de fin no puede ser anterior a la fecha de inicio.")
    if db.scalar(select(CPFiscalYear.fiscal_year_id).where(CPFiscalYear.code == code)) is not None:
        raise ValueError("Ya existe un año fiscal con ese código.")
    fiscal_year = CPFiscalYear(code=code, name=name, start_date=start_date, end_date=end_date)
    db.add(fiscal_year)
    db.flush()
    return fiscal_year


def _sequence_lock_statement(exp_year: int):
    # UPDLOCK serializes increments; HOLDLOCK retains the key-range lock when
    # this year's row does not exist yet. Both are held until caller commit.
    return (
        select(CPSequence)
        .where(CPSequence.exp_year == exp_year)
        .with_hint(CPSequence, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    )


def _allocate_sequence(db: Session, exp_year: int) -> int:
    dialect = db.get_bind().dialect.name
    if dialect == "mssql":
        row = db.scalar(_sequence_lock_statement(exp_year))
        if row is None:
            row = CPSequence(exp_year=exp_year, last_value=0)
            db.add(row)
        if row.last_value >= 9999:
            raise ValueError("Se agotó la numeración de cuatro dígitos para este año de expediente.")
        row.last_value += 1
        db.flush()
        return row.last_value
    if dialect == "sqlite":
        # Real SQLite implementation for isolated tests/local development.
        # The insert obtains a write lock before the increment; no MAX + 1.
        db.execute(sqlite_insert(CPSequence).values(exp_year=exp_year, last_value=0).on_conflict_do_nothing(index_elements=["exp_year"]))
        value = db.scalar(
            update(CPSequence).where(CPSequence.exp_year == exp_year, CPSequence.last_value < 9999)
            .values(last_value=CPSequence.last_value + 1).returning(CPSequence.last_value)
        )
        if value is None:
            raise ValueError("Se agotó la numeración de cuatro dígitos para este año de expediente.")
        return value
    raise RuntimeError("La numeración de Comunidad requiere SQL Server o SQLite de pruebas.")


def _normalized_participant_fields(fields: Mapping[str, Any]) -> dict[str, Any]:
    unknown = set(fields) - set(_TEXT_LIMITS) - {"fecha_nacimiento", "is_head_of_household"}
    if unknown:
        raise ValueError("El formulario incluye campos de expediente no permitidos.")
    values = {key: _text(fields.get(key), key, limit, required=key in {"nombre", "apellido_paterno", "genero"}) for key, limit in _TEXT_LIMITS.items()}
    values["genero"] = values["genero"].upper()
    if values["genero"] not in {"F", "M"}:
        raise ValueError("Selecciona el género del participante (F o M), como en Faro.")
    birth_date = fields.get("fecha_nacimiento")
    values["fecha_nacimiento"] = _date(birth_date, "Fecha de nacimiento") if birth_date else None
    if values["fecha_nacimiento"] and values["fecha_nacimiento"] > date.today():
        raise ValueError("La fecha de nacimiento no puede estar en el futuro.")
    head = fields.get("is_head_of_household", False)
    if not isinstance(head, bool):
        raise ValueError("Jefatura de familia: valor inválido.")
    values["is_head_of_household"] = head
    for key in ("vca", "primera_vez"):
        if values[key]:
            values[key] = values[key].upper()
            if values[key] not in {"SI", "NO"}:
                raise ValueError(f"{key}: selecciona Sí o No.")
    if values["telefono"] and not _PHONE.fullmatch(values["telefono"]):
        raise ValueError("El teléfono debe usar el formato (XXX)-XXX-XXXX, como en Faro.")
    if values["email"] and not _EMAIL.fullmatch(values["email"]):
        raise ValueError("El correo electrónico no es válido.")
    return values


def create_participant(
    db: Session, *, actor_user_id: int, exp_year: int,
    program_ids: Iterable[int], fields: Mapping[str, Any],
) -> CPParticipant:
    if isinstance(exp_year, bool) or not isinstance(exp_year, int) or not 1000 <= exp_year <= 9999:
        raise ValueError("Selecciona un año de expediente de cuatro dígitos.")
    _validate_actor(actor_user_id)
    values = _normalized_participant_fields(fields)
    programs = _active_programs(db, program_ids)

    sequence = _allocate_sequence(db, exp_year)
    participant = CPParticipant(
        exp_year=exp_year, exp_sequence=sequence, expediente_num=f"CP-{exp_year}-{sequence:04d}",
        created_by_user_id=actor_user_id, **values,
    )
    db.add(participant)
    db.flush()
    db.add_all([
        CPParticipantProgram(
            participant_id=participant.participant_id, program_id=program.program_id,
            record_number=f"CP-{exp_year}-{program.code}-{sequence:04d}", created_by_user_id=actor_user_id,
        )
        for program in programs
    ])
    db.flush()
    return participant


def _participant_for_update(db: Session, participant_id: int) -> CPParticipant:
    if isinstance(participant_id, bool) or not isinstance(participant_id, int) or participant_id <= 0:
        raise ValueError("Selecciona un expediente válido de Comunidad.")
    participant = db.scalar(
        select(CPParticipant).where(CPParticipant.participant_id == participant_id)
        .with_hint(CPParticipant, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
        .execution_options(populate_existing=True)
    )
    if participant is None:
        raise ValueError("El expediente de Comunidad no existe.")
    return participant


def update_participant(
    db: Session, *, participant_id: int, fields: Mapping[str, Any],
) -> CPParticipant:
    """Update personal fields; caller enforces Supervisor/Admin authorization.

    Omitted personal fields retain their stored values. Identity, numbering,
    creator and program links cannot be supplied through this operation.
    """
    participant = _participant_for_update(db, participant_id)
    current = {
        field: getattr(participant, field)
        for field in (*_TEXT_LIMITS, "fecha_nacimiento", "is_head_of_household")
    }
    values = _normalized_participant_fields({**current, **fields})
    # Validate the entire submission before changing any mapped attributes.
    for field, value in values.items():
        setattr(participant, field, value)
    db.flush()
    return participant


def associate_participant_programs(
    db: Session, *, participant_id: int, actor_user_id: int, program_ids: Iterable[int],
) -> CPParticipant:
    """Add only missing permanent program links to an existing Community record.

    The route must authorize each requested program before calling. Fiscal-year
    synchronization and demographic editing are separate operations. The SQL
    Server participant lock serializes concurrent association of this record;
    it is retained until the caller commits or rolls back the transaction.
    """
    _validate_actor(actor_user_id)
    participant = _participant_for_update(db, participant_id)
    programs = _active_programs(db, program_ids)
    existing_ids = set(db.scalars(
        select(CPParticipantProgram.program_id)
        .where(CPParticipantProgram.participant_id == participant_id)
    ).all())
    db.add_all([
        CPParticipantProgram(
            participant_id=participant_id,
            program_id=program.program_id,
            record_number=f"CP-{participant.exp_year}-{program.code}-{participant.exp_sequence:04d}",
            created_by_user_id=actor_user_id,
        )
        for program in programs if program.program_id not in existing_ids
    ])
    db.flush()
    return participant
