from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    report_template_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )


class ReportTemplateVersion(Base):
    __tablename__ = "report_template_versions"

    report_template_version_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    report_template_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_templates.report_template_id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )


class ProposalReportTemplate(Base):
    __tablename__ = "proposal_report_templates"

    proposal_report_template_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(Integer, ForeignKey("proposals.proposal_id"), nullable=False)
    report_key: Mapped[str] = mapped_column(String(80), nullable=False)
    report_template_version_id: Mapped[int] = mapped_column(Integer, ForeignKey("report_template_versions.report_template_version_id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.sysutcdatetime(),
        nullable=False,
    )
