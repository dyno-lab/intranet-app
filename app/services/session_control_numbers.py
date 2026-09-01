from __future__ import annotations

from datetime import date

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


def update_session_fields(
    db: Session,
    activity_session: ActivitySession,
    residential_code: str | None,
    *,
    session_date: date,
    activity_code_id: int,
    employee_id: int,
    proposal_id: int | None,
    hours: float | None,
) -> str | None:
    """Update a session without an ORM-managed row-count check."""
    if activity_session.session_id is None:
        raise ValueError("La sesión debe existir antes de actualizarse.")

    values: dict[str, object] = {
        "session_date": session_date,
        "activity_code_id": activity_code_id,
        "employee_id": employee_id,
        "proposal_id": proposal_id,
        "hours": hours,
    }
    control_number = None
    if (residential_code or "").strip():
        control_number = build_session_control_number(
            residential_code=residential_code or "",
            session_id=activity_session.session_id,
            session_date=session_date,
        )
        values["control_number"] = control_number

    table = ActivitySession.__table__
    db.execute(
        table.update()
        .where(table.c.session_id == activity_session.session_id)
        .values(**values)
    )
    return control_number
