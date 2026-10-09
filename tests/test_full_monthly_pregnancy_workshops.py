from __future__ import annotations

import unittest

from tests import test_full_monthly_report_data as fixtures
from app.api.routes import reports
from app.services.full_monthly_report_pdf import TEMPLATES


class FullMonthlyPregnancyWorkshopsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FullMonthlyReportDataTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def populate(self):
        fixture = self.fixture
        items = fixture.tables["pregnancy_report_items"]
        # Person 1 only attended under proposal 2. Their unchecked entry under
        # proposal 1 must not supply a pregnancy case or a residential count.
        fixture.db.execute(items.update().where(items.c.report_item_id == 1).values(is_pregnant=True))
        for identifier, gender in ((4, "F"), (5, "M"), (6, "F"), (7, "F"), (8, "F")):
            fixture.insert("participants", participant_id=identifier, residential_id=1,
                           nombre=f"Persona {identifier}", genero=gender, is_active=True)
        fixture.insert("pregnancy_reports", report_id=3, proposal_id=3, residential_id=1,
                       report_month=7, report_year=2026)
        fixture.insert("pregnancy_reports", report_id=4, proposal_id=1, residential_id=1,
                       report_month=8, report_year=2026)
        for identifier, (report_id, participant_id, workshops, pregnant) in enumerate((
            (1, 2, True, True), (2, 2, True, True),  # One male across two proposals.
            (1, 3, False, True), (2, 3, True, True),
            (1, 4, False, True), (1, 5, False, False),  # Recruited only.
            (2, 6, True, False),
            (3, 7, True, True), (4, 8, True, True),  # Outside the selected scope.
        ), 3):
            fixture.insert("pregnancy_report_items", report_item_id=identifier, report_id=report_id,
                           participant_id=participant_id, participated_workshops=workshops,
                           is_pregnant=pregnant)
        fixture.db.commit()

    def render(self, context):
        return TEMPLATES.get_template("ui/reports/embarazo_pdf.html").render(context)

    def test_only_workshop_participants_supply_counts_cases_and_chart(self):
        self.populate()
        context = self.fixture.build()["embarazo"]
        self.assertEqual(context["total"], {
            "recruited": 4, "participation": 4, "f": 3, "m": 1,
            "pregnant_f": 1, "pregnant_m": 1, "pregnancy_cases": 2,
            "non_pregnant": 2, "prevention_pct": 50.0,
        })
        self.assertEqual(context["chart_values"], [2, 2])
        self.assertEqual(sum(row["participation"] for row in context["rows"]), 4)
        html = self.render(context)
        self.assertIn("Participantes en talleres", html)
        self.assertNotIn("Total reclutados", html)

    def test_residential_comes_from_the_record_with_workshops_checked(self):
        # The fixture has one person, unchecked in residential 1 and checked in 2.
        context = self.fixture.build()["embarazo"]
        self.assertEqual([(row["residential_id"], row["participation"]) for row in context["rows"]],
                         [(2, 1)])

    def test_selected_month_and_proposals_still_limit_workshops(self):
        self.populate()
        context = self.fixture.build(proposal_ids=[1])["embarazo"]
        self.assertEqual(context["total"]["recruited"], 1)
        self.assertEqual(context["total"]["f"], 0)
        self.assertEqual(context["total"]["m"], 1)
        self.assertEqual(context["chart_values"], [1, 0])
        august = self.fixture.build(month=8)["embarazo"]
        self.assertEqual(august["total"]["recruited"], 1)
        self.assertEqual(august["total"]["f"], 1)
        self.assertEqual(august["chart_values"], [1, 0])

    def test_recruited_people_without_workshops_produce_no_services(self):
        context = self.fixture.build(proposal_ids=[1])["embarazo"]
        self.assertEqual(context["rows"], [])
        self.assertTrue(all(value == 0 for value in context["total"].values()))
        self.assertEqual(context["chart_values"], [0, 0])
        self.assertIn("No hay participantes con Talleres marcado", self.render(context))

    def test_standalone_report_keeps_its_existing_recruitment_metrics(self):
        self.populate()
        context = reports._build_pregnancy_summary_context(
            self.fixture.db, self.fixture.user, [1, 2], 7, 2026, 0)
        self.assertEqual(context["total"]["recruited"], 6)
        self.assertEqual(context["total"]["participation"], 4)
        self.assertEqual(context["total"]["pregnancy_cases"], 4)
        self.assertIn("Total reclutados", self.render(context))
        self.assertNotIn("Participantes en talleres", self.render(context))


if __name__ == "__main__":
    unittest.main()
