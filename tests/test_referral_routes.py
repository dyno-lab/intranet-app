import re
import unittest

from fastapi import Depends
from sqlalchemy import select

from tests import test_notification_routes as fixtures
from app.api.routes import reports
from app.core.auth import get_current_user
from app.core.residential_scope import require_faro_access
from app.models.visit_report import VisitReport
from app.models.visit_report_referral import VisitReportReferral


class ReferralRoutesTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.NotificationRoutesTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.client, self.user = self.source.client, self.source.user
        self.db = self.source.source.db
        self.tables = self.source.source.source.source.tables
        self.db.execute(self.tables["activity_codes"].update().values(code="4.g.3"))
        self.db.commit()
        self.source.app.include_router(reports.router, prefix="/ui/reports", dependencies=[Depends(require_faro_access)])
        self.source.app.dependency_overrides[get_current_user] = lambda: self.user
        self.params = dict(proposal_id=1, month=7, year=2026, employee_id=-1)

    def prepare(self, **overrides):
        response = self.client.get("/ui/reports/visitas", params={**self.params, **overrides})
        self.assertEqual(response.status_code, 200, response.text)
        token = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        return response, token.group(1) if token else ""

    def save(self, **overrides):
        values = {**self.params, "csrf_token": self.prepare()[1], "referral_count": 1,
                  "referral_type_0": "Interno", "agency_0": "Agencia de prueba", "reference_or_purpose_0": "Orientación"}
        values.update(overrides)
        return self.client.post("/ui/reports/visitas/referrals/save", data=values, follow_redirects=False)

    def pending(self):
        items = self.client.get("/ui/notifications").json()["items"]
        return next(item["pending_count"] for item in items if item["id"] == "referrals:visits")

    def test_reminder_save_and_delete_end_to_end(self):
        self.assertEqual(self.pending(), 5)
        page, token = self.prepare()
        self.assertIn("Información de referidos pendiente.", page.text)
        self.assertIn('id="visit-referrals"', page.text)
        self.assertIn("Visita Agencia", page.text)
        for kind in ("Interno", "Externo", "Visita Agencia"):
            saved = self.save(referral_type_0=kind)
            self.assertEqual(saved.status_code, 303, saved.text)
            self.assertIn("Referidos%20guardados", saved.headers["location"])
            self.assertEqual(self.pending(), 4)
            page, token = self.prepare()
            self.assertNotIn("Información de referidos pendiente.", page.text)
            self.assertIn("Agencia de prueba", page.text)
        deleted = self.client.post("/ui/reports/visitas/delete", data={**self.params, "csrf_token": token}, follow_redirects=False)
        self.assertEqual(deleted.status_code, 303)
        self.assertEqual(self.pending(), 5)
        page, _ = self.prepare()
        self.assertIn('name="referral_count" value="1"', page.text)

    def test_partial_and_oversized_rows_preserve_existing_data_and_reminder(self):
        for values in ({"agency_0": " "}, {"reference_or_purpose_0": ""}, {"referral_type_0": "Otro"},
                       {"referral_count": 21}, {"referral_count": -1}, {"agency_0": "a" * 256}):
            with self.subTest(values=values):
                self.assertEqual(self.save(**values).status_code, 422)
                self.assertEqual(self.pending(), 5)
                self.db.expire_all()
                self.assertEqual(self.db.scalars(select(VisitReportReferral)).one().agency, "Agencia")
        self.assertEqual(self.save(referral_count=0).status_code, 303)
        self.assertEqual(self.pending(), 5)

    def test_csrf_and_viewer_cannot_modify_referrals(self):
        self.assertEqual(self.save(csrf_token="bad").status_code, 403)
        token = self.prepare()[1]
        self.assertEqual(self.client.post("/ui/reports/visitas/delete", data={**self.params, "csrf_token": "bad"}).status_code, 403)
        self.user.role = "viewer"
        page, _ = self.prepare()
        self.assertNotIn('id="visitReferralsForm"', page.text)
        self.assertEqual(self.client.post("/ui/reports/visitas/referrals/save", data={**self.params, "csrf_token": token}).status_code, 403)
        self.assertEqual(self.client.post("/ui/reports/visitas/delete", data={**self.params, "csrf_token": token}).status_code, 403)

    def test_closed_or_finalized_periods_cannot_dismiss_referral_reminder(self):
        table = self.tables["proposals"]
        for values in ({"locked_through_month": 7, "locked_through_year": 2026}, {"status": "finalized"}):
            self.db.execute(table.update().where(table.c.proposal_id == 1).values(**values))
            self.db.commit()
            page, token = self.prepare()
            self.assertNotIn("<span>Guardar referidos</span>", page.text)
            saved = self.save()
            self.assertEqual(saved.status_code, 303)
            self.assertIn("Error", saved.headers["location"])
            self.assertEqual(self.pending(), 5)
            deleted = self.client.post("/ui/reports/visitas/delete", data={**self.params, "csrf_token": token}, follow_redirects=False)
            self.assertEqual(deleted.status_code, 303)
            self.assertIn("Error", deleted.headers["location"])

    def test_residential_scope_is_server_controlled_for_users_and_supervisors(self):
        for role in ("user", "supervisor"):
            self.user.role = role
            self.client.get("/test/residential/2")
            page, _ = self.prepare(employee_id=-1, proposal_id=2)
            self.assertIn('name="employee_id" value="-2"', page.text)
            self.assertEqual(self.save(proposal_id=2, employee_id=-1).status_code, 303)
            self.db.expire_all()
            report = self.db.scalars(select(VisitReport).where(VisitReport.residential_id == 2)).one()
            rows = self.db.scalars(select(VisitReportReferral).where(VisitReportReferral.report_id == report.report_id)).all()
            self.assertEqual(len(rows), 1)
            # R1's incomplete report was never changed by a forged filter.
            self.assertEqual(self.db.scalars(select(VisitReportReferral).where(VisitReportReferral.report_id == 1)).one().agency, "Agencia")
            self.client.get("/test/residential/999")
            self.assertEqual(self.client.get("/ui/notifications", follow_redirects=False).status_code, 303)


if __name__ == "__main__":
    unittest.main()
