from sqlalchemy import ForeignKey, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class Attendance(Base):
    __tablename__ = "attendance"

    attendance_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.participant_id"), index=True, nullable=True)
    proposal_participant_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposal_participants.proposal_participant_id"),
        index=True,
        nullable=True,
    )
    session_id: Mapped[int] = mapped_column(ForeignKey("activity_sessions.session_id"), index=True)

    attended: Mapped[bool] = mapped_column(Boolean, default=True)
    marked_at: Mapped["DateTime"] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime())
    marked_by: Mapped[str | None] = mapped_column(nullable=True)