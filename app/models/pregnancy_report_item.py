from sqlalchemy import Integer, ForeignKey, DateTime, func, UniqueConstraint, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PregnancyReportItem(Base):
    __tablename__ = "pregnancy_report_items"

    __table_args__ = (
        UniqueConstraint("report_id", "participant_id", name="uq_pregnancy_report_items_participant"),
    )

    report_item_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("pregnancy_reports.report_id"), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"), nullable=False, index=True)
    participated_workshops: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    is_pregnant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    gestation_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    has_children: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    children_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    children_ages: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), onupdate=func.sysutcdatetime(), nullable=False)
