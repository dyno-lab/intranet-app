from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "community-operations-test-secret-not-production")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.dialects import mssql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import get_db
from app.api.routes import community, community_operations
from app.core.config import settings
from app.db.community_operations_schema import COMMUNITY_OPERATIONS_SCHEMA_SQL
from app.models.base import Base
from app.models.community import CPProgram, CPUserAccess, CPUserProgram, CPParticipant
from app.models.community_activity import CPActivity, CPFiscalActivity
import app.models.community_catalog  # fiscal snapshot profile tables
from app.models.community_fiscal import CPFiscalEnrollment, CPFiscalParticipant, CPEnrollmentPeriod
from app.models.community_operations import CPActivitySession, CPAttendance, CPGradeReport, CPGradeItem, COMMUNITY_OPERATION_MODELS
from app.models.platform_permission import PlatformPermission
from app.models.residential import Residential
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission
from app.services.community import create_program, create_fiscal_year, create_participant, update_participant
from app.services.community_activity import create_activity
from app.services.community_fiscal import (
    sync_participants, enroll_participant, discharge_participant,
    set_fiscal_status, set_fiscal_lock, set_snapshot_freeze,
)
from app.services.community_operations import (
    create_activity_session, set_session_attendance, create_grade_report, save_grade_item,
    has_participation_on_or_after, grade_letter, grade_participant_ids,
)


class CommunityOperationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'operations.db'}")

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function("sysutcdatetime", 0, lambda: datetime.now(timezone.utc).isoformat())

        core_tables = [Residential.__table__, User.__table__, PlatformPermission.__table__, UserPlatformPermission.__table__]
        Base.metadata.create_all(self.engine, tables=[*core_tables, *[table for name, table in Base.metadata.tables.items() if name.startswith("cp_")]])
        self.db = Session(self.engine)
        self.actor = User(username="operator", password_hash="test-only", role="viewer", is_active=True, session_version=1)
        self.viewer = User(username="viewer", password_hash="test-only", role="admin", is_active=True, session_version=1)
        self.db.add_all([self.actor, self.viewer])
        self.db.flush()
        self.actor_id, self.viewer_id = self.actor.user_id, self.viewer.user_id
        self.voca = create_program(self.db, "VOCA", "Programa VOCA")
        self.tanf = create_program(self.db, "TANF-M", "Programa TANF-M")
        self.fy = create_fiscal_year(self.db, "2025", "Año 2025", date(2025, 1, 1), date(2025, 12, 31))
        self.voca_id, self.tanf_id, self.fy_id = self.voca.program_id, self.tanf.program_id, self.fy.fiscal_year_id
        self.activity = create_activity(self.db, program_id=self.voca_id, code="TALLER", description="Taller educativo", fiscal_year_ids=[self.fy_id])
        self.other_activity = create_activity(self.db, program_id=self.tanf_id, code="ORIENTACION", description="Orientación", fiscal_year_ids=[self.fy_id])
        self.activity_id, self.other_activity_id = self.activity.activity_id, self.other_activity.activity_id
        self.participant = self.new_participant("Ana", [self.voca_id, self.tanf_id])
        self.outsider = self.new_participant("Otro", [self.tanf_id])
        self.participant_id, self.outsider_id = self.participant.participant_id, self.outsider.participant_id
        sync_participants(self.db, self.fy_id, [self.participant_id, self.outsider_id], actor_user_id=self.actor_id)
        for participant_id, program_ids in ((self.participant_id, [self.voca_id, self.tanf_id]), (self.outsider_id, [self.tanf_id])):
            for program_id in program_ids:
                enroll_participant(self.db, participant_id=participant_id, program_id=program_id, fiscal_year_id=self.fy_id,
                                   start_date=date(2025, 1, 1), actor_user_id=self.actor_id)
        permission = PlatformPermission(key="access_community", name="Comunidad")
        self.db.add(permission)
        self.db.flush()
        for user_id, role in ((self.actor_id, "user"), (self.viewer_id, "viewer")):
            self.db.add(CPUserAccess(user_id=user_id, role=role))
            self.db.add(UserPlatformPermission(user_id=user_id, permission_id=permission.permission_id))
        self.db.add(CPUserProgram(user_id=self.actor_id, program_id=self.voca_id))
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def new_participant(self, name, programs, born=None):
        return create_participant(self.db, actor_user_id=self.actor_id, exp_year=2025, program_ids=programs, fields={
            "nombre": name, "apellido_paterno": "Rivera", "genero": "F",
            "fecha_nacimiento": born or date(date.today().year - 10, 1, 1),
        })

    def session(self, **changes):
        args = dict(fiscal_year_id=self.fy_id, program_id=self.voca_id, activity_id=self.activity_id,
                    session_date=date(2025, 1, 15), actor_user_id=self.actor_id)
        args.update(changes)
        return create_activity_session(self.db, **args)

    def report(self, **changes):
        args = dict(fiscal_year_id=self.fy_id, program_id=self.voca_id, report_year=2025,
                    report_month=1, actor_user_id=self.actor_id)
        args.update(changes)
        return create_grade_report(self.db, **args)

    def test_attendance_accepts_only_active_enrollment_and_preserves_history_after_discharge(self):
        session = self.session()
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.db.commit()
        discharge_participant(self.db, participant_id=self.participant_id, program_id=self.voca_id,
                              fiscal_year_id=self.fy_id, end_date=date(2025, 2, 1), actor_user_id=self.actor_id, reason="Finalizó")
        self.db.commit()
        self.assertTrue(self.db.get(CPAttendance, (session.session_id, self.participant_id)).is_present)
        later = self.session(session_date=date(2025, 2, 1))
        with self.assertRaises(ValueError):
            set_session_attendance(self.db, session_id=later.session_id, present_participant_ids=[self.participant_id])
        # Another program remains available on that same date.
        other = self.session(program_id=self.tanf_id, activity_id=self.other_activity_id, session_date=date(2025, 2, 1))
        set_session_attendance(self.db, session_id=other.session_id, present_participant_ids=[self.participant_id])
        self.assertTrue(self.db.get(CPAttendance, (other.session_id, self.participant_id)).is_present)

    def test_invalid_roster_cannot_partially_replace_existing_attendance(self):
        session = self.session()
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.db.commit()
        with self.assertRaises(ValueError):
            set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.outsider_id])
        self.assertTrue(self.db.get(CPAttendance, (session.session_id, self.participant_id)).is_present)
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[])
        self.assertFalse(self.db.get(CPAttendance, (session.session_id, self.participant_id)).is_present)
        self.db.rollback()
        self.assertTrue(self.db.get(CPAttendance, (session.session_id, self.participant_id)).is_present)

    def test_activity_must_belong_to_program_and_fiscal_year(self):
        with self.assertRaises(ValueError):
            self.session(activity_id=self.other_activity_id)
        other_year = create_fiscal_year(self.db, "2024", "Anterior", date(2024, 1, 1), date(2024, 12, 31))
        with self.assertRaises(ValueError):
            self.session(fiscal_year_id=other_year.fiscal_year_id, session_date=date(2024, 1, 15))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPActivitySession)), 0)
        self.db.add(CPActivitySession(fiscal_year_id=self.fy_id, program_id=self.voca_id,
                                      activity_id=self.other_activity_id, session_date=date(2025, 1, 15),
                                      created_by_user_id=self.actor_id))
        with self.assertRaises(IntegrityError):
            self.db.flush()
        self.db.rollback()

    def test_closed_year_closed_month_and_future_reject_operational_writes(self):
        session, report = self.session(), self.report()
        self.db.commit()
        set_fiscal_lock(self.db, self.fy_id, locked_through=date(2025, 1, 31), actor_user_id=self.actor_id)
        self.db.commit()
        with self.assertRaises(ValueError):
            set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        with self.assertRaises(ValueError):
            save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id, fields={"math_grade": "90"})
        set_fiscal_status(self.db, self.fy_id, closed=True, actor_user_id=self.actor_id)
        self.db.commit()
        with self.assertRaises(ValueError):
            self.session(session_date=date(2025, 2, 15))
        with self.assertRaises(ValueError):
            self.report(report_month=2)
        future = date.today() + timedelta(days=40)
        fy = create_fiscal_year(self.db, "FUTURE", "Futuro", future.replace(day=1), date(future.year, 12, 31))
        activity = create_activity(self.db, program_id=self.voca_id, code="FUTURE", description=None, fiscal_year_ids=[fy.fiscal_year_id])
        with self.assertRaises(ValueError):
            self.session(fiscal_year_id=fy.fiscal_year_id, activity_id=activity.activity_id, session_date=future)
        with self.assertRaises(ValueError):
            self.report(fiscal_year_id=fy.fiscal_year_id, report_year=future.year, report_month=future.month)

    def test_grades_use_faro_scale_fields_average_and_blank_values(self):
        report = self.report()
        item = save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id,
                               fields={"grade_level": "5", "is_content_room": True, "spanish_grade": "90", "math_grade": "80", "english_grade": ""})
        self.db.commit()
        self.assertEqual(item.average_grade, Decimal("85.00"))
        self.assertEqual(grade_letter(item.average_grade), "B")
        self.assertIsNone(item.english_grade)
        self.assertTrue(item.is_content_room)
        for invalid in ("101", "-1", "nan", "inf", "bad"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id, fields={"math_grade": invalid})
            self.assertEqual(item.average_grade, Decimal("85.00"))
        item = save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id, fields={"math_grade": "100"})
        self.assertEqual(item.average_grade, 95)
        self.db.rollback()
        self.assertEqual(item.average_grade, Decimal("85.00"))

    def test_school_grade_eligibility_uses_current_age_from_fiscal_snapshot(self):
        older = self.new_participant("Mayor", [self.voca_id], date(date.today().year - 22, 1, 1))
        missing = create_participant(self.db, actor_user_id=self.actor_id, exp_year=2025, program_ids=[self.voca_id],
                                     fields={"nombre": "Sin fecha", "apellido_paterno": "Rivera", "genero": "F"})
        sync_participants(self.db, self.fy_id, [older.participant_id, missing.participant_id], actor_user_id=self.actor_id)
        for participant in (older, missing):
            enroll_participant(self.db, participant_id=participant.participant_id, program_id=self.voca_id,
                               fiscal_year_id=self.fy_id, start_date=date(2025, 1, 1), actor_user_id=self.actor_id)
        report = self.report()
        for participant in (older, missing):
            with self.assertRaises(ValueError):
                save_grade_item(self.db, report_id=report.report_id, participant_id=participant.participant_id, fields={"math_grade": "90"})
        update_participant(self.db, participant_id=self.participant_id, fields={"fecha_nacimiento": date(date.today().year - 30, 1, 1)})
        set_snapshot_freeze(self.db, self.fy_id, frozen=True, actor_user_id=self.actor_id)
        save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id, fields={"math_grade": "90"})
        self.assertEqual(grade_participant_ids(self.db, report), [self.participant_id])

    def test_same_day_discharge_is_not_a_school_grade_eligible_interval(self):
        discharge_participant(self.db, participant_id=self.participant_id, program_id=self.voca_id,
                              fiscal_year_id=self.fy_id, end_date=date(2025, 1, 1), actor_user_id=self.actor_id, reason="Sin ingreso")
        report = self.report()
        self.assertNotIn(self.participant_id, grade_participant_ids(self.db, report))

    def test_retroactive_discharge_protects_present_attendance_and_grade_months(self):
        session = self.session()
        set_session_attendance(self.db, session_id=session.session_id, present_participant_ids=[self.participant_id])
        self.assertTrue(has_participation_on_or_after(self.db, self.participant_id, self.voca_id, self.fy_id, date(2025, 1, 15)))
        self.assertFalse(has_participation_on_or_after(self.db, self.participant_id, self.voca_id, self.fy_id, date(2025, 1, 16)))
        report = self.report()
        save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id, fields={"math_grade": "90"})
        self.assertTrue(has_participation_on_or_after(self.db, self.participant_id, self.voca_id, self.fy_id, date(2025, 1, 31)))
        self.assertFalse(has_participation_on_or_after(self.db, self.participant_id, self.tanf_id, self.fy_id, date(2025, 1, 1)))
        self.assertFalse(has_participation_on_or_after(self.db, self.participant_id, self.voca_id, self.fy_id, date(2025, 2, 1)))
        with self.assertRaises(ValueError):
            discharge_participant(self.db, participant_id=self.participant_id, program_id=self.voca_id,
                                  fiscal_year_id=self.fy_id, end_date=date(2025, 1, 31), actor_user_id=self.actor_id, reason="Retroactiva")

    def test_grade_report_is_unique_per_fiscal_program_and_month(self):
        self.report()
        with self.assertRaises(ValueError):
            self.report()
        self.report(program_id=self.tanf_id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPGradeReport)), 2)

    def test_models_compile_for_mssql_and_migration_is_additive(self):
        for model in COMMUNITY_OPERATION_MODELS:
            self.assertIn(f"CREATE TABLE {model.__tablename__}", str(CreateTable(model.__table__).compile(dialect=mssql.dialect())))
            self.assertIn(f"IF OBJECT_ID(N'dbo.{model.__tablename__}', N'U') IS NULL", COMMUNITY_OPERATIONS_SCHEMA_SQL)
        self.assertNotIn("DROP TABLE", COMMUNITY_OPERATIONS_SCHEMA_SQL)

    def test_http_viewer_cross_program_and_csrf_boundaries(self):
        own_session = self.session()
        other_session = self.session(program_id=self.tanf_id, activity_id=self.other_activity_id)
        own_report = self.report()
        other_report = self.report(program_id=self.tanf_id)
        own_session_id, other_session_id, own_report_id, other_report_id = own_session.session_id, other_session.session_id, own_report.report_id, other_report.report_id
        for _ in range(50):
            self.session()
        self.db.commit()
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="local-operations-test-session")
        app.mount("/static", StaticFiles(directory="app/static"), name="static")
        app.include_router(community.router)
        app.include_router(community_operations.router)

        @app.get("/_test/login/{user_id}")
        def login(user_id: int, request: Request):
            request.session.clear()
            request.session.update(user_id=user_id, session_version=1, community_program_context="all")
            return {"ok": True}

        def get_test_db():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = get_test_db
        with patch.object(settings, "COMMUNITY_ENABLED", True), TestClient(app, follow_redirects=False) as client:
            client.get(f"/_test/login/{self.actor_id}")
            first_page = client.get(f"/community/attendance?fiscal_year_id={self.fy_id}&program_id={self.voca_id}")
            self.assertEqual(first_page.status_code, 200, first_page.text)
            self.assertIn("Siguiente", first_page.text)
            self.assertIn(f"fiscal_year_id={self.fy_id}&amp;program_id={self.voca_id}&amp;page=2", first_page.text)
            second_page = client.get(f"/community/attendance?fiscal_year_id={self.fy_id}&program_id={self.voca_id}&page=2")
            self.assertIn(f'/community/attendance/{own_session_id}', second_page.text)
            self.assertIn("Anterior", second_page.text)
            grade_list = client.get(f"/community/school-grades?fiscal_year_id={self.fy_id}&program_id={self.voca_id}")
            self.assertEqual(grade_list.status_code, 200, grade_list.text)
            self.assertIn(f'/community/school-grades/{own_report_id}', grade_list.text)
            page = client.get(f"/community/attendance/{own_session_id}")
            self.assertEqual(page.status_code, 200, page.text)
            token = re.search(r'name="token" value="([^"]+)"', page.text).group(1)
            for path in (f"/community/attendance/{other_session_id}", f"/community/school-grades/{other_report_id}"):
                self.assertEqual(client.get(path).status_code, 404)
            self.assertEqual(client.post(f"/community/attendance/{own_session_id}", data={"token": "bad"}).status_code, 403)
            self.assertEqual(client.post(f"/community/attendance/{other_session_id}", data={"token": token}).status_code, 404)
            response = client.post(f"/community/attendance/{own_session_id}", data={"token": token, "present_participant_ids": [self.participant_id]})
            self.assertEqual(response.status_code, 303)
            self.assertIn("msg=", response.headers["location"])
            page = client.get(f"/community/school-grades/{own_report_id}")
            self.assertEqual(page.status_code, 200, page.text)
            response = client.post(f"/community/school-grades/{own_report_id}/participants", data={"token": token, "participant_id": self.participant_id, "math_grade": "90", "grade_level": "5"})
            self.assertEqual(response.status_code, 303)
            self.assertIn("msg=", response.headers["location"])
            self.assertIn("90.00", client.get(f"/community/school-grades/{own_report_id}").text)
            client.get(f"/_test/login/{self.viewer_id}")
            page = client.get(f"/community/attendance/{own_session_id}")
            self.assertEqual(page.status_code, 200)
            token = re.search(r'name="token" value="([^"]+)"', page.text).group(1)
            self.assertEqual(client.post(f"/community/attendance/{own_session_id}", data={"token": token}).status_code, 403)
            self.assertEqual(client.post(f"/community/school-grades/{own_report_id}/participants", data={"token": token, "participant_id": self.participant_id}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
