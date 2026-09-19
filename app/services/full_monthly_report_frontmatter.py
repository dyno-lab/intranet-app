"""Reference artwork and institutional letter for the complete report only.

The PDF assets contain the source's fixed artwork, not its historical results or
signatures. Report values below come from the existing monthly contexts.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from io import BytesIO
import os
from pathlib import Path
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, KeepTogether, NextPageTemplate, PageBreak,
    PageTemplate, Paragraph, Spacer,
)

from app.services.full_monthly_report_recruitment import recruitment_code


ASSETS = Path(__file__).resolve().parents[1] / "static" / "reports" / "full_monthly"
MONTHS = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")
SECTION_TITLES = (
    "I. Informe de posiciones existentes",
    "II. Informe de centros de servicios",
    "III. Informe mensual de participantes (No duplicado consolidado)",
    "IV. Informe mensual de participantes (No duplicado por residencial)",
    "V. Informe participación consolidado (Por servicio)",
    "VI. Participación mensual de servicios ofrecidos (Por residencial)",
    "VII. Hoja de cotejo de programas logrados por actividad",
    "VIII. Certificación de horas contacto / referidos externos",
    "IX. Informe de visitas",
    "X. Participantes propuestos vs participantes atendidos",
    "XI. Informe prevención de embarazos",
    "XII. Informe de deserción escolar",
    "XIII. Fotos",
)


@lru_cache(maxsize=1)
def _fonts():
    """Use the reference's installed Office fonts; keep other hosts usable."""
    directory = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    selected = {}
    choices = {
        "normal": ("times.ttf", "FullMonthlyTimes", "Times-Roman"),
        "bold": ("timesbd.ttf", "FullMonthlyTimesBold", "Times-Bold"),
        "italic": ("timesi.ttf", "FullMonthlyTimesItalic", "Times-Italic"),
        "boldItalic": ("timesbi.ttf", "FullMonthlyTimesBoldItalic", "Times-BoldItalic"),
        "cover": ("COPRGTB.TTF", "FullMonthlyCopperplate", "Helvetica-Bold"),
        "footer": ("arial.ttf", "FullMonthlyArial", "Helvetica"),
    }
    for key, (filename, name, fallback) in choices.items():
        path = directory / filename
        if path.is_file():
            pdfmetrics.registerFont(TTFont(name, str(path)))
            selected[key] = name
        else:
            selected[key] = fallback
    pdfmetrics.registerFontFamily(selected["normal"], **{
        key: selected[key] for key in ("normal", "bold", "italic", "boldItalic")
    })
    return selected


def _write(writer):
    buffer = BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _centered(canvas, text, x, y, font, maximum_size=24, maximum_width=365):
    size = maximum_size
    width = pdfmetrics.stringWidth(text, font, size)
    if width > maximum_width:
        size *= maximum_width / width
    canvas.setFont(font, size)
    canvas.drawCentredString(x, y, text)


def cover_pdf(data: dict, supplements: dict) -> bytes:
    """Original cover artwork with selected proposals, month and fiscal year."""
    reader = PdfReader(ASSETS / "cover.pdf")
    writer = PdfWriter()
    page = writer.add_page(reader.pages[0], excluded_keys=("/Annots", "/AA"))
    overlay = BytesIO()
    canvas = Canvas(overlay, pagesize=letter)
    font = _fonts()["cover"]
    names = [str(proposal.name) for proposal in data["proposals"]]
    if len(names) == 1:
        _centered(canvas, names[0], 352.87, 382.15, font)
    elif len(names) == 2:
        for index, name in enumerate(names):
            _centered(canvas, name, 352.87, 388 - index * 18, font, 17)
    elif len(names) == 3:
        for index, name in enumerate(names):
            _centered(canvas, name, 352.87, 390 - index * 14, font, 14)
    else:
        _centered(canvas, f"{len(names)} PROPUESTAS SELECCIONADAS", 352.87, 382.15, font, 20)
    month, year = int(data["month"]), int(data["year"])
    fiscal_start = year if month >= 7 else year - 1
    _centered(canvas, f"{MONTHS[month].upper()} {year}", 352.87, 141.74, font)
    _centered(canvas, f"Año Fiscal {fiscal_start}-{fiscal_start + 1}", 352.87, 114.98, font)
    canvas.save()
    page.merge_page(PdfReader(overlay).pages[0])
    return _write(writer)


def section_cover_pdf(index: int, data: dict) -> bytes:
    """Return the unchanged reference divider (zero-based section index)."""
    if not 0 <= index < len(SECTION_TITLES):
        raise ValueError("La sección del informe no existe.")
    return (ASSETS / f"section_{index + 1:02d}.pdf").read_bytes()


