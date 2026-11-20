import os
import unittest
from datetime import datetime, timezone

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
