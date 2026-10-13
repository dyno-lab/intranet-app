import re
import unittest
from unittest.mock import patch

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

from tests import test_notifications as fixtures
from app.api.deps import get_db
from app.api.routes import notifications as routes
from app.models.notification import FaroAnnouncement, FaroAnnouncementRead


class NotificationRoutesTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.NotificationTests()
        with patch.object(fixtures.fixtures.fixtures, "create_engine", side_effect=lambda *_args: create_engine(
                "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)):
            self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.user = self.source.user
        self.app = FastAPI()
        self.app.add_middleware(SessionMiddleware, secret_key="notification-test-secret")
        self.app.include_router(routes.router)
        def db():
            with Session(self.source.source.source.engine) as session:
                yield session
        self.app.dependency_overrides[get_db] = db
        self.permission = patch("app.core.residential_scope._FARO_PERMISSION_DEPENDENCY", return_value=self.user).start()
        self.addCleanup(patch.stopall)
        @self.app.get("/test/residential/{rid}")
        def context(request: Request, rid: int):
            request.session["active_residential_id"] = rid
        for rid in (1, 2):
            self.source.source.source.insert("user_residentials", user_residential_id=rid,
                                            user_id=self.user.user_id, residential_id=rid, is_active=True)
        self.source.db.commit()
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def token(self):
        response = self.client.get("/ui/notifications")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.headers["cache-control"], "no-store")
        return response.json()["csrf_token"]

    def publish(self, **overrides):
        values = dict(title="Cambio de horario", message="Nuevo horario de atención.", starts_on="2000-01-01",
                      ends_on="", role_scope="all", residential_scope="all", csrf_token=self.token())
        values.update(overrides)
        return self.client.post("/ui/admin/notifications", data=values, follow_redirects=False)

    def read(self, announcement_id, token=None):
        return self.client.post("/ui/notifications/read", data={"announcement_id": announcement_id, "user_id": 999},
                                headers={"X-CSRF-Token": token if token is not None else self.token()})

    def test_publish_read_and_deactivate_through_real_routes(self):
        page = self.client.get("/ui/admin/notifications")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn('id="faro-notification-bell"', page.text)
        response = self.publish()
        self.assertEqual(response.status_code, 303, response.text)
        announcement = self.client.get("/ui/notifications").json()["items"][-1]
        aid = announcement["announcement_id"]
        self.assertTrue(announcement["unread"])
        self.assertEqual(self.read(aid).status_code, 200)
        self.assertEqual(self.read(aid).status_code, 200)
        receipt = self.source.db.scalars(select(FaroAnnouncementRead)).one()
        self.assertEqual(receipt.user_id, self.user.user_id)
        self.assertFalse(self.client.get("/ui/notifications").json()["items"][-1]["unread"])
        response = self.client.post(f"/ui/admin/notifications/{aid}/deactivate", data={"csrf_token": self.token()}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.read(aid).status_code, 404)
        self.assertTrue(all(i["type"] == "task" for i in self.client.get("/ui/notifications").json()["items"]))

    def test_csrf_and_admin_permissions_for_every_mutation(self):
        self.assertEqual(self.publish(csrf_token="invalid").status_code, 403)
        aid = self.source.publish().announcement_id
        self.assertEqual(self.read(aid, token="invalid").status_code, 403)
        self.assertEqual(self.client.post(f"/ui/admin/notifications/{aid}/deactivate", data={"csrf_token": "invalid"}).status_code, 403)
        token = self.token()
        for role in ("supervisor", "user", "viewer"):
            self.user.role = role
            self.client.get("/test/residential/1")
            self.assertEqual(self.client.get("/ui/admin/notifications").status_code, 403)
            self.assertEqual(self.client.post("/ui/admin/notifications", data={"csrf_token": token}).status_code, 403)
            self.assertEqual(self.client.post(f"/ui/admin/notifications/{aid}/deactivate", data={"csrf_token": token}).status_code, 403)
        self.assertEqual(self.source.db.scalars(select(FaroAnnouncementRead)).all(), [])

    def test_viewer_can_only_record_personal_read_receipts(self):
        aid = self.source.publish().announcement_id
        self.user.role = "viewer"
        self.assertEqual(self.read(aid).status_code, 200)
        from app.core.residential_scope import _enforce_viewer_read_only
        request = Request({"type": "http", "method": "POST", "path": "/ui/notifications/read/anything", "headers": []})
        with self.assertRaises(HTTPException) as exc:
            _enforce_viewer_read_only(request, self.user)
        self.assertEqual(exc.exception.status_code, 403)

    def test_target_audience_cannot_be_overridden_by_browser(self):
        aid = self.source.publish(residential_scope="selected", residential_ids=["2"]).announcement_id
        for role in ("user", "supervisor"):
            self.user.role = role
            self.client.get("/test/residential/1")
            response = self.client.get("/ui/notifications?residential_id=2&employee_id=-2&role=admin")
            data = response.json()
            self.assertEqual({g["residential_id"] for g in data["items"][0]["groups"]}, {1})
            self.assertEqual(len(data["items"]), 1)
            self.assertEqual(self.read(aid).status_code, 404)
            self.client.get("/test/residential/2")
            self.assertEqual(self.read(aid).status_code, 200)
            self.client.get("/test/residential/999")
            response = self.client.get("/ui/notifications", follow_redirects=False)
            self.assertEqual(response.status_code, 303)

    def test_no_session_or_no_faro_permission_is_rejected(self):
        self.permission.side_effect = HTTPException(303, headers={"Location": "/home"})
        self.assertEqual(self.client.get("/ui/notifications", follow_redirects=False).status_code, 303)
        self.permission.side_effect = HTTPException(403, "No tiene acceso a Faro")
        for path in ("/ui/notifications", "/ui/admin/notifications"):
            self.assertEqual(self.client.get(path).status_code, 403)
        self.assertEqual(self.client.post("/ui/notifications/read", data={"announcement_id": 1}).status_code, 403)

    def test_invalid_audience_preserves_form_and_html_is_not_executed(self):
        response = self.publish(role_scope="selected", title="<script>alert('x')</script>")
        self.assertEqual(response.status_code, 422, response.text)
        self.assertNotIn("<script>alert", response.text)
        self.assertIn("&lt;script&gt;", response.text)
        self.assertEqual(self.source.db.scalars(select(FaroAnnouncement)).all(), [])
        self.assertEqual(self.publish(message="<img src=x onerror=alert(1)>").status_code, 303)
        page = self.client.get("/ui/admin/notifications")
        self.assertNotIn("<img src=x", page.text)
        self.assertIn("&lt;img src=x", page.text)
        self.assertTrue(re.search(r'name="csrf_token" value="[^"]+"', page.text))


if __name__ == "__main__":
    unittest.main()
