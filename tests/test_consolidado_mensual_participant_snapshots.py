from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.models.proposal import Proposal  # noqa: E402
from app.services import consolidado_mensual_service  # noqa: E402


PROPOSAL_ID = 17
RESIDENTIAL_ID = 9
SESSION_DATE = date(2026, 9, 3)


class _Result:
    def __init__(self, values=None):
        self.values = list(values or [])

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Database:
    def __init__(self, *, results):
        self.results = list(results)
        self.statements = []

    def get(self, model, object_id):
        if model is Proposal and object_id == PROPOSAL_ID:
            return SimpleNamespace(proposal_id=PROPOSAL_ID)
        return None

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)


def _participant(
    participant_id: int,
    *,
    genero: str | None,
    fecha_nacimiento: date | None,
):
    return SimpleNamespace(
        participant_id=participant_id,
        genero=genero,
        fecha_nacimiento=fecha_nacimiento,
    )


def _session(session_id: int):
    return SimpleNamespace(
        session_id=session_id,
        session_date=SESSION_DATE,
        activity_code_id=31,
        residential_id=RESIDENTIAL_ID,
        proposal_id=PROPOSAL_ID,
    )


def _age_row(rows, key: str):
    return next(row for row in rows if row["key"] == key)


def _sql(statement) -> str:
    return " ".join(str(statement).lower().split())


class ConsolidadoMensualParticipantSnapshotTests(unittest.TestCase):
    def test_demographics_use_session_proposal_snapshot_with_strict_fallback(self):
        residential = SimpleNamespace(
            residential_id=RESIDENTIAL_ID,
            code="R-9",
            name="Residential",
            municipality="Ponce",
            rq_code="RQ 9",
            is_active=True,
        )
        activity_code = SimpleNamespace(activity_code_id=31, code="1-A Workshop")
        attendance = SimpleNamespace(attended=True)

        snapshot_source = _participant(
            101,
            genero="F",
            fecha_nacimiento=date(1980, 1, 1),
        )
        snapshotted = SimpleNamespace(
            genero="M",
            fecha_nacimiento=date(2014, 9, 4),
        )
        null_snapshot_source = _participant(
            102,
            genero="M",
            fecha_nacimiento=date(2000, 1, 1),
        )
        null_snapshot = SimpleNamespace(genero=None, fecha_nacimiento=None)
        legacy_fallback = _participant(
            103,
            genero="F",
            fecha_nacimiento=date(2020, 9, 3),
        )

        db = _Database(
            results=[
                _Result([residential]),
                _Result(),
                _Result([
                    (
                        _session(1),
                        attendance,
                        snapshot_source,
                        activity_code,
                        residential,
                        snapshotted,
                    ),
                    (
                        _session(2),
                        attendance,
                        null_snapshot_source,
                        activity_code,
                        residential,
                        null_snapshot,
                    ),
                    (
                        _session(3),
                        attendance,
                        legacy_fallback,
                        activity_code,
                        residential,
                        None,
                    ),
                ]),
            ]
        )

        context = consolidado_mensual_service.build_consolidado_mensual_global(
            db,
            month=9,
            year=2026,
            proposal_id=PROPOSAL_ID,
            residential_id=RESIDENTIAL_ID,
        )

        self.assertEqual(context["selected_proposal_id"], PROPOSAL_ID)
        self.assertEqual(context["selected_residential_id"], RESIDENTIAL_ID)
        self.assertEqual(len(context["rows"]), 1)

        row = context["rows"][0]
        self.assertEqual(row["attendances"], 3)
        self.assertEqual(row["unique_participants"], 3)
        self.assertEqual(row["attendance_gender"], {"F": 1, "M": 1, "total": 2})
        self.assertEqual(row["gender"], {"F": 1, "M": 1, "total": 2})
        self.assertEqual(
            _age_row(row["attendance_age_rows"], "11_15"),
            {"key": "11_15", "label": "11 - 15 años", "F": 0, "M": 1, "total": 1},
        )
        self.assertEqual(
            _age_row(row["attendance_age_rows"], "6_7"),
            {"key": "6_7", "label": "6–7 años", "F": 1, "M": 0, "total": 1},
        )
        self.assertEqual(_age_row(row["attendance_age_rows"], "22_59")["total"], 0)

        program = next(item for item in row["programs"] if item["code"] == "1-A")
        self.assertEqual(program["attendances"], 3)
        self.assertEqual(program["unique_participants"], 3)
        self.assertEqual(program["gender"], {"F": 1, "M": 1, "total": 2})
        self.assertEqual(program["age_rows"]["11_15"]["M"], 1)
        self.assertEqual(program["age_rows"]["6_7"]["F"], 1)
        self.assertEqual(program["age_rows"]["22_59"]["total"], 0)

        attendance_sql = _sql(db.statements[2])
        self.assertIn(
            "persons.legacy_participant_id = participants.participant_id",
            attendance_sql,
        )
        self.assertIn(
            "proposal_participants.person_id = persons.person_id",
            attendance_sql,
        )
        self.assertIn(
            "proposal_participants.proposal_id = activity_sessions.proposal_id",
            attendance_sql,
        )
        self.assertIn(
            "residentials.residential_id = activity_sessions.residential_id",
            attendance_sql,
        )


if __name__ == "__main__":
    unittest.main()
