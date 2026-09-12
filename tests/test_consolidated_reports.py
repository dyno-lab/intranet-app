from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from sqlalchemy import Column, MetaData, Table, create_engine, event
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.api.routes import reports
from app.helpers.report_proposals import report_proposal_selection


class ConsolidatedReportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        event.listen(self.engine, "connect", lambda connection, _: connection.create_function(
            "datefromparts", 3, lambda year, month, day: date(year, month, day).isoformat()))
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.tables = {}
        # Real SELECTs and joins, with portable fixture tables (no server defaults).
        for model in vars(reports).values():
            table = getattr(model, "__table__", None)
            if table is not None and table.name not in self.tables:
                self.tables[table.name] = Table(table.name, metadata, *[
                    Column(c.name, c.type, primary_key=c.primary_key) for c in table.columns
                ])
        metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.insert("proposals", [{"proposal_id": i, "code": f"P{i}", "name": "Proposal"} for i in (1, 2, 3)])
        self.insert("participants", [{"participant_id": 1, "nombre": "Ana", "apellido_paterno": "Prueba",
                    "expediente_num": "E1", "fecha_nacimiento": date(2000, 1, 1), "genero": "F", "vca": "SI"}])
        self.insert("persons", [{"person_id": 1, "legacy_participant_id": 1}])
        self.insert("proposal_participants", [{"proposal_participant_id": i * 10, "proposal_id": i,
                    "person_id": 1, "nombre": "Ana", "apellido_paterno": "Prueba", "expediente_num": "E1",
                    "fecha_nacimiento": date(2000, 1, 1), "genero": "F", "vca": "SI"} for i in (1, 2, 3)])
        self.insert("activity_codes", [{"activity_code_id": 100, "code": "1.a.2", "description": "Actividad"}])
        self.insert("activity_sessions", [{"session_id": i, "proposal_id": 1 if i <= 2 else 2 if i <= 5 else 3,
                    "activity_code_id": 100, "session_date": date(2026, 7, i), "residential_id": 7, "hours": 1.0}
                    for i in range(1, 7)])
        self.insert("attendance", [{"attendance_id": i, "session_id": i, "participant_id": 1, "attended": True}
                    for i in range(1, 7)])
        for table, key in (("adm_service_types", "adm_service_type_id"), ("vca_columns", "vca_column_id")):
            self.insert(table, [{key: i * 10, "proposal_id": i, "name": "Servicio", "sort_order": 1, "is_active": True} for i in (1, 2, 3)])
        self.insert("adm_service_type_activity_codes", [{"id": i, "adm_service_type_id": i * 10, "activity_code_id": 100} for i in (1, 2, 3)])
        self.insert("vca_column_activity_codes", [{"id": i, "vca_column_id": i * 10, "activity_code_id": 100} for i in (1, 2, 3)])
        self.insert("proposal_report_programs", [{"program_id": i, "proposal_id": i, "code": "P", "name": "Programa",
                    "is_active": True, "sort_order": 1} for i in (1, 2, 3)])
        self.insert("proposal_report_program_activities", [
            {"program_activity_id": i, "program_id": i} for i in (1, 2, 3)])
        self.insert("proposal_report_program_activity_codes", [
            {"id": i, "program_activity_id": i, "activity_code_id": 100} for i in (1, 2, 3)])
        scope = {"selected_user": SimpleNamespace(residential_id=7), "is_global": True, "employee_id": 0}
        for name, value in {
            "_base_reports_context": {"proposals": [], "report_users": [], "year_options": [2026], "month_lookup": {7:"Julio"}, "user_residential_map": {}},
            "_resolve_reporting_scope": scope, "_resolve_reporting_location": {"residential_name":"Global", "municipality":"Todos", "rq_code":""},
            "_resolve_report_template_config": {}, "report_authorized_name": "Authorized",
            "_resolve_effective_program_activity_code_ids": {100},
        }.items():
            mock = patch.object(reports, name, return_value=value)
            mock.start()
            self.addCleanup(mock.stop)

    def insert(self, name, rows):
        with self.engine.begin() as connection:
            connection.execute(self.tables[name].insert(), rows)

    def context(self, builder, ids, **kwargs):
        return builder(self.db, SimpleNamespace(), ids, 7, 2026, 0,
                       period_type="custom", start_date="2026-07-01", end_date="2026-07-31", **kwargs)

    def test_program_large_catalog_keeps_sql_parameters_bounded(self):
        from sqlalchemy.dialects.mssql.pyodbc import MSDialect_pyodbc
        from app.services.report_programs import resolve_effective_program_activity_code_ids
        # Thousands of assignments, using the real legacy configuration resolver.
        self.insert("proposal_report_program_activity_codes", [
            {"id": proposal * 10000 + activity, "program_activity_id": proposal,
             "activity_code_id": activity}
            for proposal in (1, 2) for activity in range(1, 2501) if activity != 100])
        original = self.db.execute
        parameter_counts = []
        def execute(statement, *args, **kwargs):
            compiled = statement.compile(dialect=MSDialect_pyodbc(paramstyle="qmark"),
                                         compile_kwargs={"render_postcompile": True})
            parameter_counts.append(len(compiled.positiontup or []))
            return original(statement, *args, **kwargs)
        with patch.object(reports, "_resolve_effective_program_activity_code_ids",
                          side_effect=resolve_effective_program_activity_code_ids), \
             patch.object(self.db, "execute", side_effect=execute):
            for ids in (1, [1, 2]):
                context = self.context(reports._build_por_programa_context, ids)
                self.assertEqual(context["overall_total_all"], 1)
                self.assertEqual(context["program_sections"][0]["assigned_activity_count"], 2500)
        self.assertLess(max(parameter_counts), 50)

    def test_program_assignments_stay_with_their_proposal(self):
        # Activity 100 remains eligible in P1, but P2 now only assigns 200.
        self.db.execute(self.tables["proposal_report_program_activity_codes"].update()
                        .where(self.tables["proposal_report_program_activity_codes"].c.id == 2)
                        .values(activity_code_id=200))
        self.db.flush()
        self.insert("participants", [{"participant_id": 2, "nombre": "Otra", "genero": "M",
                    "fecha_nacimiento": date(2000, 1, 1)}])
        self.insert("attendance", [{"attendance_id": 20, "participant_id": 2,
                                   "session_id": 3, "attended": True}])
        context = self.context(reports._build_por_programa_context, [1, 2])
        self.assertEqual(context["overall_total_all"], 1)
        self.assertEqual(context["overall_total_m"], 0)

    def test_approved_example_one_unique_five_attendances(self):
        unique = self.context(reports._build_no_duplicado_context, [1, 2])
        duplicated = self.context(reports._build_no_duplicado_context, [1, 2], duplicated=True)
        self.assertEqual(unique["total_all"], 1)
        self.assertEqual(duplicated["total_all"], 5)
        self.assertEqual(len(self.context(reports._build_bonafide_context, [1, 2])["rows"]), 1)
        self.assertEqual(self.context(reports._build_no_duplicado_context, 1, duplicated=True)["total_all"], 2)
        self.assertEqual(self.context(reports._build_no_duplicado_context, 2, duplicated=True)["total_all"], 3)

    def test_adm_and_vca_merge_shared_configuration_once(self):
        adm = self.context(reports._build_adm_context, [1, 2])
        self.assertEqual(adm["rows"], [{"service_type_name":"Servicio", "services_count":5, "duplicados":5, "no_duplicados":1}])
        self.assertEqual(adm["sociodemographic_total"]["total"], 1)
        vca = self.context(reports._build_vca_context, [1, 2])
        self.assertEqual(len(vca["columns"]), 1)
        self.assertEqual(vca["total_people"], 1)
        self.assertEqual(list(vca["rows"][0]["column_values"].values()), [5])

    def test_program_totals_deduplicate_shared_person(self):
        context = self.context(reports._build_por_programa_context, [1, 2])
        self.assertEqual(len(context["program_sections"]), 1)
        self.assertEqual(context["overall_total_all"], 1)

    def test_hoja_cotejo_merges_activity_totals_by_id(self):
        structure = [{"program":SimpleNamespace(program_id=1), "population_blocks":[{
            "population_label":"Población", "rows":[{"activity_code_id":100, "activity_code":"1.a.2"}],
        }]}]
        with patch.object(reports, "_resolve_effective_program_population_blocks", return_value=structure):
            context = self.context(reports._build_hoja_cotejo_context, [1, 2])
        row = context["program_blocks"][0]["population_blocks"][0]["rows"][0]
        self.assertEqual((row["activities_count"], row["duplicados"], row["unique_participants"], row["contact_hours"]), (5, 5, 1, 5.0))

    def test_productivity_keeps_one_shared_goal_and_sums_execution(self):
        self.insert("activity_productivity_goals", [{"productivity_goal_id":i, "proposal_id":i,
                    "activity_code_id":100, "goal_type":"global_fixed", "goal_value":10,
                    "period_goal_value":20, "is_active":True} for i in (1, 2)])
        context = self.context(reports._build_productivity_context, [1, 2])
        self.assertEqual(len(context["summary_rows"]), 1)
        self.assertEqual(context["summary_rows"][0]["global_executed"], 5)

    def test_period_and_residential_filters_are_preserved(self):
        with patch.object(reports, "_resolve_reporting_scope", return_value={"selected_user":SimpleNamespace(residential_id=9), "is_global":False, "employee_id":-9}), patch.object(reports, "_residential_from_user", return_value="Otro"):
            context = self.context(reports._build_no_duplicado_context, [1, 2])
            self.assertEqual(context["total_all"], 0)
        context = reports._build_no_duplicado_context(self.db, SimpleNamespace(), [1, 2], 8, 2026, 0)
        self.assertEqual(context["total_all"], 0)

    def test_monthly_report_snapshots_count_person_once_across_proposals(self):
        for report_table, item_table in (
            ("school_dropout_reports", "school_dropout_report_items"),
            ("pregnancy_reports", "pregnancy_report_items"),
            ("school_grade_reports", "school_grade_report_items"),
        ):
            self.insert(report_table, [{"report_id":i, "proposal_id":i, "report_month":7,
                                       "report_year":2026, "residential_id":7} for i in (1, 2)])
            extra = {"grade_level":"10", "average_grade":90} if item_table == "school_grade_report_items" else {}
            self.insert(item_table, [{"report_item_id":i, "report_id":i, "participant_id":1, **extra} for i in (1, 2)])
        self.db.execute(self.tables["proposal_participants"].update().values(fecha_nacimiento=date(2012, 1, 1)))
        self.assertEqual(self.context(reports._build_school_dropout_summary_context, [1, 2])["total"]["recruited"], 1)
        self.assertEqual(self.context(reports._build_pregnancy_summary_context, [1, 2])["total"]["recruited"], 1)
        self.assertEqual(self.context(reports._build_notes_context, [1, 2])["total_row"]["TOTAL"], 1)

    def test_different_people_with_same_name_remain_distinct(self):
        self.insert("participants", [{"participant_id":2, "nombre":"Ana", "apellido_paterno":"Prueba",
                    "expediente_num":"E2", "fecha_nacimiento":date(2000, 1, 1), "genero":"F"}])
        self.insert("attendance", [{"attendance_id":7, "session_id":3, "participant_id":2, "attended":True}])
        self.assertEqual(self.context(reports._build_no_duplicado_context, [1, 2])["total_all"], 2)
        self.assertEqual(self.context(reports._build_no_duplicado_context, [1, 2], duplicated=True)["total_all"], 6)


