from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.helpers.reports import normalize_text
from app.models.proposal import Proposal
from app.models.user import User

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
    report_users = db.execute(
        select(User).where(User.is_active == True, User.role == "user").order_by(User.username)
    ).scalars().all()  # noqa: E712
    current_year = date.today().year
    year_options = list(range(current_year - 2, current_year + 3))
    month_lookup = dict(month_options)
    user_residential_map = {user.user_id: f"{user.username} = {residential_from_user(user)}" for user in report_users}
    residential_name = residential_from_user(current_user) if current_user.role == "user" else None
    return {
        "proposals": proposals,
        "report_users": report_users,
        "user_residential_map": user_residential_map,
        "month_options": month_options,
        "month_lookup": month_lookup,
        "year_options": year_options,
        "residential_name": residential_name,
    }


def resolve_reporting_scope(current_user: User, employee_id: int | None, db: Session) -> dict:
    selected_user = None
    is_global = False
    if current_user.role in {"admin", "supervisor"}:
        if employee_id == 0:
            is_global = True
        elif employee_id:
            selected_user = db.get(User, employee_id)
    else:
        selected_user = current_user
        employee_id = current_user.user_id
    return {
        "selected_user": selected_user,
        "is_global": is_global,
        "employee_id": employee_id,
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
