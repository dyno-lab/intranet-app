import os
import re
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, Table, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.middleware.sessions import SessionMiddleware

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from app.api.routes import school_grades
from app.core.residential_scope import require_faro_access
from app.models.user_residential import UserResidential


class SchoolGradeFilterTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        models = (school_grades.Proposal, school_grades.Residential, school_grades.User,
                  school_grades.SchoolGradeReport, UserResidential)
        tables = {model.__tablename__: Table(model.__tablename__, metadata, *[
            Column(column.name, column.type, primary_key=column.primary_key)
            for column in model.__table__.columns]) for model in models}
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(tables["proposals"].insert(), [
                dict(proposal_id=i, code=f"P{i}", name=f"Propuesta {i}", is_active=i != 3)
                for i in (1, 2, 3)])
            connection.execute(tables["residentials"].insert(), [
                dict(residential_id=i, code=f"R{i}", name=f"Residencial {i}", is_active=True)
                for i in (1, 2)])
            connection.execute(tables["user_residentials"].insert(), [
                dict(user_residential_id=i, user_id=90, residential_id=i, is_active=True)
                for i in (1, 2)])
            connection.execute(tables["school_grade_reports"].insert(), [
                dict(report_id=i, proposal_id=p, residential_id=r, report_month=m,
                     report_year=y, notes=f"Informe de prueba {i}")
                for i, p, r, m, y in ((1, 1, 1, 7, 2026), (2, 1, 2, 8, 2026),
                                     (3, 2, 1, 9, 2026), (4, 1, 1, 12, 2025),
                                     (5, 1, 1, 8, 2026), (6, 3, 1, 6, 2026))])
        self.user = SimpleNamespace(user_id=90, role="admin", username="Prueba", residential_id=None)
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="school-grade-filter-test")
        app.include_router(school_grades.router, prefix="/ui/school-grades", dependencies=[Depends(require_faro_access)])
        def db():
            with Session(self.engine) as session:
                yield session
        app.dependency_overrides[school_grades.get_db] = db
        app.dependency_overrides[school_grades.get_current_user] = lambda: self.user
        permission = patch("app.core.residential_scope._FARO_PERMISSION_DEPENDENCY", return_value=self.user)
        permission.start()
        self.addCleanup(permission.stop)
        @app.get("/test/residential/{rid}")
        def context(request: Request, rid: int):
            request.session["active_residential_id"] = rid
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def page(self, query=""):
        response = self.client.get("/ui/school-grades" + query)
        self.assertEqual(response.status_code, 200, response.text)
        identifiers = [int(value) for value in re.findall(r'href="/ui/school-grades/(\d+)"', response.text)]
        return response, identifiers

    def test_exact_production_url_shows_all_authorized_reports(self):
        _, identifiers = self.page("?proposal_id=&month=&year=")
        self.assertEqual(identifiers, [3, 5, 2, 1, 6, 4])
        self.assertEqual(self.page()[1], identifiers)
        self.assertEqual(self.page("?proposal_id=%20&month=%20&year=%20")[1], identifiers)

    def test_partial_filters_and_selected_values_are_preserved(self):
        for query, expected in (
            ("?proposal_id=1&month=&year=", [5, 2, 1, 4]),
            ("?proposal_id=&month=8&year=", [5, 2]),
            ("?proposal_id=&month=&year=2025", [4]),
            ("?proposal_id=1&month=8&year=2026", [5, 2]),
            ("?proposal_id=3&month=&year=", [6]),
        ):
            with self.subTest(query=query):
                self.assertEqual(self.page(query)[1], expected)
        response, _ = self.page("?proposal_id=1&month=8&year=2026")
        for name, value in (("proposal_id", "1"), ("month", "8"), ("year", "2026")):
            selector = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', response.text, re.S).group(1)
            self.assertRegex(selector, rf'<option value="{value}" selected>')

    def test_empty_filters_keep_global_and_residential_permissions(self):
        for role in ("admin", "supervisor", "viewer"):
            with self.subTest(role=role):
                self.user.role = role
                response, identifiers = self.page("?proposal_id=&month=&year=")
                self.assertEqual(identifiers, [3, 5, 2, 1, 6, 4])
                if role == "viewer":
                    self.assertNotIn('action="/ui/school-grades/create"', response.text)
        self.client.get("/test/residential/1")
        for role in ("admin", "supervisor", "user", "viewer"):
            with self.subTest(scoped_role=role):
                self.user.role = role
                self.assertEqual(self.page("?proposal_id=&month=&year=&residential_id=2")[1], [3, 5, 1, 6, 4])

    def test_non_integer_filters_still_return_validation_errors(self):
        for name in ("proposal_id", "month", "year"):
            for value in ("abc", "1.5"):
                with self.subTest(name=name, value=value):
                    response = self.client.get("/ui/school-grades", params={name: value})
                    self.assertEqual(response.status_code, 422)
        self.assertEqual(self.page()[1], [3, 5, 2, 1, 6, 4])


if __name__ == "__main__":
    unittest.main()
