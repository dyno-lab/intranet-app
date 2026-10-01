"""Human decisions about matching Faro and Community identities; never merged records."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Unicode, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.community import _utcnow


class CPIdentityReview(Base):
    __tablename__ = "cp_identity_reviews"
    __table_args__ = (
        UniqueConstraint("cp_participant_id", "faro_participant_id", name="UQ_cp_identity_pair"),
        CheckConstraint("reviewed_from IN ('community', 'faro')", name="CK_cp_identity_source"),
        Index("UQ_cp_identity_confirmed_community", "cp_participant_id", unique=True,
              mssql_where=text("is_same_person = 1"), sqlite_where=text("is_same_person = 1")),
        Index("UQ_cp_identity_confirmed_faro", "faro_participant_id", unique=True,
              mssql_where=text("is_same_person = 1"), sqlite_where=text("is_same_person = 1")),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cp_participant_id: Mapped[int] = mapped_column(ForeignKey("cp_participants.participant_id"), nullable=False)
    faro_participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"), nullable=False)
    is_same_person: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reviewed_from: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    comparison_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text('0'), nullable=False)
    revision: Mapped[int] = mapped_column(default=1, server_default=text('1'), nullable=False)


class CPIdentityReviewEvent(Base):
    """Append-only history, including decisions reopened by a supervisor."""
    __tablename__ = 'cp_identity_review_events'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(ForeignKey('cp_identity_reviews.id'), nullable=False, index=True)
    previous_decision: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    decision: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    comparison_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_from: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewed_by_user_id: Mapped[int] = mapped_column(ForeignKey('users.user_id'), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    reason: Mapped[str | None] = mapped_column(Unicode(500), nullable=True)
