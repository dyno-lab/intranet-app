from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import Date, DateTime, Float, ForeignKey, func, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ActivitySession(Base):
    __tablename__ = "activity_sessions"

    session_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Ownership (para roles/aislamiento)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Datos de la actividad/sesión
    session_date: Mapped[date] = mapped_column(Date, nullable=False)

    activity_code_id: Mapped[int] = mapped_column(
        ForeignKey("activity_codes.activity_code_id"),
        nullable=False,
        index=True,
    )

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.employee_id"),
        nullable=False,
        index=True,
    )

    proposal_id: Mapped[int | None] = mapped_column(
        ForeignKey("proposals.proposal_id"),
        nullable=True,
        index=True,
    )

    hours: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Auditoría
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )