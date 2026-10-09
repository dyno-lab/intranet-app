from copy import deepcopy
from io import BytesIO
from types import SimpleNamespace
import unittest

from pypdf import PdfReader

from tests import test_full_monthly_report_data as fixtures
from app.services.full_monthly_report_frontmatter import letter_pdf


class FullMonthlyLetterActivityCountTests(unittest.TestCase):
    def setUp(self):
        fixture = fixtures.FullMonthlyReportDataTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.data = fixture.build()
        self.rows = [
            dict(activity_code_id=number, activity_code=f"2.b.{number}",
                 activity_description=description, activities_count=activities, duplicados=people)
            for number, description, activities, people in (
                (2, "Visitas al Hogar o contacto con participantes", 10, 10),
                (3, "Apoyo y Seguimiento: Referidos Internos", 1, 1),
                (4, "Intercesoría para Empleo", 5, 7),
                (5, "Incentivo Educativo – Cuarto Año", 15, 15),
                (6, "Certificación Cursos Educativos, Vocacionales y Tecnológicos", 8, 16),
                (7, "Apoyo Social y Emocional para el Desarrollo de Habilidades de Autosuficiencia Económica", 9, 11),
            )
        ]
        self.block = {
            "program": SimpleNamespace(code="2B"),
            "program_display_name": "Programa 2B",
            "population_blocks": [{"population_label": "2B JÓVENES Y ADULTOS", "rows": self.rows}],
        }
        self.data["hoja_cotejo"]["program_blocks"] = [self.block]
        self.data["por_programa"]["program_sections"] = [
            {"program": self.block["program"], "total_all": 20},
        ]
        self.data["recruitment"]["groups"] = {
            ("2B", "2B JÓVENES Y ADULTOS"): {"monthly_count": 10, "cumulative_count": 18},
        }

    def text(self):
        payload = letter_pdf(self.data, {"letter_date": "2026-08-11"})
        return " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(payload)).pages).split())

    def test_user_example_counts_seven_listed_activities_including_recruitment(self):
        before = deepcopy((self.block, self.data["recruitment"]["groups"]))
        text = self.text()
        self.assertIn("Se completaron 7 tipos de actividades en el Programa 2B.", text)
        self.assertIn("10 residenciales atendidos en el mes; 18 residenciales distintos acumulados", text)
        self.assertIn("20 participantes", text)
        self.assertIn("un total de 60 servicios", text)
        for row in self.rows:
            self.assertIn(f"{row['activities_count']} actividades a {row['duplicados']} participaciones", text)
        self.assertEqual((self.block, self.data["recruitment"]["groups"]), before)

    def test_recruitment_already_in_catalogue_counts_only_once(self):
        self.rows.insert(0, dict(activity_code_id=1, activity_code="2.b.1",
                                activity_description="Reclutamiento de grupos",
                                activities_count=4, duplicados=9))
        text = self.text()
        self.assertEqual(text.count("Reclutamiento de grupos"), 1)
        self.assertIn("Se completaron 7 tipos de actividades en el Programa 2B.", text)
        self.assertIn("un total de 69 servicios", text)

    def test_history_without_activity_this_month_does_not_count_as_completed(self):
        for row in self.rows:
            row.update(activities_count=0, duplicados=0)
        self.data["recruitment"]["groups"][("2B", "2B JÓVENES Y ADULTOS")]["monthly_count"] = 0
        text = self.text()
        self.assertIn("0 residenciales atendidos en el mes; 18 residenciales distintos acumulados", text)
        self.assertIn("Se completaron 0 tipos de actividades en el Programa 2B.", text)

    def test_recruitment_without_monthly_coverage_does_not_add_to_other_activities(self):
        self.data["recruitment"]["groups"][("2B", "2B JÓVENES Y ADULTOS")]["monthly_count"] = 0
        self.assertIn("Se completaron 6 tipos de actividades en el Programa 2B.", self.text())

    def test_recruitment_itself_is_an_activity_when_residentials_were_reached(self):
        self.rows.clear()
        text = self.text()
        self.assertIn("Se completaron 1 tipos de actividades en el Programa 2B.", text)
        self.assertNotIn("No se registraron actividades durante el período.", text)

    def test_multiple_populations_count_their_recruitment_and_shared_activity_once(self):
        self.block.update(program=SimpleNamespace(code="1A"), program_display_name="Programa 1A")
        self.block["population_blocks"] = [
            {"population_label": "Niños", "rows": self.rows[:1]},
            {"population_label": "Jóvenes", "rows": self.rows[:1]},
        ]
        self.data["recruitment"]["groups"] = {
            ("1A", "Niños"): {"monthly_count": 10, "cumulative_count": 18},
            ("1A", "Jóvenes"): {"monthly_count": 5, "cumulative_count": 8},
        }
        other = {"program": SimpleNamespace(code="3C"), "program_display_name": "Programa 3C",
                 "population_blocks": [{"population_label": "Adultos", "rows": self.rows[1:2]}]}
        self.data["hoja_cotejo"]["program_blocks"].append(other)
        text = self.text()
        self.assertEqual(text.count("Visitas al Hogar o contacto con participantes"), 1)
        self.assertIn("Se completaron 3 tipos de actividades en el Programa 1A.", text)
        self.assertIn("Se completaron 1 tipos de actividades en el Programa 3C.", text)


if __name__ == "__main__":
    unittest.main()
