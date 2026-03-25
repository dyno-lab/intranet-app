from __future__ import annotations

from datetime import date, datetime
from io import BytesIO
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, StreamingResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, extract, func
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
from app.models.residential import Residential
from app.models.activity_code import ActivityCode
from app.models.vca_column import VCAColumn
from app.models.vca_column_activity_code import VCAColumnActivityCode

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
    {"name": "Karla Santiago Pérez", "title": "Coordinadora Educativa"},
    {"name": "Alice E. Beard García", "title": "Coordinadora Prevención"},
    {"name": "Annjellyn Arroyo Pagán", "title": "Coordinadora de Arte, Cultura y Recreación"},
    {"name": "Josmary Cosme", "title": "Coordinadora Desarrollo Económico y Servicio al Residente"},
]

ROWS_PER_BONAFIDE_PAGE = 26

AGE_BUCKETS = [
    ("under_5", "Menos de 5 años"),
    ("5_7", "5 - 7 años"),
    ("8_10", "8 - 10 años"),
    ("11_15", "11 - 15 años"),
    ("16_21", "16 - 21 años"),
    ("22_59", "22 - 59 años"),
    ("60_plus", "60 años en adelante"),
]

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
    if getattr(user, "residential", None):
        return _normalize_text(user.residential.name)
    username = _normalize_text(user.username).upper()
    return USER_RESIDENTIAL.get(username, _normalize_text(user.username))


def _municipality_from_user(user: User | None) -> str:
    if not user:
        return ""
    if getattr(user, "residential", None):
        return _normalize_text(user.residential.municipality)
    residential_name = _residential_from_user(user)
    return RESIDENTIAL_MUNICIPALITY.get(residential_name.upper(), "")


def _rq_from_user(user: User | None) -> str:
    if not user:
        return ""
    if getattr(user, "residential", None):
        return _normalize_text(user.residential.rq_code)
    residential_name = _residential_from_user(user)
    return RESIDENTIAL_RQ.get(residential_name.upper(), "")


def _chunk_rows(rows: list[dict], size: int) -> list[list[dict]]:
    if size <= 0:
        return [rows]
    chunks = [rows[i:i + size] for i in range(0, len(rows), size)]
    return chunks or [[]]


def _get_age_bucket(age: int | None) -> str | None:
    if age is None or age < 0:
        return None
    if age < 5:
        return "under_5"
    if age <= 7:
        return "5_7"
    if age <= 10:
        return "8_10"
    if age <= 15:
        return "11_15"
    if age <= 21:
        return "16_21"
    if age <= 59:
        return "22_59"
    return "60_plus"


def _base_reports_context(db: Session, current_user: User):
    proposals = db.execute(select(Proposal).where(Proposal.is_active == True).order_by(Proposal.code)).scalars().all()  # noqa: E712
    report_users = db.execute(
        select(User).where(User.is_active == True, User.role == "user").order_by(User.username)
    ).scalars().all()  # noqa: E712
    current_year = date.today().year
    year_options = list(range(current_year - 2, current_year + 3))
    month_lookup = dict(MONTH_OPTIONS)
    user_residential_map = {user.user_id: f"{user.username} = {_residential_from_user(user)}" for user in report_users}
    residential_name = _residential_from_user(current_user) if current_user.role == "user" else None
    return {
        "proposals": proposals,
        "report_users": report_users,
        "user_residential_map": user_residential_map,
        "month_options": MONTH_OPTIONS,
        "month_lookup": month_lookup,
        "year_options": year_options,
        "residential_name": residential_name,
    }


def _parse_optional_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    value = value.strip()
    if not value:
        return None
    return int(value)


def _parse_optional_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    value = value.strip()
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _build_period_filter(period_type: str | None, month, year, start_date, end_date):
    month = _parse_optional_int(month)
    year = _parse_optional_int(year)
    start_date = _parse_optional_date(start_date)
    end_date = _parse_optional_date(end_date)
    is_custom = period_type == "custom" and start_date and end_date
    return {
        "period_type": period_type or "monthly",
        "month": month,
        "year": year,
        "start_date": start_date,
        "end_date": end_date,
        "is_custom": bool(is_custom),
    }


def _apply_session_period_filter(stmt, period: dict):
    if period["is_custom"]:
        return stmt.where(
            ActivitySession.session_date >= period["start_date"],
            ActivitySession.session_date <= period["end_date"],
        )
    if period["month"] and period["year"]:
        return stmt.where(
            extract("month", ActivitySession.session_date) == period["month"],
            extract("year", ActivitySession.session_date) == period["year"],
        )
    return stmt


def _describe_period(period: dict, month_lookup: dict[int, str]) -> str:
    if period["is_custom"]:
        return f"{period['start_date'].strftime('%d/%m/%Y')} al {period['end_date'].strftime('%d/%m/%Y')}"
    if period["month"] and period["year"]:
        return f"{month_lookup.get(period['month'], period['month'])} {period['year']}"
    return ""


def _period_filename_suffix(context: dict) -> str:
    if context.get("selected_period_type") == "custom" and context.get("selected_start_date") and context.get("selected_end_date"):
        return f"{context['selected_start_date']}_a_{context['selected_end_date']}"
    month = context.get("selected_month") or ""
    year = context.get("selected_year") or ""
    return f"{year}_{month}"


def _build_bonafide_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)

    base_context = _base_reports_context(db, current_user)
    proposals = base_context["proposals"]
    report_users = base_context["report_users"]
    year_options = base_context["year_options"]
    month_lookup = base_context["month_lookup"]
    user_residential_map = base_context["user_residential_map"]

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

    rows = []
    municipality = None
    residential_name = None
    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        if is_global:
            residential_name = "Global"
            municipality = "Todos"
        else:
            residential_name = _residential_from_user(selected_user)
            municipality = _municipality_from_user(selected_user)

        stmt = (
            select(Participant)
            .join(Attendance, Attendance.participant_id == Participant.participant_id)
            .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
            .where(
                Attendance.attended == True,  # noqa: E712
                ActivitySession.proposal_id == proposal_id,
            )
        )
        stmt = _apply_session_period_filter(stmt, period)
        stmt = stmt.distinct().order_by(Participant.edificio, Participant.apart, Participant.apellido_paterno, Participant.nombre)
        if not is_global:
            stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
        participants = db.execute(stmt).scalars().all()

        for idx, participant in enumerate(participants, start=1):
            gender = _normalize_text(participant.genero).upper()
            first_time = _normalize_text(getattr(participant, "primera_vez", None)).upper()
            display_name = f"{participant.nombre} {participant.apellido_paterno} {participant.apellido_materno or ''}".strip()
            if first_time == "SI":
                display_name = f"{display_name} *"
            rows.append({
                "index": idx,
                "expediente": participant.expediente_num,
                "nombre": display_name,
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
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
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


REPORT_OPTIONS = [
    {"value": "bonafide", "label": "Bonafide"},
    {"value": "no-duplicado", "label": "No Duplicado"},
    {"value": "duplicados", "label": "Duplicados"},
    {"value": "por-programa", "label": "Informes por programa"},
    {"value": "vca", "label": "Informe VCA"},
    {"value": "todos", "label": "Todos"},
]

PERIOD_TYPE_OPTIONS = [
    {"value": "monthly", "label": "Mensual"},
    {"value": "quarterly", "label": "Trimestral"},
    {"value": "annual", "label": "Anual"},
    {"value": "custom", "label": "Personalizado"},
]


@router.get("/", response_class=HTMLResponse)
def reports_home(
    request: Request,
    report_key: str = "bonafide",
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    output: str = "screen",
    period_type: str = "monthly",
    authorized_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _base_reports_context(db, current_user)
    context.update(
        {
            "request": request,
            "current_user": current_user,
            "report_options": REPORT_OPTIONS,
            "period_type_options": PERIOD_TYPE_OPTIONS,
            "selected_report_key": report_key,
            "selected_proposal_id": proposal_id,
            "selected_month": month,
            "selected_year": year,
            "selected_employee_id": employee_id,
            "selected_output": output,
            "selected_period_type": period_type,
            "authorized_name": (authorized_name or "").strip(),
            "selected_start_date": start_date or "",
            "selected_end_date": end_date or "",
        }
    )
    return templates.TemplateResponse("ui/reports/index.html", context)


@router.get("/run")
def reports_run(
    report_key: str,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    output: str = "screen",
    period_type: str = "monthly",
    authorized_name: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
):
    month_value = int(month) if (month or "").strip() else None
    year_value = int(year) if (year or "").strip() else None
    period_query = f"&period_type={period_type}&start_date={start_date or ''}&end_date={end_date or ''}"

    if report_key == "bonafide":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/bonafide/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/bonafide/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/bonafide?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    if report_key == "no-duplicado":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/no-duplicado/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/no-duplicado/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/no-duplicado?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
            status_code=303,
        )

    if report_key == "duplicados":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/duplicado/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        if output == "pdf":
            return RedirectResponse(
                f"/ui/reports/duplicado/pdf?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/duplicado?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}&authorized_name={authorized_name or ''}{period_query}",
            status_code=303,
        )

    if report_key == "vca":
        if output == "excel":
            return RedirectResponse(
                f"/ui/reports/vca/excel?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
                status_code=303,
            )
        return RedirectResponse(
            f"/ui/reports/vca?proposal_id={proposal_id}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id}{period_query}",
            status_code=303,
        )

    return RedirectResponse(
        f"/ui/reports/?report_key={report_key}&proposal_id={proposal_id or ''}&month={month_value or ''}&year={year_value or ''}&employee_id={employee_id or ''}&output={output}&period_type={period_type}&authorized_name={authorized_name or ''}&start_date={start_date or ''}&end_date={end_date or ''}",
        status_code=303,
    )


def _build_vca_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)
    base_context = _base_reports_context(db, current_user)
    month_lookup = base_context["month_lookup"]

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

    columns = []
    rows = []
    residential_name = None
    total_people = 0

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        proposal = db.get(Proposal, proposal_id)
        if proposal:
            columns = db.execute(
                select(VCAColumn)
                .where(VCAColumn.proposal_id == proposal_id, VCAColumn.is_active == True)  # noqa: E712
                .order_by(VCAColumn.sort_order, VCAColumn.name)
            ).scalars().all()

            mapping_rows = db.execute(
                select(VCAColumnActivityCode, ActivityCode, VCAColumn)
                .join(ActivityCode, ActivityCode.activity_code_id == VCAColumnActivityCode.activity_code_id)
                .join(VCAColumn, VCAColumn.vca_column_id == VCAColumnActivityCode.vca_column_id)
                .where(VCAColumn.proposal_id == proposal_id, VCAColumn.is_active == True)  # noqa: E712
            ).all()
            activity_to_column = {activity.activity_code_id: column.vca_column_id for _, activity, column in mapping_rows}

            participant_stmt = (
                select(Participant)
                .join(Attendance, Attendance.participant_id == Participant.participant_id)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                    func.upper(func.ltrim(func.rtrim(func.isnull(Participant.vca, "")))) == "SI",
                )
            )
            participant_stmt = _apply_session_period_filter(participant_stmt, period)
            if is_global:
                residential_name = "Global"
            else:
                participant_stmt = participant_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
                residential_name = _residential_from_user(selected_user)
            participants = participant_stmt.distinct().order_by(Participant.apellido_paterno, Participant.nombre)
            participant_rows = db.execute(participants).scalars().all()

            attendance_stmt = (
                select(Attendance.participant_id, ActivitySession.activity_code_id)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                )
            )
            attendance_stmt = _apply_session_period_filter(attendance_stmt, period)
            if not is_global:
                attendance_stmt = attendance_stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)
            attendance_rows = db.execute(attendance_stmt).all()

            counts: dict[int, dict[int, int]] = {}
            for participant_id, activity_code_id in attendance_rows:
                column_id = activity_to_column.get(activity_code_id)
                if not column_id:
                    continue
                counts.setdefault(participant_id, {})
                counts[participant_id][column_id] = counts[participant_id].get(column_id, 0) + 1

            for participant in participant_rows:
                row_values = {column.vca_column_id: counts.get(participant.participant_id, {}).get(column.vca_column_id, "") for column in columns}
                if not any(value != "" for value in row_values.values()):
                    continue
                rows.append({
                    "participant_id": participant.participant_id,
                    "nombre": f"{participant.nombre} {participant.apellido_paterno} {participant.apellido_materno or ''}".strip(),
                    "genero": participant.genero or "",
                    "edad": _calc_age(participant.fecha_nacimiento) or "",
                    "values": row_values,
                })
            total_people = len(rows)

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, month_lookup),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "columns": columns,
        "rows": rows,
        "total_people": total_people,
    }


