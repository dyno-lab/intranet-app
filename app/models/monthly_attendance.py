"""Explicit monthly attendance handoff; independent of administrative period locks."""
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Unicode
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


def utcnow():
    return datetime.now(timezone.utc)


class MonthlyAttendanceSettings(Base):
    __tablename__ = 'monthly_attendance_settings'
    __table_args__ = (CheckConstraint('settings_id = 1', name='CK_monthly_attendance_settings_singleton'),)
    settings_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    first_month: Mapped[date] = mapped_column(Date)


class AttendanceMonth(Base):
    __tablename__ = 'attendance_months'
    __table_args__ = (CheckConstraint('report_month BETWEEN 1 AND 12 AND report_year BETWEEN 2000 AND 2100', name='CK_attendance_month_period'),)
    proposal_id: Mapped[int] = mapped_column(ForeignKey('proposals.proposal_id'), primary_key=True)
    report_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_month: Mapped[int] = mapped_column(Integer, primary_key=True)
    due_on: Mapped[date] = mapped_column(Date)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    all_announcement_id: Mapped[int | None] = mapped_column(ForeignKey('faro_announcements.announcement_id'), nullable=True)


class AttendanceMonthResidential(Base):
    __tablename__ = 'attendance_month_residentials'
    __table_args__ = (ForeignKeyConstraint(
        ['proposal_id', 'report_year', 'report_month'],
        ['attendance_months.proposal_id', 'attendance_months.report_year', 'attendance_months.report_month']),)
    proposal_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_month: Mapped[int] = mapped_column(Integer, primary_key=True)
    residential_id: Mapped[int] = mapped_column(ForeignKey('residentials.residential_id'), primary_key=True)
    is_included: Mapped[bool] = mapped_column(Boolean, default=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.user_id'), nullable=True)
    confirmed_by_name: Mapped[str | None] = mapped_column(Unicode(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    no_activity: Mapped[bool] = mapped_column(Boolean, default=False)
    confirmed_sessions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmed_participations: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confirmation_announcement_id: Mapped[int | None] = mapped_column(ForeignKey('faro_announcements.announcement_id'), nullable=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_announcement_id: Mapped[int | None] = mapped_column(ForeignKey('faro_announcements.announcement_id'), nullable=True)


class AttendanceMonthEvent(Base):
    __tablename__ = 'attendance_month_events'
    __table_args__ = (
        ForeignKeyConstraint(['proposal_id', 'report_year', 'report_month'],
            ['attendance_months.proposal_id', 'attendance_months.report_year', 'attendance_months.report_month']),
        Index('IX_attendance_month_events_period', 'proposal_id', 'report_year', 'report_month', 'event_id'),
    )
    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(Integer)
    report_year: Mapped[int] = mapped_column(Integer)
    report_month: Mapped[int] = mapped_column(Integer)
    residential_id: Mapped[int | None] = mapped_column(ForeignKey('residentials.residential_id'), nullable=True)
    kind: Mapped[str] = mapped_column(String(30))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'))
    actor_name: Mapped[str] = mapped_column(Unicode(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    message: Mapped[str] = mapped_column(Unicode(2000))
    announcement_id: Mapped[int | None] = mapped_column(ForeignKey('faro_announcements.announcement_id'), nullable=True)
