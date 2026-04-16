from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ActivityProductivityGoal(Base):
    __tablename__ = "activity_productivity_goals"

    __table_args__ = (
        UniqueConstraint("proposal_id", "activity_code_id", name="uq_activity_productivity_goals_proposal_activity"),
    )

    productivity_goal_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.proposal_id"), nullable=False, index=True)
    activity_code_id: Mapped[int] = mapped_column(ForeignKey("activity_codes.activity_code_id"), nullable=False, index=True)
    goal_type: Mapped[str] = mapped_column(String(50), nullable=False, default="none", server_default="none")
    goal_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_goal_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), nullable=False)
    updated_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime(), onupdate=func.sysutcdatetime(), nullable=False)
