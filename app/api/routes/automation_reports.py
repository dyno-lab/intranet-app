from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models.user import User
from app.models.proposal import Proposal
from app.api.routes.reports import (
    _build_no_duplicado_context,
    _build_por_programa_context,
    _build_vca_context,
    _build_pregnancy_summary_context,
    _build_school_dropout_summary_context,
    _build_notes_context,
    _build_visits_context,
    _build_hoja_cotejo_context,
)

router = APIRouter()


REPORT_BUILDERS: dict[str, Callable[..., dict[str, Any]]] = {
    "no-duplicado": _build_no_duplicado_context,
    "duplicado": lambda *args, **kwargs: _build_no_duplicado_context(*args, duplicated=True, **kwargs),
    "por-programa": _build_por_programa_context,
    "vca": _build_vca_context,
    "embarazo": _build_pregnancy_summary_context,
    "desercion-escolar": _build_school_dropout_summary_context,
    "notas": _build_notes_context,
    "visitas": _build_visits_context,
    "hoja-cotejo": _build_hoja_cotejo_context,
}


SAFE_CONTEXT_KEYS = {
    "selected_proposal_id",
    "selected_month",
    "selected_year",
    "selected_period_type",
    "selected_start_date",
    "selected_end_date",
    "period_label",
    "selected_employee_id",
    "is_global",
    "residential_name",
    "municipality",
    "rq_code",
    "rows",
    "total_f",
    "total_m",
    "total_all",
    "overall_total_f",
    "overall_total_m",
    "overall_total_all",
    "program_sections",
    "columns",
    "total_people",
    "summary_rows",
    "dashboard_cards",
    "global_progress",
    "residential_summary_rows",
    "program_blocks",
    "total_contact_hours",
    "visits_rows",
    "referral_rows",
    "service_rows",
    "totals",
    "cards",
    "subject_chart_cards",
    "general_chart_segments",
    "residential_chart_segments",
}


MONTH_NAMES = {
    1: "enero",
    2: "febrero",
    3: "marzo",
    4: "abril",
    5: "mayo",
    6: "junio",
    7: "julio",
    8: "agosto",
    9: "septiembre",
    10: "octubre",
    11: "noviembre",
    12: "diciembre",
}


def require_automation_token(x_automation_token: str | None = Header(default=None)) -> None:
    """Optional lightweight guard for local automation/n8n endpoints.

    If AUTOMATION_API_KEY is configured in .env, callers must send the same
    value in the X-Automation-Token header. When unset, endpoints remain open
    for local/LAN MVP testing.
    """
    expected = settings.AUTOMATION_API_KEY
    if expected and x_automation_token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de automatización inválido o ausente.",
        )


def _automation_user(db: Session, run_as_user_id: int | None = None) -> User:
    if run_as_user_id:
        user = db.get(User, run_as_user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=404, detail="run_as_user_id no existe o está inactivo.")
        return user

    user = db.execute(
        select(User)
        .where(User.is_active == True, User.role.in_(["admin", "supervisor"]))  # noqa: E712
        .order_by(User.user_id)
    ).scalars().first()
    if user:
        return user

    user = db.execute(
        select(User)
        .where(User.is_active == True)  # noqa: E712
        .order_by(User.user_id)
    ).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="No hay usuarios activos para ejecutar reportes.")
    return user


def _model_to_dict(value: Any) -> dict[str, Any]:
    columns = getattr(getattr(value, "__table__", None), "columns", [])
    return {column.name: _json_safe(getattr(value, column.name)) for column in columns}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if hasattr(value, "__table__"):
        return _model_to_dict(value)
    return str(value)


def _scope_payload(context: dict[str, Any]) -> dict[str, Any]:
    selected_user = context.get("selected_user")
    return {
        "type": "global" if context.get("is_global") else "residential",
        "employee_id": context.get("selected_employee_id"),
        "selected_user_id": getattr(selected_user, "user_id", None) if selected_user else None,
        "selected_username": getattr(selected_user, "username", None) if selected_user else None,
        "residential_name": context.get("residential_name"),
        "municipality": context.get("municipality"),
        "rq_code": context.get("rq_code"),
    }


def _period_payload(context: dict[str, Any]) -> dict[str, Any]:
    month = context.get("selected_month")
    year = context.get("selected_year")
    return {
        "month": month,
        "month_name": MONTH_NAMES.get(month) if isinstance(month, int) else None,
        "year": year,
        "period_type": context.get("selected_period_type"),
        "start_date": context.get("selected_start_date"),
        "end_date": context.get("selected_end_date"),
        "label": context.get("period_label"),
    }


