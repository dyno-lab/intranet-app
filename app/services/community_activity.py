"""Activity/ADM services validate and flush; callers authorize and own the transaction.

No service commits, deletes configuration, or changes an activity's permanent identity.
Fiscal deactivation affects only that year's availability, preserving report joins.
"""
from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.community import CPFiscalYear, CPProgram
from app.models.community_activity import CPActivity, CPFiscalActivity, CPADMServiceActivity, CPADMServiceType


def _text(value: str | None, label: str, limit: int, *, required: bool = True) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label}: valor inválido.")
    clean = (value or "").strip()
    if required and not clean:
        raise ValueError(f"{label} es requerido.")
    if len(clean) > limit:
        raise ValueError(f"{label} permite hasta {limit} caracteres.")
    return clean or None


def _locked_fiscal_year(db: Session, fiscal_year_id: int) -> CPFiscalYear | None:
    statement = select(CPFiscalYear).where(CPFiscalYear.fiscal_year_id == fiscal_year_id)
    # Retain the year-row lock until the caller commits, including configuration copies.
    if db.get_bind().dialect.name == "mssql":
        statement = statement.with_hint(CPFiscalYear, "WITH (UPDLOCK, HOLDLOCK)", dialect_name="mssql")
    return db.scalar(statement.execution_options(populate_existing=True))


def require_open_fiscal_year(db: Session, fiscal_year_id: int) -> CPFiscalYear:
    year = _locked_fiscal_year(db, fiscal_year_id)
    if year is None or not year.is_active:
        raise ValueError("Año fiscal no disponible.")
    if year.status != "active":
        raise ValueError("El año fiscal está cerrado. Debe reabrirlo para modificar su configuración.")
    return year


def _program(db: Session, program_id: int) -> CPProgram:
    program = db.get(CPProgram, program_id)
    if program is None or not program.is_active:
        raise ValueError("Programa no disponible.")
    return program


def _activity(db: Session, activity_id: int, program_id: int) -> CPActivity:
    activity = db.get(CPActivity, activity_id)
    if activity is None or activity.program_id != program_id:
        raise ValueError("La actividad no pertenece al programa seleccionado.")
    return activity


def create_activity(db: Session, *, program_id: int, code: str, description: str | None,
                    fiscal_year_ids: Iterable[int]) -> CPActivity:
    _program(db, program_id)
    years = sorted(set(fiscal_year_ids))
    if not years:
        raise ValueError("Seleccione al menos un año fiscal abierto para la actividad.")
    for year_id in years:
        require_open_fiscal_year(db, year_id)
    code = _text(code, "Código de actividad", 50)
    key = code.upper()
    if len(key) > 50:
        raise ValueError("El código normalizado de actividad permite hasta 50 caracteres.")
    description = _text(description, "Descripción", 255, required=False)
    if db.scalar(select(CPActivity.activity_id).where(CPActivity.program_id == program_id, CPActivity.code_key == key)) is not None:
        raise ValueError("Ya existe una actividad con ese código en el programa. Asóciela al año fiscal.")
    activity = CPActivity(program_id=program_id, code=code, code_key=key, description=description)
    db.add(activity)
    db.flush()
    db.add_all([CPFiscalActivity(activity_id=activity.activity_id, fiscal_year_id=year_id,
                                program_id=program_id) for year_id in years])
    db.flush()
    return activity


def associate_activity(db: Session, *, activity_id: int, program_id: int,
                       fiscal_year_id: int) -> CPFiscalActivity:
    require_open_fiscal_year(db, fiscal_year_id)
    _program(db, program_id)
    activity = _activity(db, activity_id, program_id)
    if not activity.is_active:
        raise ValueError("La actividad no está disponible.")
    association = db.get(CPFiscalActivity, (activity_id, fiscal_year_id))
    if association is None:
        association = CPFiscalActivity(activity_id=activity_id, fiscal_year_id=fiscal_year_id, program_id=program_id)
        db.add(association)
    else:
        association.is_active = True
    db.flush()
    return association


def set_activity_active(db: Session, *, activity_id: int, program_id: int,
                        fiscal_year_id: int, active: bool) -> CPFiscalActivity:
    require_open_fiscal_year(db, fiscal_year_id)
    _program(db, program_id)
    activity = _activity(db, activity_id, program_id)
    association = db.get(CPFiscalActivity, (activity_id, fiscal_year_id))
    if association is None:
        raise ValueError("La actividad no está asociada al año fiscal.")
    if active and not activity.is_active:
        raise ValueError("La actividad no está disponible.")
    association.is_active = bool(active)
    db.flush()
    return association


