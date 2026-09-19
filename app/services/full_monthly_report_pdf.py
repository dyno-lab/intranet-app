"""Assemble the complete monthly document without changing standalone reports.

Calculated tables use their existing contexts and PDF templates. New pages only
present those totals, manual complements and the document's navigation.
"""
from __future__ import annotations

from collections import defaultdict
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from fastapi.templating import Jinja2Templates
from PIL import Image as PillowImage, UnidentifiedImageError
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError
from reportlab.graphics.shapes import Drawing, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen.canvas import Canvas

from app.services.report_pdf import (
    PDFBackendUnavailableError, PDFRenderError,
    render_template_to_chromium_pdf_bytes, render_template_to_pdf_bytes,
)
from app.services import full_monthly_report_charts as charts
from app.services import full_monthly_report_tables as institutional_tables
from app.services.full_monthly_report_checklist import checklist_pdf
from app.services.full_monthly_report_centers import centers_pdf
from app.services.full_monthly_report_frontmatter import SECTION_TITLES, cover_pdf, section_cover_pdf, letter_pdf, contents_pdf

STATIC = Path(__file__).resolve().parents[1] / "static" / "img"
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))
INK = colors.HexColor("#17365D")
PALE = colors.HexColor("#E9EFF7")
STYLES = getSampleStyleSheet()
STYLES.add(ParagraphStyle("ReportCell", fontName="Helvetica", fontSize=8, leading=10, wordWrap="CJK"))
STYLES.add(ParagraphStyle("ReportText", fontName="Helvetica", fontSize=10, leading=15, spaceAfter=10, wordWrap="CJK"))
STYLES.add(ParagraphStyle("ReportTitle", fontName="Helvetica-Bold", fontSize=16, leading=21, textColor=INK, spaceAfter=14))
STYLES.add(ParagraphStyle("ReportSmall", fontName="Helvetica", fontSize=8, leading=11, spaceAfter=8))

SECTIONS = list(SECTION_TITLES)