def _build_no_duplicado_context(
    db: Session,
    current_user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    authorized_name: str | None = None,
    duplicated: bool = False,
    period_type: str = "monthly",
    start_date: date | str | None = None,
    end_date: date | str | None = None,
):
    period = _build_period_filter(period_type, month, year, start_date, end_date)

    base_context = _base_reports_context(db, current_user)
    report_users = base_context["report_users"]

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

    residential_name = None
    municipality = None
    rq_code = None
    if is_global:
        residential_name = "Global"
        municipality = "Todos"
        rq_code = "Global"
    elif selected_user:
        residential_name = _residential_from_user(selected_user)
        municipality = _municipality_from_user(selected_user)
        rq_code = _rq_from_user(selected_user)

    summary = {key: {"label": label, "f": 0, "m": 0, "total": 0} for key, label in AGE_BUCKETS}

    if proposal_id and ((period["month"] and period["year"]) or period["is_custom"]) and (selected_user or is_global):
        if duplicated:
            stmt = (
                select(Attendance, Participant)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .join(Participant, Participant.participant_id == Attendance.participant_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                )
            )
            stmt = _apply_session_period_filter(stmt, period)
            if not is_global:
                stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)

            attendance_rows = db.execute(stmt).all()
            for _, participant in attendance_rows:
                age = _calc_age(participant.fecha_nacimiento)
                bucket = _get_age_bucket(age)
                if not bucket:
                    continue
                gender = _normalize_text(participant.genero).upper()
                if gender.startswith("F"):
                    summary[bucket]["f"] += 1
                elif gender.startswith("M"):
                    summary[bucket]["m"] += 1
                summary[bucket]["total"] += 1
        else:
            stmt = (
                select(Participant)
                .join(Attendance, Attendance.participant_id == Participant.participant_id)
                .join(ActivitySession, ActivitySession.session_id == Attendance.session_id)
                .where(
                    Attendance.attended == True,  # noqa: E712
                    ActivitySession.proposal_id == proposal_id,
                )
            )
            stmt = _apply_session_period_filter(stmt, period)
            stmt = stmt.distinct()
            if not is_global:
                stmt = stmt.where(ActivitySession.created_by_user_id == selected_user.user_id)

            participants = db.execute(stmt).scalars().all()
            for participant in participants:
                age = _calc_age(participant.fecha_nacimiento)
                bucket = _get_age_bucket(age)
                if not bucket:
                    continue
                gender = _normalize_text(participant.genero).upper()
                if gender.startswith("F"):
                    summary[bucket]["f"] += 1
                elif gender.startswith("M"):
                    summary[bucket]["m"] += 1
                summary[bucket]["total"] += 1

    rows = []
    total_f = total_m = total_all = 0
    for key, label in AGE_BUCKETS:
        row = summary[key]
        rows.append({"label": label, "f": row["f"], "m": row["m"], "total": row["total"]})
        total_f += row["f"]
        total_m += row["m"]
        total_all += row["total"]

    return {
        **base_context,
        "selected_proposal_id": proposal_id,
        "selected_month": period["month"],
        "selected_year": period["year"],
        "selected_period_type": period["period_type"],
        "selected_start_date": period["start_date"].isoformat() if period["start_date"] else "",
        "selected_end_date": period["end_date"].isoformat() if period["end_date"] else "",
        "period_label": _describe_period(period, base_context["month_lookup"]),
        "selected_employee_id": employee_id,
        "selected_user": selected_user,
        "is_global": is_global,
        "residential_name": residential_name,
        "municipality": municipality,
        "rq_code": rq_code,
        "rows": rows,
        "total_f": total_f,
        "total_m": total_m,
        "total_all": total_all,
        "authorized_name": (authorized_name or "").strip(),
    }


