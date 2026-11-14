"""Exercise the adapters against real report queries, including consolidation."""
import json
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import Column, Table, event

from tests import test_consolidated_reports as fixtures
from app.api.routes import reports
from app.services import farogpt_report_operations as service
from app.services import activity_proposals, report_programs


class FaroGPTReportOperationsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ConsolidatedReportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        metadata = next(iter(self.fixture.tables.values())).metadata
        for module in (activity_proposals, report_programs):
            for model in vars(module).values():
                table = getattr(model, "__table__", None)
                if table is not None and table.name not in self.fixture.tables:
                    self.fixture.tables[table.name] = Table(table.name, metadata, *[
                        Column(c.name, c.type, primary_key=c.primary_key) for c in table.columns])
        metadata.create_all(self.fixture.engine)
        self.db = self.fixture.db
        self.user = SimpleNamespace(role="admin")

    def build(self, report, ids=None, residential_id=None, month=7):
        return service.build(report, self.db, self.user, ids or [1, 2], month, 2026, residential_id)

    @staticmethod
    def values(result):
        return {item["key"]: item["value"] for item in result["metrics"]}

    def test_one_person_five_attendances_across_two_proposals(self):
        unique = self.build("no_duplicado")
        duplicated = self.build("duplicado")
        self.assertEqual(self.values(unique), {"total": 1, "f": 1, "m": 0})
        self.assertEqual(self.values(duplicated), {"total": 5, "f": 5, "m": 0})
        self.assertEqual(self.values(self.build("duplicado", [2]))["total"], 3)
        self.assertEqual(unique["source_path"], "/ui/reports/no-duplicado")
        self.assertEqual(duplicated["source_path"], "/ui/reports/duplicado")

    def test_no_duplicado_preserves_report_exclusion_of_missing_age(self):
        self.fixture.insert("participants", [{"participant_id": 2, "nombre": "Secreto", "genero": "F"}])
        self.fixture.insert("attendance", [{"attendance_id": 20, "session_id": 1,
                                           "participant_id": 2, "attended": True}])
        result = self.build("duplicado")
        self.assertEqual(self.values(result)["total"], 5)
        self.assertIn("fecha de nacimiento", result["note"])

    def test_adm_consolidates_shared_service_and_preserves_unique_profiles(self):
        result = self.build("adm")
        values = self.values(result)
        self.assertEqual((values["services"], values["duplicates"], values["people"]), (5, 5, 1))
        self.assertEqual(result["tables"][0]["rows"], [["Servicio", 5, 5, 1]])
        self.assertEqual(result["source_path"], "/ui/reports/adm")
        self.assertEqual(result["primary"], "services")

    def test_vca_projects_summary_only_not_names_or_record_numbers(self):
        # Include the same person as a registered VCA in two proposals.
        self.db.execute(self.fixture.tables["proposal_participants"].update().values(is_active=True))
        self.db.flush()
        result = self.build("vca")
        values = self.values(result)
        self.assertEqual((values["registered"], values["served"]), (1, 1))
        self.assertEqual(result["tables"][1]["rows"], [["Servicio", 5]])
        serialized = json.dumps(result, ensure_ascii=False)
        for private in ("Ana", "Prueba", "E1", "participant_id", "expediente"):
            self.assertNotIn(private, serialized)

    def test_cotejo_does_not_double_count_codes_repeated_in_programs(self):
        structure = [{"program": SimpleNamespace(name=name), "program_display_name": name,
                      "population_blocks": [{"population_label": "Población", "rows": [
                          {"activity_code_id": 100, "activity_code": "1.a.2", "activity_description": "Actividad"}]}]}
                     for name in ("Programa A", "Programa B")]
        with patch.object(reports, "_resolve_effective_program_population_blocks", return_value=structure):
            result = self.build("cotejo")
        self.assertEqual(self.values(result), {"activities": 5, "duplicates": 5, "hours": 5.0})
        self.assertEqual(len(result["tables"][0]["rows"]), 2)

    def test_programs_consolidate_shared_person_and_expose_age_table(self):
        result = self.build("programs")
        self.assertEqual(self.values(result), {"total": 1, "f": 1, "m": 0})
        self.assertEqual(len(result["tables"][0]["rows"]), 1)
        self.assertEqual(result["source_path"], "/ui/reports/por-programa")

    def add_productivity_goals(self, second_goal=10):
        self.fixture.insert("activity_productivity_goals", [
            {"productivity_goal_id": i, "proposal_id": i, "activity_code_id": 100,
             "goal_type": "global_fixed", "goal_value": 10 if i == 1 else second_goal,
             "period_goal_value": 20, "is_active": True} for i in (1, 2)])

    def test_productivity_distinguishes_month_from_all_proposal_accumulated(self):
        self.add_productivity_goals()
        self.fixture.insert("activity_sessions", [{"session_id": 10, "proposal_id": 1,
            "activity_code_id": 100, "session_date": date(2026, 8, 1), "residential_id": 7, "hours": 1.0}])
        result = self.build("productivity")
        values = self.values(result)
        self.assertEqual((values["evaluated"], values["executed"], values["period_executed"], values["period_goal"]),
                         (1, 5, 6, 20))
        self.assertEqual(result["source_path"], "/ui/reports/productividad")
        self.assertIn("no se limitan", result["note"])

    def test_productivity_incompatible_goals_are_not_reported_as_zero(self):
        self.add_productivity_goals(second_goal=11)
        with self.assertRaises(HTTPException) as error:
            self.build("productivity")
        self.assertEqual(error.exception.status_code, 422)

    def test_residential_and_month_filters_apply_to_real_queries(self):
        scope = {"selected_user": SimpleNamespace(residential_id=9, name="Otro", username="Otro", residential=None),
                 "is_global": False, "employee_id": -9}
        with patch.object(reports, "_resolve_reporting_scope", return_value=scope):
            for report, key in (("no_duplicado", "total"), ("duplicado", "total"), ("adm", "services")):
                with self.subTest(report=report):
                    self.assertEqual(self.values(self.build(report, residential_id=9))[key], 0)
        self.assertEqual(self.values(self.build("duplicado", month=8))["total"], 0)

    def test_history_uses_service_residential_and_ignores_absences(self):
        self.db.execute(self.fixture.tables["participants"].update().values(residential_id=9))
        self.db.execute(self.fixture.tables["proposal_participants"].update().values(residential_id=9))
        self.db.flush()
        self.fixture.insert("attendance", [{"attendance_id": 20, "session_id": 1,
                                           "participant_id": 1, "attended": False}])
        scope = {"selected_user": SimpleNamespace(residential_id=7, username="Anterior", residential=None),
                 "is_global": False, "employee_id": -7}
        with patch.object(reports, "_resolve_reporting_scope", return_value=scope):
            result = self.build("duplicado", residential_id=7)
        self.assertEqual(self.values(result)["total"], 5)

    def test_active_scope_cannot_silently_answer_as_global_or_another_residential(self):
        scope = {"selected_user": SimpleNamespace(residential_id=7), "is_global": False, "employee_id": -7}
        with patch.object(reports, "_resolve_reporting_scope", return_value=scope):
            for rid in (None, 8):
                with self.subTest(residential=rid), self.assertRaises(HTTPException) as error:
                    self.build("adm", residential_id=rid)
                self.assertEqual(error.exception.status_code, 403)

    def test_contract_is_json_serializable_and_queries_do_not_write(self):
        statements = []
        def capture(connection, cursor, statement, parameters, context, many):
            statements.append(statement.lstrip().split()[0].upper())
        event.listen(self.fixture.engine, "before_cursor_execute", capture)
        self.addCleanup(lambda: event.remove(self.fixture.engine, "before_cursor_execute", capture))
        for report in service.REPORTS:
            with self.subTest(report=report):
                result = self.build(report)
                json.dumps(result)
                self.assertIsInstance(result["title"], str)
                self.assertIn(result["primary"], self.values(result))
                for metric in result["metrics"]:
                    self.assertIsInstance(metric["value"], (int, float))
                    self.assertTrue(metric["definition"])
                for table in result["tables"]:
                    for row in table["rows"]:
                        self.assertEqual(len(row), len(table["columns"]))
                        self.assertTrue(all(cell is None or isinstance(cell, (str, int, float)) for cell in row))
        self.assertTrue(statements)
        self.assertFalse({"INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "DROP"}.intersection(statements))

    def test_invalid_report_or_empty_selection_cannot_look_like_zero_results(self):
        for report, ids in (("unknown", [1]), ("adm", [])):
            with self.subTest(report=report), self.assertRaises(HTTPException) as error:
                service.build(report, self.db, self.user, ids, 7, 2026, None)
            self.assertEqual(error.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
