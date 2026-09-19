from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import Column, MetaData, Table, create_engine, event
from sqlalchemy.orm import Session

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import reports  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.participant import Participant  # noqa: E402
from app.services.full_monthly_report_data import build_full_monthly_report_data  # noqa: E402


class FullMonthlyReportDataTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def sql_server_dates(connection, _record):
            # Existing admin checklist uses SQL Server's MONTH/YEAR functions.
            connection.create_function("month", 1, lambda value: int(value[5:7]))
            connection.create_function("year", 1, lambda value: int(value[:4]))

        metadata = MetaData()
        self.tables = {
            source.name: Table(source.name, metadata, *[
                Column(column.name, column.type, primary_key=column.primary_key)
                for column in source.columns
            ])
            for source in Base.metadata.tables.values()
        }
        metadata.create_all(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.user = SimpleNamespace(role="admin", username="admin", residential_id=None)
        for identifier in (1, 2, 3):
            self.insert("proposals", proposal_id=identifier, code=str(identifier),
                        name=f"Propuesta {identifier}", is_active=True, status="active")
        for identifier in (1, 2):
            self.insert("residentials", residential_id=identifier, code=f"R{identifier}",
                        name=f"Residencial {identifier}", municipality="Ponce", is_active=True)
        for identifier, gender in ((1, "F"), (2, "M"), (3, "F")):
            self.insert("participants", participant_id=identifier, residential_id=1,
                        nombre=f"Participante {identifier}", apellido_paterno="Prueba",
                        expediente_num=f"TEST-{identifier}", genero=gender,
                        fecha_nacimiento=date(2000, 1, 1), is_active=True)
        self.insert("employees", employee_id=1, employee_code="EMP", full_name="Empleado", is_active=True)
        self.insert("activity_codes", activity_code_id=10, proposal_id=1,
                    code="1.a.2", description="Actividad compartida", is_active=True)
        self.insert("proposal_activity_codes", proposal_activity_code_id=1,
                    proposal_id=2, activity_code_id=10, is_active=True)
        for identifier in (1, 2):
            self.insert("proposal_population_groups", population_group_id=identifier,
                        proposal_id=identifier, code="adult", label="Adultos", sort_order=0, is_active=True)
            self.insert("proposal_report_programs", program_id=identifier, proposal_id=identifier,
                        population_group_id=identifier, code="P1", name="Programa 1",
                        formal_name="Programa formal", sort_order=0, is_active=True)
            self.insert("proposal_report_program_populations", program_population_id=identifier,
                        program_id=identifier, population_group_id=identifier, sort_order=0, is_active=True)
            self.insert("proposal_report_program_population_activity_codes",
                        program_population_id=identifier, activity_code_id=10)
            self.insert("visit_activity_mappings", mapping_id=identifier,
                        proposal_id=identifier, activity_code_id=10, is_active=True)
        sessions = (
            (1, 1, 1, date(2026, 7, 1), 2.0),
            (2, 2, 2, date(2026, 7, 31), 3.0),
            (3, 3, 1, date(2026, 7, 15), 999.0),
            (4, 1, 1, date(2026, 6, 30), 100.0),
            (5, 2, 2, date(2026, 7, 15), 0.5),
        )
        for identifier, proposal_id, residential_id, day, hours in sessions:
            self.insert("activity_sessions", session_id=identifier, proposal_id=proposal_id,
                        residential_id=residential_id, activity_code_id=10, employee_id=1,
                        session_date=day, hours=hours)
        for identifier, session_id, participant_id, attended in (
            (1, 1, 1, True), (2, 1, 2, True), (3, 2, 1, True),
            (4, 3, 3, True), (5, 4, 3, True), (6, 5, 3, False),
        ):
            self.insert("attendance", attendance_id=identifier, session_id=session_id,
                        participant_id=participant_id, attended=attended)
        for identifier in (1, 2):
            for table in ("pregnancy_reports", "school_dropout_reports", "visit_reports"):
                self.insert(table, report_id=identifier, proposal_id=identifier,
                            residential_id=identifier, report_month=7, report_year=2026)
            self.insert("pregnancy_report_items", report_item_id=identifier, report_id=identifier,
                        participant_id=1, participated_workshops=identifier == 2, is_pregnant=False)
            self.insert("school_dropout_report_items", report_item_id=identifier, report_id=identifier,
                        participant_id=1, attended_tutoring=identifier == 1,
                        attended_school=identifier == 2, current_grade="10")
        self.insert("visit_report_referrals", referral_id=1, report_id=1,
                    referral_type="Externo", agency="Agencia", sort_order=0)
        self.db.commit()

    def insert(self, table, **values):
        self.db.execute(self.tables[table].insert().values(**values))

    def build(self, **overrides):
        arguments = dict(db=self.db, current_user=self.user,
                         proposal_ids=[2, 1, 2], month=7, year=2026,
                         authorized_name="  Autorizado  ")
        arguments.update(overrides)
        return build_full_monthly_report_data(**arguments)

    def test_reuses_current_global_metrics_and_keeps_residential_totals_separate(self):
        data = self.build()

        self.assertEqual(data["period_label"], "Julio 2026")
        self.assertEqual([proposal.proposal_id for proposal in data["proposals"]], [1, 2])
        self.assertEqual(data["no_duplicado"]["total_all"], 2)
        self.assertEqual(data["duplicado"]["total_all"], 3)
        self.assertEqual(sum(row["no_duplicado"]["total_all"] for row in data["residentials"]), 3)
        self.assertEqual(data["por_programa"]["overall_total_all"], 2)
        self.assertEqual(len(data["por_programa"]["program_sections"]), 1)
        self.assertEqual(data["total_contact_hours"], 5.5)
        self.assertEqual(data["program_hours"][0]["contact_hours"], 5.5)
        self.assertEqual([row["hoja_cotejo"]["total_contact_hours"] for row in data["residentials"]], [2.0, 3.5])
        self.assertEqual([len(row["bonafide"]["rows"]) for row in data["residentials"]], [2, 1])
        self.assertEqual(data["embarazo"]["total"]["recruited"], 1)
        self.assertEqual(data["embarazo"]["total"]["participation"], 1)
        self.assertEqual(data["desercion"]["total"]["recruited"], 1)
        self.assertEqual(data["desercion"]["total"]["school"], 1)
        self.assertEqual(data["desercion"]["total"]["tutoring"], 1)
        self.assertEqual(data["visitas"]["referral_count"], 1)
        self.assertEqual([context["selected_proposal_id"] for context in data["hoja_cotejo_admin"]], [1, 2])
        expected = reports._build_no_duplicado_context(self.db, self.user, [1, 2], 7, 2026, 0, "  Autorizado  ")
        self.assertEqual(data["no_duplicado"], expected)

    def test_global_report_does_not_change_navigation_scope(self):
        self.user._active_residential_id = 1

        data = self.build()

        self.assertEqual(data["duplicado"]["total_all"], 3)
        self.assertTrue(data["no_duplicado"]["is_global"])
        self.assertEqual(len(data["residentials"]), 2)
        self.assertEqual(self.user._active_residential_id, 1)

    def test_rejects_non_admin_and_invalid_filters(self):
        for role in ("user", "supervisor", "viewer"):
            with self.subTest(role=role), self.assertRaises(HTTPException) as error:
                self.build(current_user=SimpleNamespace(role=role))
            self.assertEqual(error.exception.status_code, 403)
        for filters in ({"proposal_ids": []}, {"proposal_ids": [999]},
                        {"month": 13}, {"year": 0}):
            with self.subTest(filters=filters), self.assertRaises(HTTPException) as error:
                self.build(**filters)
            self.assertEqual(error.exception.status_code, 422)

    def test_inactive_and_unassigned_data_are_explicit_coverage_metadata(self):
        for identifier in (3, 4):
            self.insert("residentials", residential_id=identifier, code=f"R{identifier}",
                        name=f"Inactivo {identifier}", is_active=False)
        self.insert("activity_sessions", session_id=6, proposal_id=1, residential_id=3,
                    session_date=date(2026, 7, 2), activity_code_id=10, employee_id=1, hours=1)
        self.insert("activity_sessions", session_id=7, proposal_id=1, residential_id=4,
                    session_date=date(2026, 6, 2), activity_code_id=10, employee_id=1, hours=1)
        self.insert("pregnancy_reports", report_id=3, proposal_id=2, residential_id=None,
                    report_month=7, report_year=2026)

        data = self.build()

        self.assertEqual([row["residential_id"] for row in data["residentials"]], [1, 2])
        self.assertEqual([row["residential_id"] for row in data["coverage"]["inactive_residentials_with_data"]], [3])
        self.assertTrue(data["coverage"]["has_unassigned_data"])

    def test_assembly_executes_only_reads_even_with_pending_session_edits(self):
        participant = self.db.get(Participant, 1)
        participant.nombre = "Pending unrelated change"
        statements = []

        def record(_connection, _cursor, statement, _parameters, _context, _many):
            statements.append(statement)

        event.listen(self.engine, "before_cursor_execute", record)
        try:
            self.build()
        finally:
            event.remove(self.engine, "before_cursor_execute", record)

        self.assertTrue(statements)
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in statements))
        self.assertIn(participant, self.db.dirty)

    def test_empty_month_is_valid_and_has_zero_metrics(self):
        data = self.build(month=8)

        self.assertEqual(data["no_duplicado"]["total_all"], 0)
        self.assertEqual(data["duplicado"]["total_all"], 0)
        self.assertEqual(data["total_contact_hours"], 0)
        self.assertEqual(data["embarazo"]["total"]["recruited"], 0)
        self.assertEqual(data["desercion"]["total"]["recruited"], 0)
        self.assertEqual(data["visitas"]["referral_count"], 0)


if __name__ == "__main__":
    unittest.main()