@router.get("/duplicado", response_class=HTMLResponse)
def duplicado_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, duplicated=True, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/duplicado.html", context)


@router.get("/duplicado/pdf", response_class=HTMLResponse)
def duplicado_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, duplicated=True, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/duplicado_pdf.html", context)


@router.get("/duplicado/excel")
def duplicado_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, duplicated=True, period_type=period_type, start_date=start_date, end_date=end_date)

    if not (proposal_id and (context["period_label"]) and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/duplicado", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Duplicado"

    ws["A1"] = "Informe mensual de participaciones"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Duplicado por edad y sexo en los proyectos impactados"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["A5"] = "Municipio"
    ws["B5"] = context["municipality"] or ""
    ws["A6"] = "RQ"
    ws["B6"] = context["rq_code"] or ""
    ws["A7"] = "Periodo reportado"
    ws["B7"] = context["period_label"]
    ws["A8"] = "Funcionario autorizado"
    ws["B8"] = context["authorized_name"] or ""

    headers = ["Clasificación", "F", "M", "Total de participaciones"]
    header_row = 10
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    row_index = header_row + 1
    for row in context["rows"]:
        ws.cell(row=row_index, column=1, value=row["label"])
        ws.cell(row=row_index, column=2, value=row["f"])
        ws.cell(row=row_index, column=3, value=row["m"])
        ws.cell(row=row_index, column=4, value=row["total"])
        row_index += 1

    ws.cell(row=row_index, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=row_index, column=2, value=context["total_f"]).font = Font(bold=True)
    ws.cell(row=row_index, column=3, value=context["total_m"]).font = Font(bold=True)
    ws.cell(row=row_index, column=4, value=context["total_all"]).font = Font(bold=True)

    widths = {"A": 35, "B": 10, "C": 10, "D": 20}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    safe_residential = (context["residential_name"] or "duplicado").replace(" ", "_")
    filename = f"duplicado_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/no-duplicado", response_class=HTMLResponse)
