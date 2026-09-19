"""Centers sheet for the complete report, using current residential scope.

Office addresses, telephone numbers and the count of service centers remain
manual. The reference contributes only its layout and institutional logos.
"""
from __future__ import annotations

from collections import OrderedDict
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import BaseDocTemplate, Frame, LongTable, PageTemplate, Paragraph, Spacer, TableStyle


ASSETS = Path(__file__).resolve().parents[1] / "static" / "reports" / "full_monthly"
PENDING = "Pendiente de completar"
GREEN = colors.HexColor("#92D050")


@lru_cache(maxsize=1)
def _fonts():
    directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    normal, bold = "Times-Roman", "Times-Bold"
    if (directory / "ROCK.TTF").is_file() and (directory / "ROCKB.TTF").is_file():
        normal, bold = "FullMonthlyCentersRockwell", "FullMonthlyCentersRockwellBold"
        pdfmetrics.registerFont(TTFont(normal, str(directory / "ROCK.TTF")))
        pdfmetrics.registerFont(TTFont(bold, str(directory / "ROCKB.TTF")))
        pdfmetrics.registerFontFamily(normal, normal=normal, bold=bold, italic=normal, boldItalic=bold)
    return normal, bold


def _escaped(value):
    return escape(str(value if value is not None else "")).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br/>")


def _decoration(canvas, doc):
    canvas.drawImage(str(ASSETS / "centers_csif_header.png"), 203.9, 676.0,
                     width=242.0, height=84.0, mask="auto")
    canvas.drawImage(str(ASSETS / "centers_faro_footer.png"), 54.6, 24.827,
                     width=223.45, height=93.15, mask="auto")


def centers_pdf(data: dict, supplements: dict) -> bytes:
    """Return the reference's three-column sheet without importing old values.

    Municipalities organize the known residential scope; they are not treated as
    offices or counted as service centers. Long municipality groups may continue
    across pages under repeated table headings. ``centers_notes`` is plain text.
    """
    normal, bold = _fonts()
    cell = ParagraphStyle("CentersCell", fontName=normal, fontSize=11.04, leading=12.6,
                          alignment=TA_CENTER, wordWrap="CJK")
    header = ParagraphStyle("CentersHeader", parent=cell, fontName=bold)
    title = ParagraphStyle("CentersTitle", parent=header, fontSize=18, leading=21)
    notes = ParagraphStyle("CentersNotes", parent=cell, alignment=TA_LEFT, leading=14, spaceAfter=8)
    def paragraph(text, style=cell):
        return Paragraph(text, style)

    groups = OrderedDict()
    residentials = data["residentials"]
    for row in residentials:
        residential = row["residential"]
        municipality = str(residential.municipality or "").strip()
        group_key = municipality.casefold()
        if group_key not in groups:
            groups[group_key] = {"municipality": municipality, "residentials": []}
        name = row["residential_name"]
        groups[group_key]["residentials"].append(_escaped(name))

    rows = [
        [paragraph("Service Centers", title), "", ""],
        [paragraph("Office Service", header), paragraph("Impacted Public<br/>Housing", header), paragraph("Telephone", header)],
    ]
    for group in groups.values():
        municipality = group["municipality"]
        location = ("Municipio: " + _escaped(municipality)) if municipality else "Municipio pendiente de completar"
        # Keep rows within the page body. Splitting one enormous table cell can
        # duplicate table headings and leave the municipality on a later page.
        chunks, chunk = [], []
        for name in group["residentials"]:
            candidate = paragraph("<br/>".join([*chunk, name]))
            if chunk and candidate.wrap(130.45, 400)[1] > 400:
                chunks.append(chunk)
                chunk = []
            chunk.append(name)
        if chunk:
            chunks.append(chunk)
        for index, chunk in enumerate(chunks):
            label = location + (" (continuación)" if index else "")
            rows.append([
                paragraph("<b>" + label + "</b><br/><br/>Dirección del centro:<br/>" + PENDING),
                paragraph("<br/>".join(chunk)),
                paragraph(PENDING),
            ])
    if not groups:
        rows.append([paragraph(PENDING), paragraph("Sin residenciales en el alcance seleccionado."), paragraph(PENDING)])
    rows.extend([
        [paragraph("Total Office / Service Centers", header), paragraph(PENDING), ""],
        [paragraph(f"Residenciales incluidos: {len(residentials)}", header), "", ""],
    ])
    table = LongTable(rows, colWidths=[237.7, 140.45, 126.10], repeatRows=2,
                      hAlign="LEFT", splitByRow=1)
    table.setStyle(TableStyle([
        ("SPAN", (0, 0), (-1, 0)), ("BACKGROUND", (0, 0), (-1, 0), GREEN),
        ("GRID", (0, 0), (-1, -2), .5, GREEN),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("SPAN", (1, -2), (2, -2)), ("SPAN", (0, -1), (-1, -1)),
        ("TOPPADDING", (0, -1), (-1, -1), 10),
    ]))
    story = [table]
    if supplements.get("centers_notes"):
        story.extend([Spacer(1, 12), paragraph(_escaped(supplements["centers_notes"]), notes)])
    output = BytesIO()
    doc = BaseDocTemplate(output, pagesize=letter, title="Service Centers - " + data.get("period_label", ""),
                          author="Programa Faro de Esperanza", allowSplitting=True)
    frame = Frame(53.9166, 132, 504.31, 536.74,
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="centers", frames=[frame], onPage=_decoration)])
    doc.build(story)
    return output.getvalue()
