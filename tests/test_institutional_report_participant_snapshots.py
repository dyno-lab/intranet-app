from __future__ import annotations

import json
import os
import unittest
from datetime import date
from types import SimpleNamespace

from sqlalchemy.dialects import mssql


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from app.api.routes import institutional_reports  # noqa: E402


class _Result:
    def __init__(self, *, values=None, scalar=None):
        self.values = list(values or [])
        self.scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one(self):
        return self.scalar


class _Database:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)


def _sql(statement) -> str:
    return " ".join(str(statement).lower().split())


def _payload(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


class InstitutionalReportParticipantSnapshotTests(unittest.TestCase):
    def test_faro_demographics_use_snapshot_cases_and_preserve_nulls(self):
        db = _Database(
            [
                _Result(values=[17]),
                _Result(scalar=2),
                _Result(values=[2]),
                _Result(
                    values=[
                        (987654, None, None, False, "Arecibo"),
                        (-876543, date(2010, 1, 1), "Secundaria", True, "Ponce"),
                        (None, date(1980, 1, 1), "No debe contar", True, "Vieques"),
                    ]
                ),
                _Result(values=[]),
                _Result(
                    values=[
                        (True, True, 2026, 1, 1, 1, None, 987654),
                        (False, True, 2026, 1, 2, 2, "F", None),
                    ]
                ),
                _Result(values=[]),
            ]
        )

        response = institutional_reports.faro_institutional_report_data(
            request=SimpleNamespace(session={}),
            proposal_ids=["17"],
            year="2026",
            start_date="2026-01-01",
            end_date="2026-12-31",
            db=db,
        )
        payload = _payload(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["real"]["people"], 2)
        self.assertEqual(
            payload["real"]["age"],
            {
                "0 a 12": 0,
                "13 a 18": 1,
                "19 a 59": 0,
                "60 o más": 0,
                "No informado": 1,
            },
        )
        self.assertEqual(
            payload["real"]["education"],
            {"Secundaria": 1, "No informado": 1},
        )
        self.assertEqual(payload["real"]["household_heads"], 1)
        self.assertEqual(
            payload["real"]["pregnancy"],
            {"women": 1, "men": 0, "followups": 1},
        )

        people_sql = _sql(db.statements[3])
        self.assertIn("proposal_participants.fecha_nacimiento", people_sql)
        self.assertIn("proposal_participants.escolaridad_participante", people_sql)
        self.assertIn("proposal_participants.is_head_of_household", people_sql)
        self.assertIn(
            "proposal_participants.proposal_id = activity_sessions.proposal_id",
            people_sql,
        )
        self.assertIn(
            "attendance.proposal_participant_id = "
            "proposal_participants.proposal_participant_id",
            people_sql,
        )
        self.assertIn("proposal_participants.person_id = persons.person_id", people_sql)
        self.assertNotIn("attendance.participant_id", people_sql)
        self.assertNotIn("coalesce", people_sql)
        db.statements[3].compile(dialect=mssql.dialect())

        pregnancy_sql = _sql(db.statements[5])
        self.assertIn(
            "then proposal_participants.genero else participants.genero",
            pregnancy_sql,
        )
        self.assertIn(
            "proposal_participants.proposal_id = pregnancy_reports.proposal_id",
            pregnancy_sql,
        )
        db.statements[5].compile(dialect=mssql.dialect())

        serialized_payload = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("987654", serialized_payload)
        self.assertNotIn("876543", serialized_payload)

    def test_faro_adm_uses_effective_snapshot_demographics(self):
        service_type = SimpleNamespace(
            adm_service_type_id=10,
            proposal_id=17,
            name="Orientación",
            sort_order=1,
            is_active=True,
        )
        db = _Database(
            [
                _Result(values=[service_type]),
                _Result(values=[(1, 10)]),
                _Result(
                    values=[
                        (
                            1,
                            1,
                            101,
                            1,
                            10,
                            1,
                            date(1980, 1, 1),
                            "M",
                            "NO",
                            "Mutable",
                            1,
                            None,
                            None,
                            None,
                            None,
                        ),
                        (
                            1,
                            2,
                            None,
                            None,
                            10,
                            2,
                            date(2010, 1, 1),
                            "F",
                            "SI",
                            "Fallback",
                            None,
                            date(2010, 1, 1),
                            "F",
                            "SI",
                            "Fallback",
                        ),
                    ]
                ),
                _Result(values=[]),
            ]
        )

        adm = institutional_reports._faro_adm_summary(
            db,
            proposal_ids=[17],
            year=2026,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
            reference_date=date(2026, 12, 31),
        )

        self.assertEqual(adm["summary"]["duplicates"], 2)
        self.assertEqual(adm["summary"]["unique_participants"], 2)
        self.assertEqual(
            adm["sociodemographic_total"],
            {"f": 1, "m": 0, "total": 1, "vca": 1},
        )
        self.assertEqual(
            adm["family_rows"],
            [
                {"label": "Fallback", "count": 1},
                {"label": "No especificado", "count": 1},
            ],
        )
        self.assertEqual(adm["family_total"], 2)

        attendance_sql = _sql(db.statements[2])
        for snapshot_field, fallback_field in (
            ("fecha_nacimiento", "fecha_nacimiento"),
            ("genero", "genero"),
            ("vca", "vca"),
            ("composicion_familiar", "composicion_familiar"),
        ):
            with self.subTest(snapshot_field=snapshot_field):
                self.assertIn(
                    f"then proposal_participants.{snapshot_field} "
                    f"else attendance_participant.{fallback_field}",
                    attendance_sql,
                )
        self.assertIn(
            "proposal_participants.proposal_id = activity_sessions.proposal_id",
            attendance_sql,
        )
        self.assertIn(
            "proposal_participants.person_id = attendance_person.person_id",
            attendance_sql,
        )
        self.assertNotIn("coalesce", attendance_sql)
        db.statements[2].compile(dialect=mssql.dialect())


if __name__ == "__main__":
    unittest.main()