def _summary_from_context(report_key: str, context: dict[str, Any]) -> dict[str, Any]:
    if report_key in {"no-duplicado", "duplicado"}:
        return {
            "total_f": context.get("total_f", 0),
            "total_m": context.get("total_m", 0),
            "total_all": context.get("total_all", 0),
        }
    if report_key == "por-programa":
        return {
            "total_f": context.get("overall_total_f", 0),
            "total_m": context.get("overall_total_m", 0),
            "total_all": context.get("overall_total_all", 0),
        }
    if report_key == "vca":
        return {"total_people": context.get("total_people", 0)}
    if report_key == "hoja-cotejo":
        return {"total_contact_hours": context.get("total_contact_hours", 0)}
    return {}


def _context_payload(report_key: str, context: dict[str, Any]) -> dict[str, Any]:
    data = {key: _json_safe(context.get(key)) for key in SAFE_CONTEXT_KEYS if key in context}
    return {
        "report_key": report_key,
        "period": _period_payload(context),
        "scope": _scope_payload(context),
        "filters": {
            "proposal_id": context.get("selected_proposal_id"),
            "employee_id": context.get("selected_employee_id"),
        },
        "summary": _summary_from_context(report_key, context),
        "data": data,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def _build_report_payload(
    report_key: str,
    db: Session,
    user: User,
    proposal_id: int | None,
    month: int | str | None,
    year: int | str | None,
    employee_id: int | None,
    period_type: str,
    start_date: str | None,
    end_date: str | None,
) -> dict[str, Any]:
    if period_type not in {"monthly", "custom"}:
        raise HTTPException(status_code=400, detail="period_type debe ser monthly o custom.")

    builder = REPORT_BUILDERS.get(report_key)
    if not builder:
        raise HTTPException(status_code=404, detail="Reporte de automatización no existe.")

    context = builder(
        db,
        user,
        proposal_id,
        month,
        year,
        employee_id,
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
    )
    return _context_payload(report_key, context)


@router.get("/reports")
def list_automation_reports(_: None = Depends(require_automation_token)):
    return {
        "reports": sorted(REPORT_BUILDERS.keys()),
        "usage": "/api/automation/reports/{report_key}?month=3&year=2026&proposal_id=1",
    }


@router.get("/options")
def automation_options(
    db: Session = Depends(get_db),
    _: None = Depends(require_automation_token),
):
    proposals = db.execute(
        select(Proposal)
        .where(Proposal.is_active == True)  # noqa: E712
        .order_by(Proposal.code)
    ).scalars().all()
    users = db.execute(
        select(User)
        .where(User.is_active == True, User.role == "user")  # noqa: E712
        .order_by(User.username)
    ).scalars().all()
    return {
        "proposals": [
            {
                "proposal_id": proposal.proposal_id,
                "code": proposal.code,
                "name": proposal.name,
                "label": f"{proposal.proposal_id} | {proposal.code} - {proposal.name}",
            }
            for proposal in proposals
        ],
        "residentials": [
            {"employee_id": 0, "name": "Global", "label": "0 | Global"},
            *[
                {
                    "employee_id": user.user_id,
                    "username": user.username,
                    "name": _json_safe(getattr(user.residential, "name", None) or user.username),
                    "label": f"{user.user_id} | {_json_safe(getattr(user.residential, 'name', None) or user.username)}",
                }
                for user in users
            ],
        ],
        "months": [{"value": value, "name": name, "label": f"{value} | {name}"} for value, name in MONTH_NAMES.items()],
        "reports": sorted(REPORT_BUILDERS.keys()),
    }


@router.get("/reports/monthly-package")
def monthly_package(
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    run_as_user_id: int | None = None,
    include: str = "no-duplicado,duplicado,por-programa",
    db: Session = Depends(get_db),
    _: None = Depends(require_automation_token),
):
    user = _automation_user(db, run_as_user_id)
    requested_reports = [item.strip() for item in include.split(",") if item.strip()]
    payload = {
        "package_key": "monthly-package",
        "requested_reports": requested_reports,
        "reports": {},
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }
    for report_key in requested_reports:
        payload["reports"][report_key] = _build_report_payload(
            report_key,
            db,
            user,
            proposal_id,
            month,
            year,
            employee_id,
            period_type,
            start_date,
            end_date,
        )
    return payload


@router.get("/reports/{report_key}")
def automation_report(
    report_key: str,
    proposal_id: int | None = None,
    month: int | None = None,
    year: int | None = None,
    employee_id: int | None = None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    run_as_user_id: int | None = None,
    db: Session = Depends(get_db),
    _: None = Depends(require_automation_token),
):
    user = _automation_user(db, run_as_user_id)
    return _build_report_payload(
        report_key,
        db,
        user,
        proposal_id,
        month,
        year,
        employee_id,
        period_type,
        start_date,
        end_date,
    )
