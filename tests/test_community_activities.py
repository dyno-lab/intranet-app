from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "community-activity-test-session-secret")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import get_db
from app.api.routes import community_activities
from app.core.community_access import CommunityContext, require_community_context
from app.models.base import Base
from app.models.community import CPFiscalYear, CPProgram
from app.models.community_activity import COMMUNITY_ACTIVITY_MODELS, CPActivity, CPFiscalActivity, CPADMServiceActivity, CPADMServiceType
from app.models.community_operations import CPActivitySession
from app.models.residential import Residential
from app.models.user import User
from app.services.community import create_fiscal_year, create_program
from app.services.community_activity import (
    assign_adm_activity, associate_activity, copy_fiscal_configuration, create_activity,
    create_adm_service_type, set_activity_active, unassign_adm_activity, update_adm_service_type,
)


class ActivityDatabaseFixture:
    def create_database(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'activities.db'}")

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function("sysutcdatetime", 0, lambda: datetime.now(timezone.utc).isoformat())

        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in (
            Residential, User, CPProgram, CPFiscalYear, *COMMUNITY_ACTIVITY_MODELS, CPActivitySession,
        )])
        with Session(self.engine, expire_on_commit=False) as db:
            actor = User(username="activity-admin", password_hash="test-only", role="admin", is_active=True)
            db.add(actor)
            db.flush()
            self.actor_id = actor.user_id
            self.voca = create_program(db, "VOCA", "Programa VOCA")
            self.tanf = create_program(db, "TANF-M", "Programa TANF-M")
            self.year = create_fiscal_year(db, "2026", "Año 2026", date(2026, 1, 1), date(2026, 12, 31))
            self.next_year = create_fiscal_year(db, "2027", "Año 2027", date(2027, 1, 1), date(2027, 12, 31))
            db.commit()

    def activity(self, db, *, program_id=None, years=None, code="OR-01"):
        return create_activity(db, program_id=program_id or self.voca.program_id, code=code,
                               description="Orientación", fiscal_year_ids=years or [self.year.fiscal_year_id])

    def service(self, db, *, program_id=None, fiscal_year_id=None, name="Orientación"):
        return create_adm_service_type(db, program_id=program_id or self.voca.program_id,
                                       fiscal_year_id=fiscal_year_id or self.year.fiscal_year_id, name=name, sort_order=3)

    def assign(self, db, service, activity):
        return assign_adm_activity(db, service_type_id=service.adm_service_type_id, program_id=service.program_id,
                                   fiscal_year_id=service.fiscal_year_id, activity_id=activity.activity_id)

    def remove_database(self):
        self.engine.dispose()
        self.temp.cleanup()


class CommunityActivityDomainTests(ActivityDatabaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_database()
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.remove_database()

    def test_codes_are_unique_per_program_ignoring_case(self):
        first = self.activity(self.db)
        second = self.activity(self.db, program_id=self.tanf.program_id, code="or-01")
        self.assertNotEqual(first.activity_id, second.activity_id)
        with self.assertRaisesRegex(ValueError, "Ya existe una actividad"):
            self.activity(self.db, code="or-01")
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPActivity)), 2)

    def test_activity_can_span_years_and_deactivation_is_year_specific(self):
        activity = self.activity(self.db, years=[self.year.fiscal_year_id, self.next_year.fiscal_year_id])
        service = self.service(self.db)
        mapping = self.assign(self.db, service, activity)
        set_activity_active(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id,
                            fiscal_year_id=self.year.fiscal_year_id, active=False)
        self.assertFalse(self.db.get(CPFiscalActivity, (activity.activity_id, self.year.fiscal_year_id)).is_active)
        self.assertTrue(self.db.get(CPFiscalActivity, (activity.activity_id, self.next_year.fiscal_year_id)).is_active)
        self.assertTrue(self.db.get(CPADMServiceActivity, mapping.id).is_active)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPFiscalActivity)), 2)

    def test_closed_year_rejects_creation_before_any_activity_is_added(self):
        self.db.get(CPFiscalYear, self.next_year.fiscal_year_id).status = "closed"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "cerrado"):
            self.activity(self.db, years=[self.year.fiscal_year_id, self.next_year.fiscal_year_id])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPActivity)), 0)

    def test_existing_activity_can_be_associated_without_duplicate_identity(self):
        activity = self.activity(self.db)
        for _ in range(2):
            associate_activity(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id,
                                fiscal_year_id=self.next_year.fiscal_year_id)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPActivity)), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPFiscalActivity)), 2)

    def test_service_rejects_cross_program_and_cross_year_activities(self):
        activity = self.activity(self.db)
        wrong_program = self.service(self.db, program_id=self.tanf.program_id)
        wrong_year = self.service(self.db, fiscal_year_id=self.next_year.fiscal_year_id)
        with self.assertRaisesRegex(ValueError, "programa"):
            self.assign(self.db, wrong_program, activity)
        with self.assertRaisesRegex(ValueError, "mismo programa y año"):
            self.assign(self.db, wrong_year, activity)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPADMServiceActivity)), 0)

    def test_database_enforces_program_context_even_if_service_is_bypassed(self):
        activity = self.activity(self.db)
        self.db.commit()
        with self.assertRaises(IntegrityError):
            self.db.add(CPFiscalActivity(activity_id=activity.activity_id, fiscal_year_id=self.next_year.fiscal_year_id,
                                         program_id=self.tanf.program_id))
            self.db.flush()
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPFiscalActivity)), 1)

    def test_only_one_active_adm_assignment_and_removal_preserves_old_mapping(self):
        activity = self.activity(self.db)
        first = self.service(self.db)
        second = self.service(self.db, name="Taller")
        original = self.assign(self.db, first, activity)
        with self.assertRaisesRegex(ValueError, "otro tipo de servicio"):
            self.assign(self.db, second, activity)
        unassign_adm_activity(self.db, service_type_id=first.adm_service_type_id, program_id=first.program_id,
                              fiscal_year_id=first.fiscal_year_id, activity_id=activity.activity_id)
        current = self.assign(self.db, second, activity)
        self.assertFalse(self.db.get(CPADMServiceActivity, original.id).is_active)
        self.assertTrue(current.is_active)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPADMServiceActivity)), 2)

    def test_service_deactivation_preserves_activity_mapping(self):
        activity = self.activity(self.db)
        service = self.service(self.db)
        mapping = self.assign(self.db, service, activity)
        update_adm_service_type(self.db, service_type_id=service.adm_service_type_id,
                                program_id=service.program_id, fiscal_year_id=service.fiscal_year_id,
                                name=service.name, sort_order=service.sort_order, active=False)
        self.assertFalse(service.is_active)
        self.assertTrue(self.db.get(CPADMServiceActivity, mapping.id).is_active)

    def test_used_activity_keeps_its_historical_adm_classification(self):
        activity = self.activity(self.db)
        service = self.service(self.db)
        mapping = self.assign(self.db, service, activity)
        self.db.add(CPActivitySession(fiscal_year_id=service.fiscal_year_id, program_id=service.program_id,
                                     activity_id=activity.activity_id, session_date=date(2026, 2, 1),
                                     created_by_user_id=self.actor_id))
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "sesiones registradas"):
            unassign_adm_activity(self.db, service_type_id=service.adm_service_type_id,
                                  program_id=service.program_id, fiscal_year_id=service.fiscal_year_id,
                                  activity_id=activity.activity_id)
        with self.assertRaisesRegex(ValueError, "reportes históricos"):
            update_adm_service_type(self.db, service_type_id=service.adm_service_type_id,
                                    program_id=service.program_id, fiscal_year_id=service.fiscal_year_id,
                                    name="Nombre cambiado", sort_order=service.sort_order, active=True)
        update_adm_service_type(self.db, service_type_id=service.adm_service_type_id,
                                program_id=service.program_id, fiscal_year_id=service.fiscal_year_id,
                                name=service.name, sort_order=service.sort_order, active=False)
        self.assertTrue(self.db.get(CPADMServiceActivity, mapping.id).is_active)
        self.assertFalse(service.is_active)

    def test_unclassified_activity_with_sessions_cannot_be_reclassified_retroactively(self):
        activity = self.activity(self.db)
        service = self.service(self.db)
        self.db.add(CPActivitySession(fiscal_year_id=service.fiscal_year_id, program_id=service.program_id,
                                     activity_id=activity.activity_id, session_date=date(2026, 2, 1),
                                     created_by_user_id=self.actor_id))
        self.db.flush()
        with self.assertRaisesRegex(ValueError, "sesiones registradas"):
            self.assign(self.db, service, activity)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPADMServiceActivity)), 0)

    def test_closed_year_blocks_all_existing_configuration_mutations(self):
        activity = self.activity(self.db)
        service = self.service(self.db)
        mapping = self.assign(self.db, service, activity)
        self.db.get(CPFiscalYear, self.year.fiscal_year_id).status = "closed"
        self.db.commit()
        operations = [
            lambda: associate_activity(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id, fiscal_year_id=self.year.fiscal_year_id),
            lambda: set_activity_active(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id, fiscal_year_id=self.year.fiscal_year_id, active=False),
            lambda: self.service(self.db, name="Nuevo"),
            lambda: update_adm_service_type(self.db, service_type_id=service.adm_service_type_id, program_id=service.program_id, fiscal_year_id=service.fiscal_year_id, name="Cambio", sort_order=1, active=False),
            lambda: self.assign(self.db, service, activity),
            lambda: unassign_adm_activity(self.db, service_type_id=service.adm_service_type_id, program_id=service.program_id, fiscal_year_id=service.fiscal_year_id, activity_id=activity.activity_id),
        ]
        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(ValueError, "cerrado"):
                    operation()
        self.assertTrue(self.db.get(CPADMServiceActivity, mapping.id).is_active)
        self.assertEqual(service.name, "Orientación")

    def test_copy_from_closed_year_preserves_configuration_and_uses_new_service_ids(self):
        activity = self.activity(self.db)
        service = self.service(self.db)
        self.assign(self.db, service, activity)
        set_activity_active(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id,
                            fiscal_year_id=self.year.fiscal_year_id, active=False)
        self.db.get(CPFiscalYear, self.year.fiscal_year_id).status = "closed"
        self.db.commit()
        result = copy_fiscal_configuration(self.db, self.year.fiscal_year_id, self.next_year.fiscal_year_id)
        self.assertEqual(result, {"activities": 1, "service_types": 1, "mappings": 1})
        new_service = self.db.scalar(select(CPADMServiceType).where(CPADMServiceType.fiscal_year_id == self.next_year.fiscal_year_id))
        self.assertNotEqual(new_service.adm_service_type_id, service.adm_service_type_id)
        self.assertEqual((new_service.name, new_service.sort_order), ("Orientación", 3))
        copied_activity = self.db.get(CPFiscalActivity, (activity.activity_id, self.next_year.fiscal_year_id))
        self.assertFalse(copied_activity.is_active)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPActivity)), 1)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(CPADMServiceActivity)), 2)
        self.db.rollback()
        self.assertIsNone(self.db.get(CPFiscalActivity, (activity.activity_id, self.next_year.fiscal_year_id)))

    def test_copy_rejects_self_closed_destination_and_nonempty_destination(self):
        with self.assertRaisesRegex(ValueError, "distinto"):
            copy_fiscal_configuration(self.db, self.year.fiscal_year_id, self.year.fiscal_year_id)
        self.db.get(CPFiscalYear, self.next_year.fiscal_year_id).status = "closed"
        with self.assertRaisesRegex(ValueError, "cerrado"):
            copy_fiscal_configuration(self.db, self.year.fiscal_year_id, self.next_year.fiscal_year_id)
        self.db.get(CPFiscalYear, self.next_year.fiscal_year_id).status = "active"
        self.service(self.db, fiscal_year_id=self.next_year.fiscal_year_id)
        with self.assertRaisesRegex(ValueError, "ya tiene configuración"):
            copy_fiscal_configuration(self.db, self.year.fiscal_year_id, self.next_year.fiscal_year_id)


