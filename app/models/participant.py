from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import String, Date, DateTime, func, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Participant(Base):
    __tablename__ = "participants"

    __table_args__ = (
        # FASE 2: 4 dígitos únicos por empleado (created_by_user_id)
        UniqueConstraint("created_by_user_id", "exp_seq4", name="uq_participants_employee_seq4"),
    )

    participant_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Ownership (para roles/aislamiento)
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Expediente (FASE 2)
    # Formato: FE-YYYY-XX-####
    # Regla: #### (exp_seq4) es único por empleado (created_by_user_id), sin importar el año.
    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_employee_initials: Mapped[str | None] = mapped_column(String(10), nullable=True)
    exp_seq4: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # Identificación / Nombre
    expediente_num: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    inicial: Mapped[str | None] = mapped_column(String(10), nullable=True)
    apellido_paterno: Mapped[str] = mapped_column(String(150), nullable=False)
    apellido_materno: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Demográficos básicos
    genero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Ubicación
    edificio: Mapped[str | None] = mapped_column(String(50), nullable=True)
    apart: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Campos extra “New List”
    vca: Mapped[str | None] = mapped_column(String(5), nullable=True)  # SI / NO
    primera_vez: Mapped[str | None] = mapped_column(String(5), nullable=True)  # SI / NO
    composicion_familiar: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estatus: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grupo_familiar: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fuente_ingreso_principal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rango_ingreso: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    # Auditoría
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