def _service_name(name: str) -> tuple[str, str]:
    name = _text(name, "Nombre del tipo de servicio", 150)
    key = name.upper()
    if len(key) > 150:
        raise ValueError("El nombre normalizado permite hasta 150 caracteres.")
    return name, key


def _sort_order(sort_order: int) -> int:
    if isinstance(sort_order, bool) or not isinstance(sort_order, int) or not 0 <= sort_order <= 9999:
        raise ValueError("El orden debe ser un número entero entre 0 y 9999.")
    return sort_order


def _has_sessions(db: Session, *, fiscal_year_id: int, program_id: int,
                  activity_ids: Iterable[int]) -> bool:
    # Local import keeps the configuration model independent of operational services.
    from app.models.community_operations import CPActivitySession

    ids = tuple(activity_ids)
    if not ids:
        return False
    return db.scalar(select(CPActivitySession.session_id).where(
        CPActivitySession.fiscal_year_id == fiscal_year_id,
        CPActivitySession.program_id == program_id,
        CPActivitySession.activity_id.in_(ids),
    ).limit(1)) is not None


def create_adm_service_type(db: Session, *, program_id: int, fiscal_year_id: int,
                            name: str, sort_order: int = 0) -> CPADMServiceType:
    require_open_fiscal_year(db, fiscal_year_id)
    _program(db, program_id)
    name, key = _service_name(name)
    order = _sort_order(sort_order)
    if db.scalar(select(CPADMServiceType.adm_service_type_id).where(
        CPADMServiceType.program_id == program_id, CPADMServiceType.fiscal_year_id == fiscal_year_id,
        CPADMServiceType.name_key == key,
    )) is not None:
        raise ValueError("Ya existe ese tipo de servicio en el programa y año fiscal.")
    service = CPADMServiceType(program_id=program_id, fiscal_year_id=fiscal_year_id,
                               name=name, name_key=key, sort_order=order)
    db.add(service)
    db.flush()
    return service


def _service(db: Session, service_type_id: int, program_id: int, fiscal_year_id: int) -> CPADMServiceType:
    require_open_fiscal_year(db, fiscal_year_id)
    _program(db, program_id)
    service = db.get(CPADMServiceType, service_type_id)
    if service is None or service.program_id != program_id or service.fiscal_year_id != fiscal_year_id:
        raise ValueError("Tipo de servicio no disponible en el programa y año fiscal seleccionados.")
    return service


def update_adm_service_type(db: Session, *, service_type_id: int, program_id: int,
                            fiscal_year_id: int, name: str, sort_order: int, active: bool) -> CPADMServiceType:
    service = _service(db, service_type_id, program_id, fiscal_year_id)
    name, key = _service_name(name)
    order = _sort_order(sort_order)
    duplicate = db.scalar(select(CPADMServiceType.adm_service_type_id).where(
        CPADMServiceType.program_id == program_id, CPADMServiceType.fiscal_year_id == fiscal_year_id,
        CPADMServiceType.name_key == key, CPADMServiceType.adm_service_type_id != service_type_id,
    ))
    if duplicate is not None:
        raise ValueError("Ya existe ese tipo de servicio en el programa y año fiscal.")
    if name != service.name or order != service.sort_order:
        activities = db.scalars(select(CPADMServiceActivity.activity_id).where(
            CPADMServiceActivity.adm_service_type_id == service_type_id,
            CPADMServiceActivity.is_active == True,  # noqa: E712
        )).all()
        if _has_sessions(db, fiscal_year_id=fiscal_year_id, program_id=program_id, activity_ids=activities):
            raise ValueError("El tipo de servicio tiene actividades registradas. Su nombre y orden se conservan para proteger los reportes históricos.")
    service.name, service.name_key, service.sort_order, service.is_active = name, key, order, bool(active)
    db.flush()
    return service


