from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.proposal_report_program import ProposalReportProgram
from app.models.proposal_report_program_activity import ProposalReportProgramActivity
from app.models.proposal_report_program_activity_code import ProposalReportProgramActivityCode
from app.models.proposal_report_program_population import ProposalReportProgramPopulation
from app.models.proposal_population_group import ProposalPopulationGroup
from app.models.activity_code import ActivityCode
from app.models.proposal_report_program_population_activity_code import ProposalReportProgramPopulationActivityCode


def program_display_name(program: ProposalReportProgram) -> str:
    return (getattr(program, "formal_name", None) or getattr(program, "name", None) or getattr(program, "code", "")).strip()


def program_uses_population_structure(db: Session, program_id: int) -> bool:
    count = db.execute(
        select(func.count()).select_from(ProposalReportProgramPopulation).where(
            ProposalReportProgramPopulation.program_id == program_id,
            ProposalReportProgramPopulation.is_active == True,  # noqa: E712
        )
    ).scalar()
    return bool(count and count > 0)


def resolve_effective_program_activity_code_ids(db: Session, program_id: int) -> set[int]:
    if program_uses_population_structure(db, program_id):
        rows = db.execute(
            select(ProposalReportProgramPopulationActivityCode.activity_code_id)
            .join(
                ProposalReportProgramPopulation,
                ProposalReportProgramPopulation.program_population_id
                == ProposalReportProgramPopulationActivityCode.program_population_id,
            )
            .where(
                ProposalReportProgramPopulation.program_id == program_id,
                ProposalReportProgramPopulation.is_active == True,  # noqa: E712
            )
        ).all()
        return {activity_code_id for (activity_code_id,) in rows}

    synthetic_activities = db.execute(
        select(ProposalReportProgramActivity)
        .where(ProposalReportProgramActivity.program_id == program_id)
    ).scalars().all()
    if not synthetic_activities:
        return set()

    rows = db.execute(
        select(ProposalReportProgramActivityCode.activity_code_id)
        .where(
            ProposalReportProgramActivityCode.program_activity_id.in_(
                [activity.program_activity_id for activity in synthetic_activities]
            )
        )
    ).all()
    return {activity_code_id for (activity_code_id,) in rows}


def activity_code_is_assigned_anywhere_in_proposal(
    db: Session,
    proposal_id: int,
    activity_code_id: int,
    *,
    exclude_program_population_id: int | None = None,
    exclude_program_id: int | None = None,
) -> bool:
    legacy_stmt = (
        select(ProposalReportProgramActivityCode.id)
        .join(
            ProposalReportProgramActivity,
            ProposalReportProgramActivity.program_activity_id == ProposalReportProgramActivityCode.program_activity_id,
        )
        .join(
            ProposalReportProgram,
            ProposalReportProgram.program_id == ProposalReportProgramActivity.program_id,
        )
        .where(
            ProposalReportProgram.proposal_id == proposal_id,
            ProposalReportProgramActivityCode.activity_code_id == activity_code_id,
        )
    )
    if exclude_program_id is not None:
        legacy_stmt = legacy_stmt.where(ProposalReportProgram.program_id != exclude_program_id)
    legacy_match = db.execute(legacy_stmt).first()
    if legacy_match:
        return True

    new_stmt = (
        select(ProposalReportProgramPopulationActivityCode.id)
        .join(
            ProposalReportProgramPopulation,
            ProposalReportProgramPopulation.program_population_id
            == ProposalReportProgramPopulationActivityCode.program_population_id,
        )
        .join(
            ProposalReportProgram,
            ProposalReportProgram.program_id == ProposalReportProgramPopulation.program_id,
        )
        .where(
            ProposalReportProgram.proposal_id == proposal_id,
            ProposalReportProgramPopulationActivityCode.activity_code_id == activity_code_id,
        )
    )
    if exclude_program_population_id is not None:
        new_stmt = new_stmt.where(
            ProposalReportProgramPopulation.program_population_id != exclude_program_population_id
        )
    new_match = db.execute(new_stmt).first()
    return new_match is not None