def contents_pdf(entries: list[dict], data: dict) -> bytes:
    """The Word index's Times text, dotted leaders and triple page border."""
    fonts = _fonts()
    style = ParagraphStyle("CompleteContents", fontName=fonts["normal"],
                           fontSize=12, leading=15)

    class ContentsLine(Flowable):
        def __init__(self, entry):
            super().__init__()
            self.entry = entry
            self.indent = 36 if entry.get("level") else 0
            self.label = Paragraph(escape(str(entry["title"])), style)

        def wrap(self, available_width, available_height):
            self.width = available_width
            _, height = self.label.wrap(available_width - self.indent - 52, available_height)
            self.height = max(20.4, height + 5.4)
            return self.width, self.height

        def draw(self):
            self.label.drawOn(self.canv, self.indent, 5.4)
            self.canv.setFont(fonts["normal"], 12)
            self.canv.drawRightString(self.width, 8, str(self.entry["page"]))
            text_width = pdfmetrics.stringWidth(str(self.entry["title"]), fonts["normal"], 12)
            leader_start = self.indent + text_width + 12
            if self.height <= 21 and leader_start < self.width - 58:
                x = leader_start
                while x < self.width - 52:
                    self.canv.drawString(x, 8, ".")
                    x += 30

    def decorate(canvas, doc):
        canvas.setStrokeColorRGB(0, 0, 0)
        canvas.setLineWidth(.45)
        for inset in (24, 25.2, 26.4):
            canvas.rect(inset, inset, 612 - inset * 2, 792 - inset * 2)

    output = BytesIO()
    doc = BaseDocTemplate(output, pagesize=letter, title="Tabla de Contenido",
                          author="Programa Faro de Esperanza")
    frame = Frame(90, 57, 432, 666, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="contents", frames=[frame], onPage=decorate)])
    title_style = ParagraphStyle("CompleteContentsTitle", parent=style,
                                fontName=fonts["bold"], alignment=1,
                                spaceAfter=8, keepWithNext=True)
    doc.build([Paragraph("Tabla de Contenido", title_style),
               *[ContentsLine(entry) for entry in entries]])
    return output.getvalue()


