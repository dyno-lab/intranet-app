from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PregnancyReport(Base):
    __tablename__ = "pregnancy_reports"

    __table_args__ = (
        Index(
            "UX_pregnancy_reports_period_residential",
            "proposal_id",
            "report_month",
            "report_year",
            "residential_id",
            unique=True,
            mssql_where=text("residential_id IS NOT NULL"),
        ),
    )

    report_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.proposal_id"), nullable=False, index=True)
    report_month: Mapped[int] = mapped_column(Integer, nullable=False)
    report_year: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    residential_id: Mapped[int | None] = mapped_column(ForeignKey("residentials.residential_id"), nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), onupdate=func.sysutcdatetime(), nullable=False)
