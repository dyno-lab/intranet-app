from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserPlatformPermission(Base):
    __tablename__ = "user_platform_permissions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "permission_id",
            name="UX_user_platform_permissions_user_permission",
        ),
        Index("IX_user_platform_permissions_permission_id", "permission_id"),
        Index("IX_user_platform_permissions_granted_by_user_id", "granted_by_user_id"),
    )

    user_platform_permission_id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=False,
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("platform_permissions.permission_id"),
        nullable=False,
    )
    granted_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )

    user = relationship("User", foreign_keys=[user_id])
    permission = relationship("PlatformPermission")
    granted_by_user = relationship("User", foreign_keys=[granted_by_user_id])
