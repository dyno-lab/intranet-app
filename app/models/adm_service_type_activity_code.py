from __future__ import annotations

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ADMServiceTypeActivityCode(Base):
    __tablename__ = "adm_service_type_activity_codes"
    __table_args__ = (
        UniqueConstraint("adm_service_type_id", "activity_code_id", name="uq_adm_service_type_activity_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    adm_service_type_id: Mapped[int] = mapped_column(ForeignKey("adm_service_types.adm_service_type_id"), nullable=False, index=True)
    activity_code_id: Mapped[int] = mapped_column(ForeignKey("activity_codes.activity_code_id"), nullable=False, index=True)
