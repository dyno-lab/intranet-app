"""Activity attendance and monthly school grades owned by Community programs."""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.community import _utcnow


GRADE_FIELDS = (
    "spanish_grade", "english_grade", "math_grade", "science_grade", "social_studies_grade",
    "elective_1_grade", "elective_2_grade", "elective_3_grade", "elective_4_grade",
)


class CPActivitySession(Base):
    __tablename__ = "cp_activity_sessions"
    __table_args__ = (
        ForeignKeyConstraint(["activity_id", "fiscal_year_id", "program_id"],
                             ["cp_fiscal_activities.activity_id", "cp_fiscal_activities.fiscal_year_id", "cp_fiscal_activities.program_id"],
                             name="FK_cp_session_fiscal_activity"),
        Index("IX_cp_session_period_program", "fiscal_year_id", "program_id", "session_date"),
    )

    session_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_years.fiscal_year_id"), nullable=False)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), nullable=False)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Unicode(500))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)

    @property
    def control_number(self) -> str:
        return f"CP-{self.session_id}"


class CPAttendance(Base):
    __tablename__ = "cp_attendance"

    session_id: Mapped[int] = mapped_column(ForeignKey("cp_activity_sessions.session_id"), primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("cp_participants.participant_id"), primary_key=True)
    is_present: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class CPGradeReport(Base):
    __tablename__ = "cp_grade_reports"
    __table_args__ = (
        UniqueConstraint("fiscal_year_id", "program_id", "report_year", "report_month", name="UQ_cp_grade_report_period"),
        CheckConstraint("report_month BETWEEN 1 AND 12", name="CK_cp_grade_report_month"),
        CheckConstraint("report_year BETWEEN 1000 AND 9999", name="CK_cp_grade_report_year"),
    )

    report_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_years.fiscal_year_id"), nullable=False)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), nullable=False)
    report_month: Mapped[int] = mapped_column(Integer, nullable=False)
    report_year: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str | None] = mapped_column(Unicode(500))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class CPGradeItem(Base):
    __tablename__ = "cp_grade_items"
    __table_args__ = tuple(
        CheckConstraint(f"{field} IS NULL OR {field} BETWEEN 0 AND 100", name=f"CK_cp_grade_{field}")
        for field in (*GRADE_FIELDS, "average_grade")
    )

    report_id: Mapped[int] = mapped_column(ForeignKey("cp_grade_reports.report_id"), primary_key=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("cp_participants.participant_id"), primary_key=True)
    grade_level: Mapped[str | None] = mapped_column(String(20))
    is_content_room: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    spanish_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    english_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    math_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    science_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    social_studies_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    elective_1_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    elective_2_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    elective_3_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    elective_4_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    average_grade: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


COMMUNITY_OPERATION_MODELS = (CPActivitySession, CPAttendance, CPGradeReport, CPGradeItem)
