from __future__ import annotations

import math
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.proposal_report_program import ProposalReportProgram
from app.models.user import User
from app.services.consolidado_mensual_service import build_consolidado_mensual_global
from app.services.report_programs import program_display_name

FALLBACK_PROGRAM_COLUMNS = [
    {"code": "1-A", "label": "Programa 1-A"},
    {"code": "2-B", "label": "Programa 2-B"},
    {"code": "3-C", "label": "Programa 3-C"},
    {"code": "4-D", "label": "Programa 4-D"},
]
CHART_COLORS = [
    "#5B9BD5", "#ED7D31", "#A5A5A5", "#FFC000", "#4472C4", "#70AD47",
    "#264478", "#9E480E", "#636363", "#997300", "#255E91", "#43682B",
    "#7F7F7F", "#C55A11", "#2F75B5", "#548235", "#BF9000", "#7030A0",
]


def _polar_to_cartesian(cx: float, cy: float, radius: float, angle_degrees: float) -> tuple[float, float]:
    angle_radians = math.radians(angle_degrees - 90)
    return cx + (radius * math.cos(angle_radians)), cy + (radius * math.sin(angle_radians))


def _pie_path(cx: float, cy: float, radius: float, start_angle: float, end_angle: float) -> str:
    start_x, start_y = _polar_to_cartesian(cx, cy, radius, end_angle)
    end_x, end_y = _polar_to_cartesian(cx, cy, radius, start_angle)
    large_arc_flag = 1 if end_angle - start_angle > 180 else 0
    return f"M {cx:.2f} {cy:.2f} L {start_x:.2f} {start_y:.2f} A {radius:.2f} {radius:.2f} 0 {large_arc_flag} 0 {end_x:.2f} {end_y:.2f} Z"


def _chart_segments(rows: list[dict[str, Any]], total: int) -> list[dict[str, Any]]:
    if not rows or total <= 0:
        return []
    cx, cy, radius = 430.0, 210.0, 145.0
    label_radius = 210.0
    start_angle = 0.0
    segments = []
    for index, row in enumerate(rows):
        value = int(row.get("total_participation") or 0)
        if value <= 0:
            continue
        angle = (value / total) * 360.0
        end_angle = start_angle + angle
        mid_angle = start_angle + (angle / 2.0)
        label_x, label_y = _polar_to_cartesian(cx, cy, label_radius, mid_angle)
        percent = round((value / total) * 100)
        segments.append({
            "path": _pie_path(cx, cy, radius, start_angle, end_angle),
            "color": CHART_COLORS[index % len(CHART_COLORS)],
            "label_x": label_x,
            "label_y": label_y,
            "anchor": "end" if label_x < cx else "start",
            "name": row.get("residential_name", ""),
            "percent": percent,
        })
        start_angle = end_angle
    return segments


def _program_columns(db: Session, proposal_id: int | None, base: dict[str, Any]) -> list[dict[str, str]]:
    if proposal_id:
        programs = db.execute(
            select(ProposalReportProgram)
            .where(
                ProposalReportProgram.proposal_id == proposal_id,
                ProposalReportProgram.is_active == True,  # noqa: E712
            )
            .order_by(ProposalReportProgram.sort_order, ProposalReportProgram.code)
        ).scalars().all()
        if programs:
            return [
                {"code": program.code, "label": program_display_name(program) or program.code}
                for program in programs
            ]

    labels = base.get("program_labels") or {}
    discovered_codes: list[str] = []
    for row in base.get("rows", []):
        for program in row.get("programs", []):
            code = program.get("code")
            if code and code != "SIN_PROGRAMA" and code not in discovered_codes:
                discovered_codes.append(code)
    if discovered_codes:
        return [{"code": code, "label": labels.get(code, code)} for code in discovered_codes]
    return FALLBACK_PROGRAM_COLUMNS.copy()


def build_plantilla_duplicado_context(
    db: Session,
    *,
    month: int | None,
    year: int | None,
    period_type: str = "monthly",
    start_date: str | None = None,
    end_date: str | None = None,
    proposal_id: int | None = None,
    residential_id: int | None = None,
    current_user: User | None = None,
) -> dict[str, Any]:
    base = build_consolidado_mensual_global(
        db,
        month=month,
        year=year,
        period_type=period_type,
        start_date=start_date,
        end_date=end_date,
        proposal_id=proposal_id,
        residential_id=residential_id,
        current_user=current_user,
    )
    program_columns = _program_columns(db, proposal_id, base)
    program_codes = [column["code"] for column in program_columns]

    rows = []
    totals = {
        "programs": {code: 0 for code in program_codes},
        "total_participation": 0,
        "unique_participants": 0,
        "total_services": 0,
    }

    for item in base.get("rows", []):
        program_by_code = {program.get("code"): program for program in item.get("programs", [])}
        program_values = {
            code: int(program_by_code.get(code, {}).get("unique_participants") or 0)
            for code in program_codes
        }
        total_participation = sum(program_values.values())
        row = {
            "residential_name": item.get("residential_name", ""),
            "municipality": item.get("municipality", ""),
            "rq_code": item.get("rq_code", ""),
            "programs": program_values,
            "total_participation": total_participation,
            "unique_participants": int(item.get("unique_participants") or 0),
            "total_services": int(item.get("attendances") or 0),
        }
        rows.append(row)
        for code in program_codes:
            totals["programs"][code] += program_values[code]
        totals["total_participation"] += total_participation
        totals["unique_participants"] += row["unique_participants"]
        totals["total_services"] += row["total_services"]

    return {
        **base,
        "title": "Plantilla Duplicado",
        "rows": rows,
        "duplicado_totals": totals,
        "program_columns": program_columns,
        "program_codes": program_codes,
        "program_labels": {column["code"]: column["label"] for column in program_columns},
        "chart_segments": _chart_segments(rows, totals["total_participation"]),
        "page_table_number": 31,
        "page_chart_number": 33,
        "revision_label": "Rev.15/agosto/2019 CRM",
        "pdf_template_name": "ui/admin/plantilla_duplicado_pdf.html",
    }
