from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.record_identifiers import build_session_control_number
from app.models.activity_session import ActivitySession


def persist_session_control_number(
    db: Session,
    activity_session: ActivitySession,
    residential_code: str,
) -> str:
    """Store a generated control number without an ORM-managed UPDATE."""
    if activity_session.session_id is None:
        raise ValueError("La sesión debe existir antes de generar su número de control.")

    control_number = build_session_control_number(
        residential_code=residential_code,
        session_id=activity_session.session_id,
        session_date=activity_session.session_date,
    )

    # SQL Server drivers can report -1 affected rows for this UPDATE. SQLAlchemy's
    # ORM treats that value as stale data, while a Core UPDATE safely preserves
    # the same transaction without relying on the driver's row count.
    table = ActivitySession.__table__
    db.execute(
        table.update()
        .where(table.c.session_id == activity_session.session_id)
        .values(control_number=control_number)
    )
    return control_number
