from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from starlette.datastructures import FormData


os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import participants, pregnancy, school_dropout, school_grades, sessions, ui  # noqa: E402
from app.core.proposal_guard import FINALIZED_STATUS  # noqa: E402
from app.core.residential_scope import ACTIVE_RESIDENTIAL_SESSION_KEY  # noqa: E402
from app.helpers.report_context import base_reports_context  # noqa: E402
from app.models.activity_session import ActivitySession  # noqa: E402
from app.models.participant import Participant  # noqa: E402
from app.models.proposal import Proposal  # noqa: E402
from app.models.residential import Residential  # noqa: E402


class _Request:
    def __init__(self, residential_id: int | None = None, form_data=None):
        self.session = {}
        self._form_data = FormData(form_data or {})
        if residential_id is not None:
            self.session[ACTIVE_RESIDENTIAL_SESSION_KEY] = residential_id

    async def form(self):
        return self._form_data


class _Result:
    def __init__(self, values=None, scalar=None):
        self.values = list(values or [])
        self.scalar_value = scalar

    def scalars(self):
        return self

    def all(self):
        return self.values

    def scalar_one_or_none(self):
        return self.scalar_value


class _Database:
    def __init__(self, *, objects=None, results=None):
        self.objects = objects or {}
        self.results = list(results or [])
        self.statements = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, object_id):
        return self.objects.get((model, object_id))

    def execute(self, statement):
        self.statements.append(statement)
        if not self.results:
            raise AssertionError("Unexpected database query")
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def add(self, value):
        self.added.append(value)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def _privileged_user(*, active_residential_id: int | None = None):
    user = SimpleNamespace(user_id=90, role="admin", residential_id=None)
    if active_residential_id is not None:
        setattr(user, "_active_residential_id", active_residential_id)
    return user


def _residential(residential_id: int, code: str) -> Residential:
    residential = Residential(
        code=code,
        name=f"Residencial {code}",
        municipality="Ponce",
        rq_code=f"RQ-{code}",
        is_active=True,
    )
    residential.residential_id = residential_id
    return residential


