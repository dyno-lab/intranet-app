"""Presentation of complete-report tables using the supplied Word layouts.

All values come from existing report contexts or explicit manual supplements.
The cumulative and population summaries have separate input contracts because
monthly totals and the existing broad age buckets cannot reconstruct them.
No database access, historical template figures or participant identity rules
are defined here.
"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Paragraph, Table, TableStyle


ASSETS = Path(__file__).resolve().parents[1] / "static" / "reports" / "full_monthly"
BLUE = colors.HexColor("#B8CCE3")
PALE_BLUE = colors.HexColor("#DCE6F0")
PINK = colors.HexColor("#F1DCDB")
GREY = colors.HexColor("#D9D9D9")
ORANGE = colors.HexColor("#F79546")
GREEN = colors.HexColor("#6FAC46")
PALE_GREEN = colors.HexColor("#C4D69B")
PENDING = "Pendiente"


def _p(value, size=9, *, bold=False, align=1, sans=False):
    font = ("Helvetica-Bold" if bold else "Helvetica") if sans else ("Times-Bold" if bold else "Times-Roman")
    return Paragraph(escape(str(PENDING if value is None else value)).replace("\n", "<br/>"), ParagraphStyle(
        "ReferenceTable", fontName=font, fontSize=size, leading=size * 1.1,
        alignment=align, textColor=colors.black,
    ))


def _text(canvas, text, x, top, width, size=9, **options):
    paragraph = _p(text, size, **options)
    _, height = paragraph.wrap(width, 1500)
    paragraph.drawOn(canvas, x, top - height)
    return height


def _image(canvas, name, x, y, width, height, preserve=True):
    canvas.drawImage(str(ASSETS / name), x, y, width, height,
                     preserveAspectRatio=preserve, anchor="c", mask="auto")


def _document(title, wide=False):
    buffer = BytesIO()
    canvas = Canvas(buffer, pagesize=landscape(letter) if wide else letter, pageCompression=1)
    canvas.setTitle(title)
    canvas.setAuthor("Centros Sor Isolina Ferré - Faro de Esperanza")
    return buffer, canvas


def _finish(buffer, canvas):
    canvas.save()
    return buffer.getvalue()


def _number(value, decimals=None):
    if value is None:
        return PENDING
    return f"{value:,.{decimals}f}" if decimals is not None else f"{value:,}"


def _percentage(actual, target):
    if actual is None or target is None:
        return PENDING
    if target == 0:
        return "No aplica"
    return f"{actual / target:.0%}"


def _targets_total(residentials, targets):
    values = [targets.get(row["residential_id"]) for row in residentials]
    return sum(values) if values and all(value is not None for value in values) else None


def _programs(context):
    return {item["program"].code: item for item in context["program_sections"]}


def _program_label(code):
    return re.sub(r"^(\d+)[ -]?([A-Za-z])$", r"\1-\2", str(code))


def _hours(context):
    return {item["program"].code: item["program_contact_hours"] for item in context["program_blocks"]}


def _table(rows, widths, commands=(), *, size=9, bold=False, sans=False, min_height=13, row_minima=None):
    def cell(value, column):
        font_size = size
        if value in (None, PENDING, "No aplica") and widths[column] < 40:
            font = ("Helvetica-Bold" if bold else "Helvetica") if sans else ("Times-Bold" if bold else "Times-Roman")
            font_size = min(size, (widths[column] - 4.5) / stringWidth(str(value or PENDING), font, 1))
        return _p(value, font_size, bold=bold, sans=sans, align=0 if column == 0 else 1)
    cells = [[cell(value, column) for column, value in enumerate(row)] for row in rows]
    minima = [(row_minima or {}).get(index, min_height) for index in range(len(rows))]
    table = Table(cells, colWidths=widths, minRowHeights=minima)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), .5, colors.black),
        ("BOX", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        *commands,
    ]))
    return table


def _pages(items, builder, available_height, limit=18):
    """Repeat complete headers and keep every row when a layout needs to grow."""
    offset = 0
    while True:
        count = min(limit, len(items) - offset)
        while True:
            last = offset + count == len(items)
            table = builder(items[offset:offset + count], last)
            _, height = table.wrap(800, 2000)
            if height <= available_height or count <= 1:
                break
            count -= 1
        if height > available_height:
            raise ValueError("Una fila es demasiado extensa para la hoja del informe completo.")
        yield table, last
        offset += count
        if last:
            break


def _draw_table(canvas, table, x, top):
    _, height = table.wrap(800, 2000)
    table.drawOn(canvas, x, top - height)
    return top - height


def _certification_header(canvas, title, period):
    _image(canvas, "table_referral_csif.png", 266.65, 717.6, 78.45, 32.10, False)
    _text(canvas, "Faro de Esperanza\n" + title, 65, 706, 482, 12, bold=True)
    _text(canvas, "Mes: " + period, 82, 662, 235, 11, align=0)
    _text(canvas, "Área: Servicio al Residente", 306, 662, 235, 11)
    _image(canvas, "table_referral_faro.png", 57.6, 47.65, 157.3, 37.15, False)


def duplicated_pdf(data):
    programs = _programs(data["por_programa"])
    codes = list(programs)
    count = len(codes)
    widths = [143] + [280 / max(count, 1)] * count + [79, 79, 79]
    first = ["RESIDENCIAL", *(["Total Participación en el Programa de", *([""] * (count - 1))] if count else []),
             "Total\nParticipación", "Participantes No\nDuplicados", "Total de\nServicios"]
    second = ["", *["Programa " + _program_label(code) for code in codes], "", "", ""]

    def record(row):
        values = _programs(row["por_programa"])
        participation = [values.get(code, {}).get("total_all", 0) for code in codes]
        return [row["residential_name"], *map(_number, participation), _number(sum(participation)),
                _number(row["no_duplicado"]["total_all"]), _number(row["duplicado"]["total_all"])]

    total = ["Total", *[_number(programs[code]["total_all"]) for code in codes],
             _number(sum(item["total_all"] for item in programs.values())),
             _number(data["no_duplicado"]["total_all"]), _number(data["duplicado"]["total_all"])]

    def build(batch, last):
        commands = [("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#F2F2F2"))]
        if count:
            commands.extend([("BACKGROUND", (1, 0), (count, 0), colors.HexColor("#FCD5B4")),
                             ("SPAN", (1, 0), (count, 0))])
        for column in [0, count + 1, count + 2, count + 3]:
            commands.append(("SPAN", (column, 0), (column, 1)))
        if last:
            commands.append(("BACKGROUND", (0, -1), (-1, -1), GREY))
        table = _table([first, second, *[record(row) for row in batch], *([total] if last else [])], widths, commands, size=10, bold=True, min_height=14.9, row_minima={0: 18, 1: 30})
        table._cellvalues[0][0] = _p(first[0], 10, bold=True)
        if last:
            table._cellvalues[-1][0] = _p(total[0], 10, bold=True)
        return table

    buffer, canvas = _document("Informe de participación mensual de servicios ofrecidos", True)
    for index, (table, last) in enumerate(_pages(data["residentials"], build, 345)):
        if index:
            canvas.showPage()
        _image(canvas, "table_duplicate_avp.png", 55.7, 507.9, 222.77, 76.75, False)
        _text(canvas, "ÁREA DE PROGRAMAS COMUNALES Y DE RESIDENTES", 50, 504, 692, 11, bold=True, align=0)
        _text(canvas, "INFORME DE PARTICIPACIÓN MENSUAL DE SERVICIOS OFRECIDOS", 50, 490, 692, 11, bold=True)
        _text(canvas, "Por edad y sexo en los proyectos impactados", 50, 476, 692, 10.5)
        _text(canvas, "COMPAÑÍA: Centros Sor Isolina Ferré, Inc.", 67, 459, 460, 10.5, align=0)
        _text(canvas, "ÁREA: Servicios al Residente", 543, 459, 185, 10.5, align=0)
        _text(canvas, "MES REPORTADO: " + data["period_label"], 67, 443, 650, 10.5, align=0)
        bottom = _draw_table(canvas, table, 65, 429)
        if last:
            _text(canvas, "La participación suma los participantes de cada programa; una persona puede participar en más de uno. Los no duplicados conservan el total único global.", 67, bottom - 8, 655, 7, align=0)
    return _finish(buffer, canvas)


def contact_hours_table_pdf(data):
    global_hours = _hours(data["hoja_cotejo"])
    codes = list(global_hours)
    widths = [148] + [259 / max(len(codes), 1)] * len(codes) + [74]
    headers = ["Residenciales", *["Prog. " + _program_label(code) for code in codes], "Total"]
    total_hours = data["hoja_cotejo"]["total_contact_hours"]

    def build(batch, last):
        rows = [headers]
        for row in batch:
            values = _hours(row["hoja_cotejo"])
            rows.append([row["residential_name"], *[_number(values.get(code, 0), 2) for code in codes],
                         _number(row["hoja_cotejo"]["total_contact_hours"], 2)])
        if last:
            rows.append(["Total Acumuladas", *[_number(global_hours[code], 2) for code in codes], _number(total_hours, 2)])
        commands = [("BACKGROUND", (0, 0), (-1, 0), BLUE), ("BACKGROUND", (-1, 1), (-1, -1), GREY),
                    ("LINEBELOW", (0, 0), (-1, -1), 1.4, colors.black)]
        if last:
            commands.append(("BACKGROUND", (0, -1), (-1, -1), GREY))
        table = _table(rows, widths, commands, size=11, min_height=15.5)
        for row_index, row in enumerate(rows):
            if row_index == 0 or last and row_index == len(rows) - 1:
                table._cellvalues[row_index] = [_p(value, 11, bold=True) for value in row]
            else:
                table._cellvalues[row_index][-1] = _p(row[-1], 11, bold=True)
        return table

    buffer, canvas = _document("Certificación Horas Contacto por Programa/Actividades")
    for index, (table, last) in enumerate(_pages(data["residentials"], build, 370)):
        if index:
            canvas.showPage()
        _certification_header(canvas, "Certificación Horas Contacto por Programa/Actividades", data["period_label"])
        bottom = _draw_table(canvas, table, 51, 633)
        if last:
            _text(canvas, "Rev.01-2025 CXRM", 80, bottom - 5, 230, 7, align=0, sans=True)
            _text(canvas, "Total horas contacto:        " + _number(total_hours, 2), 80, bottom - 27, 360, 10.5, align=0)
            _text(canvas, "Nota: Esta información fue corroborada mediante la verificación de Hoja descripción y evaluación de actividades.", 84, bottom - 55, 450, 7.5, align=0)
            canvas.line(51, bottom - 92, 264, bottom - 92)
            _text(canvas, "Firma", 51, bottom - 95, 213, 10)
    return _finish(buffer, canvas)


def external_referrals_pdf(data):
    groups = defaultdict(list)
    aliases = {}
    for row in data["residentials"]:
        name = row["residential_name"]
        aliases[name] = name
        code = getattr(row["residential"], "code", None)
        if code:
            aliases[f"{code} - {name}"] = name
    external = [row for row in data["visitas"]["referral_rows"] if row["referral_type"].strip().casefold() == "externo"]
    for row in external:
        label = (row.get("residential_name") or "Sin residencial").strip()
        groups[aliases.get(label, label)].append(row)
    names = [row["residential_name"] for row in data["residentials"]]
    names.extend(sorted(set(groups) - set(names)))
    rows = []
    for name in names:
        referrals = groups[name]
        agencies = list(dict.fromkeys((row.get("agency") or "").strip() or "Agencia no especificada" for row in referrals))
        rows.append([name, len(referrals), "; ".join(agencies)])

    def build(batch, last):
        table_rows = [["Residenciales", "Cantidad de\nReferidos", "Agencias"], *batch]
        commands = [("BACKGROUND", (0, 0), (-1, 0), BLUE), ("LINEBELOW", (0, 0), (0, -1), 1.5, colors.black)]
        if last:
            table_rows.append(["Total Acumulados", len(external), ""])
            commands.append(("SPAN", (1, -1), (2, -1)))
        table = _table(table_rows, [148, 65, 269], commands, size=11, min_height=15.5)
        table._cellvalues[0] = [_p(value, 11, bold=True) for value in table_rows[0]]
        if last:
            table._cellvalues[-1] = [_p(value, 11, bold=True) for value in table_rows[-1]]
        return table

    buffer, canvas = _document("Referidos Realizados (Externos)")
    for index, (table, last) in enumerate(_pages(rows, build, 398)):
        if index:
            canvas.showPage()
        _certification_header(canvas, "Referidos Realizados (Externos)", data["period_label"])
        bottom = _draw_table(canvas, table, 51, 639)
        if last:
            _text(canvas, "Rev.01-2025 CXRM", 80, bottom - 5, 230, 7, align=0, sans=True)
            canvas.line(79, bottom - 52, 265, bottom - 52)
            canvas.line(330, bottom - 52, 460, bottom - 52)
            _text(canvas, "Firma", 79, bottom - 54, 186, 10)
            _text(canvas, "(D) / (M) / (A)", 330, bottom - 54, 130, 10)
    return _finish(buffer, canvas)


def _target_header(canvas, variant):
    if variant == "population":
        _image(canvas, "table_csif_header.png", 323.4, 485.7, 139.54, 39.2, False)
        _image(canvas, "table_population_footer_faro.png", 71.9, 115.95, 111.07, 28.05, False)
        _image(canvas, "table_population_footer_vivienda.jpeg", 628.55, 103.63, 95.65, 43.85, False)
    elif variant == "cumulative":
        _image(canvas, "table_cumulative_csif.png", 300.25, 503.65, 209.58, 54.35, False)
        _image(canvas, "table_cumulative_faro.png", 18.1, 95.24, 196.32, 58.35, False)
    else:
        _image(canvas, "table_program_csif.png", 299.4, 504.8, 186.92, 53.25, False)
        _image(canvas, "table_program_faro.png", 70.55, 63.95, 156.85, 28.05, False)


def _cumulative_targets_pdf(data, supplements):
    residentials, targets = data["residentials"], supplements.get("targets", {})
    cumulative = data.get("target_cumulative", {})
    by_residential = cumulative.get("by_residential", {})
    cumulative_label = cumulative.get("period_label") or PENDING
    headers = ["RESIDENCIAL", "PUEBLO", "RQ", "AMP", "PARTICIPANTES A SER SERVIDOS DURANTE PERIODO DE LA PROPUESTA",
               "PARTICIPANTES ATENDIDOS EN\n" + data["period_label"], "ATENDIDOS PERIODO PROPUESTA\nACUMULADO " + cumulative_label, "%", "%"]
    widths = [108, 51, 45, 69, 149, 136, 136, 31, 31]
    scale = 756 / sum(widths)
    widths = [width * scale for width in widths]

    def build(batch, last):
        rows = [["Participantes Propuestos vs Participantes Atendidos", *("" for _ in headers[1:])], headers]
        for row in batch:
            model = row["residential"]
            target, actual = targets.get(row["residential_id"]), row["no_duplicado"]["total_all"]
            accumulated = by_residential.get(row["residential_id"])
            amp = supplements.get("amps", {}).get(row["residential_id"]) or getattr(model, "amp_code", None) or PENDING
            rows.append([row["residential_name"], model.municipality or PENDING, model.rq_code or PENDING,
                         amp, _number(target), _number(actual), _number(accumulated),
                         _percentage(actual, target), _percentage(accumulated, target)])
        if last:
            target = _targets_total(residentials, targets)
            actual = data["no_duplicado"]["total_all"]
            accumulated = cumulative.get("total_all")
            rows.append(["TOTAL", len(residentials), "/", "/", _number(target), _number(actual), _number(accumulated),
                         _percentage(actual, target), _percentage(accumulated, target)])
        commands = [("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 1), (-1, 1), BLUE),
                    ("BACKGROUND", (5, 2), (5, -1), PALE_BLUE), ("BACKGROUND", (6, 2), (6, -1), PINK),
                    ("BACKGROUND", (7, 2), (7, -1), PALE_BLUE), ("BACKGROUND", (8, 2), (8, -1), PINK),
                    ("LINEBELOW", (0, 1), (4, -1), 1.3, colors.black)]
        if last:
            commands.append(("BACKGROUND", (5, -1), (-1, -1), GREY))
        table = _table(rows, widths, commands, size=8.2, sans=True, min_height=12.5, row_minima={0: 14, 1: 33})
        table._cellvalues[0][0] = _p(rows[0][0], 9, bold=True, sans=True)
        table._cellvalues[1] = [_p(value, 7.3, bold=True, sans=True) for value in headers]
        if last:
            table._cellvalues[-1][0] = _p("TOTAL", 8.2, bold=True, sans=True)
        return table

    buffer, canvas = _document("Participantes Propuestos vs Participantes Atendidos", True)
    for index, (table, last) in enumerate(_pages(residentials, build, 344)):
        if index:
            canvas.showPage()
        _target_header(canvas, "cumulative")
        bottom = _draw_table(canvas, table, 18, 514)
        if last:
            _text(canvas, "Rev. 1-2025 CXRM", 20, bottom - 4, 450, 7, sans=True, align=0)
            _text(canvas, "* La información recopilada es en base a los participantes que los administradores de los residenciales certifican que son residentes bonafides.", 20, bottom - 15, 745, 7, sans=True, align=0)
            _text(canvas, "Las metas, códigos AMP o acumulados sin información se muestran como pendientes. Los totales de atendidos conservan participantes únicos globales.", 20, bottom - 27, 745, 6.7, sans=True, align=0)
    return _finish(buffer, canvas)


def _group_targets_pdf(data, supplements, *, population=False):
    residentials, targets = data["residentials"], supplements.get("targets", {})
    programs = _programs(data["por_programa"])
    groups = [("children", "Programa de Niños hasta los 12"), ("youth", "Programa de Jóvenes 13 a 18 años"),
              ("adults", "Programa de Adulto 19 a 59 años"), ("older", "Prog. Adulto Mayor 60 años o más")] if population else [(code, "Programa " + _program_label(code)) for code in programs]
    group_count = len(groups)
    total_start = 1 + group_count * 4
    group_width = (441 if population else 430) / max(group_count, 1)
    widths = [94] + [value for _ in groups for value in [group_width * .215, group_width * .215, group_width * .385, group_width * .185]] + [55, 58, 38]
    table_width = sum(widths)
    x = (792 - table_width) / 2
    band = colors.HexColor("#BCD6ED") if population else PALE_GREEN
    summary_color = GREEN if population else ORANGE
    head = ["Residencial"]
    sub = [""]
    for _, label in groups:
        head.extend([label, "", "", ""])
        sub.extend(["F", "M", "Total Atendidos" if population else "Total", ""])
    head.extend(["Total Atendidos", "Total Propuestos", "%"])
    sub.extend(["", "", ""])
    population_rows = data.get("target_population_rows", {})

    def values_for(row):
        context = population_rows.get(row["residential_id"], {}) if population else _programs(row["por_programa"])
        values = []
        for key, _ in groups:
            item = context.get(key)
            values.extend([_number(item.get("f") if population else item.get("total_f")) if item else PENDING,
                           _number(item.get("m") if population else item.get("total_m")) if item else PENDING,
                           _number(item.get("total") if population else item.get("total_all")) if item else PENDING, ""])
        actual = row["no_duplicado"]["total_all"] if population else sum(item["total_all"] for item in context.values())
        target = targets.get(row["residential_id"])
        return [row["residential_name"], *values, _number(actual), _number(target), _percentage(actual, target)]

    def build(batch, last):
        rows = [head, sub, *[values_for(row) for row in batch]]
        commands = [("SPAN", (0, 0), (0, 1)), ("BACKGROUND", (1, 0), (-1, 0), summary_color),
                    ("BACKGROUND", (1, 1), (total_start - 1, 1), BLUE),
                    ("BACKGROUND", (total_start, 0), (-1, -1), summary_color),
                    ("LINEBELOW", (0, 0), (0, -1), 1.3, colors.black)]
        for index in range(group_count):
            first = 1 + index * 4
            commands.extend([("SPAN", (first, 0), (first + 3, 0)),
                             ("BACKGROUND", (first + 3, 1), (first + 3, -1), band)])
        for column in range(total_start, total_start + 3):
            commands.append(("SPAN", (column, 0), (column, 1)))
        if last:
            context = population_rows.get("global", {}) if population else programs
            total_row = ["" if population else "TOTAL"]
            for key, _ in groups:
                item = context.get(key)
                total_row.extend([_number(item.get("total") if population else item.get("total_all")) if item else PENDING, "", "", ""])
            actual = data["no_duplicado"]["total_all"] if population else sum(item["total_all"] for item in programs.values())
            target = _targets_total(residentials, targets)
            total_row.extend([_number(actual), _number(target), _percentage(actual, target)])
            rows.append(total_row)
            for index in range(group_count):
                first = 1 + index * 4
                commands.extend([("SPAN", (first, -1), (first + 2, -1)),
                                 ("BACKGROUND", (first, -1), (first + 2, -1), BLUE if population else GREY)])
        for index in range(group_count):
            column = 4 + index * 4
            commands.append(("SPAN", (column, 1), (column, -1)))
        table = _table(rows, widths, commands, size=7.4, sans=not population, min_height=10.5 if population else 11.7)
        table._cellvalues[0] = [_p(value, 7, bold=True, sans=not population) for value in head]
        table._cellvalues[1] = [_p(value, 6.5, bold=True, sans=not population) for value in sub]
        return table

    title = "Participantes Propuestos por Residencial vs Participantes Atendidos por Residencial " + data["period_label"]
    buffer, canvas = _document(title, True)
    for index, (table, last) in enumerate(_pages(residentials, build, 320)):
        if index:
            canvas.showPage()
        _target_header(canvas, "population" if population else "program")
        top = 491 if population else 496
        if not population:
            canvas.rect(x, top, sum(widths[:-3]), 13)
            _text(canvas, title, x + 2, top + 11, sum(widths[:-3]) - 4, 8, bold=True)
        bottom = _draw_table(canvas, table, x, top)
        band_height = sum(table._rowHeights[1:])
        for group_index in range(group_count):
            if not population and group_index != 1:
                continue
            column = 4 + group_index * 4
            center_x = x + sum(widths[:column]) + widths[column] / 2
            canvas.saveState()
            canvas.translate(center_x + 3, bottom + band_height / 2)
            canvas.rotate(90)
            canvas.setFont("Helvetica-Bold", 7)
            canvas.drawCentredString(0, 0, "TOTAL PARTICIPACIÓN" if population else "TOTAL PROPUESTO")
            canvas.restoreState()
        if last:
            note = "* La información recopilada es en base a los participantes que los administradores de los residenciales certifican que son residentes bonafides." if population else "*Los participantes puede que participen en más de un programa. Total Atendidos suma la participación en los programas; no representa personas únicas entre programas."
            _text(canvas, note, x, bottom - 22, table_width, 7, sans=True, align=0)
            if not population:
                _text(canvas, "Rev. 1-2025 CXRM", x, bottom - 10, table_width, 7, sans=True, align=0)
            elif not population_rows:
                _text(canvas, "Pendiente: desglose de población con cortes hasta 12, 13 a 18, 19 a 59 y 60 años o más. Los rangos agregados de otros reportes no se redistribuyen.", x, bottom - 36, table_width, 7, sans=True, align=0)
    return _finish(buffer, canvas)


def participant_targets_pdf(data, supplements):
    """Render the three supplied target sheets using explicit report inputs.

    ``target_cumulative`` has ``period_label``, ``by_residential`` (int IDs to
    unique counts), and ``total_all`` (global unique, never a sum of locations).
    ``target_population_rows`` maps int residential IDs and ``"global"`` to
    ``children``, ``youth``, ``adults``, ``older`` dictionaries with f/m/total.
    Their age intervals are <=12, 13-18, 19-59, >=60 respectively. Missing
    inputs stay pending; the renderer never splits another report's age bins.
    ``supplements.targets`` maps int residential IDs to manually entered goals;
    configured proposal goals take precedence and remain fixed across months.
    """
    from app.services.full_monthly_report_targets import configured_targets

    fixed = configured_targets(data.get("proposals", []), [row["residential"] for row in data["residentials"]])
    supplements = {**supplements, "targets": {**supplements.get("targets", {}), **fixed["targets"]},
                   "amps": fixed["amps"]}
    writer = PdfWriter()
    for payload in (_cumulative_targets_pdf(data, supplements), _group_targets_pdf(data, supplements),
                    _group_targets_pdf(data, supplements, population=True)):
        for page in PdfReader(BytesIO(payload)).pages:
            writer.add_page(page)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
