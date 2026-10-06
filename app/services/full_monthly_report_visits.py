"""Visit certification layout from visitas.pdf, using explicitly supplied totals."""
from __future__ import annotations

from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase.pdfmetrics import registerFont, stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from app.services.full_monthly_report_tables import ASSETS, _pages


@lru_cache(maxsize=1)
def _fonts():
    directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    fonts = {}
    for key, filename, fallback in (
        ("body", "times.ttf", "Times-Roman"), ("total", "timesbd.ttf", "Times-Bold"),
        ("heading", "calibrib.ttf", "Helvetica-Bold"), ("label", "calibri.ttf", "Helvetica"),
    ):
        path = directory / filename
        name = "FullMonthlyVisits_" + key
        if path.is_file():
            registerFont(TTFont(name, str(path)))
            fonts[key] = name
        else:
            fonts[key] = fallback
    return fonts


def visits_summary_pdf(entries, total, period_label):
    """Render the supplied rows without selecting a metric or changing its totals."""
    fonts = _fonts()
    styles = {key: ParagraphStyle(
        "Visits_" + key, fontName=font, fontSize=11.04, leading=11.9, alignment=1,
    ) for key, font in fonts.items()}

    def cell(value, style="body"):
        return Paragraph(escape(str(value)), styles[style])

    def build(batch, last):
        rows = [[cell("Residenciales", "heading"), cell("Visitas", "heading")]]
        rows.extend([cell(name), cell(value)] for name, value in batch)
        heights = [14.55] + [13.92] * len(batch)
        if last:
            rows.append([cell("Total Acumuladas", "total"), cell(total, "total")])
            heights.append(14.52)
        table = Table(rows, colWidths=[217.73, 173.06], minRowHeights=heights)
        commands = [
            ("GRID", (0, 0), (-1, -1), .96, colors.black),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E1F2")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]
        if last:
            commands += [("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#DDEBF7")),
                         ("BOX", (0, -1), (-1, -1), 1.92, colors.black)]
        table.setStyle(TableStyle(commands))
        return table

    output = BytesIO()
    canvas = Canvas(output, pagesize=letter, pageCompression=1)
    canvas.setTitle("Certificación de visitas - " + period_label)
    canvas.setAuthor("Centros Sor Isolina Ferré - Faro de Esperanza")
    for index, (table, _) in enumerate(_pages(list(entries), build, 345)):
        if index:
            canvas.showPage()
        canvas.drawImage(str(ASSETS / "chart_017_image11.png"), 191.48, 649.43, 247.48, 80.85, mask="auto")
        canvas.setFont(fonts["heading"], 11.04)
        canvas.drawCentredString(312.4, 641.1, "Faro de Esperanza")
        canvas.drawCentredString(312.4, 624.78, "Certificación visitas realizadas por el personal de servicios al residente.")
        canvas.setFont(fonts["body"], 11.04)
        canvas.drawString(98.304, 594.96, "Mes:")
        canvas.drawCentredString(191.49, 594.96, period_label)
        canvas.drawString(406.87, 594.96, "Área:")
        canvas.drawCentredString(492.62, 594.96, "Servicios al Residente")
        canvas.setLineWidth(.96)
        canvas.line(122.42, 591.7, 260.56, 591.7)
        canvas.line(433.39, 591.7, 551.85, 591.7)
        label = "Programa para niños, jóvenes, adultos y adulto mayor."
        canvas.setFont(fonts["label"], 11.04)
        canvas.drawCentredString(312.4, 567.54, label)
        half_width = stringWidth(label, fonts["label"], 11.04) / 2
        canvas.setLineWidth(.72)
        canvas.line(312.4 - half_width, 565.78, 312.4 + half_width, 565.78)
        _, height = table.wrap(800, 2000)
        table.drawOn(canvas, 122.42, 549.334 - height)
        canvas.setFont(fonts["label"], 8.04)
        canvas.drawString(73.704, 161.56, "Nota: Esta información fue corroborada mediante la verificación de Hoja de Visitas.")
        canvas.drawImage(str(ASSETS / "visits_footer.png"), 62.987, 52.491, 259.12, 105.33, mask="auto")
    canvas.save()
    return output.getvalue()
