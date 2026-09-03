from __future__ import annotations

import os
import unittest
from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import reports  # noqa: E402
from app.models.proposal import Proposal  # noqa: E402


PROPOSAL_ID = 17
ACTIVITY_CODE_ID = 31
SESSION_ID = 41


class _Result:
    def __init__(self, values=None):
        self.values = list(values or [])

    def scalars(self):
        return self

    def all(self):
        return self.values


class _Database:
    def __init__(self, *, results=None, objects=None):
        self.results = list(results or [])
        self.objects = dict(objects or {})
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        return self.results.pop(0)

    def get(self, model, object_id):
        return self.objects.get((model, object_id))


def _dob(age: int) -> date:
    today = date.today()
    return date(today.year - age, 1, 1)


def _participant(participant_id: int = 1, **overrides) -> Any:
    values: dict[str, Any] = {
        "participant_id": participant_id,
        "residential_id": 9,
        "created_by_user_id": 99,
        "nombre": "Mutable",
        "inicial": "M",
        "apellido_paterno": "Person",
        "apellido_materno": "Source",
        "genero": "F",
        "fecha_nacimiento": _dob(40),
        "exp_year": 2024,
        "exp_employee_initials": "SRC",
        "exp_seq4": "0001",
        "expediente_num": "SOURCE-1",
        "edificio": "Source building",
        "apart": "Source apartment",
        "vca": "NO",
        "primera_vez": "NO",
        "escolaridad_participante": "Source education",
        "composicion_familiar": "Source family",
        "relacion_familiar": "Source relation",
        "estatus": "Source status",
        "grupo_familiar": "Source group",
        "fuente_ingreso_principal": "Source income",
        "rango_ingreso": "Source range",
        "is_head_of_household": True,
        "is_active": True,
        "non_snapshot_marker": "kept-from-participant",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _proposal_participant(**overrides) -> Any:
    values: dict[str, Any] = {
        field_name: None
        for field_name in reports._PROPOSAL_PARTICIPANT_SNAPSHOT_FIELDS
    }
    values.update({
        "proposal_participant_id": 501,
        "proposal_id": PROPOSAL_ID,
        "person_id": 601,
        "nombre": "Snapshot",
        "inicial": "S",
        "apellido_paterno": "Proposal",
        "apellido_materno": "Frozen",
        "genero": "M",
        "fecha_nacimiento": _dob(12),
        "exp_year": 2025,
        "exp_employee_initials": "SNP",
        "exp_seq4": "0501",
        "expediente_num": "SNAPSHOT-501",
        "edificio": "Snapshot building",
        "apart": "Snapshot apartment",
        "vca": "SI",
        "primera_vez": "SI",
        "escolaridad_participante": "Snapshot education",
        "composicion_familiar": "Snapshot family",
        "relacion_familiar": "Snapshot relation",
        "estatus": "Snapshot status",
        "grupo_familiar": "Snapshot group",
        "fuente_ingreso_principal": "Snapshot income",
        "rango_ingreso": "Snapshot range",
        "is_head_of_household": False,
        "is_active": False,
    })
    values.update(overrides)
    return SimpleNamespace(**values)


def _user() -> Any:
    return SimpleNamespace()


def _base_context():
    return {
        "proposals": [],
        "report_users": [],
        "year_options": [2026],
        "month_lookup": {1: "Enero"},
        "user_residential_map": {},
    }


@contextmanager
def _global_report_context():
    scope = {
        "selected_user": None,
        "is_global": True,
        "employee_id": None,
    }
    with (
        patch.object(reports, "_base_reports_context", return_value=_base_context()),
        patch.object(reports, "_resolve_reporting_scope", return_value=scope),
        patch.object(reports, "report_authorized_name", return_value="Authorized"),
        patch.object(reports, "_resolve_report_template_config", return_value={}),
    ):
        yield


def _sql(statement) -> str:
    return " ".join(str(statement).lower().split())


def _assert_session_snapshot_join(test_case: unittest.TestCase, statement) -> None:
    sql = _sql(statement)
    test_case.assertIn(
        "persons.legacy_participant_id = participants.participant_id",
        sql,
    )
    test_case.assertIn(
        "proposal_participants.person_id = persons.person_id",
        sql,
    )
    test_case.assertIn(
        "proposal_participants.proposal_id = activity_sessions.proposal_id",
        sql,
    )


class ProposalReportParticipantSnapshotTests(unittest.TestCase):
    def test_proxy_overrides_all_23_fields_and_preserves_snapshot_none(self):
        self.assertEqual(len(reports._PROPOSAL_PARTICIPANT_SNAPSHOT_FIELDS), 23)
        participant = _participant()
        proposal_participant = _proposal_participant(genero=None)

        view = reports._participant_snapshot_view(participant, proposal_participant)

        for field_name in reports._PROPOSAL_PARTICIPANT_SNAPSHOT_FIELDS:
            with self.subTest(field_name=field_name):
                self.assertEqual(
                    getattr(view, field_name),
                    getattr(proposal_participant, field_name),
                )
        self.assertIsNone(view.genero)
        self.assertEqual(view.participant_id, participant.participant_id)
        self.assertEqual(view.residential_id, participant.residential_id)
        self.assertEqual(view.non_snapshot_marker, "kept-from-participant")
        self.assertIs(reports._participant_snapshot_view(participant, None), participant)

    def test_bonafide_uses_snapshot_values_and_session_proposal_join(self):
        participant = _participant()
        proposal_participant = _proposal_participant(
            expediente_num=None,
            edificio=None,
            apart=None,
        )
        db = _Database(results=[_Result([(participant, proposal_participant)])])

        with _global_report_context():
            context = reports._build_bonafide_context(
                db,
                _user(),
                PROPOSAL_ID,
                1,
                2026,
                None,
            )

        self.assertEqual(context["rows"][0]["expediente"], None)
        self.assertEqual(context["rows"][0]["nombre"], "Snapshot S. Proposal Frozen *")
        self.assertEqual(context["rows"][0]["m"], "X")
        self.assertEqual(context["rows"][0]["edificio"], "")
        self.assertEqual(context["rows"][0]["apartamento"], "")
        _assert_session_snapshot_join(self, db.statements[0])

    def test_vca_uses_effective_snapshot_filter_and_values(self):
        column = SimpleNamespace(vca_column_id=71, name="Workshop")
        activity = SimpleNamespace(activity_code_id=ACTIVITY_CODE_ID)
        mapping = SimpleNamespace()
        participant = _participant(vca="NO")
        proposal_participant = _proposal_participant(vca="SI")
        db = _Database(
            objects={(Proposal, PROPOSAL_ID): SimpleNamespace()},
            results=[
                _Result([column]),
                _Result([(mapping, activity, column)]),
                _Result([(participant, proposal_participant)]),
                _Result([(participant.participant_id, ACTIVITY_CODE_ID)]),
            ],
        )

        with _global_report_context():
            context = reports._build_vca_context(
                db,
                _user(),
                PROPOSAL_ID,
                1,
                2026,
                None,
            )

        self.assertEqual(context["rows"][0]["expediente"], "SNAPSHOT-501")
        self.assertEqual(context["rows"][0]["nombre"], "Snapshot Proposal Frozen")
        self.assertEqual(context["rows"][0]["genero"], "M")
        self.assertEqual(context["rows"][0]["column_values"], {71: 1})
        participant_sql = _sql(db.statements[2])
        self.assertIn("case when", participant_sql)
        self.assertIn("then proposal_participants.vca", participant_sql)
        self.assertIn("else participants.vca", participant_sql)
        self.assertNotIn("isnull", participant_sql)
        self.assertNotIn("coalesce", participant_sql)
        _assert_session_snapshot_join(self, db.statements[2])

    def test_adm_uses_snapshot_demographics_and_family(self):
        service_type = SimpleNamespace(
            adm_service_type_id=81,
            name="Service",
        )
        activity = SimpleNamespace(activity_code_id=ACTIVITY_CODE_ID)
        participant = _participant()
        proposal_participant = _proposal_participant()
        db = _Database(
            objects={(Proposal, PROPOSAL_ID): SimpleNamespace()},
            results=[
                _Result([service_type]),
                _Result([(SimpleNamespace(), activity, service_type)]),
                _Result([(SESSION_ID, ACTIVITY_CODE_ID)]),
                _Result([(SESSION_ID, participant.participant_id, ACTIVITY_CODE_ID)]),
                _Result([(participant, proposal_participant)]),
                _Result([]),
            ],
        )

        with _global_report_context():
            context = reports._build_adm_context(
                db,
                _user(),
                PROPOSAL_ID,
                1,
                2026,
                None,
            )

        self.assertEqual(
            context["sociodemographic_total"],
            {"f": 0, "m": 1, "total": 1, "vca": 1},
        )
        self.assertIn(
            {"label": "Snapshot family", "count": 1},
            context["family_rows"],
        )
        _assert_session_snapshot_join(self, db.statements[4])

    def test_report_table_summaries_join_and_use_proposal_snapshots(self):
        participant = _participant()
        proposal_participant = _proposal_participant()
        residential = SimpleNamespace(name="Residential")

        dropout_item = SimpleNamespace(
            current_grade="7",
            attended_tutoring=False,
            attended_school=False,
            report_10_weeks=False,
            report_20_weeks=False,
            report_30_weeks=False,
            report_40_weeks=False,
        )
        dropout_report = SimpleNamespace(
            proposal_id=PROPOSAL_ID,
            residential_id=9,
            report_year=2026,
            report_month=1,
            report_id=1,
        )
        pregnancy_item = SimpleNamespace(
            participated_workshops=True,
            is_pregnant=True,
        )
        pregnancy_report = SimpleNamespace(
            proposal_id=PROPOSAL_ID,
            residential_id=9,
            report_year=2026,
            report_month=1,
            report_id=2,
        )
        grade_item = SimpleNamespace(
            grade_level="7",
            is_content_room=False,
            average_grade=90,
            spanish_grade=90,
            english_grade=90,
            math_grade=90,
            science_grade=90,
        )
        grade_report = SimpleNamespace(
            proposal_id=PROPOSAL_ID,
            residential_id=9,
            report_year=2026,
            report_month=1,
            report_id=3,
        )

        cases = [
            (
                "dropout",
                reports._build_school_dropout_summary_context,
                dropout_item,
                dropout_report,
                "school_dropout_reports.proposal_id",
            ),
            (
                "pregnancy",
                reports._build_pregnancy_summary_context,
                pregnancy_item,
                pregnancy_report,
                "pregnancy_reports.proposal_id",
            ),
            (
                "notes",
                reports._build_notes_context,
                grade_item,
                grade_report,
                "school_grade_reports.proposal_id",
            ),
        ]

        for name, builder, item, report, report_proposal_column in cases:
            with self.subTest(report=name):
                db = _Database(results=[_Result([(
                    item,
                    report,
                    participant,
                    residential,
                    proposal_participant,
                )])])
                with _global_report_context():
                    context = builder(
                        db,
                        _user(),
                        PROPOSAL_ID,
                        1,
                        2026,
                        None,
                    )

                if name == "dropout":
                    self.assertEqual(context["total"]["m"], 1)
                    self.assertEqual(context["total"]["f"], 0)
                elif name == "pregnancy":
                    self.assertEqual(context["total"]["pregnant_m"], 1)
                    self.assertEqual(context["total"]["pregnant_f"], 0)
                else:
                    self.assertEqual(context["total_row"]["TOTAL"], 1)
                    age_row = next(
                        row
                        for row in context["rows"]
                        if row["age_label"] == "11 - 15 años"
                    )
                    self.assertEqual(age_row["TOTAL"], 1)

                sql = _sql(db.statements[0])
                self.assertIn(
                    "persons.legacy_participant_id = participants.participant_id",
                    sql,
                )
                self.assertIn(
                    "proposal_participants.person_id = persons.person_id",
                    sql,
                )
                self.assertIn(
                    f"proposal_participants.proposal_id = {report_proposal_column}",
                    sql,
                )

    def test_no_duplicado_and_duplicado_use_snapshots_with_proposal(self):
        participant = _participant()
        proposal_participant = _proposal_participant()

        no_duplicate_db = _Database(
            results=[_Result([(participant, proposal_participant)])]
        )
        duplicated_db = _Database(
            results=[_Result([
                (SimpleNamespace(), participant, proposal_participant),
                (SimpleNamespace(), participant, proposal_participant),
            ])]
        )

        with _global_report_context():
            no_duplicate = reports._calculate_no_duplicado_metric(
                no_duplicate_db,
                _user(),
                PROPOSAL_ID,
                1,
                2026,
                None,
                duplicated=False,
            )
            duplicated = reports._calculate_no_duplicado_metric(
                duplicated_db,
                _user(),
                PROPOSAL_ID,
                1,
                2026,
                None,
                duplicated=True,
            )

        self.assertEqual(no_duplicate["total_f"], 0)
        self.assertEqual(no_duplicate["total_m"], 1)
        self.assertEqual(duplicated["total_f"], 0)
        self.assertEqual(duplicated["total_m"], 2)
        _assert_session_snapshot_join(self, no_duplicate_db.statements[0])
        _assert_session_snapshot_join(self, duplicated_db.statements[0])

    def test_no_duplicado_without_proposal_uses_participant_and_deduplicates_id(self):
        first = _participant(participant_id=1, genero="F", fecha_nacimiento=_dob(12))
        second = _participant(participant_id=2, genero="M", fecha_nacimiento=_dob(12))
        db = _Database(results=[_Result([first, first, second])])

        with _global_report_context():
            context = reports._calculate_no_duplicado_metric(
                db,
                _user(),
                None,
                None,
                None,
                None,
                duplicated=False,
                period_type="custom",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 31),
            )

        self.assertEqual(context["total_all"], 2)
        self.assertEqual(context["total_f"], 1)
        self.assertEqual(context["total_m"], 1)
        self.assertNotIn("proposal_participants", _sql(db.statements[0]))

    def test_por_programa_uses_snapshot_demographics(self):
        program = SimpleNamespace(program_id=91, code="P1", name="Program")
        participant = _participant()
        proposal_participant = _proposal_participant()
        db = _Database(results=[
            _Result([program]),
            _Result([(participant, proposal_participant)]),
        ])

        with (
            _global_report_context(),
            patch.object(
                reports,
                "_resolve_reporting_location",
                return_value={
                    "residential_name": "Global",
                    "municipality": "Todos",
                    "rq_code": "",
                },
            ),
            patch.object(
                reports,
                "_resolve_effective_program_activity_code_ids",
                return_value={ACTIVITY_CODE_ID},
            ),
            patch.object(
                reports,
                "_program_report_display_name",
                return_value="Program",
            ),
        ):
            context = reports._build_por_programa_context(
                db,
                _user(),
                PROPOSAL_ID,
                1,
                2026,
                None,
            )

        section = context["program_sections"][0]
        self.assertEqual(section["total_f"], 0)
        self.assertEqual(section["total_m"], 1)
        self.assertEqual(section["total_all"], 1)
        _assert_session_snapshot_join(self, db.statements[1])


if __name__ == "__main__":
    unittest.main()
