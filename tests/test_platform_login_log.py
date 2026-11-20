import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

from authlib.integrations.base_client.errors import OAuthError

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from app.api.deps import get_db
from app.api.routes import auth, platform_settings
from app.core.platform_permissions import MANAGE_PLATFORM_SETTINGS
from app.core.security import hash_password
from app.models.base import Base
from app.models.platform_login_event import PlatformLoginEvent
from app.models.platform_permission import PlatformPermission
from app.models.residential import Residential
from app.models.user import User
from app.models.user_platform_permission import UserPlatformPermission
from app.models.user_residential import UserResidential
from app.services.platform_login_log import access_history, last_success_by_user
from tests.test_google_oauth import CONFIGURATION, _claims, _enabled_configuration


class PlatformLoginLogTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
        self.addCleanup(self.engine.dispose)

        @event.listens_for(self.engine, "connect")
        def configure_sqlite(connection, _):
            connection.create_function("sysutcdatetime", 0, lambda: datetime.now(timezone.utc).isoformat())

        models = (PlatformLoginEvent, PlatformPermission, Residential, User, UserPlatformPermission, UserResidential)
        Base.metadata.create_all(self.engine, tables=[model.__table__ for model in models])
        with Session(self.engine) as db:
            password_hash = hash_password("test-password")
            manager = User(username="manager", role="admin", email="manager@example.org", password_hash=password_hash)
            staff = User(username="staff", password_hash=password_hash)
            permission = PlatformPermission(key=MANAGE_PLATFORM_SETTINGS, name="Configuración")
            db.add_all([manager, staff, permission])
            db.flush()
            self.manager_id = manager.user_id
            db.add(UserPlatformPermission(user_id=manager.user_id, permission_id=permission.permission_id))
            db.commit()

        app = FastAPI()
        app.include_router(auth.router)
        app.include_router(platform_settings.router)
        app.mount("/static", StaticFiles(directory="app/static"), name="static")
        app.add_middleware(SessionMiddleware, secret_key="platform-login-history-test-secret")

        def test_db():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = test_db
        self.client = TestClient(app, follow_redirects=False)
        self.addCleanup(self.client.close)
        self.log = "/platform/settings/access-log"

    def login(self, username, password):
        return self.client.post("/login", data={"username": username, "password": password})

    def test_login_audit_and_permission_through_platform_routes(self):
        self.assertEqual(self.client.get(self.log).status_code, 303)
        self.assertEqual(self.login("staff", "test-password").status_code, 303)
        self.assertEqual(self.client.get(self.log).status_code, 403)
        self.assertEqual(self.login("manager", "test-password").status_code, 303)
        with Session(self.engine) as db:
            success = db.scalars(select(PlatformLoginEvent).where(PlatformLoginEvent.user_id == self.manager_id)).one()
            success.occurred_at = datetime(2026, 1, 15, 16, 30, tzinfo=timezone.utc)
            db.commit()

        for unknown_or_known in ("unknown@example.net", "manager"):
            self.assertEqual(self.login(unknown_or_known, "wrong-test-password").status_code, 200)

        with Session(self.engine) as db:
            rows = db.scalars(select(PlatformLoginEvent).order_by(PlatformLoginEvent.event_id)).all()
            self.assertEqual([r.outcome for r in rows], ["success", "success", "unknown_account", "invalid_password"])
            self.assertIsNone(rows[2].user_id)
            self.assertEqual(last_success_by_user(db)[self.manager_id].date(), datetime(2026, 1, 15).date())

        settings = self.client.get("/platform/settings")
        self.assertEqual(settings.status_code, 200)
        self.assertIn("15/01/2026 12:30 PM", settings.text)
        personal = self.client.get(self.log, params={"usuario_id": self.manager_id})
        self.assertEqual(personal.status_code, 200)
        self.assertEqual(personal.headers["Cache-Control"], "no-store")
        self.assertIn("Credenciales incorrectas", personal.text)
        self.assertNotIn("unknown@example.net", personal.text)
        self.assertNotIn("wrong-test-password", personal.text)
        rejected = self.client.get(self.log, params={"resultado": "no-autorizados", "cuenta": "UNKNOWN@EXAMPLE.NET"})
        self.assertEqual(rejected.status_code, 200)
        self.assertIn("unknown@example.net", rejected.text)
        self.assertIn("Cuenta no registrada", rejected.text)
        self.assertNotIn("Credenciales incorrectas", rejected.text)

    def test_email_search_recognizes_an_existing_session_without_inventing_a_login(self):
        # A session established before the login audit existed still has a valid user and version.
        with patch.object(auth, "record_login_event"):
            self.assertEqual(self.login("manager", "test-password").status_code, 303)

        params = {"cuenta": " MANAGER@example.org ", "resultado": "no-autorizados"}
        for _ in range(2):
            page = self.client.get(self.log, params=params)
            self.assertEqual(page.status_code, 200)
            self.assertIn("Estás usando esta cuenta", page.text)
            self.assertIn("Aún no hay un inicio de sesión registrado para esta cuenta.", page.text)

        with Session(self.engine) as db:
            self.assertEqual(db.scalars(select(PlatformLoginEvent)).all(), [])
        self.client.post("/logout")
        self.assertEqual(self.login("manager", "test-password").status_code, 303)
        with Session(self.engine) as db:
            success = db.scalars(select(PlatformLoginEvent)).one()
            success.occurred_at = datetime(2026, 2, 5, 18, 15, tzinfo=timezone.utc)
            db.commit()

        page = self.client.get(self.log, params=params)
        self.assertIn("Último inicio de sesión registrado", page.text)
        self.assertIn("05/02/2026 02:15 PM", page.text)
        self.assertIn("No hay accesos registrados con estos filtros", page.text)

    def test_new_account_search_is_not_limited_to_the_previous_user(self):
        self.assertEqual(self.login("manager", "test-password").status_code, 303)
        staff = self.client.get(self.log, params={"usuario_id": self.manager_id, "cuenta": "staff"})
        self.assertIn("Historial de staff", staff.text)
        self.assertNotIn("Estás usando esta cuenta", staff.text)
        self.assertNotIn("Ingreso exitoso</span>", staff.text)
        unknown = self.client.get(self.log, params={"cuenta": "unknown@example.org"})
        self.assertNotIn("Estás usando esta cuenta", unknown.text)
        self.assertNotIn("Último inicio de sesión registrado", unknown.text)

    def google_client(self):
        # Use Authlib's real redirect and signed-session state, with offline provider metadata.
        client = auth.create_google_oauth_client(CONFIGURATION)
        client.load_server_metadata = AsyncMock(return_value={"authorization_endpoint": "https://accounts.google.com/"})
        return client

    def test_google_hosted_block_is_visible_without_guessing_the_email(self):
        self.login("manager", "test-password")
        with TestClient(self.client.app, follow_redirects=False) as visitor, _enabled_configuration(), patch.object(
            auth, "create_google_oauth_client", return_value=self.google_client()
        ):
            self.assertTrue(visitor.get("/auth/google").is_redirect)
            # Google shows its own rejection page and never redirects the visitor back.
            with Session(self.engine) as db:
                attempts = db.scalars(select(PlatformLoginEvent).where(PlatformLoginEvent.method == "google")).all()
                self.assertEqual(len(attempts), 1)
                self.assertEqual(attempts[0].outcome, "google_pending")
                self.assertIsNone(attempts[0].identifier)
                self.assertIsNone(attempts[0].user_id)
                self.assertEqual(set(last_success_by_user(db)), {self.manager_id})

        pending = self.client.get(self.log, params={"resultado": "sin-respuesta"})
        self.assertEqual(pending.status_code, 200)
        self.assertIn("Sin respuesta de Google", pending.text)
        self.assertIn("Sin identidad comprobada", pending.text)
        for outcome in ("denegados", "exitosos", "no-autorizados"):
            filtered = self.client.get(self.log, params={"resultado": outcome})
            self.assertNotIn("Sin identidad comprobada", filtered.text)

    def test_google_return_completes_the_original_row(self):
        with Session(self.engine) as db:
            staff = db.scalar(select(User).where(User.username == "staff"))
            staff.google_sub = "google-subject-123"
            staff_id = staff.user_id
            db.commit()

        cases = [
            ({"userinfo": _claims()}, None, 303, "success", "employee@csifpr.org", staff_id),
            ({"userinfo": _claims(sub="unregistered")}, None, 403, "unknown_account", "employee@csifpr.org", None),
            ({}, OAuthError(error="access_denied"), 400, "unverified", None, None),
            ({}, None, 400, "unverified", None, None),
        ]
        for count, (token, error, status, outcome, email, user_id) in enumerate(cases, 1):
            with self.subTest(outcome=outcome), _enabled_configuration(), patch.object(
                auth, "new_google_nonce", return_value="expected-nonce"
            ), patch.object(auth, "create_google_oauth_client", return_value=self.google_client()) as oauth:
                oauth.return_value.authorize_access_token = AsyncMock(return_value=token, side_effect=error)
                start = self.client.get("/auth/google")
                self.assertTrue(start.is_redirect)
                state = parse_qs(urlsplit(start.headers["location"]).query)["state"][0]
                with Session(self.engine) as db:
                    initial = db.scalars(select(PlatformLoginEvent).order_by(PlatformLoginEvent.event_id.desc())).first()
                    self.assertIsNotNone(initial)
                    event_id = initial.event_id
                    self.assertEqual(initial.outcome, "google_pending")
                callback = self.client.get("/auth/google/callback", params={"state": state})
                self.assertEqual(callback.status_code, status)
                with Session(self.engine) as db:
                    rows = db.scalars(select(PlatformLoginEvent).order_by(PlatformLoginEvent.event_id)).all()
                    self.assertEqual(len(rows), count)
                    row = rows[-1]
                    self.assertEqual((row.event_id, row.outcome, row.identifier, row.user_id),
                                     (event_id, outcome, email, user_id))

    def test_filtered_pages_do_not_repeat_events_when_another_login_arrives(self):
        with Session(self.engine) as db:
            db.add_all([PlatformLoginEvent(method="google", outcome="success", user_id=self.manager_id)
                        for _ in range(51)])
            db.commit()
            filters = {"result": "exitosos", "account": "manager@example.org", "user_id": self.manager_id}
            first, cursor = access_history(db, before=None, **filters)
            self.assertEqual(len(first), 50)
            first_ids = {row[0].event_id for row in first}
            db.add(PlatformLoginEvent(method="google", outcome="success", user_id=self.manager_id))
            db.commit()
            second, tail = access_history(db, before=cursor, **filters)
            self.assertEqual(len(second), 1)
            self.assertNotIn(second[0][0].event_id, first_ids)
            self.assertIsNone(tail)
