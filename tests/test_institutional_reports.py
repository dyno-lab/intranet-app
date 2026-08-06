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
            _Result(values=[]),
            _Result(values=[]),
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
        self.assertEqual(payload["real"]["grades"], {
            "Español": 0,
            "Matemáticas": 0,
            "Ciencias": 0,
            "Inglés": 0,
        })
        self.assertEqual(
            list(payload["real"]["grades"]),
            ["Español", "Matemáticas", "Ciencias", "Inglés"],
        )
        self.assertEqual(payload["real"]["pregnancy"], {
            "women": 0,
            "men": 0,
            "followups": 0,
        })
        self.assertEqual(payload["filters"]["proposal_ids"], [2, 1])
        self.assertEqual(payload["meta"]["real_metrics"], [
            "activities",
            "people",
            "duplicates",
            "towns",
            "age",
            "education",
            "grades",
            "pregnancy",
            "towns_by_municipality",
        ])
        self.assertEqual(payload["meta"]["demo_metrics"], [])
        self.assertEqual(payload["meta"]["age_reference_date"], "2026-12-31")
        self.assertNotIn("attendance", str(db.statements[1]).lower())
        self.assertIn("distinct", str(db.statements[1]).lower())
        self.assertEqual(len(db.statements), 6)

    def test_data_endpoint_deduplicates_people_and_returns_aggregate_profiles_without_pii(self):
        db = _Database([
            _Result(values=[1, 2]),
            _Result(scalar=9),
            _Result(values=[1, 3, 2, 4]),
            _Result(values=[
                (90_101, date(2014, 12, 31), "  ", None),
                (90_101, date(2014, 12, 31), " Elemental ", " Caguas "),
                (90_101, date(2014, 12, 31), "Superior", "Cidra"),
                (90_102, date(2014, 12, 31), "Elemental", "Caguas"),
                (90_103, date(2014, 12, 31), " Intermedia ", " Cidra "),
                (90_104, date(2000, 2, 2), None, None),
                (90_105, date(2000, 2, 2), " Superior ", " "),
                (90_105, date(2000, 2, 2), "Superior", " Cayey "),
                (90_106, date(2007, 12, 31), "", "Cidra"),
                (90_107, date(1966, 12, 31), "Superior", "Caguas"),
                (90_108, None, None, None),
            ]),
            _Result(values=[
                (90_101, 1, 2026, 1, 1, 60, 70, 80, 90),
                (90_101, 1, 2026, 3, 1, 75, 75, 75, 75),
                (90_101, 1, 2026, 3, 2, 80, None, 110, -5),
                (90_102, 2, 2026, 1, 3, 92, 80, 70, 60),
                (None, 30, 2026, 1, 4, 50, 50, 50, 50),
                (None, 30, 2026, 2, 5, 100, 100, 100, 100),
            ]),
            _Result(values=[
                (True, True, 2026, 1, 10, 1, " Femenino ", 90_101),
                (False, False, 2026, 3, 11, 1, " masculino ", 90_101),
                (False, True, 2026, 2, 20, 2, "M", 90_102),
                (False, True, 2026, 2, 21, 2, " femenino ", 90_102),
                (False, False, 2026, 1, 30, 30, "F", None),
                (True, True, 2026, 4, 31, 30, " Femenino ", None),
                (True, True, 2026, 5, 40, 4, "No informado", 90_104),
                (False, True, 2026, 5, 41, 5, None, 90_105),
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
        self.assertEqual(payload["real"]["duplicates"], 6)
        self.assertEqual(payload["real"]["towns"], 3)
        self.assertEqual(payload["real"]["towns_by_municipality"], {
            "Caguas": 3,
            "Cayey": 1,
            "Cidra": 2,
            "No informado": 2,
        })
        self.assertEqual(payload["real"]["grades"], {
            "Español": 91,
            "Matemáticas": 90,
            "Ciencias": 85,
            "Inglés": 80,
        })
        self.assertEqual(payload["real"]["pregnancy"], {
            "women": 2,
            "men": 1,
            "followups": 3,
        })
        self.assertEqual(sum(payload["real"]["towns_by_municipality"].values()), 8)
        self.assertNotIn("people", payload["meta"]["demo_metrics"])
        self.assertNotIn("duplicates", payload["meta"]["demo_metrics"])
        self.assertNotIn("towns", payload["meta"]["demo_metrics"])
        self.assertNotIn("towns_by_municipality", payload["meta"]["demo_metrics"])
        self.assertNotIn("age", payload["meta"]["demo_metrics"])
        self.assertNotIn("education", payload["meta"]["demo_metrics"])
        self.assertIn("grades", payload["meta"]["real_metrics"])
        self.assertNotIn("grades", payload["meta"]["demo_metrics"])
        self.assertIn("pregnancy", payload["meta"]["real_metrics"])
        self.assertNotIn("pregnancy", payload["meta"]["demo_metrics"])
        self.assertEqual(payload["meta"]["demo_metrics"], [])

        attendance_sql = str(db.statements[2]).lower()
        self.assertIn("count(attendance.attendance_id)", attendance_sql)
        self.assertIn("group by persons.person_id", attendance_sql)
        self.assertIn("attendance.proposal_participant_id", attendance_sql)
        self.assertNotIn("attendance.participant_id", attendance_sql)
        self.assertNotIn("distinct", attendance_sql)
        self.assertIn("proposal_participants.proposal_id = activity_sessions.proposal_id", attendance_sql)

        people_sql = str(db.statements[3]).lower()
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

        attendance_sql_server = str(db.statements[2].compile(dialect=mssql.dialect())).lower()
        self.assertIn("attended", attendance_sql_server)
        self.assertNotIn("attended is 1", attendance_sql_server)
        people_sql_server = str(db.statements[3].compile(dialect=mssql.dialect())).lower()
        self.assertIn("attended", people_sql_server)
        self.assertNotIn("attended is 1", people_sql_server)

        grades_sql = str(db.statements[4]).lower()
        self.assertIn("school_grade_report_items", grades_sql)
        self.assertIn("school_grade_reports", grades_sql)
        self.assertIn("join participants", grades_sql)
        self.assertIn("left outer join persons", grades_sql)
        self.assertIn("datefromparts", grades_sql)
        self.assertIn("school_grade_reports.report_year =", grades_sql)
        self.assertIn("datefromparts(school_grade_reports.report_year", grades_sql)
        self.assertIn(" >= ", grades_sql)
        self.assertIn(" <= ", grades_sql)
        self.assertNotIn("attendance", grades_sql)
        grades_sql_server = str(db.statements[4].compile(dialect=mssql.dialect())).lower()
        self.assertIn("datefromparts", grades_sql_server)

        pregnancy_sql = str(db.statements[5]).lower()
        self.assertIn("pregnancy_report_items", pregnancy_sql)
        self.assertIn("pregnancy_reports", pregnancy_sql)
        self.assertIn("pregnancy_reports.proposal_id in", pregnancy_sql)
        self.assertIn("join participants", pregnancy_sql)
        self.assertIn("left outer join persons", pregnancy_sql)
        self.assertIn("datefromparts", pregnancy_sql)
        self.assertIn("pregnancy_reports.report_year =", pregnancy_sql)
        self.assertIn("datefromparts(pregnancy_reports.report_year", pregnancy_sql)
        self.assertIn(" >= ", pregnancy_sql)
        self.assertIn(" <= ", pregnancy_sql)
        self.assertNotIn("attendance", pregnancy_sql)
        pregnancy_sql_server = str(db.statements[5].compile(dialect=mssql.dialect())).lower()
        self.assertIn("datefromparts", pregnancy_sql_server)

        forbidden_keys = {
            "person_id",
            "participant_id",
            "proposal_participant_id",
            "attendance_id",
            "session_id",
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
            "report_id",
            "report_item_id",
            "spanish_grade",
            "english_grade",
            "math_grade",
            "science_grade",
            "genero",
            "is_pregnant",
            "participated_workshops",
            "gestation_time",
            "has_children",
            "children_count",
            "children_ages",
            "created_by_user_id",
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
        self.assertNotIn("2014-12-31", serialized_payload)

    def test_subject_grades_use_latest_report_and_ignore_invalid_values(self):
        grade_rows = [
            (101, 1, 2026, 1, 1, 60, 70, 80, 90),
            (101, 1, 2026, 3, 1, 75, 75, 75, 75),
            (101, 1, 2026, 3, 2, 80, None, 110, -5),
            (102, 2, 2026, 1, 3, 92, 80, 70, 60),
            (None, 30, 2026, 1, 4, 50, 50, 50, 50),
            (None, 30, 2026, 2, 5, 100, 100, 100, 100),
        ]

        self.assertEqual(
            institutional_reports._aggregate_subject_grades(grade_rows),
            {
                "Español": 91,
                "Matemáticas": 90,
                "Ciencias": 85,
                "Inglés": 80,
            },
        )

    def test_pregnancy_summary_deduplicates_and_uses_latest_available_gender(self):
        pregnancy_rows = [
            (True, True, 2026, 1, 10, 1, " Femenino ", 101),
            (False, False, 2026, 3, 11, 1, " masculino ", 101),
            (False, True, 2026, 2, 20, 2, "M", 102),
            (False, True, 2026, 2, 21, 2, " femenino ", 102),
            (False, False, 2026, 1, 30, 30, "F", None),
            (True, True, 2026, 4, 31, 30, " Femenino ", None),
            (True, True, 2026, 5, 40, 4, "No informado", 104),
            (False, True, 2026, 5, 41, 5, None, 105),
        ]

        self.assertEqual(
            institutional_reports._aggregate_pregnancy_summary(pregnancy_rows),
            {
                "women": 2,
                "men": 1,
                "followups": 3,
            },
        )

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

    def test_additional_attendances_returns_zero_for_one_attendance(self):
        self.assertEqual(institutional_reports._count_additional_attendances([1]), 0)

    def test_additional_attendances_returns_two_for_three_attendances(self):
        self.assertEqual(institutional_reports._count_additional_attendances([3]), 2)

    def test_additional_attendances_sums_multiple_people(self):
        self.assertEqual(
            institutional_reports._count_additional_attendances([1, 3, 2, 4]),
            6,
        )

    def test_data_endpoint_rejects_unavailable_proposals(self):
        db = _Database([_Result(values=[1])])

        response = self._call(db=db, proposal_ids=[1, 2])

        self.assertEqual(response.status_code, 400)
        self.assertIn("no están disponibles", _payload(response)["detail"])
        self.assertEqual(len(db.statements), 1)


if __name__ == "__main__":
    unittest.main()
