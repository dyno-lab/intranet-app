from __future__ import annotations

import os
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "community-test-session-secret-not-production")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import get_db
from app.api.routes import community_fiscal
from app.core.community_access import CommunityContext, require_community_context
from app.models.base import Base
from app.models.community import CPFiscalYear, CPParticipant, CPParticipantProgram, CPProgram, CPSequence
from app.models.community_activity import CPActivity, CPFiscalActivity
from app.models.community_catalog import CPProfileField, CPProfileValue
from app.models.community_fiscal import CPFiscalEnrollment, CPFiscalParticipant, CPFiscalState, CPEnrollmentPeriod
from app.models.community_operations import CPActivitySession, CPAttendance, CPGradeReport, CPGradeItem
from app.models.residential import Residential
from app.models.user import User
from app.services.community import create_fiscal_year, create_participant, create_program
from app.services.community_fiscal import (discharge_participant, enroll_participant, is_enrolled_on,
    reactivate_participant, require_fiscal_writable, set_fiscal_lock, set_fiscal_status,
    set_snapshot_freeze, snapshot_for_participant, sync_participants)


class _FiscalFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'fiscal.db'}")

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function("sysutcdatetime", 0, lambda: datetime.now(timezone.utc).isoformat())

        models = (Residential, User, CPProgram, CPFiscalYear, CPSequence, CPParticipant, CPParticipantProgram,
                  CPProfileField, CPProfileValue, CPFiscalState, CPFiscalParticipant, CPFiscalEnrollment,
                  CPEnrollmentPeriod, CPActivity, CPFiscalActivity, CPActivitySession, CPAttendance,
                  CPGradeReport, CPGradeItem)
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in models])
        self.db = Session(self.engine, expire_on_commit=False)
        self.actor = User(username="fiscal-test", password_hash="not-used", role="viewer", is_active=True)
        self.db.add(self.actor)
        self.db.flush()
        self.voca = create_program(self.db, "VOCA", "VOCA")
        self.tanf = create_program(self.db, "TANF-M", "TANF-M")
        self.year = create_fiscal_year(self.db, "2024", "Año fiscal 2024", date(2024, 1, 15), date(2024, 12, 20))
        self.person = create_participant(self.db, actor_user_id=self.actor.user_id, exp_year=2024,
            program_ids=[self.voca.program_id, self.tanf.program_id],
            fields={"nombre": "María", "apellido_paterno": "Rivera", "genero": "F",
                    "fecha_nacimiento": "2000-01-01", "pueblo": "Ponce"})
        self.db.commit()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp.cleanup()

    def sync(self, fiscal_year=None):
        return sync_participants(self.db, (fiscal_year or self.year).fiscal_year_id,
                                 [self.person.participant_id], actor_user_id=self.actor.user_id)

    def arguments(self, program=None):
        return dict(participant_id=self.person.participant_id, program_id=(program or self.voca).program_id,
                    fiscal_year_id=self.year.fiscal_year_id, actor_user_id=self.actor.user_id)

    def enrolled(self, on_date, program=None):
        return is_enrolled_on(self.db, self.person.participant_id, (program or self.voca).program_id,
                               self.year.fiscal_year_id, on_date)


