"""Independent Comunidad y Prevención records (no Faro participant foreign keys)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Unicode, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CPProgram(Base):
    __tablename__ = "cp_programs"

    program_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    # Keeps case as entered for display, while rejecting ICCa / ICCA duplicates.
    code_key: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CPFiscalYear(Base):
    __tablename__ = "cp_fiscal_years"
    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="CK_cp_fiscal_year_dates"),
        CheckConstraint("status IN ('active', 'closed')", name="CK_cp_fiscal_year_status"),
    )

    fiscal_year_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", server_default="active", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CPUserAccess(Base):
    __tablename__ = "cp_user_access"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'supervisor', 'viewer', 'user')", name="CK_cp_user_access_role"),
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)


class CPUserProgram(Base):
    __tablename__ = "cp_user_programs"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), primary_key=True)


class CPSequence(Base):
    __tablename__ = "cp_sequences"
    __table_args__ = (
        CheckConstraint("exp_year BETWEEN 1000 AND 9999", name="CK_cp_sequence_year"),
        CheckConstraint("last_value BETWEEN 0 AND 9999", name="CK_cp_sequence_value"),
    )

    exp_year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class CPParticipant(Base):
    __tablename__ = "cp_participants"
    __table_args__ = (
        UniqueConstraint("exp_year", "exp_sequence", name="UQ_cp_participant_year_sequence"),
        CheckConstraint("exp_year BETWEEN 1000 AND 9999", name="CK_cp_participant_year"),
        CheckConstraint("exp_sequence BETWEEN 1 AND 9999", name="CK_cp_participant_sequence"),
        CheckConstraint("genero IN ('F', 'M')", name="CK_cp_participant_gender"),
    )

    participant_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    expediente_num: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    exp_year: Mapped[int] = mapped_column(Integer, nullable=False)
    exp_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    inicial: Mapped[str | None] = mapped_column(Unicode(12))
    apellido_paterno: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    apellido_materno: Mapped[str | None] = mapped_column(Unicode(150))
    genero: Mapped[str] = mapped_column(String(10), nullable=False)
    fecha_nacimiento: Mapped[date | None] = mapped_column(Date)
    direccion_fisica: Mapped[str | None] = mapped_column(Unicode(500))
    pueblo: Mapped[str | None] = mapped_column(Unicode(100))
    vca: Mapped[str | None] = mapped_column(String(5))
    primera_vez: Mapped[str | None] = mapped_column(String(5))
    escolaridad_participante: Mapped[str | None] = mapped_column(Unicode(150))
    composicion_familiar: Mapped[str | None] = mapped_column(Unicode(100))
    relacion_familiar: Mapped[str | None] = mapped_column(Unicode(100))
    estatus: Mapped[str | None] = mapped_column(Unicode(50))
    grupo_familiar: Mapped[str | None] = mapped_column(Unicode(20))
    fuente_ingreso_principal: Mapped[str | None] = mapped_column(Unicode(100))
    rango_ingreso: Mapped[str | None] = mapped_column(Unicode(30))
    is_head_of_household: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(30))
    email: Mapped[str | None] = mapped_column(Unicode(255))
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)

    @property
    def exp_seq4(self) -> str:
        return f"{self.exp_sequence:04d}"

    @property
    def edad(self) -> int | None:
        if self.fecha_nacimiento is None:
            return None
        today = date.today()
        born = self.fecha_nacimiento
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class CPParticipantProgram(Base):
    """Permanent record number, independent of future fiscal-year memberships."""

    __tablename__ = "cp_participant_programs"

    participant_id: Mapped[int] = mapped_column(ForeignKey("cp_participants.participant_id"), primary_key=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), primary_key=True)
    record_number: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
