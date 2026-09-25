"""Activity configuration changes preserve program and fiscal history boundaries."""
from datetime import date
import unittest

from sqlalchemy import event, select, text
from sqlalchemy.dialects import mssql
from sqlalchemy.orm import Session

from tests import test_community_activities as fixtures
from app.models.community import CPFiscalYear
from app.models.community_activity import CPActivity, CPFiscalActivity
from app.models.community_operations import CPActivitySession
from app.services import community_activity as service


class ActivityManagementTests(fixtures.ActivityDatabaseFixture, unittest.TestCase):
    def setUp(self):
        self.create_database()
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.close()
        self.remove_database()

    def context(self, activity, year=None):
        return dict(activity_id=activity.activity_id, program_id=self.voca.program_id,
                    fiscal_year_id=year or self.year.fiscal_year_id)

    def test_productivity_is_specific_to_year_and_copied_with_configuration(self):
        activity = self.activity(self.db)
        service.update_activity_year(self.db, **self.context(activity), active=True,
                                     goal_type="monthly_fixed", goal_value="12",
                                     period_goal_value="120", goal_is_active=False)
        service.copy_fiscal_configuration(self.db, self.year.fiscal_year_id, self.next_year.fiscal_year_id)
        copied = self.db.get(CPFiscalActivity, (activity.activity_id, self.next_year.fiscal_year_id))
        self.assertEqual((copied.goal_type, copied.goal_value, copied.period_goal_value, copied.goal_is_active),
                         ("monthly_fixed", 12, 120, False))
        service.update_activity_year(self.db, **self.context(activity, self.next_year.fiscal_year_id), active=False,
                                     goal_type="period_fixed", period_goal_value="200", goal_is_active=True)
        self.assertEqual(copied.goal_value, None)
        self.assertEqual(copied.period_goal_value, 200)
        original = self.db.get(CPFiscalActivity, (activity.activity_id, self.year.fiscal_year_id))
        self.assertEqual(original.goal_value, 12)
        self.assertTrue(original.is_active)

    def test_invalid_goals_cannot_create_partial_activity(self):
        for values in ({"goal_type": "unknown"}, {"goal_type": "monthly_fixed", "goal_value": "0"},
                       {"goal_type": "period_fixed"}, {"goal_type": "monthly_fixed", "goal_value": "1.5"},
                       {"goal_type": "as_needed", "period_goal_value": "2147483648"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                service.create_activity(self.db, program_id=self.voca.program_id, code="INVALID", description="",
                                        fiscal_year_ids=[self.year.fiscal_year_id], **values)
            self.assertIsNone(self.db.scalar(select(CPActivity)))

    def test_shared_edits_blocked_by_closed_year_but_open_year_goals_editable(self):
        activity = self.activity(self.db, years=[self.year.fiscal_year_id, self.next_year.fiscal_year_id])
        self.db.get(CPFiscalYear, self.year.fiscal_year_id).status = "closed"
        self.db.commit()
        with self.assertRaisesRegex(ValueError, "cerrado"):
            service.update_activity(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id,
                                    code="NEW", description="Cambiar", active=True)
        with self.assertRaises(ValueError):
            service.update_activity_year(self.db, **self.context(activity), active=False, goal_type="none")
        service.update_activity_year(self.db, **self.context(activity, self.next_year.fiscal_year_id),
                                     active=True, goal_type="as_needed")
        self.assertEqual(activity.code, "OR-01")

    def test_edit_checks_program_and_unique_code(self):
        first = self.activity(self.db)
        other = self.activity(self.db, code="OTHER")
        with self.assertRaisesRegex(ValueError, "programa"):
            service.update_activity(self.db, activity_id=first.activity_id, program_id=self.tanf.program_id,
                                    code="NEW", description="", active=True)
        with self.assertRaises(ValueError):
            service.update_activity(self.db, activity_id=other.activity_id, program_id=self.voca.program_id,
                                    code="or-01", description="", active=True)
        service.update_activity(self.db, activity_id=first.activity_id, program_id=self.voca.program_id,
                                code=" UPDATED ", description="Taller", active=False)
        self.assertEqual((first.code, first.description, first.is_active), ("UPDATED", "Taller", False))

    def test_remove_year_only_removes_unused_selected_association(self):
        activity = self.activity(self.db, years=[self.year.fiscal_year_id, self.next_year.fiscal_year_id])
        service.unassociate_activity(self.db, **self.context(activity))
        self.assertIsNone(self.db.get(CPFiscalActivity, (activity.activity_id, self.year.fiscal_year_id)))
        self.assertIsNotNone(self.db.get(CPFiscalActivity, (activity.activity_id, self.next_year.fiscal_year_id)))
        self.assertIsNotNone(self.db.get(CPActivity, activity.activity_id))

    def test_sessions_and_inactive_adm_mappings_protect_removal_and_deletion(self):
        for kind in ("session", "inactive_adm"):
            activity = self.activity(self.db, code=kind)
            if kind == "session":
                self.db.add(CPActivitySession(activity_id=activity.activity_id, program_id=self.voca.program_id,
                                             fiscal_year_id=self.year.fiscal_year_id, session_date=date(2026, 1, 15),
                                             created_by_user_id=self.actor_id))
            else:
                mapping = self.assign(self.db, self.service(self.db), activity)
                mapping.is_active = False
            self.db.commit()
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "sesiones|ADM"):
                service.unassociate_activity(self.db, **self.context(activity))
            with self.subTest(kind=kind), self.assertRaisesRegex(ValueError, "sesiones|ADM"):
                service.delete_activity(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id)
            self.assertIsNotNone(self.db.get(CPActivity, activity.activity_id))

    def test_unused_activity_can_be_deleted_but_closed_year_is_protected(self):
        activity = self.activity(self.db)
        activity_id = activity.activity_id
        self.db.get(CPFiscalYear, self.year.fiscal_year_id).status = "closed"
        self.db.commit()
        for operation in (lambda: service.unassociate_activity(self.db, **self.context(activity)),
                          lambda: service.delete_activity(self.db, activity_id=activity_id, program_id=self.voca.program_id)):
            with self.assertRaises(ValueError):
                operation()
        self.db.get(CPFiscalYear, self.year.fiscal_year_id).status = "active"
        self.db.commit()
        service.delete_activity(self.db, activity_id=activity_id, program_id=self.voca.program_id)
        self.db.commit()
        self.assertIsNone(self.db.get(CPActivity, activity_id))
        self.assertIsNone(self.db.scalar(select(CPFiscalActivity)))

    def test_no_goal_clears_quantities_and_global_inactive_keeps_fiscal_state(self):
        activity = self.activity(self.db)
        service.update_activity(self.db, activity_id=activity.activity_id, program_id=self.voca.program_id,
                                code=activity.code, description=activity.description, active=False)
        association = service.update_activity_year(self.db, **self.context(activity), active=True,
                                                   goal_type="as_needed", period_goal_value="30")
        self.assertTrue(association.is_active)
        self.assertFalse(activity.is_active)
        service.update_activity_year(self.db, **self.context(activity), active=True,
                                     goal_type="none", goal_value="5", period_goal_value="30")
        self.assertIsNone(association.goal_value)
        self.assertIsNone(association.period_goal_value)
        self.assertEqual(association.goal_type, "none")


class ActivityManagementRouteTests(unittest.TestCase):
    setUp = fixtures.CommunityActivityRouteTests.setUp
    tearDown = fixtures.CommunityActivityRouteTests.tearDown
    create_database = fixtures.ActivityDatabaseFixture.create_database
    remove_database = fixtures.ActivityDatabaseFixture.remove_database
    activity = fixtures.ActivityDatabaseFixture.activity
    page = fixtures.CommunityActivityRouteTests.page
    token = fixtures.CommunityActivityRouteTests.token

    def test_all_years_view_edit_goal_and_delete_round_trip(self):
        token = self.token()
        with Session(self.engine) as db:
            activity_id = self.activity(db).activity_id
            self.activity(db, program_id=self.tanf.program_id, code="PRIVATE-TANF")
            db.commit()
        all_years = self.client.get(f"/community/activities?program_id={self.voca.program_id}&fiscal_year_id=0")
        self.assertEqual(all_years.status_code, 200)
        self.assertIn("OR-01", all_years.text)
        self.assertNotIn("PRIVATE-TANF", all_years.text)
        data = dict(token=token, program_id=self.voca.program_id, fiscal_year_id=self.year.fiscal_year_id)
        edit = self.client.post(f"/community/activities/{activity_id}/edit",
                                data={**data, "code": "EDIT-1", "description": "Taller", "active": "true"})
        self.assertEqual(edit.status_code, 303)
        self.assertNotIn("error=", edit.headers["location"])
        goal = self.client.post(f"/community/activities/{activity_id}/year",
                                data={**data, "active": "true", "goal_type": "period_fixed",
                                      "period_goal_value": "50", "goal_is_active": "true"})
        self.assertEqual(goal.status_code, 303)
        self.assertNotIn("error=", goal.headers["location"])
        self.assertIn("50", self.page().text)
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPActivity, activity_id).code, "EDIT-1")
            self.assertEqual(db.get(CPFiscalActivity, (activity_id, self.year.fiscal_year_id)).period_goal_value, 50)
        deleted = self.client.post(f"/community/activities/{activity_id}/delete", data=data)
        self.assertEqual(deleted.status_code, 303)
        with Session(self.engine) as db:
            self.assertIsNone(db.get(CPActivity, activity_id))

    def test_new_mutations_enforce_role_csrf_and_program(self):
        token = self.token()
        with Session(self.engine) as db:
            activity_id = self.activity(db).activity_id
            db.commit()
        data = dict(token=token, program_id=self.voca.program_id, fiscal_year_id=self.year.fiscal_year_id,
                    code="FORGED", description="", active="true", goal_type="none")
        for endpoint in ("edit", "year", "unassociate", "delete"):
            path = f"/community/activities/{activity_id}/{endpoint}"
            with self.subTest(endpoint=endpoint):
                for role in ("viewer", "user", "supervisor"):
                    self.role = role
                    self.assertEqual(self.client.post(path, data=data).status_code, 403)
                self.role = "admin"
                self.assertEqual(self.client.post(path, data={**data, "token": "invalid"}).status_code, 403)
                self.selected_program_id = self.tanf.program_id
                self.assertEqual(self.client.post(path, data=data).status_code, 403)
                self.selected_program_id = None
                forged = self.client.post(path, data={**data, "program_id": self.tanf.program_id})
                self.assertEqual(forged.status_code, 303)
                self.assertIn("error=", forged.headers["location"])
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPActivity, activity_id).code, "OR-01")

    def test_creation_from_all_years_and_year_removal_with_mssql_queries(self):
        compiled = []

        def check_sql(conn, clause, *args):
            sql = str(clause.compile(dialect=mssql.dialect()))
            self.assertNotRegex(sql, r"\bIS (?:1|0)\b")
            compiled.append(sql)

        event.listen(self.engine, "before_execute", check_sql)
        token = self.token()
        data = dict(token=token, program_id=self.voca.program_id, fiscal_year_id=0,
                    fiscal_year_ids=[self.year.fiscal_year_id, self.next_year.fiscal_year_id],
                    code="WITH-GOAL", description="Actividad con meta", goal_type="monthly_fixed",
                    goal_value="4", period_goal_value="48", goal_is_active="true")
        response = self.client.post("/community/activities", data=data)
        self.assertEqual(response.status_code, 303)
        self.assertNotIn("error=", response.headers["location"])
        with Session(self.engine) as db:
            activity = db.scalar(select(CPActivity))
            activity_id = activity.activity_id
            rows = db.scalars(select(CPFiscalActivity)).all()
            self.assertEqual(len(rows), 2)
            self.assertTrue(all((r.goal_type, r.goal_value, r.period_goal_value, r.goal_is_active) ==
                                ("monthly_fixed", 4, 48, True) for r in rows))
        removed = self.client.post(f"/community/activities/{activity_id}/unassociate",
                                   data={**data, "fiscal_year_id": self.next_year.fiscal_year_id})
        self.assertNotIn("error=", removed.headers["location"])
        with Session(self.engine) as db:
            self.assertEqual(len(db.scalars(select(CPFiscalActivity)).all()), 1)
        self.assertTrue(any("UPDLOCK" in sql for sql in compiled))

    def test_closed_year_forged_posts_preserve_configuration(self):
        token = self.token()
        with Session(self.engine) as db:
            activity_id = self.activity(db).activity_id
            db.get(CPFiscalYear, self.year.fiscal_year_id).status = "closed"
            db.commit()
        data = dict(token=token, program_id=self.voca.program_id, fiscal_year_id=self.year.fiscal_year_id,
                    code="CHANGED", description="", active="false", goal_type="monthly_fixed", goal_value="1")
        for endpoint in ("edit", "year", "unassociate", "delete"):
            with self.subTest(endpoint=endpoint):
                response = self.client.post(f"/community/activities/{activity_id}/{endpoint}", data=data)
                self.assertEqual(response.status_code, 303)
                self.assertIn("error=", response.headers["location"])
        with Session(self.engine) as db:
            self.assertEqual(db.get(CPActivity, activity_id).code, "OR-01")
            self.assertEqual(db.get(CPFiscalActivity, (activity_id, self.year.fiscal_year_id)).goal_type, "none")

    def test_unknown_foreign_reference_rolls_back_entire_delete(self):
        token = self.token()
        with Session(self.engine) as db:
            activity_id = self.activity(db).activity_id
            db.execute(text("CREATE TABLE activity_reference (activity_id INTEGER REFERENCES cp_activities(activity_id))"))
            db.execute(text("INSERT INTO activity_reference VALUES (:id)"), {"id": activity_id})
            db.commit()
        response = self.client.post(f"/community/activities/{activity_id}/delete", data={
            "token": token, "program_id": self.voca.program_id, "fiscal_year_id": self.year.fiscal_year_id,
        })
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(CPActivity, activity_id))
            self.assertIsNotNone(db.get(CPFiscalActivity, (activity_id, self.year.fiscal_year_id)))


if __name__ == "__main__":
    unittest.main()
