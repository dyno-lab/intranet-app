from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ParticipantMonthlyCourse(Base):
    """One Faro 2.b.5 course per existing participant identity and calendar month."""

    __tablename__ = "participant_monthly_courses"
    __table_args__ = (
        CheckConstraint("report_month BETWEEN 1 AND 12", name="CK_monthly_course_month"),
        CheckConstraint("report_year BETWEEN 2000 AND 2100", name="CK_monthly_course_year"),
        CheckConstraint("course_code IS NULL OR course_code IN ('reposteria', 'charcuteria', 'campo_laboral')", name="CK_monthly_course_code"),
    )

    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id", ondelete="CASCADE"), primary_key=True)
    report_year: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_month: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
