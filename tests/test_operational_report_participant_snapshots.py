from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import pregnancy, school_dropout, school_grades  # noqa: E402
from app.models.pregnancy_report import PregnancyReport  # noqa: E402
from app.models.proposal import Proposal  # noqa: E402
from app.models.school_dropout_report import SchoolDropoutReport  # noqa: E402
from app.models.school_grade_report import SchoolGradeReport  # noqa: E402


PROPOSAL_ID = 17
REPORT_ID = 41


class _Result:
    def __init__(self, values=None):
        self.values = list(values or [])

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Database:
    def __init__(self, *, report_model, report, proposal, results):
        self.objects = {
            (report_model, report.report_id): report,
            (Proposal, report.proposal_id): proposal,
        }
        self.results = list(results)
        self.statements = []

    def get(self, model, object_id):
        return self.objects.get((model, object_id))

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)


def _dob(age: int) -> date:
    today = date.today()
    return date(today.year - age, today.month, today.day)


def _participant(participant_id: int, *, name: str, age: int):
    return SimpleNamespace(
        participant_id=participant_id,
        expediente_num=f"MUTABLE-{participant_id}",
        nombre=name,
        inicial=None,
        apellido_paterno="Mutable",
        apellido_materno=None,
        genero="F",
        fecha_nacimiento=_dob(age),
    )


def _sql(statement) -> str:
    return " ".join(str(statement).lower().split())


class OperationalReportParticipantSnapshotTests(unittest.TestCase):
    def test_detail_rows_use_proposal_snapshot_and_preserve_legacy_fallback(self):
        cases: tuple[tuple[str, Any, Any, Any, str], ...] = (
            (
                "school grades",
                school_grades,
                school_grades.school_grade_report_detail,
                SchoolGradeReport,
                "school_grade_report_items",
            ),
            (
                "school dropout",
                school_dropout,
                school_dropout.school_dropout_report_detail,
                SchoolDropoutReport,
                "school_dropout_report_items",
            ),
            (
                "pregnancy",
                pregnancy,
                pregnancy.pregnancy_report_detail,
                PregnancyReport,
                "pregnancy_report_items",
            ),
        )

        for name, module, detail, report_model, item_table in cases:
            with self.subTest(report=name):
                report = SimpleNamespace(
                    report_id=REPORT_ID,
                    proposal_id=PROPOSAL_ID,
                    residential_id=None,
                    report_month=1,
                    report_year=2026,
                )
                proposal = SimpleNamespace(
                    status="active",
                    locked_through_month=None,
                    locked_through_year=None,
                )
                snapshotted_participant = _participant(101, name="Mutable snapshot source", age=18)
                legacy_participant = _participant(102, name="Legacy fallback", age=16)
                proposal_participant = SimpleNamespace(
                    nombre="Frozen identity",
                    genero=None,
                    fecha_nacimiento=_dob(12),
                )
                snapshot_item = SimpleNamespace(participant_id=snapshotted_participant.participant_id)
                legacy_item = SimpleNamespace(participant_id=legacy_participant.participant_id)
                db = _Database(
                    report_model=report_model,
                    report=report,
                    proposal=proposal,
                    results=[
                        _Result(),
                        _Result([
                            (snapshot_item, snapshotted_participant, proposal_participant),
                            (legacy_item, legacy_participant, None),
                        ]),
                    ],
                )

                with patch.object(
                    module.templates,
                    "TemplateResponse",
                    side_effect=lambda _template, context: context,
                ):
                    context = detail(
                        report_id=REPORT_ID,
                        request=SimpleNamespace(session={}),
                        db=db,
                        current_user=cast(Any, SimpleNamespace(role="admin")),
                    )

                snapshot_view = context["report_items"][0][1]
                self.assertEqual(snapshot_view.nombre, "Frozen identity")
                self.assertIsNone(snapshot_view.genero)
                self.assertEqual(context["age_map"][snapshotted_participant.participant_id], 12)
                self.assertIs(context["report_items"][1][1], legacy_participant)
                self.assertEqual(context["age_map"][legacy_participant.participant_id], 16)

                item_statement = db.statements[1]
                sql = _sql(item_statement)
                self.assertIn(f"from {item_table}", sql)
                self.assertIn(
                    "persons.legacy_participant_id = participants.participant_id",
                    sql,
                )
                self.assertIn(
                    "proposal_participants.person_id = persons.person_id",
                    sql,
                )
                self.assertIn("proposal_participants.proposal_id =", sql)
                self.assertIn(PROPOSAL_ID, item_statement.compile().params.values())


if __name__ == "__main__":
    unittest.main()