class CommunityActivityRouteTests(ActivityDatabaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_database()
        self.role = "admin"
        self.selected_program_id = None
        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key="activity-route-test-secret")
        self.app.mount("/static", StaticFiles(directory="app/static"), name="static")
        self.app.include_router(community_activities.router)

        def context():
            return CommunityContext(SimpleNamespace(user_id=1, username="employee"), self.role,
                                    (self.voca, self.tanf), self.selected_program_id)

        def database():
            with Session(self.engine) as db:
                yield db

        self.app.dependency_overrides[require_community_context] = context
        self.app.dependency_overrides[get_db] = database
        self.client = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.client.close()
        self.remove_database()

    def page(self, area="activities"):
        return self.client.get(f"/community/{area}?program_id={self.voca.program_id}&fiscal_year_id={self.year.fiscal_year_id}")

    def token(self):
        response = self.page()
        self.assertEqual(response.status_code, 200, response.text)
        return re.search(r'name="token" value="([^"]+)"', response.text).group(1)

    def test_route_creates_activity_and_renders_only_selected_program(self):
        token = self.token()
        response = self.client.post("/community/activities", data={
            "token": token, "program_id": self.voca.program_id, "fiscal_year_id": self.year.fiscal_year_id,
            "fiscal_year_ids": [self.year.fiscal_year_id, self.next_year.fiscal_year_id],
            "code": "VOCA-01", "description": "Orientación de prueba",
        })
        self.assertEqual(response.status_code, 303, response.text)
        with Session(self.engine) as db:
            self.activity(db, program_id=self.tanf.program_id, code="TANF-PRIVATE")
            db.commit()
            self.assertEqual(db.scalar(select(func.count()).select_from(CPFiscalActivity)), 3)
        page = self.page()
        self.assertIn("VOCA-01", page.text)
        self.assertNotIn("TANF-PRIVATE", page.text)

    def test_adm_creation_assignment_and_deactivation_route(self):
        token = self.token()
        values = {"token": token, "program_id": self.voca.program_id, "fiscal_year_id": self.year.fiscal_year_id}
        response = self.client.post("/community/adm/service-types", data={**values, "name": "Servicio de prueba", "sort_order": 2})
        self.assertEqual(response.status_code, 303, response.text)
        with Session(self.engine) as db:
            activity_id = self.activity(db).activity_id
            service_id = db.scalar(select(CPADMServiceType.adm_service_type_id))
            db.commit()
        response = self.client.post(f"/community/adm/service-types/{service_id}/activities", data={**values, "activity_id": activity_id})
        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn("OR-01", self.page("adm").text)
        response = self.client.post(f"/community/adm/service-types/{service_id}/edit", data={**values, "name": "Servicio de prueba", "sort_order": 2, "active": "false"})
        self.assertEqual(response.status_code, 303)
        with Session(self.engine) as db:
            self.assertFalse(db.get(CPADMServiceType, service_id).is_active)
            self.assertTrue(db.scalar(select(CPADMServiceActivity)).is_active)

    def test_nonadmin_roles_cannot_read_or_modify_configuration(self):
        for role in ("user", "viewer", "supervisor"):
            self.role = role
            with self.subTest(role=role):
                self.assertEqual(self.page().status_code, 403)
                self.assertEqual(self.page("adm").status_code, 403)
                self.assertEqual(self.client.post("/community/activities", data={}).status_code, 403)

    def test_invalid_csrf_and_outside_context_are_rejected(self):
        token = self.token()
        values = {"token": "wrong", "program_id": self.voca.program_id, "fiscal_year_id": self.year.fiscal_year_id, "name": "Invalid"}
        self.assertEqual(self.client.post("/community/adm/service-types", data=values).status_code, 403)
        self.selected_program_id = self.tanf.program_id
        self.assertEqual(self.page().status_code, 403)
        self.assertEqual(self.client.post("/community/adm/service-types", data={**values, "token": token}).status_code, 403)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPADMServiceType)), 0)

    def test_closed_year_hides_forms_and_rejects_forged_posts(self):
        token = self.token()
        with Session(self.engine) as db:
            db.get(CPFiscalYear, self.year.fiscal_year_id).status = "closed"
            db.commit()
        self.assertNotIn('method="post" action="/community/activities"', self.page().text)
        self.assertNotIn('action="/community/adm/service-types"', self.page("adm").text)
        response = self.client.post("/community/adm/service-types", data={
            "token": token, "program_id": self.voca.program_id, "fiscal_year_id": self.year.fiscal_year_id, "name": "Invalid",
        })
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPADMServiceType)), 0)


if __name__ == "__main__":
    unittest.main()
