from __future__ import annotations

import json
import os
import unittest
from datetime import date
from unittest.mock import patch

from sqlalchemy.dialects import mssql


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
        self.assertEqual(payload["real"]["education"], {"No informado": 0})
        self.assertEqual(payload["real"]["duplicates"], 0)
        self.assertEqual(payload["real"]["towns"], 0)
        self.assertEqual(payload["real"]["towns_by_municipality"], {"No informado": 0})
        self.assertEqual(payload["filters"]["proposal_ids"], [2, 1])
        self.assertEqual(payload["meta"]["real_metrics"], [
            "activities",
            "people",
            "duplicates",
            "towns",
            "age",
            "education",
            "towns_by_municipality",
        ])
        self.assertEqual(payload["meta"]["demo_metrics"], ["grades", "pregnancy"])
        self.assertEqual(payload["meta"]["age_reference_date"], "2026-12-31")
        self.assertNotIn("attendance", str(db.statements[1]).lower())
        self.assertIn("distinct", str(db.statements[1]).lower())
        self.assertEqual(len(db.statements), 3)

    def test_data_endpoint_deduplicates_people_and_returns_aggregate_profiles_without_pii(self):
        db = _Database([
            _Result(values=[1, 2]),
            _Result(scalar=9),
            _Result(values=[
                (90_101, date(2014, 12, 31), "  ", None, " Ana ", "Pérez", "Ríos"),
                (90_101, date(2014, 12, 31), " Elemental ", " Caguas ", " Ana ", "Pérez", "Ríos"),
                (90_101, date(2014, 12, 31), "Superior", "Cidra", " Ana ", "Pérez", "Ríos"),
                (90_102, date(2014, 12, 31), "Elemental", "Caguas", "ana", " pérez ", " ríOS "),
                (90_103, date(2014, 12, 31), " Intermedia ", " Cidra ", "ANA", "PÉREZ", "RÍOS"),
                (90_104, date(2000, 2, 2), None, None, " Luis ", "Soto", None),
                (90_105, date(2000, 2, 2), " Superior ", " ", "luis", " soto ", ""),
                (90_105, date(2000, 2, 2), "Superior", " Cayey ", "luis", " soto ", ""),
                (90_106, date(2007, 12, 31), "", "Cidra", " ", "Ortiz", "Vega"),
                (90_107, date(1966, 12, 31), "Superior", "Caguas", "Marta", " ", "López"),
                (90_108, None, None, None, "Carlos", "Díaz", None),
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
        self.assertEqual(payload["real"]["people"], 8)
        self.assertEqual(payload["real"]["age"], {
            "0 a 12": 3,
            "13 a 18": 0,
            "19 a 59": 3,
            "60 o más": 1,
            "No informado": 1,
        })
        self.assertEqual(payload["real"]["education"], {
            "Elemental": 2,
            "Intermedia": 1,
            "Superior": 2,
            "No informado": 3,
        })
        self.assertEqual(payload["real"]["duplicates"], 3)
        self.assertEqual(payload["real"]["towns"], 3)
        self.assertEqual(payload["real"]["towns_by_municipality"], {
            "Caguas": 3,
            "Cayey": 1,
            "Cidra": 2,
            "No informado": 2,
        })
        self.assertEqual(sum(payload["real"]["towns_by_municipality"].values()), 8)
        self.assertNotIn("people", payload["meta"]["demo_metrics"])
        self.assertNotIn("duplicates", payload["meta"]["demo_metrics"])
        self.assertNotIn("towns", payload["meta"]["demo_metrics"])
        self.assertNotIn("towns_by_municipality", payload["meta"]["demo_metrics"])
        self.assertNotIn("age", payload["meta"]["demo_metrics"])
        self.assertNotIn("education", payload["meta"]["demo_metrics"])

        people_sql = str(db.statements[2]).lower()
        self.assertIn("select distinct", people_sql)
        self.assertIn("attendance.proposal_participant_id", people_sql)
        self.assertNotIn("attendance.participant_id", people_sql)
        self.assertIn("attendance.attended", people_sql)
        self.assertIn("left outer join participants", people_sql)
        self.assertIn("persons.legacy_participant_id = participants.participant_id", people_sql)
        self.assertIn("left outer join users", people_sql)
        self.assertIn("participants.created_by_user_id = users.user_id", people_sql)
        self.assertIn("left outer join residentials", people_sql)
        self.assertIn("users.residential_id = residentials.residential_id", people_sql)
        self.assertIn("proposal_participants.proposal_id = activity_sessions.proposal_id", people_sql)
        self.assertIn("extract(year from activity_sessions.session_date)", people_sql)
        self.assertIn("activity_sessions.session_date >=", people_sql)
        self.assertIn("activity_sessions.session_date <=", people_sql)

        people_sql_server = str(db.statements[2].compile(dialect=mssql.dialect())).lower()
        self.assertIn("attended", people_sql_server)
        self.assertNotIn("attended is 1", people_sql_server)

        forbidden_keys = {
            "person_id",
            "participant_id",
            "proposal_participant_id",
            "nombre",
            "apellido",
            "apellido_paterno",
            "apellido_materno",
            "expediente",
            "telefono",
            "email",
            "direccion",
            "address",
            "phone",
            "fecha_nacimiento",
            "escolaridad_participante",
            "residential",
            "residencial",
            "residential_id",
            "residential_name",
            "residential_code",
            "rq_code",
            "municipality",
        }
        self.assertTrue(forbidden_keys.isdisjoint(_payload_keys(payload)))
        serialized_payload = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("90101", serialized_payload)
        self.assertNotIn("90108", serialized_payload)
        self.assertNotIn("Ana", serialized_payload)
        self.assertNotIn("Pérez", serialized_payload)
        self.assertNotIn("2014-12-31", serialized_payload)

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

    def test_duplicate_aggregation_counts_exact_person_duplicates(self):
        reference_date = date(2026, 12, 31)
        rows = [
            (1, date(2010, 5, 10), None, None, "Ana", "Pérez", "Ríos"),
            (2, date(2010, 5, 10), None, None, "Ana", "Pérez", "Ríos"),
            (3, date(2010, 5, 10), None, None, "Ana", "Pérez", "Ríos"),
        ]

        aggregates = institutional_reports._aggregate_unique_people(rows, reference_date)

        self.assertGreater(aggregates[3], 0)
        self.assertEqual(aggregates[3], 2)

    def test_duplicate_aggregation_excludes_people_with_null_birth_date(self):
        reference_date = date(2026, 12, 31)
        rows = [
            (1, None, None, None, "Ana", "Pérez", "Ríos"),
            (2, None, None, None, "Ana", "Pérez", "Ríos"),
        ]

        aggregates = institutional_reports._aggregate_unique_people(rows, reference_date)

        self.assertEqual(aggregates[3], 0)

    def test_duplicate_aggregation_ignores_different_or_empty_maternal_surnames(self):
        reference_date = date(2026, 12, 31)

        for second_maternal_surname in ("Rivera", ""):
            rows = [
                (1, date(2010, 5, 10), None, None, "Ana", "Pérez", "Ríos"),
                (
                    2,
                    date(2010, 5, 10),
                    None,
                    None,
                    "Ana",
                    "Pérez",
                    second_maternal_surname,
                ),
            ]

            with self.subTest(second_maternal_surname=second_maternal_surname):
                aggregates = institutional_reports._aggregate_unique_people(rows, reference_date)
                self.assertEqual(aggregates[3], 1)

    def test_duplicate_aggregation_normalizes_accents_whitespace_and_case(self):
        reference_date = date(2026, 12, 31)
        rows = [
            (1, date(2010, 5, 10), None, None, " Juan   Carlos ", " Pérez ", "Ríos"),
            (2, date(2010, 5, 10), None, None, "JUAN CARLOS", "PEREZ", "Rivera"),
        ]

        aggregates = institutional_reports._aggregate_unique_people(rows, reference_date)

        self.assertEqual(aggregates[3], 1)

    def test_duplicate_aggregation_counts_each_person_id_only_once(self):
        reference_date = date(2026, 12, 31)
        rows = [
            (1, date(2010, 5, 10), None, None, "Ana", "Pérez", "Ríos"),
            (1, date(2010, 5, 10), None, "Caguas", "Ana", "Pérez", "Ríos"),
            (2, date(2010, 5, 10), None, None, "Ana", "Pérez", "Rivera"),
        ]

        aggregates = institutional_reports._aggregate_unique_people(rows, reference_date)

        self.assertEqual(aggregates[0], 2)
        self.assertEqual(aggregates[3], 1)

    def test_duplicate_aggregation_requires_name_and_paternal_surname(self):
        reference_date = date(2026, 12, 31)
        incomplete_rows = [
            (1, date(2010, 5, 10), None, None, "", "Pérez", "Ríos"),
            (2, date(2010, 5, 10), None, None, "", "Pérez", "Ríos"),
            (3, date(2010, 5, 10), None, None, "Ana", "", "Ríos"),
            (4, date(2010, 5, 10), None, None, "Ana", "", "Ríos"),
        ]

        aggregates = institutional_reports._aggregate_unique_people(
            incomplete_rows,
            reference_date,
        )
        self.assertEqual(aggregates[3], 0)

    def test_data_endpoint_rejects_unavailable_proposals(self):
        db = _Database([_Result(values=[1])])

        response = self._call(db=db, proposal_ids=[1, 2])

        self.assertEqual(response.status_code, 400)
        self.assertIn("no están disponibles", _payload(response)["detail"])
        self.assertEqual(len(db.statements), 1)


if __name__ == "__main__":
    unittest.main()
