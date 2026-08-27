from __future__ import annotations

from datetime import date


def normalized_residential_code(value: str | None) -> str:
    return (value or "").strip().upper()


def build_expediente_number(*, year: int, residential_code: str, sequence: str) -> str:
    return f"FE-{year}-{normalized_residential_code(residential_code)}-{sequence}"


def build_session_control_number(
    *,
    residential_code: str,
    session_id: int,
    session_date: date,
) -> str:
    return f"{normalized_residential_code(residential_code)}{session_id}{session_date.year}"
