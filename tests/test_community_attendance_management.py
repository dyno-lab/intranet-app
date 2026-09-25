from datetime import date
import csv
import io
import json
import re
import unittest
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.dialects import mssql

from tests import test_community_operations as fixtures
from app.api.deps import get_db
from app.api.routes import community_operations
from app.core.config import settings
from app.models.community import CPUserAccess, CPParticipant
from app.models.community_fiscal import CPFiscalParticipant
from app.models.community_operations import CPActivitySession, CPAttendance
from app.services.community_operations import set_session_attendance
from app.services.community_fiscal import set_fiscal_status, discharge_participant
from app.services import community_attendance as attendance


class AttendanceManagementTests(unittest.TestCase):
    setUp = fixtures.CommunityOperationTests.setUp
    tearDown = fixtures.CommunityOperationTests.tearDown
    new_participant = fixtures.CommunityOperationTests.new_participant
    session = fixtures.CommunityOperationTests.session

    def edit(self, session, **values):
        args = dict(session_id=session.session_id, fiscal_year_id=session.fiscal_year_id,
                    program_id=session.program_id, activity_id=session.activity_id,
                    session_date=session.session_date, duration_minutes=45, notes="Sesión actualizada")
        args.update(values)
        return attendance.edit_session(self.db, **args)

    def test_short_control_duration_and_edit_preserve_attendance(self):
        session = self.session(duration_minutes=90)
        self.assertEqual(session.control_number, f"CP-{session.session_id}")
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.db.commit()
        self.edit(session, session_date=date(2025, 1, 16), duration_minutes=120)
        self.db.commit()
        self.assertEqual(session.duration_minutes, 120)
        self.assertEqual(session.control_number, f"CP-{session.session_id}")
        self.assertTrue(self.db.get(CPAttendance, (session.session_id, self.participant_id)).is_present)

    def test_attendance_prevents_context_move_and_ineligible_date_change(self):
        session = self.session()
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "programa|año"):
            self.edit(session, program_id=self.tanf_id, activity_id=self.other_activity_id)
        discharge_participant(self.db, participant_id=self.participant_id, program_id=self.voca_id,
                              fiscal_year_id=self.fy_id, end_date=date(2025, 2, 1),
                              actor_user_id=self.actor_id, reason="Baja")
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "participantes|elegibles"):
            self.edit(session, session_date=date(2025, 2, 2))
        self.assertEqual(session.session_date, date(2025, 1, 15))

    def test_empty_session_can_change_program_but_activity_must_match(self):
        session = self.session()
        with self.assertRaises(ValueError):
            self.edit(session, program_id=self.tanf_id)
        self.edit(session, program_id=self.tanf_id, activity_id=self.other_activity_id)
        self.assertEqual(session.program_id, self.tanf_id)

    def test_clear_and_delete_respect_closure_and_leave_other_sessions_untouched(self):
        first, second = self.session(), self.session()
        for session in (first, second):
            set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.db.commit()
        set_fiscal_status(self.db, self.fy_id, closed=True, actor_user_id=self.actor_id)
        self.db.commit()
        for remove in (False, True):
            with self.assertRaises(ValueError):
                attendance.clear_session(self.db, session_id=first.session_id, delete_session=remove)
        set_fiscal_status(self.db, self.fy_id, closed=False, actor_user_id=self.actor_id)
        self.db.commit()
        attendance.clear_session(self.db, session_id=first.session_id, delete_session=False)
        self.assertIsNotNone(self.db.get(CPActivitySession, first.session_id))
        self.assertIsNone(self.db.scalar(select(CPAttendance).where(CPAttendance.session_id == first.session_id)))
        first_id = first.session_id
        attendance.clear_session(self.db, session_id=first_id, delete_session=True)
        self.db.commit()
        self.assertIsNone(self.db.get(CPActivitySession, first_id))
        self.assertTrue(self.db.get(CPAttendance, (second.session_id, self.participant_id)).is_present)

    def test_duration_rejects_invalid_values(self):
        for value in (-5, 0, 6, 1.5, "NaN", "inf", True, 2147483650):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.session(duration_minutes=value)
        self.assertIsNone(self.db.scalar(select(CPActivitySession)))


