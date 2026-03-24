from __future__ import annotations

from datetime import date
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, extract
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.auth import get_current_user
from app.models.activity_session import ActivitySession
from app.models.attendance import Attendance
from app.models.participant import Participant
from app.models.proposal import Proposal
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

MONTH_OPTIONS = [
    (1, "Enero"), (2, "Febrero"), (3, "Marzo"), (4, "Abril"),
    (5, "Mayo"), (6, "Junio"), (7, "Julio"), (8, "Agosto"),
    (9, "Septiembre"), (10, "Octubre"), (11, "Noviembre"), (12, "Diciembre"),
]

USER_RESIDENTIAL = {
    "AC": "Aristides Chavier",
    "PJR": "Pedro J. Rosaly",
    "JPL": "Juan Ponce de Leon",
    "ERA": "Ernesto Ramos Antonini",
    "RLN": "Rafael Lopez Nussa",
    "LC": "La Ceiba",
    "LS": "Leonardo Santiago",
    "VP": "Villa del Parque",
    "BDM": "Brisas del Mar",
    "BV": "Bella Vista",
    "VG": "Valles de Guayama",
    "JG": "Jardines de Guamani",
    "FC": "Fernando Calimano",
    "SAC": "San Antonio Carioca",
    "EC": "El Carmen",
    "MHR": "Manuel Hernandez Rosa",
    "RH": "Rafael Hernandez",
    "CL": "Columbus Landing",
}

RESIDENTIAL_MUNICIPALITY = {
    "ARISTIDES CHAVIER": "Ponce",
    "PEDRO J. ROSALY": "Ponce",
    "JUAN PONCE DE LEON": "Ponce",
    "ERNESTO RAMOS ANTONINI": "Ponce",
    "RAFAEL LOPEZ NUSSA": "Ponce",
    "LA CEIBA": "Ponce",
    "LEONARDO SANTIAGO": "Juana Díaz",
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

FIXED_SIGNATURES = [
    {"label": "Preparado por", "name": "______________________________", "title": "Programa Faro de Esperanza"},
    {"label": "Revisado por", "name": "______________________________", "title": "Programa Faro de Esperanza"},
]


def _calc_age(dob):
    if not dob:
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _normalize_text(value: str | None) -> str:
    return (value or "").strip()


def _residential_from_user(user: User | None) -> str:
    if not user:
        return ""
    username = _normalize_text(user.username).upper()
    return USER_RESIDENTIAL.get(username, _normalize_text(user.username))


@router.get("/bonafide", response_class=HTMLResponse)
def bonafide_report(
    request: Request,
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    proposals = db.execute(select(Proposal).where(Proposal.is_active == True).order_by(Proposal.code)).scalars().all()  # noqa: E712
    report_users = db.execute(select(User).where(User.is_active == True).order_by(User.username)).scalars().all()  # noqa: E712
    current_year = date.today().year
    year_options = list(range(current_year - 2, current_year + 3))
    month_lookup = dict(MONTH_OPTIONS)

    selected_user = None
    if current_user.role == "admin":
        if employee_id:
            selected_user = db.get(User, employee_id)
    else:
        selected_user = current_user
        employee_id = current_user.user_id

    rows = []
    municipality = None
    residential_name = None
    if proposal_id and month and year and selected_user:
        residential_name = _residential_from_user(selected_user)
        municipality = RESIDENTIAL_MUNICIPALITY.get(residential_name.upper(), "")

        stmt = (
            select(Participant)
            .join(Attendance, Attendance.participant_id == Participant.participant_id)
            .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
            .where(
                Attendance.attended == True,  # noqa: E712
                ActivitySession.proposal_id == proposal_id,
                extract("month", ActivitySession.session_date) == month,
                extract("year", ActivitySession.session_date) == year,
                ActivitySession.created_by_user_id == selected_user.user_id,
            )
            .distinct()
            .order_by(Participant.edificio, Participant.apart, Participant.apellido_paterno, Participant.nombre)
        )
        participants = db.execute(stmt).scalars().all()

        for idx, participant in enumerate(participants, start=1):
            gender = _normalize_text(participant.genero).upper()
            rows.append({
                "index": idx,
                "expediente": participant.expediente_num,
                "nombre": f"{participant.nombre} {participant.apellido_paterno} {participant.apellido_materno or ''}".strip(),
                "f": "X" if gender.startswith("F") else "",
                "m": "X" if gender.startswith("M") else "",
                "edad": _calc_age(participant.fecha_nacimiento) or "",
                "edificio": participant.edificio or "",
                "apartamento": participant.apart or "",
            })

    return templates.TemplateResponse(
        "ui/reports/bonafide.html",
        {
            "request": request,
            "current_user": current_user,
            "proposals": proposals,
            "report_users": report_users,
            "month_options": MONTH_OPTIONS,
            "month_lookup": month_lookup,
            "year_options": year_options,
            "selected_proposal_id": proposal_id,
            "selected_month": month,
            "selected_year": year,
            "selected_employee_id": employee_id,
            "selected_user": selected_user,
            "residential_name": residential_name,
            "municipality": municipality,
            "rows": rows,
            "signatures": FIXED_SIGNATURES,
        },
    )
