import re
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from tests import test_community_operations as fixtures
from app.api.deps import get_db
from app.api.routes import community_operations
from app.core.config import settings
from app.models.community import CPParticipant, CPUserAccess
from app.models.community_operations import CPGradeItem, CPGradeReport
from app.services.community_fiscal import set_fiscal_lock, set_fiscal_status
from app.services.community import create_program
from app.services.community_operations import save_grade_item


class SchoolGradeManagementTests(unittest.TestCase):
    tearDown = fixtures.CommunityOperationTests.tearDown
    new_participant = fixtures.CommunityOperationTests.new_participant
    report = fixtures.CommunityOperationTests.report

    def setUp(self):
        fixtures.CommunityOperationTests.setUp(self)
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="school-grade-test-session-only")
        app.mount("/static", StaticFiles(directory="app/static"), name="static")
        app.include_router(community_operations.router)

        @app.get("/_test/login/{user_id}")
        def login(user_id: int, request: Request):
            request.session.clear()
            request.session.update(user_id=user_id, session_version=1, community_program_context="all")

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        feature = patch.object(settings, "COMMUNITY_ENABLED", True)
        feature.start()
        self.addCleanup(feature.stop)
        self.client = TestClient(app, follow_redirects=False)
        self.addCleanup(self.client.close)
        self.client.get(f"/_test/login/{self.actor_id}")
        page = self.client.get("/community/school-grades", params={
            "fiscal_year_id": self.fy_id, "program_id": self.voca_id,
        })
        self.assertEqual(page.status_code, 200, page.text)
        self.token = re.search(r'name="token" value="([^"]+)"', page.text).group(1)

    def role(self, role):
        self.db.get(CPUserAccess, self.actor_id).role = role
        self.db.commit()

    def post(self, path, **fields):
        return self.client.post(path, data={"token": self.token, **fields})

    def test_list_filters_period_and_program_and_shows_author_notes(self):
        first = self.report(notes="Seguimiento escolar")
        self.report(report_month=2)
        self.report(program_id=self.tanf_id)
        self.db.commit()
        page = self.client.get("/community/school-grades", params={"month": 1, "year": 2025})
        self.assertEqual([row[0].report_id for row in page.context["reports"]], [first.report_id])
        self.assertIn("Seguimiento escolar", page.text)
        self.assertIn("operator", page.text)
        self.assertIn('name="month"', page.text)
        self.assertIn('name="year"', page.text)
        for params in ({"month": 13}, {"year": 0}, {"month": "no"}):
            self.assertEqual(self.client.get("/community/school-grades", params=params).status_code, 422)
        self.assertEqual(self.client.get("/community/school-grades", params={"program_id": self.tanf_id}).status_code, 403)

    def test_table_preserves_zero_and_add_does_not_overwrite_existing_notes(self):
        report = self.report()
        save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id,
                        fields={"math_grade": "0", "spanish_grade": "100", "grade_level": "5"})
        self.db.commit()
        path = f"/community/school-grades/{report.report_id}"
        page = self.client.get(path)
        self.assertIn('id="grade-items"', page.text)
        self.assertIn('value="0.00"', page.text)
        response = self.post(path + "/participants/add", participant_id=self.participant_id, grade_level="6")
        self.assertEqual(response.status_code, 303)
        self.assertIn("error=", response.headers["location"])
        self.db.expire_all()
        item = self.db.get(CPGradeItem, (report.report_id, self.participant_id))
        self.assertEqual(item.average_grade, Decimal("50.00"))
        self.assertEqual(item.grade_level, "5")

    def test_add_then_save_grade_row_and_reject_ineligible_program(self):
        report = self.report()
        self.db.commit()
        path = f"/community/school-grades/{report.report_id}"
        added = self.post(path + "/participants/add", participant_id=self.participant_id,
                          grade_level="EE", is_content_room="on")
        self.assertEqual(added.status_code, 303)
        self.assertIn("msg=", added.headers["location"])
        saved = self.post(path + "/participants", participant_id=self.participant_id,
                          grade_level="5", spanish_grade="95", math_grade="85")
        self.assertIn("msg=", saved.headers["location"])
        self.db.expire_all()
        item = self.db.get(CPGradeItem, (report.report_id, self.participant_id))
        self.assertEqual(item.average_grade, Decimal("90.00"))
        self.assertFalse(item.is_content_room)
        invalid = self.post(path + "/participants/add", participant_id=self.outsider_id)
        self.assertIn("error=", invalid.headers["location"])
        self.assertIsNone(self.db.get(CPGradeItem, (report.report_id, self.outsider_id)))

    def test_user_removes_only_selected_item_or_report(self):
        own, other = self.report(), self.report(program_id=self.tanf_id)
        for report in (own, other):
            save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id,
                            fields={"math_grade": "88"})
        own_id, other_id = own.report_id, other.report_id
        self.db.commit()
        path = f"/community/school-grades/{own_id}"
        response = self.post(path + f"/participants/{self.participant_id}/delete")
        self.assertEqual(response.status_code, 303)
        self.assertIn("msg=", response.headers["location"])
        self.db.expire_all()
        self.assertIsNone(self.db.get(CPGradeItem, (own_id, self.participant_id)))
        self.assertIsNotNone(self.db.get(CPGradeReport, own_id))
        self.assertIsNotNone(self.db.get(CPGradeItem, (other_id, self.participant_id)))
        self.post(path + "/participants/add", participant_id=self.participant_id)
        response = self.post(path + "/delete?return_query=month%3D1%26year%3D2025")
        self.assertIn("/community/school-grades?month=1&year=2025&msg=", response.headers["location"])
        self.db.expire_all()
        self.assertIsNone(self.db.get(CPGradeReport, own_id))
        self.assertIsNone(self.db.get(CPGradeItem, (own_id, self.participant_id)))
        self.assertIsNotNone(self.db.get(CPGradeReport, other_id))
        self.assertIsNotNone(self.db.get(CPParticipant, self.participant_id))

    def test_delete_requires_source_scope_and_csrf_for_all_writers(self):
        own, other = self.report(), self.report(program_id=self.tanf_id)
        self.db.commit()
        for suffix in ("/delete", f"/participants/{self.participant_id}/delete"):
            self.assertEqual(self.post(f"/community/school-grades/{other.report_id}" + suffix).status_code, 404)
            bad = self.client.post(f"/community/school-grades/{own.report_id}" + suffix, data={"token": "invalid"})
            self.assertEqual(bad.status_code, 403)
        for role in ("supervisor", "admin"):
            with self.subTest(role=role):
                self.role(role)
                report = self.report(report_month=2 if role == "supervisor" else 3)
                self.db.commit()
                response = self.post(f"/community/school-grades/{report.report_id}/delete")
                self.assertEqual(response.status_code, 303)
                self.assertIn("msg=", response.headers["location"])
                self.db.expunge(report)

    def test_viewer_has_no_mutation_controls_and_all_posts_are_denied(self):
        report = self.report()
        save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id,
                        fields={"math_grade": "90"})
        self.db.commit()
        self.role("viewer")
        path = f"/community/school-grades/{report.report_id}"
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Modo de consulta", page.text)
        self.assertNotIn("Borrar informe</button>", page.text)
        self.assertNotIn(">Guardar</button>", page.text)
        self.assertNotIn(">Quitar</button>", page.text)
        for suffix in ("/delete", "/participants", "/participants/add", f"/participants/{self.participant_id}/delete"):
            self.assertEqual(self.post(path + suffix, participant_id=self.participant_id).status_code, 403)
        self.assertEqual(self.post("/community/school-grades", fiscal_year_id=self.fy_id, program_id=self.voca_id,
                                  report_year=2025, report_month=2).status_code, 403)

    def test_closed_month_and_year_preserve_notes_and_hide_write_actions(self):
        report = self.report()
        save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id,
                        fields={"math_grade": "90"})
        self.db.commit()
        path = f"/community/school-grades/{report.report_id}"
        for lock in ("month", "year"):
            with self.subTest(lock=lock):
                if lock == "month":
                    set_fiscal_lock(self.db, self.fy_id, locked_through=date(2025, 1, 31), actor_user_id=self.actor_id)
                else:
                    set_fiscal_lock(self.db, self.fy_id, locked_through=None, actor_user_id=self.actor_id)
                    set_fiscal_status(self.db, self.fy_id, closed=True, actor_user_id=self.actor_id)
                self.db.commit()
                page = self.client.get(path)
                self.assertNotIn(">Guardar</button>", page.text)
                self.assertNotIn(">Quitar</button>", page.text)
                listing = self.client.get("/community/school-grades")
                self.assertIn(report.report_id, listing.context["locked_ids"])
                for suffix in ("/delete", f"/participants/{self.participant_id}/delete", "/participants"):
                    response = self.post(path + suffix, participant_id=self.participant_id, math_grade="60")
                    self.assertEqual(response.status_code, 303)
                    self.assertIn("error=", response.headers["location"])
                self.db.expire_all()
                self.assertEqual(self.db.get(CPGradeItem, (report.report_id, self.participant_id)).average_grade,
                                 Decimal("90.00"))
        set_fiscal_status(self.db, self.fy_id, closed=False, actor_user_id=self.actor_id)
        self.db.commit()
        self.assertIn("msg=", self.post(path + "/participants", participant_id=self.participant_id,
                                       math_grade="95").headers["location"])

    def test_filtered_pagination_and_return_to_list_keep_context(self):
        self.role("admin")
        for number in range(51):
            program = create_program(self.db, f"PR{number}", f"Programa {number}")
            self.report(program_id=program.program_id)
        self.db.commit()
        first = self.client.get("/community/school-grades?month=1&year=2025")
        self.assertEqual(first.context["total"], 51)
        self.assertEqual(len(first.context["reports"]), 50)
        self.assertEqual(first.context["next_url"], "/community/school-grades?month=1&year=2025&page=2")
        second = self.client.get(first.context["next_url"])
        self.assertEqual(len(second.context["reports"]), 1)
        report = second.context["reports"][0][0]
        detail = self.client.get(f"/community/school-grades/{report.report_id}?return_query=month%3D1%26year%3D2025%26page%3D2")
        self.assertEqual(detail.context["return_query"], "month=1&year=2025&page=2")
        self.assertIn('/community/school-grades?month=1&amp;year=2025&amp;page=2', detail.text)

    def test_create_duplicate_errors_are_readable_and_do_not_duplicate_reports(self):
        fields = dict(fiscal_year_id=self.fy_id, program_id=self.voca_id, report_year=2025, report_month=1,
                      notes="Notas del programa")
        created = self.post("/community/school-grades", **fields)
        self.assertIn("msg=", created.headers["location"])
        duplicate = self.post("/community/school-grades", **fields)
        page = self.client.get(duplicate.headers["location"])
        self.assertEqual(page.status_code, 200)
        self.assertIn("Ya existe un informe", page.text)
        self.assertEqual(len(self.db.scalars(select(CPGradeReport)).all()), 1)


if __name__ == "__main__":
    unittest.main()
