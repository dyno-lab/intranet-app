from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ActivityCode(Base):
    __tablename__ = "activity_codes"

    activity_code_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("proposals.proposal_id"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
