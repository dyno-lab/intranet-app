from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from app.services.full_monthly_report_centers import _fonts, centers_pdf


def _residential(number, municipality="Ponce"):
    return {
        "residential_id": number,
        "residential_name": f"Residencial Actual {number:03d}",
        "residential": SimpleNamespace(municipality=municipality, rq_code=f"RQ{number:04d}"),
    }


class FullMonthlyReportCentersTests(unittest.TestCase):
    def test_standard_font_families_remain_unchanged_without_rockwell(self):
        with patch("app.services.full_monthly_report_centers.Path.is_file", return_value=False), \
                patch("app.services.full_monthly_report_centers.pdfmetrics.registerFontFamily") as register:
            self.assertEqual(_fonts.__wrapped__(), ("Times-Roman", "Times-Bold"))
            register.assert_not_called()

    def build(self, residentials, **supplements):
        data = {"period_label": "septiembre 2026", "residentials": residentials}
        original = deepcopy(data)
        reader = PdfReader(BytesIO(centers_pdf(data, supplements)))
        self.assertEqual(data, original)
        return reader, " ".join(" ".join(page.extract_text().split()) for page in reader.pages)

    def test_current_residentials_and_missing_center_details_are_explicit(self):
        _, text = self.build([_residential(1), _residential(2, "Salinas")])
        for value in ("Service Centers", "Office Service", "Impacted Public", "Housing", "Telephone",
                      "Residencial Actual 001", "Ponce", "Salinas",
                      "Pendiente de completar", "Residenciales incluidos: 2"):
            self.assertIn(value, text)
        for historical in ("Avenida Hostos", "CENTRO PLAYA", "787-842-0000", "AMP", "RQ0001"):
            self.assertNotIn(historical, text)

    def test_large_single_municipality_repeats_headers_and_loses_no_residential(self):
        reader, text = self.build([_residential(number) for number in range(1, 121)])
        self.assertGreater(len(reader.pages), 1)
        self.assertLessEqual(len(reader.pages), 5)
        for number in range(1, 121):
            self.assertIn(f"Residencial Actual {number:03d}", text)
        for page in reader.pages:
            self.assertEqual(page.extract_text().count("Telephone"), 1)
            self.assertEqual(page.extract_text().count("Office Service"), 1)
            self.assertIn("Municipio: Ponce", page.extract_text())
            self.assertGreaterEqual(len(page["/Resources"].get("/XObject", {})), 2)

    def test_manual_notes_render_as_literal_text(self):
        _, text = self.build([_residential(1)], centers_notes="<b>Dirección manual</b> & contacto\nSegunda línea")
        self.assertIn("<b>Dirección manual</b> & contacto", text)
        self.assertIn("Segunda línea", text)

    def test_empty_scope_does_not_invent_service_centers(self):
        _, text = self.build([])
        self.assertIn("Sin residenciales en el alcance seleccionado", text)
        self.assertIn("Residenciales incluidos: 0", text)
        self.assertIn("Pendiente de completar", text)

    def test_missing_municipality_stays_missing(self):
        row = _residential(1)
        row["residential"].municipality = None
        row["residential"].rq_code = None
        _, text = self.build([row])
        self.assertIn("Municipio pendiente de completar", text)
        self.assertNotIn("None", text)


if __name__ == "__main__":
    unittest.main()
