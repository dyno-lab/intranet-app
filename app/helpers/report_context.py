from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.residential_scope import has_global_residential_access
from app.helpers.reports import normalize_text
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.user import User

MIN_REPORTING_YEAR = 2026


@dataclass(frozen=True)
class ReportingResidentialOption:
    residential_id: int
    code: str
    name: str
    municipality: str
    rq_code: str

    @property
    def user_id(self) -> int:
        """Negative scope token that cannot collide with a legacy user ID."""
        return -self.residential_id

    @property
    def username(self) -> str:
        """Compatibility label for report templates migrated from user selectors."""
        return self.name

    @property
    def residential(self) -> ReportingResidentialOption:
        return self


def reporting_residential_option(residential: Residential | None) -> ReportingResidentialOption | None:
    if residential is None:
        return None
    return ReportingResidentialOption(
        residential_id=residential.residential_id,
        code=normalize_text(residential.code),
        name=normalize_text(residential.name),
        municipality=normalize_text(residential.municipality),
        rq_code=normalize_text(residential.rq_code),
    )


USER_RESIDENTIAL = {
    "AC": "Aristides Chavier",
    "PJR": "Pedro J. Rosaly",
    "JPDL": "Juan Ponce de León",
    "ERA": "Ernesto Ramos Antonini",
    "RLN": "Rafael Lopez Nussa",
    "LC": "La Ceiba",
    "LS": "Leónardo Santiago",
    "VDP": "Villa del Parque",
    "BDM": "Brisas del Mar",
    "BV": "Bella Vista",
    "VDG": "Valles de Guayama",
    "JDG": "Jardines de Guamani",
    "FC": "Fernando Calimano",
    "SAC": "San Antonio Carioca",
    "EC": "El Carmen",
    "MH": "Manuel Hernandez Rosa",
    "RH": "Rafael Hernandez",
    "CL": "Columbus Landing",
    "ADMIN": "Global",
}

RESIDENTIAL_MUNICIPALITY = {
    "ARISTIDES CHAVIER": "Ponce",
    "PEDRO J. ROSALY": "Ponce",
    "JUAN PONCE DE LEÓN": "Ponce",
    "ERNESTO RAMOS ANTONINI": "Ponce",
    "RAFAEL LOPEZ NUSSA": "Ponce",
    "LA CEIBA": "Ponce",
    "LEÓNARDO SANTIAGO": "Juana Díaz",
    "VILLA DEL PARQUE": "Juana Díaz",
    "BRISAS DEL MAR": "Salinas",
    "BELLA VISTA": "Salinas",
    "VALLES DE GUAYAMA": "Guayama",
    "JARDINES DE GUAMANI": "Guayama",
    "FERNANDO CALIMANO": "Guayama",
    "SAN ANTONIO CARIOCA": "Guayama",
    "EL CARMEN": "Mayagüez",
    "MANUEL HERNANDEZ ROSA": "Mayagüez",
    "RAFAEL HERNANDEZ": "Mayagüez",
    "COLUMBUS LANDING": "Mayagüez",
}

RESIDENTIAL_RQ = {
    "ARISTIDES CHAVIER": "RQ1014",
    "PEDRO J. ROSALY": "RQ1009",
    "JUAN PONCE DE LEÓN": "RQ1001",
    "ERNESTO RAMOS ANTONINI": "RQ1017",
    "RAFAEL LOPEZ NUSSA": "RQ1016",
    "LA CEIBA": "RQ5022",
    "LEÓNARDO SANTIAGO": "RQ5148",
    "VILLA DEL PARQUE": "RQ3089",
    "BRISAS DEL MAR": "RQ5045",
    "BELLA VISTA": "RQ3090",
    "VALLES DE GUAYAMA": "RQ5266",
    "JARDINES DE GUAMANI": "RQ5184",
    "FERNANDO CALIMANO": "RQ5314",
    "SAN ANTONIO CARIOCA": "RQ5048",
    "EL CARMEN": "RQ4010",
    "MANUEL HERNANDEZ ROSA": "RQ4009",
    "RAFAEL HERNANDEZ": "RQ4011",
    "COLUMBUS LANDING": "RQ4001",
}


def residential_from_user(user: User | None) -> str:
    if not user:
        return ""
    if getattr(user, "residential", None):
        return normalize_text(user.residential.name)
    username = normalize_text(user.username).upper()
    return USER_RESIDENTIAL.get(username, normalize_text(user.username))


