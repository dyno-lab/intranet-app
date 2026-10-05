import re
import unittest
from datetime import date
from decimal import Decimal
from urllib.parse import parse_qs, urlencode, urlsplit
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
from app.services.community import create_fiscal_year
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
        page = self.client.get("/community/school-grades", params={"program_id": self.voca_id, "month": 1, "year": 2025})
        self.assertEqual([row[0].report_id for row in page.context["reports"]], [first.report_id])
        self.assertIn("Seguimiento escolar", page.text)
        self.assertIn("operator", page.text)
        self.assertIn('name="month"', page.text)
        self.assertIn('name="year"', page.text)
        for params in ({"month": 13}, {"year": 0}, {"month": "no"}):
            self.assertEqual(self.client.get("/community/school-grades", params=params).status_code, 422)
        self.assertEqual(self.client.get("/community/school-grades", params={"program_id": self.tanf_id}).status_code, 403)

    def test_program_selection_limits_choices_and_creation_to_own_program(self):
        self.report()
        self.report(program_id=self.tanf_id)
        self.db.commit()
        landing = self.client.get("/community/school-grades")
        self.assertEqual(landing.status_code, 200)
        self.assertIn(f'/community/school-grades?program_id={self.voca_id}', landing.text)
        self.assertNotIn(f'/community/school-grades?program_id={self.tanf_id}', landing.text)
        self.assertNotIn('class="grades-create-form"', landing.text)
        selected = self.client.get("/community/school-grades", params={"program_id": self.voca_id})
        self.assertEqual(selected.context["selected_year"], self.fy_id)
        self.assertEqual({row[0].program_id for row in selected.context["reports"]}, {self.voca_id})
        self.assertIn(f'name="program_id" value="{self.voca_id}"', selected.text)
        self.assertIn(f'name="fiscal_year_id" value="{self.fy_id}"', selected.text)
        self.assertNotIn('id="create-program"', selected.text)
        self.role("admin")
        self.assertIn(f'/community/school-grades?program_id={self.tanf_id}',
                      self.client.get("/community/school-grades").text)

    def test_fiscal_selection_prefers_current_open_year_and_hides_closed_creation(self):
        today = date.today()
        current = create_fiscal_year(self.db, "CURRENT", "Actual", date(today.year, 1, 1), date(today.year, 12, 31))
        future = create_fiscal_year(self.db, "FUTURE", "Próximo", date(today.year + 1, 1, 1), date(today.year + 1, 12, 31))
        current_id, future_id = current.fiscal_year_id, future.fiscal_year_id
        self.db.commit()
        page = self.client.get("/community/school-grades", params={"program_id": self.voca_id})
        self.assertEqual(page.context["selected_year"], current_id)
        self.assertFalse(page.context["create_lock"])
        for fiscal_id in (self.fy_id, future_id):
            if fiscal_id == self.fy_id:
                set_fiscal_status(self.db, fiscal_id, closed=True, actor_user_id=self.actor_id)
                self.db.commit()
            page = self.client.get("/community/school-grades", params={"program_id": self.voca_id, "fiscal_year_id": fiscal_id})
            self.assertTrue(page.context["create_lock"])
            self.assertNotIn('class="grades-create-form"', page.text)

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
        query = parse_qs(urlsplit(response.headers["location"]).query)
        self.assertEqual(query["program_id"], [str(self.voca_id)])
        self.assertEqual(query["fiscal_year_id"], [str(self.fy_id)])
        self.assertEqual(query["month"], ["1"])
        self.assertIn("msg", query)
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

    def test_viewer_previews_forms_with_disabled_actions_and_all_posts_are_denied(self):
        report = self.report()
        save_grade_item(self.db, report_id=report.report_id, participant_id=self.participant_id,
                        fields={"math_grade": "90"})
        self.db.commit()
        self.role("viewer")
        path = f"/community/school-grades/{report.report_id}"
        page = self.client.get(path)
        self.assertEqual(page.status_code, 200)
        self.assertIn("Viewer · Vista de revisión", page.text)
        self.assertIn('disabled>Borrar informe</button>', page.text)
        self.assertIn('disabled>Guardar</button>', page.text)
        self.assertIn('disabled>Quitar</button>', page.text)
        self.assertIn('community-viewer.js', page.text)
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
                listing = self.client.get("/community/school-grades", params={"program_id": self.voca_id})
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
        fiscal = create_fiscal_year(self.db, "ARCHIVE", "Período configurado", date(2020, 1, 1), date(2024, 12, 31))
        fiscal_id = fiscal.fiscal_year_id
        for number in range(51):
            self.report(fiscal_year_id=fiscal_id, report_year=2020 + number // 12, report_month=1 + number % 12)
        self.report(program_id=self.tanf_id, fiscal_year_id=fiscal_id, report_year=2020)
        self.db.commit()
        filters = {"fiscal_year_id": fiscal_id, "program_id": self.voca_id}
        first = self.client.get("/community/school-grades", params=filters)
        self.assertEqual(first.context["total"], 51)
        self.assertEqual(len(first.context["reports"]), 50)
        self.assertEqual(first.context["next_url"], "/community/school-grades?" + urlencode({**filters, "page": 2}))
        second = self.client.get(first.context["next_url"])
        self.assertEqual(len(second.context["reports"]), 1)
        report = second.context["reports"][0][0]
        return_query = urlencode({**filters, "page": 2})
        detail = self.client.get(f"/community/school-grades/{report.report_id}", params={"return_query": return_query})
        self.assertEqual(detail.context["return_query"], return_query)
        self.assertIn('/community/school-grades?' + return_query.replace('&', '&amp;'), detail.text)

    def test_legacy_detail_return_keeps_report_program_and_fiscal_year(self):
        report = self.report()
        self.db.commit()
        page = self.client.get(f"/community/school-grades/{report.report_id}", params={
            "return_query": f"month=1&year=2025&program_id={self.tanf_id}&fiscal_year_id=999",
        })
        query = parse_qs(page.context["return_query"])
        self.assertEqual(query["program_id"], [str(self.voca_id)])
        self.assertEqual(query["fiscal_year_id"], [str(self.fy_id)])

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

    def test_dashboard_uses_latest_period_in_selected_program_and_fiscal_year(self):
        latest = self.report(report_month=3)
        older = self.report(report_month=1)
        other_program = self.report(program_id=self.tanf_id, report_month=6)
        archive = create_fiscal_year(self.db, "OLD", "Anterior", date(2024, 1, 1), date(2024, 12, 31))
        archived = self.report(fiscal_year_id=archive.fiscal_year_id, report_year=2024, report_month=12)
        second = self.new_participant("Segunda", [self.voca_id])
        self.db.add_all([
            CPGradeItem(report_id=latest.report_id, participant_id=self.participant_id,
                        spanish_grade=0, math_grade=80),
            CPGradeItem(report_id=latest.report_id, participant_id=second.participant_id,
                        spanish_grade=100, english_grade=90),
            CPGradeItem(report_id=older.report_id, participant_id=self.participant_id, spanish_grade=100),
            CPGradeItem(report_id=other_program.report_id, participant_id=self.participant_id, spanish_grade=100),
            CPGradeItem(report_id=archived.report_id, participant_id=self.participant_id, spanish_grade=99),
        ])
        self.db.commit()
        page = self.client.get("/community/school-grades", params={
            "program_id": self.voca_id, "fiscal_year_id": self.fy_id, "month": 1, "year": 2025,
        })
        self.assertEqual(page.status_code, 200)
        summary = page.context["grade_summary"]
        self.assertEqual(summary["report"].report_id, latest.report_id)
        self.assertEqual(summary["total"], 2)
        self.assertEqual([(s["label"], s["average"], s["count"]) for s in summary["subjects"]],
                         [("Español", 50, 2), ("Matemáticas", 80, 1), ("Inglés", 90, 1)])
        self.assertEqual([r[0].report_id for r in page.context["reports"]], [older.report_id])
        self.assertEqual(page.context["report_counts"], {older.report_id: 1})
        self.assertIn("Último informe: Marzo 2025", page.text)
        self.assertIn("1 sin nota", page.text)
        archived_page = self.client.get("/community/school-grades", params={
            "program_id": self.voca_id, "fiscal_year_id": archive.fiscal_year_id,
        })
        self.assertEqual(archived_page.context["grade_summary"]["report"].report_id, archived.report_id)
        self.assertEqual(archived_page.context["grade_summary"]["subjects"][0]["average"], 99)
        self.assertEqual(self.client.get("/community/school-grades", params={"program_id": self.tanf_id}).status_code, 403)

    def test_dashboard_empty_latest_report_does_not_reuse_older_notes(self):
        empty = self.client.get("/community/school-grades", params={"program_id": self.voca_id})
        self.assertIsNone(empty.context["grade_summary"]["report"])
        older = self.report()
        save_grade_item(self.db, report_id=older.report_id, participant_id=self.participant_id,
                        fields={"spanish_grade": "90"})
        latest = self.report(report_month=2)
        self.db.commit()
        for role in ("user", "viewer"):
            self.role(role)
            page = self.client.get("/community/school-grades", params={"program_id": self.voca_id})
            summary = page.context["grade_summary"]
            self.assertEqual(summary["report"].report_id, latest.report_id)
            self.assertEqual(summary["total"], 0)
            self.assertTrue(all(s["average"] is None and s["count"] == 0 for s in summary["subjects"]))
            self.assertIn("Sin notas", page.text)
            if role == "viewer":
                self.assertIn('class="grades-create-form"', page.text)
                self.assertIn('disabled>Crear informe</button>', page.text)


if __name__ == "__main__":
    unittest.main()
