from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProposalReportProgramPopulationActivityCode(Base):
    __tablename__ = "proposal_report_program_population_activity_codes"
    __table_args__ = (
        UniqueConstraint(
            "program_population_id",
            "activity_code_id",
            name="uq_proposal_report_program_population_activity_codes",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    program_population_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_report_program_populations.program_population_id"),
        nullable=False,
        index=True,
    )
    activity_code_id: Mapped[int] = mapped_column(
        ForeignKey("activity_codes.activity_code_id"),
        nullable=False,
        index=True,
    )