def validate_supplement_file(payload: bytes, allow_image: bool = False) -> dict:
    if payload.startswith(b"%PDF-"):
        try:
            reader = PdfReader(BytesIO(payload))
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 250:
                raise ValueError("Los anexos PDF deben tener entre 1 y 250 páginas y no estar protegidos.")
            for page in reader.pages:
                if not all(72 <= float(value) <= 3000 for value in (page.mediabox.width, page.mediabox.height)):
                    raise ValueError("El anexo contiene un tamaño de página no permitido.")
                if any(annotation.get_object().get("/Subtype") != "/Link" for annotation in page.get("/Annots", [])):
                    raise ValueError("El anexo contiene campos, firmas o anotaciones interactivas. Adjunta una copia aplanada (impresa a PDF) para conservar su apariencia.")
        except (PdfReadError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError("No se pudo leer uno de los anexos PDF.") from exc
        return {"kind": "pdf", "content": payload}
    if allow_image:
        try:
            with PillowImage.open(BytesIO(payload)) as source:
                if source.format not in {"JPEG", "PNG"} or source.width * source.height > 25000000:
                    raise ValueError("Las fotos deben ser JPEG o PNG, de hasta 25 megapíxeles.")
                source.load()
                from PIL import ImageOps
                normalized = ImageOps.exif_transpose(source).convert("RGB")
                normalized.thumbnail((2400, 2400))
                result = BytesIO()
                normalized.save(result, format="JPEG", quality=90)
                return {"kind": "image", "content": result.getvalue()}
        except (UnidentifiedImageError, OSError, PillowImage.DecompressionBombError) as exc:
            raise ValueError("No se pudo leer la fotografía. Usa JPEG, PNG o PDF.") from exc
    raise ValueError("Este anexo debe ser un archivo PDF válido.")


def _text(value, style="ReportText"):
    return Paragraph(escape(str(value if value is not None else "")).replace("\n", "<br/>"), STYLES[style])


def _table(headers, rows, widths=None, total=False):
    cells = [[_text(value, "ReportCell") for value in row] for row in [headers, *rows]]
    table = Table(cells, colWidths=widths, repeatRows=1, hAlign="LEFT")
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), PALE), ("GRID", (0, 0), (-1, -1), .45, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if total and rows:
        commands.append(("BACKGROUND", (0, -1), (-1, -1), PALE))
    table.setStyle(TableStyle(commands))
    return table


def _bars(entries, width=510):
    entries = list(entries)
    if not entries:
        return _text("No hay datos para mostrar.")
    # Numbers are printed even for empty bars; charts use the same table values.
    row_height, label_width = 25, min(225, width * .44)
    rows = []
    maximum = max([float(value or 0) for _, value in entries] + [1])
    for label, value in entries:
        drawing = Drawing(width - label_width, row_height)
        bar_width = (width - label_width - 55) * float(value or 0) / maximum
        drawing.add(Rect(0, 5, max(0, bar_width), 15, fillColor=INK, strokeColor=None))
        label_value = f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"
        drawing.add(String(bar_width + 5, 9, label_value, fontName="Helvetica", fontSize=8))
        rows.append([_text(label, "ReportCell"), drawing])
    chart = Table(rows, colWidths=[label_width, width - label_width], hAlign="LEFT")
    chart.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                              ("TOPPADDING", (0, 0), (-1, -1), 0),
                              ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return chart


def _pages(title, contents, data, wide=False):
    buffer = BytesIO()
    size = landscape(letter) if wide else letter
    def decoration(canvas, doc):
        canvas.setTitle("Informe mensual completo - " + data["period_label"])
        canvas.setAuthor("Programa Faro de Esperanza")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(INK)
        canvas.drawString(36, size[1] - 28, "CENTROS SOR ISOLINA FERRÉ | PROGRAMA FARO DE ESPERANZA")
        canvas.drawRightString(size[0] - 36, 24, data["period_label"])
        canvas.setStrokeColor(INK)
        canvas.line(36, size[1] - 36, size[0] - 36, size[1] - 36)
    doc = SimpleDocTemplate(buffer, pagesize=size, leftMargin=36, rightMargin=36, topMargin=50, bottomMargin=42)
    doc.build([_text(title, "ReportTitle"), *contents], onFirstPage=decoration, onLaterPages=decoration)
    return buffer.getvalue()


def _original(template, context, authorized_name):
    context = {**context, "authorized_name": authorized_name}
    landscape_templates = {"embarazo", "desercion_escolar", "admin/hoja_cotejo"}
    path = "ui/" + (template if template.startswith("admin/") else "reports/" + template) + "_pdf.html"
    pagination = {
        # The standalone wkhtmltopdf sheet reserves 80px above its page number.
        # On the book's Letter pages that sends only the number to another page.
        # Keep the participant table and both signature rows at their original size.
        "bonafide": ".page-number { margin-top: 12px !important; }",
        "admin/hoja_cotejo": ".page, table.data { page-break-inside: auto !important; break-inside: auto !important; } table.data thead { display: table-header-group; break-inside: avoid; page-break-inside: avoid; } table.data th { overflow-wrap: anywhere; font-size: 7px; padding: 2px; } table.data tr { page-break-inside: avoid; } .header { min-height: .55in; } .logo img { width: 2in; max-height: .50in; } .title-block { padding-top: .02in; } table.data .repeat-header-cell { padding-bottom: 2px !important; } .meta { font-size: 8.5px; }",
        "hoja_cotejo": ".cotejo-main-table th, .cotejo-main-table td { line-height: 1.15 !important; padding-top: 2px; padding-bottom: 2px; } .cotejo-activity-cell, .cotejo-activity-single-line, .cotejo-program-label { white-space: normal !important; overflow: visible !important; }",
        "visitas": ".page { display: block; min-height: 0; } .section { page-break-inside: auto; break-inside: auto; } thead { display: table-header-group; } tfoot { display: table-row-group; } tr { page-break-inside: avoid; } .page-footer { margin-top: 14px; }",
        "embarazo": ".chart-wrap { display: none !important; }",
        "adm": "thead { display: table-header-group; } tr { page-break-inside: avoid; }",
    }
    if template in pagination:
        context = {**context, "source_template": path, "sheet_css": pagination[template]}
        path = "ui/reports/full_monthly_sheet.html"
    if template in {"visitas", "embarazo", "desercion_escolar", "hoja_cotejo", "admin/hoja_cotejo"}:
        try:
            return render_template_to_chromium_pdf_bytes(templates=TEMPLATES, template_name=path, context=context)
        except PDFBackendUnavailableError:
            pass
    try:
        args = ["--page-size", "Letter"]
        if template in landscape_templates:
            args += ["--orientation", "Landscape"]
        if template == "admin/hoja_cotejo":
            for side in ("top", "right", "bottom", "left"):
                args += ["--margin-" + side, "0.25in"]
        payload = render_template_to_pdf_bytes(templates=TEMPLATES, template_name=path, context=context, wkhtmltopdf_args=args)
    except PDFBackendUnavailableError:
        payload = render_template_to_chromium_pdf_bytes(templates=TEMPLATES, template_name=path, context=context)
    if not payload.startswith(b"%PDF-"):
        raise PDFRenderError("Una sección no produjo un PDF válido.")
    return payload


def _image_page(payload, title, data):
    image = Image(BytesIO(payload))
    ratio = min(510 / image.imageWidth, 610 / image.imageHeight)
    image.drawWidth, image.drawHeight = image.imageWidth * ratio, image.imageHeight * ratio
    return _pages(title, [image], data)


def _hours(context):
    return {block["program"].code: block["program_contact_hours"] for block in context["program_blocks"]}


def _program_participations(context):
    values = []
    for block in context["program_blocks"]:
        by_activity = {}
        for population in block["population_blocks"]:
            for row in population["rows"]:
                by_activity[row["activity_code_id"]] = row["duplicados"]
        values.append((block["program"].code, sum(by_activity.values())))
    return values


def _reference_population_panels(context):
    # The model's fourth figure shows these six activity codes, not every
    # activity in each program. Use the exact existing activity row values.
    rows = {row["activity_code"].strip().casefold(): row
            for block in context["program_blocks"]
            for population in block["population_blocks"] for row in population["rows"]}
    definitions = [
        ("Niños", [("Actividades Deportivas", "1.a.7"), ("Actividad de Salud, Bienestar y Prevención", "3.c.5")]),
        ("Jóvenes", [("Actividades Deportivas", "1.a.14"), ("Actividad de Salud, Bienestar y Prevención", "3.c.13")]),
        ("Adulto", [("Actividades Deportivas", "3.a.31")]),
        ("Adulto Mayor", [("Actividades Deportivas", "4.a.11")]),
    ]
    return [{"label": label, "categories": [name for name, _ in items],
             "activities": [rows.get(code, {}).get("activities_count", 0) for _, code in items],
             "duplicated": [rows.get(code, {}).get("duplicados", 0) for _, code in items]}
            for label, items in definitions]


def _merge(parts):
    writer = PdfWriter()
    for payload in parts:
        reader = PdfReader(BytesIO(payload))
        # Copy visible pages only: do not import scripts, attachments, actions or
        # form controls from user-supplied documents into the compilation.
        for page in reader.pages:
            writer.add_page(page, excluded_keys=("/Annots", "/AA"))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def build_full_monthly_pdf(data: dict, supplements: dict) -> bytes:
    files = supplements.get("files", {})
    authorized = supplements.get("authorized_name", "")
    residentials = data["residentials"]
    sections = []
    section_details = {}
    def section(index, parts, details=()):
        parts = list(parts)
        offsets = [1]
        for part in parts:
            offsets.append(offsets[-1] + len(PdfReader(BytesIO(part)).pages))
        section_details[index] = [(title, offsets[part_index]) for title, part_index in details]
        sections.append((SECTIONS[index], _merge([section_cover_pdf(index, data), *parts])))
    def manual(index, key, explanation):
        parts = [_pages(SECTIONS[index], [_text(explanation if key in files else "Pendiente de completar. " + explanation)], data)]
        if key in files:
            parts.append(files[key]["content"])
        return parts

    section(0, manual(0, "staffing_pdf", "Plazas autorizadas, ocupadas y vacantes. Información incorporada manualmente por el administrador."))
    center_parts = [centers_pdf(data, supplements)]
    if "centers_pdf" in files:
        center_parts.append(files["centers_pdf"]["content"])
    section(1, center_parts)
    unique = data["no_duplicado"]
    section(2, [_original("no_duplicado", unique, authorized),
        charts.residential_unique_pdf([(r["residential_name"], r["no_duplicado"]["total_all"]) for r in residentials], data["period_label"])])
    parts = []
    residential_details = []
    for row in residentials:
        residential_details.append((row["residential_name"], len(parts)))
        parts += [_original("no_duplicado", row["no_duplicado"], authorized), _original("bonafide", row["bonafide"], authorized)]
    if "signed_bonafide_pdf" in files:
        parts += [_pages("Certificaciones firmadas - anexo", [_text("Documentos incorporados por el administrador para este período.")], data), files["signed_bonafide_pdf"]["content"]]
    section(3, parts, residential_details)

    programs = data["por_programa"]["program_sections"]
    program_codes = [item["program"].code for item in programs]
    parts = [institutional_tables.duplicated_pdf(data),
        _original("duplicado", data["duplicado"], authorized),
        charts.program_services_pdf(["Programa " + code for code in program_codes],
            [item["total_all"] for item in programs],
            [dict(_program_participations(data["hoja_cotejo"])).get(code, 0) for code in program_codes], data["period_label"]),
        charts.residential_services_pdf([(r["residential_name"], r["duplicado"]["total_all"]) for r in residentials], data["period_label"]),
        _original("por_programa", data["por_programa"], authorized)]
    parts.append(charts.population_activities_pdf(_reference_population_panels(data["hoja_cotejo"]), data["period_label"]))
    section(4, parts)
    section(5, [_original("duplicado", row["duplicado"], authorized) for row in residentials],
            [(row["residential_name"], index) for index, row in enumerate(residentials)])
    parts = []
    for context in data.get("hoja_cotejo_admin", []):
        recruitment = data.get("recruitment", {}).get("by_proposal", {}).get(context["selected_proposal_id"], {})
        parts.append(checklist_pdf(context, recruitment.get("program_blocks", data["hoja_cotejo"]["program_blocks"]),
            ", ".join(row["residential_name"] for row in residentials), authorized,
            recruitment=recruitment.get("groups")))
    section(6, parts)

    global_hours = _hours(data["hoja_cotejo"])
    parts = [institutional_tables.contact_hours_table_pdf(data),
        institutional_tables.external_referrals_pdf(data),
        charts.contact_hours_pdf(list(global_hours.items()), data["period_label"])]
    section(7, parts, [("Horas contacto por programa y residencial", 0),
                       ("Referidos realizados (externos)", 1), ("Gráfica de horas contacto", 2)])
    by_residential = defaultdict(lambda: {"visits": 0, "attendances": 0, "hours": 0})
    for row in data["visitas"]["rows"]:
        bucket = by_residential[row["residential_name"]]
        for key in bucket:
            bucket[key] += row[key]
    visit_rows = [[name, values["visits"], values["attendances"], f'{values["hours"]:.2f}'] for name, values in sorted(by_residential.items())]
    summary = data["visitas"]["summary"]
    visit_rows.append(["Total", summary["visits"], summary["attendances"], f'{summary["hours"]:.2f}'])
    parts = [_pages(SECTIONS[8], [_table(["Residencial", "Visitas", "Asistencias", "Horas"], visit_rows, [260, 85, 95, 100], total=True), Spacer(1, 12),
        _text("Visitas y asistencias se presentan por separado, conforme al reporte actual de visitas.")], data),
        charts.residential_visits_pdf([(r["residential_name"], by_residential[r["residential_name"]]["visits"]) for r in residentials]
            + [(name, values["visits"]) for name, values in sorted(by_residential.items()) if name not in {r["residential_name"] for r in residentials}], data["period_label"]),
        _original("visitas", data["visitas"], authorized)]
    if "visit_roles_pdf" in files:
        parts.append(files["visit_roles_pdf"]["content"])
    else:
        parts.append(_pages("Visitas por puesto", [_text("Pendiente de completar. El desglose por puesto se incorpora mediante un anexo manual; el sistema registra las visitas por empleado.")], data))
    section(8, parts)

    parts = [institutional_tables.participant_targets_pdf(data, supplements)]
    if "targets_pdf" in files:
        parts.append(files["targets_pdf"]["content"])
    section(9, parts)
    pregnancy = data["embarazo"]["total"]
    section(10, [_original("embarazo", data["embarazo"], authorized),
        charts.pregnancy_pdf(pregnancy["pregnancy_cases"], pregnancy["non_pregnant"], data["period_label"])])
    section(11, [_original("desercion_escolar", data["desercion"], authorized)])
    photos = supplements.get("photos", [])
    parts = [_pages(SECTIONS[12], [_text("Evidencia fotográfica incorporada por el administrador." if photos else "Pendiente de completar. No se adjuntaron fotografías para este informe.")], data)]
    for index, item in enumerate(photos, 1):
        parts.append(item["content"] if item["kind"] == "pdf" else _image_page(item["content"], f"Evidencia fotográfica {index}", data))
    section(12, parts)

    cover = cover_pdf(data, supplements)
    letter = letter_pdf(data, supplements)
    front_count = len(PdfReader(BytesIO(cover)).pages) + len(PdfReader(BytesIO(letter)).pages)
    toc_count = 1
    for _ in range(4):
        cursor = front_count + toc_count + 1
        toc_rows = []
        contents_entries = [{"title": "Carta de resumen de logros del mes", "page": "i", "level": 0}]
        for section_index, (title, payload) in enumerate(sections):
            toc_rows.append([title, cursor])
            contents_entries.append({"title": title, "page": cursor, "level": 0})
            for detail_title, offset in section_details.get(section_index, []):
                contents_entries.append({"title": detail_title, "page": cursor + offset, "level": 1})
            cursor += len(PdfReader(BytesIO(payload)).pages)
        toc = contents_pdf(contents_entries, data)
        actual = len(PdfReader(BytesIO(toc)).pages)
        if actual == toc_count:
            break
        toc_count = actual
    writer = PdfWriter()
    for payload in [cover, letter, toc, *[payload for _, payload in sections]]:
        for page in PdfReader(BytesIO(payload)).pages:
            writer.add_page(page, excluded_keys=("/Annots", "/AA"))
    for title, page_number in toc_rows:
        writer.add_outline_item(title, page_number - 1)
    total_pages = len(writer.pages)
    divider_pages = {page_number for _, page_number in toc_rows}
    for number, page in enumerate(writer.pages, 1):
        page.transfer_rotation_to_content()
        if number <= front_count or number in divider_pages:
            continue
        overlay = BytesIO()
        width, height = float(page.mediabox.width), float(page.mediabox.height)
        canvas = Canvas(overlay, pagesize=(width, height))
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#555555"))
        canvas.drawCentredString(width / 2, 9, f"Informe completo - {number} / {total_pages}")
        canvas.save()
        page.merge_page(PdfReader(overlay).pages[0])
    writer.add_metadata({"/Title": "Informe mensual completo - " + data["period_label"], "/Author": "Programa Faro de Esperanza"})
    writer.compress_identical_objects()
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