def no_duplicado_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/no_duplicado.html", context)


@router.get("/no-duplicado/pdf", response_class=HTMLResponse)
def no_duplicado_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/no_duplicado_pdf.html", context)


@router.get("/no-duplicado/excel")
def no_duplicado_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    authorized_name: str | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_no_duplicado_context(db, current_user, proposal_id, month, year, employee_id, authorized_name, period_type=period_type, start_date=start_date, end_date=end_date)

    if not (proposal_id and (context["period_label"]) and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/no-duplicado", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "No Duplicado"

    ws["A1"] = "Informe mensual de participantes"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "No Duplicado por edad y sexo en los proyectos impactados"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Residencial"
    ws["B4"] = context["residential_name"] or ""
    ws["A5"] = "Municipio"
    ws["B5"] = context["municipality"] or ""
    ws["A6"] = "RQ"
    ws["B6"] = context["rq_code"] or ""
    ws["A7"] = "Periodo reportado"
    ws["B7"] = context["period_label"]
    ws["A8"] = "Funcionario autorizado"
    ws["B8"] = context["authorized_name"] or ""

    headers = ["Clasificación", "F", "M", "Total de participantes"]
    header_row = 10
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    row_index = header_row + 1
    for row in context["rows"]:
        ws.cell(row=row_index, column=1, value=row["label"])
        ws.cell(row=row_index, column=2, value=row["f"])
        ws.cell(row=row_index, column=3, value=row["m"])
        ws.cell(row=row_index, column=4, value=row["total"])
        row_index += 1

    ws.cell(row=row_index, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=row_index, column=2, value=context["total_f"]).font = Font(bold=True)
    ws.cell(row=row_index, column=3, value=context["total_m"]).font = Font(bold=True)
    ws.cell(row=row_index, column=4, value=context["total_all"]).font = Font(bold=True)

    widths = {"A": 35, "B": 10, "C": 10, "D": 20}
    for col, width in widths.items():
        ws.column_dimensions[col].width = width

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    safe_residential = (context["residential_name"] or "no_duplicado").replace(" ", "_")
    filename = f"no_duplicado_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/vca", response_class=HTMLResponse)
