from __future__ import annotations

import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "community-tests-session-secret-not-production")

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import get_db
from app.api.routes import community, community_settings, community_catalogs, community_activities, community_fiscal, community_operations, community_reports, community_identity, platform_settings, portal
from app.core.config import settings
from app.models.base import Base
from app.models.community import CPProgram, CPFiscalYear, CPUserAccess, CPUserProgram, CPSequence, CPParticipant, CPParticipantProgram
from app.models.community_catalog import CPCatalogType, CPCatalogOption, CPProfileField, CPProfileValue
from app.models.participant import Participant
from app.models.platform_permission import PlatformPermission
from app.models.platform_user_audit import PlatformUserAudit
from app.models.residential import Residential
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission
from app.models.user_residential import UserResidential
from app.services.community import create_participant, create_program


class CommunityRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.temp.name) / 'web.db'}")

        @event.listens_for(self.engine, "connect")
        def sqlite_functions(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.create_function("sysutcdatetime", 0, lambda: datetime.now(timezone.utc).isoformat())

        models = (Residential, User, UserResidential, PlatformPermission, UserPlatformPermission, PlatformUserAudit,
                  CPProgram, CPFiscalYear, CPUserAccess, CPUserProgram, CPSequence, CPParticipant, CPParticipantProgram,
                  CPCatalogType, CPCatalogOption, CPProfileField, CPProfileValue)
        Base.metadata.create_all(self.engine, tables=list({model.__table__ for model in (*models, Participant)} | {table for table in Base.metadata.tables.values() if table.name.startswith('cp_')}))
        with Session(self.engine) as db:
            users = [User(username=f"employee-{i}", email=f"employee-{i}@example.com", password_hash="test-only",
                          role=role, is_active=True, session_version=1) for i, role in enumerate(("admin", "admin", "viewer", "user"), 1)]
            db.add_all(users)
            db.flush()
            self.admin_id, self.viewer_id, self.user_id, self.denied_id = [user.user_id for user in users]
            permissions = [PlatformPermission(key=key, name=key) for key in ("access_community", "access_portal_home", "manage_platform_settings")]
            db.add_all(permissions)
            db.flush()
            for user in users:
                db.add(UserPlatformPermission(user_id=user.user_id, permission_id=permissions[1].permission_id))
                if user.user_id != self.denied_id:
                    db.add(UserPlatformPermission(user_id=user.user_id, permission_id=permissions[0].permission_id))
            db.add(UserPlatformPermission(user_id=self.admin_id, permission_id=permissions[2].permission_id))
            db.add_all([CPUserAccess(user_id=self.admin_id, role="admin"), CPUserAccess(user_id=self.viewer_id, role="viewer"), CPUserAccess(user_id=self.user_id, role="user")])
            first = create_program(db, "VOCA", "Programa VOCA")
            second = create_program(db, "TANF-M", "Programa TANF-M")
            third = create_program(db, "ICP", "Programa ICP")
            self.voca_id, self.tanf_id, self.icp_id = first.program_id, second.program_id, third.program_id
            db.add_all([CPUserProgram(user_id=self.user_id, program_id=self.voca_id), CPUserProgram(user_id=self.user_id, program_id=self.tanf_id)])
            db.commit()

        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key="local-community-test-session-secret")
        self.app.mount("/static", StaticFiles(directory="app/static"), name="static")
        self.app.include_router(community.router)
        self.app.include_router(community_settings.router)
        self.app.include_router(community_catalogs.router)
        self.app.include_router(community_activities.router)
        self.app.include_router(community_fiscal.router)
        self.app.include_router(community_operations.router)
        self.app.include_router(community_reports.router)
        self.app.include_router(community_identity.router)
        self.app.include_router(platform_settings.router)
        self.app.include_router(portal.router)

        @self.app.get("/_test/session/{user_id}")
        def test_session(user_id: int, request: Request):
            request.session.clear()
            request.session.update(user_id=user_id, session_version=1)
            return {"ok": True}

        def test_db():
            with Session(self.engine) as db:
                yield db
        self.app.dependency_overrides[get_db] = test_db
        self.flag = patch.object(settings, "COMMUNITY_ENABLED", True)
        self.flag.start()
        self.client = TestClient(self.app, follow_redirects=False)

    def tearDown(self):
        self.client.close()
        self.flag.stop()
        self.engine.dispose()
        self.temp.cleanup()

    def token(self, response):
        self.assertEqual(response.status_code, 200, response.text)
        match = re.search(r'name="token" value="([^"]+)"', response.text)
        self.assertIsNotNone(match, response.text)
        return match.group(1)

    def login(self, user_id=None, program="all"):
        self.client.get(f"/_test/session/{user_id or self.admin_id}")
        token = self.token(self.client.get("/community/login"))
        response = self.client.post("/community/context", data={"program": program, "token": token})
        self.assertEqual(response.status_code, 303, response.text)
        return token

    def participant_data(self, token, **changes):
        values = {"token": token, "exp_year": "2026", "nombre": "Ana", "apellido_paterno": "Rivera",
                  "genero": "F", "fecha_nacimiento": "2000-05-12", "direccion_fisica": "Calle Prueba",
                  "pueblo": "Ponce", "program_ids": [self.voca_id, self.tanf_id]}
        values.update(changes)
        return values

    def test_program_and_fiscal_year_creation_with_configurable_dates(self):
        token = self.login()
        response = self.client.post("/community/programs", data={"token": token, "code": "ICCa", "name": "Programa ICCa"})
        self.assertEqual(response.status_code, 303)
        self.assertIn("ICCa", self.client.get("/community/programs").text)
        response = self.client.post("/community/fiscal-years", data={"token": token, "code": "2026-27", "name": "Fiscal configurable", "start_date": "2026-10-01", "end_date": "2027-09-30"})
        self.assertEqual(response.status_code, 303)
        page = self.client.get("/community/fiscal-years")
        self.assertIn("01/10/2026", page.text)
        self.assertIn("30/09/2027", page.text)

    def test_create_one_expediente_with_two_program_numbers(self):
        token = self.login(self.user_id)
        response = self.client.post("/community/participants", data=self.participant_data(token))
        self.assertEqual(response.status_code, 303, response.text)
        detail = self.client.get(response.headers["location"])
        self.assertEqual(detail.status_code, 200, detail.text)
        for number in ("CP-2026-0001", "CP-2026-VOCA-0001", "CP-2026-TANF-M-0001"):
            self.assertIn(number, detail.text)
        self.assertIn("Ponce", detail.text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 1)
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipantProgram)), 2)

    def test_independent_viewer_role_blocks_writes_even_for_faro_admin(self):
        token = self.login(self.viewer_id)
        self.assertEqual(self.client.get("/community/participants").status_code, 200)
        self.assertEqual(self.client.get("/community/participants/new").status_code, 403)
        self.assertEqual(self.client.post("/community/participants", data=self.participant_data(token)).status_code, 403)
        for path in ("programs", "fiscal-years"):
            self.assertEqual(self.client.get(f"/community/{path}").status_code, 403)

    def test_user_cannot_write_admin_configuration_or_select_unassigned_program(self):
        token = self.login(self.user_id)
        self.assertEqual(self.client.post("/community/programs", data={"token": token, "code": "SP", "name": "SP"}).status_code, 403)
        self.assertEqual(self.client.get("/community/programs").status_code, 403)
        self.assertEqual(self.client.post("/community/context", data={"token": token, "program": self.icp_id}).status_code, 403)
        self.assertEqual(self.client.post("/community/participants", data=self.participant_data(token, program_ids=[self.icp_id])).status_code, 403)

    def test_record_outside_user_programs_is_not_readable(self):
        with Session(self.engine) as db:
            p = create_participant(db, actor_user_id=self.admin_id, exp_year=2026, program_ids=[self.icp_id], fields={"nombre": "Reservado", "apellido_paterno": "Prueba", "genero": "F"})
            db.commit()
            participant_id = p.participant_id
        self.login(self.user_id)
        self.assertNotIn("Reservado", self.client.get("/community/participants").text)
        self.assertEqual(self.client.get(f"/community/participants/{participant_id}").status_code, 404)

    def test_selected_context_restricts_creation_even_if_other_program_assigned(self):
        token = self.login(self.user_id, program=str(self.voca_id))
        self.assertEqual(self.client.post("/community/participants", data=self.participant_data(token)).status_code, 403)
        self.assertEqual(self.client.post("/community/participants", data=self.participant_data(token, program_ids=[self.voca_id])).status_code, 303)

    def test_revoked_assignment_is_rechecked_on_next_request(self):
        self.login(self.user_id, program=str(self.voca_id))
        with Session(self.engine) as db:
            db.delete(db.get(CPUserProgram, (self.user_id, self.voca_id)))
            db.commit()
        response = self.client.get("/community/participants")
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/community/login")

    def test_csrf_and_missing_permission_are_enforced(self):
        self.login()
        self.assertEqual(self.client.post("/community/programs", data={"token": "wrong", "code": "SP", "name": "SP"}).status_code, 403)
        self.client.get(f"/_test/session/{self.denied_id}")
        self.assertEqual(self.client.get("/community/login").status_code, 403)
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/community/login").headers["location"], "/home")

    def test_module_is_hidden_and_unavailable_when_disabled(self):
        self.login()
        with patch.object(settings, "COMMUNITY_ENABLED", False):
            self.assertEqual(self.client.get("/community").status_code, 404)
            self.assertNotIn('href="/community/login"', self.client.get("/home").text)

    def test_portal_link_depends_on_permission(self):
        self.client.get(f"/_test/session/{self.user_id}")
        self.assertIn('href="/community/login"', self.client.get("/home").text)
        self.client.get(f"/_test/session/{self.denied_id}")
        self.assertNotIn('href="/community/login"', self.client.get("/home").text)

    def test_settings_changes_community_role_without_changing_faro_role(self):
        self.login()
        path = f"/platform/settings/users/{self.user_id}/community"
        token = self.token(self.client.get(path))
        response = self.client.post(path, data={"token": token, "role": "supervisor", "enabled": "on", "program_ids": [self.voca_id]})
        self.assertEqual(response.status_code, 303, response.text)
        with Session(self.engine) as db:
            self.assertEqual(db.get(User, self.user_id).role, "viewer")
            self.assertEqual(db.get(CPUserAccess, self.user_id).role, "supervisor")
            self.assertEqual(db.scalar(select(func.count()).select_from(PlatformUserAudit)), 1)

    def test_settings_rejects_user_access_without_programs(self):
        self.login()
        path = f"/platform/settings/users/{self.user_id}/community"
        token = self.token(self.client.get(path))
        self.assertEqual(self.client.post(path, data={"token": token, "role": "user", "enabled": "on"}).status_code, 422)
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(CPUserProgram).where(CPUserProgram.user_id == self.user_id)).all()), 2)

    def test_registration_error_preserves_form_values(self):
        token = self.login(self.user_id)
        response = self.client.post("/community/participants", data=self.participant_data(token, telefono="invalid"))
        self.assertEqual(response.status_code, 200)
        self.assertIn('value="Ana"', response.text)
        self.assertIn("(XXX)-XXX-XXXX", response.text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 0)

    def test_creation_form_uses_address_and_auto_number(self):
        self.login(self.user_id)
        response = self.client.get("/community/participants/new")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="direccion_fisica"', response.text)
        self.assertNotIn('name="exp_seq4"', response.text)
        self.assertNotIn('name="residential_id"', response.text)
        self.assertIn('name="program_ids"', response.text)

    def test_basic_lookup_and_association_preserve_one_record_and_restrict_data(self):
        with Session(self.engine) as db:
            p = create_participant(db, actor_user_id=self.admin_id, exp_year=2026, program_ids=[self.icp_id], fields={"nombre": "Existente", "apellido_paterno": "Rivera", "genero": "F", "email": "private@example.com"})
            db.commit()
            pid = p.participant_id
        token = self.login(self.user_id)
        response = self.client.get("/community/participants/lookup?q=Existente")
        self.assertIn("Existente", response.text)
        self.assertNotIn("private@example.com", response.text)
        self.assertNotIn("Programa ICP", response.text)
        self.assertEqual(self.client.get(f"/community/participants/{pid}").status_code, 404)
        response = self.client.post(f"/community/participants/{pid}/programs", data={"token": token, "program_ids": [self.voca_id]})
        self.assertEqual(response.status_code, 303)
        self.assertIn("CP-2026-VOCA-0001", self.client.get(response.headers["location"]).text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 1)

    def test_only_supervisor_or_admin_may_edit_common_data(self):
        token = self.login(self.user_id)
        response = self.client.post("/community/participants", data=self.participant_data(token))
        path = response.headers["location"].split("?")[0]
        self.assertEqual(self.client.get(path + "/edit").status_code, 403)
        self.assertEqual(self.client.post(path + "/edit", data=self.participant_data(token)).status_code, 403)
        with Session(self.engine) as db:
            db.get(CPUserAccess, self.user_id).role = "supervisor"
            db.commit()
        self.assertEqual(self.client.get(path + "/edit").status_code, 200)
        response = self.client.post(path + "/edit", data=self.participant_data(token, pueblo="Mayagüez"))
        self.assertEqual(response.status_code, 303)
        self.assertIn("Mayagüez", self.client.get(path).text)

    def test_dynamic_profile_required_and_catalog_value_are_validated(self):
        token = self.login()
        self.assertEqual(self.client.post("/community/catalogs/options", data={"token": token, "field_key": "escolaridad_participante", "value": "Universidad"}).status_code, 303)
        self.assertEqual(self.client.post("/community/catalogs/fields", data={"token": token, "field_key": "referencia", "label": "Referencia", "field_type": "text", "is_required": "on"}).status_code, 303)
        token = self.login(self.user_id)
        data = self.participant_data(token, escolaridad_participante="Universidad")
        self.assertIn("Referencia es requerido", self.client.post("/community/participants", data=data).text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 0)
            field_id = db.scalar(select(CPProfileField.field_id))
        data[f"profile_{field_id}"] = "Referencia de prueba"
        response = self.client.post("/community/participants", data=data)
        self.assertEqual(response.status_code, 303, response.text)
        self.assertIn("Referencia de prueba", self.client.get(response.headers["location"]).text)

    def test_disabling_last_catalog_choice_does_not_allow_free_text(self):
        token = self.login()
        self.client.post("/community/catalogs/options", data={"token": token, "field_key": "pueblo", "value": "Ponce"})
        with Session(self.engine) as db:
            db.scalar(select(CPCatalogOption)).is_active = False
            db.commit()
        page = self.client.get("/community/participants/new")
        self.assertRegex(page.text, r'<select[^>]+id="pueblo"')
        response = self.client.post("/community/participants", data=self.participant_data(token))
        self.assertIn("Seleccione una opción vigente para Pueblo", response.text)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(CPParticipant)), 0)


if __name__ == "__main__":
    unittest.main()