class AttendanceRouteTests(unittest.TestCase):
    tearDown = fixtures.CommunityOperationTests.tearDown
    new_participant = fixtures.CommunityOperationTests.new_participant
    session = fixtures.CommunityOperationTests.session

    def setUp(self):
        fixtures.CommunityOperationTests.setUp(self)
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="attendance-test-session-only")
        app.mount("/static", StaticFiles(directory="app/static"), name="static")
        app.include_router(community_operations.router)

        @app.get("/_test/login/{user_id}")
        def login(user_id: int, request: Request):
            request.session.clear()
            request.session.update(user_id=user_id, session_version=1, community_program_context="all")

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.feature = patch.object(settings, "COMMUNITY_ENABLED", True)
        self.feature.start()
        self.addCleanup(self.feature.stop)
        self.client = TestClient(app, follow_redirects=False)
        self.addCleanup(self.client.close)
        self.client.get(f"/_test/login/{self.actor_id}")
        page = self.client.get("/community/attendance")
        self.assertEqual(page.status_code, 200, page.text)
        self.token = re.search(r'name="token" value="([^"]+)"', page.text).group(1)

    def role(self, value):
        self.db.get(CPUserAccess, self.actor_id).role = value
        self.db.commit()

    def test_create_loads_only_program_activities_and_filters_roster(self):
        params = dict(program_id=self.voca_id, fiscal_year_id=self.fy_id)
        options = self.client.get("/community/attendance/activities", params=params)
        self.assertEqual([row["id"] for row in options.json()["activities"]], [self.activity_id])
        self.assertEqual(self.client.get("/community/attendance/activities", params={**params, "program_id": self.tanf_id}).status_code, 403)
        response = self.client.post("/community/attendance", data={
            **params, "token": self.token, "activity_id": self.activity_id, "session_date": "2025-01-15", "duration_minutes": "95",
        })
        self.assertEqual(response.status_code, 303)
        detail = self.client.get(response.headers["location"])
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual([p["participant_id"] for p in detail.context["participants"]], [self.participant_id])
        self.assertIn("CP-", detail.text)
        self.assertIn("95 min", detail.text)
        self.assertIn("Editar sesión", detail.text)
        self.assertNotIn('name="employee_id"', detail.text)
        forged = self.client.post("/community/attendance", data={
            **params, "token": self.token, "activity_id": self.other_activity_id, "session_date": "2025-01-15",
        })
        self.assertIn("programa", forged.context["form_error"])
        self.assertEqual(len(self.db.scalars(select(CPActivitySession)).all()), 1)

    def test_metrics_and_exports_share_filters_and_deduplicate_people(self):
        self.role("admin")
        first = self.session(duration_minutes=60)
        second = self.session(program_id=self.tanf_id, activity_id=self.other_activity_id)
        other_month = self.session(session_date=date(2025, 2, 1))
        for session in (first, second, other_month):
            set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.db.get(CPParticipant, self.participant_id).nombre = "Nombre actual cambiado"
        self.db.commit()
        params = dict(fiscal_year_id=self.fy_id, month=1, year=2025, from_date="2025-01-10", to_date="2025-01-20")
        page = self.client.get("/community/attendance", params=params)
        self.assertEqual(page.context["metrics"], dict(total_activities=2, total_participations=2, unique_participants=1))
        records = list(csv.reader(io.StringIO(self.client.get("/community/attendance/export.csv", params=params).content.decode("utf-8-sig"))))
        self.assertEqual(len(records), 3)
        people = list(csv.reader(io.StringIO(self.client.get("/community/attendance/export-attendance.csv", params=params).content.decode("utf-8-sig"))))
        self.assertEqual(len(people), 3)
        self.assertEqual(people[1][6], "Ana")
        filtered = self.client.get("/community/attendance", params={**params, "program_id": self.voca_id, "control_number": first.control_number})
        self.assertEqual(filtered.context["metrics"]["total_activities"], 1)
        self.role("user")
        scoped = self.client.get("/community/attendance/export.csv", params=params)
        self.assertNotIn("TANF-M", scoped.text)
        self.assertEqual(self.client.get("/community/attendance/export-attendance.csv", params={**params, "program_id": self.tanf_id}).status_code, 403)

    def test_inactive_rows_stay_visible_to_filter_without_losing_hidden_marks(self):
        discharge_participant(self.db, participant_id=self.participant_id, program_id=self.voca_id,
                              fiscal_year_id=self.fy_id, end_date=date(2025, 2, 1), actor_user_id=self.actor_id, reason="Baja")
        session = self.session(session_date=date(2025, 2, 2))
        # Simulate a legacy attendance row that is no longer eligible; a disabled checkbox must preserve it.
        self.db.add(CPAttendance(session_id=session.session_id, participant_id=self.participant_id, is_present=True))
        self.db.commit()
        page = self.client.get(f"/community/attendance/{session.session_id}")
        self.assertFalse(page.context["participants"][0]["eligible"])
        saved = self.client.post(f"/community/attendance/{session.session_id}", data={"token": self.token})
        self.assertEqual(saved.status_code, 303)
        self.db.expire_all()
        self.assertTrue(self.db.get(CPAttendance, (session.session_id, self.participant_id)).is_present)

    def test_destructive_actions_require_supervisor_csrf_scope_and_open_period(self):
        own, other = self.session(), self.session(program_id=self.tanf_id, activity_id=self.other_activity_id)
        set_session_attendance(self.db, session_id=own.session_id, present_participant_ids=[self.participant_id])
        own_id, other_id = own.session_id, other.session_id
        self.db.commit()
        for suffix in ("delete", "clear-attendance"):
            self.assertEqual(self.client.post(f"/community/attendance/{own_id}/{suffix}", data={"token": self.token}).status_code, 403)
        self.assertEqual(self.client.get(f"/community/attendance/{other_id}").status_code, 404)
        self.role("supervisor")
        for suffix in ("delete", "clear-attendance"):
            self.assertEqual(self.client.post(f"/community/attendance/{own_id}/{suffix}", data={"token": "wrong"}).status_code, 403)
        set_fiscal_status(self.db, self.fy_id, closed=True, actor_user_id=self.actor_id)
        self.db.commit()
        rejected = self.client.post(f"/community/attendance/{own_id}/delete", data={"token": self.token})
        self.assertIn("error=", rejected.headers["location"])
        set_fiscal_status(self.db, self.fy_id, closed=False, actor_user_id=self.actor_id)
        self.db.commit()
        cleared = self.client.post(f"/community/attendance/{own_id}/clear-attendance", data={"token": self.token})
        self.assertIn("msg=", cleared.headers["location"])
        deleted = self.client.post(f"/community/attendance/{own_id}/delete", data={"token": self.token})
        self.assertIn("msg=", deleted.headers["location"])
        self.db.expire_all()
        self.assertIsNone(self.db.get(CPActivitySession, own_id))
        self.assertIsNotNone(self.db.get(CPActivitySession, other_id))

    def test_edit_errors_preserve_form_and_viewer_cannot_edit(self):
        session = self.session()
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.db.commit()
        data = dict(token=self.token, program_id=self.voca_id, fiscal_year_id=self.fy_id,
                    activity_id=self.activity_id, session_date="2025-01-16", duration_minutes="35")
        edited = self.client.post(f"/community/attendance/{session.session_id}/edit", data=data)
        self.assertEqual(edited.status_code, 303)
        invalid = self.client.post(f"/community/attendance/{session.session_id}/edit", data={**data, "duration_minutes": "7"})
        self.assertEqual(invalid.status_code, 200)
        self.assertIn("múltiplo", invalid.context["form_error"])
        self.assertEqual(invalid.context["edit_form"]["duration_minutes"], "7")
        self.role("viewer")
        self.assertEqual(self.client.post(f"/community/attendance/{session.session_id}/edit", data=data).status_code, 403)
        self.db.expire_all()
        self.assertEqual(session.duration_minutes, 35)

    def test_csv_formula_text_is_escaped_and_queries_compile_for_sql_server(self):
        compiled = []

        def inspect_sql(conn, clause, *args):
            sql = str(clause.compile(dialect=mssql.dialect()))
            self.assertNotRegex(sql, r"\bIS (?:1|0|TRUE|FALSE)\b")
            compiled.append(sql)

        event.listen(self.engine, "before_execute", inspect_sql)
        session = self.session()
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        row = self.db.get(CPFiscalParticipant, (self.participant_id, self.fy_id))
        data = json.loads(row.snapshot_json)
        data["nombre"] = "=SUM(1,1)"
        row.snapshot_json = json.dumps(data)
        self.db.commit()
        page = self.client.get("/community/attendance", params={"month": 1, "control_number": session.control_number})
        self.assertEqual(page.status_code, 200)
        exported = self.client.get("/community/attendance/export-attendance.csv")
        rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
        self.assertEqual(rows[1][6], "'=SUM(1,1)")
        self.assertTrue(any("DATEPART" in sql for sql in compiled))

    def test_failed_session_delete_restores_attendance(self):
        self.role("admin")
        session = self.session()
        session_id = session.session_id
        set_session_attendance(self.db, session_id=session_id, present_participant_ids=[self.participant_id])
        self.db.execute(text("CREATE TABLE session_reference (session_id INTEGER REFERENCES cp_activity_sessions(session_id))"))
        self.db.execute(text("INSERT INTO session_reference VALUES (:id)"), {"id": session_id})
        self.db.commit()
        response = self.client.post(f"/community/attendance/{session_id}/delete", data={"token": self.token})
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(CPActivitySession, session_id))
        self.assertTrue(self.db.get(CPAttendance, (session_id, self.participant_id)).is_present)


if __name__ == "__main__":
    unittest.main()
