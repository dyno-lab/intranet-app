from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch

from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject
from reportlab.pdfgen.canvas import Canvas

from tests import test_full_monthly_report_data as fixtures
from app.services import full_monthly_report_pdf as renderer


def _one_page(text="Sección original"):
    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792))
    canvas.drawString(45, 735, text)
    canvas.save()
    return output.getvalue()


class FullMonthlyReportPdfTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.FullMonthlyReportDataTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.fixture = fixture
        self.data = fixture.build()

    def build(self, **supplements):
        # Keep real report contexts and assembly. Browser PDF rendering has its
        # own integration coverage and is the sole substituted collaborator.
        with patch.object(renderer, "_original", side_effect=lambda name, *_: _one_page("Reporte: " + name)):
            result = renderer.build_full_monthly_pdf(self.data, supplements)
        return PdfReader(BytesIO(result))

    def section_text(self, reader, title):
        outlines = reader.outline
        index = next(i for i, item in enumerate(outlines) if item.title.startswith(title))
        start = reader.get_destination_page_number(outlines[index])
        stop = reader.get_destination_page_number(outlines[index + 1]) if index + 1 < len(outlines) else len(reader.pages)
        return "\n".join(page.extract_text() for page in reader.pages[start:stop])

    def test_real_context_assembles_thirteen_sections_and_correct_page_navigation(self):
        reader = self.build(narrative="Logros del mes de prueba.", authorized_name="Autorizado")
        self.assertEqual(len(reader.outline), 13)
        destinations = [reader.get_destination_page_number(item) for item in reader.outline]
        self.assertEqual(destinations, sorted(set(destinations)))
        self.assertGreater(destinations[0], 1)
        self.assertLess(destinations[-1], len(reader.pages))
        toc = "\n".join(page.extract_text() for page in reader.pages[:destinations[0]])
        for item, destination in zip(reader.outline, destinations):
            self.assertIn(item.title, toc)
            self.assertIn("\n" + str(destination + 1) + "\n", toc)
            self.assertIn(item.title.split(".")[0] + ".", reader.pages[destination].extract_text())
        self.assertIn("Logros del mes de prueba.", toc)
        self.assertIn("2 participantes certificados", " ".join(toc.split()))
        self.assertIn("total de 3 servicios", " ".join(toc.split()))
        self.assertIn("Julio 2026", reader.metadata.title)
        for number, page in enumerate(reader.pages, 1):
            if number - 1 < destinations[0] - 1 or number - 1 in destinations:
                self.assertNotIn("Informe completo -", page.extract_text())
            else:
                self.assertIn(f"Informe completo - {number} / {len(reader.pages)}", page.extract_text())

    def test_manual_missing_target_does_not_become_zero_or_create_a_global_target(self):
        reader = self.build(targets={1: 0})
        text = " ".join(self.section_text(reader, "X.").split())
        self.assertIn("Residencial 1 Ponce Pendiente Pendiente 0 2 3 No aplica No aplica", text)
        self.assertIn("Residencial 2 Ponce Pendiente Pendiente Pendiente 1 1", text)
        self.assertIn("TOTAL 2 / / Pendiente 2 3", text)
        self.assertNotIn("0.00%", text)

    def test_complete_targets_use_global_unique_participants_for_percentage(self):
        reader = self.build(targets={1: 2, 2: 2})
        text = " ".join(self.section_text(reader, "X.").split())
        # Two monthly uniques and three cumulative uniques, not the sums of
        # residential rows (three and four respectively), divided by goal four.
        self.assertIn("TOTAL 2 / / 4 2 3 50% 75%", text)

    def test_calculated_hours_and_visits_remain_consistent_with_existing_contexts(self):
        reader = self.build()
        hours = " ".join(self.section_text(reader, "VIII.").split())
        self.assertIn("Residencial 1 2.00 2.00", hours)
        self.assertIn("Residencial 2 3.50 3.50", hours)
        self.assertIn("Total Acumuladas 5.50 5.50", hours)
        self.assertIn("Total Acumulados 1", hours)
        visits = self.section_text(reader, "IX.")
        self.assertIn("Visitas\nAsistencias\nHoras", visits)
        self.assertIn("Total\n3\n3\n5.50", visits)

    def test_manual_text_is_literal_and_does_not_become_reportlab_markup(self):
        reader = self.build(narrative="Resultado <b>literal</b> & comprobado", centers_notes="Oficina <script>alert(1)</script>")
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Resultado <b>literal</b> & comprobado", text)
        self.assertIn("Oficina <script>alert(1)</script>", text)

    def test_sheet_pagination_is_css_and_keeps_report_values_escaped(self):
        html = renderer.TEMPLATES.get_template("ui/reports/full_monthly_sheet.html").render({
            **self.data["no_duplicado"], "authorized_name": "<script>test</script>",
            "source_template": "ui/reports/no_duplicado_pdf.html",
            "sheet_css": "thead { display: table-header-group; }",
        })
        self.assertIn("<style>thead { display: table-header-group; }</style></head>", html)
        self.assertNotIn("&lt;style&gt;", html)
        self.assertNotIn("<script>test</script>", html)
        self.assertIn("&lt;script&gt;test&lt;/script&gt;", html)

    def test_empty_month_still_generates_a_complete_document_with_zero_metrics(self):
        self.data = self.fixture.build(month=8)
        reader = self.build()
        self.assertEqual(len(reader.outline), 13)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("0 participantes certificados", " ".join(text.split()))
        self.assertIn("total de 0 servicios", " ".join(text.split()))
        self.assertIn("Agosto 2026", reader.metadata.title)
        self.assertIn("Total Acumuladas 0.00 0.00", " ".join(self.section_text(reader, "VIII.").split()))

    def test_thirty_residentials_paginate_charts_without_losing_last_location(self):
        for identifier in range(3, 31):
            self.fixture.insert("residentials", residential_id=identifier, code=f"R{identifier:02}",
                                name=f"Residencial {identifier:02}", municipality="Ponce", is_active=True)
        self.data = self.fixture.build()
        reader = self.build()
        self.assertEqual(len(reader.outline), 13)
        self.assertIn("Residencial 30", self.section_text(reader, "III."))
        self.assertIn("2 participantes certificados", " ".join(" ".join(p.extract_text() for p in reader.pages[:8]).split()))

    def test_attachment_preserves_visible_content_and_excludes_active_pdf_objects(self):
        writer = PdfWriter()
        writer.add_page(PdfReader(BytesIO(_one_page("PLAZAS MANUALES AUTORIZADAS"))).pages[0])
        action = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert('test')")})
        writer.pages[0][NameObject("/AA")] = DictionaryObject({NameObject("/O"): action})
        writer.pages[0][NameObject("/Annots")] = ArrayObject([DictionaryObject({NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject("/Link"), NameObject("/A"): action})])
        writer.add_js("app.alert('document test')")
        writer.add_attachment("private.txt", b"attachment data")
        payload = BytesIO()
        writer.write(payload)
        item = renderer.validate_supplement_file(payload.getvalue())
        reader = self.build(files={"staffing_pdf": item})
        self.assertIn("PLAZAS MANUALES AUTORIZADAS", self.section_text(reader, "I."))
        self.assertEqual(list(reader.attachments), [])
        self.assertNotIn("/OpenAction", reader.trailer["/Root"])
        for page in reader.pages:
            self.assertNotIn("/AA", page)
            self.assertNotIn("/Annots", page)

    def test_visible_signature_and_form_annotations_require_a_flattened_copy(self):
        for subtype in ("/Stamp", "/Widget"):
            with self.subTest(subtype=subtype):
                writer = PdfWriter()
                writer.add_page(PdfReader(BytesIO(_one_page("DOCUMENTO FIRMADO"))).pages[0])
                writer.pages[0][NameObject("/Annots")] = ArrayObject([DictionaryObject({
                    NameObject("/Type"): NameObject("/Annot"), NameObject("/Subtype"): NameObject(subtype),
                })])
                output = BytesIO()
                writer.write(output)
                with self.assertRaisesRegex(ValueError, "(?i)aplan|imprim"):
                    renderer.validate_supplement_file(output.getvalue())

    def test_photo_validation_and_pdf_assembly_accept_real_png_and_preserve_order(self):
        image = Image.new("RGB", (80, 60), "#287050")
        output = BytesIO()
        image.save(output, format="PNG")
        photo = renderer.validate_supplement_file(output.getvalue(), allow_image=True)
        self.assertEqual(photo["kind"], "image")
        with Image.open(BytesIO(photo["content"])) as normalized:
            self.assertEqual(normalized.format, "JPEG")
            self.assertEqual(normalized.size, (80, 60))
        pdf_photo = renderer.validate_supplement_file(_one_page("SEGUNDA EVIDENCIA"), allow_image=True)
        reader = self.build(photos=[photo, pdf_photo])
        text = self.section_text(reader, "XIII.")
        self.assertLess(text.index("Evidencia fotográfica 1"), text.index("SEGUNDA EVIDENCIA"))
        self.assertGreater(sum(len(page.images) for page in reader.pages), 0)

    def test_invalid_and_encrypted_pdf_and_non_photo_images_are_rejected(self):
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        writer.encrypt("password")
        encrypted = BytesIO()
        writer.write(encrypted)
        image = Image.new("RGB", (10, 10), "white")
        gif = BytesIO()
        image.save(gif, format="GIF")
        for payload, allow_image in ((b"invalid", False), (b"%PDF-1.7\ninvalid", False),
                                     (encrypted.getvalue(), False), (gif.getvalue(), True)):
            with self.subTest(payload=payload[:12], allow_image=allow_image), self.assertRaises(ValueError):
                renderer.validate_supplement_file(payload, allow_image=allow_image)


if __name__ == "__main__":
    unittest.main()
