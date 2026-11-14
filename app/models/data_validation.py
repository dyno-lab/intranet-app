"""Faro validation tracking; source records are never changed by this module."""
from datetime import date, datetime, timezone
from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Unicode, UnicodeText, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class DataValidationIssue(Base):
    __tablename__ = "faro_validation_issues"
    __table_args__ = (
        Index("IX_faro_validation_scope", "proposal_id", "residential_id", "session_date"),
        CheckConstraint("status IN ('pending','review','resolved','justified')", name="CK_faro_validation_status"),
    )
    issue_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.proposal_id"))
    residential_id: Mapped[int | None] = mapped_column(ForeignKey("residentials.residential_id"), nullable=True)
    other_residential_id: Mapped[int | None] = mapped_column(ForeignKey("residentials.residential_id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20))
    session_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    evidence_json: Mapped[str] = mapped_column(UnicodeText)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    assignee: Mapped[str | None] = mapped_column(String(20), nullable=True)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    justification: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DataValidationEvent(Base):
    __tablename__ = "faro_validation_events"
    __table_args__ = (Index("IX_faro_validation_event_issue", "issue_key", "event_id"),)
    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    issue_key: Mapped[str] = mapped_column(ForeignKey("faro_validation_issues.issue_key"))
    actor_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    actor_name: Mapped[str] = mapped_column(Unicode(255))
    kind: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Unicode(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