class MultiProposalRouteTests(unittest.TestCase):
    def test_notes_print_preserves_multiple_proposals_in_get_and_post(self):
        app = FastAPI()
        app.include_router(reports.router, prefix="/ui/reports")
        app.dependency_overrides[reports.get_db] = lambda: None
        app.dependency_overrides[reports.get_current_user] = lambda: SimpleNamespace()
        charts = {"general_chart_image":"", "residential_chart_image":"", "subject_chart_sections":[]}
        with TestClient(app) as client, patch.object(reports, "_build_notes_context", return_value={"subject_chart_cards":[]}) as build, patch.object(reports, "build_notes_pdf_chart_images", return_value=charts), patch.object(reports.templates, "TemplateResponse", return_value=reports.HTMLResponse("OK")):
            for method in ("GET", "POST"):
                with self.subTest(method=method):
                    data = {"proposal_id":["1", "2"], "month":"7", "year":"2026", "employee_id":"0"}
                    response = client.get("/ui/reports/notas/pdf", params=data) if method == "GET" else client.post("/ui/reports/notas/pdf", data=data)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(build.call_args.args[2], [1, 2])

    def test_repeated_query_parameters_reach_existing_preview_route(self):
        app = FastAPI()
        app.include_router(reports.router, prefix="/ui/reports")
        app.dependency_overrides[reports.get_db] = lambda: None
        app.dependency_overrides[reports.get_current_user] = lambda: SimpleNamespace()
        with patch.object(reports, "_build_bonafide_context", return_value={}) as build, patch.object(reports.templates, "TemplateResponse", return_value=reports.HTMLResponse("OK")):
            response = TestClient(app).get("/ui/reports/bonafide?proposal_id=1&proposal_id=2&month=7&year=2026&employee_id=0")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(build.call_args.args[2], [1, 2])

    def test_run_redirect_preserves_multiple_proposals(self):
        request = SimpleNamespace(query_params=SimpleNamespace(getlist=lambda key: ["2", "1", "2"]))
        with patch.object(reports, "report_authorized_name", return_value="Name"):
            response = reports.reports_run("bonafide", proposal_id=2, month="7", year="2026", employee_id=0, request=request)
        self.assertIn("proposal_id=1&proposal_id=2", response.headers["location"])
        self.assertIn("employee_id=0", response.headers["location"])
