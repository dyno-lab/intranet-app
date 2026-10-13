from datetime import date
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from sqlalchemy import event
from sqlalchemy.dialects import mssql

from tests import test_notifications as fixtures
from app.services.notifications import notification_feed
from app.services.referral_requirements import REFERRAL_ACTIVITY_CODES, pending_referral_groups
from app.services.visits import replace_visit_report_referrals


class ReferralNotificationTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.NotificationTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.db, self.user = self.source.db, self.source.user
        self.tables = self.source.source.source.tables
        self.db.execute(self.tables["activity_codes"].update().values(code="1.a.3"))
        self.db.commit()

    def feed(self, user=None):
        return notification_feed(self.db, user or self.user, today=date(2026, 8, 15))

    def test_exact_32_codes_with_dots_and_no_accidental_extra_activities(self):
        expected = {
            "1.a.3", "1.b.3", "1.c.3", "1.a.10", "1.b.10", "1.c.10",
            "2.a.3", "2.b.3", "2.c.3", "2.e.3",
            "3.a.3", "3.b.3", "3.c.3", "3.d.3",
            "3.a.11", "3.b.11", "3.c.11", "3.d.11",
            "3.a.21", "3.b.21", "3.c.21", "3.d.21", "3.e.21", "3.f.21", "3.g.21",
            "4.a.3", "4.b.3", "4.c.3", "4.d.3", "4.e.3", "4.f.3", "4.g.3",
        }
        self.assertEqual(set(REFERRAL_ACTIVITY_CODES), expected)
        self.assertEqual(len(REFERRAL_ACTIVITY_CODES), 32)
        for code in sorted(expected) + ["4.G.3", "2.d.3", "3.e.3", "4.g.30", "4g3", "2.b.5"]:
            with self.subTest(code=code):
                self.db.execute(self.tables["activity_codes"].update().values(code=code))
                self.db.commit()
                groups = pending_referral_groups(self.db, today=date(2026, 8, 15))
                self.assertEqual(len(groups), 5 if code.lower() in expected else 0)

    def test_one_pending_report_per_proposal_residential_month_with_direct_links(self):
        task = self.feed()["items"][0]
        self.assertEqual(task["id"], "referrals:visits")
        self.assertEqual(task["pending_count"], 5)
        self.assertEqual(task["residential_count"], 2)
        for group in task["groups"]:
            self.assertEqual(group["pending_count"], 1)
            url = urlsplit(group["actions"][0]["url"])
            self.assertEqual((url.path, url.fragment), ("/ui/reports/visitas", "visit-referrals"))
            query = parse_qs(url.query)
            self.assertEqual(query["proposal_id"], [str(group["proposal_id"])])
            self.assertEqual(query["employee_id"], [str(-group["residential_id"])])
            self.assertEqual(query["month"], [str(group["month"])])

    def test_any_complete_type_resolves_only_matching_report_and_delete_reopens(self):
        for kind in ("Interno", "Externo", "Visita Agencia"):
            with self.subTest(kind=kind):
                replace_visit_report_referrals(self.db, 1, [{"referral_type": kind, "agency": "Agencia",
                                                           "reference_or_purpose": "Orientación"}])
                self.db.commit()
                groups = self.feed()["items"][0]["groups"]
                self.assertEqual(len(groups), 4)
                self.assertNotIn((1, 1, 7), [(g["residential_id"], g["proposal_id"], g["month"]) for g in groups])
                self.assertIn((2, 2, 7), [(g["residential_id"], g["proposal_id"], g["month"]) for g in groups])
                replace_visit_report_referrals(self.db, 1, [])
                self.db.commit()
                self.assertEqual(self.feed()["items"][0]["pending_count"], 5)

    def test_partial_legacy_rows_and_empty_report_do_not_resolve(self):
        for values in ({"referral_type": "Externo", "agency": "Agencia", "reference_or_purpose": "   "},
                       {"referral_type": "Externo", "agency": None, "reference_or_purpose": "Motivo"},
                       {"referral_type": "Otro", "agency": "Agencia", "reference_or_purpose": "Motivo"}):
            self.db.execute(self.tables["visit_report_referrals"].update().values(**values))
            self.db.commit()
            self.assertEqual(self.feed()["items"][0]["pending_count"], 5)

    def test_last_complete_referral_removes_the_task_from_the_users_feed(self):
        user = SimpleNamespace(user_id=1, role="user", _active_residential_id=2)
        self.assertEqual(self.feed(user)["attention_count"], 1)
        replace_visit_report_referrals(self.db, 2, [{"referral_type": "Externo", "agency": "Agencia",
                                                   "reference_or_purpose": "Referido 001"}])
        self.db.commit()
        self.assertEqual(self.feed(user), {"items": [], "attention_count": 0})

    def test_scope_confirmation_date_and_viewer_follow_course_rules(self):
        for role in ("user", "supervisor"):
            user = SimpleNamespace(user_id=1, role=role, residential_id=1, _active_residential_id=2)
            task = self.feed(user)["items"][0]
            self.assertEqual(task["pending_count"], 1)  # False attendance in R2 does not add a report.
            self.assertEqual(task["groups"][0]["residential_id"], 2)
        self.assertEqual(len(pending_referral_groups(self.db, today=date(2026, 7, 30))), 3)
        self.db.execute(self.tables["attendance"].update().values(attended=False))
        self.db.commit()
        self.assertEqual(self.feed()["items"], [])
        self.user.role = "viewer"
        self.assertEqual(self.feed()["items"], [])

    def test_partial_submission_cannot_delete_previously_saved_referrals(self):
        valid = {"referral_type": "Interno", "agency": "Agencia", "reference_or_purpose": "Motivo"}
        replace_visit_report_referrals(self.db, 1, [valid])
        self.db.commit()
        for invalid in ({**valid, "agency": " "}, {**valid, "referral_type": "Otro"},
                        {**valid, "reference_or_purpose": ""}, {**valid, "agency": "a" * 256}):
            with self.subTest(invalid=invalid), self.assertRaises(HTTPException):
                replace_visit_report_referrals(self.db, 1, [valid, invalid])
            self.db.commit()
            self.assertEqual(len(self.db.execute(self.tables["visit_report_referrals"].select()).all()), 1)

    def test_no_per_report_queries_or_sql_server_parameter_overflow(self):
        captured = []
        def check(state):
            compiled = state.statement.compile(dialect=mssql.dialect(), compile_kwargs={"render_postcompile": True})
            self.assertLess(len(compiled.params), 100)
            captured.append(str(compiled))
        event.listen(self.db, "do_orm_execute", check)
        self.addCleanup(event.remove, self.db, "do_orm_execute", check)
        self.assertEqual(len(pending_referral_groups(self.db, today=date(2026, 8, 15))), 5)
        self.assertEqual(len(captured), 1)


if __name__ == "__main__":
    unittest.main()
