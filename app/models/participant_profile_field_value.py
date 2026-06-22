from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ParticipantProfileFieldValue(Base):
    __tablename__ = "participant_profile_field_values"

    __table_args__ = (
        UniqueConstraint(
            "participant_id",
            "participant_profile_field_id",
            name="uq_participant_profile_field_values_participant_field",
        ),
    )

    participant_profile_field_value_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.participant_id"), nullable=False, index=True)
    participant_profile_field_id: Mapped[int] = mapped_column(
        ForeignKey("participant_profile_fields.participant_profile_field_id"),
        nullable=False,
        index=True,
    )
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