class ResidentialRouteScopeTests(unittest.TestCase):
    def test_api_lists_filter_by_active_residential(self):
        user = _privileged_user(active_residential_id=7)
        request = _Request(7)

        participant_db = _Database(results=[_Result()])
        participants.list_participants(
            request=request,
            db=participant_db,
            current_user=user,
        )
        participant_statement = participant_db.statements[0]
        self.assertIn("WHERE participants.residential_id", str(participant_statement))
        self.assertIn(7, participant_statement.compile().params.values())

        session_db = _Database(results=[_Result()])
        sessions.list_sessions(
            request=request,
            db=session_db,
            current_user=user,
        )
        session_statement = session_db.statements[0]
        self.assertIn("WHERE activity_sessions.residential_id", str(session_statement))
        self.assertIn(7, session_statement.compile().params.values())

    def test_api_lists_remain_global_in_general_mode(self):
        user = _privileged_user()
        request = _Request()

        participant_db = _Database(results=[_Result()])
        participants.list_participants(
            request=request,
            db=participant_db,
            current_user=user,
        )
        self.assertNotIn(" WHERE ", f" {str(participant_db.statements[0]).upper()} ")

        session_db = _Database(results=[_Result()])
        sessions.list_sessions(
            request=request,
            db=session_db,
            current_user=user,
        )
        self.assertNotIn(" WHERE ", f" {str(session_db.statements[0]).upper()} ")

    def test_participant_and_session_details_reject_other_residential(self):
        user = _privileged_user(active_residential_id=1)
        request = _Request(1)
        participant = SimpleNamespace(
            participant_id=10,
            residential_id=2,
            created_by_user_id=user.user_id,
        )
        participant_db = _Database(results=[_Result(scalar=participant)])

        with self.assertRaises(HTTPException) as participant_error:
            ui.participant_expediente(
                participant_id=participant.participant_id,
                request=request,
                db=participant_db,
                current_user=user,
            )
        self.assertEqual(participant_error.exception.status_code, 403)

        session = SimpleNamespace(
            session_id=20,
            residential_id=2,
            created_by_user_id=user.user_id,
        )
        session_db = _Database(objects={(ActivitySession, session.session_id): session})

        with self.assertRaises(HTTPException) as session_error:
            ui.open_session(
                session_id=session.session_id,
                request=request,
                db=session_db,
                current_user=user,
            )
        self.assertEqual(session_error.exception.status_code, 403)

    def test_creator_does_not_grant_access_to_unowned_records(self):
        user = _privileged_user(active_residential_id=1)
        request = _Request(1)
        unowned_record = SimpleNamespace(
            residential_id=None,
            created_by_user_id=user.user_id,
        )

        access_checks = (
            ui._check_participant_access,
            ui._check_session_access,
            school_grades._ensure_report_access,
            school_dropout._ensure_report_access,
            pregnancy._ensure_report_access,
        )
        for access_check in access_checks:
            with self.subTest(access_check=access_check.__module__ + "." + access_check.__name__):
                with self.assertRaises(HTTPException) as context:
                    if access_check in {ui._check_participant_access, ui._check_session_access}:
                        access_check(unowned_record, user, request)
                    else:
                        access_check(request, user, unowned_record)
                self.assertEqual(context.exception.status_code, 403)

    def test_global_school_report_creation_redirects_to_residential_mode(self):
        proposal = SimpleNamespace(
            proposal_id=3,
            status="active",
            locked_through_month=None,
            locked_through_year=None,
        )
        current_month = date.today().month
        current_year = date.today().year
        user = _privileged_user()

        routes = (
            (school_grades.create_school_grade_report, "/ui/school-grades"),
            (school_dropout.create_school_dropout_report, "/ui/school-dropout"),
            (pregnancy.create_pregnancy_report, "/ui/pregnancy"),
        )
        for create_report, expected_path in routes:
            with self.subTest(route=create_report.__module__):
                db = _Database(objects={(Proposal, proposal.proposal_id): proposal})
                response = create_report(
                    request=_Request(),
                    proposal_id=proposal.proposal_id,
                    report_month=current_month,
                    report_year=current_year,
                    notes=None,
                    db=db,
                    current_user=user,
                )
                self.assertEqual(response.status_code, 303)
                self.assertTrue(response.headers["location"].startswith(expected_path))
                self.assertIn("Entre%20bajo%20un%20residencial", response.headers["location"])
                self.assertEqual(db.statements, [])

    def test_report_selector_only_exposes_active_residential(self):
        active_residential = _residential(7, "AC")
        user = _privileged_user(active_residential_id=7)
        db = _Database(
            objects={(Residential, 7): active_residential},
            results=[_Result(), _Result(values=[active_residential])],
        )

        context = base_reports_context(db, user, [(1, "Enero")])

        residential_statement = db.statements[1]
        self.assertIn("residentials.residential_id", str(residential_statement))
        self.assertIn(7, residential_statement.compile().params.values())
        self.assertEqual(
            [option.residential_id for option in context["report_residentials"]],
            [7],
        )
        self.assertEqual(
            [option.residential_id for option in context["report_users"]],
            [7],
        )

    def test_listado_hides_finalized_proposals_until_filtered(self):
        user = _privileged_user()
        default_statement = ui._apply_session_proposal_visibility(
            ui._build_sessions_stmt(user),
            None,
        )
        default_sql = str(default_statement)

        self.assertIn("proposals.status !=", default_sql)
        self.assertIn(FINALIZED_STATUS, default_statement.compile().params.values())

        filtered_statement = ui._apply_session_filters(
            ui._build_sessions_stmt(user),
            None,
            None,
            13,
            None,
            None,
        )
        filtered_statement = ui._apply_session_proposal_visibility(
            filtered_statement,
            13,
        )
        filtered_sql = str(filtered_statement)

        self.assertIn("activity_sessions.proposal_id =", filtered_sql)
        self.assertNotIn("proposals.status !=", filtered_sql)
        self.assertIn(13, filtered_statement.compile().params.values())

    def test_listado_metrics_use_same_finalized_proposal_visibility(self):
        user = _privileged_user()
        default_statement = ui._build_filtered_session_ids_stmt(
            current_user=user,
            fd=None,
            td=None,
            proposal_id_int=None,
            month_int=None,
            year_int=None,
        )
        default_sql = str(default_statement)

        self.assertIn("LEFT OUTER JOIN proposals", default_sql)
        self.assertIn("proposals.status !=", default_sql)
        self.assertIn(FINALIZED_STATUS, default_statement.compile().params.values())

        filtered_statement = ui._build_filtered_session_ids_stmt(
            current_user=user,
            fd=None,
            td=None,
            proposal_id_int=13,
            month_int=None,
            year_int=None,
        )
        filtered_sql = str(filtered_statement)

        self.assertIn("activity_sessions.proposal_id =", filtered_sql)
        self.assertNotIn("proposals.status !=", filtered_sql)

    def test_listado_orders_sessions_from_newest_to_oldest(self):
        statement_sql = str(ui._build_sessions_stmt(_privileged_user()))
        order_by_sql = statement_sql.split("ORDER BY", 1)[1].replace("\n", " ").strip()

        self.assertTrue(
            order_by_sql.startswith(
                "activity_sessions.session_date DESC, activity_sessions.session_id DESC"
            )
        )
        self.assertNotIn("proposals.code ASC", order_by_sql)


