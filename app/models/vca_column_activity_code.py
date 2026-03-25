from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class VCAColumnActivityCode(Base):
    __tablename__ = "vca_column_activity_codes"
    __table_args__ = (
        UniqueConstraint("vca_column_id", "activity_code_id", name="uq_vca_column_activity_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    vca_column_id: Mapped[int] = mapped_column(ForeignKey("vca_columns.vca_column_id"), nullable=False, index=True)
    activity_code_id: Mapped[int] = mapped_column(ForeignKey("activity_codes.activity_code_id"), nullable=False, index=True)
