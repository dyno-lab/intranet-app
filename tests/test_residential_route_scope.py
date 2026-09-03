from __future__ import annotations

import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

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

    def scalar_one(self):
        return self.scalar_value

    def one(self):
        if self.scalar_value is not None:
            return self.scalar_value
        if len(self.values) != 1:
            raise AssertionError("Expected exactly one result row")
        return self.values[0]


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


class ParticipantExpedienteBackendTests(unittest.TestCase):
    def test_return_query_is_whitelisted_normalized_and_uses_fixed_path(self):
        return_query = (
            "page=-3&per_page=25&age_range=8_10&age_min=20&age_max=10"
            "&expediente_num=%20fe-2026-ac-0001%20&residential_id=7"
            "&next=https%3A%2F%2Fevil.example&return_url=%2F%2Fevil.example"
        )

        normalized = ui._normalize_new_list_return_query(return_query)
        normalized_params = parse_qs(normalized)

        self.assertEqual(
            normalized_params,
            {
                "page": ["1"],
                "per_page": ["25"],
                "age_range": ["8_10"],
                "age_min": ["10"],
                "age_max": ["20"],
                "expediente_num": ["FE-2026-AC-0001"],
                "residential_id": ["7"],
            },
        )
        self.assertEqual(
            ui._build_new_list_url(return_query),
            f"/ui/new-list?{normalized}",
        )
        self.assertNotIn("evil.example", ui._build_new_list_url(return_query))

    def test_new_list_expediente_link_preserves_filters_and_current_page(self):
        participant = SimpleNamespace(
            participant_id=2141,
            fecha_nacimiento=date(2016, 5, 10),
            is_active=True,
            is_head_of_household=False,
        )
        db = _Database(
            objects={(Residential, 7): _residential(7, "AC")},
            results=[
                _Result(scalar=51),
                _Result(values=[participant]),
            ],
        )
        dashboard = {
            "totals": {
                "registered_count": 0,
                "assigned_count": 0,
                "pending_sync_count": 0,
            },
            "residential_rows": [],
            "show_residential_breakdown": False,
        }

        with (
            patch.object(ui, "_build_new_list_dashboard", return_value=dashboard),
            patch.object(ui, "load_profile_field_presence_by_participants", return_value={}),
            patch.object(ui, "_participant_form_catalogs", return_value={}),
            patch.object(ui, "_participant_profile_context", return_value={}),
            patch.object(
                ui.templates,
                "TemplateResponse",
                side_effect=lambda _template, context: context,
            ),
        ):
            context = ui.new_list(
                request=_Request(7),
                page=3,
                per_page=25,
                age_range="8_10",
                age_min=None,
                age_max=None,
                expediente_num=" fe-2026-ac-0001 ",
                residential_id=None,
                db=db,
                current_user=_privileged_user(active_residential_id=7),
            )

        expediente_url = context["rows"][0]["expediente_url"]
        parsed_url = urlsplit(expediente_url)
        nested_return_query = parse_qs(parsed_url.query)["return_query"][0]

        self.assertEqual(
            parsed_url.path,
            f"/ui/new-list/{participant.participant_id}/expediente",
        )
        self.assertEqual(
            parse_qs(nested_return_query),
            {
                "page": ["3"],
                "per_page": ["25"],
                "age_range": ["8_10"],
                "age_min": ["8"],
                "age_max": ["10"],
                "expediente_num": ["FE-2026-AC-0001"],
            },
        )
        self.assertEqual(context["new_list_return_query"], nested_return_query)

    def test_proposal_and_attendance_statements_apply_residential_scope(self):
        formal_stmt = ui._build_participant_formal_proposals_stmt(
            person_id=41,
            scoped_residential_id=7,
        )
        historical_stmt = ui._build_participant_historical_proposals_stmt(
            participant_id=2141,
            person_id=41,
            scoped_residential_id=7,
        )
        participation_stmt = ui._build_participant_participation_stmt(
            participant_id=2141,
            person_id=41,
            scoped_residential_id=7,
        )

        formal_sql = str(formal_stmt)
        historical_sql = str(historical_stmt)
        participation_sql = str(participation_stmt)

        self.assertIn("proposal_participants.residential_id =", formal_sql)
        for statement, statement_sql in (
            (historical_stmt, historical_sql),
            (participation_stmt, participation_sql),
        ):
            self.assertIn("activity_sessions.residential_id =", statement_sql)
            self.assertIn("proposal_participants.residential_id =", statement_sql)
            self.assertIn("attendance.participant_id =", statement_sql)
            self.assertIn("proposal_participants.person_id =", statement_sql)
            self.assertIn(7, statement.compile().params.values())
        self.assertIn(7, formal_stmt.compile().params.values())

    def test_participation_filters_pagination_and_order_are_deterministic(self):
        statement = ui._apply_participant_participation_filters(
            ui._build_participant_participation_stmt(
                participant_id=2141,
                person_id=41,
                scoped_residential_id=7,
            ),
            date(2026, 1, 1),
            date(2026, 2, 28),
            12,
            "salud",
        )
        statement_sql = str(statement)
        order_by_sql = statement_sql.split("ORDER BY", 1)[1].replace("\n", " ").strip()
        statement_values = statement.compile().params.values()

        self.assertIn("activity_sessions.session_date >=", statement_sql)
        self.assertIn("activity_sessions.session_date <=", statement_sql)
        self.assertIn("activity_sessions.proposal_id =", statement_sql)
        self.assertIn("activity_codes.code", statement_sql)
        self.assertIn("activity_codes.description", statement_sql)
        self.assertIn("%salud%", statement_values)
        self.assertIn(12, statement_values)
        self.assertTrue(
            order_by_sql.startswith(
                "activity_sessions.session_date DESC, "
                "activity_sessions.session_id DESC, attendance.attendance_id DESC"
            )
        )
        self.assertEqual(
            ui._paginate(total_items=61, page=99, per_page=25),
            {
                "page": 3,
                "per_page": 25,
                "total_items": 61,
                "total_pages": 3,
                "offset": 50,
                "has_prev": True,
                "has_next": False,
                "prev_page": 2,
                "next_page": None,
            },
        )
        self.assertIsNone(ui._parse_optional_filter_date("not-a-date"))

    def test_participation_chart_sql_aggregates_months_with_filters_and_scope(self):
        statement = ui._build_participant_participation_chart_stmt(
            participant_id=2141,
            person_id=41,
            scoped_residential_id=7,
            period_start=date(2025, 11, 1),
            period_end=date(2026, 2, 20),
            proposal_id=12,
            activity="salud",
        )
        statement_sql = " ".join(str(statement).split())
        statement_values = statement.compile().params.values()

        self.assertIn(
            "SELECT year(activity_sessions.session_date) AS year, "
            "month(activity_sessions.session_date) AS month, "
            "count(attendance.attendance_id) AS value",
            statement_sql,
        )
        self.assertIn("LEFT OUTER JOIN proposal_participants", statement_sql)
        self.assertIn("JOIN activity_sessions", statement_sql)
        self.assertIn("JOIN activity_codes", statement_sql)
        self.assertIn("attendance.attended = true", statement_sql)
        self.assertIn("attendance.participant_id =", statement_sql)
        self.assertIn("proposal_participants.person_id =", statement_sql)
        self.assertIn("activity_sessions.residential_id =", statement_sql)
        self.assertIn("proposal_participants.residential_id =", statement_sql)
        self.assertIn("activity_sessions.session_date >=", statement_sql)
        self.assertIn("activity_sessions.session_date <=", statement_sql)
        self.assertIn("activity_sessions.proposal_id =", statement_sql)
        self.assertIn("activity_codes.code", statement_sql)
        self.assertIn("activity_codes.description", statement_sql)
        self.assertIn(
            "GROUP BY year(activity_sessions.session_date), "
            "month(activity_sessions.session_date)",
            statement_sql,
        )
        self.assertNotIn(" LIMIT ", f" {statement_sql} ")
        self.assertNotIn(" OFFSET ", f" {statement_sql} ")
        for expected_value in (
            2141,
            41,
            7,
            date(2025, 11, 1),
            date(2026, 2, 20),
            12,
            "%salud%",
        ):
            self.assertIn(expected_value, statement_values)

    def test_participation_chart_crosses_years_and_fills_zero_months(self):
        period_start, period_end = ui._participant_participation_chart_period(
            date(2025, 11, 15),
            date(2026, 2, 20),
        )

        context = ui._build_participation_chart_context(
            [
                SimpleNamespace(year=2025, month=12, value=2),
                SimpleNamespace(year=2026, month=2, value=4),
            ],
            period_start,
            period_end,
        )

        self.assertEqual(period_start, date(2025, 11, 1))
        self.assertEqual(period_end, date(2026, 2, 20))
        self.assertEqual(
            context["participation_chart_rows"],
            [
                {
                    "year": 2025,
                    "month": 11,
                    "label": "Nov 2025",
                    "value": 0,
                    "percentage": 0,
                },
                {
                    "year": 2025,
                    "month": 12,
                    "label": "Dic 2025",
                    "value": 2,
                    "percentage": 50,
                },
                {
                    "year": 2026,
                    "month": 1,
                    "label": "Ene 2026",
                    "value": 0,
                    "percentage": 0,
                },
                {
                    "year": 2026,
                    "month": 2,
                    "label": "Feb 2026",
                    "value": 4,
                    "percentage": 100,
                },
            ],
        )
        self.assertEqual(context["participation_chart_total"], 6)
        self.assertEqual(
            context["participation_chart_period_label"],
            "Nov 2025 – Feb 2026",
        )
        self.assertTrue(context["participation_chart_has_data"])

        maximum_period_start, maximum_period_end = (
            ui._participant_participation_chart_period(
                date(2020, 1, 1),
                date(2026, 2, 20),
            )
        )
        empty_context = ui._build_participation_chart_context(
            [],
            maximum_period_start,
            maximum_period_end,
        )
        self.assertEqual(maximum_period_start, date(2025, 3, 1))
        self.assertEqual(len(empty_context["participation_chart_rows"]), 12)
        self.assertEqual(empty_context["participation_chart_total"], 0)
        self.assertFalse(empty_context["participation_chart_has_data"])
        self.assertTrue(all(
            row["value"] == 0 and row["percentage"] == 0
            for row in empty_context["participation_chart_rows"]
        ))

    def test_expediente_context_filters_rows_and_returns_complete_urls(self):
        participant = SimpleNamespace(
            participant_id=2141,
            residential_id=7,
            fecha_nacimiento=date(1990, 1, 2),
            is_active=True,
            is_head_of_household=False,
        )
        residential = _residential(7, "AC")
        person = SimpleNamespace(person_id=41)
        formal_proposal = SimpleNamespace(proposal_id=12, code="P-12", name="Formal")
        historical_proposal = SimpleNamespace(proposal_id=15, code="P-15", name="Histórica")
        proposal_participant = SimpleNamespace(
            proposal_participant_id=71,
            proposal_id=12,
        )
        direct_attendance = SimpleNamespace(
            attendance_id=501,
            proposal_participant_id=None,
        )
        proposal_attendance = SimpleNamespace(
            attendance_id=500,
            proposal_participant_id=71,
        )
        newest_session = SimpleNamespace(
            session_id=91,
            session_date=date(2026, 2, 20),
        )
        older_session = SimpleNamespace(
            session_id=90,
            session_date=date(2026, 2, 19),
        )
        activity_code = SimpleNamespace(code="1.1", description="Salud preventiva")
        employee = SimpleNamespace(full_name="Ada Rivera")
        metrics = SimpleNamespace(
            participation_total=88,
            last_participation_date=date(2026, 2, 20),
        )
        db = _Database(
            results=[
                _Result(scalar=participant),
                _Result(scalar=residential),
                _Result(scalar=person),
                _Result(values=[(proposal_participant, formal_proposal)]),
                _Result(values=[formal_proposal, historical_proposal]),
                _Result(scalar=61),
                _Result(
                    values=[
                        (
                            direct_attendance,
                            newest_session,
                            activity_code,
                            employee,
                            formal_proposal,
                            None,
                        ),
                        (
                            proposal_attendance,
                            older_session,
                            activity_code,
                            employee,
                            formal_proposal,
                            proposal_participant,
                        ),
                    ]
                ),
                _Result(scalar=metrics),
                _Result(
                    values=[
                        SimpleNamespace(year=2026, month=1, value=2),
                        SimpleNamespace(year=2026, month=2, value=3),
                    ]
                ),
            ]
        )

        with (
            patch.object(ui, "load_all_profile_fields", return_value=[]),
            patch.object(ui, "load_participant_profile_values", return_value={}),
            patch.object(
                ui.templates,
                "TemplateResponse",
                side_effect=lambda _template, context: context,
            ),
        ):
            context = ui.participant_expediente(
                participant_id=participant.participant_id,
                request=_Request(7),
                return_query="page=2&age_min=9&redirect=https%3A%2F%2Fevil.example",
                participation_page=99,
                participation_from_date="2026-02-28",
                participation_to_date="2026-01-01",
                participation_proposal_id="12",
                participation_activity=" salud ",
                db=db,
                current_user=_privileged_user(active_residential_id=7),
            )

        self.assertIs(context["participant_residential"], residential)
        self.assertEqual(context["back_to_list_url"], "/ui/new-list?page=2&age_min=9")
        self.assertEqual(context["proposal_count"], 2)
        self.assertEqual(context["participation_total"], 88)
        self.assertEqual(context["last_participation_date"], date(2026, 2, 20))
        self.assertEqual(context["participation_pagination"]["page"], 3)
        self.assertEqual(
            context["participation_chart_rows"],
            [
                {
                    "year": 2026,
                    "month": 1,
                    "label": "Ene",
                    "value": 2,
                    "percentage": 67,
                },
                {
                    "year": 2026,
                    "month": 2,
                    "label": "Feb",
                    "value": 3,
                    "percentage": 100,
                },
            ],
        )
        self.assertEqual(context["participation_chart_total"], 5)
        self.assertEqual(context["participation_chart_period_label"], "Ene 2026 – Feb 2026")
        self.assertTrue(context["participation_chart_has_data"])
        self.assertIsNotNone(db.statements[6]._limit_clause)
        self.assertIsNotNone(db.statements[6]._offset_clause)
        self.assertIsNone(db.statements[8]._limit_clause)
        self.assertIsNone(db.statements[8]._offset_clause)
        self.assertEqual(
            context["participation_filters"],
            {
                "from_date": "2026-01-01",
                "to_date": "2026-02-28",
                "proposal_id": "12",
                "activity": "salud",
            },
        )
        self.assertEqual(
            [row["source"] for row in context["participation_rows"]],
            ["New-list directo", "Propuesta"],
        )
        self.assertEqual(
            context["participation_rows"][0]["session_url"],
            "/ui/listado/91",
        )

        first_params = parse_qs(urlsplit(context["participation_first_url"]).query)
        self.assertEqual(first_params["return_query"], ["page=2&age_min=9"])
        self.assertEqual(first_params["participation_from_date"], ["2026-01-01"])
        self.assertEqual(first_params["participation_to_date"], ["2026-02-28"])
        self.assertEqual(first_params["participation_proposal_id"], ["12"])
        self.assertEqual(first_params["participation_activity"], ["salud"])
        self.assertEqual(first_params["participation_page"], ["1"])
        self.assertEqual(
            parse_qs(urlsplit(context["participation_clear_url"]).query),
            {"return_query": ["page=2&age_min=9"]},
        )

    def test_historical_profile_fields_require_a_nonempty_value(self):
        active_empty = SimpleNamespace(
            participant_profile_field_id=1,
            is_active=True,
            applies_to_new_list=True,
        )
        historical_empty = SimpleNamespace(
            participant_profile_field_id=2,
            is_active=False,
            applies_to_new_list=True,
        )
        historical_value = SimpleNamespace(
            participant_profile_field_id=3,
            is_active=False,
            applies_to_new_list=True,
        )

        context = ui._build_expediente_profile_context(
            [active_empty, historical_empty, historical_value],
            {1: "", 2: "   ", 3: "teléfono anterior"},
        )

        self.assertEqual(
            [item["field"].participant_profile_field_id for item in context["profile_items"]],
            [1, 3],
        )
        self.assertFalse(context["profile_items"][0]["is_historical"])
        self.assertFalse(context["profile_items"][0]["has_value"])
        self.assertTrue(context["profile_items"][1]["is_historical"])
        self.assertTrue(context["profile_items"][1]["has_value"])
        self.assertEqual(context["missing_profile_fields"], [active_empty])
        self.assertEqual(context["missing_profile_count"], 1)


class ParticipantGenderValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_requires_participant_gender(self):
        residential = _residential(1, "AC")
        db = _Database(objects={(Residential, 1): residential})

        response = await ui.create_participant(
            residential_id=1,
            nombre="Ana",
            apellido_paterno="Pérez",
            genero=None,
            request=_Request(1),
            db=db,
            current_user=_privileged_user(active_residential_id=1),
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("sexo", response.headers["location"])
        self.assertEqual(db.statements, [])
        self.assertEqual(db.added, [])
        self.assertEqual(db.commits, 0)

    async def test_edit_requires_participant_gender(self):
        residential = _residential(1, "AC")
        participant = SimpleNamespace(
            participant_id=366,
            residential_id=1,
            created_by_user_id=27,
        )
        db = _Database(
            objects={(Residential, 1): residential},
            results=[_Result(scalar=participant)],
        )

        response = await ui.edit_participant_save(
            participant_id=participant.participant_id,
            nombre="Ana",
            apellido_paterno="Pérez",
            genero=None,
            request=_Request(1),
            db=db,
            current_user=_privileged_user(active_residential_id=1),
        )

        self.assertEqual(response.status_code, 303)
        self.assertIn("sexo", response.headers["location"])
        self.assertEqual(len(db.statements), 1)
        self.assertEqual(db.commits, 0)


class ParticipantDeletionTests(unittest.TestCase):
    def test_delete_removes_only_empty_profile_rows_before_participant(self):
        participant = SimpleNamespace(
            participant_id=2141,
            residential_id=1,
            created_by_user_id=90,
        )
        db = _Database(
            objects={(Participant, participant.participant_id): participant},
            results=[_Result() for _ in range(8)],
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
        self.assertEqual(len(statements), 8)
        for statement in statements[:5]:
            self.assertTrue(statement.lstrip().startswith("SELECT"))
        self.assertIn("DELETE FROM participant_profile_field_values", statements[5])
        self.assertIn("participant_profile_field_values.value IS NULL", statements[5])
        self.assertIn("ltrim(rtrim(participant_profile_field_values.value)) =", statements[5])
        self.assertIn("SELECT participant_profile_field_values", statements[6])
        self.assertIn("DELETE FROM participants", statements[7])
        for statement in db.statements:
            self.assertIn(
                participant.participant_id,
                statement.compile().params.values(),
            )

    def test_delete_blocks_attendance_without_cleaning_profile_rows(self):
        participant = SimpleNamespace(
            participant_id=2141,
            residential_id=1,
            created_by_user_id=90,
        )
        db = _Database(
            objects={(Participant, participant.participant_id): participant},
            results=[_Result(scalar=31), *[_Result() for _ in range(4)]],
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
        self.assertEqual(len(db.statements), 5)
        self.assertTrue(all(
            str(statement).lstrip().startswith("SELECT")
            for statement in db.statements
        ))
        self.assertIn("asistencias", response.headers["location"])

    def test_delete_rolls_back_cleanup_when_nonempty_profile_value_remains(self):
        participant = SimpleNamespace(
            participant_id=2141,
            residential_id=1,
            created_by_user_id=90,
        )
        db = _Database(
            objects={(Participant, participant.participant_id): participant},
            results=[
                *[_Result() for _ in range(6)],
                _Result(scalar=27),
            ],
        )

        response = ui.delete_participant(
            participant_id=participant.participant_id,
            request=_Request(),
            db=db,
            current_user=_privileged_user(),
        )

        statements = [str(statement) for statement in db.statements]
        self.assertEqual(response.status_code, 303)
        self.assertEqual(db.commits, 0)
        self.assertEqual(db.rollbacks, 1)
        self.assertEqual(len(statements), 7)
        for statement in statements[:5]:
            self.assertTrue(statement.lstrip().startswith("SELECT"))
        self.assertIn("DELETE FROM participant_profile_field_values", statements[5])
        self.assertTrue(statements[6].lstrip().startswith("SELECT"))
        self.assertFalse(any(
            "DELETE FROM participants" in statement
            for statement in statements
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
            results=[*[_Result() for _ in range(7)], integrity_error],
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
