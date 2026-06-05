from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Proposal(Base):
    __tablename__ = "proposals"

    proposal_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.user_id"), nullable=True)
    finalization_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    locked_through_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locked_through_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    period_lock_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        onupdate=func.sysutcdatetime(),
        nullable=False,
    )
