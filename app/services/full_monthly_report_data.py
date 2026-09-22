"""Read-only assembly of the existing monthly report contexts.

The individual contexts remain the source of truth for counts, percentages and
hours. Additional institutional tables regroup those same participants using
the supplied template's age bands and retain the existing identity rules.
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, union
from sqlalchemy.orm import Session

from app.core.auth import require_admin
from app.helpers.report_proposals import proposal_ids as normalize_proposal_ids
from app.models.activity_session import ActivitySession
from app.models.pregnancy_report import PregnancyReport
from app.models.proposal import Proposal
from app.models.residential import Residential
from app.models.school_dropout_report import SchoolDropoutReport
from app.models.school_grade_report import SchoolGradeReport
from app.models.user import User
from app.models.visit_report import VisitReport
from app.services.hoja_cotejo_admin_service import build_hoja_cotejo_admin_context
from app.services.consolidado_mensual_service import _official_residential_sort_key
from app.services.full_monthly_report_supplemental_data import build_supplemental_data
from app.services.full_monthly_report_recruitment import build_recruitment_data
from app.services.full_monthly_report_extension import consolidate_extension_checklists


class _GlobalReportUser:
    """Read-only view of an administrator for this explicitly global report."""

    _active_residential_id = None

    def __init__(self, user: User):
        self._user = user

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_user"), name)


def _coverage(db: Session, proposal_ids: list[int], month: int, year: int) -> dict[str, Any]:
    """Describe historical scope that existing residential selectors exclude."""
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    sources = [
        select(ActivitySession.residential_id).where(
            ActivitySession.proposal_id.in_(proposal_ids),
            ActivitySession.session_date >= start,
            ActivitySession.session_date <= end,
        ),
    ]
    for report in (PregnancyReport, SchoolDropoutReport, SchoolGradeReport, VisitReport):
        sources.append(select(report.residential_id).where(
            report.proposal_id.in_(proposal_ids),
            report.report_month == month,
            report.report_year == year,
        ))
    historical_scope = union(*sources).subquery()
    historical_ids = select(historical_scope.c.residential_id)
    inactive = db.execute(
        select(Residential).where(
            Residential.is_active == False,  # noqa: E712
            Residential.residential_id.in_(historical_ids),
        ).order_by(Residential.code, Residential.name)
    ).scalars().all()
    has_unassigned = db.execute(
        select(historical_scope.c.residential_id).where(
            historical_scope.c.residential_id.is_(None)
        ).limit(1)
    ).first() is not None
    return {
        "residential_scope": "active_residentials",
        "inactive_residentials_with_data": [
            {"residential_id": row.residential_id, "residential_name": row.name}
            for row in inactive
        ],
        "has_unassigned_data": bool(has_unassigned),
    }


def build_full_monthly_report_data(
    db: Session,
    current_user: User,
    proposal_ids: list[int],
    month: int,
    year: int,
    authorized_name: str | None = None,
) -> dict[str, Any]:
    """Return one monthly, global administrator report without writing data.

    Stable public shape:
    * ``proposals`` contains the selected Proposal models; ``month``, ``year``,
      ``period_label`` and ``authorized_name`` describe the document.
    * ``no_duplicado``, ``duplicado``, ``por_programa``, ``embarazo``,
      ``desercion``, ``visitas``, ``adm`` and ``hoja_cotejo`` are unmodified
      existing report-builder contexts for all selected proposals, globally.
    * ``residentials`` contains the active Residential model, its ID/name and
      existing no_duplicado, duplicado, bonafide, por_programa and hoja_cotejo
      contexts for that residential. Global totals must never be reconstructed
      by adding these rows, because a person may attend in multiple locations.
    * ``hoja_cotejo_admin`` keeps one existing context per proposal, except
      explicitly selecting both 005 and 006 produces one extension checklist
      with shared goals and continuous cumulative attendance.
    * ``program_hours`` and ``total_contact_hours`` expose the current Hoja de
      Cotejo values; ``provenance`` identifies their source. ``coverage`` flags
      inactive or unassigned locations present in the global source data.
    * ``target_population_rows`` regroups monthly participants into the supplied
      template's age/sex bands. ``target_cumulative`` contains unique people
      from the first confirmed attendance through the selected month's end,
      with separate residential and global counts and proposal start dates.
    * ``recruitment`` counts distinct session residentials reached by confirmed
      attendance, monthly and across the proposal history, by program/population.

    Existing residential reports only allow active locations. The complete
    report preserves that rule for its individual sheets while retaining the
    original unrestricted global totals and exposing coverage information.
    """
    require_admin(current_user)
    selected_ids = normalize_proposal_ids(proposal_ids)
    if not selected_ids:
        raise HTTPException(status_code=422, detail="Selecciona al menos una propuesta.")
    try:
        date(year, month, 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Selecciona un mes y año válidos.")

    # Import at the assembly seam to avoid a cycle when the report router loads
    # this service. Existing builders and their contracts remain untouched.
    from app.api.routes import reports

    report_user = _GlobalReportUser(current_user)
    with db.no_autoflush:
        proposals = db.execute(
            select(Proposal).where(Proposal.proposal_id.in_(selected_ids))
            .order_by(Proposal.proposal_id)
        ).scalars().all()
        if len(proposals) != len(selected_ids):
            raise HTTPException(status_code=422, detail="Una de las propuestas seleccionadas no existe.")

        common = dict(db=db, current_user=report_user, proposal_id=selected_ids,
                      month=month, year=year, employee_id=0)
        named = dict(common, authorized_name=authorized_name)
        contexts = {
            "no_duplicado": reports._build_no_duplicado_context(**named),
            "duplicado": reports._build_no_duplicado_context(**named, duplicated=True),
            "por_programa": reports._build_por_programa_context(**named),
            "embarazo": reports._build_pregnancy_summary_context(**common),
            "desercion": reports._build_school_dropout_summary_context(**common),
            "visitas": reports._build_visits_context(**named),
            "adm": reports._build_adm_context(**named),
            "hoja_cotejo": reports._build_hoja_cotejo_context(**common),
        }
        residential_models = db.execute(
            select(Residential).where(Residential.is_active == True)  # noqa: E712
            .order_by(Residential.code, Residential.name)
        ).scalars().all()
        residential_models.sort(key=_official_residential_sort_key)
        residentials = []
        for residential in residential_models:
            # Negative values are existing, collision-free residential tokens.
            scoped = dict(common, employee_id=-residential.residential_id)
            scoped_named = dict(scoped, authorized_name=authorized_name)
            residentials.append({
                "residential": residential,
                "residential_id": residential.residential_id,
                "residential_name": residential.name,
                "no_duplicado": reports._build_no_duplicado_context(**scoped_named),
                "duplicado": reports._build_no_duplicado_context(**scoped_named, duplicated=True),
                "bonafide": reports._build_bonafide_context(**scoped),
                "por_programa": reports._build_por_programa_context(**scoped_named),
                "hoja_cotejo": reports._build_hoja_cotejo_context(**scoped),
            })
        admin_contexts = [
            build_hoja_cotejo_admin_context(
                db, proposal_id=proposal.proposal_id, month=month, year=year,
                current_user=report_user, authorized_name=authorized_name,
            )
            for proposal in proposals
        ]
        coverage = _coverage(db, selected_ids, month, year)
        supplemental = build_supplemental_data(
            db, report_user, selected_ids, month, year, residentials,
        )
        recruitment = build_recruitment_data(db, report_user, selected_ids, month, year)
        admin_contexts = consolidate_extension_checklists(
            db, report_user, proposals, admin_contexts, recruitment, contexts["hoja_cotejo"], month, year,
        )

    hoja = contexts["hoja_cotejo"]
    return {
        "proposals": proposals,
        "selected_proposal_ids": selected_ids,
        "month": month,
        "year": year,
        "period_label": contexts["no_duplicado"]["period_label"],
        "authorized_name": contexts["no_duplicado"]["authorized_name"],
        **contexts,
        **supplemental,
        "recruitment": recruitment,
        "residentials": residentials,
        "hoja_cotejo_admin": admin_contexts,
        "total_contact_hours": hoja["total_contact_hours"],
        "program_hours": [
            {"program_code": block["program"].code,
             "program_display_name": block["program_display_name"],
             "contact_hours": block["program_contact_hours"]}
            for block in hoja["program_blocks"]
        ],
        "coverage": {**coverage, "active_residential_count": len(residentials)},
        "provenance": {
            "metrics": "existing_report_contexts",
            "global_unique": "no_duplicado.total_all",
            "global_duplicates": "duplicado.total_all",
            "program_hours": "hoja_cotejo.program_blocks.program_contact_hours",
            "total_contact_hours": "hoja_cotejo.total_contact_hours",
            "admin_goals": ("hoja_cotejo_admin_with_shared_extension"
                            if any(context.get("selected_proposal_ids") for context in admin_contexts)
                            else "hoja_cotejo_admin_by_proposal"),
        },
    }