class CommunityFiscalTests(_FiscalFixture):
    def test_sync_preserves_one_record_and_numbers_across_years(self):
        following = create_fiscal_year(self.db, "2025", "Siguiente", date(2025, 1, 1), date(2025, 12, 31))
        self.sync()
        self.sync(following)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPParticipant)), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPFiscalParticipant)), 2)
        self.assertEqual(snapshot_for_participant(self.db, self.person.participant_id, following.fiscal_year_id)["expediente_num"], "CP-2024-0001")
        self.assertEqual(self.db.get(CPParticipantProgram, (self.person.participant_id, self.voca.program_id)).record_number,
                         "CP-2024-VOCA-0001")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPFiscalEnrollment)), 0)

    def test_freeze_preserves_demographics_and_inactive_profile_history(self):
        field = CPProfileField(field_key="contacto", label="Contacto familiar", field_type="text", is_active=False)
        self.db.add(field)
        self.db.flush()
        value = CPProfileValue(participant_id=self.person.participant_id, field_id=field.field_id, value="Tía")
        self.db.add(value)
        self.sync()
        set_snapshot_freeze(self.db, self.year.fiscal_year_id, frozen=True, actor_user_id=self.actor.user_id)
        self.person.pueblo = "San Juan"
        value.value = "Madre"
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "congelados"):
            self.sync()
        snapshot = snapshot_for_participant(self.db, self.person.participant_id, self.year.fiscal_year_id)
        self.assertEqual(snapshot["pueblo"], "Ponce")
        self.assertEqual(snapshot["profile_fields"]["contacto"], {"label": "Contacto familiar", "value": "Tía"})
        self.assertEqual(self.person.pueblo, "San Juan")

    def test_close_freezes_and_reopen_keeps_freeze_until_explicit_unfreeze(self):
        self.sync()
        set_fiscal_status(self.db, self.year.fiscal_year_id, closed=True, actor_user_id=self.actor.user_id)
        with self.assertRaisesRegex(ValueError, "cerrado"):
            require_fiscal_writable(self.db, self.year.fiscal_year_id, date(2024, 2, 1))
        with self.assertRaisesRegex(ValueError, "Reabra"):
            set_snapshot_freeze(self.db, self.year.fiscal_year_id, frozen=False, actor_user_id=self.actor.user_id)
        set_fiscal_status(self.db, self.year.fiscal_year_id, closed=False, actor_user_id=self.actor.user_id)
        require_fiscal_writable(self.db, self.year.fiscal_year_id, date(2024, 2, 1))
        with self.assertRaisesRegex(ValueError, "congelados"):
            self.sync()
        set_snapshot_freeze(self.db, self.year.fiscal_year_id, frozen=False, actor_user_id=self.actor.user_id)
        self.assertEqual(self.sync(), 1)

    def test_discharge_is_exclusive_and_does_not_affect_other_program(self):
        self.sync()
        enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments())
        enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments(self.tanf))
        discharge_participant(self.db, end_date=date(2024, 3, 1), reason="Finalizó", **self.arguments(self.tanf))
        self.assertTrue(self.enrolled(date(2024, 2, 29), self.tanf))
        self.assertFalse(self.enrolled(date(2024, 3, 1), self.tanf))
        self.assertTrue(self.enrolled(date(2024, 3, 1), self.voca))
        reactivate_participant(self.db, start_date=date(2024, 8, 1), reason="Regresó", **self.arguments(self.tanf))
        self.assertFalse(self.enrolled(date(2024, 7, 31), self.tanf))
        self.assertTrue(self.enrolled(date(2024, 8, 1), self.tanf))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPEnrollmentPeriod)), 3)
        self.assertFalse(self.enrolled(date(2024, 12, 21)))

    def test_requires_sync_and_permanent_association(self):
        with self.assertRaisesRegex(ValueError, "sincronizar"):
            enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments())
        self.sync()
        unrelated = create_program(self.db, "ICP", "ICP")
        with self.assertRaisesRegex(ValueError, "asocie"):
            enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments(unrelated))

    def test_reactivation_cannot_overlap_or_replace_history(self):
        self.sync()
        enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments())
        with self.assertRaisesRegex(ValueError, "ya está activo"):
            reactivate_participant(self.db, start_date=date(2024, 2, 2), reason="Reingreso", **self.arguments())
        discharge_participant(self.db, end_date=date(2024, 3, 1), reason="Baja", **self.arguments())
        with self.assertRaisesRegex(ValueError, "última baja"):
            reactivate_participant(self.db, start_date=date(2024, 2, 28), reason="Reingreso", **self.arguments())
        reactivate_participant(self.db, start_date=date(2024, 3, 1), reason="Reingreso", **self.arguments())
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPEnrollmentPeriod)), 2)

    def test_month_locks_and_configurable_date_boundaries(self):
        for invalid in (date(2024, 1, 14), date(2024, 12, 21)):
            with self.assertRaisesRegex(ValueError, "inicio y fin"):
                require_fiscal_writable(self.db, self.year.fiscal_year_id, invalid)
        set_fiscal_lock(self.db, self.year.fiscal_year_id, locked_through=date(2024, 2, 29), actor_user_id=self.actor.user_id)
        with self.assertRaisesRegex(ValueError, "períodos están cerrados"):
            require_fiscal_writable(self.db, self.year.fiscal_year_id, date(2024, 2, 29))
        require_fiscal_writable(self.db, self.year.fiscal_year_id, date(2024, 3, 1))
        with self.assertRaisesRegex(ValueError, "último día"):
            set_fiscal_lock(self.db, self.year.fiscal_year_id, locked_through=date(2024, 2, 28), actor_user_id=self.actor.user_id)
        set_fiscal_lock(self.db, self.year.fiscal_year_id, locked_through=None, actor_user_id=self.actor.user_id)
        require_fiscal_writable(self.db, self.year.fiscal_year_id, date(2024, 2, 29))

    def test_future_operations_rejected(self):
        future = date.today() + timedelta(days=10)
        year = create_fiscal_year(self.db, "FUTURE", "Futuro", date.today(), future)
        with self.assertRaisesRegex(ValueError, "futuras"):
            require_fiscal_writable(self.db, year.fiscal_year_id, future)

    def test_retroactive_discharge_preserves_existing_attendance(self):
        self.sync()
        enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments())
        activity = CPActivity(program_id=self.voca.program_id, code="TALLER", code_key="TALLER")
        self.db.add(activity)
        self.db.flush()
        self.db.add(CPFiscalActivity(activity_id=activity.activity_id, fiscal_year_id=self.year.fiscal_year_id, program_id=self.voca.program_id))
        self.db.flush()
        session = CPActivitySession(fiscal_year_id=self.year.fiscal_year_id, program_id=self.voca.program_id,
                                    activity_id=activity.activity_id, session_date=date(2024, 3, 2), created_by_user_id=self.actor.user_id)
        self.db.add(session)
        self.db.flush()
        self.db.add(CPAttendance(session_id=session.session_id, participant_id=self.person.participant_id, is_present=True))
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "asistencias o notas"):
            discharge_participant(self.db, end_date=date(2024, 3, 2), reason="Baja", **self.arguments())
        self.assertTrue(self.enrolled(date(2024, 3, 2)))
        discharge_participant(self.db, end_date=date(2024, 3, 3), reason="Baja", **self.arguments())
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPAttendance)), 1)

    def test_flush_only_allows_caller_rollback(self):
        self.sync()
        enroll_participant(self.db, start_date=date(2024, 2, 1), **self.arguments())
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPFiscalParticipant)), 0)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPFiscalEnrollment)), 0)