def assign_adm_activity(db: Session, *, service_type_id: int, program_id: int,
                        fiscal_year_id: int, activity_id: int) -> CPADMServiceActivity:
    service = _service(db, service_type_id, program_id, fiscal_year_id)
    if not service.is_active:
        raise ValueError("Reactive el tipo de servicio antes de asociar actividades.")
    activity = _activity(db, activity_id, program_id)
    fiscal_activity = db.get(CPFiscalActivity, (activity_id, fiscal_year_id))
    if not activity.is_active or fiscal_activity is None or not fiscal_activity.is_active:
        raise ValueError("La actividad debe estar activa y asociada al mismo programa y año fiscal.")
    existing = db.scalar(select(CPADMServiceActivity).where(
        CPADMServiceActivity.fiscal_year_id == fiscal_year_id,
        CPADMServiceActivity.activity_id == activity_id, CPADMServiceActivity.is_active == True,  # noqa: E712
    ))
    if existing is not None:
        if existing.adm_service_type_id == service_type_id:
            return existing
        raise ValueError("La actividad ya está asociada a otro tipo de servicio ADM. Quite esa asociación primero.")
    if _has_sessions(db, fiscal_year_id=fiscal_year_id, program_id=program_id, activity_ids=[activity_id]):
        raise ValueError("La actividad tiene sesiones registradas. Su clasificación ADM se conserva para proteger los reportes históricos.")
    mapping = db.scalar(select(CPADMServiceActivity).where(
        CPADMServiceActivity.adm_service_type_id == service_type_id, CPADMServiceActivity.activity_id == activity_id,
    ))
    if mapping is None:
        mapping = CPADMServiceActivity(adm_service_type_id=service_type_id, activity_id=activity_id,
                                        fiscal_year_id=fiscal_year_id, program_id=program_id)
        db.add(mapping)
    else:
        mapping.is_active = True
    db.flush()
    return mapping


def unassign_adm_activity(db: Session, *, service_type_id: int, program_id: int,
                          fiscal_year_id: int, activity_id: int) -> None:
    _service(db, service_type_id, program_id, fiscal_year_id)
    mapping = db.scalar(select(CPADMServiceActivity).where(
        CPADMServiceActivity.adm_service_type_id == service_type_id,
        CPADMServiceActivity.activity_id == activity_id,
    ))
    if mapping is None:
        raise ValueError("Asociación ADM no encontrada.")
    if mapping.is_active and _has_sessions(db, fiscal_year_id=fiscal_year_id, program_id=program_id, activity_ids=[activity_id]):
        raise ValueError("La actividad tiene sesiones registradas. No puede quitar su clasificación ADM histórica.")
    mapping.is_active = False
    db.flush()


def copy_fiscal_configuration(db: Session, source_fiscal_year_id: int, target_fiscal_year_id: int) -> dict[str, int]:
    """Copy configuration into an empty open year; no participants or transactions.

    The source may be closed. A nonempty destination is rejected rather than merged
    or overwritten. The caller must commit or roll back the complete operation.
    """
    if source_fiscal_year_id == target_fiscal_year_id:
        raise ValueError("Seleccione un año fiscal de destino distinto al de origen.")
    # Lock both rows in ID order so an active source cannot change during copying.
    years = {year_id: _locked_fiscal_year(db, year_id)
             for year_id in sorted((source_fiscal_year_id, target_fiscal_year_id))}
    if years[source_fiscal_year_id] is None:
        raise ValueError("Año fiscal de origen no encontrado.")
    require_open_fiscal_year(db, target_fiscal_year_id)
    for model in (CPFiscalActivity, CPADMServiceType):
        if db.scalar(select(model).where(model.fiscal_year_id == target_fiscal_year_id).limit(1)) is not None:
            raise ValueError("El año fiscal de destino ya tiene configuración. La copia requiere un año sin configuración.")
    activities = db.scalars(select(CPFiscalActivity).where(CPFiscalActivity.fiscal_year_id == source_fiscal_year_id)).all()
    services = db.scalars(select(CPADMServiceType).where(CPADMServiceType.fiscal_year_id == source_fiscal_year_id)).all()
    mappings = db.scalars(select(CPADMServiceActivity).where(CPADMServiceActivity.fiscal_year_id == source_fiscal_year_id)).all()
    db.add_all([CPFiscalActivity(activity_id=row.activity_id, fiscal_year_id=target_fiscal_year_id,
                                program_id=row.program_id, is_active=row.is_active) for row in activities])
    db.flush()
    service_ids: dict[int, int] = {}
    for row in services:
        clone = CPADMServiceType(fiscal_year_id=target_fiscal_year_id, program_id=row.program_id,
                                 name=row.name, name_key=row.name_key, sort_order=row.sort_order, is_active=row.is_active)
        db.add(clone)
        db.flush()
        service_ids[row.adm_service_type_id] = clone.adm_service_type_id
    db.add_all([CPADMServiceActivity(adm_service_type_id=service_ids[row.adm_service_type_id],
                                    activity_id=row.activity_id, fiscal_year_id=target_fiscal_year_id,
                                    program_id=row.program_id, is_active=row.is_active) for row in mappings])
    db.flush()
    return {"activities": len(activities), "service_types": len(services), "mappings": len(mappings)}
