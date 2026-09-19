from __future__ import annotations

import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import event

from tests import test_full_monthly_report_data as fixtures
from app.api.routes import reports
from app.models.participant import Participant
from app.services.full_monthly_report_supplemental_data import build_supplemental_data


def _dob(age):
    today = date.today()
    return date(today.year - age, today.month, min(today.day, 28))


class FullMonthlyReportSupplementalDataTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.FullMonthlyReportDataTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.db = self.fixture.db
        self.user = self.fixture.user
        self.residentials = [{"residential_id": 1}, {"residential_id": 2}]

    def build(self, **overrides):
        values = dict(db=self.db, current_user=self.user, proposal_ids=[2, 1, 2],
                      month=7, year=2026, residentials=self.residentials)
        values.update(overrides)
        return build_supplemental_data(**values)

    def add_participant(self, identifier, *, dob, gender="F"):
        self.fixture.insert("participants", participant_id=identifier, residential_id=1,
                            nombre=f"Participante {identifier}", apellido_paterno="Prueba",
                            expediente_num=f"TEST-{identifier}", genero=gender,
                            fecha_nacimiento=dob, is_active=True)

    def add_session(self, identifier, day, participant_id, *, proposal_id=1, attended=True, residential_id=1):
        self.fixture.insert("activity_sessions", session_id=identifier, proposal_id=proposal_id,
                            residential_id=residential_id, activity_code_id=10,
                            employee_id=1, session_date=day, hours=1)
        self.fixture.insert("attendance", attendance_id=identifier + 100, session_id=identifier,
                            participant_id=participant_id, attended=attended)

    def test_monthly_population_and_cumulative_counts_deduplicate_across_proposals(self):
        result = self.build()

        monthly = result["target_population_rows"]
        self.assertEqual(monthly[1]["adults"], {"f": 1, "m": 1, "total": 2})
        self.assertEqual(monthly[2]["adults"], {"f": 1, "m": 0, "total": 1})
        self.assertEqual(monthly["global"]["adults"], {"f": 1, "m": 1, "total": 2})
        cumulative = result["target_cumulative"]
        self.assertEqual(cumulative["by_residential"], {1: 3, 2: 1})
        self.assertEqual(cumulative["total_all"], 3)
        self.assertEqual(cumulative["proposal_starts"], {1: date(2026, 6, 30), 2: date(2026, 7, 31)})
        self.assertEqual(cumulative["start_date"], date(2026, 6, 30))
        self.assertEqual(cumulative["end_date"], date(2026, 7, 31))
        self.assertEqual(cumulative["period_label"], "30/06/2026 al 31/07/2026")
        existing = reports._build_no_duplicado_context(self.db, self.user, [1, 2], 7, 2026, 0,
                                                       period_type="custom", start_date=date(2026, 6, 30),
                                                       end_date=date(2026, 7, 31))
        self.assertEqual(cumulative["total_all"], existing["total_all"])

    def test_population_boundaries_follow_current_age_and_keep_missing_gender_in_total(self):
        for identifier, age in enumerate((12, 13, 18, 19, 59, 60), 10):
            self.add_participant(identifier, dob=_dob(age), gender="M" if identifier % 2 else "F")
            self.fixture.insert("attendance", attendance_id=identifier + 10, session_id=1,
                                participant_id=identifier, attended=True)
        for identifier, dob in ((20, None), (21, date.today() + timedelta(days=1))):
            self.add_participant(identifier, dob=dob)
            self.fixture.insert("attendance", attendance_id=identifier + 10, session_id=1,
                                participant_id=identifier, attended=True)
        self.add_participant(22, dob=_dob(12), gender=None)
        self.fixture.insert("attendance", attendance_id=32, session_id=1, participant_id=22, attended=True)

        counts = self.build()["target_population_rows"]["global"]

        self.assertEqual(counts["children"], {"f": 1, "m": 0, "total": 2})
        self.assertEqual(counts["youth"], {"f": 1, "m": 1, "total": 2})
        self.assertEqual(counts["adults"], {"f": 2, "m": 2, "total": 4})
        self.assertEqual(counts["older"], {"f": 0, "m": 1, "total": 1})

    def test_latest_selected_proposal_snapshot_controls_global_age_and_gender(self):
        self.fixture.insert("persons", person_id=10, legacy_participant_id=1, nombre="Persona")
        for identifier, proposal_id, age, gender in ((11, 1, 19, "F"), (12, 2, 12, "M")):
            self.fixture.insert("proposal_participants", proposal_participant_id=identifier,
                                proposal_id=proposal_id, person_id=10, nombre="Persona",
                                fecha_nacimiento=_dob(age), genero=gender, is_active=True)

        counts = self.build()["target_population_rows"]

        self.assertEqual(counts[1]["adults"]["total"], 2)
        self.assertEqual(counts[2]["children"], {"f": 0, "m": 1, "total": 1})
        self.assertEqual(counts["global"]["children"], {"f": 0, "m": 1, "total": 1})
        self.assertEqual(counts["global"]["adults"], {"f": 0, "m": 1, "total": 1})

    def test_future_and_unconfirmed_attendance_do_not_extend_the_period(self):
        self.add_participant(4, dob=_dob(10))
        self.add_session(6, date(2026, 6, 1), 4, attended=False)
        self.add_session(7, date(2026, 8, 1), 4)
        self.add_session(8, date(2026, 5, 1), 4, proposal_id=3)

        result = self.build()["target_cumulative"]

        self.assertEqual(result["start_date"], date(2026, 6, 30))
        self.assertEqual(result["total_all"], 3)

    def test_first_month_reuses_monthly_counts_without_cumulative_context_queries(self):
        with patch.object(reports, "_build_no_duplicado_context", wraps=reports._build_no_duplicado_context) as builder:
            result = self.build(proposal_ids=[2])

        self.assertEqual(result["target_cumulative"]["total_all"], 1)
        self.assertEqual(result["target_cumulative"]["by_residential"], {1: 0, 2: 1})
        builder.assert_not_called()

    def test_cumulative_uniques_are_not_the_sum_of_monthly_uniques(self):
        self.add_session(10, date(2026, 6, 10), 1)
        self.add_session(11, date(2026, 6, 11), 1)

        result = self.build()["target_cumulative"]

        # June has persons 1 and 3; July has persons 1 and 2. The union is 3.
        self.assertEqual(result["total_all"], 3)
        self.assertEqual(result["by_residential"], {1: 3, 2: 1})
        self.assertEqual(result["start_date"], date(2026, 6, 10))

    def test_single_proposal_global_unique_is_not_the_sum_of_residentials(self):
        self.add_session(10, date(2026, 7, 20), 1, proposal_id=2, residential_id=1)

        result = self.build(proposal_ids=[2])

        self.assertEqual(result["target_population_rows"]["global"]["adults"]["total"], 1)
        self.assertEqual(result["target_cumulative"]["by_residential"], {1: 1, 2: 1})
        self.assertEqual(result["target_cumulative"]["total_all"], 1)

    def test_empty_month_preserves_prior_unique_count_but_pre_start_month_is_zero(self):
        later = self.build(month=8)
        self.assertEqual(sum(row["total"] for row in later["target_population_rows"]["global"].values()), 0)
        self.assertEqual(later["target_cumulative"]["total_all"], 3)
        before = self.build(month=5)
        self.assertIsNone(before["target_cumulative"]["start_date"])
        self.assertEqual(before["target_cumulative"]["proposal_starts"], {1: None, 2: None})
        self.assertEqual(before["target_cumulative"]["total_all"], 0)
        self.assertEqual(before["target_cumulative"]["by_residential"], {1: 0, 2: 0})

    def test_cumulative_range_crosses_year_boundary_without_reset(self):
        self.add_participant(4, dob=_dob(10))
        self.add_participant(5, dob=_dob(13))
        self.add_session(6, date(2025, 11, 30), 4)
        self.add_session(7, date(2027, 2, 1), 5)

        result = self.build(month=1, year=2027)["target_cumulative"]

        self.assertEqual(result["start_date"], date(2025, 11, 30))
        self.assertEqual(result["end_date"], date(2027, 1, 31))
        self.assertEqual(result["total_all"], 4)

    def test_global_coverage_includes_unassigned_and_inactive_locations(self):
        self.fixture.insert("residentials", residential_id=3, code="R3", name="Inactivo", municipality="Ponce", is_active=False)
        for identifier, residential_id in ((4, 3), (5, None)):
            self.add_participant(identifier, dob=_dob(10))
            self.add_session(identifier + 10, date(2026, 7, 10), identifier, residential_id=residential_id)

        result = self.build()

        self.assertEqual(result["target_population_rows"]["global"]["children"]["total"], 2)
        self.assertNotIn(3, result["target_population_rows"])
        self.assertEqual(result["target_cumulative"]["total_all"], 5)
        self.assertEqual(result["target_cumulative"]["by_residential"], {1: 3, 2: 1})

    def test_admin_scope_stays_global_and_pending_changes_are_not_flushed(self):
        self.user._active_residential_id = 1
        participant = self.db.get(Participant, 1)
        participant.nombre = "Unrelated pending change"
        statements = []

        def record(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(self.fixture.engine, "before_cursor_execute", record)
        try:
            result = self.build()
        finally:
            event.remove(self.fixture.engine, "before_cursor_execute", record)

        self.assertTrue(statements)
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in statements))
        self.assertEqual(result["target_cumulative"]["by_residential"][2], 1)
        self.assertEqual(self.user._active_residential_id, 1)
        self.assertIn(participant, self.db.dirty)

    def test_rejects_non_admin_and_invalid_selection(self):
        for override in ({"current_user": SimpleNamespace(role="supervisor")},
                         {"proposal_ids": []}, {"proposal_ids": [999]}, {"month": 13}, {"year": 0}):
            with self.subTest(override=override), self.assertRaises(HTTPException) as error:
                self.build(**override)
            self.assertEqual(error.exception.status_code, 403 if "current_user" in override else 422)


if __name__ == "__main__":
    unittest.main()
