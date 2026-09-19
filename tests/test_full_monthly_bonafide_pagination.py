from __future__ import annotations

import unittest
from io import BytesIO
from unittest.mock import patch

from pypdf import PdfReader

from app.api.routes.reports import FIXED_SIGNATURES, ROWS_PER_BONAFIDE_PAGE
from app.services import full_monthly_report_pdf as renderer
from app.services import report_pdf


def _available(resolve):
    try:
        resolve()
        return True
    except report_pdf.PDFBackendUnavailableError:
        return False


def bonafide_context(count):
    rows = [dict(index=i, expediente=f"FE-2026-AC-{i:04}",
                 nombre=f"Participante de Prueba {i:03}", f="X", m="", edad=35,
                 edificio="12", apartamento="101") for i in range(1, count + 1)]
    return dict(period_label="Agosto 2026", residential_name="Aristides Chavier",
                municipality="Ponce", rows=rows, rows_per_page=ROWS_PER_BONAFIDE_PAGE,
                pages=[rows[i:i + ROWS_PER_BONAFIDE_PAGE]
                       for i in range(0, len(rows), ROWS_PER_BONAFIDE_PAGE)] or [[]],
                signatures=FIXED_SIGNATURES, report_template_config={})


class FullMonthlyBonafidePaginationTests(unittest.TestCase):
    def assert_sheets_keep_table_signatures_and_number_together(self, count):
        context = bonafide_context(count)
        result = renderer._original("bonafide", context, "")
        reader = PdfReader(BytesIO(result))
        self.assertEqual(len(reader.pages), len(context["pages"]),
                         "Each Bonafide sheet must occupy one physical page, including its number.")
        for number, (page, rows) in enumerate(zip(reader.pages, context["pages"]), 1):
            text = " ".join(page.extract_text().split())
            self.assertIn(f"Página {number} de {len(context['pages'])}", text)
            self.assertIn("CERTIFICACIÓN DE PARTICIPACIÓN DE RESIDENTES BONAFIDE", text)
            for signature in FIXED_SIGNATURES:
                self.assertIn(signature["name"], text)
                self.assertIn(signature["title"], text)
            for row in rows:
                self.assertIn(row["expediente"], text)
                self.assertIn(row["nombre"], text)

    @unittest.skipUnless(_available(report_pdf._resolve_wkhtmltopdf_binary), "wkhtmltopdf is unavailable")
    def test_letter_pages_keep_bonafide_number_with_its_contents_in_wkhtmltopdf(self):
        for count in (0, 24, 25):
            with self.subTest(participants=count):
                self.assert_sheets_keep_table_signatures_and_number_together(count)

    @unittest.skipUnless(_available(report_pdf._resolve_chromium_pdf_binary), "Chromium is unavailable")
    def test_chromium_fallback_preserves_bonafide_contents_and_pagination(self):
        # Only simulate an unavailable first backend; Chromium renders the real HTML.
        with patch.object(report_pdf, "_resolve_wkhtmltopdf_binary",
                          side_effect=report_pdf.PDFBackendUnavailableError):
            self.assert_sheets_keep_table_signatures_and_number_together(25)


if __name__ == "__main__":
    unittest.main()
