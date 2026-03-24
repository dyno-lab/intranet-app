from __future__ import annotations

from datetime import date
from io import BytesIO
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, extract
from sqlalchemy.orm import Session
from openpyxl import Workbook
from openpyxl.styles import Font

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

FIXED_SIGNATURES = [
    {"label": "Preparado por", "name": "______________________________", "title": "Programa Faro de Esperanza"},
    {"label": "Revisado por", "name": "______________________________", "title": "Programa Faro de Esperanza"},
]

ROWS_PER_BONAFIDE_PAGE = 26


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


def _chunk_rows(rows: list[dict], size: int) -> list[list[dict]]:
    if size <= 0:
        return [rows]
    chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
    return chunks or [[]]


def _build_bonafide_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | None,
    year: int | None,
    employee_id: int | None,
):
    proposals = db.execute(select(Proposal).where(Proposal.is_active == True).order_by(Proposal.code)).scalars().all()  # noqa: E712
    report_users = db.execute(
        select(User).where(User.is_active == True, User.role != "admin").order_by(User.username)
    ).scalars().all()  # noqa: E712
    current_year = date.today().year
    year_options = list(range(current_year - 2, current_year + 3))
    month_lookup = dict(MONTH_OPTIONS)
    user_residential_map = {user.user_id: f"{user.username} = {_residential_from_user(user)}" for user in report_users}

    selected_user = None
    is_global = False
    if current_user.role == "admin":
        if employee_id == 0:
            is_global = True
        elif employee_id:
            selected_user = db.get(User, employee_id)
    else:
        selected_user = current_user
        employee_id = current_user.user_id

    rows = []
    municipality = None
    residential_name = None
    if proposal_id and month and year and (selected_user or is_global):
        if is_global:
            residential_name = "Global"
            municipality = "Todos"
        else:
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
            )
            .distinct()
            .order_by(Participant.edificio, Participant.apart, Participant.apellido_paterno, Participant.nombre)
        )
        if not is_global:
            stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
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

    return {
        "proposals": proposals,
        "report_users": report_users,
        "user_residential_map": user_residential_map,
        "month_options": MONTH_OPTIONS,
        "month_lookup": month_lookup,
        "year_options": year_options,
        "selected_proposal_id": proposal_id,
        "selected_month": month,
        "selected_year": year,
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "municipality": municipality,
        "rows": rows,
        "pages": _chunk_rows(rows, ROWS_PER_BONAFIDE_PAGE),
        "rows_per_page": ROWS_PER_BONAFIDE_PAGE,
        "signatures": FIXED_SIGNATURES,
    }


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
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/bonafide.html", context)


@router.get("/bonafide/pdf", response_class=HTMLResponse)
def bonafide_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/bonafide_pdf.html", context)


@router.get("/bonafide/excel")
def bonafide_report_excel(
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id)

    if not (proposal_id and month and year and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/bonafide", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Bonafide"

    ws["A1"] = "Programa Faro de Esperanza"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Listado Bonafide"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Fecha"
    ws["B4"] = f"{context['month_lookup'].get(month, month)} {year}"
    ws["A5"] = "Residencial"
    ws["B5"] = context["residential_name"] or ""
    ws["A6"] = "Municipio"
    ws["B6"] = context["municipality"] or ""

    headers = ["#", "Expediente", "Nombre", "F", "M", "Edad", "Edif.", "Apto."]
    header_row = 8
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    for row_index, row in enumerate(context["rows"], start=header_row + 1):
        ws.cell(row=row_index, column=1, value=row["index"])
        ws.cell(row=row_index, column=2, value=row["expediente"])
        ws.cell(row=row_index, column=3, value=row["nombre"])
        ws.cell(row=row_index, column=4, value=row["f"])
        ws.cell(row=row_index, column=5, value=row["m"])
        ws.cell(row=row_index, column=6, value=row["edad"])
        ws.cell(row=row_index, column=7, value=row["edificio"])
        ws.cell(row=row_index, column=8, value=row["apartamento"])

    widths = {"A": 6, "B": 20, "C": 40, "D": 6, "E": 6, "F": 8, "G": 12, "H": 12}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    safe_residential = (context["residential_name"] or "bonafide").replace(" ", "_")
    filename = f"bonafide_{safe_residential}_{year}_{month}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
