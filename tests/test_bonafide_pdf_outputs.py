from __future__ import annotations

import os
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from zipfile import ZipFile

os.environ.setdefault("DB_SERVER", "test-server")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-password")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-32-characters")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import automation_reports, reports
from app.services import full_monthly_report_pdf as full
from app.services.report_pdf import PDFBackendUnavailableError, PDFRenderError
from tests.test_full_monthly_bonafide_pagination import bonafide_context


class BonafidePdfOutputsTests(unittest.TestCase):
    def test_complete_report_uses_the_standalone_printable_sheet(self):
        context = bonafide_context(25)
        with patch.object(full, "render_template_to_chromium_pdf_bytes", return_value=b"%PDF-printable") as browser, \
             patch.object(full, "render_template_to_pdf_bytes", return_value=b"%PDF-legacy") as legacy:
            self.assertEqual(full._original("bonafide", context, "Autorizado"), b"%PDF-printable")
        args = browser.call_args.kwargs
        self.assertEqual(args["template_name"], "ui/reports/bonafide_pdf.html")
        self.assertEqual(args["context"], {**context, "authorized_name": "Autorizado"})
        self.assertTrue(args["prefer_chrome"])
        legacy.assert_not_called()

    def test_complete_bonafide_never_falls_back_to_the_crowded_format(self):
        for error in (PDFBackendUnavailableError("Browser unavailable"), PDFRenderError("Rendering failed")):
            with self.subTest(error=type(error).__name__), \
                 patch.object(full, "render_template_to_chromium_pdf_bytes", side_effect=error), \
                 patch.object(full, "render_template_to_pdf_bytes", return_value=b"%PDF-legacy") as legacy:
                with self.assertRaises(type(error)):
                    full._original("bonafide", bonafide_context(1), "")
                legacy.assert_not_called()

    def test_other_complete_sheets_keep_their_renderers_and_pagination(self):
        for template, chromium in (("no_duplicado", False), ("adm", False), ("visitas", True),
                                   ("embarazo", True), ("desercion_escolar", True), ("hoja_cotejo", True)):
            with self.subTest(template=template), \
                 patch.object(full, "render_template_to_chromium_pdf_bytes", return_value=b"%PDF-browser") as browser, \
                 patch.object(full, "render_template_to_pdf_bytes", return_value=b"%PDF-legacy") as legacy:
                self.assertEqual(full._original(template, {"rows": []}, "Firma"),
                                 b"%PDF-browser" if chromium else b"%PDF-legacy")
                selected, unused = (browser, legacy) if chromium else (legacy, browser)
                unused.assert_not_called()
                self.assertNotIn("prefer_chrome", selected.call_args.kwargs)
                if template in {"adm", "visitas", "embarazo", "hoja_cotejo"}:
                    self.assertEqual(selected.call_args.kwargs["template_name"], "ui/reports/full_monthly_sheet.html")

    def test_zip_downloads_keep_every_report_and_only_change_bonafide(self):
        for module, url in ((reports, "/todos/pdf"), (automation_reports, "/reports/todos/pdf")):
            with self.subTest(route=url):
                self.check_zip(module, url)

    def test_zip_downloads_report_browser_errors_without_legacy_bonafide(self):
        for module, url in ((reports, "/todos/pdf"), (automation_reports, "/reports/todos/pdf")):
            for error, status in ((PDFBackendUnavailableError("Browser unavailable"), 503),
                                  (PDFRenderError("Rendering failed"), 500)):
                with self.subTest(route=url, status=status):
                    self.check_zip(module, url, error, status)

    def check_zip(self, module, url, error=None, status=200):
        names = ["bonafide", "no_duplicado", "duplicado", "visitas", "por_programa", "hoja_cotejo",
                 "desercion_escolar", "embarazo", "notas", "vca", "adm"]
        bundle = {("desercion" if name == "desercion_escolar" else name):
                  {"residential_name": "Prueba", "selected_month": 8, "selected_year": 2026}
                  for name in names}
        user = SimpleNamespace(role="admin", user_id=1)
        app = FastAPI()
        app.include_router(module.router)
        app.dependency_overrides[module.get_db] = lambda: None
        if module is reports:
            app.dependency_overrides[reports.get_current_user] = lambda: user
        else:
            app.dependency_overrides[automation_reports.require_automation_access] = lambda: user
        with TestClient(app) as client, \
             patch.object(automation_reports, "_automation_user", return_value=user), \
             patch.object(module, "_build_all_reports_bundle_context", return_value=bundle) as build, \
             patch.object(module, "build_notes_pdf_chart_images", return_value={}), \
             patch.object(module, "render_template_to_chromium_pdf_bytes",
                          return_value=b"%PDF-printable", side_effect=error) as browser, \
             patch.object(module, "render_template_to_pdf_bytes",
                          side_effect=lambda **kw: ("%PDF-" + kw["template_name"]).encode()) as legacy:
            response = client.get(url + "?proposal_id=5&month=8&year=2026&employee_id=0")
        self.assertEqual(response.status_code, status)
        self.assertEqual(build.call_args.args[2], 5)
        browser.assert_called_once()
        self.assertTrue(browser.call_args.kwargs["prefer_chrome"])
        self.assertEqual(browser.call_args.kwargs["template_name"], "ui/reports/bonafide_pdf.html")
        if error:
            legacy.assert_not_called()
            self.assertNotEqual(response.headers["content-type"], "application/zip")
            return
        self.assertEqual(response.headers["content-type"], "application/zip")
        self.assertEqual(response.headers["content-disposition"],
                         'attachment; filename="todos_los_reportes_Prueba_2026_8.zip"')
        self.assertEqual(legacy.call_count, len(names) - 1)
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(archive.namelist(), [f"{name}_Prueba_2026_8.pdf" for name in names])
            self.assertEqual(archive.read("bonafide_Prueba_2026_8.pdf"), b"%PDF-printable")
            for name in names[1:]:
                self.assertEqual(archive.read(f"{name}_Prueba_2026_8.pdf"),
                                 f"%PDF-ui/reports/{name}_pdf.html".encode())


if __name__ == "__main__":
    unittest.main()
