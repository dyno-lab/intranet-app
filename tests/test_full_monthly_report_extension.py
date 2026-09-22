from datetime import date
from io import BytesIO
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import event

from app.models.participant import Participant
from app.services import full_monthly_report_pdf as renderer
from app.services.full_monthly_report_checklist import checklist_rows
from tests import test_full_monthly_report_data as fixtures
from tests.test_full_monthly_report_pdf import _one_page


class FullMonthlyReportExtensionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FullMonthlyReportDataTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        proposals = self.fixture.tables["proposals"]
        for identifier, code, name in ((1, "005", "2025-000094-B"), (2, "006", "2025-000094-C")):
            self.fixture.db.execute(proposals.update().where(proposals.c.proposal_id == identifier)
                                    .values(code=code, name=name))
            self.fixture.insert("activity_productivity_goals", productivity_goal_id=identifier,
                                proposal_id=identifier, activity_code_id=10, goal_type="global_fixed",
                                goal_value=12, is_active=True)
        self.fixture.db.commit()

    def build(self, **kwargs):
        return self.fixture.build(**kwargs)

    def test_combined_report_keeps_monthly_metrics_and_uses_one_continuous_checklist(self):
        data = self.build()
        self.assertEqual(len(data["hoja_cotejo_admin"]), 1)
        context = data["hoja_cotejo_admin"][0]
        self.assertEqual(context["selected_proposal_ids"], [1, 2])
        self.assertEqual(context["first_attendance_date"], date(2026, 6, 30))
        self.assertEqual(context["elapsed_months"], 2)
        row = context["program_blocks"][0]["rows"][0]
        self.assertEqual((row["activities_count"], row["duplicados"], row["unique_participants"]), (3, 3, 2))
        self.assertEqual((row["goal_target"], row["monthly_percent"]), (12, 25))
        self.assertEqual(row["cumulative_ratio"], "3/24")
        self.assertEqual(data["no_duplicado"]["total_all"], 2)
        self.assertEqual(data["duplicado"]["total_all"], 3)
        self.assertEqual(data["target_cumulative"]["total_all"], 3)
        self.assertEqual(data["total_contact_hours"], 5.5)
        self.assertEqual(data["por_programa"]["overall_total_all"], 2)
        self.assertEqual(data["embarazo"]["total"]["participation"], 1)
        self.assertEqual(data["desercion"]["total"]["tutoring"], 1)
        self.assertEqual(data["visitas"]["referral_count"], 1)
        recruitment = context["recruitment"]
        groups = checklist_rows(context, recruitment["program_blocks"], recruitment["groups"])
        rows = [row for _, entries in groups for _, row in entries if row]
        self.assertEqual(sum(row["activity_description"] == "Reclutamiento de grupos" for row in rows), 1)
        self.assertIn("2 residenciales distintos acumulados", rows[0]["achievement_text"])

    def test_selecting_only_one_proposal_never_expands_its_data_scope(self):
        for identifier, unique, duplicate, cumulative, start in (
            (1, 2, 2, 3, date(2026, 6, 30)), (2, 1, 1, 1, date(2026, 7, 31)),
        ):
            with self.subTest(proposal=identifier):
                data = self.build(proposal_ids=[identifier])
                self.assertEqual(data["selected_proposal_ids"], [identifier])
                self.assertEqual(data["no_duplicado"]["total_all"], unique)
                self.assertEqual(data["duplicado"]["total_all"], duplicate)
                self.assertEqual(data["target_cumulative"]["total_all"], cumulative)
                context = data["hoja_cotejo_admin"][0]
                self.assertEqual(context["selected_proposal_id"], identifier)
                self.assertEqual(context["first_attendance_date"], start)
                self.assertNotIn("recruitment", context)

    def test_explicit_period_goal_is_used_once_and_empty_month_keeps_history(self):
        goals = self.fixture.tables["activity_productivity_goals"]
        self.fixture.db.execute(goals.update().values(period_goal_value=36))
        self.fixture.db.commit()
        data = self.build(month=8)
        self.assertEqual(len(data["hoja_cotejo_admin"]), 1)
        context = data["hoja_cotejo_admin"][0]
        self.assertEqual(context["elapsed_months"], 3)
        row = context["program_blocks"][0]["rows"][0]
        self.assertEqual(row["activities_count"], 0)
        self.assertEqual(row["cumulative_ratio"], "3/36")
        self.assertEqual(data["target_cumulative"]["total_all"], 3)

    def test_shared_monthly_goal_continues_through_empty_months_and_year_change(self):
        for month, year, elapsed, ratio in ((8, 2026, 3, "3/36"), (1, 2027, 8, "3/96")):
            with self.subTest(month=month, year=year):
                context = self.build(month=month, year=year)["hoja_cotejo_admin"][0]
                self.assertEqual(context["elapsed_months"], elapsed)
                self.assertEqual(context["program_blocks"][0]["rows"][0]["cumulative_ratio"], ratio)

    def test_different_configured_activity_goals_are_reported_instead_of_chosen_silently(self):
        goals = self.fixture.tables["activity_productivity_goals"]
        self.fixture.db.execute(goals.update().where(goals.c.proposal_id == 2).values(goal_value=24))
        self.fixture.db.commit()
        with self.assertRaises(HTTPException) as error:
            self.build()
        self.assertEqual(error.exception.status_code, 422)
        self.assertIn("1.a.2", error.exception.detail)

    def test_other_selected_proposals_keep_their_own_checklist_and_data(self):
        data = self.build(proposal_ids=[3, 2, 1, 2])
        self.assertEqual(len(data["hoja_cotejo_admin"]), 2)
        context = next(c for c in data["hoja_cotejo_admin"] if c.get("selected_proposal_ids") == [1, 2])
        self.assertEqual(context["program_blocks"][0]["rows"][0]["activities_count"], 3)
        self.assertEqual(data["duplicado"]["total_all"], 4)
        self.assertEqual(data["no_duplicado"]["total_all"], 3)
        self.assertTrue(any(c["selected_proposal_id"] == 3 for c in data["hoja_cotejo_admin"]))

    def test_extension_assembly_is_read_only_and_does_not_flush_unrelated_edits(self):
        participant = self.fixture.db.get(Participant, 1)
        participant.nombre = "Cambio ajeno pendiente"
        statements = []
        def record(_conn, _cursor, statement, params, _context, _many):
            statements.append((statement, len(params)))
        event.listen(self.fixture.engine, "before_cursor_execute", record)
        try:
            self.build()
        finally:
            event.remove(self.fixture.engine, "before_cursor_execute", record)
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql, _ in statements))
        self.assertLess(max(count for _, count in statements), 2100)
        self.assertIn(participant, self.fixture.db.dirty)

    def test_pdf_has_one_extension_checklist_with_matching_letter_and_navigation(self):
        data = self.build()
        with patch.object(renderer, "_original", side_effect=lambda name, *_: _one_page("Reporte: " + name)):
            pdf = PdfReader(BytesIO(renderer.build_full_monthly_pdf(data, {})))
        self.assertEqual(len(pdf.outline), 13)
        starts = [pdf.get_destination_page_number(item) for item in pdf.outline]
        text = " ".join(" ".join(page.extract_text() for page in pdf.pages[starts[6]:starts[7]]).split())
        self.assertEqual(text.count("HOJA MENSUAL DE COTEJO"), 1)
        self.assertIn("005", text)
        self.assertIn("006", text)
        self.assertIn("3/24", text)
        self.assertIn("2 residenciales distintos acumulados", text)
        front = " ".join(" ".join(page.extract_text() for page in pdf.pages[:starts[0]]).split())
        self.assertIn("2 participantes certificados", front)
        self.assertIn("total de 3 servicios", front)
        self.assertIn("2 residenciales distintos acumulados", front)
        for number, page in enumerate(pdf.pages, 1):
            if number - 1 > starts[0] and number - 1 not in starts:
                self.assertIn(f"Informe completo - {number} / {len(pdf.pages)}", page.extract_text())


if __name__ == "__main__":
    unittest.main()
