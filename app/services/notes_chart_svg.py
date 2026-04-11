from __future__ import annotations

import base64
import math
from html import escape
from typing import Iterable

GRADE_COLORS = {
    "A": "#198754",
    "B": "#0dcaf0",
    "C": "#ffc107",
    "D": "#6c757d",
    "F": "#dc3545",
}
NOTE_LETTERS = ["A", "B", "C", "D", "F"]


def _svg_data_uri(svg: str) -> str:
    payload = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{payload}"


def _fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def _polar_to_cartesian(cx: float, cy: float, radius: float, angle_deg: float) -> tuple[float, float]:
    angle_rad = math.radians(angle_deg - 90)
    return (cx + radius * math.cos(angle_rad), cy + radius * math.sin(angle_rad))


def _pie_slice_path(cx: float, cy: float, radius: float, start_angle: float, end_angle: float) -> str:
    start_x, start_y = _polar_to_cartesian(cx, cy, radius, end_angle)
    end_x, end_y = _polar_to_cartesian(cx, cy, radius, start_angle)
    large_arc = 1 if end_angle - start_angle > 180 else 0
    return (
        f"M {cx:.2f} {cy:.2f} "
        f"L {start_x:.2f} {start_y:.2f} "
        f"A {radius:.2f} {radius:.2f} 0 {large_arc} 0 {end_x:.2f} {end_y:.2f} Z"
    )


def build_notes_pie_chart_svg(title: str, counts: dict[str, int], width: int = 720, height: int = 360) -> str:
    total = sum(max(int(counts.get(letter, 0) or 0), 0) for letter in NOTE_LETTERS)
    cx, cy, radius = 180, 180, 115
    legend_x = 380
    legend_y = 92
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width/2:.0f}" y="30" text-anchor="middle" font-size="22" font-family="Arial" font-weight="700" fill="#111">{escape(title)}</text>',
    ]
    if total <= 0:
        parts.append(f'<circle cx="{cx}" cy="{cy}" r="{radius}" fill="#f1f3f5" stroke="#ced4da" stroke-width="2"/>')
        parts.append(f'<text x="{cx}" y="{cy}" text-anchor="middle" font-size="20" font-family="Arial" fill="#6c757d">Sin datos</text>')
    else:
        angle = 0.0
        for letter in NOTE_LETTERS:
            value = max(int(counts.get(letter, 0) or 0), 0)
            if value <= 0:
                continue
            sweep = (value / total) * 360.0
            path = _pie_slice_path(cx, cy, radius, angle, angle + sweep)
            parts.append(f'<path d="{path}" fill="{GRADE_COLORS[letter]}" stroke="#ffffff" stroke-width="2"/>')
            mid_angle = angle + sweep / 2
            if (value / total) >= 0.04:
                tx, ty = _polar_to_cartesian(cx, cy, radius * 0.62, mid_angle)
                parts.append(
                    f'<text x="{tx:.2f}" y="{ty:.2f}" text-anchor="middle" dominant-baseline="middle" '
                    f'font-size="16" font-family="Arial" font-weight="700" fill="#ffffff">{_fmt_pct((value/total)*100)}</text>'
                )
            angle += sweep
    row = 0
    for letter in NOTE_LETTERS:
        value = max(int(counts.get(letter, 0) or 0), 0)
        pct = ((value / total) * 100) if total else 0
        y = legend_y + row * 42
        parts.extend([
            f'<rect x="{legend_x}" y="{y - 14}" width="22" height="22" rx="4" fill="{GRADE_COLORS[letter]}"/>',
            f'<text x="{legend_x + 34}" y="{y}" font-size="18" font-family="Arial" font-weight="700" fill="#111">{letter}</text>',
            f'<text x="{legend_x + 80}" y="{y}" font-size="16" font-family="Arial" fill="#333">{value} estudiantes</text>',
            f'<text x="{legend_x + 230}" y="{y}" font-size="16" font-family="Arial" fill="#666">{pct:.2f}%</text>',
        ])
        row += 1
    parts.append(f'<text x="{legend_x}" y="{legend_y + 5 * 42 + 18}" font-size="16" font-family="Arial" fill="#111">Total evaluados: {total}</text>')
    parts.append('</svg>')
    return _svg_data_uri(''.join(parts))


