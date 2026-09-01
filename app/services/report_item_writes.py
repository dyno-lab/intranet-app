from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session


def update_report_item_fields(
    db: Session,
    model: Any,
    report_item_id: int,
    values: Mapping[str, Any],
) -> None:
    """Update a school report item without an ORM-managed row-count check."""
    table = model.__table__
    db.execute(
        table.update()
        .where(table.c.report_item_id == report_item_id)
        .values(**dict(values))
    )


def delete_report_item(
    db: Session,
    model: Any,
    report_item_id: int,
) -> None:
    """Delete a school report item without an ORM-managed row-count check."""
    table = model.__table__
    db.execute(
        table.delete().where(table.c.report_item_id == report_item_id)
    )
