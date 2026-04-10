from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Person(Base):
    __tablename__ = "persons"

    person_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    inicial: Mapped[str | None] = mapped_column(String(10), nullable=True)
    apellido_paterno: Mapped[str] = mapped_column(String(150), nullable=False)
    apellido_materno: Mapped[str | None] = mapped_column(String(150), nullable=True)
    genero: Mapped[str | None] = mapped_column(String(10), nullable=True)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date, nullable=True)
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
