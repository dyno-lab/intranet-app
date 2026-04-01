from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProposalReportProgramPopulation(Base):
    __tablename__ = "proposal_report_program_populations"
    __table_args__ = (
        UniqueConstraint(
            "program_id",
            "population_group_id",
            name="uq_proposal_report_program_populations_program_population",
        ),
    )

    program_population_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_report_programs.program_id"),
        nullable=False,
        index=True,
    )
    population_group_id: Mapped[int] = mapped_column(
        ForeignKey("proposal_population_groups.population_group_id"),
        nullable=False,
        index=True,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )
