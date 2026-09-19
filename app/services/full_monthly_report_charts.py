"""Vector charts for the complete report, following the supplied July PDF.

This module only presents explicit values supplied by the report builder. It
does not query data, infer totals, or reuse historical figures from the model.
The Excel-style perspective is recreated with vector shapes, so the labels and
figures remain searchable and sharp in the compiled document.
"""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import json
from math import ceil, cos, isfinite, log10, radians, sin
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph


STATIC = Path(__file__).resolve().parents[1] / "static"
REFERENCE = STATIC / "reports" / "full_monthly"
BLUE = colors.HexColor("#4F81BD")
LIGHT_BLUE = colors.HexColor("#95B3D7")
ORANGE = colors.HexColor("#ED7D31")
RED = colors.HexColor("#C0504D")
GREEN = colors.HexColor("#9BBB83")
ROLE_COLORS = [colors.HexColor(value) for value in (
    "#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5",
    "#70AD47", "#264478", "#636363", "#92A05D",
)]
PIE_COLORS = [colors.HexColor(value) for value in (
    "#4F81BD", "#C0504D", "#9BBB59", "#8064A2", "#4BACC6", "#F79646",
    "#1F497D", "#953735", "#76923C", "#604A7B", "#31859B", "#E46C0A",
    "#95B3D7", "#D99694", "#C3D69B", "#B1A0C7", "#92CDDC", "#FAC090",
)]


def _number(value):
    numeric = float(value)
    if not isfinite(numeric) or numeric < 0:
        raise ValueError("Las gráficas requieren cantidades finitas y no negativas.")
    return numeric


def _entries(entries):
    return [(str(label), _number(value)) for label, value in entries]


def _fmt(value, decimals=None):
    if decimals is not None:
        return f"{value:,.{decimals}f}"
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:,.2f}"


def _paragraph(canvas, text, x, y, width, font_size=9, align=0, bold=False):
    paragraph = Paragraph(escape(str(text)).replace("\n", "<br/>"), ParagraphStyle(
        "Chart", fontName="Helvetica-Bold" if bold else "Helvetica",
        fontSize=font_size, leading=font_size * 1.24, alignment=align,
        textColor=colors.black,
    ))
    _, height = paragraph.wrap(width, 1000)
    paragraph.drawOn(canvas, x, y - height)
    return height


def _page(title, period_label, portrait=False, reference="unique"):
    stream = BytesIO()
    size = letter if portrait else landscape(letter)
    canvas = Canvas(stream, pagesize=size, pageCompression=1)
    canvas.setTitle(title + (" - " + period_label if period_label else ""))
    canvas.setAuthor("Centros Sor Isolina Ferré - Faro de Esperanza")
    _decorate(canvas, size, reference=reference)
    return stream, canvas, size


@lru_cache(maxsize=1)
def _artwork():
    return json.loads((REFERENCE / "chart_artwork.json").read_text(encoding="utf-8"))


def _decorate(canvas, size, reference="unique"):
    # Each source chart places its logos differently. Preserve those placements
    # and aspect ratios; the letter artwork has different internal whitespace.
    for placement in _artwork()[reference]:
        canvas.drawImage(str(REFERENCE / placement["file"]), placement["x"],
                         placement["y"], placement["width"], placement["height"],
                         preserveAspectRatio=False, mask="auto")


def _finish(stream, canvas):
    canvas.save()
    return stream.getvalue()


def _frame(canvas, x, y, width, height, title):
    canvas.setStrokeColor(colors.HexColor("#555555"))
    canvas.setLineWidth(.6)
    canvas.rect(x, y, width, height, fill=0, stroke=1)
    _paragraph(canvas, title, x + 10, y + height - 11, width - 20, 15, 1, True)


def _maximum(values, divisions=6):
    maximum = max([*values, 1])
    raw = maximum / divisions
    magnitude = 10 ** int(log10(raw) // 1)
    step = next(item * magnitude for item in (1, 2, 5, 10) if item * magnitude >= raw)
    return ceil(maximum / step) * step, step


def _polygon(canvas, points, fill):
    path = canvas.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    path.close()
    canvas.setFillColor(fill)
    canvas.drawPath(path, fill=1, stroke=0)


def _shade(color, factor):
    return colors.Color(min(1, color.red * factor), min(1, color.green * factor), min(1, color.blue * factor))


def _column(canvas, x, baseline, width, height, color, depth=6):
    if height <= 0:
        return
    canvas.setFillColor(color)
    canvas.rect(x, baseline, width, height, stroke=0, fill=1)
    _polygon(canvas, [(x + width, baseline), (x + width + depth, baseline + depth),
                      (x + width + depth, baseline + height + depth), (x + width, baseline + height)], _shade(color, .72))
    _polygon(canvas, [(x, baseline + height), (x + depth, baseline + height + depth),
                      (x + width + depth, baseline + height + depth), (x + width, baseline + height)], _shade(color, 1.13))


def _columns(canvas, categories, series, box, *, angled=False, axes=True, labels=True, font_size=9):
    x, y, width, height = box
    values = [value for _, data, _ in series for value in data]
    maximum, step = _maximum(values)
    canvas.setStrokeColor(colors.HexColor("#777777"))
    canvas.setLineWidth(.5)
    canvas.line(x, y, x + width, y)
    if axes:
        canvas.line(x, y, x, y + height)
        for i in range(int(round(maximum / step)) + 1):
            tick_y = y + i * step / maximum * height
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(colors.black)
            canvas.drawRightString(x - 6, tick_y - 3, _fmt(i * step))
    if not categories:
        _paragraph(canvas, "No hay datos para mostrar.", x, y + height / 2, width, 11, 1)
        return
    group = width / len(categories)
    gap = 2
    bar_width = min(43, group * .66 / max(len(series), 1))
    depth = min(8, bar_width * .28)
    for index, category in enumerate(categories):
        center = x + (index + .5) * group
        first = center - (bar_width * len(series) + gap * (len(series) - 1)) / 2
        for series_index, (_, data, color) in enumerate(series):
            value = data[index]
            bar_x = first + series_index * (bar_width + gap)
            bar_height = value / maximum * height
            _column(canvas, bar_x, y, bar_width, bar_height, color, depth)
            if labels:
                canvas.setFillColor(colors.black)
                canvas.setFont("Helvetica-Bold", font_size)
                canvas.drawCentredString(bar_x + bar_width / 2 + depth / 2, y + bar_height + depth + 5, _fmt(value))
        canvas.setFillColor(colors.black)
        if angled:
            canvas.saveState()
            canvas.translate(center + 3, y - 7)
            canvas.rotate(48)
            canvas.setFont("Helvetica", font_size)
            canvas.drawRightString(0, 0, category)
            canvas.restoreState()
        else:
            _paragraph(canvas, category, center - group * .46, y - 8, group * .92, font_size, 1)


def _legend(canvas, entries, x, y, width=170, font_size=8, line_height=17):
    for name, color in entries:
        canvas.setFillColor(color)
        canvas.rect(x, y - 7, 5, 5, stroke=0, fill=1)
        used = _paragraph(canvas, name, x + 9, y, width - 9, font_size)
        y -= max(line_height, used + 5)


def residential_unique_pdf(entries, period_label=""):
    entries = _entries(entries)
    stream, canvas, size = _page("Participantes No Duplicados", period_label)
    # Continue large configurations without silently discarding residenciales.
    batches = [entries[i:i + 20] for i in range(0, len(entries), 20)] or [[]]
    for index, batch in enumerate(batches):
        if index:
            canvas.showPage()
            _decorate(canvas, size)
        _frame(canvas, 102, 167, 588, 300, "Participantes No Duplicados")
        _columns(canvas, [name for name, _ in batch], [("No duplicados", [v for _, v in batch], BLUE)],
                 (169, 274, 489, 147), angled=True, font_size=8)
        canvas.saveState()
        canvas.translate(143, 308)
        canvas.rotate(90)
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(0, 0, "No de Participantes")
        canvas.restoreState()
        _paragraph(canvas, "Residenciales", 250, 188, 300, 9, 1, True)
        _paragraph(canvas, "Gráfica 1: Se demuestra la participación mensual por cada residencial impactado. La cantidad de participantes no es duplicada.", 110, 153, 580, 9)
    return _finish(stream, canvas)


def program_services_pdf(categories, unique, duplicated, period_label=""):
    categories = [str(item) for item in categories]
    unique, duplicated = [_number(v) for v in unique], [_number(v) for v in duplicated]
    if len(categories) != len(unique) or len(categories) != len(duplicated):
        raise ValueError("Cada programa debe tener ambos valores de participación.")
    stream, canvas, _ = _page("Participación Mensual de Servicios Ofrecidos", period_label, reference="program")
    _frame(canvas, 72, 130, 622, 333, "Participación Mensual de Servicios Ofrecidos")
    _columns(canvas, categories, [("TOTAL PART.", unique, BLUE), ("DUPLICADOS", duplicated, LIGHT_BLUE)],
             (122, 167, 530, 229), axes=False, font_size=9)
    _legend(canvas, [("TOTAL PART.", BLUE), ("DUPLICADOS", LIGHT_BLUE)], 365, 368, 130, 8, 14)
    _paragraph(canvas, "Gráfica 2: Se demuestra la participación mensual por programa y la cantidad de servicios ofrecidos Programa Faro de Esperanza.", 72, 99, 650, 9)
    return _finish(stream, canvas)


def _pie(canvas, entries, center, radius, *, palette=PIE_COLORS, depth=25, explode=0, outside=True, inside_percent=True):
    total = sum(value for _, value in entries)
    cx, cy = center
    rx, ry = radius
    if not total:
        canvas.setStrokeColor(colors.grey)
        canvas.ellipse(cx - rx, cy - ry, cx + rx, cy + ry, stroke=1, fill=0)
        _paragraph(canvas, "No hay datos para mostrar.", cx - rx, cy + 6, rx * 2, 10, 1)
        return
    slices, angle = [], 90.0
    for index, (label, value) in enumerate(entries):
        if value == 0:
            continue
        extent = -360 * value / total
        mid = radians(angle + extent / 2)
        dx, dy = explode * cos(mid), explode * sin(mid) * ry / rx
        slices.append((angle, extent, mid, dx, dy, palette[index % len(palette)], label, value))
        angle += extent
    for drop in range(int(depth), 0, -1):
        for start, extent, mid, dx, dy, color, label, value in slices:
            canvas.setFillColor(_shade(color, .65))
            canvas.wedge(cx + dx - rx, cy + dy - ry - drop, cx + dx + rx, cy + dy + ry - drop, start, extent, stroke=0, fill=1)
    for start, extent, mid, dx, dy, color, label, value in slices:
        canvas.setFillColor(color)
        canvas.wedge(cx + dx - rx, cy + dy - ry, cx + dx + rx, cy + dy + ry, start, extent, stroke=0, fill=1)
    if not outside:
        if not inside_percent:
            return
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica", 8)
        tiny = []
        for _, _, mid, dx, dy, _, _, value in slices:
            if value / total >= .04:
                canvas.drawCentredString(cx + dx + cos(mid) * rx * .66, cy + dy + sin(mid) * ry * .66, f"{value / total:.0%}")
            else:
                tiny.append((cx + dx + cos(mid) * rx, cy + dy + sin(mid) * ry, value))
        previous = None
        for edge_x, edge_y, value in sorted(tiny):
            label_x = max(edge_x, previous + 24) if previous is not None else edge_x
            canvas.setStrokeColor(colors.grey)
            canvas.setLineWidth(.4)
            canvas.line(edge_x, edge_y, label_x, cy + ry + 9)
            canvas.drawCentredString(label_x, cy + ry + 11, f"{value / total:.0%}")
            previous = label_x
        return
    # Keep every callout visible and separate even when adjacent wedges are tiny.
    for side in (-1, 1):
        labels = sorted([item for item in slices if (1 if cos(item[2]) >= 0 else -1) == side], key=lambda item: sin(item[2]))
        min_y, max_y = cy - ry - 28, cy + ry + 52
        spacing = min(29, (max_y - min_y) / max(len(labels) - 1, 1))
        positions = []
        for item in labels:
            desired = cy + sin(item[2]) * (ry + 44)
            positions.append(max(desired, positions[-1] + spacing if positions else min_y))
        if positions and positions[-1] > max_y:
            positions = [position - (positions[-1] - max_y) for position in positions]
        for item, label_y in zip(labels, positions):
            _, _, mid, dx, dy, _, label, value = item
            edge_x = cx + dx + cos(mid) * rx
            edge_y = cy + dy + sin(mid) * ry
            label_x = cx + side * (rx + 30)
            canvas.setStrokeColor(colors.HexColor("#555555"))
            canvas.setLineWidth(.5)
            canvas.line(edge_x, edge_y, label_x, label_y - 6)
            text_x = label_x + 4 if side == 1 else label_x - 138
            _paragraph(canvas, f"{label}\n{value / total:.0%}", text_x, label_y + 8, 134, 8, 0 if side == 1 else 2, True)


def residential_services_pdf(entries, period_label=""):
    entries = _entries(entries)
    stream, canvas, _ = _page("Informe de participación mensual de servicios ofrecidos", period_label, reference="residential_pie")
    _paragraph(canvas, "ÁREA DE PROGRAMAS COMUNALES Y DE RESIDENTES\nINFORME DE PARTICIPACIÓN MENSUAL DE SERVICIOS OFRECIDOS", 48, 493, 690, 11, 1, True)
    _paragraph(canvas, "Por edad y sexo en los proyectos impactados", 150, 462, 490, 10, 1)
    _paragraph(canvas, "Por ciento de Participación de " + period_label, 376, 439, 370, 10, 1, True)
    _pie(canvas, entries, (393, 257), (188, 103), depth=33, explode=11)
    _paragraph(canvas, "Gráfica 3: Muestra el % de participación por residencial del programa de servicios.", 67, 80, 680, 10, bold=True)
    return _finish(stream, canvas)


def population_activities_pdf(panels, period_label=""):
    stream, canvas, size = _page("Participación por población y actividad", period_label, reference="population")
    panels = list(panels)
    batches = [panels[i:i + 4] for i in range(0, len(panels), 4)] or [[]]
    for page_index, batch in enumerate(batches):
        if page_index:
            canvas.showPage()
            _decorate(canvas, size, reference="population")
        panel_width = 700 / max(len(batch), 1)
        for index, panel in enumerate(batch):
            categories = [str(value) for value in panel["categories"]]
            activities = [_number(v) for v in panel["activities"]]
            duplicated = [_number(v) for v in panel["duplicated"]]
            if len(categories) != len(activities) or len(categories) != len(duplicated):
                raise ValueError("Cada actividad debe tener sus valores de actividades y duplicados.")
            left = 53 + index * panel_width
            _paragraph(canvas, panel["label"], left, 483, panel_width - 15, 13, 1, True)
            _columns(canvas, categories, [("Actividades", activities, BLUE), ("Duplicados", duplicated, ORANGE)],
                     (left + 25, 263, panel_width - 43, 188), font_size=7)
        _legend(canvas, [("Actividades", BLUE), ("Duplicados", ORANGE)], 648, 229, 100, 8, 14)
        _paragraph(canvas, "Gráfica 4: Se demuestra la participación mensual y la cantidad de actividades realizadas\nofrecidas por programa en el Programa Faro de Esperanza.", 95, 158, 600, 9, 1)
    return _finish(stream, canvas)


def _certification_header(canvas, title, period_label, width=612, title_top=664):
    _paragraph(canvas, "Faro de Esperanza\n" + title, 70, title_top, width - 140, 10, 1, True)
    _paragraph(canvas, "Mes: " + period_label, 82, 620, 260, 10)
    _paragraph(canvas, "Área: Servicio al Residente", width - 290, 620, 210, 10, 2)


def contact_hours_pdf(entries, period_label=""):
    entries = _entries(entries)
    stream, canvas, _ = _page("Certificación Horas Contacto por Programa/Actividades", period_label, portrait=True, reference="hours")
    _certification_header(canvas, "Certificación Horas Contacto por Programa/Actividades", period_label)
    left, bottom, width, height = 80, 360, 452, 238
    canvas.setFillColor(LIGHT_BLUE)
    canvas.setStrokeColor(BLUE)
    canvas.rect(left, bottom, width, height, stroke=1, fill=1)
    _paragraph(canvas, "Horas Contacto por Programa/Actividades", left + 9, bottom + height - 10, width - 18, 14, 1, True)
    x, y, plot_width, plot_height = 178, 401, 342, 154
    canvas.setFillColor(colors.white)
    canvas.rect(x, y, plot_width, plot_height, stroke=0, fill=1)
    maximum, step = _maximum([value for _, value in entries])
    for index in range(int(round(maximum / step)) + 1):
        grid_y = y + index * step / maximum * plot_height
        canvas.setStrokeColor(colors.HexColor("#555555"))
        canvas.setLineWidth(.5)
        canvas.line(x, grid_y, x + plot_width, grid_y)
        canvas.setFillColor(colors.black)
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(x - 6, grid_y - 3, _fmt(index * step, 2))
    canvas.saveState()
    canvas.translate(114, 439)
    canvas.rotate(90)
    canvas.setFont("Helvetica-Bold", 10)
    canvas.drawString(0, 0, "Horas Contacto")
    canvas.restoreState()
    step_x = plot_width / max(len(entries), 1)
    points = [(x + (index + .5) * step_x, y + value / maximum * plot_height) for index, (_, value) in enumerate(entries)]
    canvas.setStrokeColor(BLUE)
    canvas.setLineWidth(2)
    for first, second in zip(points, points[1:]):
        canvas.line(*first, *second)
    for point_x, point_y in points:
        _polygon(canvas, [(point_x, point_y + 4), (point_x + 3, point_y), (point_x, point_y - 4), (point_x - 3, point_y)], BLUE)
    canvas.setStrokeColor(colors.HexColor("#6A819D"))
    canvas.setLineWidth(.5)
    canvas.rect(98, bottom + 5, 422, 35, stroke=1, fill=0)
    canvas.line(98, bottom + 23, 520, bottom + 23)
    _paragraph(canvas, "Horas Contacto", 101, bottom + 18, 76, 8)
    for index, (label, value) in enumerate(entries):
        cell_x = x + index * step_x
        canvas.line(cell_x, bottom + 5, cell_x, bottom + 40)
        _paragraph(canvas, label, cell_x + 2, bottom + 35, step_x - 4, 8, 1)
        _paragraph(canvas, _fmt(value, 2), cell_x + 2, bottom + 18, step_x - 4, 8, 1)
    _paragraph(canvas, "Gráfica 5: Se demuestra la cantidad de horas contacto en actividades por área de servicios.", 80, 341, 452, 9)
    _paragraph(canvas, "Nota: Esta información fue consolidada mediante verificación de hojas de cotejo y evaluación de actividades.", 116, 305, 380, 7, 1)
    return _finish(stream, canvas)


def residential_visits_pdf(entries, period_label=""):
    entries = _entries(entries)
    stream, canvas, size = _page("Certificación visitas realizadas por el personal de servicios al residente", period_label, portrait=True, reference="visits")
    batches = [entries[i:i + 20] for i in range(0, len(entries), 20)] or [[]]
    for page_index, batch in enumerate(batches):
        if page_index:
            canvas.showPage()
            _decorate(canvas, size, reference="visits")
        _certification_header(canvas, "Certificación visitas realizadas por el personal de servicios al residente.", period_label, title_top=643)
        _paragraph(canvas, "Programa para niños, jóvenes, adultos y adulto mayor", 115, 593, 382, 10, 1)
        _frame(canvas, 101, 237, 430, 331, "")
        x, y, width, height = 151, 335, 302, 218
        maximum, step = _maximum([value for _, value in batch])
        for index in range(int(round(maximum / step)) + 1):
            line_y = y + index * step / maximum * height
            canvas.setStrokeColor(colors.HexColor("#777777"))
            canvas.setLineWidth(.6)
            canvas.line(x, line_y, x + width, line_y)
            canvas.setFillColor(colors.black)
            canvas.setFont("Helvetica", 8)
            canvas.drawRightString(x - 7, line_y - 3, _fmt(index * step))
        pitch = width / max(len(batch) - 1, 1)
        points = [(x + i * pitch, y + value / maximum * height) for i, (_, value) in enumerate(batch)]
        canvas.setStrokeColor(GREEN)
        canvas.setLineWidth(2)
        for first, second in zip(points, points[1:]):
            canvas.line(*first, *second)
        for (point_x, point_y), (label, _) in zip(points, batch):
            canvas.setFillColor(GREEN)
            canvas.rect(point_x - 4, point_y - 4, 8, 8, stroke=0, fill=1)
            canvas.saveState()
            canvas.translate(point_x + 3, y - 5)
            canvas.rotate(90)
            canvas.setFillColor(colors.black)
            canvas.setFont("Helvetica", 7)
            canvas.drawRightString(0, 0, label)
            canvas.restoreState()
        _legend(canvas, [("Visitas", GREEN)], 465, 411, 65, 9)
        _paragraph(canvas, "Gráfica 6: El personal del Programa Faro de Esperanza tiene como propósito primordial asistir a los residentes con Orientación, Servicios de Intervención y actividades productivas por realizar.", 101, 224, 430, 8)
        canvas.setStrokeColor(colors.black)
        canvas.line(101, 168, 290, 168)
        canvas.line(403, 168, 529, 168)
        _paragraph(canvas, "Firma", 101, 162, 189, 8, 1)
        _paragraph(canvas, "(D) / (M) / (A)", 403, 162, 126, 8, 1)
    return _finish(stream, canvas)


def visit_roles_pdf(entries, period_label=""):
    entries = _entries(entries)
    stream, canvas, _ = _page("Visitas realizadas por el personal de servicios al residente", period_label, portrait=True, reference="roles")
    _certification_header(canvas, "Visitas realizadas por el personal de servicios al residente.", period_label)
    _paragraph(canvas, "Programa para niños, jóvenes, adultos y adulto mayor", 110, 593, 392, 10, 1)
    _frame(canvas, 81, 374, 453, 203, "Visitas realizadas por el personal de servicios al\nresidente")
    _pie(canvas, entries, (239, 463), (127, 57), palette=ROLE_COLORS, depth=27, outside=False)
    _legend(canvas, [(label, ROLE_COLORS[index % len(ROLE_COLORS)]) for index, (label, _) in enumerate(entries)], 378, 530, 145, 7, 14)
    _paragraph(canvas, "Nota: Esta información fue consolidada mediante la verificación de Hojas de Visitas.", 90, 363, 440, 7, 1)
    canvas.setStrokeColor(colors.black)
    canvas.line(110, 294, 290, 294)
    canvas.line(398, 294, 527, 294)
    _paragraph(canvas, "Firma", 110, 288, 180, 8, 1)
    _paragraph(canvas, "(D) / (M) / (A)", 398, 288, 129, 8, 1)
    return _finish(stream, canvas)


def pregnancy_pdf(pregnancies, non_pregnancies, period_label=""):
    entries = _entries([("Embarazos", pregnancies), ("No Embarazos", non_pregnancies)])
    stream, canvas, _ = _page("Prevención de Embarazos en Jóvenes Féminas y Masculinos", period_label, reference="pregnancy")
    _paragraph(canvas, "Prevención de Embarazos en Jóvenes Féminas y Masculinos", 105, 517, 590, 14, 1, True)
    _frame(canvas, 142, 193, 484, 274, "")
    _pie(canvas, entries, (356, 334), (132, 70), palette=[BLUE, RED], depth=25, explode=8, outside=False, inside_percent=False)
    total = sum(value for _, value in entries)
    if total:
        _paragraph(canvas, f"Embarazos, {entries[0][1] / total:.0%}", 368, 418, 150, 8)
        _paragraph(canvas, f"No Embarazos, {entries[1][1] / total:.0%}", 144, 365, 145, 8)
    _legend(canvas, [("Embarazos", BLUE), ("No Embarazos", RED)], 551, 337, 90, 8, 34)
    _paragraph(canvas, "Gráfica 7: El programa Faro de Esperanza tiene como meta prevenir el por ciento de embarazo en los adolescentes.", 128, 182, 590, 9)
    return _finish(stream, canvas)
