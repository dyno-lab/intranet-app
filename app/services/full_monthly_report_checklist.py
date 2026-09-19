"""Institutional checklist layout for the complete report only.

The columns follow the supplied monthly PDF. Activity rows keep the existing
administrative values. Recruitment rows show distinct residential coverage.
"""
from __future__ import annotations

from calendar import monthrange
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from app.services.report_pdf import PDFRenderError
from app.services.full_monthly_report_frontmatter import _fonts
from app.services.full_monthly_report_recruitment import recruitment_code
from app.services.hoja_cotejo_admin_service import _percent as goal_percent, _format_cumulative_ratio


STATIC = Path(__file__).resolve().parents[1] / "static" / "reports" / "full_monthly"
WIDTHS = [280, 31, 31, 104, 84, 92, 63, 63]
FONTS = _fonts()
BODY = ParagraphStyle("InstitutionalChecklistBody", fontName=FONTS["normal"], fontSize=6, leading=6.84)
CENTER = ParagraphStyle("InstitutionalChecklistValue", parent=BODY, fontName=FONTS["bold"], alignment=1)
HEADER = ParagraphStyle("InstitutionalChecklistHeader", parent=CENTER, fontSize=5.04, leading=5.76)
GROUP = ParagraphStyle("InstitutionalChecklistGroup", parent=HEADER, alignment=0)


def _paragraph(text, style=BODY):
    return Paragraph(escape(str(text or "")).replace("\n", "<br/>"), style)


def _percent(value):
    return "N/A" if value is None else f"{value}%"


def _recruitment_row(code, counts, original=None):
    target = original["goal_target"] if original else None
    cumulative_target = original["cumulative_target"] if original else None
    monthly, cumulative = counts["monthly_count"], counts["cumulative_count"]
    return {
        "activity_code": code, "activity_description": "Reclutamiento de grupos",
        "achievement_text": (f"{monthly} residenciales atendidos en el mes; "
                             f"{cumulative} residenciales distintos acumulados en el período de la propuesta."),
        "activities_count": monthly,
        "monthly_percent": goal_percent(monthly, target),
        "met": monthly >= target if target is not None else None,
        "goal_summary": original["goal_summary"] if original else "Meta no configurada",
        "cumulative_ratio": _format_cumulative_ratio(cumulative, cumulative_target),
        "percent": goal_percent(cumulative, cumulative_target),
    }


def checklist_rows(context, populations, recruitment=None):
    """Group the original row objects for display without changing their values."""
    programs = []
    for program in context.get("program_blocks", []):
        source_rows = {row["activity_code_id"]: row for row in program["rows"]}
        displayed = set()
        rows = []
        matching = next((block for block in populations if block["program"].code == program["program_code"]), {})
        for population in matching.get("population_blocks", []):
            key = (program["program_code"], population["population_label"])
            counts = (recruitment or {}).get(key)
            code = recruitment_code(*key, population["rows"])
            selected = [source_rows[row["activity_code_id"]] for row in population["rows"]
                        if row["activity_code_id"] in source_rows and row["activity_code_id"] not in displayed]
            if selected or counts is not None:
                rows.append((population["population_label"], None))
                if counts is not None:
                    original = next((row for row in selected if code and row["activity_code"].casefold() == code), None)
                    rows.append((None, _recruitment_row(code, counts, original)))
                    if original:
                        displayed.add(original["activity_code_id"])
                for row in selected:
                    if row["activity_code_id"] not in displayed:
                        rows.append((None, row))
                        displayed.add(row["activity_code_id"])
        remaining = [row for row in program["rows"] if row["activity_code_id"] not in displayed]
        if remaining:
            rows.append((program["program_display_name"], None))
            rows.extend((None, row) for row in remaining)
        programs.append((program["program_code"], rows))
    return programs