def municipality_from_user(user: User | None) -> str:
    if not user:
        return ""
    if getattr(user, "residential", None):
        return normalize_text(user.residential.municipality)
    residential_name = residential_from_user(user)
    return RESIDENTIAL_MUNICIPALITY.get(residential_name.upper(), "")


def rq_from_user(user: User | None) -> str:
    if not user:
        return ""
    if getattr(user, "residential", None):
        return normalize_text(user.residential.rq_code)
    residential_name = residential_from_user(user)
    return RESIDENTIAL_RQ.get(residential_name.upper(), "")


def base_reports_context(db: Session, current_user: User, month_options: list[tuple[int, str]]):
    proposals = db.execute(select(Proposal).where(Proposal.is_active == True).order_by(Proposal.code)).scalars().all()  # noqa: E712
    active_residential_id = getattr(current_user, "_active_residential_id", None)
    if active_residential_id is None and current_user.role not in {"admin", "supervisor"}:
        active_residential_id = current_user.residential_id

    residential_stmt = (
        select(Residential)
        .where(Residential.is_active == True)  # noqa: E712
        .order_by(Residential.code, Residential.name)
    )
    if active_residential_id is not None and not has_global_residential_access(current_user):
        residential_stmt = residential_stmt.where(
            Residential.residential_id == active_residential_id
        )
    residential_records = db.execute(residential_stmt).scalars().all()
    report_residentials = [
        option
        for residential in residential_records
        if (option := reporting_residential_option(residential)) is not None
    ]
    current_year = date.today().year
    year_options = list(range(MIN_REPORTING_YEAR, current_year + 1))
    month_lookup = dict(month_options)
    residential_option_map = {}
    for residential in report_residentials:
        label = f"{residential.code} - {residential.name}"
        residential_option_map[residential.residential_id] = label
        residential_option_map[residential.user_id] = label
    current_residential = reporting_residential_option(db.get(Residential, active_residential_id)) if active_residential_id else None
    residential_name = (
        current_residential.name
        if current_residential and not has_global_residential_access(current_user)
        else None
    )
    return {
        "proposals": proposals,
        "report_residentials": report_residentials,
        "residential_option_map": residential_option_map,
        # Compatibility keys retained while report URLs still call the scope parameter employee_id.
        "report_users": report_residentials,
        "user_residential_map": residential_option_map,
        "month_options": month_options,
        "month_lookup": month_lookup,
        "year_options": year_options,
        "residential_name": residential_name,
        "active_residential_id": active_residential_id,
    }


def resolve_reporting_scope(current_user: User, employee_id: int | None, db: Session) -> dict:
    selected_residential = None
    is_global = False
    residential_id = None
    scope_token = employee_id

    active_residential_id = getattr(current_user, "_active_residential_id", None)
    if active_residential_id is not None:
        residential_id = active_residential_id
        residential = db.get(Residential, residential_id)
        if residential and residential.is_active:
            selected_residential = reporting_residential_option(residential)
            scope_token = selected_residential.user_id
    elif current_user.role in {"admin", "supervisor"}:
        if employee_id == 0:
            is_global = True
        elif employee_id is not None and employee_id < 0:
            residential_id = abs(employee_id)
        elif employee_id:
            legacy_user = db.get(User, employee_id)
            residential_id = legacy_user.residential_id if legacy_user else None

        residential = db.get(Residential, residential_id) if residential_id else None
        if residential and residential.is_active:
            selected_residential = reporting_residential_option(residential)
            scope_token = selected_residential.user_id
    else:
        residential_id = getattr(current_user, "_active_residential_id", None) or current_user.residential_id
        residential = db.get(Residential, residential_id) if residential_id else None
        if residential and residential.is_active:
            selected_residential = reporting_residential_option(residential)
            scope_token = selected_residential.user_id

    return {
        "selected_residential": selected_residential,
        "residential_id": residential_id,
        "is_global": is_global,
        # Compatibility keys retained while templates and URLs are migrated incrementally.
        "selected_user": selected_residential,
        "employee_id": scope_token,
    }


def resolve_reporting_location(selected_user: User | None, is_global: bool) -> dict:
    residential_name = None
    municipality = None
    rq_code = None
    if is_global:
        residential_name = "Global"
        municipality = "Todos"
        rq_code = "Global"
    elif selected_user:
        residential_name = residential_from_user(selected_user)
        municipality = municipality_from_user(selected_user)
        rq_code = rq_from_user(selected_user)
    return {
        "residential_name": residential_name,
        "municipality": municipality,
        "rq_code": rq_code,
    }
