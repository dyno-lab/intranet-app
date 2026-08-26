from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserResidential(Base):
    __tablename__ = "user_residentials"
    __table_args__ = (
        UniqueConstraint("user_id", "residential_id", name="UX_user_residentials_user_residential"),
        Index("IX_user_residentials_user_active", "user_id", "is_active"),
        Index("IX_user_residentials_residential_active", "residential_id", "is_active"),
    )

    user_residential_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    residential_id: Mapped[int] = mapped_column(
        ForeignKey("residentials.residential_id"),
        nullable=False,
    )
    assigned_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )

    residential = relationship("Residential")
