from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VisitReportReferral(Base):
    __tablename__ = "visit_report_referrals"

    referral_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("visit_reports.report_id"), nullable=False, index=True)
    referral_type: Mapped[str] = mapped_column(String(20), nullable=False)
    agency: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reference_or_purpose: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), onupdate=func.sysutcdatetime(), nullable=False)
