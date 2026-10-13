from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, String, Unicode
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FaroAnnouncement(Base):
    __tablename__ = "faro_announcements"
    __table_args__ = (
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="CK_faro_announcement_dates"),
        Index("IX_faro_announcement_visibility", "is_active", "starts_on", "ends_on"),
    )

    announcement_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(Unicode(160))
    message: Mapped[str] = mapped_column(Unicode(4000))
    starts_on: Mapped[date] = mapped_column(Date)
    ends_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class FaroAnnouncementRole(Base):
    __tablename__ = "faro_announcement_roles"
    __table_args__ = (CheckConstraint("role IN ('admin', 'supervisor', 'user', 'viewer')", name="CK_faro_announcement_role"),)

    announcement_id: Mapped[int] = mapped_column(ForeignKey("faro_announcements.announcement_id", ondelete="CASCADE"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), primary_key=True)


class FaroAnnouncementResidential(Base):
    __tablename__ = "faro_announcement_residentials"

    announcement_id: Mapped[int] = mapped_column(ForeignKey("faro_announcements.announcement_id", ondelete="CASCADE"), primary_key=True)
    residential_id: Mapped[int] = mapped_column(ForeignKey("residentials.residential_id"), primary_key=True)


class FaroAnnouncementRead(Base):
    __tablename__ = "faro_announcement_reads"

    announcement_id: Mapped[int] = mapped_column(ForeignKey("faro_announcements.announcement_id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
