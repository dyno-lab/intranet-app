"""Keep the existing VCA detail and append the institutional sheet in Legal."""
from io import BytesIO

from pypdf import PdfReader, PdfWriter

from app.services.report_pdf import render_template_to_pdf_bytes


def render_vca_legacy_pdf(*, templates, context, request=None):
    # wkhtmltopdf cannot switch paper sizes using named CSS pages. Render the
    # original detail with its existing settings, then append the Legal summary.
    detail = render_template_to_pdf_bytes(
        templates=templates, template_name="ui/reports/vca_pdf.html",
        context={**context, "vca_summary": None}, request=request,
    )
    writer = PdfWriter()
    writer.append(PdfReader(BytesIO(detail)))
    summary = render_template_to_pdf_bytes(
        templates=templates, template_name="ui/reports/vca_compliance_pdf.html",
        context=context, request=request,
        wkhtmltopdf_args=[
            "--page-size", "Legal", "--orientation", "Landscape",
            "--margin-top", "8.9mm", "--margin-bottom", "8.9mm",
            "--margin-left", "8.9mm", "--margin-right", "8.9mm",
            "--footer-left", "REV. 2024", "--footer-center", "[page]",
            "--footer-right", "INFORME DE CUMPLIMIENTO VCA",
            "--footer-font-name", "Arial", "--footer-font-size", "6",
            "--page-offset", str(len(writer.pages)),
        ],
    )
    writer.append(PdfReader(BytesIO(summary)))
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
