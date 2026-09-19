from io import BytesIO
import unittest

from pypdf import PdfReader

from app.services import full_monthly_report_charts as charts


def text_of(payload):
    return "\n".join(page.extract_text() for page in PdfReader(BytesIO(payload)).pages)


class FullMonthlyReportChartsTests(unittest.TestCase):
    def test_program_comparison_prints_both_explicit_series(self):
        text = text_of(charts.program_services_pdf(
            ["Programa A", "Programa B"], [17, 29], [53, 61], "agosto 2026"
        ))
        for value in ("Programa A", "Programa B", "17", "29", "53", "61", "TOTAL PART.", "DUPLICADOS"):
            self.assertIn(value, text)
        with self.assertRaises(ValueError):
            charts.program_services_pdf(["Programa A"], [17], [53, 61])

    def test_pregnancy_percentages_use_supplied_cohort_and_zero_is_empty(self):
        text = text_of(charts.pregnancy_pdf(3, 9))
        self.assertIn("Embarazos, 25%", text)
        self.assertIn("No Embarazos, 75%", text)
        empty = text_of(charts.pregnancy_pdf(0, 0))
        self.assertIn("No hay datos para mostrar.", empty)
        self.assertNotIn("100%", empty)

    def test_hours_table_retains_decimal_values_and_rejects_invalid_values(self):
        text = text_of(charts.contact_hours_pdf([("Programa A", 13.75), ("Programa B", 0)]))
        self.assertIn("13.75", text)
        self.assertIn("0.00", text)
        for value in (-1, float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                charts.contact_hours_pdf([("Programa A", value)])

    def test_large_residential_configuration_preserves_all_entries(self):
        entries = [(f"Residencial {index:02}", index + 1) for index in range(31)]
        for builder in (charts.residential_unique_pdf, charts.residential_visits_pdf):
            with self.subTest(builder=builder.__name__):
                reader = PdfReader(BytesIO(builder(entries)))
                self.assertEqual(len(reader.pages), 2)
                text = "\n".join(page.extract_text() for page in reader.pages)
                for name, _ in entries:
                    self.assertIn(name, text)

    def test_population_panels_preserve_series_and_escape_labels(self):
        text = text_of(charts.population_activities_pdf([{
            "label": "Niños <A>", "categories": ["Actividad <B>"],
            "activities": [17], "duplicated": [43],
        }]))
        for expected in ("Niños <A>", "Actividad <B>", "17", "43", "Actividades", "Duplicados"):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
