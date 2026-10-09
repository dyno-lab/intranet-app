from __future__ import annotations

import unittest
from hashlib import sha256
from io import BytesIO
from pathlib import Path
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
        center_pages = set(range(destinations[1] + 1, destinations[2]))
        for number, page in enumerate(reader.pages, 1):
            if number - 1 < destinations[0] - 1 or number - 1 in destinations or number - 1 in center_pages:
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
        visits = " ".join(self.section_text(reader, "IX.").split())
        self.assertIn("Certificación visitas realizadas por el personal de servicios al residente.", visits)
        self.assertIn("Residenciales Visitas", visits)
        self.assertIn("Residencial 1 2 Residencial 2 1", visits)
        self.assertIn("Total Acumuladas 3", visits)
        self.assertNotIn("Visitas Asistencias Horas", visits)
        self.assertIn("Gráfica 6:", visits)
        self.assertNotIn("Reporte: visitas", visits)
        self.assertNotIn("Visitas por puesto", visits)
        self.assertNotIn("Pendiente de completar", visits)
        starts = [reader.get_destination_page_number(item) for item in reader.outline]
        # Section IX contains only its cover, certification and chart by default.
        self.assertEqual(starts[9] - starts[8], 3)

    def test_manual_text_is_literal_and_does_not_become_reportlab_markup(self):
        reader = self.build(narrative="Resultado <b>literal</b> & comprobado", centers_notes="Oficina <script>alert(1)</script>")
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("Resultado <b>literal</b> & comprobado", text)
        self.assertNotIn("Oficina <script>alert(1)</script>", text)

    def test_centers_are_the_two_original_pages_without_added_text_or_scaling(self):
        source_path = Path(__file__).resolve().parents[1] / "app/static/reports/full_monthly/service_centers.pdf"
        self.assertEqual(sha256(source_path.read_bytes()).hexdigest(),
                         "48eee734eac36ea7db8f7aeb8f3016d0a67320e7c55279ca5fc1af96965fce32")
        source = PdfReader(source_path)
        reader = self.build(centers_notes="No modificar las páginas originales")
        starts = [reader.get_destination_page_number(item) for item in reader.outline]
        pages = reader.pages[starts[1] + 1:starts[2]]
        self.assertEqual(len(pages), 2)
        self.assertEqual([(float(p.mediabox.width), float(p.mediabox.height)) for p in pages],
                         [(612, 792), (792, 612)])
        for original, included in zip(source.pages, pages):
            self.assertEqual(included.get_contents().get_data(), original.get_contents().get_data())
            self.assertEqual(included.extract_text(), original.extract_text())
            self.assertEqual(included.mediabox, original.mediabox)
            self.assertEqual(included.cropbox, original.cropbox)
            self.assertEqual(included.rotation, original.rotation)
            self.assertEqual([image.data for image in included.images], [image.data for image in original.images])
            self.assertNotIn("Informe completo -", included.extract_text())
        self.assertIn("Service Centers", pages[0].extract_text())
        self.assertIn("Residents Services Centers", pages[1].extract_text())
        # The next cover is still indexed at its physical page after both sheets.
        self.assertEqual(starts[2] - starts[1], 3)

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
        self.assertIn("Residencial 1 0 Residencial 2 0 Total Acumuladas 0",
                      " ".join(self.section_text(reader, "IX.").split()))

    def test_thirty_residentials_paginate_charts_without_losing_last_location(self):
        for identifier in range(3, 31):
            self.fixture.insert("residentials", residential_id=identifier, code=f"R{identifier:02}",
                                name=f"Residencial {identifier:02}", municipality="Ponce", is_active=True)
        self.data = self.fixture.build()
        reader = self.build()
        self.assertEqual(len(reader.outline), 13)
        self.assertIn("Residencial 30", self.section_text(reader, "III."))
        visits = " ".join(self.section_text(reader, "IX.").split())
        self.assertIn("Residencial 30 0", visits)
        self.assertEqual(visits.count("Total Acumuladas"), 1)
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

    def test_uploaded_staffing_and_centers_replace_provisional_sheets(self):
        files = {key: renderer.validate_supplement_file(_one_page(label)) for key, label in (
            ("staffing_pdf", "POSICIONES FINALES"), ("centers_pdf", "CENTROS Y MAPA FINALES"),
            ("visit_roles_pdf", "VISITAS POR PUESTO AUTORIZADAS"),
        )}
        staffing = PdfWriter()
        for label in ("POSICIONES FINALES", "PLAZAS SEGUNDA HOJA"):
            staffing.add_page(PdfReader(BytesIO(_one_page(label))).pages[0])
        payload = BytesIO()
        staffing.write(payload)
        files["staffing_pdf"] = renderer.validate_supplement_file(payload.getvalue())
        reader = self.build(files=files)
        for section, label in (("I.", "POSICIONES FINALES"), ("II.", "CENTROS Y MAPA FINALES"),
                               ("IX.", "VISITAS POR PUESTO AUTORIZADAS")):
            body = self.section_text(reader, section)
            self.assertEqual(body.count(label), 1)
            self.assertNotIn("Pendiente de completar", body)
            self.assertNotIn("Plazas autorizadas, ocupadas y vacantes", body)
            self.assertNotIn("Office Service", body)
        # Each section retains its existing cover followed by the supplied PDF.
        starts = [reader.get_destination_page_number(item) for item in reader.outline]
        self.assertEqual(starts[1] - starts[0], 3)
        self.assertIn("PLAZAS SEGUNDA HOJA", self.section_text(reader, "I."))
        self.assertEqual(starts[2] - starts[1], 2)
        self.assertEqual(starts[9] - starts[8], 4)
        visits = self.section_text(reader, "IX.")
        self.assertLess(visits.index("Gráfica 6:"), visits.index("VISITAS POR PUESTO AUTORIZADAS"))
        self.assertNotIn("Reporte: visitas", visits)

    def test_missing_staffing_reserves_two_numbered_blank_pages_and_keeps_centers(self):
        reader = self.build()
        starts = [reader.get_destination_page_number(item) for item in reader.outline]
        self.assertEqual(starts[1] - starts[0], 3)
        for index in range(starts[0] + 1, starts[1]):
            page = reader.pages[index]
            self.assertEqual(page.extract_text().strip(), f"Informe completo - {index + 1} / {len(reader.pages)}")
            self.assertEqual(len(page.images), 0)
            self.assertEqual((float(page.mediabox.width), float(page.mediabox.height)), (612, 792))
        self.assertIn("Service Centers", self.section_text(reader, "II."))
        self.assertIn("Residents Services Centers", self.section_text(reader, "II."))

    def test_signed_bonafides_replace_only_their_residential_in_order_and_update_index(self):
        signed = PdfWriter()
        for label in ("FIRMADO RESIDENCIAL 1 - PAGINA 1", "FIRMADO RESIDENCIAL 1 - PAGINA 2"):
            signed.add_page(PdfReader(BytesIO(_one_page(label))).pages[0])
        output = BytesIO()
        signed.write(output)
        uploads = {1: renderer.validate_supplement_file(output.getvalue())}
        def original(name, context, _authorized):
            return _one_page(name + " " + str(context.get("residential_name", "")))
        with patch.object(renderer, "_original", side_effect=original) as render:
            reader = PdfReader(BytesIO(renderer.build_full_monthly_pdf(self.data, {"signed_bonafides": uploads})))
        text = self.section_text(reader, "IV.")
        expected = ["no_duplicado Residencial 1", "FIRMADO RESIDENCIAL 1 - PAGINA 1",
                    "FIRMADO RESIDENCIAL 1 - PAGINA 2", "no_duplicado Residencial 2", "bonafide Residencial 2"]
        positions = [text.index(label) for label in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("bonafide Residencial 1", text)
        self.assertNotIn("Certificaciones firmadas - anexo", text)
        self.assertEqual([call.args[1]["residential_name"] for call in render.call_args_list if call.args[0] == "bonafide"],
                         ["Residencial 2"])
        starts = [reader.get_destination_page_number(item) for item in reader.outline]
        self.assertEqual(starts[4] - starts[3], 6)  # Cover, two summaries, three Bonafide pages.
        toc = " ".join(" ".join(page.extract_text() for page in reader.pages[:starts[0]]).split())
        self.assertIn(f'Residencial 1 {starts[3] + 2}', toc)
        self.assertIn(f'Residencial 2 {starts[3] + 5}', toc)
        for index in range(starts[3] + 1, starts[4]):
            self.assertIn(f"Informe completo - {index + 1} / {len(reader.pages)}", reader.pages[index].extract_text())

    def test_all_signed_bonafides_follow_report_order_not_upload_order(self):
        uploads = {identifier: renderer.validate_supplement_file(_one_page(f"FIRMADO {identifier}"))
                   for identifier in (2, 1)}
        with patch.object(renderer, "_original", side_effect=lambda name, *_: _one_page(name)) as render:
            reader = PdfReader(BytesIO(renderer.build_full_monthly_pdf(self.data, {"signed_bonafides": uploads})))
        text = self.section_text(reader, "IV.")
        self.assertLess(text.index("FIRMADO 1"), text.index("FIRMADO 2"))
        self.assertEqual(text.count("FIRMADO 1"), 1)
        self.assertEqual(text.count("FIRMADO 2"), 1)
        self.assertFalse(any(call.args[0] == "bonafide" for call in render.call_args_list))
        self.assertNotIn("Certificaciones firmadas - anexo", text)

    def test_no_signed_bonafides_keep_all_generated_bonafides(self):
        reader = self.build()
        text = self.section_text(reader, "IV.")
        self.assertEqual(text.count("Reporte: bonafide"), 2)
        self.assertEqual(text.count("Reporte: no_duplicado"), 2)
        self.assertNotIn("Certificaciones firmadas - anexo", text)

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
