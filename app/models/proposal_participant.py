from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProposalParticipant(Base):
    __tablename__ = "proposal_participants"

    __table_args__ = (
        UniqueConstraint("proposal_id", "person_id", name="uq_proposal_participants_proposal_person"),
    )

    proposal_participant_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.proposal_id"), nullable=False, index=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.person_id"), nullable=False, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True, index=True)

    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_employee_initials: Mapped[str | None] = mapped_column(String(10), nullable=True)
    exp_seq4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    expediente_num: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    edificio: Mapped[str | None] = mapped_column(String(50), nullable=True)
    apart: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vca: Mapped[str | None] = mapped_column(String(5), nullable=True)
    primera_vez: Mapped[str | None] = mapped_column(String(5), nullable=True)
    composicion_familiar: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estatus: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grupo_familiar: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fuente_ingreso_principal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rango_ingreso: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        onupdate=func.sysutcdatetime(),
        nullable=False,
    )
