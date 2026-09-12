"""Proposal selection shared by read-only consolidated reports."""
from __future__ import annotations

from fastapi import HTTPException


def proposal_ids(value) -> list[int]:
    if value is None:
        return []
    values = value if isinstance(value, (list, tuple, set)) else [value]
    try:
        ids = sorted({int(item) for item in values})
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Selecciona propuestas válidas.")
    if any(item <= 0 for item in ids):
        raise HTTPException(status_code=422, detail="Selecciona propuestas válidas.")
    return ids


def primary_proposal_id(value) -> int | None:
    ids = proposal_ids(value)
    return ids[0] if ids else None


def proposal_filter(column, value):
    ids = proposal_ids(value)
    return column == ids[0] if len(ids) == 1 else column.in_(ids)


def report_proposal_selection(request, fallback=None):
    params = getattr(request, "query_params", None)
    values = params.getlist("proposal_id") if params is not None else []
    ids = proposal_ids(values if values else fallback)
    return ids if len(ids) > 1 else (ids[0] if ids else None)
