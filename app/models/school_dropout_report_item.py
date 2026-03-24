from sqlalchemy import Integer, ForeignKey, DateTime, func, UniqueConstraint, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SchoolDropoutReportItem(Base):
    __tablename__ = "school_dropout_report_items"

    __table_args__ = (
        UniqueConstraint("report_id", "participant_id", name="uq_school_dropout_report_items_participant"),
    )

    report_item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("school_dropout_reports.report_id"), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"), nullable=False, index=True)
    attended_tutoring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    current_grade: Mapped[str | None] = mapped_column(String(20), nullable=True)
    attended_school: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    report_10_weeks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    report_20_weeks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    report_30_weeks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    report_40_weeks: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), onupdate=func.sysutcdatetime(), nullable=False)