def _table(rows, month):
    headings = [
        f"PROGRAMA POR ACTIVIDAD SEGÚN\nEL PLAN DE TRABAJO SOMETIDO PARA EL MES DE {month}",
        "ACTIVIDAD\nREALIZADA", "",
        "POR CIENTO (%) DE LOGROS ALCANZADOS\nPOR PROGRAMA DE CADA ACTIVIDAD REALIZADA",
        f'SE LOGRÓ EL 100%\n"MILESTONE" PARA {month}', "FRECUENCIA",
        "ACTIVIDADES\nLOGRADAS POR\nPERIODO\nPROPUESTA",
        "POR CIENTO (%) DE\nLOGROS ALCANZADOS\nPERIODO PROPUESTA",
    ]
    cells = [[_paragraph(value, HEADER) for value in headings],
             ["", _paragraph("SÍ", HEADER), _paragraph("NO", HEADER), "", "", "", "", ""]]
    commands = [("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#C6D9F1")),
                ("SPAN", (1, 0), (2, 0)), ("BACKGROUND", (1, 1), (2, 1), colors.white)]
    for column in (0, 3, 4, 5, 6, 7):
        commands.append(("SPAN", (column, 0), (column, 1)))
    for group, row in rows:
        if row is None:
            cells.append([_paragraph("PROGRAMA #" + group.upper(), GROUP), "", "", "", "", "", "",
                          _paragraph("95.0% IP-GOAL", HEADER)])
            index = len(cells) - 1
            commands.extend([("SPAN", (0, index), (-2, index)),
                             ("BACKGROUND", (0, index), (-1, index), colors.HexColor("#8DB3E2"))])
            continue
        description = Paragraph(
            "<b>" + escape(row["activity_code"].upper()) + "</b> " + escape(row["activity_description"])
            + "<br/><i>" + escape(row["achievement_text"]) + "</i>", BODY)
        cells.append([description,
                      _paragraph("X" if row["activities_count"] > 0 else "", CENTER),
                      _paragraph("" if row["activities_count"] > 0 else "X", CENTER),
                      _paragraph(_percent(row["monthly_percent"]), CENTER),
                      _paragraph("N/A" if row["met"] is None else "SI" if row["met"] else "NO", CENTER),
                      _paragraph(row["goal_summary"], CENTER),
                      _paragraph(row["cumulative_ratio"], CENTER),
                      _paragraph(_percent(row["percent"]), CENTER)])
    table = Table(cells, colWidths=WIDTHS, hAlign="LEFT")
    table.setStyle(TableStyle(commands + [
        ("GRID", (0, 0), (-1, -1), .4, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    return table


def checklist_pdf(context, populations, residential_names, authorized_name="", *, recruitment=None):
    output = BytesIO()
    canvas = Canvas(output, pagesize=(792, 612))
    canvas.setTitle("Hoja mensual de cotejo - " + context["period_label"])
    month = context["period_label"].rsplit(" ", 1)[0]
    year = context["selected_year"]
    month_number = context["selected_month"]
    last_day = monthrange(year, month_number)[1]
    residences = _paragraph("RESIDENCIALES: " + residential_names, ParagraphStyle("ChecklistLocations", parent=BODY, fontName=FONTS["bold"], fontSize=6, leading=6.96))
    _, location_height = residences.wrap(756, 120)
    top = min(496, 513 - location_height)

    def decorate():
        logo = STATIC / "checklist_header.png"
        if logo.exists():
            canvas.drawImage(str(logo), 24.35, 570.41, width=150.95, height=37.493, mask="auto")
        canvas.setFont(FONTS["bold"], 6)
        canvas.drawCentredString(421, 539, "ÁREA DE PROGRAMAS COMUNALES Y DE RESIDENTES")
        canvas.drawCentredString(421, 532, "HOJA MENSUAL DE COTEJO DE PROGRAMAS LOGRADAS POR ACTIVIDAD SEGÚN EL PLAN DE TRABAJO")
        canvas.drawString(18, 525, "COMPAÑÍA: Centro Sor Isolina Ferré, Inc.")
        canvas.drawCentredString(487, 525, f"PERÍODO DE INFORME: DESDE 1 de {month.lower()} de {year} HASTA {last_day} de {month.lower()} de {year}")
        residences.drawOn(canvas, 18, 517 - location_height)
        proposal = context.get("proposal")
        if proposal:
            canvas.setFont(FONTS["normal"], 5.3)
            canvas.drawRightString(771, 547, f"PROPUESTA: {proposal.code} - {proposal.name}")
        certificate = _paragraph("Yo, " + (authorized_name or "____________________________") + " persona autorizada del Programa de Prevención, certifico que la información presentada en este informe es correcta.")
        _, h = certificate.wrap(740, 30)
        certificate.drawOn(canvas, 18, 35 - h)
        canvas.setLineWidth(.4)
        canvas.line(18, 21, 166, 21)
        canvas.line(448, 21, 580, 21)
        canvas.setFont(FONTS["normal"], 6.2)
        canvas.drawCentredString(92, 14, "Firma del Representante Autorizado")
        canvas.drawCentredString(514, 14, "Fecha")

    had_page = False
    for code, entries in checklist_rows(context, populations, recruitment):
        pending = list(entries)
        current_group = code
        while pending:
            page_rows = []
            if pending[0][1] is not None:
                page_rows.append((current_group + " (continuación)", None))
            while pending:
                # In the reference, 3C starts a separate sheet per population.
                if code == "3C" and pending[0][1] is None and any(row is not None for _, row in page_rows):
                    break
                candidate = page_rows + [pending[0]]
                # A section heading must stay with at least its first activity.
                lookahead = candidate + pending[1:2] if pending[0][1] is None else candidate
                height = _table(lookahead, month.upper()).wrap(sum(WIDTHS), 440)[1]
                if height > top - 59:
                    if any(row is not None for _, row in page_rows):
                        break
                    raise PDFRenderError("Una descripción de la hoja de cotejo supera el espacio de una página.")
                item = pending.pop(0)
                page_rows.append(item)
                if item[1] is None:
                    current_group = item[0]
            decorate()
            table = _table(page_rows, month.upper())
            _, height = table.wrap(sum(WIDTHS), 440)
            table.drawOn(canvas, 23, top - height)
            canvas.showPage()
            had_page = True
    if not had_page:
        decorate()
        canvas.setFont("Times-Roman", 9)
        canvas.drawString(24, 470, "No hay actividades configuradas para esta propuesta y período.")
        canvas.showPage()
    canvas.save()
    return output.getvalue()
