"""Contract and database-backed coverage for the aggregate-only report adapter."""
import json
import unittest
from datetime import date

from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.dialects import mssql

from tests import test_full_monthly_report_data as fixtures
from app.api.routes import reports
from app.models.participant import Participant
from app.services import farogpt_report_followups as adapter
from app.services.certification_report import build_certification_report
from app.services.participant_courses import build_course_report


class FaroGPTFollowupReportTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.FullMonthlyReportDataTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.db, self.user = self.source.db, self.source.user
        self.user.user_id = 1
        tables = self.source.tables
        self.db.execute(tables["participants"].update().values(fecha_nacimiento=date(2012, 1, 1)))
        self.db.execute(tables["proposal_report_programs"].update().values(code="1A"))
        self.db.execute(tables["activity_codes"].update().values(code="2.b.5"))
        self.db.execute(tables["pregnancy_report_items"].update().where(
            tables["pregnancy_report_items"].c.report_item_id == 1).values(is_pregnant=True))
        self.source.insert("pregnancy_report_items", report_item_id=3, report_id=1, participant_id=2,
                           participated_workshops=False, is_pregnant=False)
        self.source.insert("school_dropout_report_items", report_item_id=3, report_id=1, participant_id=2,
                           attended_tutoring=False, attended_school=False, current_grade="8")
        for identifier, proposal, residential, month in ((1, 1, 1, 7), (2, 2, 2, 7), (3, 3, 1, 7), (4, 1, 1, 8)):
            self.source.insert("school_grade_reports", report_id=identifier, proposal_id=proposal,
                               residential_id=residential, report_month=month, report_year=2026)
        for identifier, report, participant, average, math in (
            (1, 1, 1, 95, 95), (2, 1, 2, 80, 60), (3, 2, 1, 70, 85),
            (4, 3, 3, 95, 95), (5, 4, 3, 95, 95),
        ):
            self.source.insert("school_grade_report_items", report_item_id=identifier, report_id=report,
                               participant_id=participant, average_grade=average, math_grade=math,
                               spanish_grade=90, english_grade=80, science_grade=70, grade_level="8",
                               is_content_room=False)
        self.source.insert("participant_monthly_courses", participant_id=1, report_year=2026,
                           report_month=7, course_code="reposteria", revision=1)
        self.source.insert("visit_report_referrals", referral_id=2, report_id=2, referral_type="Interno",
                           agency="PRIVATE-AGENCY", reference_or_purpose="PRIVATE-REFERRAL", sort_order=0)
        self.source.insert("visit_report_referrals", referral_id=3, report_id=2, referral_type="Visita Agencia",
                           agency="PRIVATE-AGENCY", reference_or_purpose="PRIVATE-REFERRAL", sort_order=1)
        self.db.commit()

    def build(self, report, **kwargs):
        args = dict(report=report, db=self.db, user=self.user, proposal_ids=[1, 2], month=7, year=2026,
                    residential_id=None)
        args.update(kwargs)
        return adapter.build(**args)

    def values(self, report, **kwargs):
        return {m["key"]: m["value"] for m in self.build(report, **kwargs)["metrics"]}

    def test_notes_deduplicate_selected_proposals_and_use_reported_grade_distributions(self):
        values = self.values("notes")
        self.assertEqual((values["total"], values["A"], values["B"], values["C"]), (2, 0, 1, 1))
        self.assertEqual((values["math_b"], values["math_d"], values["math_total"]), (1, 1, 2))
        self.assertEqual(self.values("notes", residential_id=1)["A"], 1)
        self.assertEqual(self.values("notes", residential_id=2)["total"], 1)
        self.assertEqual(self.values("notes", proposal_ids=[2])["total"], 1)
        self.assertEqual(self.values("notes", month=8)["total"], 1)

    def test_pregnancy_distinguishes_cases_from_followup_and_workshop_population(self):
        values = self.values("pregnancy")
        self.assertEqual((values["pregnancy_cases"], values["recruited"], values["participation"]), (1, 2, 1))
        self.assertEqual((values["pregnant_f"], values["pregnant_m"], values["non_pregnant"], values["prevention_pct"]), (1, 0, 0, 0))
        self.assertEqual(self.build("pregnancy")["primary"], "pregnancy_cases")
        self.assertEqual(self.values("pregnancy", residential_id=2)["pregnancy_cases"], 0)
        self.assertEqual(self.values("pregnancy", residential_id=1)["pregnancy_cases"], 1)
        self.assertIn("no es el total", self.build("pregnancy")["metrics"][0]["definition"])

    def test_school_followup_preserves_union_of_flags_without_calling_recruits_dropouts(self):
        values = self.values("dropout")
        self.assertEqual((values["recruited"], values["tutoring"], values["school"]), (2, 1, 1))
        self.assertEqual((values["tutoring_pct"], values["school_pct"]), (50, 50))
        self.assertEqual((values["grade_8"], values["grade_10"]), (1, 1))
        self.assertEqual(self.values("dropout", residential_id=2)["tutoring"], 0)
        self.assertIn("no es un conteo de desertores", self.build("dropout")["metrics"][0]["definition"])

    def test_visits_keep_session_hours_confirmed_attendance_and_referral_rows_separate(self):
        values = self.values("visits")
        self.assertEqual((values["visits"], values["attendances"], values["hours"]), (3, 3, 5.5))
        self.assertEqual((values["referrals"], values["referrals_internal"], values["referrals_external"], values["referrals_agency"]), (3, 1, 1, 1))
        self.assertEqual(self.values("visits", residential_id=1)["referrals"], 1)
        self.assertEqual(self.values("visits", residential_id=2)["referrals"], 2)
        self.assertEqual(self.values("visits", proposal_ids=[1])["visits"], 1)

    def test_courses_count_unique_people_and_monthly_selections(self):
        values = self.values("courses")
        self.assertEqual((values["total"], values["pending"], values["reposteria"], values["charcuteria"]), (2, 1, 1, 0))
        self.assertEqual((self.values("courses", residential_id=2)["total"], self.values("courses", residential_id=2)["pending"]), (1, 0))
        self.assertEqual(self.values("courses", month=8)["total"], 0)

    def test_bonafide_and_certification_reuse_existing_counts_without_individual_rows(self):
        self.assertEqual(self.values("bonafide"), {"total": 2, "f": 1, "m": 1})
        values = self.values("certification")
        self.assertEqual((values["people"], values["total"], values["1A"], values["unclassified"]), (2, 3, 3, 0))
        self.assertEqual((self.values("certification", residential_id=1)["total"], self.values("certification", residential_id=2)["total"]), (2, 1))
        self.assertEqual(self.values("bonafide", residential_id=2)["total"], 1)

    def test_values_match_real_builders_for_global_residential_and_single_proposal(self):
        for selected, residential in (([1, 2], None), ([1, 2], 1), ([1, 2], 2), ([1], None)):
            employee_id = 0 if residential is None else -residential
            args = (self.db, self.user, selected, 7, 2026, employee_id)
            with self.subTest(selected=selected, residential=residential):
                sources = {
                    "notes": reports._build_notes_context(*args)["total_row"]["TOTAL"],
                    "pregnancy": reports._build_pregnancy_summary_context(*args)["total"]["pregnancy_cases"],
                    "dropout": reports._build_school_dropout_summary_context(*args)["total"]["recruited"],
                    "visits": reports._build_visits_context(*args)["summary"]["visits"],
                    "bonafide": len(reports._build_bonafide_context(*args)["rows"]),
                    "courses": build_course_report(self.db, self.user, proposal_ids=selected, month=7, year=2026, employee_id=employee_id)["total"],
                    "certification": build_certification_report(self.db, self.user, selected_proposals=selected, month=7, year=2026, employee_id=employee_id)["people_count"],
                }
                for report, expected in sources.items():
                    output = self.build(report, proposal_ids=selected, residential_id=residential)
                    values = {m["key"]: m["value"] for m in output["metrics"]}
                    self.assertEqual(values[output["primary"]], expected)

    def test_all_reports_are_aggregate_only_read_only_and_compile_for_sql_server(self):
        statements = []
        def capture(_connection, statement, _multiparams, _params, _options):
            statements.append(str(statement.compile(dialect=mssql.dialect())))
        # An unrelated dirty model must not be autoflushed by report reads.
        participant = self.db.get(Participant, 1)
        participant.nombre = "PRIVATE-DIRTY-NAME"
        event.listen(self.source.engine, "before_execute", capture)
        try:
            for report in sorted(adapter.REPORTS):
                with self.subTest(report=report):
                    output = self.build(report)
                    self.assertIn(output["primary"], {m["key"] for m in output["metrics"]})
                    self.assertTrue(output["source_path"].startswith("/ui/reports/"))
                    self.assertTrue(all(isinstance(m["value"], (int, float)) for m in output["metrics"]))
                    for table in output["tables"]:
                        self.assertTrue(all(len(row) == len(table["columns"]) for row in table["rows"]))
                    serialized = json.dumps(output)
                    for private in ("PRIVATE-", "Participante 1", "TEST-1", "Empleado", "participant_id", "employee_id", "expediente_num", "reference_or_purpose"):
                        self.assertNotIn(private, serialized)
        finally:
            event.remove(self.source.engine, "before_execute", capture)
        self.assertTrue(statements)
        self.assertTrue(all(sql.lstrip().upper().startswith("SELECT") for sql in statements))
        self.assertIn(participant, self.db.dirty)

    def test_active_residential_scope_cannot_be_overridden_by_global_or_other_residential(self):
        self.user.role = "supervisor"
        self.user._active_residential_id = 2
        for report in sorted(adapter.REPORTS):
            with self.subTest(report=report):
                self.assertEqual(self.values(report), self.values(report, residential_id=1))
        self.assertEqual(self.values("certification")["people"], 1)
        self.assertEqual(self.values("pregnancy")["pregnancy_cases"], 0)

    def test_empty_month_has_zero_metrics_in_every_report(self):
        for report in sorted(adapter.REPORTS):
            with self.subTest(report=report):
                self.assertTrue(all(value == 0 for value in self.values(report, month=9).values()))

    def test_permissions_and_invalid_input_fail_instead_of_showing_fake_zeros(self):
        for role in ("user", "viewer", "unknown"):
            self.user.role = role
            with self.assertRaises(HTTPException) as error:
                self.build("pregnancy")
            self.assertEqual(error.exception.status_code, 403)
        self.user.role = "admin"
        for arguments in ({"month": 0}, {"month": "7"}, {"year": 9999}, {"proposal_ids": []},
                          {"proposal_ids": [True]}, {"residential_id": -1}, {"report": "unknown"}):
            with self.subTest(arguments=arguments), self.assertRaises(HTTPException) as error:
                self.build(**{"report": "notes", **arguments})
            self.assertEqual(error.exception.status_code, 422)
        with self.assertRaises(HTTPException) as error:
            self.build("notes", residential_id=99999)
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
