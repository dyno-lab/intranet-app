from datetime import date
from types import SimpleNamespace
import unittest
from urllib.parse import parse_qs, urlsplit

from fastapi import HTTPException
from sqlalchemy import event, select
from sqlalchemy.dialects import mssql

from tests import test_participant_courses as fixtures
from app.models.notification import FaroAnnouncement, FaroAnnouncementRead
from app.services.notifications import (
    admin_announcements, course_notification, create_announcement,
    mark_announcement_read, notification_feed, visible_announcements,
)
from app.services.participant_courses import build_course_report


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.source = fixtures.ParticipantCoursesTests()
        self.source.setUp()
        self.addCleanup(self.source.doCleanups)
        self.db, self.user = self.source.db, self.source.user
        self.today = date(2026, 8, 15)

    def publish(self, **overrides):
        values = dict(title="Cambios en el programa", message="Información para el equipo.",
                      starts_on="2000-01-01", ends_on="", role_scope="all", residential_scope="all")
        values.update(overrides)
        return create_announcement(self.db, self.user, values)

    def feed(self, user=None):
        return notification_feed(self.db, user or self.user, today=self.today)

    def test_unique_participant_months_and_correct_report_actions(self):
        task = course_notification(self.db, self.user, today=self.today)
        self.assertEqual(task["pending_count"], 5)  # June 1 + July 3 + August 1; duplicate July in R2.
        self.assertEqual(task["residential_count"], 2)
        self.assertEqual(len(task["groups"]), 4)
        july = next(g for g in task["groups"] if g["month"] == 7 and g["residential_id"] == 1)
        self.assertEqual(july["period"], "Julio 2026")
        self.assertEqual(july["pending_count"], 3)
        for group in task["groups"]:
            url = urlsplit(group["actions"][0]["url"])
            self.assertEqual(url.path, "/ui/reports/cursos")
            query = parse_qs(url.query)
            report = build_course_report(self.db, self.user, proposal_ids=query["proposal_id"],
                year=query["year"][0], month=query["month"][0], employee_id=int(query["employee_id"][0]))
            self.assertEqual(report["pending"], group["pending_count"])

    def test_save_resolves_month_across_residentials_read_does_not(self):
        announcement = self.publish()
        mark_announcement_read(self.db, self.user, announcement.announcement_id)
        self.assertEqual(self.feed()["items"][0]["pending_count"], 5)
        self.source.save([self.source.change()])
        feed = self.feed()
        self.assertEqual(feed["items"][0]["pending_count"], 4)
        self.assertEqual(feed["items"][0]["residential_count"], 1)
        self.assertEqual(feed["attention_count"], 1)
        self.assertFalse(feed["items"][1]["unread"])
        self.source.save([self.source.change(course="", revision=1)])
        self.assertEqual(self.feed()["items"][0]["pending_count"], 5)

    def test_exact_activity_confirmed_only_future_and_legacy_course(self):
        self.assertEqual(course_notification(self.db, self.user, today=date(2026, 7, 30))["pending_count"], 4)
        self.source.source.insert("participant_monthly_courses", participant_id=1, report_year=2026,
                                  report_month=7, course_code="campo_laboral", revision=1)
        self.db.commit()
        self.assertEqual(self.feed()["items"][0]["pending_count"], 4)
        self.db.execute(self.source.source.tables["activity_codes"].update().values(code="2.b.50"))
        self.db.commit()
        self.assertEqual(self.feed()["items"], [])

    def test_user_and_supervisor_active_scope_never_use_legacy_residential(self):
        for role in ("user", "supervisor", "admin"):
            user = SimpleNamespace(user_id=1, role=role, residential_id=1, _active_residential_id=2)
            task = self.feed(user)["items"][0]
            self.assertEqual(task["pending_count"], 1)
            self.assertEqual([g["residential_id"] for g in task["groups"]], [2])
        with self.assertRaises(HTTPException):
            self.feed(SimpleNamespace(user_id=1, role="user", residential_id=1))

    def test_target_roles_and_residentials_intersect_and_reads_are_personal(self):
        general = self.publish()
        targeted = self.publish(role_scope="selected", roles=["user", "supervisor"],
                                residential_scope="selected", residential_ids=["2"])
        r1 = SimpleNamespace(user_id=2, role="user", _active_residential_id=1)
        r2 = SimpleNamespace(user_id=3, role="user", _active_residential_id=2)
        supervisor = SimpleNamespace(user_id=4, role="supervisor")
        announcements = lambda user: [i for i in self.feed(user)["items"] if i["type"] == "announcement"]
        self.assertEqual(len(announcements(r1)), 1)
        self.assertEqual(len(announcements(r2)), 2)
        self.assertEqual(len(announcements(supervisor)), 2)
        self.assertEqual(len(announcements(self.user)), 1)
        for _ in range(2):
            mark_announcement_read(self.db, r2, targeted.announcement_id)
        self.assertEqual(len(self.db.scalars(select(FaroAnnouncementRead)).all()), 1)
        self.assertEqual(sum(i["unread"] for i in announcements(r2)), 1)
        self.assertEqual(sum(i["unread"] for i in announcements(supervisor)), 2)
        with self.assertRaises(HTTPException) as exc:
            mark_announcement_read(self.db, r1, targeted.announcement_id)
        self.assertEqual(exc.exception.status_code, 404)
        self.assertTrue(general.is_active)

    def test_scheduled_expired_retired_and_inactive_targets(self):
        self.publish(title="Future", starts_on="2027-01-01")
        self.publish(title="Expired", ends_on="2026-08-14")
        self.publish(title="Inclusive", starts_on="2026-08-15", ends_on="2026-08-15")
        retired = self.publish(title="Retired")
        retired.is_active = False
        self.publish(title="Inactive", residential_scope="selected", residential_ids=["2"])
        self.db.execute(self.source.source.tables["residentials"].update().where(
            self.source.source.tables["residentials"].c.residential_id == 2).values(is_active=False))
        self.db.commit()
        self.assertEqual([i["title"] for i in self.feed()["items"] if i["type"] == "announcement"], ["Inclusive"])
        with self.assertRaises(HTTPException):
            mark_announcement_read(self.db, self.user, retired.announcement_id)

    def test_validation_does_not_publish_to_broader_audience(self):
        for invalid in ({"title": " "}, {"message": "x" * 4001}, {"title": "😀" * 81}, {"ends_on": "1999-01-01"},
                        {"role_scope": "selected"}, {"role_scope": "selected", "roles": ["bad"]},
                        {"residential_scope": "selected", "residential_ids": [999]},
                        {"roles": ["user"]}, {"residential_scope": "selected", "residential_ids": ["bad"]}):
            with self.subTest(invalid=invalid), self.assertRaises(HTTPException):
                self.publish(**invalid)
        self.assertEqual(self.db.scalars(select(FaroAnnouncement)).all(), [])
        self.user.role = "supervisor"
        with self.assertRaises(HTTPException) as exc:
            self.publish()
        self.assertEqual(exc.exception.status_code, 403)

    def test_closed_periods_still_link_to_report_with_existing_restrictions(self):
        proposal = self.source.source.tables["proposals"]
        self.db.execute(proposal.update().where(proposal.c.proposal_id == 1).values(status="finalized"))
        self.db.commit()
        self.assertEqual(self.feed()["items"][0]["pending_count"], 5)
        with self.assertRaises(HTTPException):
            self.source.save([self.source.change()])

    def test_viewer_receives_announcements_without_course_edit_tasks(self):
        self.publish()
        self.user.role = "viewer"
        self.assertEqual([i["type"] for i in self.feed()["items"]], ["announcement"])

    def test_feed_query_budget_constant_and_sql_server_compatible(self):
        self.publish(residential_scope="selected", residential_ids=["1", "2"])
        statements = []
        def capture(_conn, _cursor, statement, _params, _context, _many):
            statements.append(statement)
            compiled = str(_context.compiled.statement.compile(dialect=mssql.dialect()))
            self.assertNotIn("STRFTIME", compiled)
        event.listen(self.source.source.engine, "before_cursor_execute", capture)
        self.addCleanup(event.remove, self.source.source.engine, "before_cursor_execute", capture)
        self.feed()
        self.assertEqual(len(statements), 3)  # Courses, referrals and announcements; no per-report queries.
        compiled = str(visible_announcements(self.user).compile(dialect=mssql.dialect()))
        self.assertIn("EXISTS", compiled)
        self.assertEqual(admin_announcements(self.db)[0]["residentials"], "Residencial 1, Residencial 2")

    def test_more_than_sql_server_parameter_limit_of_pending_participants(self):
        source = self.source.source
        source.db.execute(source.tables["participants"].insert(), [
            {"participant_id": identifier, "residential_id": 1, "nombre": f"Persona {identifier}"}
            for identifier in range(100, 2300)])
        source.db.execute(source.tables["attendance"].insert(), [
            {"attendance_id": identifier, "session_id": 1, "participant_id": identifier, "attended": True}
            for identifier in range(100, 2300)])
        source.db.commit()
        self.assertEqual(self.feed()["items"][0]["pending_count"], 2205)

    def test_legacy_attendance_without_proposal_has_a_review_action(self):
        source = self.source.source
        source.db.execute(source.tables["activity_sessions"].update().where(
            source.tables["activity_sessions"].c.session_id == 6).values(proposal_id=None))
        source.db.commit()
        august = next(g for g in self.feed()["items"][0]["groups"] if g["month"] == 8)
        self.assertTrue(august["needs_proposal"])
        self.assertEqual(august["actions"], [{"label": "Revisar asistencias sin propuesta", "url": "/ui/listado"}])


if __name__ == "__main__":
    unittest.main()
