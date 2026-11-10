"""The budget prototype must use the portal session and stay read-only on the server."""
import unittest

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from tests.test_platform_settings import _Database, _Result, _user
from app.api.deps import get_db
from app.api.routes import portal
from app.core.platform_permissions import ACCESS_AUTOMATION, ACCESS_PORTAL_HOME


class AutomationMockupTests(unittest.TestCase):
    def setUp(self):
        self.user = _user(17, "mockup-test", role="supervisor")
        self.db = _Database(users={17: self.user})
        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key="mockup-test-only")
        self.app.mount("/static", StaticFiles(directory="app/static"), name="static")
        self.app.include_router(portal.router)
        self.app.dependency_overrides[get_db] = lambda: self.db

        @self.app.get("/test/session/{version}")
        def session(request: Request, version: int):
            request.session.update(user_id=17, session_version=version)

        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def login(self, permissions=(ACCESS_AUTOMATION,)):
        self.client.get("/test/session/1")
        self.db.results.append(_Result(list(permissions)))

    def test_anonymous_is_redirected_to_portal(self):
        response = self.client.get("/automatizaciones", follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/home")
        self.assertNotIn("faro-budget-design", response.text)

    def test_permission_is_required_even_for_admin(self):
        self.user.role = "admin"
        self.login(())
        response = self.client.get("/automatizaciones")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("faro-budget-design", response.text)

    def test_revoked_and_inactive_sessions_are_rejected(self):
        for inactive in (False, True):
            with self.subTest(inactive=inactive):
                self.user.is_active = not inactive
                self.client.get("/test/session/1" if inactive else "/test/session/0")
                response = self.client.get("/automatizaciones", follow_redirects=False)
                self.assertEqual(response.status_code, 303)

    def test_authorized_page_renders_demo_without_database_writes(self):
        self.login()
        response = self.client.get("/automatizaciones")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('id="faro-budget-design"', response.text)
        self.assertIn("Datos de prueba", response.text)
        self.assertIn("se reinician al recargar", response.text)
        self.assertIn("Revisión por categoría", response.text)
        self.assertIn('href="/home"', response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.db.commits, 0)
        self.assertEqual(self.db.added, [])
        self.assertEqual(self.db.deleted, [])
        self.assertEqual(len(self.db.statements), 1, "Only permission lookup is expected.")

    def test_no_server_mutation_endpoint(self):
        self.login()
        response = self.client.post("/automatizaciones", data={"amount": 100})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(self.db.commits, 0)

    def test_portal_links_to_mockup_only_with_permission(self):
        self.login((ACCESS_PORTAL_HOME, ACCESS_AUTOMATION))
        response = self.client.get("/home")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/automatizaciones"', response.text)
        self.db.results.append(_Result([ACCESS_PORTAL_HOME]))
        response = self.client.get("/home")
        self.assertNotIn('href="/automatizaciones"', response.text)


if __name__ == "__main__":
    unittest.main()
