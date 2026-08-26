from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformUserAudit(Base):
    __tablename__ = "platform_user_audit"
    __table_args__ = (
        Index("IX_platform_user_audit_created_at", "created_at"),
        Index("IX_platform_user_audit_target_created", "target_user_id", "created_at"),
        Index("IX_platform_user_audit_actor_created", "actor_user_id", "created_at"),
    )

    audit_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    actor_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    details: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )
