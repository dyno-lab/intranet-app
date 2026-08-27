from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Participant(Base):
    __tablename__ = "participants"

    __table_args__ = (
        Index(
            "UX_participants_residential_seq4",
            "residential_id",
            "exp_seq4",
            unique=True,
            mssql_where=text("residential_id IS NOT NULL AND exp_seq4 IS NOT NULL"),
        ),
    )

    participant_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Propiedad residencial histórica y auditoría del usuario creador.
    residential_id: Mapped[int | None] = mapped_column(
        ForeignKey("residentials.residential_id"),
        nullable=True,
        index=True,
    )
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Expediente (FASE 2)
    # Formato: FE-YYYY-{CODIGO_RESIDENCIAL}-####
    # Regla: #### es único por residencial, sin importar el año o usuario.
    exp_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exp_employee_initials: Mapped[str | None] = mapped_column(String(20), nullable=True)
    exp_seq4: Mapped[str | None] = mapped_column(String(4), nullable=True)

    # Identificación / Nombre
    expediente_num: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    inicial: Mapped[str | None] = mapped_column(String(12), nullable=True)
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
    escolaridad_participante: Mapped[str | None] = mapped_column(String(150), nullable=True)
    composicion_familiar: Mapped[str | None] = mapped_column(String(100), nullable=True)
    relacion_familiar: Mapped[str | None] = mapped_column(String(100), nullable=True)
    estatus: Mapped[str | None] = mapped_column(String(50), nullable=True)
    grupo_familiar: Mapped[str | None] = mapped_column(String(20), nullable=True)
    fuente_ingreso_principal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rango_ingreso: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_head_of_household: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
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
