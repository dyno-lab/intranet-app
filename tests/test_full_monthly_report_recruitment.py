from datetime import date
from io import BytesIO
import unittest

from pypdf import PdfReader
from sqlalchemy import event

from tests import test_full_monthly_report_data as fixtures
from app.services.full_monthly_report_checklist import checklist_pdf
from app.services.full_monthly_report_frontmatter import letter_pdf


class CompleteReportRecruitmentTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FullMonthlyReportDataTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.insert = self.fixture.insert
        self.insert("proposals", proposal_id=4, code="4", name="Propuesta nueva", is_active=True)
        self.insert("activity_codes", activity_code_id=40, proposal_id=4,
                    code="1.a.2", description="Servicio a niños", is_active=True)
        self.configure(4, "Niños", 40)
        for identifier in range(10, 24):
            self.insert("residentials", residential_id=identifier, code=f"R{identifier}",
                        name=f"Residencial {identifier}", is_active=True)
        self.next_session = 100

    def configure(self, proposal_id, label, activity_id):
        self.insert("proposal_population_groups", population_group_id=proposal_id,
                    proposal_id=proposal_id, code=label, label=label, sort_order=0, is_active=True)
        self.insert("proposal_report_programs", program_id=proposal_id, proposal_id=proposal_id,
                    population_group_id=proposal_id, code="1A", name="Programa 1A", sort_order=0, is_active=True)
        self.insert("proposal_report_program_populations", program_population_id=proposal_id,
                    program_id=proposal_id, population_group_id=proposal_id, sort_order=0, is_active=True)
        self.insert("proposal_report_program_population_activity_codes",
                    program_population_id=proposal_id, activity_code_id=activity_id)

    def session(self, month, residential_id, *, proposal_id=4, activity_id=40, attended=True, year=2026):
        identifier = self.next_session
        self.next_session += 1
        self.insert("activity_sessions", session_id=identifier, proposal_id=proposal_id,
                    residential_id=residential_id, activity_code_id=activity_id, employee_id=1,
                    session_date=date(year, month, 15), hours=1)
        for participant_id in (1, 2):
            self.insert("attendance", attendance_id=identifier * 10 + participant_id,
                        session_id=identifier, participant_id=participant_id, attended=attended)

    def build(self, month=9, proposal_ids=None, year=2026):
        return self.fixture.build(proposal_ids=proposal_ids or [4], month=month, year=year)

    def recruitment(self, month=9, proposal_ids=None, year=2026):
        return self.build(month, proposal_ids, year)["recruitment"]

    def example(self):
        for month, residential_ids in ((7, range(10, 21)), (8, range(10, 22)), (9, range(10, 19))):
            for identifier in residential_ids:
                self.session(month, identifier)
        self.session(9, 10)  # Multiple sessions and people do not add groups.
        self.session(10, 22)  # A future new residential cannot enter September.
        self.session(6, 23, attended=False)

    def test_eleven_twelve_nine_accumulates_twelve_distinct_residentials(self):
        self.example()
        for month, monthly, cumulative in ((7, 11, 11), (8, 12, 12), (9, 9, 12), (10, 1, 13)):
            with self.subTest(month=month):
                data = self.recruitment(month)
                group = data["groups"][("1A", "Niños")]
                self.assertEqual(group["monthly_count"], monthly)
                self.assertEqual(group["cumulative_count"], cumulative)
                self.assertEqual(len(data["cumulative_residential_ids"]), cumulative)
                self.assertEqual(data["by_proposal"][4]["start_date"], date(2026, 7, 15))
                self.assertNotIn(23, data["cumulative_residential_ids"])

    def test_new_residential_adds_even_when_monthly_count_is_smaller(self):
        for identifier in range(10, 22):
            self.session(8, identifier)
        for identifier in [*range(10, 18), 22]:
            self.session(9, identifier)
        group = self.recruitment()["groups"][("1A", "Niños")]
        self.assertEqual(group["monthly_count"], 9)
        self.assertEqual(group["cumulative_count"], 13)  # Union, not max(monthly).

    def test_proposal_population_assignment_precedes_consolidation(self):
        for identifier, label in ((5, "Jóvenes"), (6, "Niños")):
            self.insert("proposals", proposal_id=identifier, code=str(identifier), name=label, is_active=True)
            self.insert("proposal_activity_codes", proposal_id=identifier, activity_code_id=40, is_active=True)
            self.configure(identifier, label, 40)
        self.session(7, 10)
        self.session(8, 10, proposal_id=6)
        self.session(8, 11, proposal_id=6)
        self.session(9, 12, proposal_id=5)
        self.session(9, 13, proposal_id=3)  # Not selected.
        result = self.recruitment(proposal_ids=[4, 5, 6])
        self.assertEqual(result["groups"][("1A", "Niños")]["cumulative_count"], 2)
        self.assertEqual(result["groups"][("1A", "Jóvenes")]["cumulative_count"], 1)
        self.assertEqual(result["cumulative_residential_ids"], [10, 11, 12])
        self.assertEqual(result["by_proposal"][4]["groups"][("1A", "Niños")]["cumulative_count"], 1)
        self.assertEqual(result["by_proposal"][6]["start_date"], date(2026, 8, 15))

    def test_session_location_not_participant_home_and_unassigned_is_not_a_group(self):
        self.session(9, 12)
        self.session(9, None)
        table = self.fixture.tables["residentials"]
        self.fixture.db.execute(table.update().where(table.c.residential_id == 12).values(is_active=False))
        result = self.recruitment()
        self.assertEqual(result["monthly_residential_ids"], [12])
        self.assertEqual(result["groups"][("1A", "Niños")]["monthly_count"], 1)

    def test_empty_month_preserves_history_and_new_year_does_not_restart(self):
        self.session(11, 10)
        result = self.recruitment(month=1, year=2027)
        self.assertEqual(result["groups"][("1A", "Niños")]["monthly_count"], 0)
        self.assertEqual(result["groups"][("1A", "Niños")]["cumulative_count"], 1)
        before = self.recruitment(month=10)
        self.assertEqual(before["cumulative_residential_ids"], [])
        self.assertIsNone(before["by_proposal"][4]["start_date"])

    def test_letter_and_checklist_show_same_counts_without_changing_existing_metrics(self):
        self.example()
        data = self.build()
        context = data["hoja_cotejo_admin"][0]
        before = dict(context["totals"])
        text = " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(letter_pdf(data, {}))).pages).split())
        self.assertIn("9 residenciales impactados", text)
        self.assertIn("Reclutamiento de grupos", text)
        self.assertIn("9 residenciales atendidos en el mes", text)
        self.assertIn("12 residenciales distintos acumulados", text)
        proposal = data["recruitment"]["by_proposal"][4]
        payload = checklist_pdf(context, proposal["program_blocks"], "Residenciales de prueba",
                                recruitment=proposal["groups"])
        text = " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(payload)).pages).split())
        self.assertIn("1.A.1 Reclutamiento de grupos", text)
        self.assertIn("9 residenciales atendidos en el mes", text)
        self.assertIn("12 residenciales distintos acumulados", text)
        self.assertIn("Meta no configurada", text)
        self.assertEqual(context["totals"], before)
        self.assertEqual(context["totals"]["activities_count"], 10)

    def test_generation_only_reads_and_keeps_sql_parameter_count_bounded(self):
        for _ in range(1100):
            self.session(9, 10)
        statements = []
        def inspect(conn, cursor, statement, parameters, context, executemany):
            statements.append((statement, len(parameters)))
        event.listen(self.fixture.engine, "before_cursor_execute", inspect)
        try:
            result = self.recruitment()
        finally:
            event.remove(self.fixture.engine, "before_cursor_execute", inspect)
        self.assertEqual(result["groups"][("1A", "Niños")]["monthly_count"], 1)
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql, _ in statements))
        self.assertLess(max(count for _, count in statements), 2100)

    def test_configured_recruitment_goal_is_preserved_without_duplicate_rows(self):
        self.example()
        self.insert("activity_codes", activity_code_id=41, proposal_id=4,
                    code="1.a.1", description="Reclutamiento de grupos", is_active=True)
        self.insert("proposal_report_program_population_activity_codes",
                    program_population_id=4, activity_code_id=41)
        self.insert("activity_productivity_goals", productivity_goal_id=41, proposal_id=4,
                    activity_code_id=41, goal_type="global_fixed", goal_value=12,
                    period_goal_value=12, is_active=True)
        from app.services.full_monthly_report_checklist import checklist_rows
        data = self.build()
        context = data["hoja_cotejo_admin"][0]
        proposal = data["recruitment"]["by_proposal"][4]
        groups = checklist_rows(context, proposal["program_blocks"], proposal["groups"])
        rows = [row for _, entries in groups for _, row in entries if row]
        recruitment = [row for row in rows if row["activity_code"] == "1.a.1"]
        self.assertEqual(len(recruitment), 1)
        self.assertEqual(recruitment[0]["monthly_percent"], 75)
        self.assertEqual(recruitment[0]["cumulative_ratio"], "12/12")
        self.assertEqual(recruitment[0]["percent"], 100)
        original = next(row for row in context["program_blocks"][0]["rows"] if row["activity_code"] == "1.a.1")
        self.assertEqual(original["activities_count"], 0)
        self.assertEqual(original["cumulative_ratio"], "0/12")

    def test_renamed_population_keeps_configured_recruitment_code_and_goal(self):
        self.session(9, 10)
        population = self.fixture.tables["proposal_population_groups"]
        self.fixture.db.execute(population.update().where(population.c.population_group_id == 4)
                                .values(label="Niños (5 a 12 años)"))
        self.insert("activity_codes", activity_code_id=41, proposal_id=4,
                    code="1.a.1", description="Reclutamiento de grupos", is_active=True)
        self.insert("proposal_report_program_population_activity_codes",
                    program_population_id=4, activity_code_id=41)
        self.insert("activity_productivity_goals", productivity_goal_id=41, proposal_id=4,
                    activity_code_id=41, goal_type="global_fixed", goal_value=12,
                    period_goal_value=12, is_active=True)
        self.session(9, 10, activity_id=41)
        from app.services.full_monthly_report_checklist import checklist_rows
        data = self.build()
        proposal = data["recruitment"]["by_proposal"][4]
        groups = checklist_rows(data["hoja_cotejo_admin"][0], proposal["program_blocks"], proposal["groups"])
        rows = [row for _, entries in groups for _, row in entries if row]
        recruitment = [row for row in rows if row["activity_description"] == "Reclutamiento de grupos"]
        self.assertEqual(len(recruitment), 1)
        self.assertEqual(recruitment[0]["activity_code"], "1.a.1")
        self.assertEqual(recruitment[0]["cumulative_ratio"], "1/12")
        text = " ".join(" ".join(page.extract_text() for page in PdfReader(BytesIO(letter_pdf(data, {}))).pages).split())
        self.assertEqual(text.count("Reclutamiento de grupos"), 1)
        self.assertIn("1 residenciales atendidos en el mes", text)


if __name__ == "__main__":
    unittest.main()
