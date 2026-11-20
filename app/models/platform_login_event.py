from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Unicode, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PlatformLoginEvent(Base):
    __tablename__ = "platform_login_events"
    __table_args__ = (
        Index("IX_login_event_user_result_time", "user_id", "outcome", "occurred_at"),
        Index("IX_login_event_result_id", "outcome", "event_id"),
    )

    event_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    identifier: Mapped[str | None] = mapped_column(Unicode(320))
    method: Mapped[str] = mapped_column(String(10))
    outcome: Mapped[str] = mapped_column(String(32))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.sysutcdatetime())
