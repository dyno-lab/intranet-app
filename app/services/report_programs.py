from __future__ import annotations

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.proposal_report_program import ProposalReportProgram
from app.models.proposal_report_program_activity import ProposalReportProgramActivity
from app.models.proposal_report_program_activity_code import ProposalReportProgramActivityCode
from app.models.proposal_report_program_population import ProposalReportProgramPopulation
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
