"""Program-owned activities and fiscal-year ADM configuration for Comunidad."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Unicode, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CPActivity(Base):
    __tablename__ = "cp_activities"
    __table_args__ = (
        UniqueConstraint("program_id", "code_key", name="UQ_cp_activity_program_code"),
        UniqueConstraint("activity_id", "program_id", name="UQ_cp_activity_program"),
    )

    activity_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), nullable=False)
    code: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    code_key: Mapped[str] = mapped_column(Unicode(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Unicode(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CPFiscalActivity(Base):
    __tablename__ = "cp_fiscal_activities"
    __table_args__ = (
        ForeignKeyConstraint(["activity_id", "program_id"], ["cp_activities.activity_id", "cp_activities.program_id"], name="FK_cp_fiscal_activity_program"),
        UniqueConstraint("activity_id", "fiscal_year_id", "program_id", name="UQ_cp_fiscal_activity_context"),
    )

    activity_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_years.fiscal_year_id"), primary_key=True)
    program_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    goal_type: Mapped[str] = mapped_column(String(30), default="none", server_default="none", nullable=False)
    goal_value: Mapped[int | None] = mapped_column(Integer)
    period_goal_value: Mapped[int | None] = mapped_column(Integer)
    goal_is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CPADMServiceType(Base):
    __tablename__ = "cp_adm_service_types"
    __table_args__ = (
        UniqueConstraint("fiscal_year_id", "program_id", "name_key", name="UQ_cp_adm_service_name"),
        UniqueConstraint("adm_service_type_id", "fiscal_year_id", "program_id", name="UQ_cp_adm_service_context"),
    )

    adm_service_type_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("cp_fiscal_years.fiscal_year_id"), nullable=False)
    program_id: Mapped[int] = mapped_column(ForeignKey("cp_programs.program_id"), nullable=False)
    name: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    name_key: Mapped[str] = mapped_column(Unicode(150), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class CPADMServiceActivity(Base):
    """Inactive mappings remain stored; only one mapping per activity/year is active."""

    __tablename__ = "cp_adm_service_activities"
    __table_args__ = (
        ForeignKeyConstraint(["adm_service_type_id", "fiscal_year_id", "program_id"], ["cp_adm_service_types.adm_service_type_id", "cp_adm_service_types.fiscal_year_id", "cp_adm_service_types.program_id"], name="FK_cp_adm_mapping_service"),
        ForeignKeyConstraint(["activity_id", "fiscal_year_id", "program_id"], ["cp_fiscal_activities.activity_id", "cp_fiscal_activities.fiscal_year_id", "cp_fiscal_activities.program_id"], name="FK_cp_adm_mapping_activity"),
        UniqueConstraint("adm_service_type_id", "activity_id", name="UQ_cp_adm_service_activity"),
        Index("UQ_cp_adm_active_activity", "fiscal_year_id", "activity_id", unique=True, mssql_where=text("is_active = 1"), sqlite_where=text("is_active = 1")),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    adm_service_type_id: Mapped[int] = mapped_column(Integer, nullable=False)
    activity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_year_id: Mapped[int] = mapped_column(Integer, nullable=False)
    program_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


COMMUNITY_ACTIVITY_MODELS = (CPActivity, CPFiscalActivity, CPADMServiceType, CPADMServiceActivity)
