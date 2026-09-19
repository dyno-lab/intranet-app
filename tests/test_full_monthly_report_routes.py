from __future__ import annotations

import os
import re
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfWriter  # noqa: E402
from sqlalchemy import Column, MetaData, Table, create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402
from starlette.middleware.sessions import SessionMiddleware  # noqa: E402

from app.api.deps import get_db  # noqa: E402
from app.api.routes import full_monthly_report as routes  # noqa: E402
from app.core.auth import get_current_user  # noqa: E402


def _pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


class FullMonthlyReportRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        tables = {}
        for model in (routes.Proposal, routes.Residential):
            source = model.__table__
            tables[source.name] = Table(source.name, metadata, *[
                Column(column.name, column.type, primary_key=column.primary_key) for column in source.columns
            ])
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(tables["proposals"].insert(), [
                {"proposal_id": identifier, "code": str(identifier), "name": f"Propuesta {identifier}", "is_active": True}
                for identifier in (1, 2)
            ])
            connection.execute(tables["residentials"].insert(), [
                {"residential_id": identifier, "code": f"R{identifier}", "name": f"Residencial {identifier}",
                 "municipality": "Ponce", "is_active": identifier == 1}
                for identifier in (1, 2)
            ])
        self.user = SimpleNamespace(user_id=1, username="admin", role="admin", is_active=True, residential_id=None)
        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-report-session-secret")
        app.include_router(routes.router, prefix="/ui/reports")

        def database():
            with Session(self.engine) as db:
                yield db

        def current_user():
            if self.user is None:
                raise HTTPException(303, headers={"Location": "/home"})
            return self.user

        app.dependency_overrides[get_db] = database
        # Exercise the real require_admin dependency on both endpoints.
        app.dependency_overrides[get_current_user] = current_user
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.pdf = _pdf_bytes()
        renderer = patch.object(routes, "_build_pdf", return_value=self.pdf)
        self.render = renderer.start()
        self.addCleanup(renderer.stop)

    def prepare(self, **overrides):
        params = {"proposal_id": [2, 1, 2], "month": 7, "year": 2026}
        params.update(overrides)
        return self.client.get("/ui/reports/completo", params=params, follow_redirects=False)

    def form(self, **overrides):
        response = self.prepare()
        self.assertEqual(response.status_code, 200, response.text)
        token = re.search(r'name="token" value="([^"]+)"', response.text).group(1)
        values = {"proposal_id": [2, 1], "month": "7", "year": "2026", "token": token}
        values.update(overrides)
        return values

    def post(self, values=None, **kwargs):
        return self.client.post("/ui/reports/completo/pdf", data=values or {}, follow_redirects=False, **kwargs)

    def test_prepare_renders_selected_proposals_and_active_manual_targets(self):
        response = self.prepare()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("Julio 2026", response.text)
        self.assertIn("Propuesta 1", response.text)
        self.assertIn("Propuesta 2", response.text)
        self.assertEqual(response.text.count('name="proposal_id" value="2"'), 1)
        self.assertIn('name="target_1"', response.text)
        self.assertNotIn('name="target_2"', response.text)
        self.render.assert_not_called()

    def test_reports_generate_preserves_selection_and_requires_admin(self):
        from urllib.parse import parse_qs, urlsplit
        from app.api.routes import reports

        self.client.app.include_router(reports.router, prefix="/ui/reports")
        params = {"report_key": "completo", "proposal_id": [2, 1], "month": "7",
                  "year": "2026", "period_type": "monthly", "authorized_name": "Nombre & Apellido"}
        for output in ("screen", "pdf"):
            with self.subTest(output=output):
                response = self.client.get("/ui/reports/run", params={**params, "output": output}, follow_redirects=False)
                self.assertEqual(response.status_code, 303)
                location = urlsplit(response.headers["location"])
                self.assertEqual(location.path, "/ui/reports/completo")
                selection = parse_qs(location.query)
                self.assertEqual(set(selection["proposal_id"]), {"2", "1"})
                self.assertEqual(selection["authorized_name"], ["Nombre & Apellido"])
                self.assertEqual(self.client.get(response.headers["location"]).status_code, 200)
        for invalid in ({"period_type": "custom"}, {"output": "excel"}):
            self.assertEqual(self.client.get("/ui/reports/run", params={**params, **invalid}).status_code, 400)
        self.user.role = "supervisor"
        self.assertEqual(self.client.get("/ui/reports/run", params=params, follow_redirects=False).status_code, 403)
        self.render.assert_not_called()

    def test_preview_and_download_return_one_pdf_and_do_not_cache_it(self):
        for disposition in ("inline", "attachment"):
            with self.subTest(disposition=disposition):
                response = self.post(self.form(disposition=disposition, authorized_name="  Autorizado  "))
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.content, self.pdf)
                self.assertEqual(response.headers["content-type"], "application/pdf")
                self.assertEqual(response.headers["cache-control"], "no-store")
                self.assertEqual(response.headers["x-content-type-options"], "nosniff")
                self.assertEqual(response.headers["content-disposition"],
                                 f'{disposition}; filename="informe_mensual_completo_2026_07.pdf"')
                self.assertEqual(self.render.call_args.args[2:5], ([2, 1], 7, 2026))
                self.assertEqual(self.render.call_args.args[5]["authorized_name"], "Autorizado")

    def test_non_admin_cannot_prepare_or_post_even_with_an_existing_valid_form(self):
        form = self.form()
        for role in ("user", "viewer", "supervisor"):
            self.user.role = role
            with self.subTest(role=role):
                self.assertEqual(self.prepare().status_code, 403)
                self.assertEqual(self.post(form).status_code, 403)
        self.render.assert_not_called()

    def test_unauthenticated_requests_preserve_login_redirect(self):
        self.user = None
        for response in (self.prepare(), self.post()):
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/home")
        self.render.assert_not_called()

    def test_missing_wrong_and_non_ascii_csrf_tokens_are_rejected(self):
        form = self.form()
        for token in (None, "incorrect-token", "contraseña"):
            values = {key: value for key, value in form.items() if key != "token"}
            if token is not None:
                values["token"] = token
            with self.subTest(token=token):
                self.assertEqual(self.post(values).status_code, 403)
        self.render.assert_not_called()

    def test_invalid_selection_is_rejected_on_prepare_and_generate(self):
        form = self.form()
        for invalid in ({"month": "13"}, {"month": "abc"}, {"year": "1999"},
                        {"proposal_id": "999"}, {"proposal_id": "-1"}, {"proposal_id": []}):
            with self.subTest(invalid=invalid):
                self.assertEqual(self.prepare(**invalid).status_code, 400)
                self.assertEqual(self.post({**form, **invalid}).status_code, 400)
        self.render.assert_not_called()

    def test_zero_target_is_preserved_and_blank_target_remains_missing(self):
        response = self.post(self.form(target_1="0", target_2=""))
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.render.call_args.args[5]["targets"], {1: 0})

    def test_invalid_targets_text_length_and_disposition_do_not_render(self):
        form = self.form()
        for invalid in ({"target_1": "-1"}, {"target_1": "1.5"}, {"target_2": "4"},
                        {"target_1": "1000001"}, {"narrative": "x" * 20001}, {"disposition": "execute"},
                        {"letter_date": "2026-02-30"}, {"letter_signer_name": "x" * 201}):
            with self.subTest(invalid=list(invalid)):
                self.assertEqual(self.post({**form, **invalid}).status_code, 400)
        self.render.assert_not_called()

    def test_valid_manual_pdf_is_forwarded_and_disguised_upload_is_rejected(self):
        form = self.form()
        response = self.post(form, files={"staffing_pdf": ("plazas.pdf", self.pdf, "application/pdf")})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.render.call_args.args[5]["files"]["staffing_pdf"]["content"], self.pdf)
        self.render.reset_mock()
        response = self.post(form, files={"staffing_pdf": ("plazas.pdf", b"not a PDF", "application/pdf")})
        self.assertEqual(response.status_code, 400)
        self.render.assert_not_called()

    def test_file_and_aggregate_size_limits_are_enforced_before_generation(self):
        form = self.form()
        with patch.object(routes, "MAX_FILE_BYTES", len(self.pdf) - 1):
            response = self.post(form, files={"staffing_pdf": ("plazas.pdf", self.pdf)})
        self.assertEqual(response.status_code, 413)
        with patch.object(routes, "MAX_TOTAL_BYTES", len(self.pdf) * 2 - 1):
            response = self.post(form, files=[("staffing_pdf", ("plazas.pdf", self.pdf)),
                                              ("centers_pdf", ("centros.pdf", self.pdf))])
        self.assertEqual(response.status_code, 413)
        self.render.assert_not_called()

    def test_multiple_staffing_files_and_more_than_twenty_photos_are_rejected(self):
        form = self.form()
        for field, count in (("staffing_pdf", 2), ("photos", 21)):
            with self.subTest(field=field):
                response = self.post(form, files=[(field, (f"anexo{index}.pdf", self.pdf)) for index in range(count)])
                self.assertEqual(response.status_code, 400)
        self.render.assert_not_called()

    def test_request_body_limit_applies_to_chunked_requests_with_unknown_fields(self):
        form = self.form()
        boundary = "report-test-boundary"
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"token\"\r\n\r\n{form['token']}\r\n"
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"unexpected\"; filename=\"blob\"\r\n"
                "Content-Type: application/octet-stream\r\n\r\n").encode() + b"x" * (1024 * 1024 + 512)
        with patch.object(routes, "MAX_TOTAL_BYTES", 128):
            response = self.client.post("/ui/reports/completo/pdf", content=iter([body[:200], body[200:]]),
                                        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        self.assertEqual(response.status_code, 413)
        self.render.assert_not_called()

    def test_render_failure_does_not_return_internal_error_details_as_pdf(self):
        from app.services.report_pdf import PDFBackendUnavailableError, PDFRenderError

        form = self.form()
        for error, code in ((PDFBackendUnavailableError("No hay motor PDF"), 503),
                            (PDFRenderError("sensitive internal execution path"), 500)):
            self.render.side_effect = error
            with self.subTest(code=code):
                if code == 500:
                    with self.assertLogs(routes.logger, level="ERROR"):
                        response = self.post(form)
                else:
                    response = self.post(form)
                self.assertEqual(response.status_code, code)
                self.assertNotIn("sensitive internal execution path", response.text)
                self.assertNotEqual(response.headers["content-type"], "application/pdf")


if __name__ == "__main__":
    unittest.main()
