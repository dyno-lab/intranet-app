"""Community announcements are scoped to Community roles and programs."""
from datetime import date, datetime
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Unicode
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base
from app.models.community import _utcnow


class CPAnnouncement(Base):
    __tablename__ = "cp_announcements"
    __table_args__ = (
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="CK_cp_announcement_dates"),
        Index("IX_cp_announcement_visibility", "is_active", "starts_on", "ends_on"),
    )
    announcement_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Unicode(160))
    message: Mapped[str] = mapped_column(Unicode(4000))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    withdrawn_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CPAnnouncementRole(Base):
    __tablename__ = "cp_announcement_roles"
    __table_args__ = (CheckConstraint("role IN ('admin', 'supervisor', 'user', 'viewer')", name="CK_cp_announcement_role"),)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("cp_announcements.announcement_id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), primary_key=True)


class CPAnnouncementProgram(Base):
    __tablename__ = "cp_announcement_programs"
    announcement_id: Mapped[int] = mapped_column(ForeignKey("cp_announcements.announcement_id", ondelete="CASCADE"), primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), primary_key=True)


class CPAnnouncementRead(Base):
    __tablename__ = "cp_announcement_reads"
    announcement_id: Mapped[int] = mapped_column(ForeignKey("cp_announcements.announcement_id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