def resolve_effective_program_population_blocks(db: Session, proposal_id: int) -> list[dict]:
    programs = db.execute(
        select(ProposalReportProgram)
        .where(
            ProposalReportProgram.proposal_id == proposal_id,
            ProposalReportProgram.is_active == True,  # noqa: E712
        )
        .order_by(ProposalReportProgram.sort_order, ProposalReportProgram.code)
    ).scalars().all()
    if not programs:
        return []

    population_groups = db.execute(
        select(ProposalPopulationGroup)
        .where(ProposalPopulationGroup.proposal_id == proposal_id)
        .order_by(ProposalPopulationGroup.sort_order, ProposalPopulationGroup.code)
    ).scalars().all()
    population_group_by_id = {group.population_group_id: group for group in population_groups}

    activity_codes = db.execute(
        select(ActivityCode)
        .where(ActivityCode.proposal_id == proposal_id)
        .order_by(ActivityCode.code)
    ).scalars().all()
    activity_code_by_id = {activity.activity_code_id: activity for activity in activity_codes}

    program_ids = [program.program_id for program in programs]
    program_populations = db.execute(
        select(ProposalReportProgramPopulation)
        .where(
            ProposalReportProgramPopulation.program_id.in_(program_ids),
            ProposalReportProgramPopulation.is_active == True,  # noqa: E712
        )
        .order_by(ProposalReportProgramPopulation.sort_order, ProposalReportProgramPopulation.program_population_id)
    ).scalars().all() if program_ids else []
    populations_by_program_id: dict[int, list[ProposalReportProgramPopulation]] = {}
    for population in program_populations:
        populations_by_program_id.setdefault(population.program_id, []).append(population)

    program_population_ids = [population.program_population_id for population in program_populations]
    population_activity_rows = db.execute(
        select(ProposalReportProgramPopulationActivityCode)
        .where(ProposalReportProgramPopulationActivityCode.program_population_id.in_(program_population_ids))
    ).scalars().all() if program_population_ids else []
    population_activity_ids_by_population_id: dict[int, set[int]] = {}
    for mapping in population_activity_rows:
        population_activity_ids_by_population_id.setdefault(mapping.program_population_id, set()).add(mapping.activity_code_id)

    blocks: list[dict] = []
    for program in programs:
        uses_population_structure = program_uses_population_structure(db, program.program_id)
        population_blocks: list[dict] = []

        if uses_population_structure:
            for population in populations_by_program_id.get(program.program_id, []):
                population_group = population_group_by_id.get(population.population_group_id)
                activity_ids = sorted(population_activity_ids_by_population_id.get(population.program_population_id, set()))
                rows = []
                for activity_id in activity_ids:
                    activity = activity_code_by_id.get(activity_id)
                    if not activity:
                        continue
                    rows.append({
                        "activity_code_id": activity.activity_code_id,
                        "activity_code": activity.code,
                        "activity_description": activity.description or "",
                    })
                population_blocks.append({
                    "program_population_id": population.program_population_id,
                    "population_group_id": population.population_group_id,
                    "population_label": population_group.label if population_group else "Sin clasificación",
                    "rows": rows,
                })
        else:
            population_group = population_group_by_id.get(program.population_group_id)
            activity_ids = sorted(resolve_effective_program_activity_code_ids(db, program.program_id))
            rows = []
            for activity_id in activity_ids:
                activity = activity_code_by_id.get(activity_id)
                if not activity:
                    continue
                rows.append({
                    "activity_code_id": activity.activity_code_id,
                    "activity_code": activity.code,
                    "activity_description": activity.description or "",
                })
            population_blocks.append({
                "program_population_id": None,
                "population_group_id": program.population_group_id,
                "population_label": population_group.label if population_group else "Sin clasificación",
                "rows": rows,
            })

        blocks.append({
            "program": program,
            "program_display_name": program_display_name(program),
            "population_blocks": population_blocks,
        })

    return blocks
