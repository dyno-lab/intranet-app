from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ParticipantProfileField(Base):
    __tablename__ = "participant_profile_fields"

    __table_args__ = (
        UniqueConstraint("field_key", name="uq_participant_profile_fields_field_key"),
    )

    participant_profile_field_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    field_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    field_type: Mapped[str] = mapped_column(String(30), nullable=False, default="text", server_default="text")
    placeholder: Mapped[str | None] = mapped_column(String(150), nullable=True)
    help_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    validation_pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    applies_to_new_list: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
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
