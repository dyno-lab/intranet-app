"""Human decisions about matching Faro and Community identities; never merged records."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
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
