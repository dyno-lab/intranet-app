from __future__ import annotations

import unittest
from datetime import date

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.models.activity_code import ActivityCode  # noqa: F401
from app.models.activity_session import ActivitySession
from app.models.employee import Employee  # noqa: F401
from app.models.proposal import Proposal  # noqa: F401
from app.models.residential import Residential  # noqa: F401
from app.services.session_control_numbers import persist_session_control_number, update_session_fields


class _Database:
    def __init__(self) -> None:
        self.statements: list[object] = []

    def execute(self, statement: object) -> None:
        self.statements.append(statement)


class SessionControlNumberTests(unittest.TestCase):
    def test_persists_jardines_control_number_with_core_update(self):
        db = _Database()
        activity_session = ActivitySession(
            session_date=date(2026, 8, 24),
            activity_code_id=1,
            employee_id=2,
            proposal_id=5,
            residential_id=3,
            created_by_user_id=7,
        )
        activity_session.session_id = 42

        control_number = persist_session_control_number(
            db,
            activity_session,
            "JDG",
        )

        self.assertEqual(control_number, "JDG422026")
        self.assertIsNone(activity_session.control_number)
        self.assertEqual(len(db.statements), 1)
        statement = db.statements[0]
        self.assertIn("UPDATE activity_sessions", str(statement))
        self.assertIn(42, statement.compile().params.values())
        self.assertIn("JDG422026", statement.compile().params.values())

    def test_commit_does_not_emit_a_second_orm_update(self):
        engine = create_engine("sqlite+pysqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE activity_sessions (
                    session_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    control_number VARCHAR(64),
                    residential_id INTEGER,
                    created_by_user_id INTEGER,
                    session_date DATE NOT NULL,
                    activity_code_id INTEGER NOT NULL,
                    employee_id INTEGER NOT NULL,
                    proposal_id INTEGER,
                    hours FLOAT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))

        executed_statements: list[str] = []

        def capture_statement(
            connection,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ) -> None:
            executed_statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture_statement)
        try:
            with Session(engine) as db:
                activity_session = ActivitySession(
                    session_date=date(2026, 8, 24),
                    activity_code_id=1,
                    employee_id=2,
                    proposal_id=5,
                    residential_id=3,
                    created_by_user_id=7,
                )
                activity_session.session_id = 42
                db.add(activity_session)
                db.flush()

                persist_session_control_number(db, activity_session, "JDG")
                db.commit()
                db.refresh(activity_session)

                self.assertEqual(activity_session.control_number, "JDG422026")

                executed_statements.clear()
                update_session_fields(
                    db,
                    activity_session,
                    "JDG",
                    session_date=date(2026, 8, 25),
                    activity_code_id=9,
                    employee_id=8,
                    proposal_id=6,
                    hours=1.5,
                )
                db.commit()
                db.refresh(activity_session)

                self.assertEqual(activity_session.control_number, "JDG422026")
                self.assertEqual(activity_session.session_date, date(2026, 8, 25))
                self.assertEqual(activity_session.activity_code_id, 9)
                self.assertEqual(activity_session.employee_id, 8)
                self.assertEqual(activity_session.proposal_id, 6)
                self.assertEqual(activity_session.hours, 1.5)

            update_statements = [
                statement
                for statement in executed_statements
                if statement.lstrip().upper().startswith("UPDATE")
            ]
            self.assertEqual(len(update_statements), 1)
        finally:
            event.remove(engine, "before_cursor_execute", capture_statement)
            engine.dispose()

    def test_requires_a_flushed_session_id(self):
        db = _Database()
        activity_session = ActivitySession(
            session_date=date(2026, 8, 24),
            activity_code_id=1,
            employee_id=2,
        )

        with self.assertRaises(ValueError):
            persist_session_control_number(db, activity_session, "JDG")

        self.assertEqual(db.statements, [])


if __name__ == "__main__":
    unittest.main()
