"""Fiscal participation and historical demographics, separate from permanent records."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Unicode, UnicodeText, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.community import _utcnow


class CPFiscalState(Base):
    __tablename__ = "cp_fiscal_states"

    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_years.fiscal_year_id"), primary_key=True)
    snapshots_frozen: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    locked_through: Mapped[date | None] = mapped_column(Date)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class CPFiscalParticipant(Base):
    __tablename__ = "cp_fiscal_participants"

    participant_id: Mapped[int] = mapped_column(ForeignKey("cp_participants.participant_id"), primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_years.fiscal_year_id"), primary_key=True)
    snapshot_json: Mapped[str] = mapped_column(UnicodeText, nullable=False)
    updated_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)


class CPFiscalEnrollment(Base):
    __tablename__ = "cp_fiscal_enrollments"
    __table_args__ = (
        UniqueConstraint("participant_id", "program_id", "fiscal_year_id", name="UQ_cp_enrollment_participant_program_year"),
        ForeignKeyConstraint(["participant_id", "program_id"],
                             ["cp_participant_programs.participant_id", "cp_participant_programs.program_id"],
                             name="FK_cp_enrollment_permanent_program"),
        ForeignKeyConstraint(["participant_id", "fiscal_year_id"],
                             ["cp_fiscal_participants.participant_id", "cp_fiscal_participants.fiscal_year_id"],
                             name="FK_cp_enrollment_snapshot"),
    )

    enrollment_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("cp_participants.participant_id"), nullable=False)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), nullable=False)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_years.fiscal_year_id"), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CPEnrollmentPeriod(Base):
    """The end date is exclusive: a discharge stops participation that same day."""

    __tablename__ = "cp_enrollment_periods"
    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="CK_cp_enrollment_period_dates"),
        UniqueConstraint("enrollment_id", "start_date", name="UQ_cp_enrollment_period_start"),
    )

    period_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_enrollments.enrollment_id"), nullable=False, index=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Unicode(250), nullable=False)
    observation: Mapped[str | None] = mapped_column(Unicode(1000))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    end_reason: Mapped[str | None] = mapped_column(Unicode(250))
    end_observation: Mapped[str | None] = mapped_column(Unicode(1000))
    ended_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