def build_notes_residential_bar_chart_svg(rows: Iterable[dict], width: int = 1080, height: int = 520) -> str:
    rows = list(rows)
    max_total = max((sum(max(int(row.get(letter, 0) or 0), 0) for letter in NOTE_LETTERS) for row in rows), default=0)
    chart_left, chart_right = 110, width - 40
    chart_top, chart_bottom = 60, height - 110
    chart_width = chart_right - chart_left
    chart_height = chart_bottom - chart_top
    bar_group_width = chart_width / max(len(rows), 1)
    bar_width = min(72, bar_group_width * 0.55)
    scale_max = max_total if max_total > 0 else 1
    tick_count = min(max(scale_max, 1), 5)
    tick_step = max(1, math.ceil(scale_max / tick_count))
    axis_top_value = max(tick_step * tick_count, scale_max)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
        f'<text x="{width/2:.0f}" y="30" text-anchor="middle" font-size="22" font-family="Arial" font-weight="700" fill="#111">Notas académicas por residencial</text>',
    ]
    for tick in range(0, axis_top_value + 1, tick_step):
        y = chart_bottom - (tick / axis_top_value) * chart_height
        parts.append(f'<line x1="{chart_left}" y1="{y:.2f}" x2="{chart_right}" y2="{y:.2f}" stroke="#e9ecef" stroke-width="1"/>')
        parts.append(f'<text x="{chart_left - 10}" y="{y + 4:.2f}" text-anchor="end" font-size="12" font-family="Arial" fill="#666">{tick}</text>')
    parts.append(f'<line x1="{chart_left}" y1="{chart_bottom}" x2="{chart_right}" y2="{chart_bottom}" stroke="#333" stroke-width="1.5"/>')
    parts.append(f'<line x1="{chart_left}" y1="{chart_top}" x2="{chart_left}" y2="{chart_bottom}" stroke="#333" stroke-width="1.5"/>')
    for idx, row in enumerate(rows):
        total = sum(max(int(row.get(letter, 0) or 0), 0) for letter in NOTE_LETTERS)
        x_center = chart_left + bar_group_width * idx + bar_group_width / 2
        x = x_center - bar_width / 2
        running_height = 0.0
        for letter in NOTE_LETTERS:
            value = max(int(row.get(letter, 0) or 0), 0)
            if value <= 0:
                continue
            segment_height = (value / axis_top_value) * chart_height
            y = chart_bottom - running_height - segment_height
            parts.append(f'<rect x="{x:.2f}" y="{y:.2f}" width="{bar_width:.2f}" height="{segment_height:.2f}" fill="{GRADE_COLORS[letter]}"/>')
            if segment_height >= 18:
                parts.append(f'<text x="{x_center:.2f}" y="{y + segment_height / 2 + 4:.2f}" text-anchor="middle" font-size="11" font-family="Arial" font-weight="700" fill="#fff">{value}</text>')
            running_height += segment_height
        label = escape(str(row.get("residential_name", "")))
        parts.append(f'<text x="{x_center:.2f}" y="{chart_bottom + 18}" text-anchor="middle" font-size="11" font-family="Arial" fill="#333">{label}</text>')
        parts.append(f'<text x="{x_center:.2f}" y="{chart_bottom + 34}" text-anchor="middle" font-size="11" font-family="Arial" font-weight="700" fill="#111">Total {total}</text>')
    legend_x = chart_left
    legend_y = height - 38
    for idx, letter in enumerate(NOTE_LETTERS):
        x = legend_x + idx * 115
        parts.append(f'<rect x="{x}" y="{legend_y - 12}" width="18" height="18" rx="3" fill="{GRADE_COLORS[letter]}"/>')
        parts.append(f'<text x="{x + 28}" y="{legend_y + 2}" font-size="14" font-family="Arial" fill="#111">{letter}</text>')
    if not rows:
        parts.append(f'<text x="{width/2:.0f}" y="{height/2:.0f}" text-anchor="middle" font-size="22" font-family="Arial" fill="#6c757d">Sin datos por residencial</text>')
    parts.append('</svg>')
    return _svg_data_uri(''.join(parts))


def build_notes_pdf_chart_images(context: dict) -> dict:
    general_counts = {label: value for label, value in zip(context.get("pie_labels", []), context.get("pie_values", []))}
    general_chart_image = build_notes_pie_chart_svg("Distribución general de notas", general_counts)
    residential_chart_image = build_notes_residential_bar_chart_svg(context.get("residential_chart_rows", []))
    subject_chart_sections = []
    for subject_card in context.get("subject_chart_cards", []):
        image = build_notes_pie_chart_svg(subject_card.get("subject_name", "Materia"), subject_card.get("counts", {}), width=620, height=320)
        subject_chart_sections.append({
            "subject_name": subject_card.get("subject_name", "Materia"),
            "image": image,
            "counts": subject_card.get("counts", {}),
            "segments": subject_card.get("segments", []),
        })
    return {
        "general_chart_image": general_chart_image,
        "residential_chart_image": residential_chart_image,
        "subject_chart_images": [section["image"] for section in subject_chart_sections],
        "subject_chart_sections": subject_chart_sections,
    }