class CommunityFiscalRouteTests(_FiscalFixture):
    def setUp(self):
        super().setUp()
        self.context = CommunityContext(self.actor, "admin", (self.voca, self.tanf))
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="fiscal-route-tests-not-production")
        app.mount("/static", StaticFiles(directory="app/static"), name="static")
        app.include_router(community_fiscal.router)
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[require_community_context] = lambda: self.context

        @app.get("/_test/session")
        def session(request: Request):
            request.session["community_csrf"] = "fiscal-test-token"
            return {"ok": True}

        self.client = TestClient(app, follow_redirects=False)
        self.client.get("/_test/session")

    def tearDown(self):
        self.client.close()
        super().tearDown()

    def test_render_sync_and_membership_forms(self):
        response = self.client.get(f"/community/fiscal-participants?fiscal_year_id={self.year.fiscal_year_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("Sin sincronizar", response.text)
        self.assertIn("Cerrar año fiscal y congelar", response.text)
        response = self.client.post("/community/fiscal-participants/sync", data={"token": "fiscal-test-token",
            "fiscal_year_id": self.year.fiscal_year_id, "participant_ids": [self.person.participant_id]})
        self.assertEqual(response.status_code, 303)
        response = self.client.get(f"/community/participants/{self.person.participant_id}/memberships?fiscal_year_id={self.year.fiscal_year_id}")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("CP-2024-VOCA-0001", response.text)
        self.assertIn("CP-2024-TANF-M-0001", response.text)
        self.assertIn("Dar de alta", response.text)

    def test_program_scope_viewer_and_csrf_are_checked_server_side(self):
        self.sync()
        self.context = CommunityContext(self.actor, "user", (self.voca,), self.voca.program_id)
        path = f"/community/participants/{self.person.participant_id}/memberships"
        payload = dict(token="fiscal-test-token", fiscal_year_id=self.year.fiscal_year_id,
                       program_id=self.tanf.program_id, action="enroll", effective_date="2024-02-01", reason="Alta")
        self.assertEqual(self.client.post(path, data=payload).status_code, 403)
        self.assertEqual(self.client.get("/community/fiscal-participants").status_code, 403)
        payload["program_id"] = self.voca.program_id
        payload["token"] = "wrong"
        self.assertEqual(self.client.post(path, data=payload).status_code, 403)
        payload["token"] = "fiscal-test-token"
        self.assertEqual(self.client.post(path, data=payload).status_code, 303)
        page = self.client.get(path)
        self.assertNotIn("TANF-M", page.text)
        self.context = CommunityContext(self.actor, "viewer", (self.voca, self.tanf))
        self.assertEqual(self.client.post(path, data=payload).status_code, 403)
        self.assertNotIn("Dar de baja", self.client.get(path).text)

    def test_supervisor_cannot_close_year_and_user_cannot_sync(self):
        self.context = CommunityContext(self.actor, "supervisor", (self.voca, self.tanf))
        response = self.client.post(f"/community/fiscal-years/{self.year.fiscal_year_id}/status",
                                    data={"token": "fiscal-test-token", "action": "close"})
        self.assertEqual(response.status_code, 403)
        self.context = CommunityContext(self.actor, "user", (self.voca,))
        self.assertEqual(self.client.post("/community/fiscal-participants/sync", data={"token": "fiscal-test-token",
            "fiscal_year_id": self.year.fiscal_year_id, "participant_ids": [self.person.participant_id]}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
