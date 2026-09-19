from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import unittest

from pypdf import PdfReader

from tests import test_full_monthly_report_data as fixtures
from app.services.full_monthly_report_checklist import checklist_pdf, checklist_rows
from app.services.full_monthly_report_frontmatter import cover_pdf, letter_pdf
from app.services.full_monthly_report_pdf import _reference_population_panels
from app.services.report_pdf import PDFRenderError


class FullMonthlyReferenceTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.FullMonthlyReportDataTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.data = fixture.build()

    def test_cover_replaces_historical_month_proposal_and_fiscal_year(self):
        data = {**self.data, "month": 3, "year": 2027}
        text = PdfReader(BytesIO(cover_pdf(data, {}))).pages[0].extract_text()
        self.assertIn("MARZO 2027", text)
        self.assertIn("2026-2027", text)
        self.assertIn("Propuesta 1", text)
        self.assertIn("Propuesta 2", text)
        self.assertNotIn("JULIO 2026", text)
        self.assertNotIn("2025-000094-C", text)

    def test_letter_current_values_date_signer_and_coverage_are_preserved(self):
        self.data["coverage"]["has_unassigned_data"] = True
        pdf = letter_pdf(self.data, {"letter_date": "2026-08-11", "letter_signer_name": "Firmante de prueba",
                                     "letter_signer_title": "Dirección", "letter_copy": "c: Revisión institucional"})
        text = " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages).split())
        for value in ("11 de agosto de 2026", "2 participantes certificados", "total de 3 servicios",
                      "5.50 horas contacto", "1 referidos externos", "Firmante de prueba", "Dirección",
                      "c: Revisión institucional", "sin residencial"):
            self.assertIn(value, text)
        self.assertNotIn("4,982", text)

    def test_checklist_keeps_each_original_activity_and_existing_percentages(self):
        context = self.data["hoja_cotejo_admin"][0]
        rows = context["program_blocks"][0]["rows"]
        before = deepcopy(rows)
        displayed = [row for _, group in checklist_rows(context, self.data["hoja_cotejo"]["program_blocks"])
                     for _, row in group if row is not None]
        self.assertEqual(displayed, rows)
        self.assertIs(displayed[0], rows[0])
        pdf = checklist_pdf(context, self.data["hoja_cotejo"]["program_blocks"], "Residencial 1", "Firma de prueba")
        text = " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(pdf)).pages).split())
        self.assertIn("ACTIVIDAD REALIZADA", text)
        self.assertIn('"MILESTONE" PARA JULIO', text)
        self.assertIn("Firma de prueba", text)
        self.assertIn(rows[0]["achievement_text"], text)
        self.assertEqual(rows, before)

    def test_overlong_checklist_row_fails_instead_of_looping_or_clipping(self):
        context = self.data["hoja_cotejo_admin"][0]
        context["program_blocks"][0]["rows"][0]["activity_description"] = "texto extenso " * 20000
        with self.assertRaises(PDFRenderError):
            checklist_pdf(context, self.data["hoja_cotejo"]["program_blocks"], "Residencial 1")

    def test_population_chart_uses_only_the_six_activities_in_the_reference(self):
        rows = [{"activity_code": code, "activities_count": activity, "duplicados": duplicated}
                for code, activity, duplicated in (("1.a.7", 2, 7), ("3.c.5", 3, 8),
                    ("1.a.14", 4, 9), ("3.c.13", 5, 10), ("3.a.31", 6, 11), ("4.a.11", 7, 12),
                    ("1.a.2", 900, 9000))]
        context = {"program_blocks": [{"population_blocks": [{"rows": rows}]}]}
        panels = _reference_population_panels(context)
        self.assertEqual([p["activities"] for p in panels], [[2, 3], [4, 5], [6], [7]])
        self.assertEqual([p["duplicated"] for p in panels], [[7, 8], [9, 10], [11], [12]])


if __name__ == "__main__":
    unittest.main()
