"""Residential transfers retain identity, local record numbers and audit history."""
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ParticipantResidentialNumber(Base):
    __tablename__ = "participant_residential_numbers"
    __table_args__ = (Index("UX_participant_residential_number", "residential_id", "sequence", unique=True,
                           mssql_where=text("sequence IS NOT NULL"), sqlite_where=text("sequence IS NOT NULL")),)

    number_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"), index=True)
    residential_id: Mapped[int] = mapped_column(ForeignKey("residentials.residential_id"))
    sequence: Mapped[str | None] = mapped_column(String(4), nullable=True)
    expediente_num: Mapped[str] = mapped_column(String(50), unique=True)
    exp_year: Mapped[int] = mapped_column(Integer)


class ParticipantTransfer(Base):
    __tablename__ = "participant_transfers"

    transfer_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"), index=True)
    from_residential_id: Mapped[int] = mapped_column(ForeignKey("residentials.residential_id"))
    to_residential_id: Mapped[int] = mapped_column(ForeignKey("residentials.residential_id"))
    effective_date: Mapped[date] = mapped_column(Date)
    old_expediente_num: Mapped[str] = mapped_column(String(50))
    new_expediente_num: Mapped[str] = mapped_column(String(50))
    proposal_codes: Mapped[str] = mapped_column(String(1000))
    reason: Mapped[str] = mapped_column(String(500))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime())
