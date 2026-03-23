from sqlalchemy import Integer, ForeignKey, DateTime, func, UniqueConstraint, Boolean, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SchoolGradeReportItem(Base):
    __tablename__ = "school_grade_report_items"

    __table_args__ = (
        UniqueConstraint("report_id", "participant_id", name="uq_school_grade_report_items_participant"),
    )

    report_item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("school_grade_reports.report_id"), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"), nullable=False, index=True)
    grade_level: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_content_room: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    spanish_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    english_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    math_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    science_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    social_studies_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    elective_1_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    elective_2_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    elective_3_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    elective_4_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    average_grade: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), onupdate=func.sysutcdatetime(), nullable=False)
