from __future__ import annotations

import os
import unittest

from sqlalchemy import Boolean, Column, Integer, MetaData, Table, create_engine, event
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.services.visits import (  # noqa: E402
    build_visit_attendance_map,
    calculate_visits_rows_and_summary,
)


class VisitAttendanceParameterLimitTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        self.addCleanup(self.engine.dispose)
        self.attendance = Table(
            "attendance", MetaData(),
            Column("attendance_id", Integer, primary_key=True),
            Column("session_id", Integer),
            Column("attended", Boolean),
        )
        self.attendance.create(self.engine)
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)
        self.parameter_counts = []

        def enforce_sql_server_limit(state):
            compiled = state.statement.compile(
                dialect=mssql.dialect(), compile_kwargs={"render_postcompile": True},
            )
            self.parameter_counts.append(len(compiled.params))
            self.assertLessEqual(len(compiled.params), 2100)

        event.listen(self.db, "do_orm_execute", enforce_sql_server_limit)

    def test_large_selection_preserves_counts_and_report_summary(self):
        count = 4501
        with self.engine.begin() as connection:
            connection.execute(self.attendance.insert(), [
                {"session_id": i, "attended": True} for i in range(1, count + 1)
            ] + [
                {"session_id": 1, "attended": True},
                {"session_id": 1, "attended": False},
                {"session_id": 99999, "attended": True},
            ])

        attendance_map = build_visit_attendance_map(
            self.db, list(range(1, count + 1)) + [1],
        )
        self.assertEqual(attendance_map, {i: 2 if i == 1 else 1 for i in range(1, count + 1)})
        self.assertGreater(len(self.parameter_counts), 1)
        session_rows = [(i, 7, "Employee", 0.5, 9, "Residential") for i in range(1, count + 1)]
        for is_global in (True, False):
            with self.subTest(is_global=is_global):
                rows, summary = calculate_visits_rows_and_summary(
                    session_rows, attendance_map, is_global=is_global,
                )
                self.assertEqual(summary, {"visits": count, "attendances": count + 1, "hours": 2250.5})
                self.assertEqual(rows, [{
                    "employee_id": 7, "employee_name": "Employee",
                    "residential_name": "Residential" if is_global else "",
                    "visits": count, "attendances": count + 1, "hours": 2250.5,
                }])

    def test_small_selection_preserves_absences_and_sessions_without_attendance(self):
        with self.engine.begin() as connection:
            connection.execute(self.attendance.insert(), [
                {"session_id": 1, "attended": True},
                {"session_id": 1, "attended": True},
                {"session_id": 2, "attended": False},
                {"session_id": 4, "attended": True},
            ])
        self.assertEqual(build_visit_attendance_map(self.db, [1, 2, 3]), {1: 2})
        self.assertEqual(len(self.parameter_counts), 1)

    def test_empty_selection_does_not_query(self):
        self.assertEqual(build_visit_attendance_map(self.db, []), {})
        self.assertEqual(self.parameter_counts, [])