class ParticipantDeletionTests(unittest.TestCase):
    def test_delete_only_removes_unreferenced_participant(self):
        participant = SimpleNamespace(
            participant_id=2141,
            residential_id=1,
            created_by_user_id=90,
        )
        db = _Database(
            objects={(Participant, participant.participant_id): participant},
            results=[_Result() for _ in range(7)],
        )

        response = ui.delete_participant(
            participant_id=participant.participant_id,
            request=_Request(),
            db=db,
            current_user=_privileged_user(),
        )

        statements = [str(statement) for statement in db.statements]
        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(statements), 7)
        for statement in statements[:6]:
            self.assertTrue(statement.lstrip().startswith("SELECT"))
        self.assertIn("DELETE FROM participants", statements[6])
        for statement in db.statements:
            self.assertIn(
                participant.participant_id,
                statement.compile().params.values(),
            )

    def test_delete_blocks_profile_references_without_modifying_data(self):
        participant = SimpleNamespace(
            participant_id=2141,
            residential_id=1,
            created_by_user_id=90,
        )
        db = _Database(
            objects={(Participant, participant.participant_id): participant},
            results=[
                _Result(),
                _Result(scalar=27),
                _Result(),
                _Result(),
                _Result(),
                _Result(),
            ],
        )

        response = ui.delete_participant(
            participant_id=participant.participant_id,
            request=_Request(),
            db=db,
            current_user=_privileged_user(),
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.rollbacks, 0)
        self.assertEqual(len(db.statements), 6)
        self.assertTrue(all(
            str(statement).lstrip().startswith("SELECT")
            for statement in db.statements
        ))
        self.assertIn("modo%20seguridad", response.headers["location"])
        self.assertIn("campos%20adicionales", response.headers["location"])

    def test_delete_rolls_back_an_unexpected_related_record(self):
        participant = SimpleNamespace(
            participant_id=2141,
            residential_id=1,
            created_by_user_id=90,
        )
        integrity_error = IntegrityError(
            "DELETE FROM participants",
            {"participant_id": participant.participant_id},
            Exception("foreign key conflict"),
        )
        db = _Database(
            objects={(Participant, participant.participant_id): participant},
            results=[*[_Result() for _ in range(6)], integrity_error],
        )

        response = ui.delete_participant(
            participant_id=participant.participant_id,
            request=_Request(),
            db=db,
            current_user=_privileged_user(),
        )

        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.rollbacks, 1)
        self.assertIn("no%20pudo%20eliminarse", response.headers["location"])


class ParticipantEditPersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def test_edit_uses_explicit_update_without_dirtying_participant(self):
        residential = _residential(1, "AC")
        participant = SimpleNamespace(
            participant_id=366,
            residential_id=1,
            created_by_user_id=27,
            nombre="Nombre anterior",
        )
        db = _Database(
            objects={(Residential, 1): residential},
            results=[
                _Result(scalar=participant),
                _Result(),
                _Result(),
                _Result(),
            ],
        )
        user = _privileged_user(active_residential_id=1)

        with (
            patch.object(ui.settings, "PHASE2_EXPEDIENTE_ENABLED", True),
            patch.object(ui, "load_active_new_list_fields", return_value=[]),
            patch.object(ui, "save_profile_field_values") as save_profile_values,
        ):
            response = await ui.edit_participant_save(
                participant_id=participant.participant_id,
                expediente_num=None,
                exp_year=2026,
                exp_employee_initials=None,
                exp_seq4="0042",
                nombre="Ana",
                inicial="M",
                apellido_paterno="Pérez",
                apellido_materno="Rivera",
                fecha_nacimiento="1990-01-02",
                genero="F",
                edificio="A",
                apart="101",
                estatus="Activo",
                vca="SI",
                primera_vez="NO",
                escolaridad_participante="Universidad",
                composicion_familiar="Familiar",
                grupo_familiar="2",
                relacion_familiar="Jefa",
                fuente_ingreso_principal="Empleo",
                rango_ingreso="1",
                is_head_of_household=None,
                request=_Request(1),
                db=db,
                current_user=user,
            )

        update_statement = db.statements[3]
        update_sql = str(update_statement)
        update_values = update_statement.compile().params.values()

        self.assertEqual(response.status_code, 303)
        self.assertIn("UPDATE participants SET", update_sql)
        self.assertIn("participants.participant_id =", update_sql)
        self.assertIn("FE-2026-AC-0042", update_values)
        self.assertIn("Ana", update_values)
        self.assertIn(366, update_values)
        self.assertEqual(participant.nombre, "Nombre anterior")
        self.assertEqual(db.added, [])
        self.assertEqual(db.commits, 1)
        save_profile_values.assert_called_once_with(db, participant, [], {})


if __name__ == "__main__":
    unittest.main()
