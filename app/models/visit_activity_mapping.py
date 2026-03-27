from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VisitActivityMapping(Base):
    __tablename__ = "visit_activity_mappings"

    __table_args__ = (
        UniqueConstraint("proposal_id", "activity_code_id", name="uq_visit_activity_mappings_proposal_activity"),
    )

    mapping_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.proposal_id"), nullable=False, index=True)
    activity_code_id: Mapped[int] = mapped_column(ForeignKey("activity_codes.activity_code_id"), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), onupdate=func.sysutcdatetime(), nullable=False)
