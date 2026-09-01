from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("UX_users_email", "email", unique=True, mssql_where=text("email IS NOT NULL")),
        Index(
            "UX_users_google_sub",
            "google_sub",
            unique=True,
            mssql_where=text("google_sub IS NOT NULL"),
        ),
    )

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    local_login_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("1"),
    )
    session_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
    )

    # Roles esperados: "admin" | "supervisor" | "viewer" | "user"
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="user")

    residential_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("residentials.residential_id"),
        nullable=True,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )

    residential = relationship("Residential")
