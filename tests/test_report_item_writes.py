from __future__ import annotations

import unittest

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.models.school_dropout_report_item import SchoolDropoutReportItem
from app.services.report_item_writes import delete_report_item, update_report_item_fields


class ReportItemWriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")

        def register_sql_server_functions(dbapi_connection, connection_record) -> None:
            dbapi_connection.create_function(
                "sysutcdatetime",
                0,
                lambda: "2026-09-01 00:00:00",
            )

        event.listen(self.engine, "connect", register_sql_server_functions)
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE school_dropout_report_items (
                    report_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_id INTEGER NOT NULL,
                    participant_id INTEGER NOT NULL,
                    attended_tutoring BOOLEAN DEFAULT 0 NOT NULL,
                    current_grade VARCHAR(20),
                    attended_school BOOLEAN DEFAULT 0 NOT NULL,
                    report_10_weeks BOOLEAN DEFAULT 0 NOT NULL,
                    report_20_weeks BOOLEAN DEFAULT 0 NOT NULL,
                    report_30_weeks BOOLEAN DEFAULT 0 NOT NULL,
                    report_40_weeks BOOLEAN DEFAULT 0 NOT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """))
            connection.execute(text("""
                INSERT INTO school_dropout_report_items (
                    report_item_id,
                    report_id,
                    participant_id
                ) VALUES (7, 3, 11)
            """))

        self.executed_statements: list[str] = []

        def capture_statement(
            connection,
            cursor,
            statement,
            parameters,
            context,
            executemany,
        ) -> None:
            self.executed_statements.append(statement)

        self.capture_statement = capture_statement
        event.listen(self.engine, "before_cursor_execute", self.capture_statement)

    def tearDown(self) -> None:
        event.remove(
            self.engine,
            "before_cursor_execute",
            self.capture_statement,
        )
        self.engine.dispose()

    def test_updates_existing_dropout_item_without_a_second_orm_update(self):
        with Session(self.engine) as db:
            item = db.get(SchoolDropoutReportItem, 7)
            self.assertIsNotNone(item)

            update_report_item_fields(
                db,
                SchoolDropoutReportItem,
                7,
                {
                    "attended_tutoring": True,
                    "current_grade": "10",
                    "attended_school": True,
                    "report_10_weeks": True,
                    "report_20_weeks": False,
                    "report_30_weeks": False,
                    "report_40_weeks": False,
                },
            )
            db.commit()
            db.refresh(item)

            self.assertTrue(item.attended_tutoring)
            self.assertEqual(item.current_grade, "10")
            self.assertTrue(item.attended_school)

        update_statements = [
            statement
            for statement in self.executed_statements
            if statement.lstrip().upper().startswith("UPDATE")
        ]
        self.assertEqual(len(update_statements), 1)

    def test_deletes_existing_dropout_item_with_core_delete(self):
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(SchoolDropoutReportItem, 7))
            delete_report_item(db, SchoolDropoutReportItem, 7)
            db.commit()

        with Session(self.engine) as verification_db:
            self.assertIsNone(verification_db.get(SchoolDropoutReportItem, 7))

        delete_statements = [
            statement
            for statement in self.executed_statements
            if statement.lstrip().upper().startswith("DELETE")
        ]
        self.assertEqual(len(delete_statements), 1)


if __name__ == "__main__":
    unittest.main()
