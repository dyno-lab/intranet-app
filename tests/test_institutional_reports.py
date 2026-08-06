from __future__ import annotations

import json
import os
import unittest
from datetime import date
from unittest.mock import patch


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from app.api.routes import institutional_reports  # noqa: E402


class _Request:
    def __init__(self, session: dict | None = None):
        self.session = session or {}


class _Result:
    def __init__(self, *, values: list | None = None, scalar: int | None = None):
        self._values = values or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._values

    def scalar_one(self):
        return self._scalar


class _Database:
    def __init__(self, results: list[_Result] | None = None):
        self.results = list(results or [])
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("The endpoint executed an unexpected database query.")
        return self.results.pop(0)


def _payload(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


def _payload_keys(value) -> set[str]:
    if isinstance(value, dict):
        keys = set(value)
        for item in value.values():
            keys.update(_payload_keys(item))
        return keys
    if isinstance(value, list):
        keys = set()
        for item in value:
            keys.update(_payload_keys(item))
        return keys
    return set()


class FaroInstitutionalReportDataTests(unittest.TestCase):
    def _authorized_request(self) -> _Request:
        return _Request({institutional_reports._FARO_AUTHORIZED_AT_KEY: 1_000})

    def _call(self, *, request=None, db=None, proposal_ids=None, year=None, start_date=None, end_date=None):
        with (
            patch.object(institutional_reports, "_configured_faro_pin", return_value="1234"),
            patch.object(institutional_reports, "_current_timestamp", return_value=1_000),
        ):
            return institutional_reports.faro_institutional_report_data(
                request=request or self._authorized_request(),
                proposal_ids=proposal_ids,
                year=year,
                start_date=start_date,
                end_date=end_date,
                db=db or _Database(),
            )

    def test_data_endpoint_requires_pin_authorization(self):
        response = self._call(request=_Request(), proposal_ids=["not-an-id"])

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("autorización", _payload(response)["detail"])

    def test_data_endpoint_validates_filters_after_authorization(self):
        response = self._call(proposal_ids=["not-an-id"])

        self.assertEqual(response.status_code, 400)
        self.assertIn("números enteros", _payload(response)["detail"])

    def test_data_endpoint_requires_at_least_one_proposal(self):
        response = self._call(proposal_ids=[])

        self.assertEqual(response.status_code, 400)
        self.assertEqual(_payload(response)["detail"], "Seleccione al menos una propuesta.")

    def test_data_endpoint_rejects_inverted_dates_without_querying(self):
        response = self._call(
            proposal_ids=[1],
            start_date=date(2026, 2, 1),
            end_date=date(2026, 1, 31),
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("fecha inicial", _payload(response)["detail"].lower())

    def test_data_endpoint_counts_distinct_sessions_for_repeated_proposal_params(self):
        db = _Database([
            _Result(values=[1, 2]),
            _Result(scalar=7),
            _Result(values=[]),
        ])

        response = self._call(
            db=db,
            proposal_ids=[2, 1, 2],
            year=2026,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        payload = _payload(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["real"]["activities"], 7)
        self.assertEqual(payload["real"]["people"], 0)
        self.assertEqual(sum(payload["real"]["age"].values()), 0)
        self.assertEqual(payload["filters"]["proposal_ids"], [2, 1])
        self.assertEqual(payload["meta"]["real_metrics"], ["activities", "people", "age"])
        self.assertEqual(payload["meta"]["age_reference_date"], "2026-12-31")
        self.assertNotIn("attendance", str(db.statements[1]).lower())
        self.assertIn("distinct", str(db.statements[1]).lower())
        self.assertEqual(len(db.statements), 3)

    def test_data_endpoint_deduplicates_people_and_groups_age_without_pii(self):
        db = _Database([
            _Result(values=[1, 2]),
            _Result(scalar=9),
            _Result(values=[
                (90_101, date(2014, 12, 31)),
                (90_101, date(2014, 12, 31)),
                (90_102, date(2013, 12, 31)),
                (90_103, date(2007, 12, 31)),
                (90_104, date(1966, 12, 31)),
                (90_105, None),
                (90_106, date(2027, 1, 1)),
            ]),
        ])

        response = self._call(
            db=db,
            proposal_ids=[1, 2],
            year=2026,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31),
        )
        payload = _payload(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["real"]["people"], 6)
        self.assertEqual(payload["real"]["age"], {
            "0 a 12": 1,
            "13 a 18": 1,
            "19 a 59": 1,
            "60 o más": 1,
            "No informado": 2,
        })
        self.assertNotIn("people", payload["meta"]["demo_metrics"])
        self.assertNotIn("age", payload["meta"]["demo_metrics"])

        people_sql = str(db.statements[2]).lower()
        self.assertIn("select distinct", people_sql)
        self.assertIn("attendance.proposal_participant_id", people_sql)
        self.assertNotIn("attendance.participant_id", people_sql)
        self.assertIn("attendance.attended is true", people_sql)
        self.assertIn("proposal_participants.proposal_id = activity_sessions.proposal_id", people_sql)
        self.assertIn("extract(year from activity_sessions.session_date)", people_sql)
        self.assertIn("activity_sessions.session_date >=", people_sql)
        self.assertIn("activity_sessions.session_date <=", people_sql)

        forbidden_keys = {
            "person_id",
            "participant_id",
            "proposal_participant_id",
            "nombre",
            "expediente",
            "telefono",
            "email",
            "direccion",
            "address",
            "phone",
            "fecha_nacimiento",
            "residential",
            "residencial",
        }
        self.assertTrue(forbidden_keys.isdisjoint(_payload_keys(payload)))
        serialized_payload = json.dumps(payload)
        self.assertNotIn("90101", serialized_payload)
        self.assertNotIn("90106", serialized_payload)

    def test_age_reference_date_precedence(self):
        self.assertEqual(
            institutional_reports._age_reference_date(date(2025, 6, 30), 2026),
            date(2025, 6, 30),
        )
        self.assertEqual(
            institutional_reports._age_reference_date(None, 2026),
            date(2026, 12, 31),
        )
        with patch.object(institutional_reports, "_current_date", return_value=date(2026, 8, 6)):
            self.assertEqual(
                institutional_reports._age_reference_date(None, None),
                date(2026, 8, 6),
            )

    def test_data_endpoint_rejects_unavailable_proposals(self):
        db = _Database([_Result(values=[1])])

        response = self._call(db=db, proposal_ids=[1, 2])

        self.assertEqual(response.status_code, 400)
        self.assertIn("no están disponibles", _payload(response)["detail"])
        self.assertEqual(len(db.statements), 1)


if __name__ == "__main__":
    unittest.main()