def _roman(number):
    text = ""
    for value, letters in ((1000, "m"), (900, "cm"), (500, "d"), (400, "cd"),
                           (100, "c"), (90, "xc"), (50, "l"), (40, "xl"),
                           (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")):
        while number >= value:
            number -= value
            text += letters
    return text


def _letter_decoration(canvas, doc, first=False):
    fonts = _fonts()
    if first:
        canvas.drawImage(str(ASSETS / "letter_avp.png"), 14.25, 699.76,
                         width=146.6, height=68.988, mask="auto")
        canvas.drawImage(str(ASSETS / "letter_csif.png"), 199.3, 613.2,
                         width=213.4, height=142.8, mask="auto")
    else:
        canvas.setFont(fonts["normal"], 12)
        canvas.drawRightString(522, 746, "Página " + _roman(doc.page))
    canvas.drawImage(str(ASSETS / "letter_faro.png"), 23.35, 13.746,
                     width=147.95, height=61.65, mask="auto")
    canvas.setFont(fonts["footer"], 9)
    for y, line in ((59.304, "Centros Sor Isolina Ferré, Inc. - Programa Faro de Esperanza"),
                    (48.984, "PO Box 7313, Ponce, Puerto Rico 0073-7313"),
                    (38.52, "Teléfono: (787) 842-0000 Ext. 1206/1208")):
        canvas.drawCentredString(306.05, y, line)


def _plain(value):
    return escape(str(value if value is not None else "")).replace("\n", "<br/>")


def _number(value):
    return f"{int(value or 0):,}"


def _program_rows(block):
    """Present each current activity once; never add repeated population rows."""
    rows = {}
    for population in block["population_blocks"]:
        for row in population["rows"]:
            rows.setdefault(row["activity_code_id"], row)
    return rows


def letter_pdf(data: dict, supplements: dict) -> bytes:
    """Institutional letter in the reference layout, with current report values.

    The optional narrative adds observations; it never replaces the calculated
    summary. The signature area is blank unless an authorized name is supplied.
    No handwritten signature or historical count is copied from the source.
    """
    fonts = _fonts()
    initial = ParagraphStyle("LetterFirst", fontName=fonts["normal"], fontSize=11.04,
                             leading=12.64, spaceAfter=12.64, alignment=TA_JUSTIFY)
    body = ParagraphStyle("LetterBody", parent=initial, fontSize=9.96,
                          leading=11.52, spaceAfter=11.52)
    heading = ParagraphStyle("LetterHeading", parent=body, fontName=fonts["bold"],
                             spaceBefore=4, spaceAfter=0, keepWithNext=True,
                             leftIndent=54)
    activity = ParagraphStyle("LetterActivity", parent=body, spaceAfter=0,
                              leftIndent=68, firstLineIndent=-14)
    address = ParagraphStyle("LetterAddress", parent=initial, spaceAfter=0, alignment=0)
    datestyle = ParagraphStyle("LetterDate", parent=address, fontSize=12, leading=14)
    def paragraph(text, style=body):
        return Paragraph(text, style)
    supplied_date = supplements.get("letter_date")
    report_date = date.fromisoformat(supplied_date) if supplied_date else date.today()
    period = f"{MONTHS[int(data['month'])]} {data['year']}"
    residentials = data["residentials"]
    recruitment = data.get("recruitment")
    reached_ids = set(recruitment["monthly_residential_ids"]) if recruitment is not None else None
    locations = [r["residential_name"] + (
        f" ({r['residential'].municipality})" if r["residential"].municipality else ""
    ) for r in residentials if reached_ids is None or r["residential_id"] in reached_ids]
    if recruitment is not None:
        listed_ids = {r["residential_id"] for r in residentials}
        locations.extend(recruitment["residential_names"][identifier]
                         for identifier in sorted(reached_ids - listed_ids))
    story = [
        paragraph(f"{report_date.day} de {MONTHS[report_date.month]} de {report_date.year}", datestyle),
        Spacer(1, 24),
        paragraph("Sra. Olga Santiago Jiménez<br/>"
                  "Gerente de Programas División de Propuestas de Servicio<br/>"
                  "Programas Comunales y Servicios al Residentes<br/>"
                  "Administración de Vivienda Pública<br/>"
                  "Ave. Barbosa 606 Edif. Juan C. Cordero<br/>"
                  "Río Piedras, PR 00936-3188", address),
        Spacer(1, 24),
        paragraph("Estimada Sra. Santiago:", initial),
        paragraph(f"Respetuosamente <b>{_plain(period)}</b>. En este informe estamos evidenciando "
                  "el trabajo que se está realizando diariamente en el Programa Faro de Esperanza "
                  f"en los {_number(len(locations))} residenciales impactados mencionados a continuación:", initial),
        paragraph(_plain(", ".join(locations)) + "." if locations
                  else "No se registraron residenciales con asistencia confirmada durante el mes.", initial),
        paragraph("Durante el mes reportado hemos tenido una participación activa de "
                  f"<b><i><u>{_number(data['no_duplicado']['total_all'])} participantes certificados</u></i></b> "
                  "en nuestro programa. En resumen, el Programa Faro de Esperanza de los Centros Sor "
                  "Isolina Ferré ofreció durante el mes reportado un total de "
                  f"<b><i><u>{_number(data['duplicado']['total_all'])} servicios</u></i></b> "
                  "(firmas durante el período), según hojas de asistencias.", initial),
    ]
    if len(data["proposals"]) > 1:
        story.append(paragraph("Propuestas incluidas: " + _plain(
            "; ".join(str(proposal.name) for proposal in data["proposals"])) + ".", initial))
    story.extend([
        paragraph("El Programa cuenta con los siguientes programas de servicios:", initial),
        NextPageTemplate("following"), PageBreak(),
    ])
    program_sections = {section["program"].code: section
                        for section in data["por_programa"]["program_sections"]}
    for block in data["hoja_cotejo"]["program_blocks"]:
        code = block["program"].code
        program = program_sections.get(code)
        active_rows = {key: row for key, row in _program_rows(block).items()
                       if row["activities_count"] or row["duplicados"]}
        service_count = sum(row["duplicados"] for row in _program_rows(block).values())
        if program is None:
            # An absent existing-program context is not evidence of zero people.
            unique_phrase = ""
        else:
            unique_phrase = ("una participación de "
                             f"<b><i><u>{_number(program['total_all'])} participantes</u></i></b> con ")
        name = _plain(block["program_display_name"])
        story.append(paragraph(f"En el <b>{name}</b> tuvimos durante el mes reportado "
                               f"{unique_phrase}un total de <b><i><u>{_number(service_count)} servicios</u></i></b> "
                               "ofrecidos. Los mismos se desglosan a continuación:"))
        sequence = 0
        displayed = set()
        for population in block["population_blocks"]:
            group_counts = data.get("recruitment", {}).get("groups", {}).get((code, population["population_label"]))
            group_code = recruitment_code(code, population["population_label"], population["rows"])
            population_rows = [row for row in population["rows"]
                               if row["activity_code_id"] in active_rows
                               and row["activity_code_id"] not in displayed]
            if not population_rows and group_counts is None:
                continue
            story.append(paragraph(f"PROGRAMA #{_plain(code)}: {_plain(str(population['population_label']).upper())}", heading))
            if group_counts is not None:
                sequence += 1
                story.append(paragraph(
                    f"{sequence}. Reclutamiento de grupos - "
                    f"<b><u>{_number(group_counts['monthly_count'])}</u></b> residenciales atendidos en el mes; "
                    f"<b><u>{_number(group_counts['cumulative_count'])}</u></b> residenciales distintos acumulados "
                    "en el período de la propuesta.", activity))
            for row in population_rows:
                displayed.add(row["activity_code_id"])
                if group_counts is not None and group_code and row["activity_code"].casefold() == group_code:
                    continue
                sequence += 1
                story.append(paragraph(
                    f"{sequence}. {_plain(row['activity_description'])} - "
                    f"<b><u>{_number(row['activities_count'])}</u></b> actividades a "
                    f"<b><u>{_number(row['duplicados'])}</u></b> participaciones.", activity))
        if not active_rows:
            story.append(paragraph("No se registraron actividades durante el período."))
        story.extend([Spacer(1, 11.52), paragraph(
            f"Se completaron <b><u>{_number(len(active_rows))}</u></b> tipos de actividades "
            f"en el Programa {_plain(code)}.")])
    story.append(PageBreak())
    hours = f"{float(data['total_contact_hours']):,.2f}"
    visits = data["visitas"]
    external_referrals = sum(
        str(row.get("referral_type") or "").casefold() == "externo"
        for row in visits.get("referral_rows", [])
    )
    story.extend([
        paragraph(f"Un total de <b><i><u>{hours} horas contacto a tiempo real</u></i></b> se certificaron. "
                  f"Nuestro personal realizó un total de <b><i><u>{_number(visits['summary']['visits'])} visitas</u></i></b>, "
                  f"con <b><i><u>{_number(visits['summary']['attendances'])} participaciones</u></i></b>, "
                  f"y <b><i><u>{_number(external_referrals)} referidos externos</u></i></b> "
                  "para el manejo de casos individualizados."),
        paragraph("Ver informe adjunto para más información sobre las actividades y servicios realizados "
                  f"por el Programa Faro de Esperanza durante el mes de <b>{_plain(period)}</b>."),
    ])
    coverage = data.get("coverage", {})
    inactive = coverage.get("inactive_residentials_with_data", [])
    if inactive:
        story.append(paragraph(
            "Cobertura: los totales globales incluyen registros de residenciales actualmente inactivos. "
            "Las hojas individuales conservan el alcance de los reportes actuales (residenciales activos). "
            "Inactivos con datos: " + _plain(", ".join(row["residential_name"] for row in inactive)) + "."))
    if coverage.get("has_unassigned_data"):
        story.append(paragraph(
            "Cobertura: existen registros del período sin residencial asignado. "
            "Verifica su clasificación antes de finalizar el informe."))
    if supplements.get("narrative"):
        story.append(paragraph(_plain(supplements["narrative"])))
    authorized = (supplements.get("letter_signer_name") or supplements.get("authorized_name")
                  or data.get("authorized_name") or "")
    signature_lines = [
        _plain(authorized) if authorized else "________________________________________",
        _plain(supplements.get("letter_signer_title") or "Funcionario autorizado"),
    ]
    if supplements.get("letter_copy"):
        signature_lines.append(_plain(supplements["letter_copy"]))
    signature = [
        paragraph("Agradecemos la colaboración y el respaldo que han ofrecido a nuestro programa.<br/>Cordialmente,"),
        paragraph("<br/>".join(signature_lines)),
    ]
    story.append(KeepTogether(signature))
    output = BytesIO()
    doc = BaseDocTemplate(output, pagesize=letter, title="Carta de resumen de logros del mes",
                          author="Programa Faro de Esperanza", allowSplitting=True)
    first_frame = Frame(90.024, 90, 432, 502, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    next_frame = Frame(90.024, 90, 432, 617, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[first_frame],
                     onPage=lambda canvas, document: _letter_decoration(canvas, document, True),
                     autoNextPageTemplate="following"),
        PageTemplate(id="following", frames=[next_frame], onPage=_letter_decoration),
    ])
    doc.build(story)
    return output.getvalue()
