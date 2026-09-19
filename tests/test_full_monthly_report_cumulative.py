from datetime import date
import unittest

from tests import test_full_monthly_report_data as fixtures
from app.services.hoja_cotejo_admin_service import build_hoja_cotejo_admin_context


class CompleteReportCumulativeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FullMonthlyReportDataTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        insert = self.fixture.insert
        insert("proposals", proposal_id=4, code="4", name="Propuesta de prueba", is_active=True)
        insert("activity_codes", activity_code_id=30, proposal_id=4, code="1.a.4",
               description="Actividad mensual", is_active=True)
        insert("proposal_population_groups", population_group_id=3, proposal_id=4,
               code="children", label="Niños", sort_order=0, is_active=True)
        insert("proposal_report_programs", program_id=3, proposal_id=4,
               population_group_id=3, code="1A", name="Programa 1A", sort_order=0, is_active=True)
        insert("proposal_report_program_populations", program_population_id=3,
               program_id=3, population_group_id=3, sort_order=0, is_active=True)
        insert("proposal_report_program_population_activity_codes",
               program_population_id=3, activity_code_id=30)
        insert("activity_productivity_goals", productivity_goal_id=3, proposal_id=4,
               activity_code_id=30, goal_type="global_fixed", goal_value=12, is_active=True)

    def session(self, identifier, day, attended=True):
        self.fixture.insert("activity_sessions", session_id=identifier, proposal_id=4,
                            residential_id=1, activity_code_id=30, employee_id=1,
                            session_date=day, hours=1)
        self.fixture.insert("attendance", attendance_id=identifier, session_id=identifier,
                            participant_id=1, attended=attended)

    def context(self, month, year):
        return build_hoja_cotejo_admin_context(
            self.fixture.db, proposal_id=4, month=month, year=year,
            current_user=self.fixture.user,
        )

    def test_confirmed_first_attendance_and_monthly_or_explicit_period_goal(self):
        self.session(90, date(2026, 6, 1), attended=False)
        for i in range(18):
            self.session(100 + i, date(2026, 7 if i < 10 else 8, 20))
        self.session(200, date(2026, 9, 1))

        context = self.context(8, 2026)
        row = context["program_blocks"][0]["rows"][0]
        self.assertEqual(context["first_attendance_date"], date(2026, 7, 20))
        self.assertEqual(context["elapsed_months"], 2)
        self.assertEqual(row["activities_count"], 8)
        self.assertEqual(row["cumulative_ratio"], "18/24")
        self.assertEqual(row["percent"], 75)

        goals = self.fixture.tables["activity_productivity_goals"]
        self.fixture.db.execute(goals.update().where(goals.c.productivity_goal_id == 3)
                                .values(period_goal_value=36))
        self.fixture.db.expire_all()
        row = self.context(8, 2026)["program_blocks"][0]["rows"][0]
        self.assertEqual(row["cumulative_ratio"], "18/36")
        self.assertEqual(row["percent"], 50)

    def test_proposal_accumulation_does_not_reset_in_january(self):
        self.session(100, date(2026, 11, 30))
        self.session(101, date(2026, 12, 1))
        self.session(102, date(2027, 1, 31))
        context = self.context(1, 2027)
        row = context["program_blocks"][0]["rows"][0]
        self.assertEqual(context["elapsed_months"], 3)
        self.assertEqual(row["activities_count"], 1)
        self.assertEqual(row["cumulative_ratio"], "3/36")


if __name__ == "__main__":
    unittest.main()