def vca_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_vca_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/vca.html", context)


@router.get("/vca/excel")
def vca_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_vca_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    if not (proposal_id and context["period_label"] and context["columns"]):
        return RedirectResponse("/ui/reports/vca", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "VCA"
    ws["A1"] = "Informe VCA"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A3"] = "Residencial"
    ws["B3"] = context["residential_name"] or ""
    ws["A4"] = "Periodo reportado"
    ws["B4"] = context["period_label"]
    ws["A5"] = "Total personas con impedimentos"
    ws["B5"] = context["total_people"]

    headers = ["Nombre", "Género", "Edad"] + [column.name for column in context["columns"]]
    header_row = 7
    for col_index, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_index, value=header)
        cell.font = Font(bold=True)

    for row_index, row in enumerate(context["rows"], start=header_row + 1):
        ws.cell(row=row_index, column=1, value=row["nombre"])
        ws.cell(row=row_index, column=2, value=row["genero"])
        ws.cell(row=row_index, column=3, value=row["edad"])
        for offset, column in enumerate(context["columns"], start=4):
            ws.cell(row=row_index, column=offset, value=row["values"].get(column.vca_column_id, ""))

    ws.column_dimensions["A"].width = 35
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 10
    for index in range(len(context["columns"])):
        ws.column_dimensions[chr(68 + index)].width = 28

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    safe_residential = (context["residential_name"] or "vca").replace(" ", "_")
    filename = f"vca_{safe_residential}_{_period_filename_suffix(context)}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bonafide", response_class=HTMLResponse)
def bonafide_report(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/bonafide.html", context)


@router.get("/bonafide/pdf", response_class=HTMLResponse)
def bonafide_report_pdf(
    request: Request,
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)
    context.update({"request": request, "current_user": current_user})
    return templates.TemplateResponse("ui/reports/bonafide_pdf.html", context)


@router.get("/bonafide/excel")
def bonafide_report_excel(
    proposal_id: int | None = None,
    month: str | None = None,
    year: str | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    context = _build_bonafide_context(db, current_user, proposal_id, month, year, employee_id, period_type=period_type, start_date=start_date, end_date=end_date)

    if not (proposal_id and (context["period_label"]) and (context["selected_user"] or context["is_global"])):
        return RedirectResponse("/ui/reports/bonafide", status_code=303)

    wb = Workbook()
    ws = wb.active
    ws.title = "Bonafide"

    ws["A1"] = "Programa Faro de Esperanza"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Listado Bonafide"
    ws["A2"].font = Font(bold=True)
    ws["A4"] = "Periodo"
    ws["B4"] = context["period_label"]
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
    filename = f"bonafide_{safe_residential}_{_period_filename_suffix(context)}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
