import re
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import func, select

from tests import test_participant_transfers as fixtures
from app.api.deps import get_db
from app.api.routes.participant_transfers import router
from app.core.auth import get_current_user
from app.models.participant_transfer import ParticipantTransfer


class ParticipantTransferRouteTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ParticipantTransferTests()
        self.fixture.setUp()
        f = self.fixture
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="transfer-tests-only")
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: f.db
        app.dependency_overrides[get_current_user] = lambda: f.actor
        self.client = TestClient(app)
        self.url = f"/ui/new-list/{f.participant.participant_id}/transfer"
        page = self.client.get(self.url)
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="token" value="([^"]+)"', page.text)[1]
        self.form = dict(destination_id=f.b.residential_id, expected_residential_id=f.a.residential_id,
                         effective_date="2026-10-01", reason="Mudanza", edificio="4", apart="20", token=token)

    def tearDown(self):
        self.client.close()
        self.fixture.tearDown()

    def test_preview_confirm_and_history(self):
        f = self.fixture
        response = self.client.post(self.url, data={**self.form, "mode": "preview"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("FE-2026-B-0002", response.text)
        self.assertEqual(f.db.scalar(select(func.count()).select_from(ParticipantTransfer)), 0)
        response = self.client.post(self.url, data={**self.form, "mode": "confirm",
                                    "expected_expediente_num": "FE-2026-B-0002"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(f.participant.residential_id, f.b.residential_id)
        history = self.client.get(self.url)
        self.assertEqual(history.status_code, 200)
        self.assertIn("FE-2026-A-0001", history.text)
        self.assertIn("Mudanza", history.text)
        replay = self.client.post(self.url, data={**self.form, "mode": "confirm",
                                  "expected_expediente_num": "FE-2026-B-0002"})
        self.assertEqual(replay.status_code, 409)
        self.assertEqual(f.db.scalar(select(func.count()).select_from(ParticipantTransfer)), 1)

    def test_csrf_and_residential_context_cannot_transfer(self):
        self.assertEqual(self.client.post(self.url, data={**self.form, "token": "wrong"}).status_code, 403)
        self.fixture.actor._active_residential_id = self.fixture.a.residential_id
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, data=self.form).status_code, 403)
        self.assertIsNone(self.fixture.old.valid_until)

    def test_viewer_and_regular_user_cannot_get_or_post(self):
        for role in ("viewer", "user"):
            self.fixture.actor.role = role
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.post(self.url, data=self.form).status_code, 403)
